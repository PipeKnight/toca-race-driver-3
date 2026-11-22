[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$Disc,
    [Parameter(Mandatory)][string]$DataDirectory,
    [Parameter(Mandatory)][string]$SetupDirectory,
    [string]$RoadAmericaDirectory,
    [switch]$Direct,
    [switch]$SetupOnly,
    [switch]$Fullscreen,
    [switch]$NoSave,
    [uint32]$FrameLimit
)

$ErrorActionPreference = 'Stop'
$sources = Import-PowerShellDataFile -LiteralPath (Join-Path $PSScriptRoot 'WindowsPreviewSources.psd1')
$play = Join-Path $PSScriptRoot 'Play-RecompiledToca.ps1'
$game = 'toca-slus-21182'
$setup = [IO.Path]::GetFullPath($SetupDirectory)
if ($setup.Length -gt [IO.Path]::GetPathRoot($setup).Length) { $setup = $setup.TrimEnd('\') }
$toolchain = Join-Path $setup 'tools'
$compiler = Join-Path $toolchain 'llvm-mingw\bin\clang++.exe'
$archives = Join-Path $PSScriptRoot 'sources'
$patches = @($sources.Patches | ForEach-Object { Join-Path $PSScriptRoot "patches\$_" })

function Get-SetupKey {
    $parts = @($sources.SetupRevision, $sources.Backend.SHA256, $sources.Chd.SHA256)
    $parts += @(Get-FileHash -LiteralPath $patches | Select-Object -ExpandProperty Hash)
    $sha = [Security.Cryptography.SHA256]::Create()
    try {
        $hash = $sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($parts -join "`n"))
        [BitConverter]::ToString($hash).Replace('-', '').Substring(0, 12).ToLowerInvariant()
    } finally {
        $sha.Dispose()
    }
}

function Install-Backend([string]$Destination) {
    foreach ($source in $sources.Backend, $sources.Chd) {
        $archive = Join-Path $archives $source.File
        if ((Get-FileHash -LiteralPath $archive).Hash -ne $source.SHA256) {
            throw "Source archive checksum mismatch for $($source.File)."
        }
    }

    $stage = Join-Path $setup ('.sources-' + [Guid]::NewGuid().ToString('N').Substring(0, 8))
    [void][IO.Directory]::CreateDirectory($stage)
    try {
        Add-Type -AssemblyName System.IO.Compression.FileSystem
        [IO.Compression.ZipFile]::ExtractToDirectory((Join-Path $archives $sources.Backend.File), $stage)
        $backendSource = Join-Path $stage $sources.Backend.Directory
        Copy-Item -LiteralPath (Join-Path $archives $sources.Chd.File) -Destination (Join-Path $backendSource 'libchdr.tar.gz')
        Push-Location -LiteralPath $backendSource
        try {
            & "$env:SystemRoot\System32\tar.exe" -xf libchdr.tar.gz
            if ($LASTEXITCODE -ne 0) { throw 'Could not extract the pinned libchdr archive.' }
            Remove-Item -LiteralPath (Join-Path $backendSource 'libchdr.tar.gz')

            # The upstream fetchers verify each preseeded archive before unpacking it.
            $seedDirectory = Join-Path $setup 'downloads'
            if (Test-Path -LiteralPath $seedDirectory -PathType Container) {
                $seedTarget = Join-Path $backendSource 'downloads'
                [void][IO.Directory]::CreateDirectory($seedTarget)
                foreach ($name in $sources.DependencyArchives) {
                    $seed = Join-Path $seedDirectory $name
                    if (Test-Path -LiteralPath $seed -PathType Leaf) { Copy-Item -LiteralPath $seed -Destination $seedTarget }
                }
            }
            & (Join-Path $backendSource 'scripts\portable.ps1') -Dir $toolchain
            if (!(Test-Path -LiteralPath $compiler -PathType Leaf)) { throw 'The portable toolchain is incomplete.' }

            $git = Join-Path $toolchain 'mingit\cmd\git.exe'
            $gitEnvironment = @{}
            $gitVariables = 'GIT_DIR', 'GIT_WORK_TREE', 'GIT_INDEX_FILE', 'GIT_COMMON_DIR', 'GIT_CEILING_DIRECTORIES'
            foreach ($name in $gitVariables) {
                $gitEnvironment[$name] = [Environment]::GetEnvironmentVariable($name, 'Process')
            }
            try {
                foreach ($name in $gitVariables) { [Environment]::SetEnvironmentVariable($name, $null, 'Process') }
                # Apply paths relative to the extracted sources even inside an existing Git checkout.
                $env:GIT_CEILING_DIRECTORIES = $stage
                foreach ($patch in $patches) {
                    & $git apply --no-index -- $patch
                    if ($LASTEXITCODE -ne 0) { throw "Could not apply $(Split-Path -Leaf $patch)." }
                }
            } finally {
                foreach ($name in $gitVariables) {
                    [Environment]::SetEnvironmentVariable($name, $gitEnvironment[$name], 'Process')
                }
            }
        } finally {
            Pop-Location
        }
        $resolvedSource = (Get-Item -LiteralPath $backendSource).FullName
        if ((Split-Path -Parent $resolvedSource) -ne $stage -or
            (Split-Path -Parent $Destination) -ne $setup -or (Test-Path -LiteralPath $Destination)) {
            throw 'Unexpected location for the staged backend.'
        }
        [IO.Directory]::Move($resolvedSource, $Destination)
    } finally {
        $staging = Get-Item -LiteralPath $stage -Force
        if ($staging.Parent.FullName -eq $setup -and !($staging.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
            Remove-Item -LiteralPath $staging.FullName -Recurse -Force
        }
    }
}

function Repair-CMakeCompilerDetection {
    if ($toolchain -notmatch '[[\]]') { return }

    # CMake 4.4.4 treats brackets in its own installation path as glob patterns.
    $module = Join-Path $toolchain 'cmake\share\cmake-4.4\Modules\CMakeCompilerIdDetection.cmake'
    $content = [IO.File]::ReadAllText($module)
    $compilerGlob = '${CMAKE_ROOT}/Modules/Compiler/*-'
    if (!$content.Contains($compilerGlob)) {
        if ($content.Contains('${compiler_module_root}/Modules/Compiler/*-')) { return }
        throw 'The portable CMake compiler detection module is unexpected.'
    }
    $declaration = 'function(compiler_id_detection outvar lang)'
    if (!$content.Contains($declaration)) { throw 'The portable CMake compiler detection function is missing.' }
    $updated = $content.Replace($declaration, @'
function(compiler_id_detection outvar lang)
  string(REGEX REPLACE "([][])" "[\\1]" compiler_module_root "${CMAKE_ROOT}")
'@).Replace($compilerGlob, '${compiler_module_root}/Modules/Compiler/*-')
    $staged = "$module.toca"
    [IO.File]::WriteAllText($staged, $updated)
    [IO.File]::Replace($staged, $module, [NullString]::Value)
}

function Invoke-TocaBuild([string]$Backend, [string]$DiscPath, [string]$DvdHash) {
    Repair-CMakeCompilerDetection
    $savedEnvironment = [Environment]::GetEnvironmentVariables('Process')
    Push-Location -LiteralPath $Backend
    try {
        & { . (Join-Path $toolchain 'env.ps1') -Quiet }
        $temp = Join-Path $setup 'temp'
        [void][IO.Directory]::CreateDirectory($temp)
        $env:TEMP = $temp
        $env:TMP = $temp
        $env:MSYSTEM = 'MINGW64'
        $env:CC = (Join-Path $toolchain 'llvm-mingw\bin\clang.exe').Replace('\', '/')
        $env:CXX = $compiler.Replace('\', '/')
        $env:PS2_JOBS = [Math]::Min(8, [Environment]::ProcessorCount)
        $env:PS2_PORT_DIRECT_ISO = '1'
        $env:PS2_LIBCHDR_DIR = (Join-Path $Backend $sources.Chd.Directory).Replace('\', '/')

        $buildArgs = @('scripts/port.sh', $game, $DiscPath.Replace('\', '/'), '--native-only', '--no-explore')
        if ($DvdHash) { $buildArgs += @('--dvd-sha256', $DvdHash) }
        & (Join-Path $toolchain 'mingit\usr\bin\bash.exe') @buildArgs | Out-Host
        return $LASTEXITCODE
    } finally {
        Pop-Location
        foreach ($name in @([Environment]::GetEnvironmentVariables('Process').Keys)) {
            if (!$savedEnvironment.Contains($name)) { [Environment]::SetEnvironmentVariable($name, $null, 'Process') }
        }
        foreach ($name in $savedEnvironment.Keys) {
            [Environment]::SetEnvironmentVariable($name, [string]$savedEnvironment[$name], 'Process')
        }
    }
}

if (!(Test-Path -LiteralPath $Disc)) {
    [Console]::Error.WriteLine("Disc source does not exist: $Disc")
    exit 2
}
$discPath = (Resolve-Path -LiteralPath $Disc).ProviderPath
$dvdHash = $null
if (Test-Path -LiteralPath $discPath -PathType Container) {
    $dvdHash = '437B2DD9D69F92487C996F783316170EA1D1E3700407D982F40F63C2DC8BD3ED'
} elseif ([IO.Path]::GetExtension($discPath) -ieq '.chd') {
    $dvdHash = '08C1F20904BB99067588F0AFF8637F0E97CBD46D2570F4A0247245E32E5DDF29'
} elseif ([IO.Path]::GetExtension($discPath) -ine '.iso') {
    [Console]::Error.WriteLine('Use an ISO, DVD CHD, or folder containing the extracted disc files.')
    exit 2
}

$lock = $null
$isoHandle = $null
try {
    $backend = Join-Path $setup ('backend-' + (Get-SetupKey))
    $runnerDirectory = Join-Path $backend "build\native-$game"
    $marker = Join-Path $backend '.toca-ready'
    $ready = (Test-Path -LiteralPath $marker -PathType Leaf) -and
             (Test-Path -LiteralPath (Join-Path $runnerDirectory 'ps2run.exe') -PathType Leaf) -and
             (Test-Path -LiteralPath (Join-Path $runnerDirectory 'SDL2.dll') -PathType Leaf) -and
             (Test-Path -LiteralPath $compiler -PathType Leaf)
    if (!$ready) {
        if ($Direct) { throw 'This build is not prepared. Run once without --direct to set up the game.' }
        if (!$dvdHash) {
            try {
                $isoHandle = [IO.File]::Open($discPath, 'Open', 'Read', 'Read')
            } catch {
                [Console]::Error.WriteLine("Could not open the ISO for read-only setup. $($_.Exception.Message)")
                exit 2
            }
            & $play -Disc $discPath -ValidateOnly
            if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        }

        [void][IO.Directory]::CreateDirectory($setup)
        $lock = [IO.File]::Open((Join-Path $setup '.toca-setup.lock'), 'OpenOrCreate', 'ReadWrite', 'None')
        if (!(Test-Path -LiteralPath $backend -PathType Container)) {
            Install-Backend $backend
        } elseif (!(Test-Path -LiteralPath $compiler -PathType Leaf) -or
                  !(Test-Path -LiteralPath (Join-Path $toolchain 'env.ps1') -PathType Leaf)) {
            & (Join-Path $backend 'scripts\portable.ps1') -Dir $toolchain
        }
        $buildExit = Invoke-TocaBuild $backend $discPath $dvdHash
        if ($buildExit -eq 2) { exit 2 }
        if ($buildExit -ne 0) { throw "The recompilation build exited with code $buildExit." }
        $elf = Join-Path $backend "games\$game\disc\SLUS_211.82"
        if ((Get-FileHash -LiteralPath $elf).Hash -ne '350EC46060655197F383DC15AB893231F575D99BFE03F40257AB476525B3B34E') {
            throw 'The extracted executable does not match SLUS-21182 v1.02.'
        }
        if (!(Test-Path -LiteralPath (Join-Path $runnerDirectory 'ps2run.exe') -PathType Leaf) -or
            !(Test-Path -LiteralPath (Join-Path $runnerDirectory 'SDL2.dll') -PathType Leaf)) {
            throw 'The build did not produce the Windows runner and its SDL dependency.'
        }
        [IO.File]::WriteAllText($marker, $game)
        Write-Host 'Setup completed.'
        if ($SetupOnly) { exit 0 }
    }
} catch {
    [Console]::Error.WriteLine("Windows setup failed. $($_.Exception.Message)")
    exit 3
} finally {
    if ($lock) { $lock.Dispose() }
    if ($isoHandle) { $isoHandle.Dispose() }
}

& $play -Disc $discPath -PreparedDirectory $runnerDirectory -DataDirectory $DataDirectory -CompilerPath $compiler `
    -RoadAmericaDirectory $RoadAmericaDirectory -Fullscreen:$Fullscreen -NoSave:$NoSave `
    -FrameLimit $FrameLimit -ValidateOnly:$SetupOnly
exit $LASTEXITCODE

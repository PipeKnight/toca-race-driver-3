[CmdletBinding()]
param(
    [Alias('Iso')]
    [string]$Disc,
    [switch]$Fullscreen,
    [switch]$NoSave,
    [uint32]$FrameLimit = 0,
    [string]$PreparedDirectory,
    [string]$DataDirectory,
    [string]$CompilerPath,
    [string]$RoadAmericaDirectory,
    [string]$DtmModDirectory,
    [switch]$ValidateOnly,
    [switch]$Help
)

if ($Help) {
    @'
Usage: Play-RecompiledToca.ps1 -Disc <path> [-PreparedDirectory <path>] [-DataDirectory <path>] [-Fullscreen] [-NoSave] [-FrameLimit <count>]

Launch the local Windows build for SLUS-21182 v1.02 from an ISO, DVD CHD, or extracted disc folder.
The launcher checks the DVD data or extracted-file layout's SHA-256 before starting the runner.
DVD CHD requires a runner built with libchdr. -Iso remains an alias for -Disc.
Use -PreparedDirectory to run a prepared copy containing ps2run.exe and its runtime files.
Use -DataDirectory to choose where to keep saves and runtime files.
Use -RoadAmericaDirectory to load a locally generated Road America add-on with its own memory card.
Use -DtmModDirectory to load local DTM overlays with a separate memory card.
The game uses its own portable memory card. Use -NoSave to run without a card.
Set -FrameLimit to close automatically after a fixed number of guest frames.
Set -ValidateOnly to check the disc without launching the runner.
See docs/native-recompilation.md for build instructions.
'@
    exit 0
}

$ErrorActionPreference = 'Stop'
if (!$Disc -or !(Test-Path -LiteralPath $Disc)) {
    [Console]::Error.WriteLine('Pass a SLUS-21182 v1.02 ISO, DVD CHD, or extracted disc folder with -Disc.')
    exit 2
}
$discPath = (Resolve-Path -LiteralPath $Disc).Path
$isFolder = Test-Path -LiteralPath $discPath -PathType Container
$isChd = !$isFolder -and [IO.Path]::GetExtension($discPath) -ieq '.chd'

function Quote-RunnerPath([string]$Path) {
    # Double trailing backslashes before the closing quote in a Windows command line.
    return '"' + ($Path -replace '(\\+)$', '$1$1') + '"'
}

$compiler = $CompilerPath
if (!$ValidateOnly -or $isFolder -or $isChd) {
    $root = Split-Path -Parent $PSScriptRoot
    $backend = Join-Path $root '.tools\ps2-native-recomp-0.0.5'
    if ($PreparedDirectory) {
        if (!(Test-Path -LiteralPath $PreparedDirectory -PathType Container)) {
            [Console]::Error.WriteLine('Pass an existing prepared directory with -PreparedDirectory.')
            exit 2
        }
        $gameDir = (Resolve-Path -LiteralPath $PreparedDirectory).Path
        $runner = Join-Path $gameDir 'ps2run.exe'
        $tempDir = Join-Path $gameDir 'temp'
    } else {
        $runner = Join-Path $backend 'build\native-toca-slus-21182\ps2run.exe'
        $gameDir = Join-Path $backend 'games\toca-slus-21182'
        if (!$compiler) { $compiler = Join-Path $backend 'tools\portable\llvm-mingw\bin\clang++.exe' }
        $tempDir = Join-Path $backend 'temp'
    }
    if (!(Test-Path -LiteralPath $runner -PathType Leaf) -or !(Test-Path -LiteralPath $gameDir -PathType Container)) {
        [Console]::Error.WriteLine('The local recompilation is incomplete. See docs/native-recompilation.md.')
        exit 3
    }
    if ($DataDirectory) {
        $gameDir = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($DataDirectory)
        $tempDir = Join-Path $gameDir 'temp'
    }

    $displayMode = if ($Fullscreen) { '--fullscreen' } else { '--window' }
    $runnerArgs = @('--disc', (Quote-RunnerPath $discPath), '--game-dir', (Quote-RunnerPath $gameDir), $displayMode)
    if ($RoadAmericaDirectory) {
        if (!(Test-Path -LiteralPath $RoadAmericaDirectory -PathType Container)) {
            [Console]::Error.WriteLine('Pass a generated Road America add-on directory.')
            exit 2
        }
        $addonPath = (Resolve-Path -LiteralPath $RoadAmericaDirectory).ProviderPath
        $runnerArgs += @('--road-america', (Quote-RunnerPath $addonPath))
    }
    if ($DtmModDirectory) {
        if (!(Test-Path -LiteralPath $DtmModDirectory -PathType Container)) {
            [Console]::Error.WriteLine('Pass a DTM mod directory.')
            exit 2
        }
        $dtmPath = (Resolve-Path -LiteralPath $DtmModDirectory).ProviderPath
        $runnerArgs += @('--dtm-mod', (Quote-RunnerPath $dtmPath))
    }
    if (!$NoSave) {
        $cardName = if ($RoadAmericaDirectory) { 'road-america.ps2' } else { 'toca-slus-21182.ps2' }
        if ($DtmModDirectory) {
            $cardName = if ($RoadAmericaDirectory) { 'road-america-dtm.ps2' } else { 'dtm-mod.ps2' }
        }
        $memoryCard = Join-Path $gameDir $cardName
        $runnerArgs += @('--memcard', (Quote-RunnerPath $memoryCard))
    }
    if ($FrameLimit) {
        $runnerArgs += @('--frames', $FrameLimit)
    }
}

$previousCompiler = $env:PS2_VU_CXX
$previousTemp = $env:TEMP
$previousTmp = $env:TMP
$previousEfuTiming = $env:PS2_TOCA_EFU_TIMING
$discHandle = $null
try {
    $expectedSize = 4697882624
    $expectedSha256 = if ($isFolder) {
        '437B2DD9D69F92487C996F783316170EA1D1E3700407D982F40F63C2DC8BD3ED'
    } else {
        '08C1F20904BB99067588F0AFF8637F0E97CBD46D2570F4A0247245E32E5DDF29'
    }
    try {
        if (!$isFolder) {
            $discHandle = [IO.File]::Open($discPath, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::Read)
        }
        if ($isChd -or $isFolder) {
            $decoder = [Diagnostics.Process]::new()
            $decoder.StartInfo.FileName = $runner
            $decoderFlag = if ($isFolder) { '--decode-dvd-folder' } else { '--decode-dvd-chd' }
            $decoder.StartInfo.Arguments = "$decoderFlag $(Quote-RunnerPath $discPath)"
            $decoder.StartInfo.UseShellExecute = $false
            $decoder.StartInfo.RedirectStandardOutput = $true
            $decoder.StartInfo.CreateNoWindow = $true
            try {
                if (!$decoder.Start()) { throw 'Could not start the DVD reader.' }
                $decoded = $decoder.StandardOutput.BaseStream
                try {
                    $decodedSha256 = (Get-FileHash -InputStream $decoded -Algorithm SHA256).Hash
                } finally {
                    $decoded.Dispose()
                }
                $decoder.WaitForExit()
                $supported = $decoder.ExitCode -eq 0 -and $decodedSha256 -eq $expectedSha256
            } finally {
                $decoder.Dispose()
            }
        } else {
            $supported = $discHandle.Length -eq $expectedSize -and
                (Get-FileHash -InputStream $discHandle -Algorithm SHA256).Hash -eq $expectedSha256
        }
    } catch {
        [Console]::Error.WriteLine("Could not read the disc for validation. $($_.Exception.Message)")
        exit 2
    }
    if (!$supported) {
        [Console]::Error.WriteLine("Unsupported disc source. Expected SLUS-21182 v1.02 with $expectedSize decoded bytes and SHA-256 $expectedSha256.")
        exit 2
    }
    if ($ValidateOnly) { exit 0 }

    New-Item -ItemType Directory -Path $tempDir -Force | Out-Null
    if ($compiler -and (Test-Path -LiteralPath $compiler -PathType Leaf)) {
        $env:PS2_VU_CXX = $compiler
    }
    $env:TEMP = $tempDir
    $env:TMP = $tempDir
    if (!$previousEfuTiming) {
        $env:PS2_TOCA_EFU_TIMING = '1'
    }
    $startInfo = [Diagnostics.ProcessStartInfo]::new($runner, ($runnerArgs -join ' '))
    $startInfo.WorkingDirectory = $gameDir
    $startInfo.UseShellExecute = $false
    $process = [Diagnostics.Process]::Start($startInfo)
    try {
        $process.WaitForExit()
        $exitCode = $process.ExitCode
    } finally {
        $process.Dispose()
    }
} finally {
    if ($discHandle) {
        $discHandle.Dispose()
    }
    $env:PS2_VU_CXX = $previousCompiler
    $env:TEMP = $previousTemp
    $env:TMP = $previousTmp
    $env:PS2_TOCA_EFU_TIMING = $previousEfuTiming
}
exit $exitCode

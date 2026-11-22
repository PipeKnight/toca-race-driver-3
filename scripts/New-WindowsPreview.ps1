[CmdletBinding()]
param(
    [string]$Destination = (Join-Path (Split-Path -Parent $PSScriptRoot) 'build\windows-preview-x64'),
    [string]$ArchiveCache = (Join-Path (Split-Path -Parent $PSScriptRoot) '.tools\downloads')
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$sources = Import-PowerShellDataFile -LiteralPath (Join-Path $PSScriptRoot 'WindowsPreviewSources.psd1')
$compiler = Join-Path $env:SystemRoot 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'
if (!(Test-Path -LiteralPath $compiler -PathType Leaf)) { throw 'The Windows .NET Framework C# compiler is unavailable.' }

$destinationPath = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($Destination)
$cachePath = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($ArchiveCache)
$support = Join-Path $destinationPath 'support'
foreach ($directory in $cachePath, (Join-Path $support 'sources'), (Join-Path $support 'patches')) {
    [void][IO.Directory]::CreateDirectory($directory)
}

foreach ($source in $sources.Backend, $sources.Chd) {
    $archive = Join-Path $cachePath $source.File
    if (!(Test-Path -LiteralPath $archive -PathType Leaf)) {
        $download = "$archive.$([Guid]::NewGuid().ToString('N')).part"
        try {
            Invoke-WebRequest -UseBasicParsing -Uri $source.Url -OutFile $download
            if ((Get-FileHash -LiteralPath $download).Hash -ne $source.SHA256) {
                throw "Downloaded source checksum mismatch for $($source.File)."
            }
            Move-Item -LiteralPath $download -Destination $archive
        } finally {
            if (Test-Path -LiteralPath $download -PathType Leaf) { Remove-Item -LiteralPath $download -Force }
        }
    }
    if ((Get-FileHash -LiteralPath $archive).Hash -ne $source.SHA256) {
        throw "Cached source checksum mismatch for $($source.File)."
    }
    Copy-Item -LiteralPath $archive -Destination (Join-Path $support 'sources') -Force
}

foreach ($name in 'Launch-Windows.ps1', 'Play-RecompiledToca.ps1', 'WindowsPreviewSources.psd1') {
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot $name) -Destination $support -Force
}
foreach ($name in @($sources.Patches) + 'LICENSE') {
    Copy-Item -LiteralPath (Join-Path $root "patches\$name") -Destination (Join-Path $support 'patches') -Force
}

$exe = Join-Path $destinationPath 'TocaRecomp.exe'
& $compiler /nologo /optimize+ /target:exe /platform:x64 "/out:$exe" (Join-Path $PSScriptRoot 'TocaRecomp.cs')
if ($LASTEXITCODE -ne 0) { throw "Could not build the Windows launcher (exit code $LASTEXITCODE)." }
Write-Host "Windows preview package built in $destinationPath"

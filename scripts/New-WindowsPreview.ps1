[CmdletBinding()]
param(
    [string]$Destination,
    [string]$ArchiveCache
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
if (!$Destination) { $Destination = Join-Path $root 'build\windows-preview-x64' }
if (!$ArchiveCache) { $ArchiveCache = Join-Path $root '.tools\downloads' }
$sources = Import-PowerShellDataFile -LiteralPath (Join-Path $PSScriptRoot 'WindowsPreviewSources.psd1')
$compiler = Join-Path $env:SystemRoot 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'
if (!(Test-Path -LiteralPath $compiler -PathType Leaf)) { throw 'The Windows .NET Framework C# compiler is unavailable.' }

$destinationPath = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($Destination)
$cachePath = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($ArchiveCache)
[void][IO.Directory]::CreateDirectory($cachePath)
$resources = [ordered]@{}

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
    $resources["support/sources/$($source.File)"] = $archive
}

foreach ($name in 'Launch-Windows.ps1', 'Play-RecompiledToca.ps1', 'WindowsPreviewSources.psd1') {
    $resources["support/$name"] = Join-Path $PSScriptRoot $name
}
foreach ($name in @($sources.Patches) + 'LICENSE') {
    $resources["support/patches/$name"] = Join-Path $root "patches\$name"
}
$resources['support/README.md'] = Join-Path $root 'docs\windows-preview-release-notes.md'

[void][IO.Directory]::CreateDirectory($destinationPath)
$exe = Join-Path $destinationPath 'TocaRecomp.exe'
$stage = Join-Path $destinationPath ('.TocaRecomp-' + [Guid]::NewGuid().ToString('N'))
$response = "$stage.rsp"
$stagedExe = "$stage.exe"
$options = @('/nologo', '/optimize+', '/target:exe', '/platform:x64', "/out:`"$stagedExe`"")
foreach ($resource in $resources.GetEnumerator()) {
    $options += "/resource:`"$($resource.Value)`",$($resource.Key),private"
}
$options += '"' + (Join-Path $PSScriptRoot 'TocaRecomp.cs') + '"'
try {
    [IO.File]::WriteAllLines($response, [string[]]$options, [Text.Encoding]::UTF8)
    & $compiler "@$response"
    if ($LASTEXITCODE -ne 0) { throw "Could not build the Windows launcher (exit code $LASTEXITCODE)." }
    for ($attempt = 1; ; $attempt++) {
        try {
            if ([IO.File]::Exists($exe)) {
                [IO.File]::Replace($stagedExe, $exe, [NullString]::Value, $true)
            } else {
                [IO.File]::Move($stagedExe, $exe)
            }
            break
        } catch [IO.IOException] {
            if ($attempt -ge 10 -or ![IO.File]::Exists($stagedExe)) { throw }
            Start-Sleep -Milliseconds 200
        }
    }
} finally {
    [IO.File]::Delete($response)
    [IO.File]::Delete($stagedExe)
}
Write-Host "Windows preview executable built at $exe"

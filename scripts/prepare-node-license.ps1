# Recover the license for an installed official Node binary without changing it.
[CmdletBinding()]
param([string]$NodePath = (Join-Path $env:ProgramFiles 'nodejs\node.exe'))
$ErrorActionPreference = 'Stop'
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$version = (& $NodePath --version).Trim()
if ($LASTEXITCODE -ne 0 -or $version -notmatch '^v\d+\.\d+\.\d+$') { throw 'Unexpected Node version.' }
$name = "node-$version-win-x64"
$folder = Join-Path $root ".build\node-license\$version"
New-Item -ItemType Directory -Force -Path $folder | Out-Null
$zipPath = Join-Path $folder "$name.zip"
$base = "https://nodejs.org/dist/$version"
# Restrict downloads to the fixed official origin, and verify its release checksum.
$checksums = (Invoke-WebRequest -Uri "$base/SHASUMS256.txt" -UseBasicParsing).Content
$match = [regex]::Match([string]$checksums, "(?m)^([a-fA-F0-9]{64})\s+" + [regex]::Escape("$name.zip") + '\r?$')
if (-not $match.Success) { throw 'Official release checksum was not found.' }
if (-not (Test-Path -LiteralPath $zipPath)) {
    Invoke-WebRequest -Uri "$base/$name.zip" -OutFile $zipPath -UseBasicParsing
}
if ((Get-FileHash -LiteralPath $zipPath -Algorithm SHA256).Hash -ne $match.Groups[1].Value) {
    throw 'Node archive checksum mismatch; refusing to use it.'
}
Add-Type -AssemblyName System.IO.Compression.FileSystem
$archive = [IO.Compression.ZipFile]::OpenRead($zipPath)
try {
    $binaryEntry = $archive.GetEntry("$name/node.exe")
    $licenseEntry = $archive.GetEntry("$name/LICENSE")
    if (-not $binaryEntry -or -not $licenseEntry) { throw 'Official archive lacks Node or LICENSE.' }
    $stream = $binaryEntry.Open()
    $sha = [Security.Cryptography.SHA256]::Create()
    try { $binaryHash = [BitConverter]::ToString($sha.ComputeHash($stream)).Replace('-', '') }
    finally { $stream.Dispose(); $sha.Dispose() }
    if ($binaryHash -ne (Get-FileHash -LiteralPath $NodePath -Algorithm SHA256).Hash) {
        throw 'Installed node.exe is not byte-identical to the official release. No license copied.'
    }
    $license = Join-Path $folder 'LICENSE'
    [IO.Compression.ZipFileExtensions]::ExtractToFile($licenseEntry, $license, $true)
    Write-Output $license
} finally { $archive.Dispose() }

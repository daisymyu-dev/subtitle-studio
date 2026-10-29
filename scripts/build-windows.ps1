[CmdletBinding()]
param(
    [string]$Python = (Join-Path $PSScriptRoot '..\.build\venv\Scripts\python.exe'),
    [string]$NodePath = (Join-Path $env:ProgramFiles 'nodejs\node.exe'),
    [string]$NodeLicensePath,
    [switch]$WithoutNode,
    [switch]$EnableASR,
    [switch]$InstallDependencies
)
$ErrorActionPreference = 'Stop'
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$bundle = if ($EnableASR) { 'SubtitleStudio-ASR-Internal' } else { 'SubtitleStudio-Core' }
$output = Join-Path $root "dist\$bundle"
$work = if ($EnableASR) { '.build\pyinstaller-asr' } else { '.build\pyinstaller-core' }
# PyInstaller replaces its generated COLLECT folder on rebuild. Validate that
# exact target before allowing its recursive cleanup; never follow a junction
# or clean a directory that contains application/user state.
$expectedOutput = [IO.Path]::GetFullPath((Join-Path $root "dist\$bundle"))
if ([IO.Path]::GetFullPath($output) -ne $expectedOutput) { throw 'Unexpected build output target.' }
foreach ($path in @($root, (Join-Path $root 'dist'), $output)) {
    if ((Test-Path -LiteralPath $path) -and
        ((Get-Item -LiteralPath $path -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)) {
        throw 'Build output must not contain junctions or symbolic links.'
    }
}
if (Test-Path -LiteralPath $output) {
    if ((Resolve-Path -LiteralPath $output).Path -ne $expectedOutput -or
        -not (Test-Path -LiteralPath (Join-Path $output 'BUILD-DEPENDENCIES.txt'))) {
        throw 'Refusing to replace an unrecognized output directory.'
    }
    foreach ($name in @('results', '.work', '.uploads', '.models', '.git', 'learning.sqlite3', 'studio.log')) {
        if (Test-Path -LiteralPath (Join-Path $output $name)) { throw 'Refusing to replace an output containing user state.' }
    }
    if (Get-ChildItem -LiteralPath $output -Recurse -Force | Where-Object { $_.Attributes -band [IO.FileAttributes]::ReparsePoint } | Select-Object -First 1) {
        throw 'Refusing recursive build cleanup through reparse points.'
    }
    Write-Host "Validated generated rebuild target: $expectedOutput"
}
Push-Location $root
try {
    if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
        throw 'Build Python is missing. Create .build/venv first; see docs/build.md.'
    }
    New-Item -ItemType Directory -Force -Path (Join-Path $root '.build\tmp') | Out-Null
    $env:TEMP = $env:TMP = Join-Path $root '.build\tmp'
    & $Python -c "import struct,sys; assert sys.platform == 'win32' and struct.calcsize('P') == 8; assert sys.version_info[:2] == (3,12)"
    if ($LASTEXITCODE -ne 0) { throw 'Use 64-bit Python 3.12 on Windows.' }
    if ($InstallDependencies) {
        & $Python -m pip install --index-url https://pypi.org/simple -r requirements-build.txt
        if ($LASTEXITCODE -ne 0) { throw 'Build dependency install failed.' }
        if ($EnableASR) {
            & $Python -m pip install --index-url https://pypi.org/simple -r requirements-asr.txt -c requirements-lock.txt
            if ($LASTEXITCODE -ne 0) { throw 'Optional internal ASR install failed.' }
        }
    }
    & $Python -m pip check
    if ($LASTEXITCODE -ne 0) { throw 'Build dependency validation failed.' }

    Remove-Item Env:SUBTITLE_STUDIO_BUILD_NODE -ErrorAction SilentlyContinue
    Remove-Item Env:SUBTITLE_STUDIO_BUILD_NODE_LICENSE -ErrorAction SilentlyContinue
    $env:SUBTITLE_STUDIO_BUILD_ASR = if ($EnableASR) { '1' } else { '0' }
    if ($EnableASR) { Write-Warning 'INTERNAL ASR BUILD ONLY. Codec license/corresponding-source review is unresolved. Do not publish this output.' }
    if (-not $WithoutNode -and (Test-Path -LiteralPath $NodePath -PathType Leaf)) {
        if (-not $NodeLicensePath) { $NodeLicensePath = Join-Path (Split-Path $NodePath) 'LICENSE' }
        if (-not (Test-Path -LiteralPath $NodeLicensePath -PathType Leaf)) {
            throw 'Node LICENSE is missing. Use prepare-node-license.ps1 or explicitly build -WithoutNode.'
        }
        if ((Split-Path -Leaf $NodeLicensePath) -ne 'LICENSE') { throw 'Node license file must be named LICENSE.' }
        $env:SUBTITLE_STUDIO_BUILD_NODE = (Resolve-Path -LiteralPath $NodePath).Path
        $env:SUBTITLE_STUDIO_BUILD_NODE_LICENSE = (Resolve-Path -LiteralPath $NodeLicensePath).Path
    }
    & $Python -m PyInstaller --noconfirm --distpath dist --workpath $work scripts\SubtitleStudio.spec
    if ($LASTEXITCODE -ne 0) { throw 'PyInstaller build failed.' }
    Copy-Item -LiteralPath launch.cmd -Destination (Join-Path $output 'launch.cmd')
    foreach ($directory in @('docs', 'examples')) {
        if (Test-Path -LiteralPath $directory) {
            Copy-Item -LiteralPath $directory -Destination $output -Recurse -Force
        }
    }
    foreach ($name in @('README.md', 'LICENSE', 'THIRD_PARTY_NOTICES.md', 'THIRD_PARTY_NOTICES', 'PRIVACY.md', 'SECURITY.md')) {
        if (Test-Path -LiteralPath $name) { Copy-Item -LiteralPath $name -Destination (Join-Path $output $name) }
    }
    if ($env:SUBTITLE_STUDIO_BUILD_NODE_LICENSE) {
        $nodeNotice = Join-Path $output 'licenses\node'
        New-Item -ItemType Directory -Force -Path $nodeNotice | Out-Null
        Copy-Item -LiteralPath $env:SUBTITLE_STUDIO_BUILD_NODE_LICENSE -Destination (Join-Path $nodeNotice 'LICENSE')
    }
    & $Python -m pip freeze --all | Out-File -LiteralPath (Join-Path $output 'BUILD-DEPENDENCIES.txt') -Encoding utf8
    & $Python scripts\build-notices.py $output
    if ($LASTEXITCODE -ne 0) { throw 'Bundled license inventory failed.' }
    if (-not $EnableASR -and -not $WithoutNode) {
        & $Python scripts\verify-bundle.py $output
        if ($LASTEXITCODE -ne 0) { throw 'Core bundle integrity verification failed.' }
    }
    Write-Host "Built dist/$bundle. Keep the EXE and _internal folder together."
} finally {
    Remove-Item Env:SUBTITLE_STUDIO_BUILD_NODE -ErrorAction SilentlyContinue
    Remove-Item Env:SUBTITLE_STUDIO_BUILD_NODE_LICENSE -ErrorAction SilentlyContinue
    Remove-Item Env:SUBTITLE_STUDIO_BUILD_ASR -ErrorAction SilentlyContinue
    Pop-Location
}

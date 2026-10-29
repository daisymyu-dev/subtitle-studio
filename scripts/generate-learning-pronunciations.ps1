[CmdletBinding()]
param(
    [switch]$Force,
    [string]$NodePath = 'C:\Program Files\nodejs\node.exe'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# No output-directory parameter: only this project's fixed canonical WAV paths.
$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$webRoot = [IO.Path]::GetFullPath((Join-Path $projectRoot 'web'))
$outputDirectory = [IO.Path]::GetFullPath((Join-Path $webRoot 'pronunciations'))
$expectedDirectory = $webRoot + [IO.Path]::DirectorySeparatorChar + 'pronunciations'
if (-not [IO.Path]::IsPathRooted($outputDirectory) -or
    -not [string]::Equals($outputDirectory, $expectedDirectory, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Output must be the absolute project web/pronunciations directory.'
}

function Assert-NoReparsePoint([string]$Path) {
    $current = [IO.Path]::GetFullPath($Path)
    while ($current) {
        if (Test-Path -LiteralPath $current) {
            $item = Get-Item -LiteralPath $current -Force
            if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
                throw "Refusing reparse point in owned output path: $current"
            }
        }
        $parent = [IO.Path]::GetDirectoryName($current)
        if ($parent -eq $current) { break }
        $current = $parent
    }
}

Assert-NoReparsePoint $outputDirectory
if (-not (Test-Path -LiteralPath $NodePath -PathType Leaf)) { throw 'Local Node.js executable not found.' }

# Send only ASCII canonical IDs/spoken text through stdout, not IPA or executable PS.
$readManifest = @'
const path = require('node:path');
const root = process.argv[1];
const dictionary = require(path.join(root, 'web/learning-pronunciations.js'));
const lexicon = require(path.join(root, 'web/learning-lexicon.js'));
const ids = lexicon.map(item => item.id).sort();
const keys = Object.keys(dictionary).sort();
if (Object.getPrototypeOf(dictionary) !== Object.prototype || ids.length !== 24 ||
    new Set(ids).size !== 24 || JSON.stringify(ids) !== JSON.stringify(keys)) {
  throw Error('Manifest must have exactly the current 24 canonical IDs.');
}
const rows = ids.map(id => {
  const entry = dictionary[id];
  if (!/^[a-z][a-z0-9-]*$/.test(id) || entry.audio !== '/pronunciations/' + id + '.wav' ||
      typeof entry.spoken !== 'string' || !/^[A-Za-z][A-Za-z .,'-]*[A-Za-z.]$/.test(entry.spoken)) {
    throw Error('Unsafe canonical pronunciation entry: ' + id);
  }
  return {id, spoken: entry.spoken, audio: entry.audio};
});
process.stdout.write(JSON.stringify(rows));
'@
$json = & $NodePath -e $readManifest $projectRoot
if ($LASTEXITCODE -ne 0) { throw 'Local pronunciation manifest validation failed.' }
$entries = @((($json -join [Environment]::NewLine) | ConvertFrom-Json))
if ($entries.Count -ne 24) { throw 'Expected 24 canonical pronunciation entries.' }

# Validate ALL targets before creating or touching any file, including with -Force.
$targets = @()
foreach ($entry in $entries) {
    $target = [IO.Path]::GetFullPath((Join-Path $outputDirectory ($entry.id + '.wav')))
    if (-not [string]::Equals([IO.Path]::GetDirectoryName($target), $outputDirectory,
        [StringComparison]::OrdinalIgnoreCase)) { throw 'Audio target escaped the owned directory.' }
    Assert-NoReparsePoint $target
    if (Test-Path -LiteralPath $target) {
        if (-not (Test-Path -LiteralPath $target -PathType Leaf)) { throw "Not a regular audio file: $target" }
        if (-not $Force) { throw "Refusing to overwrite existing pronunciation assets. Use -Force explicitly: $target" }
    }
    $targets += [pscustomobject]@{ Id = $entry.id; Spoken = $entry.spoken; Path = $target }
}

Add-Type -AssemblyName System.Speech
$synthesizer = New-Object System.Speech.Synthesis.SpeechSynthesizer
$results = @()
try {
    $synthesizer.SelectVoice('Microsoft Zira Desktop')
    if ($synthesizer.Voice.Name -ne 'Microsoft Zira Desktop' -or $synthesizer.Voice.Culture.Name -ne 'en-US') {
        throw 'The required Microsoft Zira Desktop en-US voice is unavailable; no fallback is allowed.'
    }
    $synthesizer.Rate = -1
    $synthesizer.Volume = 100
    $format = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo -ArgumentList @(
        22050, [System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen,
        [System.Speech.AudioFormat.AudioChannel]::Mono
    )
    Assert-NoReparsePoint $outputDirectory
    [IO.Directory]::CreateDirectory($outputDirectory) | Out-Null
    foreach ($target in $targets) {
        Assert-NoReparsePoint $target.Path
        if (-not $Force) {
            # Exclusive reservation prevents silently replacing a newly appeared file.
            # SetOutputToWaveFile then writes the empty file reserved by this invocation.
            $reservation = [IO.File]::Open($target.Path, [IO.FileMode]::CreateNew,
                [IO.FileAccess]::Write, [IO.FileShare]::None)
            $reservation.Dispose()
        }
        try {
            $synthesizer.SetOutputToWaveFile($target.Path, $format)
            $synthesizer.Speak($target.Spoken)
        }
        finally {
            $synthesizer.SetOutputToNull()
        }

        # Read RIFF chunks rather than assuming every encoder uses a 44-byte header.
        $reader = [IO.BinaryReader]::new([IO.File]::OpenRead($target.Path))
        try {
            $length = $reader.BaseStream.Length
            if ([Text.Encoding]::ASCII.GetString($reader.ReadBytes(4)) -ne 'RIFF') { throw 'Missing RIFF header.' }
            if ($reader.ReadUInt32() + 8 -ne $length) { throw 'Incomplete RIFF output.' }
            if ([Text.Encoding]::ASCII.GetString($reader.ReadBytes(4)) -ne 'WAVE') { throw 'Missing WAVE format.' }
            $dataBytes = 0
            while ($reader.BaseStream.Position + 8 -le $length) {
                $chunk = [Text.Encoding]::ASCII.GetString($reader.ReadBytes(4))
                $size = $reader.ReadUInt32()
                $next = $reader.BaseStream.Position + $size + ($size % 2)
                if ($next -gt $length) { throw 'Truncated WAVE chunk.' }
                if ($chunk -eq 'data') { $dataBytes += $size }
                $reader.BaseStream.Position = $next
            }
            if ($dataBytes -le 0) { throw 'The generated pronunciation is empty.' }
        }
        finally { $reader.Dispose() }
        $results += [pscustomobject]@{
            Id = $target.Id; Voice = $synthesizer.Voice.Name; Culture = $synthesizer.Voice.Culture.Name
            Rate = $synthesizer.Rate; SampleRate = 22050; Bits = 16; Channels = 1
            Seconds = [Math]::Round($dataBytes / 44100.0, 4); Bytes = $length
            Sha256 = (Get-FileHash -LiteralPath $target.Path -Algorithm SHA256).Hash.ToLowerInvariant()
            Path = $target.Path
        }
    }
}
finally { $synthesizer.Dispose() }

$results | ConvertTo-Json -Depth 3

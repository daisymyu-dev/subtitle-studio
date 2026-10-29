'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const crypto = require('node:crypto');
const {spawnSync} = require('node:child_process');
const lexicon = require('../web/learning-lexicon.js');
const project = path.resolve(__dirname, '..');
const manifestPath = path.join(project, 'web/learning-pronunciations.js');
const generatorPath = path.join(project, 'scripts/generate-learning-pronunciations.ps1');
const provenancePath = path.join(project, 'docs/pronunciation-sources.md');

function manifest() {
  assert.ok(fs.existsSync(manifestPath), 'Missing offline pronunciation manifest');
  return require(manifestPath);
}

function waveInfo(bytes, id) {
  assert.ok(bytes.length > 44, id + ': a populated WAVE file');
  assert.equal(bytes.toString('ascii', 0, 4), 'RIFF', id);
  assert.equal(bytes.toString('ascii', 8, 12), 'WAVE', id);
  assert.equal(bytes.readUInt32LE(4) + 8, bytes.length, id + ': complete RIFF length');
  let format, data;
  let offset = 12;
  while (offset + 8 <= bytes.length) {
    const type = bytes.toString('ascii', offset, offset + 4);
    const size = bytes.readUInt32LE(offset + 4);
    const start = offset + 8;
    assert.ok(start + size <= bytes.length, id + ': complete ' + type + ' chunk');
    if (type === 'fmt ') {
      assert.ok(size >= 16, id + ': PCM format');
      format = {
        encoding: bytes.readUInt16LE(start), channels: bytes.readUInt16LE(start + 2),
        sampleRate: bytes.readUInt32LE(start + 4), byteRate: bytes.readUInt32LE(start + 8),
        blockAlign: bytes.readUInt16LE(start + 12), bits: bytes.readUInt16LE(start + 14)
      };
    }
    if (type === 'data') data = bytes.subarray(start, start + size);
    offset = start + size + (size % 2);
  }
  assert.equal(offset, bytes.length, id + ': no truncated trailing chunks');
  assert.ok(format && data && data.length, id + ': format and nonempty audio');
  assert.deepEqual(format, {encoding: 1, channels: 1, sampleRate: 22050,
    byteRate: 44100, blockAlign: 2, bits: 16}, id + ': portable mono PCM');
  assert.equal(data.length % format.blockAlign, 0, id + ': complete samples');
  let peak = 0;
  for (let i = 0; i < data.length; i += 2) peak = Math.max(peak, Math.abs(data.readInt16LE(i)));
  assert.ok(peak > 100, id + ': not a silent placeholder');
  const seconds = data.length / format.byteRate;
  assert.ok(seconds >= 0.25 && seconds < 10, id + ': short clip, ' + seconds + 's');
  return {seconds, bytes: bytes.length};
}

test('offline UMD pronunciation dictionary is a plain object for exactly the current 24 canonical IDs', () => {
  const dictionary = manifest();
  assert.equal(Object.getPrototypeOf(dictionary), Object.prototype);
  assert.equal(lexicon.length, 24);
  assert.deepEqual(Object.keys(dictionary).sort(), lexicon.map(entry => entry.id).sort());
  const source = fs.readFileSync(manifestPath, 'utf8');
  const browser = {window: {}};
  vm.runInNewContext(source, browser);
  assert.deepEqual(JSON.parse(JSON.stringify(browser.window.LearningPronunciations)), dictionary);
  const withoutWindow = {};
  vm.runInNewContext(source, withoutWindow);
  assert.deepEqual(JSON.parse(JSON.stringify(withoutWindow.LearningPronunciations)), dictionary);
});

test('every ID has only canonical spoken text, US reference IPA, a primary source and a fixed safe local audio path', () => {
  for (const [id, entry] of Object.entries(manifest())) {
    assert.deepEqual(Object.keys(entry).sort(), ['audio', 'canonical', 'ipa', 'source', 'spoken']);
    for (const field of ['ipa', 'spoken', 'canonical', 'source']) {
      assert.equal(typeof entry[field], 'string', id + ': ' + field);
      assert.ok(entry[field].trim(), id + ': ' + field);
      assert.equal(entry[field], entry[field].trim(), id + ': trimmed ' + field);
    }
    assert.match(entry.ipa, /^\/[^\r\n]+\/$/u, id + ': delimited reference IPA');
    assert.match(entry.ipa, /[ɪʊəɚɝæɑɔʌɛθðʃʒŋˈˌː]/u, id + ': phonetic notation');
    assert.match(entry.spoken, /^[A-Za-z][A-Za-z .,'’-]*[A-Za-z.]$/, id + ': natural English, no slash or markup');
    const source = new URL(entry.source);
    assert.equal(source.protocol, 'https:');
    assert.equal(source.hostname, 'dictionary.cambridge.org');
    assert.match(source.pathname, /^\/(?:us\/)?(?:dictionary|pronunciation)\/english\/[a-z-]+$/);
    assert.equal(source.search + source.hash, '');
    assert.match(id, /^[a-z][a-z0-9-]*$/);
    assert.equal(entry.audio, '/pronunciations/' + id + '.wav');
    const absolute = path.resolve(project, 'web', '.' + entry.audio);
    assert.equal(path.dirname(absolute), path.join(project, 'web/pronunciations'));
    if (!['glass-half', 'nimby'].includes(id)) {
      const normalize = text => text.toLowerCase().replace(/-/g, ' ').replace(/[.!]$/g, '');
      assert.equal(normalize(entry.canonical), normalize(lexicon.find(item => item.id === id).term), id);
      assert.equal(normalize(entry.spoken), normalize(entry.canonical), id);
    }
  }
});

test('alternatives are two spoken sentences and difficult US headwords keep the referenced canonical phonetics', () => {
  const dictionary = manifest();
  assert.equal(dictionary['glass-half'].canonical, 'glass half full / glass half empty');
  assert.equal(dictionary['glass-half'].spoken, 'Glass half full. Glass half empty.');
  assert.equal(dictionary.nimby.canonical, 'not in my backyard / NIMBY');
  assert.equal(dictionary.nimby.spoken, 'Not in my backyard. Nimby.');
  assert.match(dictionary.nimby.ipa, /ˈnɪm\.bi/u);
  assert.equal(dictionary.bifurcated.ipa, '/ˈbaɪ.fɚ.keɪ.tɪd/');
  assert.equal(dictionary.otherworldly.ipa, '/ˌʌð.ɚˈwɝːld.li/');
  assert.equal(dictionary.ensued.ipa, '/ɪnˈsuːd/');
});

test('all 24 canonical assets are real, non-silent, short RIFF/WAVE PCM files with no missing or extra WAVs', () => {
  const dictionary = manifest();
  const directory = path.join(project, 'web/pronunciations');
  assert.ok(fs.existsSync(directory), 'Missing generated offline pronunciation assets');
  assert.deepEqual(fs.readdirSync(directory).filter(name => /\.wav$/i.test(name)).sort(),
    Object.keys(dictionary).map(id => id + '.wav').sort());
  const digests = new Set();
  for (const [id, entry] of Object.entries(dictionary)) {
    const file = path.join(directory, id + '.wav');
    assert.ok(fs.existsSync(file), entry.audio);
    assert.ok(!fs.lstatSync(file).isSymbolicLink(), id + ': owned regular asset');
    const bytes = fs.readFileSync(file);
    waveInfo(bytes, id);
    digests.add(crypto.createHash('sha256').update(bytes).digest('hex'));
  }
  assert.equal(digests.size, 24, 'Each canonical expression has its own recording');
});

test('provenance distinguishes reference IPA, assembled broad phrase IPA and offline synthetic demonstrations', () => {
  const dictionary = manifest();
  assert.ok(fs.existsSync(provenancePath), 'Missing pronunciation provenance');
  const documentation = fs.readFileSync(provenancePath, 'utf8');
  for (const [id, entry] of Object.entries(dictionary)) {
    assert.ok(documentation.includes('`' + id + '`'), id + ': provenance row');
    assert.ok(documentation.includes(entry.source), id + ': primary source');
  }
  assert.match(documentation, /Microsoft Zira Desktop/);
  assert.match(documentation, /en-US/);
  assert.match(documentation, /assembled broad IPA/i);
  assert.match(documentation, /not.*(?:exact|sentence).*stress/i);
  assert.match(documentation, /not.*original.*(?:speaker|audio)/i);
  assert.match(documentation, /no dictionary (?:definitions|audio)/i);
});

test('offline generator refuses a second run without Force and leaves every existing asset untouched', {
  skip: process.platform === 'win32' ? false : 'System.Speech generator is Windows-only'
}, () => {
  const dictionary = manifest();
  assert.ok(fs.existsSync(generatorPath), 'Missing offline generator');
  const files = Object.keys(dictionary).map(id => path.join(project, 'web/pronunciations', id + '.wav'));
  const hashes = () => files.map(file => crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex'));
  const before = hashes();
  const result = spawnSync('powershell.exe', ['-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
    '-File', generatorPath], {cwd: project, encoding: 'utf8', timeout: 30000});
  assert.ifError(result.error);
  assert.notEqual(result.status, 0, 'No implicit overwrite on regeneration');
  assert.match(result.stdout + result.stderr, /Refusing to overwrite/);
  assert.deepEqual(hashes(), before, 'Refusal is read-only across all assets');
});

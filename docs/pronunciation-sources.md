# Offline canonical pronunciation provenance

## Scope and labels

The 24 entries in `web/learning-pronunciations.js` match the current learning lexicon's canonical IDs. CommonJS exports a plain object; a browser receives `window.LearningPronunciations`. Each entry has only `ipa`, `spoken`, `audio`, `canonical`, and `source`. Canonical forms are independent of caption inflections and casing. The two slash-separated glass and NIMBY alternatives are spoken as two separate short sentences, never as the word "slash"; NIMBY is spoken as the word "Nimby", not five letter names.

IPA is a **reference US dictionary/canonical form**, not a narrow transcription of the generated WAV, and not original-speaker phonetics. Multiword entries use **assembled broad IPA** from component headwords and ordinary inflection rules. Phrase stress marks preserve component lexical stress; they do **not claim exact sentence stress**, connected-speech timing, emphasis, or a dictionary-published whole-phrase transcription. We normalize typographic spaces around schwas, use explicit schwas instead of optional syllabic-consonant typography, and omit the optional US flap diacritic in broad phrase IPA (e.g. quarter /t/ rather than /t̬/).

All WAVs are **offline synthetic English demonstrations, not the original speaker or original audio**, generated only through installed Windows `System.Speech` with **Microsoft Zira Desktop**, culture **en-US**, rate **-1**, volume **100**, PCM **22,050 Hz / 16-bit / mono**. No network TTS, credentials, paid tools, or provider audio is used. **No dictionary definitions or audio are copied**; only short headword phonetic facts are referenced. Dictionary links are provenance references, not runtime audio dependencies. Zira can differ from the reference IPA in stress, reductions or vowel realization; neither the reference nor the synthetic example certifies the video's pronunciation.

## Sources and editorial derivation

Primary publisher: Cambridge Dictionary (Cambridge University Press), read-only pronunciation/headword lookup on 2026-10-28. Some bare `/dictionary/english/` pages returned HTTP 403; the publisher's indexed US/pronunciation versions supplied the cited facts. Sources below identify headwords, not claims of licensed recordings or whole-phrase dictionary entries. Ordinary short component words retain conventional broad US forms.

| Canonical ID | Primary manifest source | Reference type / editorial derivation |
| --- | --- | --- |
| `glass-half` | [glass](https://dictionary.cambridge.org/us/pronunciation/english/glass) | Assembled broad IPA for two alternatives. US glass /ɡlæs/; ordinary half, full, empty. |
| `natural-governor` | [governor](https://dictionary.cambridge.org/us/pronunciation/english/governor) | Assembled; governor /ˈɡʌv.ɚ.nɚ/ with [natural](https://dictionary.cambridge.org/us/pronunciation/english/natural). |
| `nimby` | [NIMBY](https://dictionary.cambridge.org/us/pronunciation/english/nimby) | NIMBY /ˈnɪm.bi/ is the dictionary headword. Expanded alternative assembled using [backyard](https://dictionary.cambridge.org/pronunciation/english/backyard), US /ˌbækˈjɑːrd/. |
| `coiled-spring` | [coil](https://dictionary.cambridge.org/dictionary/english/coil) | Assembled; coil /kɔɪl/ plus voiced past-participle /d/, then spring. |
| `buy-the-dip` | [dip](https://dictionary.cambridge.org/us/pronunciation/english/dip) | Assembled; dip /dɪp/ with buy and weak the /ðə/. No caption-specific "this AI" expansion. |
| `tailwinds` | [tailwind](https://dictionary.cambridge.org/us/pronunciation/english/tailwind) | Dictionary singular /ˈteɪl.wɪnd/ plus plural /z/. |
| `otherworldly` | [otherworldly](https://dictionary.cambridge.org/us/dictionary/english/otherworldly) | Exact reference US /ˌʌð.ɚˈwɝːld.li/: primary stress on world, not other. |
| `astounding` | [astounding](https://dictionary.cambridge.org/us/pronunciation/english/astounding) | Dictionary US /əˈstaʊn.dɪŋ/. |
| `bifurcated` | [bifurcate](https://dictionary.cambridge.org/pronunciation/english/bifurcate) | Dictionary US base /ˈbaɪ.fɚ.keɪt/ plus syllabic past /ɪd/, with resyllabification: /ˈbaɪ.fɚ.keɪ.tɪd/. Derived inflection, not a quoted bifurcated entry; primary stress remains initial. |
| `ensued` | [ensue](https://dictionary.cambridge.org/pronunciation/english/ensue) | US base /ɪnˈsuː/ plus past /d/: /ɪnˈsuːd/. No British /j/. |
| `historical-analogs` | [analog](https://dictionary.cambridge.org/pronunciation/english/analog) | Assembled with [historical](https://dictionary.cambridge.org/us/pronunciation/english/historical); noun analog /ˈæn.ə.lɑːɡ/ plus plural /z/. |
| `irrational-exuberance` | [exuberance](https://dictionary.cambridge.org/pronunciation/english/exuberance) | Assembled with [irrational](https://dictionary.cambridge.org/us/pronunciation/english/irrational); US exuberance has no /j/ after /z/. |
| `preemptive-tightening` | [preemptive](https://dictionary.cambridge.org/pronunciation/english/preemptive) | Assembled; this US spelling's pronunciation page gives /priˈemp.tɪv/. Retains the full canonical "policy". [Tighten](https://dictionary.cambridge.org/us/pronunciation/english/tighten) plus /ɪŋ/; policy has the US /ɑː/ vowel. |
| `qoq-revenue` | [revenue](https://dictionary.cambridge.org/us/pronunciation/english/revenue) | Assembled; US revenue /ˈrev.ə.nuː/ with [quarter](https://dictionary.cambridge.org/us/pronunciation/english/quarter), over, growth. Hyphens do not get spoken. |
| `priced-in` | [price](https://dictionary.cambridge.org/pronunciation/english/price) | Assembled; price /praɪs/ plus voiceless past /t/, then in. Not caption variant "getting priced in". |
| `de-risking` | [derisk](https://dictionary.cambridge.org/us/dictionary/english/derisk) | Derived broad form: productive de- /diː/ + risk /rɪsk/ + /ɪŋ/. The business entry's written /ˌdiːˈrɪsk/ is UK-labelled; no separate US string is supplied there, so the US derived form is editorial, not falsely quoted as an exact US dictionary entry. |
| `long-short-positioning` | [position](https://dictionary.cambridge.org/pronunciation/english/position) | Assembled; US position /pəˈzɪʃ.ən/ plus /ɪŋ/, long and short. Natural display/spoken hyphen joins long-short. |
| `capitulation` | [capitulation](https://dictionary.cambridge.org/pronunciation/english/capitulation) | US /kəˌpɪtʃ.əˈleɪ.ʃən/, normalizing schwa typography only. |
| `dovish` | [dovish](https://dictionary.cambridge.org/pronunciation/english/dovish) | Dictionary US /ˈdʌv.ɪʃ/. |
| `style-tilt` | [tilt](https://dictionary.cambridge.org/pronunciation/english/tilt) | Assembled; style plus tilt /tɪlt/. |
| `frontier-models` | [frontier](https://dictionary.cambridge.org/us/pronunciation/english/frontier) | Assembled; US frontier /frʌnˈtɪr/ with ordinary US model plus plural /z/. |
| `revenue-per-worker` | [revenue](https://dictionary.cambridge.org/us/pronunciation/english/revenue) | Assembled; US revenue with unstressed per /pɚ/ and [worker](https://dictionary.cambridge.org/us/pronunciation/english/worker), /ˈwɝː.kɚ/. |
| `cds-widen` | [default](https://dictionary.cambridge.org/pronunciation/english/default) | Assembled full canonical words, not letters C-D-S; US default /dɪˈfɑːlt/ with credit, swaps and widen. This is a canonical expression, not the video's sentence stress. |
| `treasury-issuance` | [issuance](https://dictionary.cambridge.org/us/pronunciation/english/issuance) | Assembled; US issuance /ˈɪʃ.u.əns/ with [Treasury](https://dictionary.cambridge.org/pronunciation/english/treasury), /ˈtreʒ.ɚ.i/. |

## Reproduction and safety

For optional regeneration on Windows, install PowerShell 7 from its official distribution and use:

```powershell
pwsh -NoProfile -NonInteractive -File .\scripts\generate-learning-pronunciations.ps1
```

This requires the installed **Microsoft Zira Desktop en-US** voice and local Node at `C:\Program Files\nodejs\node.exe` (or an explicitly supplied `-NodePath`). On this host, Windows PowerShell 5.1 failed inside `System.Speech.Internal.ObjectTokens.SAPICategories.DefaultDeviceOut()` with a null-reference error before any output was written. Read-only inventory and exact-name selection both succeeded under bundled PowerShell **7.6.5**, and that runtime generated all 24 assets without changing the synthesis code. This is a runtime-specific reproduction concern, not a missing voice or reason to substitute a remote service.

The script derives absolute paths from its own project directory, validates exactly 24 lexicon IDs and fixed `/pronunciations/{id}.wav` paths, rejects reparse points/junctions/symlinks in output ancestry, and preflights every target before writing. It selects Zira by exact name with no voice/provider fallback. It reserves new files exclusively and writes through `SpeechSynthesizer.SetOutputToWaveFile`, releasing each output before validating its RIFF chunks. Any existing canonical asset causes a read-only refusal unless the operator explicitly passes `-Force`. Even `-Force` cannot redirect output outside this project's `web/pronunciations` or follow linked targets. Interrupted generation may leave incomplete owned WAVs; inspect them, then explicitly use `-Force` to regenerate if desired. Unrelated files are never deleted.

Successful generation prints JSON with each canonical ID, actual selected voice/culture, format, duration, byte size, SHA-256 and absolute path. It does not modify the manifest, lexicon, UI, server, or this document. Audio output is a demonstration; playback integration remains a separate responsibility.

Focused checks:

```powershell
& 'C:\Program Files\nodejs\node.exe' --test tests/test_learning_pronunciations.js
```

These check the exact 24 IDs, browser/CommonJS export, canonical fields, reference-IPA corrections, safe asset paths, complete non-silent RIFF/WAVE PCM clips, individual asset hashes, source documentation, and read-only refusal on a second generation run. Windows-only generator execution checks skip on other platforms; manifest/audio checks remain portable. Parent integration/global tests are intentionally outside this worker's scope.

## Generated asset inventory and focused verification

Generated 2026-10-28 under PowerShell 7.6.5, actual selected **Microsoft Zira Desktop / en-US**, rate -1, volume 100, mono 16-bit PCM at 22,050 Hz for every file. Each filename below is relative to `web/pronunciations/`. Regeneration is not required to play the included demonstration audio.

| WAV filename | Duration (seconds) | File size (bytes) |
| --- | ---: | ---: |
| `astounding.wav` | 1.7693 | 78074 |
| `bifurcated.wav` | 1.7444 | 76972 |
| `buy-the-dip.wav` | 1.6543 | 73002 |
| `capitulation.wav` | 2.1193 | 93506 |
| `cds-widen.wav` | 2.7841 | 122826 |
| `coiled-spring.wav` | 1.8393 | 81160 |
| `de-risking.wav` | 1.7693 | 78072 |
| `dovish.wav` | 1.5644 | 69036 |
| `ensued.wav` | 1.6344 | 72124 |
| `frontier-models.wav` | 2.1943 | 96814 |
| `glass-half.wav` | 4.0290 | 177726 |
| `historical-analogs.wav` | 2.4292 | 107172 |
| `irrational-exuberance.wav` | 2.4491 | 108052 |
| `long-short-positioning.wav` | 2.3891 | 105406 |
| `natural-governor.wav` | 2.0992 | 92622 |
| `nimby.wav` | 3.6541 | 161190 |
| `otherworldly.wav` | 1.8193 | 80276 |
| `preemptive-tightening.wav` | 2.6691 | 117754 |
| `priced-in.wav` | 1.6444 | 72564 |
| `qoq-revenue.wav` | 3.0590 | 134950 |
| `revenue-per-worker.wav` | 2.1492 | 94826 |
| `style-tilt.wav` | 1.9444 | 85792 |
| `tailwinds.wav` | 1.9493 | 86010 |
| `treasury-issuance.wav` | 2.1093 | 93064 |
| **24-file total** | **53.4668** | **2358990** |

TDD record: the initial focused run failed all six assertions with **Missing offline pronunciation manifest** (RED); after implementation and local generation, the same focused suite passed **6/6**, with no skips (GREEN). WAV checks confirm complete RIFF chunk sizes, mono PCM format, sensible duration, nonzero signal, and 24 distinct hashes. The second-run refusal check confirmed every existing file's SHA-256 stayed unchanged. These are automated structural/signal checks, not a human listening or phonetic-match certification. No parent UI/server integration or global test suite was run by this worker.

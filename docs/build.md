# Windows portable build and runtime

Version: `0.1.0-beta.1`. Target: Windows 10/11 x64. Public download: **Windows Core**.

Core includes subtitle learning, local caption imports, independent DOCX export,
ONNX/tokenizers/Hugging Face punctuation support and official Node for yt-dlp.
It does **not** include ASR, PyAV, FFmpeg/codec DLLs or CTranslate2. Uncaptioned
video/media transcription and original-audio cache validation/shadowing are not
available in Core. Original YouTube video playback still uses the browser bridge.
The UI may still expose source-only options; selecting them reports a dependency
error instead of silently fabricating a transcript or substituting synthetic audio.

## Run without Python or Codex

Extract the complete portable archive, keep `SubtitleStudio.exe` and `_internal/`
together, and run `launch.cmd`. No installed Python, Node, Codex, Word or account
is needed for local caption import and DOCX generation. Node, when included, is
used by yt-dlp, not Word export. The unsigned beta may trigger Windows SmartScreen;
no signing or clean-machine compatibility certification is claimed.

The server only binds `127.0.0.1`; the YouTube player bridge uses a separate random
loopback port. Root APIs retain their session token and host/origin checks. The
root document never loads the YouTube SDK. An occupied app port is skipped (up to
ten attempts); a running instance is never reused across different data folders.

```powershell
.\SubtitleStudio.exe --help
.\SubtitleStudio.exe --version
.\SubtitleStudio.exe --check-runtime
.\SubtitleStudio.exe --open --port 8767 --data-dir C:\Temp\SubtitleStudio-smoke
```

`--help`/`--version` do not start the server, create app data or show error dialogs.
`--check-runtime` checks actual DOCX serialization, yt-dlp import, optional ASR WAV
decoding/native imports, and bundled Node startup, without downloading any model.
Core reports `core_ready: true`, punctuation library versions, and `asr: null`.
It does not prove model inference quality or that YouTube/translation is reachable.
Use the UI's shutdown action to stop the process cleanly.

## Program assets versus user data

Frozen program assets come only from PyInstaller's `sys._MEIPASS` (`_internal/`),
never from the working directory or an existing private application checkout.
Frozen state defaults to `%LOCALAPPDATA%\SubtitleStudio`. If LOCALAPPDATA is absent,
the fallback is the current user's `AppData\Local\SubtitleStudio` folder.

Data selection precedence is `--data-dir`, `SUBTITLE_STUDIO_DATA_DIR`, then default.
Overrides may be absolute or relative to the shell's working directory. Blank
paths, drive roots, network shares, files, and frozen program/asset descendants
are rejected. Symlinks/junctions are resolved when checking the selected root.
Choose a dedicated local folder you own; never point this at a personal app's data.

The data root contains `results/`, `.uploads/`, `.work/tmp/`, `.models/`, `.cache/`,
the local learning database, and `studio.log`. TEMP/TMP, Hugging Face model caches
and the generic cache root are directed there before server/library startup.
The frozen app does not write beside its executable. Explicit Word export can
also create its documented non-overwriting copy on the OS Desktop; this is a
user-requested export, not application state.

Python-source launch keeps its historical default: results, uploads, temporary
files and logs under the checkout containing `app.py`, regardless of working
directory. The same overrides are supported. Future model downloads use that
selected root's `.models/`; an old global Hugging Face cache is not automatically
imported. No existing private installation or data is migrated, modified or read.

```powershell
python app.py --data-dir .work/smoke --port 8767
```

## Build from a clean checkout

Use official 64-bit Python 3.12 and build on Windows. No global pip installation is
performed. `.build/` and `dist/` are build outputs, not source or user data.

```powershell
python -m venv .build/venv
.\.build\venv\Scripts\python.exe -m pip install --index-url https://pypi.org/simple -r requirements-build.txt
```

`requirements.txt` pins caption/DOCX dependencies and includes
`requirements-punctuation.txt`. Optional source ASR dependencies are separate:
`python -m pip install -r requirements-asr.txt -c requirements-lock.txt`.
The default Windows build installs **Core only** and uses the exact Windows/Python
3.12 constraints in `requirements-lock.txt`. Even if ASR is installed in the build
venv for source tests, Core excludes its modules, metadata and native DLLs.
The pinned builder is PyInstaller 6.22.3, the stable official PyPI version checked
when this build was prepared: https://pypi.org/project/pyinstaller/6.22.3/

The default optional Node path is the official installation's
`%ProgramFiles%\nodejs\node.exe`, with its adjacent `LICENSE`. If that installation
omits LICENSE, recover it without changing the installation:

```powershell
$nodeLicense = .\scripts\prepare-node-license.ps1
.\scripts\build-windows.ps1 -NodeLicensePath $nodeLicense
```

Recovery downloads only the matching official `nodejs.org` Windows x64 archive,
checks its published SHA-256, and requires its node.exe to be byte-identical to
the installed binary before extracting LICENSE under `.build/`. The installed
binary is bundled unchanged. No npm modules, user Node, Codex executable or secret
is copied. Frozen yt-dlp disables implicit JS runtimes, then uses only
`_internal/runtime/node.exe`. Use `-WithoutNode` explicitly if Node cannot be licensed
or is not wanted; some YouTube extraction may then be unavailable.

The default build produces `dist/SubtitleStudio-Core/` (not a one-file
self-extracting binary). `-EnableASR` is an explicit **internal-only** option and
emits a redistribution warning; it writes a separate `SubtitleStudio-ASR-Internal/`
folder and is not the downloadable beta. Never zip the whole `dist/` directory.
The original full test candidate, if present, remains local and must not be published.
Only allowlisted `web/` assets, installed dependency files, public `docs/` and
`examples/`, and license notices are collected. It never recursively includes
the checkout, `.git/`, `.venv/`, `.build/`, results, cached models, cookies or logs.
`--internal-ytdlp` runs `yt_dlp.main` before app startup; it is not a Python shell
or arbitrary module runner. yt-dlp uses `--ignore-config` and disables its cache.

## Verify before release

```powershell
.\.build\venv\Scripts\python.exe -m unittest discover -s tests -v
node --test tests/*.js
.\.build\venv\Scripts\python.exe scripts/smoke-windows.py --executable dist/SubtitleStudio-Core/SubtitleStudio.exe --port 8767
```

The smoke test strips Python/Node from PATH, removes Python environment overrides,
uses throwaway data, verifies CLI/runtime/native decoding, HTTP assets, token and
origin rejection, separate bridge isolation, local caption extraction and learning
history, then shuts down only its own process. It does not contact port 8765, use
cookies or user media, download models, or call translation/TTS/paid services.

Local punctuation libraries are bundled; model weights are not. First punctuation
use requires its separately pinned upstream model download and network access.
ASR is source-install-only for this release. No end-to-end uncached model
download/inference or real YouTube extraction is implied by the offline smoke.
Existing network/provider restrictions still apply. A Core integrity check must
find no `av`, `av.libs`, `faster_whisper`, `ctranslate2`, codec DLLs or mutagen in
the portable files or executable's embedded Python module archive.

## Licenses and publication gate

The application source's MIT license is not a blanket license for the portable
folder. `BUILD-DEPENDENCIES.txt` records the actual build environment;
`BUNDLED-DISTRIBUTIONS.json` records shipped metadata license fields, versions,
upstream URLs and copied license paths. `licenses/` retains supplied dependency,
Python and Node notices; Node LICENSE also remains beside the bundled node.exe.
Package-level notices (including ONNX Runtime's ThirdPartyNotices) are copied too.
The Tokenizers/FlatBuffers wheels omit LICENSE; their exact official tagged
source LICENSE files are cached under `.build/` and included with URL/SHA-256
provenance in the inventory. This build-only recovery needs network access once.
`BUNDLED-LICENSES.md` summarizes the bundled license evidence. Core has no codec
payload and no `FFMPEG-BUILD-INFO.json`; that file is produced for internal ASR only.

Mutagen is installed only because yt-dlp's default extra requests it, but both
its code and metadata are explicitly excluded from the bundle. Metadata embedding
is unsupported; caption extraction and original-audio download do not request it.

The public Core build excludes the following unresolved redistribution case:
PyAV wheels carry FFmpeg and additional codec DLLs, including x264/x265 in this
installed wheel. Their actual licenses and corresponding-source/build-material
obligations need separate review; PyAV's BSD metadata alone does not cover them.
The inventory preserves reported compiled configurations and licenses rather than
asserting that the entire wheel is LGPL-only. Upstream links alone do not certify
redistribution compliance. **Do not publish an ASR/full binary until that review
and required corresponding-source/license packaging are complete.** This gate
does not apply to codec-free Core; inspect its generated inventory and exclusions.

After verification and licensing review, the release owner packages the entire
`SubtitleStudio-Core/` folder as `SubtitleStudio-0.1.0-beta.1-windows-x64.zip`, generates its checksum,
and publishes it. These build scripts never push Git or publish releases.

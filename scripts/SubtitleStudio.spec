# Build on Windows x64 using the isolated requirements-build.txt environment.
from importlib.util import find_spec
from importlib.metadata import PackageNotFoundError
import os
from pathlib import Path
from PyInstaller.utils.hooks import collect_all, copy_metadata

ROOT = Path(SPECPATH).parent
enable_asr = os.environ.get('SUBTITLE_STUDIO_BUILD_ASR') == '1'
bundle_name = 'SubtitleStudio-ASR-Internal' if enable_asr else 'SubtitleStudio-Core'
datas = []
binaries = []
hiddenimports = []

# Explicit asset allowlist. Never collect the repository, user data, or models.
asset_extensions = {'.html', '.css', '.js', '.wav', '.jpg', '.png', '.svg', '.woff', '.woff2'}
for path in sorted((ROOT / 'web').rglob('*')):
    if path.is_file() and path.suffix.lower() in asset_extensions:
        datas.append((str(path), str(path.parent.relative_to(ROOT))))

required = ('yt_dlp', 'yt_dlp_ejs', 'docx', 'onnxruntime', 'tokenizers', 'huggingface_hub')
optional = ('faster_whisper', 'av', 'ctranslate2') if enable_asr else ()
for package in required + optional:
    if not find_spec(package):
        if package in required:
            raise RuntimeError(f'Missing required build dependency: {package}')
        continue
    data, binary, hidden = collect_all(package, filter_submodules=lambda name: '.tests' not in name and '.__pyinstaller' not in name)
    datas += data
    binaries += binary
    hiddenimports += hidden

# Preserve installed distribution metadata and third-party license notices.
for distribution in ('yt-dlp', 'python-docx',
                     'onnxruntime', 'tokenizers', 'huggingface-hub', 'yt-dlp-ejs',
                     'numpy', 'lxml', 'certifi', 'requests', 'urllib3', 'websockets',
                     'brotli', 'pycryptodomex') + (('faster-whisper', 'av', 'ctranslate2') if enable_asr else ()):
    try:
        datas += copy_metadata(distribution, recursive=True)
    except PackageNotFoundError:
        if distribution in ('yt-dlp', 'python-docx'):
            raise

datas = [(source, target) for source, target in datas
         if '__pyinstaller' not in Path(source).parts and
         not any(part.lower().startswith(('mutagen-', 'pyinstaller-', 'pyinstaller_hooks_contrib-', 'altgraph-', 'pefile-', 'pywin32_ctypes-'))
                 and part.endswith('.dist-info') for part in Path(source).parts)]
excluded = ['mutagen', 'PyInstaller', '_pyinstaller_hooks_contrib', 'yt_dlp.__pyinstaller',
            'tkinter', 'IPython', 'pytest', 'torch', 'tensorflow', 'matplotlib']
if not enable_asr:
    excluded += ['av', 'faster_whisper', 'ctranslate2']
    forbidden = ('av-', 'faster_whisper-', 'ctranslate2-')
    datas = [(source, target) for source, target in datas
             if not any(part.startswith(forbidden) and part.endswith('.dist-info') for part in Path(source).parts)]

node = os.environ.get('SUBTITLE_STUDIO_BUILD_NODE')
node_license = os.environ.get('SUBTITLE_STUDIO_BUILD_NODE_LICENSE')
if node:
    if not node_license or not Path(node_license).is_file():
        raise RuntimeError('A Node.js license must accompany the optional node.exe.')
    binaries.append((node, 'runtime'))
    datas.append((node_license, 'runtime'))

for name in ('LICENSE', 'PRIVACY.md', 'SECURITY.md'):
    if (ROOT / name).is_file():
        datas.append((str(ROOT / name), 'notices'))

a = Analysis([str(ROOT / 'app.py')], pathex=[str(ROOT)], binaries=binaries,
             datas=datas, hiddenimports=hiddenimports,
             excludes=excluded,
             noarchive=False, optimize=1)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='SubtitleStudio',
          debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
          console=True, disable_windowed_traceback=False)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name=bundle_name)

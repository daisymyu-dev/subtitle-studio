"""Fail closed if a public Core bundle accidentally includes ASR/codec payloads."""

import argparse
import json
from pathlib import Path
import re
from PyInstaller.archive.readers import CArchiveReader


def verify_core(root):
    root = Path(root).resolve()
    forbidden_modules = ('av', 'faster_whisper', 'ctranslate2', 'mutagen', 'PyInstaller', '_pyinstaller_hooks_contrib')
    archive = CArchiveReader(str(root / 'SubtitleStudio.exe')).open_embedded_archive('PYZ.pyz')
    modules = [name for name in archive.toc if any(name == term or name.startswith(term + '.') for term in forbidden_modules)]
    forbidden_dll = re.compile(r'^(?:avcodec|avdevice|avfilter|avformat|avutil|swresample|swscale|libx264|libx265|ffmpeg|ctranslate2)', re.I)
    files = []
    for path in root.rglob('*'):
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        parts = [part.lower() for part in relative.parts]
        if any(part in (*(term.lower() for term in forbidden_modules), 'av.libs', '__pyinstaller') or
               any(part.startswith(term.lower() + '-') and part.endswith('.dist-info') for term in forbidden_modules)
               for part in parts) or (path.suffix.lower() == '.dll' and forbidden_dll.match(path.name)):
            files.append(str(relative))
    if modules or files:
        raise RuntimeError(json.dumps({'forbidden_modules': modules, 'forbidden_files': files}))
    for required in ('_internal/runtime/node.exe', '_internal/runtime/LICENSE', 'licenses/node/LICENSE',
                     'LICENSE', 'THIRD_PARTY_NOTICES.md', 'docs/PRIVACY.md', 'docs/build.md',
                     'BUNDLED-DISTRIBUTIONS.json', 'BUNDLED-LICENSES.md', 'BUILD-DEPENDENCIES.txt'):
        if not (root / required).is_file():
            raise RuntimeError('Missing required release file: ' + required)
    if (root / 'FFMPEG-BUILD-INFO.json').exists():
        raise RuntimeError('Core unexpectedly contains FFmpeg build evidence/payload.')
    if not any(name == 'onnxruntime' for name in archive.toc) or 'tokenizers' not in archive.toc:
        raise RuntimeError('Core punctuation runtime was not bundled.')
    print(json.dumps({'core_integrity': 'passed', 'forbidden_modules': [], 'forbidden_files': []}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    verify_core(parser.parse_args().directory)

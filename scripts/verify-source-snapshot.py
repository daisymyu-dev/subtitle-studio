"""Compare frozen application bytecode with the current source, not timestamps."""

import argparse
import hashlib
import json
import marshal
from pathlib import Path
import types
from PyInstaller.archive.readers import CArchiveReader


def normalized(code):
    return code.replace(co_filename='<source>', co_consts=tuple(
        normalized(value) if isinstance(value, types.CodeType) else value for value in code.co_consts))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    parser.add_argument('--assets', action='store_true', help='Also require current public assets/docs')
    parser.add_argument('--report', type=Path, help='Write a path-free SHA-256 source inventory after verification')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    output = args.directory.resolve()
    archive = CArchiveReader(str(output / 'SubtitleStudio.exe'))
    pyz = archive.open_embedded_archive('PYZ.pyz')
    sources = [root / 'app.py', *sorted((root / 'studio').glob('*.py'))]
    stale = []
    for source in sources:
        if source.name == 'app.py':
            frozen = marshal.loads(archive.extract('app'))
        else:
            name = 'studio' if source.name == '__init__.py' else 'studio.' + source.stem
            frozen = pyz.extract(name)
        expected = compile(source.read_bytes(), str(source), 'exec', dont_inherit=True, optimize=1)
        if normalized(frozen) != normalized(expected):
            stale.append(str(source.relative_to(root)))
    if stale:
        raise RuntimeError('Frozen application source is stale: ' + ', '.join(stale))
    checked = []
    if args.assets:
        for folder in ('web', 'docs', 'examples'):
            for source in (root / folder).rglob('*'):
                if not source.is_file():
                    continue
                target = (output / '_internal' if folder == 'web' else output) / source.relative_to(root)
                if not target.is_file() or hashlib.sha256(source.read_bytes()).digest() != hashlib.sha256(target.read_bytes()).digest():
                    stale.append(str(source.relative_to(root)))
                checked.append(source)
        for name in ('README.md', 'LICENSE', 'THIRD_PARTY_NOTICES.md', 'launch.cmd'):
            source = root / name
            if source.read_bytes() != (output / name).read_bytes():
                stale.append(name)
            checked.append(source)
        if stale:
            raise RuntimeError('Frozen public assets/docs are stale: ' + ', '.join(stale))
    report = {'frozen_source_snapshot': 'passed', 'python_files': len(sources),
              'current_assets_checked': len(checked),
              'executable_sha256': hashlib.sha256((output / 'SubtitleStudio.exe').read_bytes()).hexdigest(),
              'files': [{'path': str(source.relative_to(root)).replace('\\', '/'),
                         'sha256': hashlib.sha256(source.read_bytes()).hexdigest()}
                        for source in sources + checked]}
    if args.report:
        args.report.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps({key: value for key, value in report.items() if key != 'files'}))


if __name__ == '__main__':
    main()

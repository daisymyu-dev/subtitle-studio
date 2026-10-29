"""Inventory the actual frozen distributions and preserve their supplied notices.

This records evidence, not a blanket license grant or a legal compliance verdict.
"""

import argparse
import ctypes
import hashlib
from importlib.metadata import PathDistribution, distribution
import json
from pathlib import Path
import shutil
import sys
from urllib.request import urlopen


def build_notices(destination):
    destination = Path(destination).resolve()
    internal = destination / '_internal'
    notices = destination / 'licenses'
    notices.mkdir(exist_ok=True)
    inventory = []
    for metadata in sorted(internal.glob('*.dist-info')):
        dist = PathDistribution(metadata)
        name = dist.metadata['Name']
        if name.lower() == 'mutagen':
            raise RuntimeError('Excluded mutagen metadata unexpectedly appeared in the bundle.')
        license_files = []
        for path in metadata.rglob('*'):
            if not path.is_file() or path.suffix in ('.pyc', '.pyo') or '__pycache__' in path.parts:
                continue
            relative = path.relative_to(metadata)
            if not any(term in str(relative).lower() for term in ('license', 'copying', 'notice', 'authors')):
                continue
            target = notices / f'{name}-{dist.version}' / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
            license_files.append(str(target.relative_to(destination)).replace('\\', '/'))
        # Some wheels (notably ONNX Runtime) keep notices inside the package,
        # rather than the dist-info directory. Preserve those as well.
        installed = distribution(name)
        for entry in installed.files or ():
            if '..' in entry.parts or '__pycache__' in entry.parts or entry.suffix in ('.pyc', '.pyo'):
                continue
            if not any(term in str(entry).lower() for term in ('license', 'copying', 'notice', 'authors')):
                continue
            source = Path(installed.locate_file(entry))
            if not source.is_file():
                continue
            target = notices / f'{name}-{dist.version}' / entry
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            license_files.append(str(target.relative_to(destination)).replace('\\', '/'))
        supplements = []
        # These official wheels omit LICENSE. Fetch only the exact tagged
        # upstream license, caching build-only downloads under this checkout.
        upstream = {'tokenizers': 'huggingface/tokenizers', 'flatbuffers': 'google/flatbuffers'}
        if not license_files and name.lower() in upstream:
            url = f'https://raw.githubusercontent.com/{upstream[name.lower()]}/v{dist.version}/LICENSE'
            cache = Path(__file__).resolve().parents[1] / '.build' / 'license-supplements' / f'{name}-{dist.version}' / 'LICENSE'
            if not cache.is_file():
                with urlopen(url, timeout=30) as response:
                    content = response.read(1024 * 1024 + 1)
                if len(content) > 1024 * 1024 or b'Apache License' not in content:
                    raise RuntimeError('Unexpected upstream license content: ' + name)
                cache.parent.mkdir(parents=True, exist_ok=True)
                cache.write_bytes(content)
            target = notices / f'{name}-{dist.version}' / 'LICENSE'
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(cache, target)
            license_files.append(str(target.relative_to(destination)).replace('\\', '/'))
            supplements.append({'url': url, 'sha256': hashlib.sha256(target.read_bytes()).hexdigest()})
        inventory.append({'name': name, 'version': dist.version,
                          'license_expression': dist.metadata.get('License-Expression', ''),
                          'license_field': dist.metadata.get('License', ''),
                          'license_classifiers': [v for v in dist.metadata.get_all('Classifier', []) if v.startswith('License')],
                          'project_urls': dist.metadata.get_all('Project-URL', []),
                          'home_page': dist.metadata.get('Home-page', ''),
                          'license_files': sorted(set(license_files)), 'supplemental_license_sources': supplements})
    for candidate in (Path(sys.base_prefix) / 'LICENSE.txt', Path(sys.base_prefix) / 'LICENSE'):
        if candidate.is_file():
            target = notices / 'Python' / 'LICENSE.txt'
            target.parent.mkdir(exist_ok=True)
            shutil.copy2(candidate, target)
            break
    else:
        raise RuntimeError('The build Python license was not found.')
    # The compiled bootloader is covered by PyInstaller's explicit exception.
    # Preserve that notice without bundling the GPL build-engine modules.
    builder = distribution('pyinstaller')
    for entry in builder.files or ():
        if entry.name == 'COPYING.txt':
            target = notices / f'PyInstaller-bootloader-{builder.version}' / 'COPYING.txt'
            target.parent.mkdir(exist_ok=True)
            shutil.copy2(builder.locate_file(entry), target)
    (destination / 'BUNDLED-DISTRIBUTIONS.json').write_text(json.dumps(inventory, indent=2), encoding='utf-8')

    ffmpeg = None
    if (internal / 'av.libs').is_dir():
        import av
        source = Path(av.__file__).parent.parent / 'av.libs'
        library = ctypes.CDLL(str(next(source.glob('avutil-*.dll'))))
        library.av_version_info.restype = ctypes.c_char_p
        ffmpeg = {'pyav': av.__version__, 'ffmpeg': library.av_version_info().decode(), 'libraries': []}
        for stem in ('avutil', 'avcodec', 'avformat', 'avfilter', 'avdevice', 'swscale', 'swresample'):
            binary = next(source.glob(stem + '-*.dll'))
            library = ctypes.CDLL(str(binary))
            info = {'library': stem}
            for suffix in ('license', 'configuration'):
                function = getattr(library, stem + '_' + suffix)
                function.restype = ctypes.c_char_p
                info[suffix] = function().decode()
            ffmpeg['libraries'].append(info)
        ffmpeg['dlls'] = [{'name': file.name, 'sha256': hashlib.sha256(file.read_bytes()).hexdigest()}
                          for file in sorted((internal / 'av.libs').glob('*.dll'))]
        ffmpeg['source_links'] = ['https://github.com/PyAV-Org/PyAV/tree/v' + av.__version__,
                                  'https://github.com/PyAV-Org/pyav-ffmpeg',
                                  'https://ffmpeg.org/download.html#get-sources',
                                  'https://ffmpeg.org/legal.html',
                                  'https://code.videolan.org/videolan/x264',
                                  'https://bitbucket.org/multicoreware/x265_git/']
        ffmpeg['release_review_required'] = True
        (destination / 'FFMPEG-BUILD-INFO.json').write_text(json.dumps(ffmpeg, indent=2), encoding='utf-8')
    lines = ['# Bundled dependency license evidence', '',
             'Subtitle Studio source is MIT. Bundled Python, Node and third-party libraries retain their own licenses.',
             'See BUNDLED-DISTRIBUTIONS.json for actual metadata, and licenses/ for supplied notices.',
             'BUILD-DEPENDENCIES.txt lists the build environment, including unbundled build-only packages.',
             'The PyInstaller build engine is excluded; its compiled bootloader notice/exception is retained.',
             'Mutagen code and metadata are excluded; metadata embedding is unsupported.', '',
             'Python source and license: https://www.python.org/downloads/source/',
             'Node source and notices for the bundled version: https://nodejs.org/en/download/releases', '']
    if ffmpeg:
        lines += ['## Publication review required', '',
                  f"PyAV {ffmpeg['pyav']} carries FFmpeg {ffmpeg['ffmpeg']} and third-party codec DLLs.",
                  'FFMPEG-BUILD-INFO.json records each DLL hash, reported license and compiled configuration.',
                  'Do not assume BSD metadata for PyAV covers the FFmpeg DLLs or x264/x265.',
                  'Before redistribution, retain all required codec licenses and provide corresponding source/build',
                  'materials as required by their actual licenses. Upstream links alone are not a compliance verdict.',
                  *ffmpeg['source_links'], '']
    (destination / 'BUNDLED-LICENSES.md').write_text('\n'.join(lines), encoding='utf-8')
    print(f'Inventoried {len(inventory)} bundled distributions; FFmpeg redistribution review required: {bool(ffmpeg)}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('destination', type=Path)
    build_notices(parser.parse_args().destination)

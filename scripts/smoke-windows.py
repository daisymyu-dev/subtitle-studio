"""Offline portable EXE smoke; no user data, browser login, models or paid calls."""

import argparse
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, Request, build_opener


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--executable', required=True, type=Path)
    parser.add_argument('--port', type=int, default=8767)
    parser.add_argument('--expect-asr', action='store_true', help='Internal ASR builds only; not the public Core download')
    args = parser.parse_args()
    if args.port == 8765:
        parser.error('Port 8765 is reserved for the separate personal installation.')
    executable = args.executable.resolve(strict=True)
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', args.port))
    root = Path(__file__).resolve().parents[1]
    (root / '.work').mkdir(exist_ok=True)
    opener = build_opener(ProxyHandler({}))
    before = {str(p.relative_to(executable.parent)): (p.stat().st_size, p.stat().st_mtime_ns)
              for p in executable.parent.rglob('*') if p.is_file()}
    with tempfile.TemporaryDirectory(prefix='portable-smoke-', dir=root / '.work') as temporary:
        data = Path(temporary) / 'data'
        env = dict(os.environ)
        for name in ('PYTHONHOME', 'PYTHONPATH', 'SUBTITLE_STUDIO_DATA_DIR'):
            env.pop(name, None)
        windows = Path(env.get('SystemRoot', r'C:\Windows'))
        env['PATH'] = str(windows / 'System32') + os.pathsep + str(windows)
        env['LOCALAPPDATA'] = str(Path(temporary) / 'local-appdata')
        env['TEMP'] = env['TMP'] = temporary
        for argument in ('--help', '--version', '--internal-ytdlp', '--check-runtime'):
            command = [str(executable), argument]
            if argument == '--internal-ytdlp':
                command += ['--version']
            result = subprocess.run(command, capture_output=True, text=True, encoding='utf-8',
                                    errors='replace', env=env, cwd=temporary, timeout=60)
            if result.returncode:
                raise AssertionError(f'{argument} failed: {result.stderr}')
            if argument == '--check-runtime':
                runtime = json.loads(result.stdout)
                assert runtime['core_ready'] and runtime['docx'] and runtime['punctuation']['onnxruntime'], runtime
                if args.expect_asr:
                    assert runtime['asr']['decoded_samples'] == 16000, runtime
                else:
                    assert runtime['asr'] is None, 'The Core build must not carry ASR or codecs'
        assert not data.exists()
        address = f'http://127.0.0.1:{args.port}'
        process = subprocess.Popen([str(executable), '--port', str(args.port), '--data-dir', str(data)],
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, cwd=temporary)
        token = None

        def request(path, body=None, headers=None, authenticated=True, base=address):
            selected = {'Origin': address}
            if authenticated and token:
                selected['X-App-Token'] = token
            selected.update(headers or {})
            if isinstance(body, dict):
                body = json.dumps(body).encode()
                selected['Content-Type'] = 'application/json'
            return opener.open(Request(base + path, data=body, headers=selected), timeout=10)

        def read_json(path, body=None):
            with request(path, body) as response:
                return json.load(response)

        def rejected(path, code, **kwargs):
            try:
                with request(path, **kwargs):
                    raise AssertionError(f'{path} unexpectedly accepted')
            except HTTPError as error:
                assert error.code == code, (path, error.code)

        try:
            deadline = time.monotonic() + 45
            while True:
                if process.poll() is not None:
                    raise AssertionError('EXE exited before startup: ' + process.stderr.read().decode(errors='replace'))
                try:
                    with request('/health', authenticated=False) as response:
                        assert json.load(response)['app'] == 'youtube-subtitle-studio'
                    break
                except (URLError, TimeoutError, ConnectionError):
                    if time.monotonic() > deadline:
                        raise AssertionError('EXE did not start on the dedicated smoke port')
                    time.sleep(.2)
            with request('/', authenticated=False) as response:
                page = response.read().decode('utf-8')
                assert "script-src 'self'" in response.headers['Content-Security-Policy']
            token = re.search(r'<meta name="app-token" content="([^"]+)"', page)[1]
            bridge = re.search(r'<meta name="video-bridge" content="([^"]+)"', page)[1]
            assert bridge.startswith('http://127.0.0.1:') and bridge != address
            for asset in ('/app.js', '/learning-library.js', '/learning.css', '/watch-core.js',
                          '/pronunciations/otherworldly.wav', '/vendor/open-props-easing.css'):
                with request(asset, authenticated=False) as response:
                    assert response.status == 200 and response.read(), asset
            rejected('/api/learning', 403, authenticated=False)
            rejected('/api/learning', 403, headers={'Origin': 'https://untrusted.example'})
            bridge_path = '/youtube-bridge.js'
            with request(bridge_path, authenticated=False, base=bridge) as response:
                assert token.encode() not in response.read()
            rejected('/api/learning', 404, authenticated=False, base=bridge)
            captions = b'WEBVTT\n\n00:00:00.000 --> 00:00:02.000\nThis example is written for the portable smoke test.\n'
            with request('/api/uploads', captions,
                         {'Content-Type': 'application/octet-stream', 'X-File-Name': 'smoke.vtt'}) as response:
                upload = json.load(response)
            job = read_json('/api/jobs', {'source': 'file', 'upload_id': upload['upload_id'],
                                         'options': {'mode': 'captions'}})['id']
            deadline = time.monotonic() + 20
            while True:
                status = read_json('/api/jobs/' + job)
                if status['status'] == 'done':
                    break
                assert status['status'] != 'error', status
                assert time.monotonic() < deadline, 'Caption job timed out'
                time.sleep(.1)
            profile = read_json('/api/learning/term', {'key': 'example', 'term': 'example', 'state': 'known'})
            assert profile['known'] == ['example']
            assert read_json('/api/learning/progress', {'job_id': job, 'time': 1.25})['ok']
            history = read_json('/api/library')['items']
            assert any(item['id'] == job and item['position'] == 1.25 for item in history)
            retained = data / 'results' / job
            assert retained.is_dir()
            assert any('This example is written' in path.read_text('utf-8') for path in retained.glob('*.txt'))
            print(json.dumps({'runtime': runtime, 'http': 'passed', 'caption_import': 'passed',
                              'learning_history': 'passed', 'token_origin_bridge_guards': 'passed',
                              'data_isolation': 'passed', 'port': args.port}))
        finally:
            if process.poll() is None and token:
                try:
                    with request('/api/shutdown', {}):
                        pass
                    process.wait(timeout=15)
                except Exception:
                    process.terminate()
            if process.poll() is None:
                process.terminate()
            stdout, stderr = process.communicate(timeout=15)
            if process.returncode:
                raise AssertionError('Portable process failed: ' + stderr.decode(errors='replace'))
        after = {str(p.relative_to(executable.parent)): (p.stat().st_size, p.stat().st_mtime_ns)
                 for p in executable.parent.rglob('*') if p.is_file()}
        assert before == after, 'Program directory was modified at runtime'


if __name__ == '__main__':
    main()

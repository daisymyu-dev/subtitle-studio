"""Local-only HTTP boundary tests; never fetch the YouTube SDK."""

from html.parser import HTMLParser
from http.client import HTTPConnection
import base64
import hashlib
import importlib.util
from pathlib import Path
import socket
import tempfile
import threading
import unittest
from urllib.parse import parse_qs, urlsplit


APP_ORIGIN = 'http://127.0.0.1:8765'
VIDEO = 'BaW_jenozKc'
CHANNEL = '9b02f4a31de248218f7c739fd063be18'


class PageParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.metas = {}
        self.scripts = []
        self.styles = []
        self.in_style = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'meta':
            self.metas[attrs.get('name')] = attrs.get('content')
        if tag == 'script':
            self.scripts.append(attrs)
        if tag == 'style':
            self.in_style = True

    def handle_endtag(self, tag):
        if tag == 'style':
            self.in_style = False

    def handle_data(self, data):
        if self.in_style:
            self.styles.append(data)


class VideoBridgeModuleTests(unittest.TestCase):
    def test_task_a_module_is_available(self):
        self.assertIsNotNone(importlib.util.find_spec('studio.video_bridge'),
                             'Task A needs the isolated VideoBridge module')


@unittest.skipUnless(importlib.util.find_spec('studio.video_bridge'), 'module not implemented yet')
class VideoBridgeHTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from studio.video_bridge import VideoBridge
        cls.bridge = VideoBridge(APP_ORIGIN)
        cls.parts = urlsplit(cls.bridge.origin)

    @classmethod
    def tearDownClass(cls):
        cls.bridge.close()

    def request(self, path, method='GET', host=None, extra_hosts=()):
        connection = HTTPConnection('127.0.0.1', self.parts.port, timeout=3)
        self.addCleanup(connection.close)
        connection.putrequest(method, path, skip_host=True)
        if host is not False:
            connection.putheader('Host', host or self.parts.netloc)
        for value in extra_hosts:
            connection.putheader('Host', value)
        connection.endheaders()
        response = connection.getresponse()
        return response.status, dict(response.getheaders()), response.read()

    def test_random_loopback_origin_and_fixed_url(self):
        self.assertEqual(self.parts.scheme, 'http')
        self.assertEqual(self.parts.hostname, '127.0.0.1')
        self.assertGreater(self.parts.port, 0)
        self.assertNotEqual(self.bridge.origin, APP_ORIGIN)
        url = urlsplit(self.bridge.url(VIDEO, CHANNEL))
        self.assertEqual(url.netloc, self.parts.netloc)
        self.assertEqual(url.path, '/player')
        self.assertEqual(parse_qs(url.query), {'v': [VIDEO], 'channel': [CHANNEL]})
        self.assertTrue(any(t.daemon and t.name == f'video-bridge-{self.parts.port}'
                            for t in threading.enumerate()))

    def test_page_only_injects_validated_public_configuration(self):
        path = urlsplit(self.bridge.url(VIDEO, CHANNEL))
        status, headers, body = self.request(path.path + '?' + path.query)
        self.assertEqual(status, 200)
        page = body.decode()
        parser = PageParser()
        parser.feed(page)
        self.assertEqual(parser.metas['bridge-app-origin'], APP_ORIGIN)
        self.assertEqual(parser.metas['bridge-video-id'], VIDEO)
        self.assertEqual(parser.metas['bridge-channel'], CHANNEL)
        self.assertEqual(parser.metas['referrer'], 'strict-origin-when-cross-origin')
        self.assertEqual(parser.scripts, [{'src': '/youtube-bridge.js', 'defer': None}])
        self.assertNotIn(str(Path(__file__).resolve().parents[1]), page)
        self.assertNotIn('app-token', page.lower())
        self.assertEqual(headers['Referrer-Policy'], 'strict-origin-when-cross-origin')
        self.assertEqual(headers['X-Content-Type-Options'], 'nosniff')
        self.assertEqual(headers['Cache-Control'], 'no-store')
        csp = headers['Content-Security-Policy']
        self.assertIn("default-src 'none'", csp)
        self.assertIn(f'frame-ancestors {APP_ORIGIN}', csp)
        self.assertIn('https://www.youtube.com/iframe_api', csp)
        self.assertIn('https://www.youtube.com/s/player/', csp)
        self.assertIn('https://www.youtube-nocookie.com', csp)
        self.assertNotIn('unsafe-inline', csp)
        self.assertNotIn('unsafe-eval', csp)
        self.assertNotIn('*', csp)
        self.assertFalse(any(key.lower().startswith('access-control-') for key in headers))

    def test_only_the_two_bridge_routes_exist(self):
        status, headers, body = self.request('/youtube-bridge.js')
        self.assertEqual(status, 200)
        self.assertIn('javascript', headers['Content-Type'])
        self.assertIn(b'https://www.youtube.com/iframe_api', body)
        for path in ('/', '/app.js', '/api/jobs', '/api/shutdown', '/AGENTS.md',
                     '/..%2fstudio/server.py', '/player/', '/youtube-bridge.js?token=x'):
            with self.subTest(path=path):
                self.assertEqual(self.request(path)[0], 404)

    def test_host_is_exact_and_required_even_for_errors_and_other_methods(self):
        for host in (False, 'localhost:' + str(self.parts.port), 'evil.example',
                     self.parts.netloc + '.evil.example', self.parts.netloc + ',evil.example'):
            for method in ('GET', 'HEAD', 'POST', 'OPTIONS'):
                with self.subTest(host=host, method=method):
                    self.assertEqual(self.request('/youtube-bridge.js', method, host)[0], 403)
        self.assertEqual(self.request('/youtube-bridge.js', extra_hosts=(self.parts.netloc,))[0], 403)

    def test_no_mutations_preflight_or_cors(self):
        for method in ('POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS', 'TRACE', 'CONNECT'):
            with self.subTest(method=method):
                status, headers, _ = self.request('/player', method)
                self.assertEqual(status, 405)
                self.assertFalse(any(k.lower().startswith('access-control-') for k in headers))

    def test_head_has_security_headers_and_no_body(self):
        path = f'/player?v={VIDEO}&channel={CHANNEL}'
        status, headers, body = self.request(path, 'HEAD')
        self.assertEqual(status, 200)
        self.assertGreater(int(headers['Content-Length']), 0)
        self.assertEqual(body, b'')
        self.assertIn('Content-Security-Policy', headers)

    def test_status_and_player_share_viewport_without_hiding_youtube_controls(self):
        _, headers, body = self.request(f'/player?v={VIDEO}&channel={CHANNEL}')
        parser = PageParser()
        parser.feed(body.decode())
        css = ''.join(parser.styles)
        self.assertIn('body{display:grid;grid-template-rows:auto minmax(0,1fr)', css)
        digest = base64.b64encode(hashlib.sha256(css.encode()).digest()).decode()
        self.assertIn(f"'sha256-{digest}'", headers['Content-Security-Policy'])

    def test_player_query_rejects_missing_extra_duplicate_and_injection_values(self):
        queries = ('', f'v={VIDEO}', f'channel={CHANNEL}',
                   f'v={VIDEO}&channel=short', f'v=bad&channel={CHANNEL}',
                   f'v={VIDEO}%0A&channel={CHANNEL}',
                   f'v={VIDEO}&channel={CHANNEL}%0A',
                   f'v={VIDEO}&channel={CHANNEL}&v={VIDEO}',
                   f'v={VIDEO}&channel={CHANNEL}&channel={CHANNEL}',
                   f'v={VIDEO}&channel={CHANNEL}&app_origin=https://evil.example',
                   f'v={VIDEO}&channel=%22%3E%3Cscript%3Ex%3C/script%3E',
                   f'v={VIDEO}&channel={CHANNEL}&junk')
        for query in queries:
            with self.subTest(query=query):
                self.assertEqual(self.request('/player?' + query)[0], 400)

    def test_python_url_rejects_invalid_video_ids_and_channels(self):
        for video in ('', 'short', VIDEO + '\n', '../' + VIDEO, None, 123):
            with self.subTest(video=video), self.assertRaises(ValueError):
                self.bridge.url(video, CHANNEL)
        for channel in ('', 'a' * 15, CHANNEL + '\n', 'a/b' * 10, None, 123):
            with self.subTest(channel=channel), self.assertRaises(ValueError):
                self.bridge.url(VIDEO, channel)
        self.bridge.url(VIDEO, 'a_A-0123456789012')


@unittest.skipUnless(importlib.util.find_spec('studio.video_bridge'), 'module not implemented yet')
class VideoBridgeLifecycleTests(unittest.TestCase):
    def test_custom_web_root_serves_only_fixed_asset_and_never_discloses_paths(self):
        from studio.video_bridge import VideoBridge
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'youtube-bridge.js').write_bytes(b'/* isolated bridge asset */')
            (root / 'app.js').write_bytes(b'not public')
            bridge = VideoBridge(APP_ORIGIN, web_root=root)
            self.addCleanup(bridge.close)
            connection = HTTPConnection('127.0.0.1', urlsplit(bridge.origin).port, timeout=3)
            self.addCleanup(connection.close)
            connection.request('GET', '/youtube-bridge.js')
            response = connection.getresponse()
            self.assertEqual(response.status, 200)
            self.assertEqual(response.read(), b'/* isolated bridge asset */')
            connection.request('GET', f'/player?v={VIDEO}&channel={CHANNEL}')
            response = connection.getresponse()
            self.assertNotIn(str(root).encode(), response.read())
            connection.request('GET', '/app.js')
            response = connection.getresponse()
            self.assertEqual(response.status, 404)
            self.assertNotIn(b'not public', response.read())
            connection.close()
            bridge.close()

    def test_concurrent_close_is_safe(self):
        from studio.video_bridge import VideoBridge
        bridge = VideoBridge(APP_ORIGIN)
        errors = []
        def close():
            try:
                bridge.close()
            except Exception as error:
                errors.append(error)
        threads = [threading.Thread(target=close) for _ in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=3)
        self.assertEqual(errors, [])
        self.assertFalse(any(t.is_alive() for t in threads))

    def test_unsafe_parent_origin_is_rejected_before_start(self):
        from studio.video_bridge import VideoBridge
        for origin in ('*', 'null', '', None, 'https://evil.example',
                       APP_ORIGIN + '/', APP_ORIGIN + '/path', APP_ORIGIN + '?x=1',
                       'http://user@127.0.0.1:8765', APP_ORIGIN + '\r\nX: yes',
                       'http://127.0.0.1:0', 'http://127.0.0.1:65536'):
            with self.subTest(origin=origin), self.assertRaises(ValueError):
                VideoBridge(origin)

    def test_close_is_idempotent_stops_thread_and_releases_port(self):
        from studio.video_bridge import VideoBridge
        bridge = VideoBridge(APP_ORIGIN)
        port = urlsplit(bridge.origin).port
        bridge.close()
        bridge.close()
        self.assertFalse(any(t.name == f'video-bridge-{port}' for t in threading.enumerate()))
        with socket.socket() as connection:
            connection.settimeout(.5)
            self.assertNotEqual(connection.connect_ex(('127.0.0.1', port)), 0)


"""Unprivileged, separate-origin YouTube player; no application APIs or secrets."""

import base64
import hashlib
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import re
import threading
from urllib.parse import parse_qs, urlencode, urlsplit


_VIDEO = re.compile(r'[A-Za-z0-9_-]{11}', re.ASCII)
_CHANNEL = re.compile(r'[A-Za-z0-9_-]{16,}', re.ASCII)
_APP_ORIGIN = re.compile(r'http://127\.0\.0\.1:([1-9][0-9]{0,4})', re.ASCII)
_STYLE = (
    'html,body{margin:0;width:100%;height:100%;background:#111;color:#eee;'
    'font:14px system-ui,sans-serif}body{display:grid;grid-template-rows:auto minmax(0,1fr)}'
    '#player{display:block;width:100%;height:100%;grid-row:2;min-height:0;'
    'border:0}#bridge-status{margin:0;padding:12px}#bridge-status:empty{display:none}'
)
_STYLE_HASH = base64.b64encode(hashlib.sha256(_STYLE.encode()).digest()).decode('ascii')


def _public_values(video_id, channel):
    if not isinstance(video_id, str) or not _VIDEO.fullmatch(video_id):
        raise ValueError('Invalid YouTube video ID')
    if not isinstance(channel, str) or not _CHANNEL.fullmatch(channel):
        raise ValueError('Invalid bridge channel')


class _BridgeServer(ThreadingHTTPServer):
    daemon_threads = True


class VideoBridge:
    """Start a daemon bridge on an ephemeral IPv4 loopback port.

    app_origin must be the main application's exact http://127.0.0.1:port
    origin, without a trailing slash. Only public video/channel values enter
    the bridge. The caller owns shutdown and may safely call close repeatedly.
    """

    def __init__(self, app_origin, web_root=None):
        match = _APP_ORIGIN.fullmatch(app_origin) if isinstance(app_origin, str) else None
        if not match or int(match[1]) > 65535:
            raise ValueError('Expected an exact HTTP IPv4 loopback application origin')
        self.app_origin = app_origin
        root = Path(web_root) if web_root is not None else Path(__file__).resolve().parents[1] / 'web'
        # Resolve only the one fixed asset, never a browser-supplied file path.
        self._script = (root / 'youtube-bridge.js').read_bytes()
        self._close_lock = threading.Lock()
        self._closed = False
        self._server = _BridgeServer(('127.0.0.1', 0), _Handler)
        while self._server.server_port == int(match[1]):
            self._server.server_close()
            self._server = _BridgeServer(('127.0.0.1', 0), _Handler)
        self.origin = f'http://127.0.0.1:{self._server.server_port}'
        self._server.bridge = self
        self._thread = threading.Thread(
            target=self._server.serve_forever, kwargs={'poll_interval': .05},
            name=f'video-bridge-{self._server.server_port}', daemon=True)
        try:
            self._thread.start()
        except BaseException:
            self._server.server_close()
            raise

    def url(self, video_id, channel):
        _public_values(video_id, channel)
        return self.origin + '/player?' + urlencode({'v': video_id, 'channel': channel})

    def close(self):
        with self._close_lock:
            if self._closed:
                return
            self._server.shutdown()
            self._server.server_close()
            self._thread.join()
            self._closed = True

    def _page(self, video_id, channel):
        _public_values(video_id, channel)
        return (
            '<!doctype html><html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<meta name="referrer" content="strict-origin-when-cross-origin">'
            f'<meta name="bridge-app-origin" content="{escape(self.app_origin, quote=True)}">'
            f'<meta name="bridge-video-id" content="{escape(video_id, quote=True)}">'
            f'<meta name="bridge-channel" content="{escape(channel, quote=True)}">'
            '<title>YouTube player</title>'
            f'<style>{_STYLE}</style><script src="/youtube-bridge.js" defer></script>'
            '</head><body><p id="bridge-status" role="status">Loading YouTube player…</p>'
            '<div id="player"></div></body></html>'
        )


class _Handler(BaseHTTPRequestHandler):
    server_version = 'VideoBridge/1.0'
    sys_version = ''

    def setup(self):
        super().setup()
        self.connection.settimeout(5)

    def log_message(self, *args):
        # The opaque channel is not a log identifier.
        pass

    def parse_request(self):
        if not super().parse_request():
            return False
        hosts = self.headers.get_all('Host', [])
        if hosts != [urlsplit(self.server.bridge.origin).netloc]:
            self._send(403, 'Invalid Host')
            return False
        return True

    def _send(self, status, body, content_type='text/plain; charset=utf-8'):
        if isinstance(body, str):
            body = body.encode('utf-8')
        app_origin = self.server.bridge.app_origin
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'strict-origin-when-cross-origin')
        self.send_header('Content-Security-Policy',
                         "default-src 'none'; script-src 'self' "
                         'https://www.youtube.com/iframe_api https://www.youtube.com/s/player/; '
                         f"style-src 'sha256-{_STYLE_HASH}'; "
                         'frame-src https://www.youtube-nocookie.com https://www.youtube.com; '
                         f"frame-ancestors {app_origin}; base-uri 'none'; form-action 'none'")
        if status == 405:
            self.send_header('Allow', 'GET, HEAD')
        self.end_headers()
        if self.command != 'HEAD':
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

    def do_GET(self):
        try:
            target = urlsplit(self.path)
        except ValueError:
            self._send(400, 'Invalid request')
            return
        if target.scheme or target.netloc or target.fragment:
            self._send(404, 'Not found')
        elif target.path == '/youtube-bridge.js' and not target.query:
            self._send(200, self.server.bridge._script, 'text/javascript; charset=utf-8')
        elif target.path == '/player':
            try:
                query = parse_qs(target.query, keep_blank_values=True, strict_parsing=True,
                                 encoding='utf-8', errors='strict', max_num_fields=2)
                if set(query) != {'v', 'channel'} or any(len(v) != 1 for v in query.values()):
                    raise ValueError('Invalid parameters')
                body = self.server.bridge._page(query['v'][0], query['channel'][0])
            except (ValueError, UnicodeError):
                self._send(400, 'Invalid player parameters')
                return
            self._send(200, body, 'text/html; charset=utf-8')
        else:
            self._send(404, 'Not found')

    do_HEAD = do_GET

    def _method_not_allowed(self):
        self._send(405, 'Method not allowed')

    def __getattr__(self, name):
        if name.startswith('do_'):
            return self._method_not_allowed
        raise AttributeError(name)


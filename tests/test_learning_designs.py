from html.parser import HTMLParser
from pathlib import Path
import re
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import urlopen

from studio.server import make_server

PROJECT = Path(__file__).resolve().parents[1]


class PreviewParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = []
        self.unsafe = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if 'id' in attrs:
            self.ids.append(attrs['id'])
        self.unsafe.extend(key for key in attrs if key == 'style' or key.startswith('on'))


class LearningDesignContractTests(unittest.TestCase):
    def test_preview_is_explicit_demo_not_live_translation(self):
        html = (PROJECT / 'web/concept.html').read_text('utf-8')
        self.assertIn('自编示例', html)
        self.assertIn('未接入自动翻译', html)
        self.assertIn('合成示范', html)
        self.assertNotIn('/app.js', html)
        parser = PreviewParser()
        parser.feed(html)
        self.assertEqual(len(parser.ids), len(set(parser.ids)))
        self.assertEqual(parser.unsafe, [])
        for required in ('lesson-audio', 'play-pause', 'previous-line', 'next-line', 'translation-toggle',
                         'vocab-title', 'vocab-meaning', 'save-word', 'sentence-list', 'playback-rate'):
            self.assertIn(required, parser.ids)

    def test_learning_text_contrast(self):
        css = (PROJECT / 'web/concept.css').read_text('utf-8')
        def color(block, name):
            return re.search(r'--' + name + r':#([0-9a-f]{6})', block).group(1)
        def luminance(value):
            channels = [int(value[i:i + 2], 16) / 255 for i in (0, 2, 4)]
            channels = [c / 12.92 if c <= .04045 else ((c + .055) / 1.055) ** 2.4 for c in channels]
            return sum(c * w for c, w in zip(channels, (.2126, .7152, .0722)))
        def ratio(a, b):
            low, high = sorted((luminance(a), luminance(b)))
            return (high + .05) / (low + .05)
        folio = re.search(r':root\{([^}]+)', css).group(1)
        prism = re.search(r'\[data-study="prism"\]\{([^}]+)', css).group(1)
        self.assertGreaterEqual(ratio(color(folio, 'muted'), color(folio, 'paper')), 4.5)
        self.assertGreaterEqual(ratio(color(folio, 'muted'), color(folio, 'accent-soft')), 4.5)
        self.assertGreaterEqual(ratio(color(prism, 'muted'), color(prism, 'paper')), 4.5)
        self.assertGreaterEqual(ratio(color(prism, 'muted'), 'd5e3eb'), 4.5)

    def test_focus_view_keeps_audio_errors_visible(self):
        css = (PROJECT / 'web/concept.css').read_text('utf-8')
        rule = re.search(r'\[data-study="nocturne"\] \.audio-message\{([^}]+)', css).group(1)
        self.assertNotIn('display:none', rule)

    def test_english_only_selector_matches_the_body_itself(self):
        css = (PROJECT / 'web/concept.css').read_text('utf-8')
        self.assertIn('[data-study="folio"].english-only .sentence', css)


class LearningDesignHTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.server = make_server(Path(self.temp.name), 0, web_root=PROJECT / 'web')
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f'http://127.0.0.1:{self.server.server_port}'

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.temp.cleanup()

    def test_all_new_views_and_comparison_are_isolated(self):
        for view in ('folio', 'prism', 'nocturne'):
            with self.subTest(view=view), urlopen(self.base + '/concept?view=' + view) as response:
                body = response.read().decode()
                self.assertIn(f'data-study="{view}"', body)
                self.assertNotIn('data-study="__VIEW__"', body)
        with urlopen(self.base + '/concepts') as response:
            body = response.read().decode()
            for view in ('folio', 'prism', 'nocturne'):
                self.assertIn('/concept?view=' + view, body)
        with urlopen(self.base + '/?design=studio') as response:
            self.assertIn('id="task-form"', response.read().decode())

    def test_unknown_view_is_not_reflected_as_markup(self):
        with urlopen(self.base + '/concept?view=%22%3E%3Cscript%3E') as response:
            body = response.read().decode()
            self.assertIn('data-study="folio"', body)
            self.assertNotIn('<script>', body)

    def test_only_whitelisted_preview_assets_are_served(self):
        for asset in ('/concept.css', '/concept-core.js', '/concept.js', '/concepts.css'):
            with self.subTest(asset=asset), urlopen(self.base + asset) as response:
                self.assertEqual(response.status, 200)
        with self.assertRaises(HTTPError) as raised:
            urlopen(self.base + '/demo/audio/../service.py')
        self.assertEqual(raised.exception.code, 404)


if __name__ == '__main__':
    unittest.main()

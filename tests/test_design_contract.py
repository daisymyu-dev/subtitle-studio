from collections import Counter
from html.parser import HTMLParser
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ContractParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = []
        self.inline_attributes = []
        self.design_links = []
        self.download_formats = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if 'id' in attrs:
            self.ids.append(attrs['id'])
        if tag == 'button' and 'data-format' in attrs:
            self.download_formats.append(attrs['data-format'])
        for key in attrs:
            if key == 'style' or key.startswith('on'):
                self.inline_attributes.append(key)
        if tag == 'a' and attrs.get('href', '').startswith('/?design='):
            self.design_links.append(attrs['href'])


class DesignContractTests(unittest.TestCase):
    def test_learning_profile_and_card_are_local_and_accessible(self):
        html=(ROOT/'web/index.html').read_text('utf-8');parser=ContractParser();parser.feed(html)
        for name in ('learning-tools','learning-toggle','learning-card','learning-term','learning-meaning','learning-close','learning-warning','learning-ipa','learning-speak','learning-stop','learning-audio','learning-audio-status'):
            self.assertIn(name,parser.ids)
        self.assertIn('IELTS 7',html)
        self.assertLess(html.index('src="/learning-core.js"'),html.index('src="/watch-sync.js"'))
        self.assertLess(html.index('src="/learning-pronunciations.js"'),html.index('src="/learning-highlights.js"'))
        self.assertIn('非视频原声',html)
        self.assertIn('preload="none"',html)
    def test_original_player_width_cannot_overflow_narrow_cards(self):
        css=(ROOT/'web/watch.css').read_text('utf-8')
        self.assertIn('.watch-frame-wrap{width:100%;min-width:0}',css)
    def test_two_pages_have_original_video_and_synchronized_full_text(self):
        html=(ROOT/'web/index.html').read_text('utf-8');parser=ContractParser();parser.feed(html)
        for name in ('page-watch','page-study','watch-input','study-pane','original-video-frame','watch-current-en','watch-current-zh','watch-transcript-list','watch-follow'):
            self.assertIn(name,parser.ids)
        self.assertIn('name="video-bridge"',html)
        self.assertNotIn('src="https://www.youtube.com/iframe_api"',html)
    def test_only_word_download_remains(self):
        parser = ContractParser()
        parser.feed((ROOT / 'web/index.html').read_text('utf-8'))
        self.assertEqual(parser.download_formats, ['docx'])
        self.assertIn('word-start', parser.ids)
        self.assertIn('word-download', parser.ids)

    def test_original_shadowing_has_real_controls_and_honest_boundaries(self):
        html=(ROOT/'web/index.html').read_text('utf-8')
        parser=ContractParser();parser.feed(html)
        for name in ('shadow-open','shadowing','shadow-prepare','shadow-audio','shadow-play','shadow-pause',
                     'shadow-previous','shadow-next','shadow-loop','shadow-gap','shadow-rate','shadow-toggle-chinese','shadow-list'):
            self.assertIn(name,parser.ids)
        self.assertIn('不是合成语音',html)
        self.assertIn('不一定是完整句子',html)

    def test_three_designs_share_accessible_functional_ids(self):
        parser = ContractParser()
        parser.feed((ROOT / 'web/index.html').read_text('utf-8'))
        required = {'task-form', 'url', 'file', 'file-label', 'mode', 'language', 'model', 'asr-language',
                    'tab-youtube', 'tab-file', 'youtube-pane', 'file-pane', 'start', 'shutdown', 'form-error',
                    'step-input', 'step-captions', 'step-export', 'status-card', 'status-title', 'status-message',
                    'recognition-progress', 'results', 'result-title', 'result-meta', 'result-warning',
                    'preview', 'preview-note', 'output-path'}
        self.assertTrue(required.issubset(parser.ids))
        self.assertFalse([key for key, count in Counter(parser.ids).items() if count > 1])
        self.assertEqual(set(parser.design_links), {'/?design=studio', '/?design=signal', '/?design=chrome'})
        self.assertEqual(parser.inline_attributes, [])

    def test_theme_css_has_three_layouts_and_reduced_motion(self):
        css = (ROOT / 'web/themes.css').read_text('utf-8')
        for name in ('studio', 'signal', 'chrome'):
            self.assertIn(f'[data-design="{name}"]', css)
        self.assertIn('prefers-reduced-motion', (ROOT / 'web/style.css').read_text('utf-8'))

    def test_learning_uses_one_gold_legend_and_explains_whole_video_repeat_limit(self):
        html=(ROOT/'web/index.html').read_text('utf-8')
        css=(ROOT/'web/learning.css').read_text('utf-8')
        self.assertIn('金色 · 值得学的表达',html)
        self.assertIn('同一表达全文最多标注 2 次',html)
        self.assertNotIn('aria-label="标注类别"',html)
        self.assertIn('--learn-gold:',css)
        self.assertNotIn('--learn-vocab',css)
        self.assertNotIn('--learn-finance',css)

    def test_brand_accessible_name_contains_visible_brand(self):
        html = (ROOT / 'web/index.html').read_text('utf-8')
        self.assertIn('aria-label="字幕工作台，', html)

    def test_decorative_input_label_does_not_change_accessible_name(self):
        html = (ROOT / 'web/index.html').read_text('utf-8')
        self.assertIn('class="label-aside" aria-hidden="true"', html)

    def test_signal_header_and_footer_have_contrasting_focus_rule(self):
        css = (ROOT / 'web/themes.css').read_text('utf-8')
        self.assertIn('[data-design="signal"] .topbar a:focus-visible', css)
        self.assertIn('[data-design="signal"] footer a:focus-visible', css)
        self.assertIn('outline-color:#ebf96b', css)

    def test_signal_poster_does_not_float_over_results_when_scrolled(self):
        css = (ROOT / 'web/themes.css').read_text('utf-8')
        rule = re.search(r'\[data-design="signal"\] \.intro\{([^}]+)\}', css)
        self.assertIsNotNone(rule)
        self.assertNotIn('position:sticky', rule.group(1))


if __name__ == '__main__':
    unittest.main()

import unittest

from studio.subtitles import (
    Cue, choose_track, clean_cues, normalize_youtube_url,
    parse_subtitles, render_subtitles, safe_filename,
)


class SubtitleTests(unittest.TestCase):
    def test_normalize_url(self):
        for url in ['https://youtu.be/BaW_jenozKc?t=1',
                    'https://www.youtube.com/shorts/BaW_jenozKc',
                    'https://www.youtube.com/watch?v=BaW_jenozKc&list=abc']:
            self.assertEqual(normalize_youtube_url(url),
                             'https://www.youtube.com/watch?v=BaW_jenozKc')

    def test_reject_unsafe_urls(self):
        for url in ['http://127.0.0.1/a', 'https://youtube.com.evil.test/watch?v=BaW_jenozKc',
                    'https://user:pass@youtube.com/watch?v=BaW_jenozKc',
                    'https://youtube.com:999/watch?v=BaW_jenozKc',
                    'https://youtube.com/playlist?list=xxx', 'file:///etc/passwd']:
            with self.subTest(url=url), self.assertRaises(ValueError):
                normalize_youtube_url(url)

    def test_parse_vtt(self):
        text = 'WEBVTT\n\nNOTE ignored\ncomment\n\n1\n00:00:00.100 --> 00:00:02.000 align:start\n<c>Hello &amp; welcome.</c>\n\n00:02.000 --> 00:03.100\nSecond line.\n'
        self.assertEqual(parse_subtitles(text, 'vtt'), [
            Cue(.1, 2, 'Hello & welcome.'), Cue(2, 3.1, 'Second line.')])

    def test_parse_srt(self):
        self.assertEqual(parse_subtitles('\ufeff1\n00:00:01,000 --> 00:00:02,250\nHello\nworld!\n', 'srt'),
                         [Cue(1, 2.25, 'Hello world!')])

    def test_parse_json3(self):
        self.assertEqual(parse_subtitles('{"events":[{"tStartMs":10,"dDurationMs":1200,"segs":[{"utf8":"Hi "},{"utf8":"there"}]}]}', 'json3'),
                         [Cue(.01, 1.21, 'Hi there')])

    def test_only_rolling_overlaps_are_deduplicated(self):
        cues = [Cue(0, 2, 'Hello world'), Cue(1, 3, 'Hello world again'),
                Cue(4, 5, 'Hello world again')]
        self.assertEqual(clean_cues(cues, rolling=True),
                         [Cue(0, 3, 'Hello world again'), Cue(4, 5, 'Hello world again')])

    def test_export_formats_and_rounding(self):
        cues = [Cue(.9996, 2.001, 'One & two.')]
        self.assertIn('00:00:01,000 --> 00:00:02,001', render_subtitles(cues, 'srt'))
        self.assertTrue(render_subtitles(cues, 'vtt').startswith('WEBVTT\n'))
        self.assertEqual(render_subtitles(cues, 'txt'), 'One & two.\n')

    def test_original_auto_beats_translated_uploaded_track(self):
        info = {'language': 'en', 'subtitles': {'zh': [{'ext': 'vtt', 'url': 'https://www.youtube.com/a'}]},
                'automatic_captions': {'en-orig': [{'ext': 'vtt', 'url': 'https://www.youtube.com/b'}]}}
        self.assertEqual(choose_track(info)['kind'], 'platform_auto')

    def test_uploaded_track_preferred_within_language(self):
        info = {'language': 'en', 'subtitles': {'en-test': [{'ext': 'vtt', 'url': 'https://www.youtube.com/a'}]},
                'automatic_captions': {'en-orig': [{'ext': 'json3', 'url': 'https://www.youtube.com/b'}]}}
        self.assertEqual(choose_track(info)['kind'], 'uploaded_caption')

    def test_automatic_translations_never_pass_as_original(self):
        info = {'language': 'zh', 'automatic_captions': {
            'en': [{'ext': 'vtt', 'url': 'https://www.youtube.com/api/timedtext?lang=zh&tlang=en', 'name': 'English'}]}}
        self.assertIsNone(choose_track(info, 'en'))

    def test_filename_is_safe(self):
        self.assertNotIn('/', safe_filename('../CON:<test>?'))
        self.assertFalse(safe_filename('CON').upper() == 'CON')

    def test_original_language_inferred_from_original_auto_track(self):
        info = {'subtitles': {'fr': [{'ext': 'vtt', 'url': 'https://www.youtube.com/a'}]},
                'automatic_captions': {'en-orig': [{'ext': 'vtt', 'url': 'https://www.youtube.com/b'}]}}
        self.assertEqual(choose_track(info)['code'], 'en-orig')

    def test_ambiguous_multilingual_tracks_do_not_guess_original(self):
        info = {'subtitles': {'fr': [{'ext': 'vtt', 'url': 'https://www.youtube.com/a'}],
                              'en': [{'ext': 'vtt', 'url': 'https://www.youtube.com/b'}]}}
        self.assertIsNone(choose_track(info))
        self.assertEqual(choose_track(info, 'en')['code'], 'en')

    def test_literal_caption_text_survives_repeated_validation(self):
        cues = parse_subtitles('WEBVTT\n\n00:00:00.000 --> 00:00:02.000\nUse &lt;name&gt; &amp;amp;.\n', 'vtt')
        self.assertEqual(render_subtitles(clean_cues(cues), 'txt'), 'Use <name> &amp;.\n')

    def test_chinese_rolling_prefix_without_spaces(self):
        cues = [Cue(0, 2, '你好世界'), Cue(1, 3, '你好世界欢迎'), Cue(4, 5, '你好世界欢迎')]
        self.assertEqual(clean_cues(cues, rolling=True), [Cue(0, 3, '你好世界欢迎'), Cue(4, 5, '你好世界欢迎')])

    def test_long_rolling_sequence_keeps_bounded_time_windows(self):
        words = [f'w{i}' for i in range(30)]
        cues = [Cue(i, i + 3, ' '.join(words[i:i + 3])) for i in range(28)]
        cleaned = clean_cues(cues, rolling=True)
        self.assertGreater(len(cleaned), 1)
        self.assertLessEqual(max(cue.end - cue.start for cue in cleaned), 8)
        self.assertEqual(' '.join(cue.text for cue in cleaned), ' '.join(words))


if __name__ == '__main__':
    unittest.main()

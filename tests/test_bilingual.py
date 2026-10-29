import io
import json
import unittest
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlparse

from studio.bilingual import (GoogleWebTranslator, TranslationError, align_captions,
                              choose_chinese_track, complete_chinese)
from studio.subtitles import Cue


def track(code, translated=False):
    return {'ext': 'vtt', 'url': 'https://www.youtube.com/api/timedtext?lang=en' + ('&tlang=' + code if translated else '')}


class BilingualTests(unittest.TestCase):
    def test_uploaded_chinese_precedes_platform_translation(self):
        info = {'subtitles': {'zh-Hant': [track('zh')]},
                'automatic_captions': {'zh-Hans': [track('zh-Hans', True)]}}
        self.assertEqual(choose_chinese_track(info)['kind'], 'uploaded_chinese')

    def test_translated_track_is_labelled_and_unknown_not_selected(self):
        selected = choose_chinese_track({'automatic_captions': {'zh-Hans': [track('zh-Hans', True)]}})
        self.assertEqual(selected['kind'], 'youtube_translation')
        self.assertIsNone(choose_chinese_track({'subtitles': {'ja': [track('ja')]}}))

    def test_overlap_components_keep_all_words_once(self):
        english = [Cue(0, 2, 'One.'), Cue(2, 4, 'Two.'), Cue(6, 7, 'Three.')]
        chinese = [Cue(0, 4, '第一二句。'), Cue(6, 7, '第三句。')]
        blocks = align_captions(english, chinese)
        self.assertEqual([x['english'] for x in blocks], ['One. Two.', 'Three.'])
        self.assertEqual([x['chinese'] for x in blocks], ['第一二句。', '第三句。'])
        self.assertEqual(blocks[0]['end'], 4)

    def test_unmatched_english_is_translated_and_not_omitted(self):
        blocks = align_captions([Cue(i * 2, i * 2 + 1, str(i)) for i in range(250)], [])
        class Translator:
            def translate_many(self, texts, progress=None):
                return ['译' + x for x in texts]
        complete_chinese(blocks, Translator())
        self.assertEqual(len(blocks), 250)
        self.assertEqual(blocks[-1]['chinese'], '译249')

    def test_incomplete_translation_cannot_be_exported(self):
        class Translator:
            def translate_many(self, texts, progress=None):
                return ['']
        with self.assertRaises(TranslationError):
            complete_chinese(align_captions([Cue(0, 1, 'Missing.')], []), Translator())

    def test_multiple_chinese_segments_inside_one_english_are_preserved(self):
        blocks = align_captions([Cue(0, 4, 'Full sentence.')], [Cue(0, 2, '前半句'), Cue(2, 4, '后半句')])
        self.assertEqual(blocks[0]['chinese'], '前半句 后半句')

    def test_partial_chinese_cannot_complete_a_long_overlapping_transcript(self):
        blocks = align_captions([Cue(i, i + 2, f'English {i}.') for i in range(251)], [Cue(0, 2, '开头')])
        self.assertGreater(len(blocks), 1)
        self.assertTrue(all(x['end'] - x['start'] <= 30 for x in blocks))
        self.assertFalse(blocks[-1]['chinese'])
        class Translator:
            def translate_many(self, texts, progress=None):
                self.texts = texts
                return ['完整译文' for _ in texts]
        translator = Translator()
        complete_chinese(blocks, translator)
        self.assertIn('English 250.', ' '.join(translator.texts))

    def test_alignment_is_chronological_even_if_input_is_not(self):
        blocks = align_captions([Cue(2, 4, 'Two.'), Cue(0, 2, 'One.')], [Cue(0, 4, '一二。')])
        self.assertEqual(blocks[0]['english'], 'One. Two.')
        self.assertEqual(blocks[0]['start'], 0)

    def test_chinese_covering_only_half_a_sentence_is_not_complete(self):
        blocks = align_captions([Cue(0, 10, 'A whole sentence.')], [Cue(0, 3, '片段')])
        self.assertEqual(blocks[0]['chinese'], '')


class GoogleTests(unittest.TestCase):
    def client(self, transform):
        self.requests = []
        def open_request(request, timeout):
            text = parse_qs(urlparse(request.full_url).query)['q'][0]
            self.requests.append(text)
            return io.BytesIO(json.dumps([[[transform(text), text]]]).encode())
        return GoogleWebTranslator(opener=open_request, sleep=lambda _: None)

    def test_batch_preserves_order_deduplicates_and_reports(self):
        translator = self.client(lambda x: '\n'.join('中文' + line for line in x.split('\n')))
        progress = []
        self.assertEqual(translator.translate_many(['One', 'Two', 'One'], lambda a, b: progress.append((a, b))),
                         ['中文One', '中文Two', '中文One'])
        self.assertEqual(len(self.requests), 1)
        self.assertEqual(progress[-1], (3, 3))

    def test_lost_newlines_fall_back_to_smaller_batches(self):
        translator = self.client(lambda x: '译文' + x.replace('\n', ' '))
        self.assertEqual(translator.translate_many(['One', 'Two']), ['译文One', '译文Two'])
        self.assertEqual(len(self.requests), 3)

    def test_long_input_is_not_truncated(self):
        translator = self.client(lambda x: '译文')
        translator.translate_many(['word ' * 1400])
        self.assertTrue(all(len(x) <= 2400 for x in self.requests))
        self.assertGreater(len(self.requests), 1)
        self.assertEqual(sum(x.count('word') for x in self.requests), 1400)

    def test_rate_limit_is_bounded_and_private_text_not_exposed(self):
        calls = []
        def limited(request, timeout):
            calls.append(1)
            raise HTTPError(request.full_url, 429, 'Rate limit', {}, None)
        with self.assertRaises(TranslationError) as raised:
            GoogleWebTranslator(opener=limited, sleep=lambda _: None).translate_many(['private phrase'])
        self.assertLessEqual(len(calls), 3)
        self.assertNotIn('private phrase', str(raised.exception))

    def test_malformed_response_is_not_a_translation(self):
        with self.assertRaises(TranslationError):
            GoogleWebTranslator(opener=lambda *a, **k: io.BytesIO(b'{"bad":true}')).translate_many(['Hello'])

    def test_a_missing_segment_is_not_silently_discarded(self):
        raw = json.dumps([[['第一句', 'First.'], [None, 'Second.']]]).encode()
        with self.assertRaises(TranslationError):
            GoogleWebTranslator(opener=lambda *a, **k: io.BytesIO(raw)).translate_many(['First. Second.'])

    def test_whitespace_translation_cannot_replace_nonblank_source(self):
        raw = json.dumps([[['第一句', 'First.'], ['   ', 'Second.']]]).encode()
        with self.assertRaises(TranslationError):
            GoogleWebTranslator(opener=lambda *a, **k: io.BytesIO(raw)).translate_many(['First. Second.'])

    def test_blank_separator_segment_preserves_batch_boundaries(self):
        raw = json.dumps([[['第一句', 'First.'], ['\n', '\n'], ['第二句', 'Second.']]]).encode()
        translated = GoogleWebTranslator(opener=lambda *a, **k: io.BytesIO(raw)).translate_many(['First.', 'Second.'])
        self.assertEqual(translated, ['第一句', '第二句'])

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from studio.bilingual import TranslationError
from studio.service import Pipeline, UserError, validate_options
from studio.subtitles import Cue


class Tools:
    def __init__(self, count=3, chinese=True):
        self.count, self.chinese = count, chinese
    def metadata(self, url, **kwargs):
        return {'title': '完整中英对照测试', 'language': 'en', 'duration': self.count * 2,
                'subtitles': {'en': [{'ext': 'json3', 'url': 'https://www.youtube.com/api/timedtext?lang=en'}],
                              **({'zh': [{'ext': 'json3', 'url': 'https://www.youtube.com/api/timedtext?lang=zh'}]} if self.chinese else {})}}
    def caption(self, track):
        return json.dumps({'events': [{'tStartMs': i * 2000, 'dDurationMs': 1000,
                                      'segs': [{'utf8': ('中文' if track['code'].startswith('zh') else 'English ') + str(i)}]}
                                     for i in range(self.count)]})


class Translator:
    def __init__(self):
        self.calls = []
    def translate_many(self, texts, progress=None):
        self.calls.extend(texts)
        if progress:
            progress(len(texts), len(texts))
        return ['译文' + x for x in texts]


class WordPipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.desktop = self.root / 'Desktop'
        self.desktop.mkdir()
        self.translator = Translator()
        self.written = []
    def tearDown(self):
        self.temp.cleanup()
    def writer(self, destination, title, url, blocks, source_note, english_note):
        self.written.extend(blocks)
        self.english_note = english_note
        Path(destination).write_bytes(b'word document test double')
        return Path(destination)
    def pipeline(self, tools=None, **kwargs):
        return Pipeline(self.root, tools or Tools(), translator=self.translator,
                        word_writer=self.writer, desktop_dir=self.desktop, **kwargs)
    def run_word(self, pipeline):
        return pipeline.process('youtube', 'https://youtu.be/BaW_jenozKc', {'bilingual_word': True})

    def test_option_is_explicit_boolean(self):
        self.assertFalse(validate_options({})['bilingual_word'])
        for value in ('true', 1, None, {}):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_options({'bilingual_word': value})

    def test_full_document_does_not_use_truncated_preview(self):
        result = self.run_word(self.pipeline(Tools(count=251)))
        self.assertEqual(len(result['preview']), 200)
        self.assertEqual(len(self.written), 251)
        self.assertEqual(self.written[-1]['chinese'], '中文250')
        self.assertEqual(self.translator.calls, [])
        self.assertTrue(Path(result['desktop_path']).is_file())
        self.assertEqual(Path(result['desktop_path']).parent, self.desktop)
        saved = json.loads((Path(result['output_dir']) / 'bilingual.json').read_text('utf-8'))
        self.assertEqual(len(saved['blocks']), 251)
        self.assertIn('docx', result['files'])

    def test_missing_chinese_uses_translation(self):
        result = self.run_word(self.pipeline(Tools(chinese=False)))
        self.assertEqual(len(self.translator.calls), 3)
        self.assertIn('Google', result['chinese_source'])
        self.assertTrue(all(x['chinese'] for x in self.written))

    def test_word_records_actual_english_provenance(self):
        self.run_word(self.pipeline())
        self.assertIn('上传的英文字幕', self.english_note)

    def test_translation_failure_does_not_create_word_or_desktop_file(self):
        self.translator.translate_many = lambda *a, **k: (_ for _ in ()).throw(TranslationError('翻译暂不可用'))
        with self.assertRaises(UserError) as raised:
            self.run_word(self.pipeline(Tools(chinese=False)))
        self.assertEqual(raised.exception.code, 'translation')
        self.assertEqual(self.written, [])
        self.assertEqual(list(self.desktop.iterdir()), [])
        self.assertEqual(len(list((self.root / 'results').glob('*/*.txt'))), 1)

    def test_ordinary_extraction_does_not_translate_or_write_desktop(self):
        result = self.pipeline(Tools(chinese=False)).process('youtube', 'https://youtu.be/BaW_jenozKc', {})
        self.assertEqual(self.translator.calls, [])
        self.assertEqual(self.written, [])
        self.assertNotIn('desktop_path', result)

    def test_word_request_is_youtube_only(self):
        with self.assertRaises(ValueError):
            self.pipeline().process('file', self.root / 'file.srt', {'bilingual_word': True})

    def test_detected_non_english_asr_is_not_labelled_english(self):
        tools = Tools(chinese=False)
        tools.metadata = lambda *a, **k: {'title': '中文视频', 'language': 'zh'}
        tools.audio = lambda *a: self.root / 'sample.wav'
        with self.assertRaises(UserError) as raised:
            self.run_word(self.pipeline(tools, transcriber=lambda *a: ([Cue(0, 1, '中文')], {'language': 'zh'})))
        self.assertEqual(raised.exception.code, 'english_required')
        self.assertEqual(self.translator.calls, [])

    def test_missing_english_caption_can_transcribe_and_export_word(self):
        tools = Tools(chinese=False)
        tools.metadata = lambda *a, **k: {'title': 'Spoken English', 'language': 'en'}
        tools.audio = lambda *a: self.root / 'sample.wav'
        result = self.run_word(self.pipeline(tools, transcriber=lambda *a: ([Cue(0, 2, 'A spoken example.')], {'language': 'en'})))
        self.assertEqual(result['source'], 'local_asr')
        self.assertIn('Whisper', self.english_note)
        self.assertTrue(Path(result['desktop_path']).exists())

    def test_desktop_failure_is_not_success_and_keeps_local_word(self):
        with patch('studio.word_document.save_to_desktop', side_effect=OSError('Denied')):
            with self.assertRaises(UserError) as raised:
                self.run_word(self.pipeline())
        self.assertEqual(raised.exception.code, 'desktop_save')
        self.assertEqual(len(list((self.root / 'results').glob('*/*.docx'))), 1)
        self.assertEqual(list(self.desktop.iterdir()), [])

    def test_missing_json3_duration_cannot_silently_omit_english(self):
        tools = Tools(chinese=False)
        tools.caption = lambda *a: json.dumps({'events': [
            {'tStartMs': 0, 'dDurationMs': 1000, 'segs': [{'utf8': 'First.'}]},
            {'tStartMs': 1000, 'segs': [{'utf8': 'Second.'}]}]})
        with self.assertRaises(UserError) as raised:
            self.run_word(self.pipeline(tools))
        self.assertEqual(raised.exception.code, 'caption_parse')
        self.assertEqual(self.written, [])

    def test_malformed_vtt_cue_cannot_silently_omit_english(self):
        tools = Tools(chinese=False)
        tools.metadata = lambda *a, **k: {'title': 'Bad timing', 'subtitles': {'en': [{'ext': 'vtt', 'url': 'https://www.youtube.com/api/timedtext'}]}}
        tools.caption = lambda *a: 'WEBVTT\n\n00:00:00.000 --> 00:00:01.000\nFirst.\n\n00:00:bad --> 00:00:02.000\nSecond.\n'
        with self.assertRaises(UserError) as raised:
            self.run_word(self.pipeline(tools))
        self.assertEqual(raised.exception.code, 'caption_parse')
        self.assertEqual(self.written, [])

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import subprocess

from studio.service import NativeTools, Pipeline, UserError, validate_options
from studio.subtitles import Cue


class FakeTools:
    def __init__(self, info=None, fail=False):
        self.info = info or {'title': 'Example', 'language': 'en'}
        self.fail = fail
        self.audio_calls = 0

    def metadata(self, url, check_captions=True):
        if self.fail:
            raise UserError('network', '无法连接 YouTube。')
        return self.info

    def caption(self, track):
        return 'WEBVTT\n\n00:00:00.000 --> 00:00:01.000\nA local test.\n'

    def audio(self, url, folder):
        self.audio_calls += 1
        path = folder / 'audio.wav'
        path.write_bytes(b'test')
        return path


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.asr_calls = 0

    def tearDown(self):
        self.temp.cleanup()

    def asr(self, path, options, report):
        self.asr_calls += 1
        return [Cue(0, 1.5, 'A spoken test.')], {'language': 'en', 'duration': 1.5}

    def test_no_caption_falls_back_to_asr(self):
        tools = FakeTools()
        result = Pipeline(self.root, tools, self.asr).process('youtube', 'https://youtu.be/BaW_jenozKc', {})
        self.assertEqual(result['source'], 'local_asr')
        self.assertEqual(tools.audio_calls, 1)
        self.assertEqual(self.asr_calls, 1)
        self.assertEqual(set(result['files']), {'srt', 'vtt', 'txt'})
        self.assertTrue((Path(result['output_dir']) / result['files']['srt']).exists())
        study = json.loads((Path(result['output_dir']) / 'study-cues.json').read_text('utf-8'))
        self.assertEqual(study[0]['text'], 'A spoken test.')
        self.assertEqual(json.loads((Path(result['output_dir']) / 'metadata.json').read_text('utf-8'))['source'], 'local_asr')

    def test_metadata_failure_does_not_download_audio(self):
        tools = FakeTools(fail=True)
        with self.assertRaises(UserError) as raised:
            Pipeline(self.root, tools, self.asr).process('youtube', 'https://youtu.be/BaW_jenozKc', {})
        self.assertEqual(raised.exception.code, 'network')
        self.assertEqual(tools.audio_calls, 0)
        self.assertEqual(self.asr_calls, 0)

    def test_existing_captions_do_not_run_asr(self):
        tools = FakeTools({'title': '字幕测试', 'language': 'en', 'subtitles': {
            'en': [{'url': 'https://www.youtube.com/api/timedtext', 'ext': 'vtt'}]}})
        result = Pipeline(self.root, tools, self.asr).process('youtube', 'https://youtu.be/BaW_jenozKc', {})
        self.assertEqual(result['source'], 'uploaded_caption')
        self.assertEqual(self.asr_calls, 0)

    def test_caption_only_does_not_silently_transcribe(self):
        with self.assertRaises(UserError) as raised:
            Pipeline(self.root, FakeTools(), self.asr).process('youtube', 'https://youtu.be/BaW_jenozKc', {'mode': 'captions'})
        self.assertEqual(raised.exception.code, 'no_captions')
        self.assertEqual(self.asr_calls, 0)

    def test_imported_vtt_keeps_original_text(self):
        path = self.root / 'sample.vtt'
        path.write_text('WEBVTT\n\n00:00:00.000 --> 00:00:02.000\nOriginal, not rewritten.\n', encoding='utf-8')
        result = Pipeline(self.root, FakeTools(), self.asr).process('file', path, {})
        self.assertEqual(result['source'], 'local_caption')
        self.assertEqual((Path(result['output_dir']) / result['files']['txt']).read_text('utf-8'), 'Original, not rewritten.\n')

    def test_reject_invalid_options(self):
        for options in [{'mode': 'shell'}, {'model': 'evil/path'}, {'language': 'nonsense'}, {'asr_language': 'en;whoami'}]:
            with self.subTest(options=options), self.assertRaises(ValueError):
                validate_options(options)

    def test_html_response_is_not_treated_as_no_captions(self):
        tools = FakeTools({'title': 'Test', 'language': 'en', 'subtitles': {
            'en': [{'ext': 'vtt', 'url': 'https://www.youtube.com/api/timedtext'}]}})
        tools.caption = lambda track: '<html>verification required</html>'
        with self.assertRaises(UserError) as raised:
            Pipeline(self.root, tools, self.asr).process('youtube', 'https://youtu.be/BaW_jenozKc', {})
        self.assertEqual(raised.exception.code, 'caption_parse')
        self.assertEqual(tools.audio_calls, 0)
        self.assertEqual(self.asr_calls, 0)

    def test_asr_timestamps_do_not_exceed_audio_duration(self):
        path = self.root / 'sample.wav'
        path.write_bytes(b'test')
        def overrun(path, options, report):
            return [Cue(0, 4, 'Hello.')], {'duration': 1.25, 'language': 'en'}
        result = Pipeline(self.root, FakeTools(), overrun).process('file', path, {})
        self.assertEqual(result['preview'][0]['end'], 1.25)

    def test_caption_discovery_warning_prevents_asr_fallback(self):
        tools = NativeTools(self.root)
        response = subprocess.CompletedProcess([], 0, '{"title":"x"}', 'WARNING: Skipping subtitles: missing PO token')
        with patch.object(tools, 'command', return_value=['yt-dlp']), patch('studio.service.subprocess.run', return_value=response):
            with self.assertRaises(UserError) as raised:
                tools.metadata('https://youtu.be/BaW_jenozKc')
        self.assertEqual(raised.exception.code, 'caption_discovery')

    def test_explicit_asr_ignores_caption_only_discovery_warnings(self):
        tools = NativeTools(self.root)
        media = self.root / 'sample.wav'
        media.write_bytes(b'test')
        response = subprocess.CompletedProcess([], 0, '{"title":"x"}', 'WARNING: Skipping subtitles: missing PO token')
        with patch.object(tools, 'command', return_value=['yt-dlp']), patch('studio.service.subprocess.run', return_value=response), patch.object(tools, 'audio', return_value=media):
            result = Pipeline(self.root, tools, self.asr).process('youtube', 'https://youtu.be/BaW_jenozKc', {'mode': 'asr'})
        self.assertEqual(result['source'], 'local_asr')
        self.assertEqual(self.asr_calls, 1)


if __name__ == '__main__':
    unittest.main()

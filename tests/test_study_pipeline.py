"""Offline Task B contracts: explicit bilingual study and full cached Word export."""

from concurrent.futures import ThreadPoolExecutor
import copy
import json
import os
from pathlib import Path
import stat
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from studio.bilingual import TranslationError
from studio.service import Pipeline, UserError, validate_options
from studio.subtitles import Cue

try:
    from studio.study_export import export_study_word
except ModuleNotFoundError as error:
    if error.name != 'studio.study_export':
        raise
    export_study_word = None


URL = 'https://www.youtube.com/watch?v=BaW_jenozKc'


class Tools:
    def __init__(self, count=251, chinese=True):
        self.count, self.chinese = count, chinese
        self.calls = []

    def metadata(self, url, **kwargs):
        self.calls.append(('metadata', url, kwargs))
        return {'title': 'Study <original> & title', 'language': 'en', 'duration': self.count * 2,
                'subtitles': {'en': [{'ext': 'json3', 'url': 'https://www.youtube.com/api/timedtext?lang=en'}],
                              **({'zh': [{'ext': 'json3', 'url': 'https://www.youtube.com/api/timedtext?lang=zh'}]}
                                 if self.chinese else {})}}

    def caption(self, track):
        self.calls.append(('caption', track['code']))
        return json.dumps({'events': [{'tStartMs': i * 2000, 'dDurationMs': 1000,
                                     'segs': [{'utf8': ('中文' if track['code'].startswith('zh') else 'English ') + str(i)}]}
                                    for i in range(self.count)]})

    def audio(self, *args):
        raise AssertionError('Unexpected audio extraction')


class Translator:
    def __init__(self):
        self.calls = []

    def translate_many(self, texts, progress=None):
        self.calls.extend(texts)
        return ['译文 ' + text for text in texts]


class Fixture(unittest.TestCase):
    def setUp(self):
        work = Path(__file__).resolve().parents[1] / '.work' / 'tmp'
        work.mkdir(parents=True, exist_ok=True)
        temporary = tempfile.TemporaryDirectory(prefix='study-export-', dir=work)
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.desktop = self.root / 'Desktop'
        self.tools = Tools()
        self.translator = Translator()
        self.writes = []
        self.pipeline = Pipeline(self.root, self.tools, translator=self.translator,
                                 word_writer=self.writer, desktop_dir=self.desktop)

    def writer(self, path, title, url, blocks, chinese_note, english_note):
        self.writes.append((Path(path), title, url, copy.deepcopy(blocks), chinese_note, english_note))
        Path(path).write_bytes(b'offline complete Word fixture')
        return Path(path)

    def study(self, **options):
        self.result = self.pipeline.process('youtube', URL, {'bilingual_study': True, **options})
        self.job = Path(self.result['output_dir'])
        return self.result

    def read(self, name):
        return json.loads((self.job / name).read_text('utf-8'))

    def write(self, name, data):
        (self.job / name).write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')

    def export(self, **kwargs):
        self.assertTrue(callable(export_study_word), 'Task B must provide export_study_word')
        return export_study_word(self.root, self.result['id'], word_writer=self.writer,
                                 desktop_dir=self.desktop, **kwargs)


class StudyPipelineTests(Fixture):
    def test_study_is_an_explicit_strict_boolean_default_false(self):
        self.assertIs(validate_options({}).get('bilingual_study'), False)
        for value in ('true', 'false', 1, 0, None, {}, []):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_options({'bilingual_study': value})

    def test_study_retains_full_bilingual_data_without_word_or_desktop(self):
        result = self.study()
        self.assertEqual(result.get('bilingual_count'), 251)
        self.assertEqual(len(result['bilingual_preview']), 200)
        stored = self.read('bilingual.json')
        self.assertEqual(len(stored['blocks']), 251)
        self.assertEqual(stored['blocks'][-1]['chinese'], '中文250')
        self.assertEqual(stored['chinese_source'], result['chinese_source'])
        self.assertIn('上传的中文字幕', result['chinese_source'])
        self.assertEqual(self.read('metadata.json'), result)
        self.assertEqual(len(self.read('study-cues.json')), 251)
        self.assertEqual(set(result['files']), {'srt', 'vtt', 'txt'})
        self.assertNotIn('desktop_path', result)
        self.assertFalse(self.desktop.exists())
        self.assertFalse(list(self.job.glob('*.docx')))
        self.assertEqual(self.writes, [])
        self.assertEqual(self.translator.calls, [])

    def test_study_translates_missing_chinese_and_labels_provenance(self):
        self.tools.chinese = False
        result = self.study()
        self.assertEqual(len(self.translator.calls), 251)
        self.assertIn('Google', result.get('chinese_source', ''))
        self.assertTrue(all(block['chinese'] for block in self.read('bilingual.json')['blocks']))
        self.assertEqual(self.writes, [])

    def test_study_is_youtube_only(self):
        (self.root / 'user.srt').write_text('1\n00:00:00,000 --> 00:00:01,000\nUser text.\n', encoding='utf-8')
        with self.assertRaises(ValueError):
            self.pipeline.process('file', self.root / 'user.srt', {'bilingual_study': True})

    def test_study_forces_english_track_even_if_other_language_requested(self):
        self.study(language='zh')
        self.assertEqual(self.result['language'], 'en')
        self.assertTrue(self.read('study-cues.json')[0]['text'].startswith('English'))

    def test_study_rejects_partial_english_caption_parsing(self):
        self.tools.caption = lambda track: json.dumps({'events': [
            {'tStartMs': 0, 'dDurationMs': 1000, 'segs': [{'utf8': 'First.'}]},
            {'tStartMs': 1000, 'segs': [{'utf8': 'Lost second.'}]}]})
        with self.assertRaises(UserError) as raised:
            self.study()
        self.assertEqual(raised.exception.code, 'caption_parse')

    def test_study_rejects_non_english_asr(self):
        self.tools.metadata = lambda *a, **k: {'title': 'Other audio', 'language': 'zh'}
        self.tools.audio = lambda *a: self.root / 'user.wav'
        self.pipeline.transcriber = lambda *a: ([Cue(0, 1, '中文')], {'language': 'zh'})
        with self.assertRaises(UserError) as raised:
            self.study()
        self.assertEqual(raised.exception.code, 'english_required')
        self.assertEqual(self.translator.calls, [])

    def test_study_translation_failure_never_publishes_complete_metadata(self):
        self.tools.chinese = False
        self.translator.translate_many = lambda *a: ['部分翻译']
        with self.assertRaises(UserError) as raised:
            self.study()
        self.assertEqual(raised.exception.code, 'translation')
        self.assertEqual(list((self.root / 'results').glob('*/metadata.json')), [])
        self.assertEqual(self.writes, [])
        self.assertFalse(self.desktop.exists())

    def test_study_chinese_failure_falls_back_to_translation(self):
        original = self.tools.caption
        self.tools.caption = lambda track: '<html>failed</html>' if track['code'] == 'zh' else original(track)
        result = self.study()
        self.assertIn('Google', result.get('chinese_source', ''))
        self.assertEqual(len(self.translator.calls), 251)

    def test_explicit_word_flag_keeps_legacy_immediate_word_even_with_study_flag(self):
        result = self.study(bilingual_word=True)
        self.assertEqual(len(self.writes), 1)
        self.assertTrue(Path(result['desktop_path']).is_file())

    def test_study_asr_is_english_and_keeps_model_provenance_on_later_export(self):
        self.tools.metadata = lambda *a, **k: {'title': 'Spoken English', 'language': 'en'}
        self.tools.audio = lambda *a: self.root / 'user.wav'
        self.pipeline.transcriber = lambda *a: ([Cue(0, 1.23456, 'Spoken English.')], {'language': 'en'})
        self.study()
        self.assertEqual(self.writes, [])
        self.assertFalse(self.desktop.exists())
        self.export()
        self.assertIn('Whisper', self.writes[0][5])
        self.assertIn('base', self.writes[0][5])

    def test_false_study_keeps_ordinary_extraction_unchanged(self):
        result = self.pipeline.process('youtube', URL, {'bilingual_study': False})
        self.assertNotIn('bilingual_count', result)
        self.assertFalse((Path(result['output_dir']) / 'bilingual.json').exists())
        self.assertEqual(self.translator.calls, [])
        self.assertEqual(self.writes, [])


class CachedExportTests(Fixture):
    def setUp(self):
        super().setUp()
        self.study()

    def test_export_uses_all_251_stored_blocks_without_any_extraction_or_translation(self):
        calls = copy.deepcopy(self.tools.calls)
        with patch('studio.service.NativeTools', side_effect=AssertionError('No extraction')), \
                patch('studio.bilingual.GoogleWebTranslator', side_effect=AssertionError('No translator')), \
                patch('urllib.request.urlopen', side_effect=AssertionError('No network')):
            result = self.export()
        self.assertEqual(self.tools.calls, calls)
        self.assertEqual(self.translator.calls, [])
        self.assertEqual(len(self.writes), 1)
        self.assertEqual(len(self.writes[0][3]), 251)
        self.assertEqual(self.writes[0][3][-1]['english'], 'English 250')
        self.assertEqual(self.writes[0][3][-1]['chinese'], '中文250')
        self.assertIn('上传的英文字幕', self.writes[0][5])
        self.assertEqual(self.writes[0][4], self.result['chinese_source'])
        self.assertEqual(Path(result['desktop_path']).parent, self.desktop)
        self.assertEqual(Path(result['desktop_path']).read_bytes(), b'offline complete Word fixture')
        self.assertEqual(self.read('metadata.json'), result)
        self.assertEqual(result['bilingual_count'], 251)

    def test_default_writer_is_the_existing_offline_word_module(self):
        self.assertTrue(callable(export_study_word), 'Task B must provide export_study_word')
        with patch('studio.word_document.write_word_document', side_effect=self.writer) as writer:
            export_study_word(self.root, self.result['id'], desktop_dir=self.desktop)
        writer.assert_called_once()

    def test_writer_temporary_files_stay_under_project_work_tmp(self):
        self.export()
        self.assertEqual(self.writes[0][0].parent.parent, self.root / '.work' / 'tmp')
        self.assertFalse(self.writes[0][0].exists())

    def test_existing_immediate_word_job_can_be_exported_from_cache_again(self):
        self.study(bilingual_word=True)
        previous = Path(self.result['desktop_path'])
        old_data = previous.read_bytes()
        self.export()
        self.assertEqual(previous.read_bytes(), old_data)
        self.assertEqual(len(self.writes), 2)

    def test_current_metadata_reads_do_not_use_untrusted_previews(self):
        self.write('metadata.json', dict(self.result, preview=[], bilingual_preview=[]))
        self.export()
        self.assertEqual(len(self.writes[0][3]), 251)

    def test_invalid_xml_chinese_is_rejected_even_with_a_mock_writer(self):
        data = self.read('bilingual.json')
        data['blocks'][-1]['chinese'] = '不能写入\x01'
        self.write('bilingual.json', data)
        with self.assertRaises(UserError):
            self.export()
        self.assertEqual(self.writes, [])

    def test_missing_full_store_does_not_fall_back_to_200_row_preview(self):
        (self.job / 'bilingual.json').unlink(missing_ok=True)
        with self.assertRaises(UserError):
            self.export()
        self.assertEqual(self.writes, [])

    def test_missing_source_cues_fails_instead_of_preview_fallback(self):
        (self.job / 'study-cues.json').unlink()
        with self.assertRaises(UserError):
            self.export()
        self.assertEqual(self.writes, [])

    def test_corrupt_partial_or_mismatched_stored_blocks_fail_before_writing(self):
        self.assertTrue((self.job / 'bilingual.json').exists(), 'Study must retain bilingual.json')
        original = self.read('bilingual.json')
        mutations = [lambda data: data.update(blocks=data['blocks'][:200]),
                     lambda data: data['blocks'][220].update(chinese='  '),
                     lambda data: data['blocks'][220].update(english='altered English'),
                     lambda data: data['blocks'][220].update(start=440.25),
                     lambda data: data['blocks'][220].update(end=float('nan')),
                     lambda data: data['blocks'][220].update(start=True),
                     lambda data: data['blocks'].append(data['blocks'][-1]),
                     lambda data: data['blocks'].reverse(),
                     lambda data: data.update(chinese_source=''),
                     lambda data: data.update(chinese_source='different provenance')]
        for mutate in mutations:
            data = copy.deepcopy(original)
            mutate(data)
            self.write('bilingual.json', data)
            with self.subTest(data=str(mutate)), self.assertRaises(UserError):
                self.export()
        self.assertEqual(self.writes, [])
        self.assertFalse(self.desktop.exists())

    def test_bilingual_groups_must_cover_every_full_source_cue_in_order(self):
        self.assertTrue((self.job / 'bilingual.json').exists(), 'Study must retain bilingual.json')
        data = self.read('bilingual.json')
        blocks = data['blocks']
        data['blocks'] = [dict(start=blocks[0]['start'], end=blocks[1]['end'],
                               english=blocks[0]['english'] + ' ' + blocks[1]['english'], chinese='合并段落')] + blocks[2:]
        self.write('bilingual.json', data)
        self.result.update(bilingual_count=250, bilingual_preview=data['blocks'][:200])
        self.write('metadata.json', self.result)
        self.export()
        self.assertEqual(len(self.writes[0][3]), 250)
        self.assertEqual(self.writes[0][3][0]['english'], 'English 0 English 1')

    def test_english_suffix_can_not_disappear_even_with_plausible_counts(self):
        self.assertTrue((self.job / 'bilingual.json').exists(), 'Study must retain bilingual.json')
        data = self.read('bilingual.json')
        data['blocks'] = data['blocks'][:200]
        self.write('bilingual.json', data)
        self.result['bilingual_count'] = 200
        self.write('metadata.json', self.result)
        with self.assertRaises(UserError):
            self.export()
        self.assertEqual(self.writes, [])

    def test_malformed_metadata_and_source_cues_are_rejected(self):
        original_meta = self.read('metadata.json')
        original_cues = self.read('study-cues.json')
        for changes in ({'count': 200}, {'count': True}, {'bilingual_count': 200},
                        {'language': 'zh'}, {'source': 'translated'}, {'title': ''},
                        {'chinese_source': ''}, {'id': 'b' * 32}, {'url': 'https://evil.test/'},
                        {'source': 'local_asr', 'model': None}):
            self.write('metadata.json', dict(original_meta, **changes))
            with self.subTest(changes=changes), self.assertRaises(UserError):
                self.export()
        self.write('metadata.json', original_meta)
        for cues in (original_cues[:200], [dict(original_cues[0], text='changed')] + original_cues[1:],
                     [dict(original_cues[0], end=10 ** 1000)] + original_cues[1:]):
            self.write('study-cues.json', cues)
            with self.subTest(cues=len(cues)), self.assertRaises(UserError):
                self.export()
        self.assertEqual(self.writes, [])

    def test_invalid_json_duplicate_keys_and_nonfinite_values_are_not_accepted(self):
        originals = {name: (self.job / name).read_bytes() for name in ('metadata.json', 'study-cues.json')}
        for name, raw in [('metadata.json', '{'), ('metadata.json', '[]'),
                          ('metadata.json', '{"id":"x","id":"y"}'),
                          ('study-cues.json', '[NaN]'), ('study-cues.json', '[]')]:
            (self.job / name).write_text(raw, encoding='utf-8')
            with self.subTest(name=name, raw=raw), self.assertRaises(UserError):
                self.export()
            (self.job / name).write_bytes(originals[name])

    def test_non_string_source_is_invalid_data_not_an_internal_type_error(self):
        for source in ([], {}):
            self.write('metadata.json', dict(self.result, source=source))
            with self.subTest(source=source):
                try:
                    self.export()
                except Exception as error:
                    self.assertIsInstance(error, UserError)
                    self.assertEqual(error.code, 'study_data')
                else:
                    self.fail('Malformed provenance must fail before writing')

    def test_truncating_both_stores_and_counts_cannot_omit_retained_source_suffix(self):
        self.assertTrue((self.job / 'bilingual.json').exists())
        stored = self.read('bilingual.json')
        stored['blocks'] = stored['blocks'][:200]
        self.write('bilingual.json', stored)
        self.write('study-cues.json', self.read('study-cues.json')[:200])
        self.write('metadata.json', dict(self.result, count=200, bilingual_count=200))
        with self.assertRaises(UserError):
            self.export()
        self.assertEqual(self.writes, [])

    def test_untrusted_absolute_output_metadata_is_never_a_write_destination(self):
        user_file = self.root / 'user.docx'
        user_file.write_bytes(b'never touch user data')
        self.write('metadata.json', dict(self.result, output_dir=str(self.root), desktop_path=str(user_file)))
        result = self.export()
        self.assertEqual(Path(result['output_dir']), self.job)
        self.assertEqual(user_file.read_bytes(), b'never touch user data')
        self.assertEqual(Path(result['desktop_path']).parent, self.desktop)

    def test_lock_collision_never_deletes_existing_user_file(self):
        lock = self.job / '.study-word.lock'
        lock.write_bytes(b'existing user file or active lock')
        with self.assertRaises(UserError) as raised:
            self.export()
        self.assertEqual(raised.exception.code, 'busy')
        self.assertEqual(lock.read_bytes(), b'existing user file or active lock')

    def test_failed_export_releases_own_lock_for_explicit_retry(self):
        with patch('studio.word_document.save_to_desktop', side_effect=OSError('denied')):
            with self.assertRaises(UserError):
                self.export()
        self.assertFalse((self.job / '.study-word.lock').exists())
        self.export()
        self.assertTrue(Path(self.read('metadata.json')['desktop_path']).exists())

    def test_untrusted_metadata_paths_are_rejected_without_touching_user_file(self):
        user_file = self.root / 'user.docx'
        user_file.write_bytes(b'keep user data')
        original = self.read('metadata.json')
        for key, value in [('srt', '../user.docx'), ('docx', str(user_file)),
                           ('txt', 'CON.txt'), ('docx', 'name.docx:stream'), ('vtt', 'trailing.vtt.')]:
            changed = copy.deepcopy(original)
            changed['files'][key] = value
            self.write('metadata.json', changed)
            with self.subTest(value=value), self.assertRaises(UserError):
                self.export()
        self.assertEqual(user_file.read_bytes(), b'keep user data')
        self.assertEqual(self.writes, [])

    def test_invalid_job_ids_fail_without_side_effects(self):
        self.assertTrue(callable(export_study_word), 'Task B must provide export_study_word')
        for value in ('../escape', 'A' * 32, '', 'a' * 31, None, self.job):
            with self.subTest(value=value), self.assertRaises(ValueError):
                export_study_word(self.root, value, word_writer=self.writer, desktop_dir=self.desktop)
        self.assertEqual(self.writes, [])

    def test_repeated_export_never_overwrites_retained_or_desktop_user_files(self):
        # Use the same safe filename function as the existing Word workflow.
        from studio.subtitles import safe_filename
        name = safe_filename(self.result['title']) + ' 中英对照.docx'
        retained = self.job / name
        retained.write_bytes(b'user retained file')
        self.desktop.mkdir()
        desktop_file = self.desktop / name
        desktop_file.write_bytes(b'user Desktop file')
        first = self.export()
        second = self.export()
        self.assertEqual(retained.read_bytes(), b'user retained file')
        self.assertEqual(desktop_file.read_bytes(), b'user Desktop file')
        self.assertNotEqual(first['desktop_path'], second['desktop_path'])
        self.assertEqual(Path(first['desktop_path']).read_bytes(), b'offline complete Word fixture')
        self.assertEqual(Path(second['desktop_path']).read_bytes(), b'offline complete Word fixture')

    def test_writer_failure_preserves_metadata_user_files_and_desktop(self):
        before = (self.job / 'metadata.json').read_bytes()
        def broken(path, *args):
            path.write_bytes(b'partial')
            raise RuntimeError('writer failure')
        self.assertTrue(callable(export_study_word), 'Task B must provide export_study_word')
        with self.assertRaises(UserError) as raised:
            export_study_word(self.root, self.result['id'], word_writer=broken, desktop_dir=self.desktop)
        self.assertEqual(raised.exception.code, 'word')
        self.assertEqual((self.job / 'metadata.json').read_bytes(), before)
        self.assertFalse(self.desktop.exists())
        self.assertFalse(list(self.job.glob('*.docx')))

    def test_desktop_failure_leaves_local_word_but_metadata_unchanged(self):
        before = (self.job / 'metadata.json').read_bytes()
        with patch('studio.word_document.save_to_desktop', side_effect=OSError('denied')):
            with self.assertRaises(UserError) as raised:
                self.export()
        self.assertEqual(raised.exception.code, 'desktop_save')
        self.assertEqual((self.job / 'metadata.json').read_bytes(), before)
        self.assertEqual(len(list(self.job.glob('*.docx'))), 1)

    def test_metadata_publication_is_atomic_and_failure_keeps_old_metadata_and_copies(self):
        self.assertTrue(callable(export_study_word), 'Task B must provide export_study_word')
        before = (self.job / 'metadata.json').read_bytes()
        real_replace = os.replace
        def replace(source, target):
            if Path(target) == self.job / 'metadata.json':
                self.assertEqual((self.job / 'metadata.json').read_bytes(), before)
                self.assertIn('desktop_path', json.loads(Path(source).read_text('utf-8')))
                raise OSError('metadata publication denied')
            return real_replace(source, target)
        with patch('os.replace', side_effect=replace):
            with self.assertRaises(UserError):
                self.export()
        self.assertEqual((self.job / 'metadata.json').read_bytes(), before)
        self.assertEqual(len(list(self.desktop.glob('*.docx'))), 1)

    def test_concurrent_same_job_exports_are_serialized_or_rejected(self):
        self.assertTrue(callable(export_study_word), 'Task B must provide export_study_word')
        started, release = threading.Event(), threading.Event()
        def blocked(path, *args):
            started.set()
            if not release.wait(5):
                raise RuntimeError('test timeout')
            return self.writer(path, *args)
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(export_study_word, self.root, self.result['id'],
                                word_writer=blocked, desktop_dir=self.desktop)
            try:
                self.assertTrue(started.wait(3))
                second = pool.submit(export_study_word, self.root, self.result['id'],
                                     word_writer=self.writer, desktop_dir=self.desktop)
            finally:
                release.set()
            first.result(timeout=5)
            try:
                second.result(timeout=5)
            except UserError as error:
                self.assertEqual(error.code, 'busy')
        self.assertIn('docx', self.read('metadata.json')['files'])
        self.assertTrue(all(path.read_bytes() == b'offline complete Word fixture'
                            for path in self.desktop.glob('*.docx')))

    def test_reparse_or_symlink_components_are_rejected(self):
        self.assertTrue(callable(export_study_word), 'Task B must provide export_study_word')
        original = Path.lstat
        for target in (self.root, self.root / 'results', self.job, self.job / 'metadata.json',
                       self.job / 'study-cues.json', self.job / 'bilingual.json',
                       self.job / self.result['files']['srt']):
            for mode, attributes in ((stat.S_IFLNK | 0o777, 0), (stat.S_IFREG | 0o600, 0x400)):
                def fake_lstat(path, *args, **kwargs):
                    if path == target:
                        return SimpleNamespace(st_mode=mode, st_file_attributes=attributes)
                    return original(path, *args, **kwargs)
                with self.subTest(target=target, mode=mode), patch.object(Path, 'lstat', new=fake_lstat):
                    with self.assertRaises(UserError) as raised:
                        self.export()
                    self.assertEqual(raised.exception.code, 'study_path')
        self.assertEqual(self.writes, [])

    def test_destination_candidate_links_are_rejected_without_removal(self):
        from studio.subtitles import safe_filename
        target = self.job / (safe_filename(self.result['title']) + ' 中英对照.docx')
        original = Path.lstat
        def linked(path, *args, **kwargs):
            if path == target:
                return SimpleNamespace(st_mode=stat.S_IFLNK | 0o777, st_file_attributes=0x400)
            return original(path, *args, **kwargs)
        with patch.object(Path, 'lstat', new=linked):
            with self.assertRaises(UserError) as raised:
                self.export()
        self.assertEqual(raised.exception.code, 'study_path')
        self.assertFalse(self.desktop.exists())


if __name__ == '__main__':
    unittest.main()

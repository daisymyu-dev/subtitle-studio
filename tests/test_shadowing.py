"""Offline contracts for retained study data and the explicit original-audio cache."""

import json
from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import stat
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import wave

from studio.bilingual import align_captions
from studio.service import UserError
from studio.subtitles import Cue, render_subtitles

try:
    from studio.shadowing import ShadowingStore
except ModuleNotFoundError as error:
    if error.name != 'studio.shadowing':
        raise
    ShadowingStore = None


def make_wav(path):
    with wave.open(str(path), 'wb') as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(16000)
        stream.writeframes(b'\0\0' * 1600)
    return path


class LocalTools:
    def __init__(self):
        self.calls = []
        self.started = threading.Event()
        self.release = threading.Event()
        self.failures = 0
        self.output = lambda folder: make_wav(folder / 'original.wav')
        self.active = 0
        self.max_active = 0
        self.lock = threading.Lock()

    def study_audio(self, url, temp_dir):
        with self.lock:
            self.calls.append((url, temp_dir))
            self.active += 1
            self.max_active = max(self.max_active, self.active)
        try:
            self.started.set()
            if not self.release.wait(3):
                raise RuntimeError('Offline test gate timed out')
            if self.failures:
                self.failures -= 1
                (temp_dir / 'partial.part').write_bytes(b'incomplete')
                raise UserError('network', f'network secret=do-not-expose {temp_dir}')
            return self.output(temp_dir)
        finally:
            with self.lock:
                self.active -= 1


class ShadowingFixture(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(ShadowingStore, 'Task 1 must provide studio.shadowing.ShadowingStore')
        work = Path(__file__).resolve().parents[1] / '.work' / 'tmp'
        work.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix='shadowing-test-', dir=work)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.job_id = 'a' * 32
        self.job = self.root / 'results' / self.job_id
        self.job.mkdir(parents=True)
        self.cues = [{'start': i * 2, 'end': i * 2 + 1.5, 'text': f'Sentence {i}.'}
                     for i in range(245)]
        self.metadata = {'id': self.job_id, 'title': 'Original title',
                         'url': 'https://www.youtube.com/watch?v=BaW_jenozKc',
                         'source': 'uploaded_caption', 'count': len(self.cues),
                         'files': {'srt': 'Original title.srt'}, 'preview': self.cues[:200]}
        self.write_json('metadata.json', self.metadata)
        self.write_json('study-cues.json', self.cues)
        (self.job / self.metadata['files']['srt']).write_text(
            render_subtitles([Cue(**cue) for cue in self.cues], 'srt'), encoding='utf-8')
        self.store = ShadowingStore(self.root, tools=object())
        self.addCleanup(self.store.close)

    def write_json(self, name, value):
        (self.job / name).write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')

    def link(self, source, target, directory=False):
        try:
            os.symlink(source, target, target_is_directory=directory)
            return
        except OSError:
            pass
        # This Windows account cannot create symlinks/junctions. Exercise the
        # exact lstat reparse/symlink check without requiring elevated rights.
        original = Path.lstat

        def linked_lstat(path, *args, **kwargs):
            if path == target:
                return SimpleNamespace(st_mode=stat.S_IFLNK | 0o777, st_file_attributes=0x400)
            return original(path, *args, **kwargs)

        mock = patch.object(Path, 'lstat', new=linked_lstat)
        mock.start()
        self.addCleanup(mock.stop)


class StudyTests(ShadowingFixture):
    def test_full_json_cues_keep_more_than_preview_and_original_words(self):
        self.cues[0]['text'] = '  Original <name> & words.\nSecond line.  '
        self.write_json('study-cues.json', self.cues)
        study = self.store.load_study(self.job_id)
        self.assertEqual(set(study), {'id', 'title', 'url', 'cues', 'chinese_note'})
        self.assertEqual(study['id'], self.job_id)
        self.assertEqual(study['title'], self.metadata['title'])
        self.assertEqual(study['url'], self.metadata['url'])
        self.assertEqual(len(study['cues']), 245)
        self.assertEqual(study['cues'][0], {'start': 0, 'end': 1.5,
                                          'english': self.cues[0]['text'], 'chinese': ''})
        self.assertEqual(study['cues'][-1]['english'], 'Sentence 244.')

    def test_legacy_srt_keeps_the_full_result(self):
        (self.job / 'study-cues.json').unlink()
        study = self.store.load_study(self.job_id)
        self.assertEqual(len(study['cues']), 245)
        self.assertEqual(study['cues'][-1]['english'], 'Sentence 244.')

    def test_chinese_uses_maximum_overlap_not_english_equality(self):
        self.write_json('bilingual.json', {'chinese_source': '机器翻译，需复核', 'blocks': [
            {'start': 0, 'end': 0.25, 'english': 'Different grouping', 'chinese': '短段落'},
            {'start': 0.25, 'end': 4, 'english': 'Two sentences together', 'chinese': '较大重叠段落'},
            {'start': 20, 'end': 22, 'english': 'Another paragraph', 'chinese': '另一段'}]})
        study = self.store.load_study(self.job_id)
        self.assertEqual(study['cues'][0]['chinese'], '较大重叠段落')
        self.assertEqual(study['cues'][1]['chinese'], '较大重叠段落')
        self.assertEqual(study['cues'][2]['chinese'], '')
        self.assertIn('段落参考', study['chinese_note'])
        self.assertIn('不是逐句', study['chinese_note'])
        self.assertIn('机器翻译', study['chinese_note'])

    def test_nested_english_cue_uses_its_source_bilingual_group(self):
        english = [Cue(0, 30, 'First paragraph.'),
                   Cue(29, 32, 'Second paragraph.'),
                   Cue(29.2, 29.8, 'Nested cue.')]
        blocks = align_captions(english, [])
        self.assertEqual([block['english'] for block in blocks],
                         ['First paragraph.', 'Second paragraph. Nested cue.'])
        for block, chinese in zip(blocks, ['第一段', '第二段']):
            block['chinese'] = chinese
        self.write_json('bilingual.json', {'chinese_source': '机器翻译，需复核', 'blocks': blocks})
        self.write_json('study-cues.json', [vars(cue) for cue in english])
        self.write_json('metadata.json', dict(self.metadata, count=len(english)))

        study = self.store.load_study(self.job_id)

        self.assertEqual([cue['chinese'] for cue in study['cues']],
                         ['第一段', '第二段', '第二段'])
        self.assertIn('来源分组', study['chinese_note'])

    def test_source_bilingual_groups_handle_unsorted_repeated_english(self):
        english = [Cue(29.2, 29.8, '  Same words.\nSecond line.  '),
                   Cue(29, 32, '  Same words.\nSecond line.  '),
                   Cue(0, 30, '  Same words.\nSecond line.  ')]
        blocks = align_captions(english, [])
        self.assertEqual(len(blocks), 2)
        for block, chinese in zip(blocks, ['第一段', '第二段']):
            block['chinese'] = chinese
        self.write_json('bilingual.json', {'blocks': blocks})
        self.write_json('metadata.json', dict(self.metadata, count=len(english)))
        for legacy_srt in (False, True):
            with self.subTest(legacy_srt=legacy_srt):
                self.write_json('study-cues.json', [vars(cue) for cue in english])
                if legacy_srt:
                    (self.job / 'study-cues.json').unlink()
                    (self.job / self.metadata['files']['srt']).write_text(
                        render_subtitles(english, 'srt'), encoding='utf-8')

                study = self.store.load_study(self.job_id)

                self.assertEqual([cue['chinese'] for cue in study['cues']],
                                 ['第二段', '第二段', '第一段'])
                self.assertEqual([cue['english'] for cue in study['cues']],
                                 [cue.text for cue in english])

    def test_source_bilingual_group_with_empty_chinese_does_not_borrow_another(self):
        english = [Cue(0, 30, 'First paragraph.'),
                   Cue(29, 32, 'Second paragraph.'),
                   Cue(29.2, 29.8, 'Nested cue.')]
        blocks = align_captions(english, [])
        blocks[0]['chinese'] = '第一段'
        self.write_json('bilingual.json', {'blocks': blocks})
        self.write_json('study-cues.json', [vars(cue) for cue in english])
        self.write_json('metadata.json', dict(self.metadata, count=len(english)))

        study = self.store.load_study(self.job_id)

        self.assertEqual([cue['chinese'] for cue in study['cues']], ['第一段', '', ''])

    def test_corrupt_json_never_falls_back_to_srt_or_preview(self):
        for raw in ('{', '{}', '[]', '[null]', '[{"start":0,"end":1}]'):
            with self.subTest(raw=raw):
                (self.job / 'study-cues.json').write_text(raw, encoding='utf-8')
                with self.assertRaises(UserError):
                    self.store.load_study(self.job_id)

    def test_all_malformed_json_cues_are_rejected_not_dropped(self):
        for changes in ({'start': -1}, {'start': True}, {'end': float('nan')},
                        {'end': float('inf')}, {'end': 0}, {'start': '0'},
                        {'text': ''}, {'text': ' \n '}, {'text': None}):
            with self.subTest(changes=changes):
                self.write_json('study-cues.json', [dict(self.cues[0], **changes)] + self.cues[1:])
                with self.assertRaises(UserError):
                    self.store.load_study(self.job_id)

    def test_truncated_complete_cue_list_is_rejected(self):
        self.write_json('study-cues.json', self.cues[:200])
        with self.assertRaises(UserError):
            self.store.load_study(self.job_id)

    def test_unrepresentable_integer_timestamps_are_reported_as_invalid_data(self):
        self.write_json('study-cues.json', [dict(self.cues[0], end=10 ** 1000)] + self.cues[1:])
        with self.assertRaises(UserError):
            self.store.load_study(self.job_id)

    def test_unrepresentable_legacy_srt_clock_is_reported_as_invalid_data(self):
        (self.job / 'study-cues.json').unlink()
        huge = '9' * 1000
        (self.job / self.metadata['files']['srt']).write_text(
            f'1\n{huge}:00:00,000 --> {huge}:00:01,000\nOriginal words.\n', encoding='utf-8')
        with self.assertRaises(UserError):
            self.store.load_study(self.job_id)

    def test_duplicate_json_fields_are_rejected(self):
        (self.job / 'study-cues.json').write_text(
            '[{"start":0,"start":1,"end":2,"text":"Do not silently replace a field"}]',
            encoding='utf-8')
        with self.assertRaises(UserError):
            self.store.load_study(self.job_id)

    def test_strict_srt_rejects_invalid_blocks_instead_of_skipping_them(self):
        (self.job / 'study-cues.json').unlink()
        good = '1\n00:00:00,000 --> 00:00:01,000\nOriginal words.\n\n'
        for bad in ('unparsed words', 'NOTE silently ignored',
                    '2\n00:99:00,000 --> 00:99:01,000\nBad clock.',
                    '2\n00:00:02,000 --> 00:00:01,000\nBackwards.',
                    '2\n00:00:02,000 --> 00:00:03,000\n',
                    '2\n00:00:02,000 --> 00:00:03,000 garbage\nBad timing.'):
            with self.subTest(bad=bad):
                (self.job / self.metadata['files']['srt']).write_text(good + bad, encoding='utf-8')
                with self.assertRaises(UserError):
                    self.store.load_study(self.job_id)

    def test_corrupt_metadata_and_bilingual_are_rejected(self):
        for name, raw in (('metadata.json', '{}'), ('metadata.json', '{'),
                          ('bilingual.json', '{}'), ('bilingual.json', '{'),
                          ('bilingual.json', '{"blocks":[{"start":0,"end":1,"chinese":null}]}')):
            with self.subTest(name=name, raw=raw):
                self.write_json('metadata.json', self.metadata)
                (self.job / name).write_text(raw, encoding='utf-8')
                with self.assertRaises(UserError):
                    self.store.load_study(self.job_id)

    def test_invalid_job_ids_and_filename_traversal_are_rejected(self):
        for job_id in ('../' + self.job_id, 'A' * 32, '', None, 'a' * 31, 'a' * 33):
            with self.subTest(job_id=job_id):
                with self.assertRaises((ValueError, UserError)):
                    self.store.load_study(job_id)
        for name in ('../outside.srt', '..\\outside.srt', 'C:\\outside.srt',
                     '/outside.srt', 'stream:caption.srt', 'NUL.srt', 'bad.srt '):
            with self.subTest(name=name):
                self.metadata['files']['srt'] = name
                self.write_json('metadata.json', self.metadata)
                with self.assertRaises(UserError):
                    self.store.load_study(self.job_id)

    def test_non_youtube_source_url_is_rejected_without_tools(self):
        for url in ('file:///secret.wav', 'https://example.com/a',
                    'https://user:password@www.youtube.com/watch?v=BaW_jenozKc'):
            with self.subTest(url=url):
                self.metadata['url'] = url
                self.write_json('metadata.json', self.metadata)
                with self.assertRaises(UserError):
                    self.store.load_study(self.job_id)

    def test_local_caption_study_is_readable_without_a_download_url(self):
        self.metadata['url'] = None
        self.write_json('metadata.json', self.metadata)
        self.assertIsNone(self.store.load_study(self.job_id)['url'])


class AudioTests(ShadowingFixture):
    def setUp(self):
        super().setUp()
        self.assertTrue(callable(getattr(self.store, 'prepare', None)), 'Explicit prepare() is required')
        self.store.close()
        self.tools = LocalTools()
        self.store = ShadowingStore(self.root, self.tools)
        self.addCleanup(self.store.close)
        self.addCleanup(self.tools.release.set)

    def wait_for(self, status, job_id=None):
        job_id = job_id or self.job_id
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            snapshot = self.store.snapshot(job_id)
            if snapshot['status'] == status:
                return snapshot
            time.sleep(0.01)
        self.fail(f'Did not reach {status}: {self.store.snapshot(job_id)}')

    def prepare_ready(self):
        self.tools.release.set()
        self.store.prepare(self.job_id)
        return self.wait_for('ready')

    def add_job(self, number):
        job_id = f'{number:032x}'
        job = self.root / 'results' / job_id
        job.mkdir()
        metadata = dict(self.metadata, id=job_id)
        (job / 'metadata.json').write_text(json.dumps(metadata), encoding='utf-8')
        (job / 'study-cues.json').write_text(json.dumps(self.cues), encoding='utf-8')
        return job_id

    def test_read_methods_stay_idle_without_downloading(self):
        self.assertFalse(self.store.busy)
        self.assertEqual(self.store.snapshot(self.job_id)['status'], 'idle')
        self.assertIsNone(self.store.media_file(self.job_id))
        self.store.load_study(self.job_id)
        self.assertEqual(self.tools.calls, [])

    def test_default_tools_are_native_without_any_call(self):
        from studio.service import NativeTools
        default = ShadowingStore(self.root)
        self.addCleanup(default.close)
        self.assertIsInstance(default.tools, NativeTools)
        self.assertEqual(default.snapshot(self.job_id)['status'], 'idle')

    def test_prepare_duplicate_calls_use_one_download_and_public_snapshots(self):
        first = self.store.prepare(self.job_id)
        self.assertIn(first['status'], ('queued', 'downloading'))
        self.assertTrue(self.tools.started.wait(2))
        self.assertTrue(self.store.busy)
        self.assertEqual(self.store.snapshot(self.job_id)['status'], 'downloading')
        with ThreadPoolExecutor(max_workers=6) as pool:
            snapshots = list(pool.map(lambda _: self.store.prepare(self.job_id), range(12)))
        self.assertTrue(all(item['status'] in ('queued', 'downloading') for item in snapshots))
        self.assertEqual(len(self.tools.calls), 1)
        self.assertIsNone(self.store.media_file(self.job_id))
        self.tools.release.set()
        ready = self.wait_for('ready')
        self.assertFalse(self.store.busy)
        self.assertEqual(ready['id'], self.job_id)
        self.assertIsInstance(ready['message'], str)
        self.assertNotIn(str(self.root), json.dumps(ready))
        self.assertNotIn('file', ready)
        path = self.store.media_file(self.job_id)
        self.assertIsInstance(path, Path)
        self.assertEqual(path.parent, self.job)
        self.assertEqual(self.tools.calls[0][0], self.metadata['url'])
        self.assertTrue(self.tools.calls[0][1].is_relative_to(self.root / '.work'))
        self.assertFalse(self.tools.calls[0][1].exists())
        ready['status'] = 'mutated'
        self.assertEqual(self.store.snapshot(self.job_id)['status'], 'ready')
        self.assertEqual(self.store.prepare(self.job_id)['status'], 'ready')
        self.assertEqual(len(self.tools.calls), 1)

    def test_cache_survives_store_restart_without_a_download(self):
        self.prepare_ready()
        path = self.store.media_file(self.job_id)
        self.store.close()
        restarted = ShadowingStore(self.root, tools=object())
        self.addCleanup(restarted.close)
        self.assertEqual(restarted.snapshot(self.job_id)['status'], 'ready')
        self.assertEqual(restarted.media_file(self.job_id), path)
        self.assertEqual(restarted.prepare(self.job_id)['status'], 'ready')
        manifest = json.loads((self.job / 'shadowing-audio.json').read_text('utf-8'))
        self.assertEqual(manifest['file'], path.name)
        self.assertFalse(Path(manifest['file']).is_absolute())

    def test_network_failure_is_safe_cleans_partials_and_allows_explicit_retry(self):
        sentinel = self.job / 'user-file.txt'
        sentinel.write_text('keep me', encoding='utf-8')
        self.tools.failures = 1
        self.tools.release.set()
        self.store.prepare(self.job_id)
        failed = self.wait_for('error')
        self.assertNotIn('do-not-expose', json.dumps(failed))
        self.assertNotIn(str(self.root), json.dumps(failed))
        self.assertIn('网络', failed['message'])
        self.assertIsNone(self.store.media_file(self.job_id))
        self.assertFalse(self.store.busy)
        self.assertEqual(list((self.root / '.work').iterdir()), [])
        self.assertEqual(self.store.snapshot(self.job_id)['status'], 'error')
        self.assertEqual(len(self.tools.calls), 1)
        self.store.prepare(self.job_id)
        self.wait_for('ready')
        self.assertEqual(len(self.tools.calls), 2)
        self.assertEqual(sentinel.read_text('utf-8'), 'keep me')

    def test_invalid_audio_and_extension_disguises_are_not_marked_ready(self):
        def bad(folder, name, data):
            path = folder / name
            path.write_bytes(data)
            return path
        for output in (lambda folder: bad(folder, 'audio.wav', b'not audio'),
                       lambda folder: bad(folder, 'audio.wav', b''),
                       lambda folder: make_wav(folder / 'audio.txt'),
                       lambda folder: make_wav(folder / 'audio.m4a'),
                       lambda folder: folder):
            with self.subTest(output=output):
                self.tools.output = output
                self.tools.release.set()
                self.store.prepare(self.job_id)
                self.wait_for('error')
                self.assertIsNone(self.store.media_file(self.job_id))
                self.assertFalse((self.job / 'shadowing-audio.json').exists())
                self.assertEqual(list((self.root / '.work').iterdir()), [])

    def test_audio_limit_is_500_mib_and_is_enforced_before_decode(self):
        import studio.shadowing as shadowing
        self.assertEqual(shadowing.MAX_AUDIO_BYTES, 500 * 1024 * 1024)
        with patch.object(shadowing, 'MAX_AUDIO_BYTES', 100):
            self.tools.release.set()
            self.store.prepare(self.job_id)
            failed = self.wait_for('error')
            self.assertIn('500 MiB', failed['message'])
            self.assertIsNone(self.store.media_file(self.job_id))
        with patch.object(shadowing, 'MAX_AUDIO_BYTES', 3244):
            self.store.prepare(self.job_id)
            self.wait_for('ready')

    def test_download_must_be_inside_its_temporary_directory(self):
        outside = make_wav(self.root / 'user-original.wav')
        self.tools.output = lambda folder: outside
        self.tools.release.set()
        self.store.prepare(self.job_id)
        self.wait_for('error')
        self.assertIsNone(self.store.media_file(self.job_id))
        self.assertTrue(outside.exists())

    def test_exclusive_cache_filename_collision_does_not_delete_user_file(self):
        collision = self.job / ('shadowing-audio-' + 'f' * 32 + '.wav')
        collision.write_bytes(b'user data must survive even a generated-name collision')
        with patch('studio.shadowing.uuid.uuid4', return_value=SimpleNamespace(hex='f' * 32)):
            self.tools.release.set()
            self.store.prepare(self.job_id)
            self.wait_for('error')
        self.assertTrue(collision.exists(), 'Failed exclusive creation must not delete an existing file')
        self.assertEqual(collision.read_bytes(), b'user data must survive even a generated-name collision')

    def test_required_m4a_webm_and_optional_audio_formats_decode_locally(self):
        import av

        def encoded(folder, suffix, format_name, codec):
            path = folder / ('original' + suffix)
            with av.open(str(path), mode='w', format=format_name) as output:
                stream = output.add_stream(codec, rate=48000)
                stream.layout = 'mono'
                frame = av.AudioFrame(format='s16', layout='mono', samples=960)
                frame.sample_rate = 48000
                frame.pts = 0
                for plane in frame.planes:
                    plane.update(bytes(plane.buffer_size))
                for packet in stream.encode(frame):
                    output.mux(packet)
                for packet in stream.encode(None):
                    output.mux(packet)
            return path

        self.tools.release.set()
        for index, (suffix, container, codec) in enumerate((('.m4a', 'ipod', 'aac'),
                ('.webm', 'webm', 'libopus'), ('.mp3', 'mp3', 'libmp3lame'),
                ('.ogg', 'ogg', 'libopus'), ('.opus', 'ogg', 'libopus'))):
            with self.subTest(suffix=suffix):
                job_id = self.add_job(10 + index)
                self.tools.output = lambda folder: encoded(folder, suffix, container, codec)
                self.store.prepare(job_id)
                self.wait_for('ready', job_id)
                self.assertEqual(self.store.media_file(job_id).suffix, suffix)

    def test_webm_video_without_audio_is_rejected(self):
        import av

        def video(folder):
            path = folder / 'not-audio.webm'
            with av.open(str(path), mode='w', format='webm') as output:
                stream = output.add_stream('libvpx', rate=24)
                stream.width = stream.height = 16
                stream.pix_fmt = 'yuv420p'
                frame = av.VideoFrame(16, 16, 'yuv420p')
                for plane in frame.planes:
                    plane.update(bytes(plane.buffer_size))
                for packet in stream.encode(frame):
                    output.mux(packet)
                for packet in stream.encode(None):
                    output.mux(packet)
            return path

        self.tools.output = video
        self.tools.release.set()
        self.store.prepare(self.job_id)
        self.wait_for('error')
        self.assertIsNone(self.store.media_file(self.job_id))

    def test_download_symlink_is_rejected_and_external_source_is_not_deleted(self):
        outside = make_wav(self.root / 'user-original.wav')

        def linked(folder):
            target = folder / 'original.wav'
            self.link(outside, target)
            return target

        self.tools.output = linked
        self.tools.release.set()
        self.store.prepare(self.job_id)
        self.wait_for('error')
        self.assertTrue(outside.exists())
        self.assertIsNone(self.store.media_file(self.job_id))

    def test_work_junction_is_rejected_before_calling_download_tools(self):
        outside = self.root / 'outside-work'
        outside.mkdir()
        self.link(outside, self.root / '.work', directory=True)
        self.tools.release.set()
        self.store.prepare(self.job_id)
        self.wait_for('error')
        self.assertEqual(self.tools.calls, [])

    def test_manifest_link_is_not_read_or_overwritten(self):
        outside = self.root / 'user-manifest.json'
        outside.write_text('keep me', encoding='utf-8')
        self.link(outside, self.job / 'shadowing-audio.json')
        self.assertEqual(self.store.snapshot(self.job_id)['status'], 'error')
        self.tools.release.set()
        self.store.prepare(self.job_id)
        self.wait_for('error')
        self.assertEqual(outside.read_text('utf-8'), 'keep me')
        self.assertEqual(self.tools.calls, [])

    def test_cached_audio_link_is_rejected_on_read(self):
        self.prepare_ready()
        media = self.store.media_file(self.job_id)
        outside = self.root / 'user-original.wav'
        media.replace(outside)
        self.link(outside, media)
        self.assertEqual(self.store.snapshot(self.job_id)['status'], 'error')
        self.assertIsNone(self.store.media_file(self.job_id))
        self.assertTrue(outside.exists())

    def test_bad_manifest_and_missing_or_tampered_cache_do_not_trigger_download(self):
        self.prepare_ready()
        manifest_path = self.job / 'shadowing-audio.json'
        original = json.loads(manifest_path.read_text('utf-8'))
        for change in ({'file': '../user.wav'}, {'file': 'C:\\outside.wav'},
                       {'size': 1}, {'version': 999}, {'id': 'b' * 32},
                       {'url': 'https://example.com/not-the-source'}):
            with self.subTest(change=change):
                self.write_json('shadowing-audio.json', dict(original, **change))
                self.assertEqual(self.store.snapshot(self.job_id)['status'], 'error')
                self.assertIsNone(self.store.media_file(self.job_id))
        self.write_json('shadowing-audio.json', original)
        media = self.store.media_file(self.job_id)
        media.write_bytes(b'x' * media.stat().st_size)
        self.assertEqual(self.store.snapshot(self.job_id)['status'], 'error')
        self.assertIsNone(self.store.media_file(self.job_id))
        self.assertEqual(len(self.tools.calls), 1)
        self.store.prepare(self.job_id)
        self.wait_for('ready')
        self.assertEqual(len(self.tools.calls), 2)

    def test_failed_explicit_cache_repair_reports_the_network_error(self):
        self.prepare_ready()
        self.store.media_file(self.job_id).write_bytes(b'damaged')
        self.tools.failures = 1
        self.store.prepare(self.job_id)
        failed = self.wait_for('error')
        self.assertIn('网络', failed['message'])
        self.assertNotIn(str(self.root), json.dumps(failed))

    def test_single_worker_and_four_waiting_jobs_with_retry_when_queue_full(self):
        self.store.prepare(self.job_id)
        self.assertTrue(self.tools.started.wait(2))
        queued = [self.add_job(number) for number in range(1, 5)]
        for job_id in queued:
            self.assertEqual(self.store.prepare(job_id)['status'], 'queued')
        self.assertEqual(self.store.prepare(queued[0])['status'], 'queued')
        rejected = self.add_job(5)
        self.assertEqual(self.store.prepare(rejected)['status'], 'error')
        self.assertEqual(len(self.tools.calls), 1)
        self.tools.release.set()
        for job_id in [self.job_id] + queued:
            self.wait_for('ready', job_id)
        self.assertEqual(self.tools.max_active, 1)
        self.store.prepare(rejected)
        self.wait_for('ready', rejected)
        self.assertEqual(len(self.tools.calls), 6)

    def test_close_is_idempotent_and_no_new_preparation_can_start(self):
        self.store.close()
        self.store.close()
        self.assertEqual(self.store.prepare(self.job_id)['status'], 'error')
        self.assertFalse(self.store.busy)
        self.assertEqual(self.tools.calls, [])

    def test_close_cancels_waiting_jobs_and_joins_the_active_worker(self):
        self.store.prepare(self.job_id)
        self.assertTrue(self.tools.started.wait(2))
        queued = self.add_job(7)
        self.store.prepare(queued)
        closer = threading.Thread(target=self.store.close, daemon=True)
        closer.start()
        self.wait_for('error', queued)
        self.tools.release.set()
        closer.join(3)
        self.assertFalse(closer.is_alive())
        self.assertFalse(self.store.busy)
        self.assertEqual(len(self.tools.calls), 1)
        self.assertEqual(self.store.snapshot(self.job_id)['status'], 'ready')

    def test_no_source_url_fails_preparation_without_tools(self):
        self.metadata['url'] = None
        self.write_json('metadata.json', self.metadata)
        self.assertEqual(self.store.prepare(self.job_id)['status'], 'error')
        self.assertFalse(self.store.busy)
        self.assertEqual(self.tools.calls, [])


class LinkTests(ShadowingFixture):
    def test_cue_symlink_is_rejected_even_when_target_is_inside_root(self):
        source = self.root / 'real-cues.json'
        (self.job / 'study-cues.json').replace(source)
        self.link(source, self.job / 'study-cues.json')
        with self.assertRaises(UserError):
            self.store.load_study(self.job_id)

    def test_result_directory_symlink_is_rejected(self):
        self.link(self.root / 'other-job', self.job, directory=True)
        with self.assertRaises(UserError):
            self.store.load_study(self.job_id)

    def test_legacy_srt_symlink_is_rejected(self):
        (self.job / 'study-cues.json').unlink()
        name = self.metadata['files']['srt']
        target = self.root / name
        (self.job / name).replace(target)
        self.link(target, self.job / name)
        with self.assertRaises(UserError):
            self.store.load_study(self.job_id)

    def test_results_parent_junction_is_rejected(self):
        results = self.root / 'results'
        self.link(self.root / 'other-results', results, directory=True)
        with self.assertRaises(UserError):
            self.store.load_study(self.job_id)

    def test_replaced_store_root_is_rejected(self):
        self.link(self.root.parent / 'other-root', self.root, directory=True)
        with self.assertRaises(UserError):
            self.store.load_study(self.job_id)


if __name__ == '__main__':
    unittest.main()

import hashlib
import importlib.util
import io
import re
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from urllib.error import URLError


class PunctuationContractTests(unittest.TestCase):
    def test_local_punctuation_module_exists(self):
        self.assertIsNotNone(importlib.util.find_spec('studio.punctuation'),
                             'The approved local punctuation module is missing')


class FakeBackend:
    """Subword IDs/offsets and labels, without any model or network dependency."""

    def __init__(self, labels=None, *, width=3, force_window_stop=False):
        self.labels = labels or {}
        self.width = width
        self.force_window_stop = force_window_stop
        self.seen = set()

    def encode(self, text):
        self.text = text
        self.ids, offsets, self.predictions = [], [], {}
        for word in re.finditer(r'\S+', text):
            for start in range(word.start(), word.end(), self.width):
                end = min(start + self.width, word.end())
                token_id = len(self.ids) + 4
                self.ids.append(token_id)
                offsets.append((start, end))
                self.predictions[token_id] = (self.labels.get(word.group(), 0)
                                              if end == word.end() else 0)
        return self.ids, offsets

    def predict(self, ids):
        self.seen.update(ids)
        result = [self.predictions[i] for i in ids]
        if self.force_window_stop:
            result[-1] = 2
        return result


class PunctuationTests(unittest.TestCase):
    def setUp(self):
        from studio import punctuation
        self.module = punctuation
        work = Path(__file__).resolve().parents[1] / '.work'
        work.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix='punctuation-', dir=work)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def marks(self, text, backend, report=None):
        with patch.object(self.module, '_load_backend', return_value=backend):
            return self.module.punctuation_marks(text, root=self.root, report=report)

    def test_subword_labels_map_to_original_character_offsets_and_case(self):
        text = '  Hello\tUNBELIEVABLE\nworld  '
        backend = FakeBackend({'hello': 3, 'unbelievable': 2, 'world': 4})
        result = self.marks(text, backend)
        self.assertEqual(result, [(7, ','), (20, '.'), (26, '?')])
        restored = text
        for offset, mark in reversed(result):
            restored = restored[:offset] + mark + restored[offset:]
        self.assertEqual(restored, '  Hello,\tUNBELIEVABLE.\nworld?  ')
        self.assertEqual(backend.text, 'hello unbelievable world')

    def test_unicode_offsets_are_python_characters_not_utf8_bytes(self):
        text = '\U0001f642 CAFÉ\u00a0İstanbul'
        self.assertEqual(self.marks(text, FakeBackend({'café': 3, 'i\u0307stanbul': 2})),
                         [(6, ','), (15, '.')])

    def test_combining_marks_remain_part_of_the_original_word(self):
        text = '“CAFE\u0301” hello'
        self.assertEqual(self.marks(text, FakeBackend({'cafe\u0301': 3, 'hello': 2})),
                         [(6, ','), (len(text), '.')])

    def test_existing_punctuation_wins_even_across_quotes_and_whitespace(self):
        text = 'Hello, world! Really? Wait; “yes.” Next\n, final'
        backend = FakeBackend({word: 2 for word in
                               ('hello', 'world', 'really', 'wait', 'yes', 'next', 'final')})
        self.assertEqual(self.marks(text, backend), [(len(text), '.')])

    def test_existing_unicode_terminal_punctuation_is_not_duplicated(self):
        text = 'hello‼ world． yes： okay؟ final'
        backend = FakeBackend({word: 2 for word in ('hello', 'world', 'yes', 'okay', 'final')})
        self.assertEqual(self.marks(text, backend), [(len(text), '.')])

    def test_missing_punctuation_can_be_inserted_before_closing_quote(self):
        text = '“hello” world'
        self.assertEqual(self.marks(text, FakeBackend({'hello': 3, 'world': 2})),
                         [(6, ','), (len(text), '.')])

    def test_does_not_insert_inside_decimals_contractions_or_abbreviations(self):
        text = "Dr Smith paid 3.14 in the U.S. and can't re-enter snake_case"
        backend = FakeBackend(width=1)
        original_predict = backend.predict

        def every_piece_has_a_stop(ids):
            original_predict(ids)
            return [2] * len(ids)

        backend.predict = every_piece_has_a_stop
        marks = self.marks(text, backend)
        permitted = {match.end() for match in re.finditer(r'Smith|paid|3\.14|in|the|and|can.t|re-enter|snake_case', text)}
        self.assertTrue(marks)
        self.assertTrue(all(offset in permitted for offset, _ in marks), marks)
        self.assertNotIn((2, '.'), marks)

    def test_acronym_label_is_not_a_license_to_rewrite_words(self):
        self.assertEqual(self.marks('NATO US', FakeBackend({'nato': 1, 'us': 1})), [])

    def test_common_words_are_not_mistaken_for_abbreviations(self):
        self.assertEqual(self.marks('no I am', FakeBackend({'no': 3, 'am': 2})),
                         [(2, ','), (7, '.')])

    def test_internal_apostrophes_are_retained_in_the_inference_copy(self):
        text = '“CAN’T” it\'s we\'ll'
        backend = FakeBackend({"can't": 3, "we'll": 2})
        self.assertEqual(self.marks(text, backend), [(6, ','), (len(text), '.')])
        self.assertEqual(backend.text, "can't it's we'll")

    def test_empty_or_punctuation_only_text_needs_no_model(self):
        with patch.object(self.module, '_load_backend', side_effect=AssertionError('loaded')):
            for text in ('', ' \n\t', '... “”—!?'):
                self.assertEqual(self.module.punctuation_marks(text, root=self.root), [])

    def test_long_windows_cover_every_subword_without_artificial_seam_stops(self):
        text = ' '.join('w' + str(i) for i in range(40))
        backend = FakeBackend({'w12': 2}, width=50, force_window_stop=True)
        with patch.object(self.module, '_WINDOW_TOKENS', 8), \
                patch.object(self.module, '_OVERLAP_TOKENS', 3):
            marks = self.marks(text, backend)
        self.assertEqual(marks, [(text.index('w12') + 3, '.'), (len(text), '.')])
        self.assertEqual(backend.seen, set(backend.ids))

    def test_word_longer_than_window_is_not_split_by_a_punctuation_insertion(self):
        text = 'a' * 45 + ' done'
        backend = FakeBackend({'a' * 45: 3, 'done': 2}, width=1, force_window_stop=True)
        with patch.object(self.module, '_WINDOW_TOKENS', 8), \
                patch.object(self.module, '_OVERLAP_TOKENS', 3):
            self.assertEqual(self.marks(text, backend), [(45, ','), (len(text), '.')])

    def test_probabilistic_progress_has_no_transcript(self):
        events = []
        self.marks('private transcript', FakeBackend({'transcript': 2}),
                   lambda *args, **kwargs: events.append((args, kwargs)))
        self.assertTrue(events)
        self.assertIn('概率', str(events))
        for notice in ('212 MB', '.models', '不上传', '字幕', '音频'):
            self.assertIn(notice, str(events))
        self.assertNotIn('private transcript', str(events))
        self.assertTrue(all(event[0][0] == 'punctuation' for event in events))

    def test_missing_model_is_an_explicit_error_not_fake_success(self):
        with patch.object(self.module, '_load_backend',
                          side_effect=self.module.PunctuationError('model unavailable')):
            with self.assertRaisesRegex(self.module.PunctuationError, 'unavailable'):
                self.module.punctuation_marks('hello world', root=self.root)

    def test_inference_failure_does_not_expose_text_or_return_partial_marks(self):
        backend = FakeBackend()
        backend.predict = lambda ids: (_ for _ in ()).throw(RuntimeError('private transcript'))
        with self.assertRaises(self.module.PunctuationError) as raised:
            self.marks('private transcript', backend)
        self.assertNotIn('private transcript', str(raised.exception))
        self.assertIn('本地', str(raised.exception))

    def test_invalid_prediction_lengths_types_and_labels_fail_closed(self):
        for predictions in ([], [5], [2.1], [True]):
            with self.subTest(predictions=predictions):
                backend = FakeBackend(width=50)
                backend.predict = lambda ids: predictions
                with self.assertRaises(self.module.PunctuationError):
                    self.marks('hello', backend)

    def test_invalid_offsets_or_special_ids_fail_closed(self):
        for encoded in (([4], [(0, 99)]), ([4, 5], [(0, 5)]),
                        ([1], [(0, 5)]), ([4], [(5, 0)]), ([4], [(0, 4)])):
            with self.subTest(encoded=encoded):
                backend = FakeBackend()
                backend.encode = lambda text: encoded
                backend.predict = lambda ids: [0] * len(ids)
                with self.assertRaises(self.module.PunctuationError):
                    self.marks('hello', backend)


class ModelAssetTests(unittest.TestCase):
    def setUp(self):
        from studio import punctuation
        self.module = punctuation
        work = Path(__file__).resolve().parents[1] / '.work'
        work.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix='punctuation-', dir=work)
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.payload = b'fake-model'
        self.asset = replace(punctuation._ASSETS[0], size=len(self.payload),
                             sha256=hashlib.sha256(self.payload).hexdigest())

    def test_manifest_pins_two_public_files_and_revisions(self):
        self.assertEqual(len(self.module._ASSETS), 2)
        for asset in self.module._ASSETS:
            self.assertRegex(asset.revision, r'^[0-9a-f]{40}$')
            self.assertRegex(asset.sha256, r'^[0-9a-f]{64}$')
            self.assertLess(asset.size, 220_000_000)
            self.assertEqual(asset.url, 'https://huggingface.co/' + asset.repo
                             + '/resolve/' + asset.revision + '/' + asset.filename)

    def test_valid_cached_asset_works_offline(self):
        target = self.directory / self.asset.filename
        target.write_bytes(self.payload)
        with patch.object(self.module, '_download', side_effect=AssertionError('network')):
            self.assertEqual(self.module._ensure_asset(self.directory, self.asset), target)

    def test_corrupt_cached_asset_fails_without_loading_it(self):
        target = self.directory / self.asset.filename
        target.write_bytes(b'x' * len(self.payload))
        with self.assertRaises(self.module.PunctuationError):
            self.module._ensure_asset(self.directory, self.asset)

    def test_download_is_fixed_get_without_credentials_or_source_text(self):
        calls = []

        def open_request(request, timeout):
            calls.append(request)
            self.assertGreater(timeout, 0)
            self.assertLessEqual(timeout, 60)
            return io.BytesIO(self.payload)

        with patch.object(self.module, '_open_download', side_effect=open_request):
            target = self.module._ensure_asset(self.directory, self.asset)
        self.assertEqual(target.read_bytes(), self.payload)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0].full_url, self.asset.url)
        self.assertIsNone(calls[0].data)
        self.assertEqual(calls[0].get_method(), 'GET')
        headers = {key.lower(): value for key, value in calls[0].header_items()}
        self.assertNotIn('authorization', headers)
        self.assertNotIn('cookie', headers)
        self.assertFalse(list(self.directory.glob('*.part')))

    def test_failed_truncated_oversized_or_wrong_digest_download_leaves_no_model(self):
        responses = [io.BytesIO(b'bad'), io.BytesIO(self.payload + b'x'),
                     io.BytesIO(b'x' * len(self.payload)), URLError('offline')]
        for response in responses:
            with self.subTest(response=response):
                kwargs = ({'side_effect': response} if isinstance(response, Exception)
                          else {'return_value': response})
                with patch.object(self.module, '_open_download', **kwargs):
                    with self.assertRaises(self.module.PunctuationError):
                        self.module._ensure_asset(self.directory, self.asset)
                self.assertFalse((self.directory / self.asset.filename).exists())
                self.assertFalse(list(self.directory.glob('*.part')))

    def test_redirects_cannot_send_requests_to_arbitrary_hosts_or_plain_http(self):
        handler = self.module._ModelRedirects()
        from urllib.request import Request
        for url in ('https://evil.example/model', 'http://huggingface.co/model',
                    'https://user:password@huggingface.co/model',
                    'https://huggingface.co:444/model'):
            with self.subTest(url=url), self.assertRaises(self.module.PunctuationError):
                handler.redirect_request(Request(self.asset.url), None, 302, 'Found', {}, url)

    def test_download_time_budget_is_bounded_and_partial_file_is_removed(self):
        with patch.object(self.module, '_open_download', return_value=io.BytesIO(self.payload)), \
                patch.object(self.module.time, 'monotonic', side_effect=[0, 301]):
            with self.assertRaisesRegex(self.module.PunctuationError, '超时'):
                self.module._ensure_asset(self.directory, self.asset)
        self.assertFalse(list(self.directory.iterdir()))

    def test_missing_dependency_fails_before_any_download(self):
        import builtins
        original_import = builtins.__import__

        def missing_runtime(name, *args, **kwargs):
            if name == 'onnxruntime':
                raise ModuleNotFoundError(name)
            return original_import(name, *args, **kwargs)

        with patch('builtins.__import__', side_effect=missing_runtime), \
                patch.object(self.module, '_download', side_effect=AssertionError('network')):
            with self.assertRaisesRegex(self.module.PunctuationError, 'ONNXRuntime'):
                self.module._load_backend(self.directory)


class OnnxAdapterTests(unittest.TestCase):
    def test_punctuation_and_boundary_heads_use_bos_eos_and_int64_input(self):
        import numpy as np
        from studio.punctuation import _OnnxBackend
        calls = []

        class Session:
            def run(self, outputs, inputs):
                calls.append((outputs, inputs))
                return [np.array([[4, 3, 2, 4]], dtype=np.int64),
                        np.array([[True, False, True, True]], dtype=np.bool_)]

        tokenizer = SimpleNamespace(encode=lambda text, **kwargs:
                                    SimpleNamespace(ids=[4, 5], offsets=[(0, 2), (2, 5)]))
        backend = _OnnxBackend(tokenizer, Session())
        self.assertEqual(backend.encode('hello'), ([4, 5], [(0, 2), (2, 5)]))
        self.assertEqual(backend.predict([4, 5]), [3, 2])
        self.assertEqual(calls[0][0], ['post_preds', 'seg_preds'])
        np.testing.assert_array_equal(calls[0][1]['input_ids'], [[1, 4, 5, 2]])
        self.assertEqual(calls[0][1]['input_ids'].dtype, np.int64)

    def test_positive_boundary_supplies_period_only_for_null_or_comma(self):
        import numpy as np
        from studio.punctuation import _OnnxBackend
        post = np.array([[0, 0, 3, 4, 1, 2, 0]], dtype=np.int64)
        seg = np.array([[False, True, True, True, True, True, False]], dtype=np.bool_)
        backend = _OnnxBackend(None, SimpleNamespace(run=lambda *args: [post, seg]))
        self.assertEqual(backend.predict([4, 5, 6, 7, 8]), [2, 2, 4, 1, 2])

    def test_negative_boundary_does_not_invent_splits_for_comma_run_on(self):
        import numpy as np
        from studio.punctuation import _OnnxBackend
        post = np.array([[0, 3, 0, 4, 0]], dtype=np.int64)
        seg = np.array([[False, False, False, True, False]], dtype=np.bool_)
        backend = _OnnxBackend(None, SimpleNamespace(run=lambda *args: [post, seg]))
        self.assertEqual(backend.predict([4, 5, 6]), [3, 0, 4])

    def test_bad_onnx_shape_or_dtype_is_not_accepted_as_labels(self):
        import numpy as np
        from studio.punctuation import PunctuationError, _OnnxBackend
        for output in (np.zeros((1, 3, 5)), np.zeros((1, 2), dtype=np.int64),
                       np.zeros((1, 3), dtype=np.float32)):
            with self.subTest(shape=output.shape):
                backend = _OnnxBackend(None, SimpleNamespace(
                    run=lambda *args: [output, np.zeros((1, 3), dtype=np.bool_)]))
                with self.assertRaises(PunctuationError):
                    backend.predict([4])

    def test_bad_boundary_shape_type_or_missing_head_fails_closed(self):
        import numpy as np
        from studio.punctuation import PunctuationError, _OnnxBackend
        post = np.zeros((1, 3), dtype=np.int64)
        for output in (np.zeros((1, 2), dtype=np.bool_), np.zeros((1, 3, 1), dtype=np.bool_),
                       np.zeros((1, 3), dtype=np.float32), np.zeros((1, 3), dtype=np.int64), None):
            outputs = [post] if output is None else [post, output]
            with self.subTest(output=output):
                backend = _OnnxBackend(None, SimpleNamespace(run=lambda *args: outputs))
                with self.assertRaises(PunctuationError):
                    backend.predict([4])


if __name__ == '__main__':
    unittest.main()

import contextlib
import importlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]


class RuntimeTests(unittest.TestCase):
    def runtime(self):
        self.assertIsNotNone(importlib.util.find_spec('studio.runtime'),
                             'Runtime path separation has not been implemented')
        return importlib.import_module('studio.runtime')

    def test_source_assets_and_default_data_are_checkout_not_cwd(self):
        runtime = self.runtime()
        with patch.object(sys, 'frozen', False, create=True), patch.dict(os.environ, {}, clear=True):
            self.assertEqual(runtime.asset_root(), ROOT)
            self.assertEqual(runtime.data_root(), ROOT)

    def test_frozen_assets_use_meipass_and_data_use_localappdata(self):
        runtime = self.runtime()
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            with patch.object(sys, 'frozen', True, create=True), \
                    patch.object(sys, '_MEIPASS', str(base / 'installed' / '_internal'), create=True), \
                    patch.object(sys, 'executable', str(base / 'installed' / 'SubtitleStudio.exe')), \
                    patch.dict(os.environ, {'LOCALAPPDATA': str(base / 'user')}, clear=True):
                self.assertEqual(runtime.asset_root(), base / 'installed' / '_internal')
                self.assertEqual(runtime.data_root(), base / 'user' / 'SubtitleStudio')

    def test_explicit_override_beats_environment_and_resolves_relative_path(self):
        runtime = self.runtime()
        with tempfile.TemporaryDirectory() as directory, \
                patch.dict(os.environ, {'SUBTITLE_STUDIO_DATA_DIR': directory}):
            self.assertEqual(runtime.data_root('.work/smoke'), (Path.cwd() / '.work/smoke').resolve())
            self.assertEqual(runtime.data_root(), Path(directory).resolve())

    def test_unsafe_data_override_is_rejected(self):
        runtime = self.runtime()
        with tempfile.TemporaryDirectory() as directory:
            installed = Path(directory) / 'installed'
            with patch.object(sys, 'frozen', True, create=True), \
                    patch.object(sys, '_MEIPASS', str(installed / '_internal'), create=True), \
                    patch.object(sys, 'executable', str(installed / 'SubtitleStudio.exe')):
                for value in ('', '   ', str(Path(directory).anchor), str(installed), str(installed / 'data')):
                    with self.subTest(value=value), self.assertRaises(ValueError):
                        runtime.data_root(value)

    def test_prepare_runtime_keeps_temp_and_model_caches_inside_data_root(self):
        runtime = self.runtime()
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {}, clear=True):
            root = Path(directory) / 'data'
            runtime.prepare_data(root)
            for variable in ('TEMP', 'TMP', 'HF_HOME', 'HF_HUB_CACHE', 'XDG_CACHE_HOME'):
                self.assertTrue(Path(os.environ[variable]).resolve().is_relative_to(root))
            self.assertEqual(Path(tempfile.gettempdir()), root / '.work' / 'tmp')
            tempfile.tempdir = None


class NativeRuntimeTests(unittest.TestCase):
    def test_frozen_command_uses_internal_entry_and_only_bundled_node(self):
        from studio.service import NativeTools
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            node = root / 'runtime' / 'node.exe'
            node.parent.mkdir()
            node.touch()
            with patch.object(sys, 'frozen', True, create=True), \
                    patch.object(sys, '_MEIPASS', str(root), create=True), \
                    patch('studio.service.shutil.which', side_effect=AssertionError('No user PATH in frozen mode')):
                command = NativeTools(root / 'data').command()
            self.assertEqual(command[:2], [sys.executable, '--internal-ytdlp'])
            self.assertIn('node:' + str(node), command)
            self.assertIn('--ignore-config', command)
            self.assertIn('--no-cache-dir', command)

    def test_frozen_without_node_does_not_probe_user_path(self):
        from studio.service import NativeTools
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(sys, 'frozen', True, create=True), \
                patch.object(sys, '_MEIPASS', directory, create=True), \
                patch('studio.service.shutil.which', side_effect=AssertionError('No user PATH in frozen mode')):
            command = NativeTools(directory).command()
            self.assertNotIn('--js-runtimes', command)
            self.assertIn('--no-js-runtimes', command)

    def test_source_command_still_uses_python_module(self):
        from studio.service import NativeTools
        with patch.object(sys, 'frozen', False, create=True), \
                patch('studio.service.importlib.util.find_spec', return_value=object()):
            self.assertEqual(NativeTools(ROOT).command()[:3], [sys.executable, '-m', 'yt_dlp'])


class EntryPointTests(unittest.TestCase):
    def test_runtime_check_exercises_docx_and_available_asr_without_model_downloads(self):
        result = subprocess.run([sys.executable, str(ROOT / 'app.py'), '--check-runtime'],
                                capture_output=True, text=True, timeout=40)
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report['version'], '0.1.0-beta.1')
        self.assertTrue(report['docx'])
        self.assertIn('core_ready', report, 'Core dependency readiness is missing')
        self.assertTrue(report['core_ready'])
        self.assertTrue(report['punctuation']['onnxruntime'])
        self.assertTrue(report['punctuation']['tokenizers'])
        self.assertTrue(report['punctuation']['huggingface_hub'])
        self.assertIn('yt_dlp', report)
        if importlib.util.find_spec('faster_whisper'):
            self.assertEqual(report['asr']['decoded_samples'], 16000)

    def test_help_and_version_do_not_start_server_or_make_data(self):
        for argument, expected in (('--help', '--data-dir'), ('--version', '0.1.0-beta.1')):
            with self.subTest(argument=argument), tempfile.TemporaryDirectory() as directory:
                data = Path(directory) / 'must-not-exist'
                result = subprocess.run([sys.executable, str(ROOT / 'app.py'), argument],
                                        capture_output=True, text=True, timeout=15,
                                        env=dict(os.environ, SUBTITLE_STUDIO_DATA_DIR=str(data)))
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn(expected, result.stdout)
                self.assertFalse(data.exists())

    def test_internal_ytdlp_dispatch_happens_without_app_startup(self):
        import app
        with patch('yt_dlp.main', return_value=0) as run, \
                patch.dict(sys.modules, {'studio.server': None}), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(app.main(['--internal-ytdlp', '--version']), 0)
        run.assert_called_once_with(['--version'])


if __name__ == '__main__':
    unittest.main()

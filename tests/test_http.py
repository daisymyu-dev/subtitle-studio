import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
import sys
import types
from email.message import Message
from unittest.mock import Mock, patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from studio.server import Handler, make_server
from studio.service import Pipeline, UserError

PROJECT = Path(__file__).resolve().parents[1]


class HTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.sentence_jobs = Mock()
        self.sentence_jobs.active.return_value = False
        self.sentence_class = Mock(return_value=self.sentence_jobs)
        module = types.ModuleType('studio.sentence_study')
        module.SentencePreparation = self.sentence_class
        self.sentence_module_patch = patch.dict(sys.modules, {'studio.sentence_study': module})
        self.sentence_module_patch.start()
        self.addCleanup(self.sentence_module_patch.stop)
        self.server = make_server(self.root, 0, web_root=PROJECT / 'web')
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f'http://127.0.0.1:{self.server.server_port}'

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.temp.cleanup()

    def request(self, path, data=None, headers=None, authorized=True):
        base_headers = {'X-App-Token': self.server.token} if authorized else {}
        base_headers.update(headers or {})
        if isinstance(data, dict):
            data = json.dumps(data).encode()
            base_headers['Content-Type'] = 'application/json'
        return urlopen(Request(self.base + path, data=data, headers=base_headers), timeout=5)

    def test_page_and_security_headers(self):
        with self.request('/', authorized=False) as response:
            body = response.read().decode()
            self.assertIn(self.server.token, body)
            self.assertIn("frame-ancestors 'none'", response.headers['Content-Security-Policy'])
            self.assertEqual(response.headers['X-Content-Type-Options'], 'nosniff')

    def test_learning_profile_history_and_dictionary_use_existing_security_boundary(self):
        with self.assertRaises(HTTPError) as rejected:self.request('/api/learning',authorized=False)
        self.assertEqual(rejected.exception.code,403)
        with self.request('/api/learning/term',{'key':'bifurcated','term':'bifurcated','state':'known'}) as response:
            self.assertEqual(json.load(response)['known'],['bifurcated'])
        with self.request('/api/learning') as response:self.assertEqual(json.load(response)['known'],['bifurcated'])
        job='a'*32;folder=self.root/'results'/job;folder.mkdir(parents=True)
        (folder/'metadata.json').write_text(json.dumps({'id':job,'title':'Self-authored sample','count':2}))
        with self.request('/api/learning/progress',{'job_id':job,'time':4.5}) as response:self.assertTrue(json.load(response)['ok'])
        with self.request('/api/library') as response:self.assertEqual(json.load(response)['items'][0]['position'],4.5)
        expected={'word':'example','phonetic':'','definitions':[],'source_url':'https://dictionaryapi.dev/','license':{}}
        with patch.object(self.server.dictionary,'lookup',return_value=expected) as lookup:
            with self.request('/api/dictionary',{'word':'example'}) as response:self.assertEqual(json.load(response)['word'],'example')
            lookup.assert_called_once_with('example')
        with self.assertRaises(HTTPError) as rejected:self.request('/api/dictionary',{'word':'example','url':'http://private.test'})
        self.assertEqual(rejected.exception.code,400)

    def test_pronunciation_assets_are_local_allowlisted_audio_only(self):
        with self.request('/learning-pronunciations.js', authorized=False) as response:
            self.assertIn('javascript',response.headers['Content-Type'])
            self.assertIn('otherworldly',response.read().decode('utf-8'))
        with self.request('/pronunciations/otherworldly.wav', authorized=False) as response:
            self.assertEqual(response.headers['Content-Type'],'audio/wav')
            data=response.read();self.assertEqual(data[:4],b'RIFF');self.assertEqual(data[8:12],b'WAVE')
        for path in ('/pronunciations/not-allowed.wav','/pronunciations/../metadata.json','/pronunciations/%2e%2e/studio.log'):
            with self.subTest(path=path),self.assertRaises(HTTPError) as raised:
                self.request(path,authorized=False)
            self.assertEqual(raised.exception.code,404)

    def test_core_rejects_original_audio_before_queueing_or_downloading(self):
        with patch('importlib.util.find_spec', return_value=None), \
                patch.object(self.server.shadowing, 'prepare') as prepare:
            with self.request('/health', authorized=False) as response:
                self.assertFalse(json.load(response)['capabilities']['original_audio'])
            with self.assertRaises(HTTPError) as rejected:
                self.request('/api/jobs/' + 'a' * 32 + '/audio', {})
            self.assertEqual(rejected.exception.code, 409)
            body = json.load(rejected.exception)
            self.assertEqual(body['code'], 'dependency')
            self.assertIn('Core', body['error'])
            prepare.assert_not_called()

    def test_three_designs_are_whitelisted_and_keep_the_same_form(self):
        for design in ('studio', 'signal', 'chrome'):
            with self.subTest(design=design), self.request('/?design=' + design, authorized=False) as response:
                body = response.read().decode()
                self.assertIn(f'data-design="{design}"', body)
                self.assertIn('id="task-form"', body)
                self.assertIn('id="start"', body)
                self.assertIn(self.server.token, body)

    def test_comparison_page_and_design_assets(self):
        with self.request('/designs', authorized=False) as response:
            body = response.read().decode()
            for design in ('studio', 'signal', 'chrome'):
                self.assertIn('/?design=' + design, body)
        for asset in ('/themes.css', '/designs.css', '/vendor/open-props-easing.css'):
            with self.subTest(asset=asset), self.request(asset, authorized=False) as response:
                self.assertIn('text/css', response.headers['Content-Type'])
        with self.assertRaises(HTTPError) as raised:
            self.request('/vendor/../../studio/server.py', authorized=False)
        self.assertEqual(raised.exception.code, 404)

    def test_unknown_design_cannot_inject_html(self):
        with self.request('/?design=%22%3E%3Cscript%3Ealert(1)%3C/script%3E', authorized=False) as response:
            body = response.read().decode()
            self.assertIn('data-design="studio"', body)
            self.assertNotIn('<script>alert(1)', body)

    def test_unauthorized_api_rejected(self):
        with self.assertRaises(HTTPError) as raised:
            self.request('/api/jobs', {}, authorized=False)
        self.assertEqual(raised.exception.code, 403)

    def test_word_job_endpoint_is_explicit_and_does_not_accept_paths(self):
        with patch.object(self.server.jobs, 'submit', return_value='c' * 32) as submit:
            with self.request('/api/word-jobs', {'url': 'https://youtu.be/BaW_jenozKc', 'model': 'base'}) as response:
                self.assertEqual(json.load(response)['id'], 'c' * 32)
            args = submit.call_args.args
            self.assertEqual(args[0], 'youtube')
            self.assertTrue(args[2]['bilingual_word'])
            self.assertIs(args[2]['sentence_study'], True)
            self.assertEqual(args[2]['language'], 'en')
            for bad in ({'url': 'https://youtu.be/BaW_jenozKc', 'desktop_path': 'C:/elsewhere'},
                        {'url': 'http://127.0.0.1'}, {'url': 'https://youtu.be/BaW_jenozKc', 'model': 'evil'}):
                with self.assertRaises(HTTPError) as raised:
                    self.request('/api/word-jobs', bad)
                self.assertEqual(raised.exception.code, 400)

    def test_word_endpoint_requires_session_token(self):
        with self.assertRaises(HTTPError) as raised:
            self.request('/api/word-jobs', {'url': 'https://youtu.be/BaW_jenozKc'}, authorized=False)
        self.assertEqual(raised.exception.code, 403)

    def test_study_job_does_not_request_automatic_word_export(self):
        with patch.object(self.server.jobs,'submit',return_value='a'*32) as submit:
            with self.request('/api/study-jobs',{'url':'https://youtu.be/BaW_jenozKc','model':'base'}) as response:
                self.assertEqual(json.load(response)['id'],'a'*32)
            options=submit.call_args.args[2]
            self.assertTrue(options['bilingual_study']);self.assertFalse(options['bilingual_word'])
            self.assertIs(options['sentence_study'], True)

    def test_root_isolates_player_scripts_to_separate_origin(self):
        with self.request('/',authorized=False) as response:
            html=response.read().decode();policy=response.headers['Content-Security-Policy']
            self.assertIn(self.server.video_bridge.origin,html)
            self.assertIn('frame-src '+self.server.video_bridge.origin,policy)
            self.assertIn("script-src 'self';",policy)

    def test_completed_memory_snapshot_reconciles_sentence_upgrade_and_old_download(self):
        job_id='8'*32;directory=self.root/'results'/job_id;directory.mkdir(parents=True)
        old={'id':job_id,'title':'Old','files':{'docx':'old.docx'}}
        self.server.jobs.jobs[job_id]={'id':job_id,'status':'done','result':old}
        (directory/'old.docx').write_bytes(b'old paragraph')
        upgraded={'id':job_id,'title':'Sentence study','files':{},'sentence_version':1,'sentence_count':2}
        (directory/'metadata.json').write_text(json.dumps(upgraded),'utf-8')
        with self.request(f'/api/jobs/{job_id}') as response:
            self.assertEqual(json.load(response)['result'].get('sentence_version'),1)
        self.assertEqual(self.server.jobs.jobs[job_id]['result'], upgraded)
        # Download must also reconcile when no preceding status refresh occurred.
        self.server.jobs.jobs[job_id]['result'] = old
        with self.assertRaises(HTTPError) as raised:self.request(f'/api/jobs/{job_id}/files/docx')
        self.assertEqual(raised.exception.code,404)

    def test_reconciliation_ignores_invalid_metadata_and_running_jobs(self):
        job_id = '9' * 32
        directory = self.root / 'results' / job_id
        directory.mkdir(parents=True)
        old = {'id': job_id, 'files': {}}
        self.server.jobs.jobs[job_id] = {'id': job_id, 'status': 'done', 'result': old}
        for metadata in ({'id': '0' * 32, 'files': {}, 'sentence_version': 1},
                         {'id': job_id, 'files': [], 'sentence_version': 1},
                         {'id': job_id, 'files': {}, 'sentence_version': True},
                         {'id': job_id, 'files': {}, 'sentence_version': 2}):
            (directory / 'metadata.json').write_text(json.dumps(metadata), 'utf-8')
            with self.request(f'/api/jobs/{job_id}') as response:
                self.assertEqual(json.load(response)['result'], old)
        self.server.jobs.jobs[job_id]['status'] = 'running'
        (directory / 'metadata.json').write_text(json.dumps({'id': job_id, 'files': {}, 'sentence_version': 1}), 'utf-8')
        with self.request(f'/api/jobs/{job_id}') as response:
            self.assertEqual(json.load(response)['status'], 'running')

    def test_cached_word_endpoint_requires_auth_empty_body_and_updates_memory(self):
        job_id='d'*32
        result={'id':job_id,'title':'Cached study','files':{'docx':'study.docx'}}
        self.server.jobs.jobs[job_id]={'id':job_id,'status':'done','result':{'id':job_id,'files':{}}}
        with patch('studio.study_export.export_study_word',return_value=result) as export:
            with self.assertRaises(HTTPError) as raised:
                self.request(f'/api/jobs/{job_id}/word',{},authorized=False)
            self.assertEqual(raised.exception.code,403);export.assert_not_called()
            with self.assertRaises(HTTPError) as raised:
                self.request(f'/api/jobs/{job_id}/word',{'url':'https://youtu.be/BaW_jenozKc'})
            self.assertEqual(raised.exception.code,400);export.assert_not_called()
            with self.request(f'/api/jobs/{job_id}/word',{}) as response:
                self.assertEqual(json.load(response),result)
            export.assert_called_once_with(self.root,job_id)
            self.assertEqual(self.server.jobs.jobs[job_id]['result'],result)

    def test_docx_download_is_whitelisted_with_word_mime(self):
        job_id = 'e' * 32
        directory = self.root / 'results' / job_id
        directory.mkdir(parents=True)
        (directory / 'test.docx').write_bytes(b'docx fixture')
        self.server.jobs.jobs[job_id] = {'id': job_id, 'status': 'done',
            'result': {'files': {'docx': 'test.docx'}}}
        with self.request('/api/jobs/' + job_id + '/files/docx') as response:
            self.assertIn('wordprocessingml.document', response.headers['Content-Type'])
            self.assertEqual(response.read(), b'docx fixture')
        with self.assertRaises(HTTPError) as raised:
            self.request('/api/jobs/' + job_id + '/files/txt')
        self.assertEqual(raised.exception.code, 404)

    def test_cached_word_export_blocks_shutdown_until_finished(self):
        entered, release = threading.Event(), threading.Event()
        outcomes = []
        def export(root, job_id):
            entered.set()
            if not release.wait(5):
                raise TimeoutError()
            return {'id': job_id, 'files': {'docx': 'study.docx'}}
        def request_export():
            try:
                with self.request('/api/jobs/' + 'd' * 32 + '/word', {}) as response:
                    outcomes.append(response.status)
            except Exception as error:
                outcomes.append(error)
        with patch('studio.study_export.export_study_word', side_effect=export), patch.object(self.server, 'shutdown') as shutdown:
            worker = threading.Thread(target=request_export)
            worker.start()
            try:
                self.assertTrue(entered.wait(3))
                with self.assertRaises(HTTPError) as raised:
                    self.request('/api/shutdown', {})
                self.assertEqual(raised.exception.code, 400)
                shutdown.assert_not_called()
            finally:
                release.set()
                worker.join(5)
            self.assertEqual(outcomes, [200])
            with self.request('/api/shutdown', {}) as response:
                self.assertEqual(response.status, 200)

    def test_failed_word_export_releases_shutdown_guard(self):
        with patch('studio.study_export.export_study_word', side_effect=OSError('failed')):
            with self.assertRaises(HTTPError) as raised:
                self.request('/api/jobs/' + 'd' * 32 + '/word', {})
            self.assertEqual(raised.exception.code, 500)
        with patch.object(self.server, 'shutdown'), self.request('/api/shutdown', {}) as response:
            self.assertEqual(response.status, 200)

    def test_sentence_routes_require_auth_and_empty_json(self):
        path = '/api/jobs/' + 'a' * 32 + '/sentences'
        for data in (None, {}):
            with self.assertRaises(HTTPError) as raised:
                self.request(path, data, authorized=False)
            self.assertEqual(raised.exception.code, 403)
        for body in ({'url': 'https://example.com'}, {'path': 'C:/private'}, {'model': 'anything'}, b'[]', b'null', b'{', b''):
            with self.subTest(body=body), self.assertRaises(HTTPError) as raised:
                self.request(path, body, {'Content-Type': 'application/json'})
            self.assertEqual(raised.exception.code, 400)
        self.sentence_jobs.prepare.assert_not_called()
        self.sentence_jobs.snapshot.return_value = {'id': 'a' * 32, 'status': 'running'}
        with self.request(path, {}) as response:
            self.assertEqual(response.status, 202)
            self.assertEqual(json.load(response), self.sentence_jobs.snapshot.return_value)
        self.sentence_jobs.prepare.assert_called_once_with('a' * 32)
        with self.request(path) as response:
            self.assertEqual(response.status, 200)
            self.assertEqual(json.load(response), self.sentence_jobs.snapshot.return_value)
        self.sentence_jobs.snapshot.assert_called_with('a' * 32)

    def test_sentence_preparation_blocks_shutdown(self):
        self.sentence_jobs.active.return_value = True
        with patch.object(self.server, 'shutdown') as shutdown:
            with self.assertRaises(HTTPError) as raised:
                self.request('/api/shutdown', {})
            self.assertEqual(raised.exception.code, 400)
            shutdown.assert_not_called()

    def test_sentence_service_lifecycle(self):
        self.sentence_class.assert_called_once_with(self.root)
        self.server.shutdown()
        self.server.server_close()
        self.sentence_jobs.close.assert_called_once_with()

    def test_shutdown_retains_original_job_and_audio_guards(self):
        with patch.object(self.server, 'shutdown') as shutdown:
            for status in ('queued', 'running'):
                self.server.jobs.jobs['a' * 32] = {'status': status}
                with self.assertRaises(HTTPError) as raised:
                    self.request('/api/shutdown', {})
                self.assertEqual(raised.exception.code, 400)
            self.server.jobs.jobs.clear()
            with patch.object(type(self.server.shadowing), 'busy', new_callable=lambda: property(lambda store: True)):
                with self.assertRaises(HTTPError) as raised:
                    self.request('/api/shutdown', {})
                self.assertEqual(raised.exception.code, 400)
            shutdown.assert_not_called()

    def test_shutdown_rejects_new_auxiliary_operations(self):
        shutdown_called = threading.Event()
        with patch.object(self.server, 'shutdown', side_effect=shutdown_called.set):
            with self.request('/api/shutdown', {}) as response:
                self.assertEqual(response.status, 200)
            self.assertTrue(shutdown_called.wait(2))
        with patch('studio.study_export.export_study_word') as export:
            for endpoint in ('word', 'sentences'):
                with self.assertRaises(HTTPError) as raised:
                    self.request('/api/jobs/' + 'a' * 32 + '/' + endpoint, {})
                self.assertEqual(raised.exception.code, 400)
            export.assert_not_called()
            self.sentence_jobs.prepare.assert_not_called()

    def test_cross_origin_and_bad_host_rejected(self):
        for headers in [{'Origin': 'https://evil.example'}, {'Host': 'evil.example'}]:
            with self.subTest(headers=headers), self.assertRaises(HTTPError) as raised:
                self.request('/api/jobs', {}, headers)
            self.assertEqual(raised.exception.code, 403)

    def test_upload_job_and_export(self):
        data = b'WEBVTT\n\n00:00:00.000 --> 00:00:02.500\nThis is a local test.\n'
        with self.request('/api/uploads', data, {'X-File-Name': 'sample.vtt'}) as response:
            upload = json.load(response)
        with self.request('/api/jobs', {'source': 'file', 'upload_id': upload['upload_id'], 'options': {}}) as response:
            job_id = json.load(response)['id']
        for _ in range(50):
            with self.request('/api/jobs/' + job_id) as response:
                job = json.load(response)
            if job['status'] in ('done', 'error'):
                break
            time.sleep(.02)
        self.assertEqual(job['status'], 'done', job)
        self.assertEqual(job['result']['title'], 'sample')
        with self.request(f'/api/jobs/{job_id}/files/txt') as response:
            self.assertEqual(response.read().decode(), 'This is a local test.\n')
        with self.assertRaises(HTTPError) as raised:
            self.request(f'/api/jobs/{job_id}/files/metadata.json')
        self.assertEqual(raised.exception.code, 404)

    def test_bad_inputs_and_path_traversal(self):
        for path, data, headers in [('/api/uploads', b'x', {'X-File-Name': '../secret.vtt'}),
                                    ('/api/uploads', b'x', {'X-File-Name': 'script.exe'}),
                                    ('/api/jobs', {'source': 'file', 'path': 'C:/Windows/win.ini'}, {}),
                                    ('/api/jobs', {'source': 'youtube', 'url': 'http://127.0.0.1'}, {})]:
            with self.subTest(path=path, data=data), self.assertRaises(HTTPError) as raised:
                self.request(path, data, headers)
            self.assertEqual(raised.exception.code, 400)

    def test_long_uploaded_subtitle_filename_keeps_its_suffix(self):
        data = b'WEBVTT\n\n00:00:00.000 --> 00:00:01.000\nHello.\n'
        with self.request('/api/uploads', data, {'X-File-Name': 'a' * 95 + '.vtt'}) as response:
            upload = json.load(response)
        stored = self.server.uploads[upload['upload_id']]['path']
        self.assertEqual(stored.suffix, '.vtt')

    def test_queue_rejection_does_not_leave_unreachable_upload(self):
        with self.request('/api/uploads', b'x', {'X-File-Name': 'sample.vtt'}) as response:
            upload = json.load(response)
        with patch.object(self.server.jobs, 'submit', side_effect=UserError('busy', 'Busy')):
            with self.assertRaises(HTTPError) as raised:
                self.request('/api/jobs', {'source': 'file', 'upload_id': upload['upload_id'], 'options': {}})
        self.assertEqual(raised.exception.code, 409)
        self.assertEqual(self.server.uploads, {})
        self.assertEqual(list(self.server.upload_root.iterdir()), [])


class RejectedBodyTests(unittest.TestCase):
    def handler(self, headers, command='POST'):
        handler = Handler.__new__(Handler)
        handler.command = command
        handler.headers = Message()
        for key, value in headers:
            handler.headers[key] = value
        handler.server = Mock(server_port=8765, token='correct')
        handler.connection = Mock()
        handler.connection.gettimeout.return_value = 120
        handler.rfile = Mock()
        handler.rfile.read1.return_value = b'{}'
        handler._send = Mock()
        return handler

    def test_guard_drains_small_body_before_forbidden_without_parsing(self):
        for headers in ([('Host', '127.0.0.1:8765')], [('Host', 'evil')],
                        [('Host', '127.0.0.1:8765'), ('Origin', 'https://evil')]):
            handler = self.handler(headers + [('Content-Length', '2')])
            def sent(code, body):
                self.assertEqual(code, 403)
                handler.rfile.read1.assert_called_once_with(2)
            handler._send.side_effect = sent
            with patch('studio.server.json.loads') as parse:
                self.assertFalse(handler._guard(True))
            parse.assert_not_called()
            self.assertGreater(handler.connection.settimeout.call_args_list[0].args[0], 0)
            self.assertLessEqual(handler.connection.settimeout.call_args_list[0].args[0], .5)
            self.assertEqual(handler.connection.settimeout.call_args.args, (120,))

    def test_rejection_drain_skips_ambiguous_or_large_framing(self):
        for headers in ([], [('Content-Length', '4097')], [('Content-Length', '-1')],
                        [('Content-Length', '+2')], [('Content-Length', '2, 2')],
                        [('Content-Length', '2'), ('Content-Length', '2')],
                        [('Content-Length', '2'), ('Transfer-Encoding', '')],
                        [('Content-Length', '2'), ('Expect', '100-continue')],
                        [('Content-Length', '0')], [('Content-Length', '２')]):
            with self.subTest(headers=headers):
                handler = self.handler(headers)
                self.assertFalse(handler._guard(True))
                handler.rfile.read1.assert_not_called()
                handler.rfile.read.assert_not_called()
                handler._send.assert_called_once()

    def test_rejection_drain_stops_on_timeout_and_restores_timeout(self):
        handler = self.handler([('Content-Length', '4096')])
        handler.rfile.read1.side_effect = TimeoutError()
        self.assertFalse(handler._guard(True))
        handler.rfile.read1.assert_called_once_with(4096)
        self.assertEqual(handler.connection.settimeout.call_args.args, (120,))
        self.assertEqual(handler._send.call_args.args[0], 403)

    def test_rejection_drain_has_total_deadline_not_per_chunk_timeout(self):
        handler = self.handler([('Content-Length', '4096')])
        handler.rfile.read1.return_value = b'x'
        with patch('studio.server.time.monotonic', side_effect=[10, 10, 10.6]):
            self.assertFalse(handler._guard(True))
        handler.rfile.read1.assert_called_once_with(4096)


if __name__ == '__main__':
    unittest.main()

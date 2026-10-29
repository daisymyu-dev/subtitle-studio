"""Loopback-only HTTP API. Never accepts arbitrary server-side paths."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from contextlib import contextmanager
import json
from pathlib import Path
import re
import secrets
import sqlite3
import threading
import time
from urllib.parse import parse_qs, quote, unquote, urlparse
import uuid

from .service import JobManager, Pipeline, UserError, validate_options
from .subtitles import normalize_youtube_url, safe_filename

MAX_UPLOAD = 500 * 1024 * 1024
EXTENSIONS = {'.srt', '.vtt', '.mp3', '.wav', '.m4a', '.mp4', '.webm', '.mov', '.mkv', '.ogg', '.flac', '.aac', '.opus'}
DESIGNS = {
    'studio': {'name': '暗色录音棚', 'number': '01', 'top': '捕捉声音，', 'bottom': '留下原话。', 'tagline': 'THE ORIGINAL. ON RECORD.', 'note': '一台留住每句话的本地工作站。'},
    'signal': {'name': '先锋信号站', 'number': '02', 'top': '声音，', 'bottom': '有迹可循。', 'tagline': 'MAKE EVERY WORD VISIBLE.', 'note': '把听见的，变成看得见的。'},
    'chrome': {'name': '银色精密仪器', 'number': '03', 'top': '从声音，', 'bottom': '到清晰。', 'tagline': 'LESS NOISE. MORE CLARITY.', 'note': '给每一段声音，一个清晰的落点。'},
}
STUDY_VIEWS = {'folio': 'A · 书页型', 'prism': 'B · 并排型', 'nocturne': 'C · 专注型'}
PRONUNCIATION_IDS = (
    'glass-half','natural-governor','nimby','coiled-spring','buy-the-dip','tailwinds',
    'otherworldly','astounding','bifurcated','ensued','historical-analogs',
    'irrational-exuberance','preemptive-tightening','qoq-revenue','priced-in',
    'de-risking','long-short-positioning','capitulation','dovish','style-tilt',
    'frontier-models','revenue-per-worker','cds-widen','treasury-issuance',
)
STATIC_ASSETS = {
    '/learning-library.js': ('learning-library.js', 'text/javascript; charset=utf-8'),
    '/learning-dictionary.js': ('learning-dictionary.js', 'text/javascript; charset=utf-8'),
    '/privacy.html': ('privacy.html', 'text/html; charset=utf-8'),
    '/learning-pronunciations.js': ('learning-pronunciations.js', 'text/javascript; charset=utf-8'),
    **{f'/pronunciations/{term}.wav': (f'pronunciations/{term}.wav', 'audio/wav') for term in PRONUNCIATION_IDS},
    '/learning-lexicon.js': ('learning-lexicon.js', 'text/javascript; charset=utf-8'),
    '/learning-core.js': ('learning-core.js', 'text/javascript; charset=utf-8'),
    '/learning-highlights.js': ('learning-highlights.js', 'text/javascript; charset=utf-8'),
    '/learning.css': ('learning.css', 'text/css; charset=utf-8'),
    '/watch-core.js': ('watch-core.js', 'text/javascript; charset=utf-8'),
    '/watch-sync.js': ('watch-sync.js', 'text/javascript; charset=utf-8'),
    '/watch.css': ('watch.css', 'text/css; charset=utf-8'),
    '/shadow-core.js': ('shadow-core.js', 'text/javascript; charset=utf-8'),
    '/shadowing.js': ('shadowing.js', 'text/javascript; charset=utf-8'),
    '/shadowing.css': ('shadowing.css', 'text/css; charset=utf-8'),
    '/app.js': ('app.js', 'text/javascript; charset=utf-8'),
    '/style.css': ('style.css', 'text/css; charset=utf-8'),
    '/themes.css': ('themes.css', 'text/css; charset=utf-8'),
    '/designs.css': ('designs.css', 'text/css; charset=utf-8'),
    '/vendor/open-props-easing.css': ('vendor/open-props-easing.css', 'text/css; charset=utf-8'),
    '/concept.css': ('concept.css', 'text/css; charset=utf-8'),
    '/concept-core.js': ('concept-core.js', 'text/javascript; charset=utf-8'),
    '/concept.js': ('concept.js', 'text/javascript; charset=utf-8'),
    '/concepts.css': ('concepts.css', 'text/css; charset=utf-8'),
    **{f'/demo/audio/{index:02}.wav': (f'demo/audio/{index:02}.wav', 'audio/wav') for index in range(4)},
    **{f'/previews/{name}.jpg': (f'previews/{name}.jpg', 'image/jpeg') for name in STUDY_VIEWS},
    **{f'/previews/{name}.jpg': (f'previews/{name}.jpg', 'image/jpeg') for name in DESIGNS},
}


def parse_byte_range(value, size):
    if size <= 0:
        raise ValueError('Empty audio')
    if value is None:
        return 0, size - 1, False
    match = re.fullmatch(r'bytes=(\d*)-(\d*)', value)
    if not match or not any(match.groups()):
        raise ValueError('Invalid range')
    left, right = match.groups()
    if not left:
        length = int(right)
        if length <= 0:
            raise ValueError('Invalid suffix')
        return max(0, size - length), size - 1, True
    start, end = int(left), int(right) if right else size - 1
    if start >= size or end < start:
        raise ValueError('Unsatisfiable range')
    return start, min(end, size - 1), True


class StudioServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, root, port=8765, pipeline=None, web_root=None, shadowing=None):
        from .shadowing import ShadowingStore
        self.root = Path(root)
        self.web_root = Path(web_root or Path(__file__).resolve().parents[1] / 'web')
        self.upload_root = self.root / '.uploads'
        self.upload_root.mkdir(parents=True, exist_ok=True)
        self.token = secrets.token_urlsafe(32)
        self.uploads = {}
        self.upload_lock = threading.Lock()
        self.operation_lock = threading.Lock()
        self.active_operations = 0
        self.stopping = False
        from .learning_store import LearningStore
        from .dictionary import DictionaryClient
        self.learning = LearningStore(self.root)
        self.dictionary = DictionaryClient()
        super().__init__(('127.0.0.1', port), Handler)
        self.jobs = JobManager(pipeline or Pipeline(root))
        self.shadowing = shadowing or ShadowingStore(root)
        self.media_tickets = {}
        self.media_lock = threading.Lock()
        from .video_bridge import VideoBridge
        try:
            from .sentence_study import SentencePreparation
            self.sentence_jobs = SentencePreparation(root)
            self.video_bridge = VideoBridge(f'http://127.0.0.1:{self.server_port}', self.web_root)
        except BaseException:
            self.server_close()
            raise

    def server_close(self):
        if getattr(self, 'sentence_jobs', None):
            self.sentence_jobs.close()
        if getattr(self, 'video_bridge', None):
            self.video_bridge.close()
        if getattr(self, 'jobs', None):
            self.jobs.close()
        if getattr(self, 'shadowing', None):
            self.shadowing.close()
        with self.upload_lock:
            for upload in self.uploads.values():
                upload['path'].unlink(missing_ok=True)
                upload['path'].parent.rmdir()
            self.uploads.clear()
        super().server_close()

    @contextmanager
    def auxiliary_operation(self):
        # Admission and shutdown share a lock; work itself must not hold it.
        with self.operation_lock:
            if self.stopping:
                raise ValueError('工具正在关闭，请重新启动后重试。')
            self.active_operations += 1
        try:
            yield
        finally:
            with self.operation_lock:
                self.active_operations -= 1


def make_server(root, port=8765, pipeline=None, web_root=None, shadowing=None):
    return StudioServer(root, port, pipeline, web_root, shadowing)


class Handler(BaseHTTPRequestHandler):
    server_version = 'SubtitleStudio/1.0'

    def setup(self):
        super().setup()
        self.connection.settimeout(120)

    def log_message(self, *args):
        # Do not log URLs, temporary tokens, metadata or subtitle text.
        pass

    def _send(self, code, body, content_type='application/json; charset=utf-8', headers=None):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False).encode('utf-8')
        elif isinstance(body, str):
            body = body.encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; media-src 'self'; "
                         f"frame-src {self.server.video_bridge.origin}; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        if self.command == 'HEAD':
            return
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _guard(self, authenticated=False):
        host = f'127.0.0.1:{self.server.server_port}'
        if self.headers.get('Host') != host:
            error = '仅允许从本机地址访问。'
        elif self.headers.get('Origin') and self.headers.get('Origin') != 'http://' + host:
            error = '不接受其他网页发起的请求。'
        elif authenticated and not secrets.compare_digest(self.headers.get('X-App-Token', ''), self.server.token):
            error = '页面会话已过期，请刷新。'
        else:
            return True
        self._drain_rejected_body()
        self._send(403, {'error': error})
        return False

    def _drain_rejected_body(self):
        # Avoid Windows resets for small rejected POSTs, without interpreting them
        # or waiting on ambiguous framing, large uploads, or 100-continue clients.
        lengths = self.headers.get_all('Content-Length', [])
        if (self.command != 'POST' or len(lengths) != 1
                or self.headers.get_all('Transfer-Encoding') is not None
                or self.headers.get_all('Expect') is not None
                or not re.fullmatch(r'[0-9]{1,4}', lengths[0])):
            return
        remaining = int(lengths[0])
        if not 0 < remaining <= 4096:
            return
        previous_timeout = self.connection.gettimeout()
        deadline = time.monotonic() + .5
        try:
            while remaining:
                timeout = deadline - time.monotonic()
                if timeout <= 0:
                    break
                self.connection.settimeout(min(.5, timeout))
                block = self.rfile.read1(remaining)
                if not block:
                    break
                remaining -= len(block)
        except OSError:
            pass
        finally:
            self.connection.settimeout(previous_timeout)

    def do_GET(self):
        path = urlparse(self.path).path
        if not self._guard(path.startswith('/api/')):
            return
        if path in ('/api/learning','/api/library'):
            try:
                self._send(200,self.server.learning.profile() if path=='/api/learning' else {'items':self.server.learning.history()})
            except (OSError,sqlite3.Error,ValueError):
                self._send(500,{'error':'本机学习记录暂时不可用。'})
        elif match := re.fullmatch(r'/media/([a-f0-9]{32})/audio', path):
            self._stream_audio(match[1])
        elif match := re.fullmatch(r'/api/jobs/([a-f0-9]{32})/sentences', path):
            try:
                self._send(200, self.server.sentence_jobs.snapshot(match[1]))
            except (UserError, ValueError, OSError) as error:
                self._send(404, {'error': str(error) if isinstance(error, (UserError, ValueError)) else '学习资料文件不可用，请重新整理字幕。'})
        elif match := re.fullmatch(r'/api/jobs/([a-f0-9]{32})/(study|audio)', path):
            try:
                self._send(200, self.server.shadowing.load_study(match[1]) if match[2] == 'study' else self._audio_status(match[1]))
            except (UserError, ValueError, OSError) as error:
                self._send(404, {'error': str(error) if isinstance(error, (UserError, ValueError)) else '学习资料文件不可用，请重新整理字幕。'})
        elif path == '/health':
            import importlib.util
            from .runtime import VERSION
            self._send(200, {'app': 'youtube-subtitle-studio', 'version': VERSION,
                             'capabilities': {'asr': importlib.util.find_spec('faster_whisper') is not None,
                                              'original_audio': importlib.util.find_spec('av') is not None,
                                              'dictionary': True, 'library': True, 'local_word': True}})
        elif path == '/':
            page = (self.server.web_root / 'index.html').read_text(encoding='utf-8')
            design = parse_qs(urlparse(self.path).query).get('design', ['studio'])[0]
            if design not in DESIGNS:
                design = 'studio'
            replacements = {'__SESSION_TOKEN__': self.server.token, '__DESIGN__': design,
                            '__VIDEO_BRIDGE_ORIGIN__': self.server.video_bridge.origin,
                            **{f'__DESIGN_{key.upper()}__': value for key, value in DESIGNS[design].items()},
                            **{f'__CURRENT_{name.upper()}__': 'aria-current="page"' if name == design else '' for name in DESIGNS}}
            for key, value in replacements.items():
                page = page.replace(key, value)
            self._send(200, page, 'text/html; charset=utf-8')
        elif path == '/designs':
            self._send(200, (self.server.web_root / 'designs.html').read_bytes(), 'text/html; charset=utf-8')
        elif path == '/concepts':
            self._send(200, (self.server.web_root / 'concepts.html').read_bytes(), 'text/html; charset=utf-8')
        elif path == '/concept':
            view = parse_qs(urlparse(self.path).query).get('view', ['folio'])[0]
            if view not in STUDY_VIEWS:
                view = 'folio'
            page = (self.server.web_root / 'concept.html').read_text(encoding='utf-8')
            self._send(200, page.replace('__VIEW__', view).replace('__VIEW_LABEL__', STUDY_VIEWS[view]), 'text/html; charset=utf-8')
        elif path in STATIC_ASSETS:
            filename, content_type = STATIC_ASSETS[path]
            target = self.server.web_root / filename
            if not target.is_file():
                self._send(404, {'error': '预览尚未生成或文件已被移动。'})
                return
            self._send(200, target.read_bytes(), content_type)
        elif match := re.fullmatch(r'/api/jobs/([a-f0-9]{32})(?:/files/(srt|vtt|txt|docx))?', path):
            job = self.server.jobs.snapshot(match[1])
            if not job:
                job = self._retained_job(match[1])
            elif job['status'] == 'done':
                # Sentence migration publishes metadata outside JobManager. Read
                # it under the same lock used by completed Word memory updates.
                with self.server.jobs.lock:
                    retained = self._retained_job(match[1])
                    current = self.server.jobs.jobs.get(match[1])
                    version = retained['result'].get('sentence_version') if retained else None
                    if current and current['status'] == 'done' and type(version) is int and version == 1:
                        current['result'] = retained['result']
                        job = dict(current)
            if not job:
                self._send(404, {'error': '未找到任务；重启前的结果仍保存在 results 文件夹。'})
            elif not match[2]:
                self._send(200, job)
            elif job['status'] != 'done':
                self._send(409, {'error': '任务尚未完成。'})
            else:
                result = job['result']
                ext = match[2]
                if ext not in result['files']:
                    self._send(404, {'error': '此任务没有生成该格式，请使用一键中英 Word 按钮。'})
                    return
                target = self.server.root / 'results' / match[1] / result['files'][ext]
                if target.resolve().parent != (self.server.root / 'results' / match[1]).resolve() or target.name != result['files'][ext]:
                    self._send(404, {'error': '结果文件名无效。'})
                    return
                if not target.is_file():
                    self._send(404, {'error': '结果文件已被移动或删除。'})
                    return
                self._send(200, target.read_bytes(),
                           'application/vnd.openxmlformats-officedocument.wordprocessingml.document' if ext == 'docx' else 'text/vtt; charset=utf-8' if ext == 'vtt' else 'text/plain; charset=utf-8',
                           {'Content-Disposition': f"attachment; filename=\"subtitles.{ext}\"; filename*=UTF-8''{quote(target.name)}"})
        else:
            self._send(404, {'error': '未找到。'})

    def _retained_job(self, job_id):
        directory = (self.server.root / 'results' / job_id).resolve()
        if directory.parent != (self.server.root / 'results').resolve():
            return None
        path = directory / 'metadata.json'
        try:
            if path.resolve().parent != directory or path.stat().st_size > 10 * 1024 * 1024:
                return None
            result = json.loads(path.read_text('utf-8'))
            if result.get('id') != job_id or not isinstance(result.get('files'), dict):
                return None
            return {'id': job_id, 'status': 'done', 'stage': 'done', 'message': '已恢复本机保存的完整结果。', 'result': result}
        except (OSError, ValueError, TypeError, AttributeError):
            return None

    def _audio_status(self, job_id):
        status = dict(self.server.shadowing.snapshot(job_id))
        if status['status'] == 'ready':
            with self.server.media_lock:
                entry = self.server.media_tickets.get(job_id)
                if not entry or entry['deadline'] <= time.monotonic() + 30:
                    entry = {'ticket': secrets.token_urlsafe(32), 'deadline': time.monotonic() + 1800,
                             'expires_at': time.time() + 1800}
                    self.server.media_tickets[job_id] = entry
            status['media_url'] = f'/media/{job_id}/audio?ticket={entry["ticket"]}'
            status['expires_at'] = entry['expires_at']
        return status

    def _stream_audio(self, job_id):
        ticket = parse_qs(urlparse(self.path).query).get('ticket', [''])[0]
        with self.server.media_lock:
            expected = self.server.media_tickets.get(job_id)
        if (not expected or expected['deadline'] <= time.monotonic() or not secrets.compare_digest(ticket, expected['ticket'])
                or self.headers.get('Sec-Fetch-Site') not in (None, 'same-origin')):
            self._send(403, {'error': '原音播放凭证无效，请重新打开跟读区。'})
            return
        path = self.server.shadowing.media_file(job_id)
        if not path:
            self._send(404, {'error': '请先准备原音。'})
            return
        try:
            size = path.stat().st_size
            try:
                start, end, partial = parse_byte_range(self.headers.get('Range'), size)
            except ValueError:
                self._send(416, b'', headers={'Content-Range': f'bytes */{size}', 'Accept-Ranges': 'bytes'})
                return
            mime = {'.m4a': 'audio/mp4', '.mp4': 'audio/mp4', '.webm': 'audio/webm', '.wav': 'audio/wav',
                    '.mp3': 'audio/mpeg', '.ogg': 'audio/ogg', '.opus': 'audio/ogg'}.get(path.suffix.lower())
            if not mime:
                self._send(415, {'error': '此原音格式不能播放。'})
                return
            with path.open('rb') as stream:
                self.send_response(206 if partial else 200)
                for key,value in {'Content-Type':mime,'Content-Length':str(end-start+1), 'Accept-Ranges':'bytes',
                                  'Cache-Control':'no-store','Referrer-Policy':'no-referrer',
                                  'X-Content-Type-Options':'nosniff','Cross-Origin-Resource-Policy':'same-origin'}.items():
                    self.send_header(key,value)
                if partial:
                    self.send_header('Content-Range',f'bytes {start}-{end}/{size}')
                self.end_headers()
                if self.command == 'HEAD':
                    return
                stream.seek(start)
                remaining = end-start+1
                while remaining:
                    block=stream.read(min(64*1024,remaining))
                    if not block:
                        break
                    self.wfile.write(block)
                    remaining-=len(block)
        except (BrokenPipeError, ConnectionResetError, OSError):
            # A client may stop after its selected fragment; never log media URLs.
            self.close_connection = True

    def do_HEAD(self):
        if re.fullmatch(r'/media/[a-f0-9]{32}/audio',urlparse(self.path).path):
            self.do_GET()
        else:
            self._send(404,b'')

    def _length(self, maximum):
        if self.headers.get('Transfer-Encoding'):
            raise ValueError('不支持分块上传。')
        try:
            size = int(self.headers.get('Content-Length', ''))
        except ValueError:
            raise ValueError('缺少有效的文件长度。') from None
        if not 0 < size <= maximum:
            raise ValueError('文件为空或超过大小限制（音视频最大 500 MiB）。')
        return size

    def _json(self):
        if self.headers.get_content_type() != 'application/json':
            raise ValueError('请求格式应为 JSON。')
        data = json.loads(self.rfile.read(self._length(16 * 1024)))
        if not isinstance(data, dict):
            raise ValueError('请求格式无效。')
        return data

    def _upload(self):
        size = self._length(MAX_UPLOAD)
        name = unquote(self.headers.get('X-File-Name', ''))
        if (not name or len(name) > 180 or '/' in name or '\\' in name
                or Path(name).suffix.lower() not in EXTENSIONS):
            raise ValueError('请选择支持的音视频文件，或 UTF-8 编码的 SRT / VTT。')
        with self.server.upload_lock:
            if len(self.server.uploads) >= 8:
                raise ValueError('待处理文件过多，请先处理或重启工具。')
            upload_id = uuid.uuid4().hex
            directory = self.server.upload_root / upload_id
            directory.mkdir()
            target = directory / (safe_filename(Path(name).stem) + Path(name).suffix.lower())
            try:
                remaining = size
                with target.open('xb') as output:
                    while remaining:
                        block = self.rfile.read(min(1024 * 1024, remaining))
                        if not block:
                            raise ValueError('文件上传未完成，请重新选择。')
                        output.write(block)
                        remaining -= len(block)
            except Exception:
                target.unlink(missing_ok=True)
                directory.rmdir()
                raise
            self.server.uploads[upload_id] = {'path': target, 'name': name}
        self._send(201, {'upload_id': upload_id, 'name': name})

    def do_POST(self):
        if not self._guard(True):
            return
        path = urlparse(self.path).path
        try:
            if path == '/api/learning/term':
                with self.server.auxiliary_operation():
                    self._send(200,self.server.learning.set_term(self._json()))
            elif path == '/api/learning/progress':
                data=self._json()
                if set(data)!={'job_id','time'}:raise ValueError('学习进度参数无效。')
                with self.server.auxiliary_operation():
                    self.server.learning.set_progress(data['job_id'],data['time'])
                    self._send(200,{'ok':True})
            elif path == '/api/dictionary':
                data=self._json()
                if set(data)!={'word'}:raise ValueError('查词只接受一个英文单词。')
                from .dictionary import DictionaryError
                try:
                    with self.server.auxiliary_operation():
                        self._send(200,self.server.dictionary.lookup(data['word']))
                except DictionaryError as error:self._send(409,{'error':str(error),'code':'dictionary'})
            elif path == '/api/uploads':
                self._upload()
            elif match := re.fullmatch(r'/api/jobs/([a-f0-9]{32})/sentences', path):
                if self._json():
                    raise ValueError('准备句子只接受当前任务，不接受外部网址或本机路径。')
                with self.server.auxiliary_operation():
                    self.server.sentence_jobs.prepare(match[1])
                    self._send(202, self.server.sentence_jobs.snapshot(match[1]))
            elif match := re.fullmatch(r'/api/jobs/([a-f0-9]{32})/audio', path):
                if self._json():
                    raise ValueError('准备原音只接受当前任务，不接受外部网址或本机路径。')
                import importlib.util
                if importlib.util.find_spec('av') is None:
                    raise UserError('dependency', 'Windows Core 不包含本地原音跟读所需的音频组件，未下载音轨。可继续使用视频播放器，或按 docs/build.md 安装源码版可选依赖。')
                self.server.shadowing.prepare(match[1])
                self._send(202, self._audio_status(match[1]))
            elif match := re.fullmatch(r'/api/jobs/([a-f0-9]{32})/word', path):
                if self._json():
                    raise ValueError('导出只接受当前任务，不接受网址或本机路径。')
                from .study_export import export_study_word
                with self.server.auxiliary_operation():
                    result = export_study_word(self.server.root, match[1])
                    with self.server.jobs.lock:
                        job = self.server.jobs.jobs.get(match[1])
                        if job and job['status'] == 'done':
                            job['result'] = result
                    self._send(200, result)
            elif path == '/api/study-jobs':
                data = self._json()
                if set(data) - {'url', 'model'}:
                    raise ValueError('字幕学习只接受视频链接和识别模型。')
                value = normalize_youtube_url(data.get('url', ''))
                options = validate_options({'mode':'auto','language':'en','asr_language':'auto',
                                            'model':data.get('model','base'),'bilingual_study':True,
                                            'sentence_study':True})
                self._send(202, {'id':self.server.jobs.submit('youtube',value,options)})
            elif path == '/api/word-jobs':
                data = self._json()
                if set(data) - {'url', 'model'}:
                    raise ValueError('Word 按钮只接受视频链接和识别模型，不接受本机路径。')
                value = normalize_youtube_url(data.get('url', ''))
                options = validate_options({'mode': 'auto', 'language': 'en', 'asr_language': 'auto',
                                            'model': data.get('model', 'base'), 'bilingual_word': True,
                                            'sentence_study': True})
                self._send(202, {'id': self.server.jobs.submit('youtube', value, options)})
            elif path == '/api/jobs':
                data = self._json()
                options = validate_options(data.get('options', {}))
                source = data.get('source')
                if source == 'youtube':
                    value = normalize_youtube_url(data.get('url', ''))
                    job_id = self.server.jobs.submit(source, value, options)
                elif source == 'file':
                    with self.server.upload_lock:
                        upload = self.server.uploads.pop(data.get('upload_id', ''), None)
                    if not upload:
                        raise ValueError('请先选择并上传本地文件；不支持任意本机路径。')
                    def cleanup():
                        upload['path'].unlink(missing_ok=True)
                        upload['path'].parent.rmdir()
                    try:
                        job_id = self.server.jobs.submit(source, upload['path'], options, cleanup)
                    except Exception:
                        cleanup()
                        raise
                else:
                    raise ValueError('请选择 YouTube 链接或本地文件。')
                self._send(202, {'id': job_id})
            elif path == '/api/shutdown':
                # Consume a small optional JSON body before rejecting a busy
                # request; closing with unread POST bytes can reset TCP on Windows.
                if self.headers.get('Content-Length', '0') != '0' and self._json():
                    raise ValueError('关闭工具不接受额外参数。')
                with self.server.operation_lock:
                    with self.server.jobs.lock:
                        jobs_busy = any(job['status'] in ('queued', 'running') for job in self.server.jobs.jobs.values())
                    if (self.server.active_operations or self.server.sentence_jobs.active()
                            or self.server.shadowing.busy or jobs_busy):
                        raise ValueError('还有任务未完成，请完成后再关闭。')
                    self.server.stopping = True
                self._send(200, {'message': '工具已关闭，可以再次双击桌面入口启动。'})
                threading.Thread(target=self.server.shutdown, daemon=True).start()
            else:
                self._send(404, {'error': '未找到。'})
        except UserError as error:
            self._send(409, {'error': str(error), 'code': error.code})
        except (ValueError, TypeError, KeyError, UnicodeError):
            import sys
            error = sys.exception()
            message = str(error) if isinstance(error, ValueError) and not isinstance(error, json.JSONDecodeError) else '输入格式不正确，请检查后重试。'
            self._send(400, {'error': message})
        except (OSError, TimeoutError, sqlite3.Error):
            self._send(500, {'error': '本地文件读写失败，请检查磁盘空间、权限和文件是否被占用。'})

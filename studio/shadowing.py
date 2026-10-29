"""Full retained study cues and explicitly prepared, local original audio.

No read method downloads media. Persisted paths are always relative safe names;
public data never contains a server media path. Invalid study data raises the
same UserError used by the service, rather than returning a partial transcript.
"""

from collections import deque
import json
import math
import os
from pathlib import Path
import re
import stat
import tempfile
import threading
import uuid

from .service import NativeTools, UserError
from .subtitles import normalize_youtube_url


MAX_AUDIO_BYTES = 500 * 1024 * 1024
_MANIFEST = 'shadowing-audio.json'
_FORMATS = {'.m4a': 'mov', '.webm': 'matroska', '.wav': 'wav',
            '.mp3': 'mp3', '.ogg': 'ogg', '.opus': 'ogg'}
_MESSAGES = {'idle': '尚未准备原音；点击准备后才会下载。',
             'queued': '原音准备已排队。',
             'downloading': '正在下载并检查原始音频，请稍候。',
             'ready': '原始音频已就绪。',
             'error': '原音准备失败，请稍后重试。'}


def _audio_error():
    return UserError('study_audio', '音频无效、格式不支持或超过 500 MiB，请重新准备原音。')


def _failure_message(error):
    # Never echo downloader exceptions: they can contain local paths or tokens.
    return {'network': '网络连接失败，请检查网络后重试原音准备。',
            'timeout': '原音下载超时，请检查网络后重试。',
            'rate_limit': 'YouTube 暂时限制请求，请稍后重试原音准备。',
            'access': 'YouTube 要求访问权限或验证；本工具不自动读取 Cookies。',
            'unavailable': '视频当前不可访问，无法准备原音。',
            'dependency': '原音处理依赖不可用，请检查本地安装。',
            'study_audio': str(_audio_error()),
            'study_path': str(_path_error()),
            'study_data': str(_data_error())}.get(getattr(error, 'code', None), _MESSAGES['error'])


def _data_error():
    return UserError('study_data', '跟读数据缺失或损坏，不能保证字幕全文；请重新提取字幕。')


def _path_error():
    return UserError('study_path', '跟读文件路径无效或包含链接，无法安全读取。')


def _safe_name(value):
    if (not isinstance(value, str) or not value or value in ('.', '..')
            or value[-1] in ' .'
            or re.search(r'[<>:"/\\|?*\x00-\x1f]', value)
            or value.split('.')[0].upper() in {
                'CON', 'PRN', 'AUX', 'NUL',
                *(f'COM{i}' for i in range(1, 10)), *(f'LPT{i}' for i in range(1, 10))}):
        raise _path_error()
    return value


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise _data_error()
        result[key] = value
    return result


def _times(value):
    if not isinstance(value, dict):
        raise _data_error()
    start, end = value.get('start'), value.get('end')
    try:
        valid = (type(start) in (int, float) and type(end) in (int, float)
                 and math.isfinite(start) and math.isfinite(end)
                 and start >= 0 and end > start)
    except OverflowError:
        valid = False
    if not valid:
        raise _data_error()
    return start, end


def _parse_srt(text):
    """Parse every SRT block, with no cleaning/filtering or preview fallback."""
    clock = r'([0-9]{2,}):([0-5][0-9]):([0-5][0-9])[,.]([0-9]{3})'
    timing = re.compile(clock + r'[ \t]+-->[ \t]+' + clock)
    cues = []
    for block in re.split(r'\n[ \t]*\n', text.replace('\r\n', '\n').strip('\n')):
        lines = block.splitlines()
        if len(lines) < 3 or not re.fullmatch(r'[0-9]+', lines[0]):
            raise _data_error()
        match = timing.fullmatch(lines[1])
        if not match or not '\n'.join(lines[2:]).strip():
            raise _data_error()
        try:
            parts = [int(part) for part in match.groups()]
            start = parts[0] * 3600 + parts[1] * 60 + parts[2] + parts[3] / 1000
            end = parts[4] * 3600 + parts[5] * 60 + parts[6] + parts[7] / 1000
        except (ValueError, OverflowError):
            raise _data_error() from None
        cue = {'start': start, 'end': end, 'text': '\n'.join(lines[2:])}
        _times(cue)
        cues.append(cue)
    return cues


def _source_chinese(cues, blocks):
    """Recover exact chronological source groups before using time overlap."""
    if not blocks:
        return {}
    ordered = sorted(enumerate(cues), key=lambda item: (item[1]['start'], item[1]['end']))
    cursor, references = 0, {}
    for block in blocks:
        if cursor >= len(ordered) or block['start'] != ordered[cursor][1]['start']:
            return {}
        parts, length, end = [], 0, -1
        while cursor < len(ordered) and length < len(block['english']):
            index, cue = ordered[cursor]
            length += len(cue['text']) + (1 if parts else 0)
            parts.append(cue['text'])
            end = max(end, cue['end'])
            references[index] = block['chinese']
            cursor += 1
        if ' '.join(parts) != block['english'] or end != block['end']:
            return {}
    # Legacy blocks may not retain source text; never trust a partial match.
    return references if cursor == len(ordered) else {}


class ShadowingStore:
    """One download worker, four waiting jobs, and reusable per-result media.

    load_study/snapshot/media_file are read-only. prepare is the only download
    trigger; it returns safe error snapshots for closed/full/no-source cases.
    Malformed IDs raise ValueError; missing/invalid result data raises UserError.
    close cancels queued work and waits for an already active download to finish.
    """

    def __init__(self, root, tools=None):
        root = Path(root).absolute()
        if root.is_symlink() or getattr(root, 'is_junction', lambda: False)():
            raise _path_error()
        self.root = root.resolve()
        self.tools = NativeTools(self.root) if tools is None else tools
        self._condition = threading.Condition(threading.RLock())
        self._queue = deque()
        self._active = None
        self._states = {}
        self._verified = {}
        self._closed = False
        self._worker = None

    def _confined(self, path, base=None):
        """Reject reparse points as well as resolved escapes (including junctions)."""
        base = self.root if base is None else base
        try:
            relative = path.relative_to(self.root)
            path.relative_to(base)
            current = self.root
            for part in ('', *relative.parts):
                if part:
                    current = current / part
                try:
                    info = current.lstat()
                except FileNotFoundError:
                    continue
                if (stat.S_ISLNK(info.st_mode)
                        or getattr(info, 'st_file_attributes', 0)
                        & getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0x400)):
                    raise _path_error()
            path.resolve().relative_to(base.resolve())
        except (OSError, ValueError, RuntimeError):
            raise _path_error() from None
        return path

    def _file(self, path):
        self._confined(path)
        try:
            if not stat.S_ISREG(path.stat().st_mode):
                raise _path_error()
        except OSError:
            raise _data_error() from None
        return path

    def _json(self, path):
        self._file(path)
        try:
            if path.stat().st_size > 64 * 1024 * 1024:
                raise _data_error()
            return json.loads(path.read_text(encoding='utf-8-sig'), object_pairs_hook=_unique_object)
        except (OSError, ValueError, UnicodeError, RecursionError):
            raise _data_error() from None

    def _job(self, job_id):
        if not isinstance(job_id, str) or not re.fullmatch(r'[a-f0-9]{32}', job_id):
            raise ValueError('任务编号无效。')
        job = self._confined(self.root / 'results' / job_id)
        metadata = self._json(job / 'metadata.json')
        if (not isinstance(metadata, dict) or metadata.get('id') != job_id
                or not isinstance(metadata.get('title'), str) or not metadata['title'].strip()
                or not isinstance(metadata.get('files'), dict)):
            raise _data_error()
        name = _safe_name(metadata['files'].get('srt'))
        if Path(name).suffix.lower() != '.srt':
            raise _data_error()
        self._confined(job / name)
        url = metadata.get('url')
        if url is not None:
            if not isinstance(url, str):
                raise _data_error()
            try:
                url = normalize_youtube_url(url)
            except ValueError:
                raise _data_error() from None
        return job, metadata, url

    def load_study(self, job_id):
        job, metadata, url = self._job(job_id)
        if metadata.get('sentence_version')==1:
            from .sentence_study import load_sentence_data
            return load_sentence_data(self.root,job_id)
        cue_file = self._confined(job / 'study-cues.json')
        if cue_file.exists():
            cues = self._json(cue_file)
        else:
            try:
                cues = _parse_srt(self._file(job / metadata['files']['srt']).read_text(encoding='utf-8-sig'))
            except (OSError, UnicodeError):
                raise _data_error() from None
        if not isinstance(cues, list) or not cues:
            raise _data_error()
        count = metadata.get('count')
        if count is not None and (type(count) is not int or count != len(cues)):
            raise _data_error()
        for cue in cues:
            _times(cue)
            if not isinstance(cue.get('text'), str) or not cue['text'].strip():
                raise _data_error()
        bilingual_file = self._confined(job / 'bilingual.json')
        blocks, source = [], ''
        if bilingual_file.exists():
            bilingual = self._json(bilingual_file)
            if not isinstance(bilingual, dict) or not isinstance(bilingual.get('blocks'), list):
                raise _data_error()
            blocks = bilingual['blocks']
            source = bilingual.get('chinese_source', '')
            if not isinstance(source, str):
                raise _data_error()
            for block in blocks:
                _times(block)
                if (not isinstance(block.get('english'), str)
                        or not isinstance(block.get('chinese'), str)):
                    raise _data_error()
        references = _source_chinese(cues, blocks)
        result = []
        for index, cue in enumerate(cues):
            best, chinese = 0, references.get(index, '')
            if index not in references:
                for block in blocks:
                    overlap = min(cue['end'], block['end']) - max(cue['start'], block['start'])
                    if overlap > best:
                        best, chinese = overlap, block['chinese']
            result.append({'start': cue['start'], 'end': cue['end'],
                           'english': cue['text'], 'chinese': chinese})
        return {'id': job_id, 'title': metadata['title'], 'url': url, 'cues': result,
                'chinese_note': '中文为段落参考（优先按英文来源分组匹配），不是逐句精确翻译。'
                                + (f' 来源：{source}' if source else '')}

    @staticmethod
    def _public(job_id, status, message=None):
        return {'id': job_id, 'status': status, 'message': message or _MESSAGES[status]}

    @staticmethod
    def _stamp(path):
        info = path.stat()
        return (info.st_size, info.st_mtime_ns, info.st_ctime_ns, info.st_ino)

    def _validate_audio(self, path):
        self._file(path)
        suffix = path.suffix.lower()
        if suffix not in _FORMATS or not 0 < path.stat().st_size <= MAX_AUDIO_BYTES:
            raise _audio_error()
        try:
            import av
        except ImportError:
            raise UserError('dependency', '本地音频检查依赖不可用。') from None
        try:
            # Force a supported local container, not an auto-detected playlist
            # that could ask FFmpeg to fetch another URL. Decode actual audio,
            # rather than trusting the extension or container's stream labels.
            with path.open('rb') as stream, av.open(
                    stream, mode='r', format=_FORMATS[suffix],
                    options={'protocol_whitelist': 'file'}) as media:
                if not media.streams.audio or media.streams.video:
                    raise _audio_error()
                if not any(frame.samples > 0 and frame.sample_rate > 0
                           for frame in media.decode(audio=0)):
                    raise _audio_error()
        except Exception:
            raise _audio_error() from None

    def _cached(self, job_id, job, url):
        try:
            manifest = self._json(job / _MANIFEST)
            if (not isinstance(manifest, dict) or type(manifest.get('version')) is not int
                    or manifest['version'] != 1 or manifest.get('id') != job_id
                    or not url or manifest.get('url') != url
                    or type(manifest.get('size')) is not int):
                return None
            path = self._file(job / _safe_name(manifest.get('file')))
            stamp = self._stamp(path)
            if manifest['size'] != stamp[0] or not 0 < stamp[0] <= MAX_AUDIO_BYTES:
                return None
            if path.suffix.lower() not in _FORMATS:
                return None
            if self._verified.get(path) != stamp:
                self._validate_audio(path)
                self._verified[path] = stamp
            return path
        except (UserError, OSError, ValueError):
            return None

    def _snapshot_locked(self, job_id, job, url):
        state = self._states.get(job_id)
        if state and state['status'] in ('queued', 'downloading'):
            return dict(state)
        if self._cached(job_id, job, url) is not None:
            return self._public(job_id, 'ready')
        if state and state['status'] == 'error':
            return dict(state)
        # lstat sees even a broken symlink, without following it.
        try:
            (job / _MANIFEST).lstat()
            has_manifest = True
        except FileNotFoundError:
            has_manifest = False
        except OSError:
            has_manifest = True
        if has_manifest or (state and state['status'] == 'ready'):
            return self._public(job_id, 'error', '原音缓存缺失或无效，请重新准备原音。')
        return dict(state) if state else self._public(job_id, 'idle')

    def snapshot(self, job_id):
        job, _, url = self._job(job_id)
        with self._condition:
            return self._snapshot_locked(job_id, job, url)

    def media_file(self, job_id):
        job, _, url = self._job(job_id)
        with self._condition:
            state = self._states.get(job_id)
            if state and state['status'] in ('queued', 'downloading'):
                return None
            return self._cached(job_id, job, url)

    def prepare(self, job_id):
        study = self.load_study(job_id)
        job, _, url = self._job(job_id)
        with self._condition:
            if self._closed:
                return self._public(job_id, 'error', '原音准备已关闭，请重启后重试。')
            state = self._snapshot_locked(job_id, job, url)
            if state['status'] in ('queued', 'downloading', 'ready'):
                return state
            if not study['url']:
                state = self._public(job_id, 'error', '此任务没有 YouTube 来源地址，无法准备原音。')
            elif len(self._queue) >= 4:
                state = self._public(job_id, 'error', '原音等待队列已满（最多 4 个），请稍后重试。')
            else:
                state = self._public(job_id, 'queued')
                self._queue.append((job_id, url))
                if self._worker is None:
                    self._worker = threading.Thread(target=self._run, name='shadowing-audio', daemon=True)
                    self._worker.start()
            self._states[job_id] = state
            self._condition.notify_all()
            return dict(state)

    @property
    def busy(self):
        with self._condition:
            return self._active is not None or bool(self._queue)

    def _run(self):
        while True:
            with self._condition:
                self._condition.wait_for(lambda: self._closed or self._queue)
                if self._closed:
                    return
                job_id, url = self._queue.popleft()
                self._active = job_id
                self._states[job_id] = self._public(job_id, 'downloading')
            try:
                self._download(job_id, url)
                state = self._public(job_id, 'ready')
            except Exception as error:
                state = self._public(job_id, 'error', _failure_message(error))
            with self._condition:
                self._states[job_id] = state
                self._active = None
                self._condition.notify_all()

    def _download(self, job_id, url):
        job, _, current_url = self._job(job_id)
        if url != current_url:
            raise _data_error()
        self._confined(job / _MANIFEST)
        work = self._confined(self.root / '.work')
        work.mkdir(exist_ok=True)
        self._confined(work)
        published, created, cached = False, False, None
        with tempfile.TemporaryDirectory(prefix='shadowing-', dir=work) as directory:
            temp = self._confined(Path(directory), work)
            try:
                source = self._confined(Path(self.tools.study_audio(url, temp)), temp)
                self._validate_audio(source)
                cached = self._confined(job / f'shadowing-audio-{uuid.uuid4().hex}{source.suffix.lower()}')
                size = 0
                with source.open('rb') as reader, cached.open('xb') as writer:
                    created = True
                    while block := reader.read(1024 * 1024):
                        size += len(block)
                        if size > MAX_AUDIO_BYTES:
                            raise _audio_error()
                        writer.write(block)
                    writer.flush()
                    os.fsync(writer.fileno())
                self._validate_audio(cached)
                manifest = {'version': 1, 'id': job_id, 'url': url,
                            'file': cached.name, 'size': size}
                staged = temp / 'manifest.json'
                staged.write_text(json.dumps(manifest, ensure_ascii=False), encoding='utf-8')
                # Recheck confinement before publication; never follow an old
                # manifest link or overwrite an existing user audio filename.
                self._confined(cached)
                self._confined(job / _MANIFEST)
                os.replace(staged, job / _MANIFEST)
                published = True
            finally:
                if created and not published:
                    self._confined(cached).unlink(missing_ok=True)

    def close(self):
        """Cancel waiting jobs; finish/join active work. Safe to call repeatedly."""
        with self._condition:
            self._closed = True
            while self._queue:
                job_id, _ = self._queue.popleft()
                self._states[job_id] = self._public(job_id, 'error', '原音准备已关闭，请重启后重试。')
            self._condition.notify_all()
            worker = self._worker
        if worker is not None and worker is not threading.current_thread():
            worker.join()

"""Explicit offline Word export from complete, confined retained study data.

No extraction/translation objects are constructed here. Paths come only from
the trusted application root and validated retained basenames, never clients.
An exclusive per-job lock rejects overlapping exports (also across processes).
After a crash a surviving lock fails closed; it is not automatically removed.
"""

from contextlib import contextmanager
import json
import math
import os
from pathlib import Path
import re
import shutil
import stat
import tempfile

from .service import UserError
from .subtitles import Cue, normalize_youtube_url, render_subtitles, safe_filename


_LIMIT = 64 * 1024 * 1024
_ENGLISH = {'uploaded_caption': '视频上传的英文字幕',
            'platform_auto': 'YouTube 英文自动字幕', 'local_asr': '本地 Whisper 语音识别'}
_INVALID_XML = re.compile('[\x00-\x08\x0b\x0c\x0e-\x1f\ud800-\udfff\ufffe\uffff]')


def _data_error():
    return UserError('study_data', '中英学习数据缺失或损坏，无法保证全文与来源完整；请重新提取字幕。')


def _path_error():
    return UserError('study_path', '学习文件路径无效或包含链接，无法安全导出。')


def _text(value):
    if not isinstance(value, str) or not value.strip() or _INVALID_XML.search(value):
        raise _data_error()
    return value


def _times(value):
    if not isinstance(value, dict):
        raise _data_error()
    start, end = value.get('start'), value.get('end')
    try:
        valid = (type(start) in (int, float) and type(end) in (int, float)
                 and math.isfinite(start) and math.isfinite(end) and start >= 0 and end > start)
    except OverflowError:
        valid = False
    if not valid:
        raise _data_error()
    return start, end


def _safe_name(value):
    if (not isinstance(value, str) or not value or value in ('.', '..') or value[-1] in ' .'
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


def _invalid_constant(value):
    raise _data_error()


def _finite_float(value):
    number = float(value)
    if not math.isfinite(number):
        raise _data_error()
    return number


class _Retained:
    def __init__(self, root, job_id):
        # abspath normalizes '..' without following a symlink/junction first.
        self.root = Path(os.path.abspath(root))
        self.job = self.root / 'results' / job_id
        self.checked(self.job)
        if not self.job.is_dir():
            raise _data_error()

    def checked(self, path):
        """lstat every component, including root ancestors; never resolve first."""
        try:
            path.relative_to(self.root)
            current = Path(path.anchor)
            for part in path.parts[1:]:
                current /= part
                try:
                    info = current.lstat()
                except FileNotFoundError:
                    continue
                if (stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0)
                        & getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0x400)):
                    raise _path_error()
            path.resolve().relative_to(self.root.resolve())
        except (OSError, ValueError, RuntimeError):
            raise _path_error() from None
        return path

    def file(self, path):
        self.checked(path)
        try:
            info = path.lstat()
            if not stat.S_ISREG(info.st_mode):
                raise _path_error()
        except FileNotFoundError:
            raise _data_error() from None
        return path

    def work(self):
        path = self.checked(self.root / '.work' / 'tmp')
        path.mkdir(parents=True, exist_ok=True)
        return self.checked(path)

    def content(self, name):
        path = self.file(self.job / name)
        try:
            with path.open('rb') as stream:
                before = os.fstat(stream.fileno())
                raw = stream.read(_LIMIT + 1)
                after = os.fstat(stream.fileno())
            if len(raw) > _LIMIT:
                raise _data_error()
            self.file(path)
            # Windows Python 3.12 fstat/lstat disagree on legacy st_ctime;
            # device/inode/size/mtime identify the same unchanged file.
            stamp = lambda info: (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)
            if stamp(before) != stamp(after) or stamp(after) != stamp(path.lstat()):
                raise _data_error()
            return raw.decode('utf-8-sig')
        except (OSError, UnicodeError):
            raise _data_error() from None

    def read(self, name):
        try:
            return json.loads(self.content(name), object_pairs_hook=_unique_object,
                              parse_constant=_invalid_constant, parse_float=_finite_float)
        except (OSError, ValueError, UnicodeError, RecursionError):
            raise _data_error() from None

    @contextmanager
    def locked(self):
        lock = self.checked(self.job / '.study-word.lock')
        try:
            handle = lock.open('xb')
        except FileExistsError:
            raise UserError('busy', '此任务正在导出 Word，请等待完成后重试。') from None
        identity = os.fstat(handle.fileno())
        try:
            yield
        finally:
            handle.close()
            self.remove_owned(lock, identity)

    def remove_owned(self, path, identity):
        """Cleanup only our own unchanged temporary file; never unlink a link."""
        try:
            self.checked(path)
            now = path.lstat()
            if (now.st_dev, now.st_ino) == (identity.st_dev, identity.st_ino):
                path.unlink()
        except (OSError, UserError):
            pass

    def load(self, job_id):
        result = self.read('metadata.json')
        if (not isinstance(result, dict) or result.get('id') != job_id
                or result.get('language') != 'en' or not isinstance(result.get('source'), str)
                or result['source'] not in _ENGLISH
                or not isinstance(result.get('files'), dict)):
            raise _data_error()
        _text(result.get('title'))
        _text(result.get('warning'))
        if result['source'] == 'local_asr' and result.get('model') not in ('tiny', 'base', 'small'):
            raise _data_error()
        try:
            url = normalize_youtube_url(_text(result.get('url')))
        except ValueError:
            raise _data_error() from None
        for extension, name in result['files'].items():
            if extension not in ('srt', 'vtt', 'txt', 'docx'):
                raise _path_error()
            _safe_name(name)
            if Path(name).suffix.lower() != '.' + extension:
                raise _path_error()
            self.file(self.job / name)
        if not {'srt', 'vtt', 'txt'}.issubset(result['files']):
            raise _data_error()
        # Never use output_dir or desktop_path from disk as a write target.
        result['output_dir'] = str(self.job.resolve())
        result['url'] = url
        if result.get('sentence_version') == 1:
            from .sentence_study import load_sentence_data
            data=load_sentence_data(self.root,job_id)
            blocks=data['cues'];note=data['chinese_note']
            english_note=_ENGLISH[result['source']]+'；'+result['warning']
            return result,blocks,note,english_note
        cues = self.read('study-cues.json')
        stored = self.read('bilingual.json')
        if (not isinstance(cues, list) or not cues or type(result.get('count')) is not int
                or result['count'] != len(cues) or not isinstance(stored, dict)
                or not isinstance(stored.get('blocks'), list) or not stored['blocks']):
            raise _data_error()
        blocks = stored['blocks']
        if type(result.get('bilingual_count')) is not int or result['bilingual_count'] != len(blocks):
            raise _data_error()
        note = _text(stored.get('chinese_source'))
        if note != _text(result.get('chinese_source')):
            raise _data_error()
        for cue in cues:
            _times(cue)
            _text(cue.get('text'))
        # An independently retained source export prevents mutually truncated
        # JSON stores/counts from looking complete. Preserve sub-ms timestamps
        # in study-cues; compare their canonical millisecond SRT representation.
        try:
            expected_srt = render_subtitles([Cue(cue['start'], cue['end'], cue['text']) for cue in cues], 'srt')
        except (ValueError, OverflowError):
            raise _data_error() from None
        if self.content(result['files']['srt']).replace('\r\n', '\n') != expected_srt:
            raise _data_error()
        self.coverage(cues, blocks)
        english_note = _ENGLISH[result['source']]
        if result['source'] == 'local_asr':
            english_note += f'（{result["model"]} 模型）'
        english_note += '；' + result['warning']
        return result, blocks, note, english_note

    @staticmethod
    def coverage(cues, blocks):
        """Match whole chronological cue groups, not a preview or just counts.

        Each block must contain exactly the next source cue(s), unchanged and
        once only, with their exact enclosing time range. Overlapping cues are
        legitimate; a group ends when its English text is fully accounted for.
        """
        cues = sorted(cues, key=lambda cue: (cue['start'], cue['end']))
        cursor = 0
        for block in blocks:
            start, end = _times(block)
            english = _text(block.get('english'))
            _text(block.get('chinese'))
            if cursor >= len(cues) or start != cues[cursor]['start']:
                raise _data_error()
            parts, length, furthest = [], 0, -1
            while cursor < len(cues) and length < len(english):
                cue = cues[cursor]
                parts.append(cue['text'])
                length += len(cue['text']) + (1 if len(parts) > 1 else 0)
                furthest = max(furthest, cue['end'])
                cursor += 1
            if ' '.join(parts) != english or end != furthest:
                raise _data_error()
        if cursor != len(cues):
            raise _data_error()

    def publish_metadata(self, result):
        target = self.file(self.job / 'metadata.json')
        staged = None
        try:
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=self.work(),
                                             prefix='.study-metadata-', suffix='.tmp', delete=False) as output:
                staged = Path(output.name)
                identity = os.fstat(output.fileno())
                json.dump(result, output, ensure_ascii=False, indent=2, allow_nan=False)
                output.flush()
                os.fsync(output.fileno())
            self.file(staged)
            self.file(target)
            os.replace(staged, target)
        finally:
            if staged is not None:
                self.remove_owned(staged, identity)


def _write_local(store, result, blocks, note, english_note, writer):
    # Give the existing writer its own staging directory: its atomic replace
    # must never target an existing user-owned retained file.
    store.checked(store.job)
    with tempfile.TemporaryDirectory(prefix='study-word-', dir=store.work()) as directory:
        staged = Path(directory) / 'document.docx'
        store.checked(staged)
        try:
            writer(staged, result['title'], result['url'], blocks, note, english_note)
            store.file(staged)
            if not staged.stat().st_size:
                raise ValueError('Empty Word output')
        except (OSError, RuntimeError, ValueError):
            raise UserError('word', 'Word 文档生成失败；完整中英学习数据已保留，请稍后重试。') from None
        filename = _safe_name(safe_filename(result['title']) + ' 中英对照.docx')
        stem = Path(filename).stem
        number = 0
        while True:
            suffix = f' ({number})' if number else ''
            candidate = store.checked(store.job / f'{stem}{suffix}.docx')
            try:
                output = candidate.open('xb')
            except FileExistsError:
                number += 1
                continue
            identity = os.fstat(output.fileno())
            try:
                with output, store.file(staged).open('rb') as source:
                    shutil.copyfileobj(source, output)
            except BaseException:
                store.remove_owned(candidate, identity)
                raise
            return candidate


def export_study_word(root, job_id, *, word_writer=None, desktop_dir=None):
    """Return updated persisted result after explicit offline Word/Desktop save.

    root/desktop_dir are trusted application settings (desktop_dir is primarily
    for tests). Callers pass only a retained job ID, never a client output path.
    Error codes: study_data/study_path, busy, word, desktop_save, study_metadata.
    Metadata changes only after both copies succeed; failures preserve data and
    completed copies. The HTTP owner must update its jobs snapshot under lock.
    """
    if not isinstance(job_id, str) or not re.fullmatch(r'[a-f0-9]{32}', job_id):
        raise ValueError('任务编号无效。')
    store = _Retained(root, job_id)
    with store.locked():
        result, blocks, note, english_note = store.load(job_id)
        from .word_document import write_word_document, save_to_desktop
        try:
            local = _write_local(store, result, blocks, note, english_note, word_writer or write_word_document)
        except OSError:
            raise UserError('word', 'Word 本地保存失败；完整中英学习数据已保留。') from None
        try:
            saved = save_to_desktop(store.file(local), desktop_dir)
        except OSError:
            raise UserError('desktop_save', 'Word 已生成，但桌面保存失败；本地文档与学习数据已保留。') from None
        result['files']['docx'] = local.name
        result['desktop_path'] = str(saved)
        result['bilingual_count'] = len(blocks)
        result['bilingual_preview'] = blocks[:200]
        if result.get('sentence_version')==1:result['word_sentence_version']=1
        try:
            store.publish_metadata(result)
        except (OSError, ValueError):
            raise UserError('study_metadata', 'Word 已保存，但任务记录更新失败；原学习数据与文档均已保留，请重试。') from None
        return result

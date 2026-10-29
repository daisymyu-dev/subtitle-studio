"""Extraction, local ASR, provenance and sequential background jobs."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from datetime import datetime, timezone
from functools import lru_cache
import importlib.util
import json
import logging
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen
import uuid

from .subtitles import Cue, choose_track, clean_cues, normalize_youtube_url, parse_subtitles, render_subtitles, safe_filename


class UserError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def validate_options(options):
    if not isinstance(options, dict):
        raise ValueError('设置格式不正确。')
    result = {'mode': 'auto', 'language': 'auto', 'asr_language': 'auto', 'model': 'base'}
    result.update({key: options[key] for key in result if key in options})
    allowed = {'mode': ('auto', 'captions', 'asr'), 'model': ('tiny', 'base', 'small'),
               'language': ('auto', 'en', 'zh', 'ja', 'es', 'fr', 'de'),
               'asr_language': ('auto', 'en', 'zh', 'ja', 'es', 'fr', 'de')}
    if any(value not in allowed[key] for key, value in result.items()):
        raise ValueError('请选择有效的处理模式、语言和模型。')
    result['bilingual_word'] = options.get('bilingual_word', False)
    if type(result['bilingual_word']) is not bool:
        raise ValueError('Word 导出设置必须是明确的开关。')
    result['bilingual_study'] = options.get('bilingual_study', False)
    if type(result['bilingual_study']) is not bool:
        raise ValueError('中英学习设置必须是明确的开关。')
    result['sentence_study'] = options.get('sentence_study', False)
    if type(result['sentence_study']) is not bool:
        raise ValueError('逐句学习设置必须是明确的开关。')
    if result['sentence_study'] and not (result['bilingual_study'] or result['bilingual_word']):
        raise ValueError('逐句模式需要明确启用中英学习或 Word。')
    return result


def _process_error(message):
    lower = str(message).lower()
    if any(word in lower for word in ('sign in', 'login', 'cookies', 'confirm you', 'age-restricted', 'private video', 'members-only')):
        return UserError('access', 'YouTube 要求登录、验证或访问权限。这不是“没有字幕”。本工具不自动读取 Cookies；可改用你有权使用的本地文件。')
    if '429' in lower or 'too many requests' in lower:
        return UserError('rate_limit', 'YouTube 暂时限制了请求（429）。请稍后重试，不代表视频没有字幕。')
    if any(word in lower for word in ('getaddrinfo', 'timed out', 'resolve', 'connection', 'network', 'certificate')):
        return UserError('network', '网络连接或证书校验失败。请检查本机是否能访问 YouTube，再重试；这不是“没有字幕”。')
    if any(word in lower for word in ('unavailable', 'removed', 'not available', 'video does not exist')):
        return UserError('unavailable', '视频当前不可访问，可能已删除、设为私密或存在地区限制。')
    return UserError('extractor', 'yt-dlp 未能完成读取。请稍后重试或更新项目内的 yt-dlp；也可以使用本地文件。')


class NativeTools:
    def __init__(self, root):
        self.root = Path(root)

    def command(self):
        frozen = getattr(sys, 'frozen', False)
        if frozen:
            command = [sys.executable, '--internal-ytdlp']
        elif importlib.util.find_spec('yt_dlp'):
            command = [sys.executable, '-m', 'yt_dlp']
        else:
            executable = shutil.which('yt-dlp') or str(Path.home() / '.local/bin/yt-dlp.exe')
            if not Path(executable).is_file():
                raise UserError('dependency', '未找到 yt-dlp。请先安装项目依赖。')
            command = [executable]
        command += ['--ignore-config', '--no-cache-dir', '--no-playlist',
                    '--socket-timeout', '25', '--retries', '1', '--extractor-retries', '1']
        if frozen:
            from .runtime import asset_root
            node = asset_root() / 'runtime' / 'node.exe'
            # Do not implicitly discover Deno/Node on a user's PATH.
            command += ['--no-js-runtimes']
        else:
            node = shutil.which('node') or r'C:\Program Files\nodejs\node.exe'
        if Path(node).is_file():
            command += ['--js-runtimes', f'node:{node}']
        return command

    def _run(self, arguments, timeout, check_captions=False):
        env = dict(os.environ, PYTHONIOENCODING='utf-8', PYTHONUTF8='1')
        try:
            result = subprocess.run(self.command() + arguments, capture_output=True, text=True,
                                    encoding='utf-8', errors='replace', timeout=timeout, env=env,
                                    creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        except subprocess.TimeoutExpired:
            raise UserError('timeout', 'YouTube 读取超时，请检查网络后重试，或改用本地文件。') from None
        except OSError:
            raise UserError('dependency', '无法启动 yt-dlp，请检查本地安装。') from None
        if result.returncode:
            raise _process_error(result.stderr)
        warning = result.stderr.lower()
        if (check_captions and any(word in warning for word in ('caption', 'subtitle'))
                and any(word in warning for word in ('skipping', 'failed', 'unable', 'missing', 'token'))):
            raise UserError('caption_discovery', 'yt-dlp 警告字幕查询不完整，不能认定视频没有字幕。请重试或手动选择语音识别。')
        return result.stdout

    def metadata(self, url, check_captions=True):
        try:
            return json.loads(self._run(['--skip-download', '--dump-single-json', url], 150, check_captions=check_captions))
        except json.JSONDecodeError:
            raise UserError('metadata', 'yt-dlp 返回了无法解析的视频信息，请重试。') from None

    def caption(self, track):
        url = track['url']
        parsed = urlparse(url)
        host = parsed.hostname or ''
        if (parsed.scheme != 'https' or parsed.username or parsed.port not in (None, 443)
                or not any(host == domain or host.endswith('.' + domain)
                           for domain in ('youtube.com', 'googlevideo.com'))):
            raise UserError('caption_url', '字幕服务返回了不受支持的地址。')
        try:
            request = Request(url, headers={'User-Agent': 'Mozilla/5.0', 'Accept': '*/*'})
            with urlopen(request, timeout=35) as response:
                raw = response.read(20 * 1024 * 1024 + 1)
            if len(raw) > 20 * 1024 * 1024:
                raise UserError('caption_size', '字幕文件过大，超过本工具的 20 MiB 限制。')
            return raw.decode('utf-8-sig')
        except HTTPError as error:
            raise UserError('caption_fetch', f'字幕请求失败（HTTP {error.code}），不是没有字幕。请稍后重试，或手动切换到语音识别模式。') from None
        except (URLError, TimeoutError, UnicodeError):
            raise UserError('caption_fetch', '字幕正文读取失败，不是没有字幕。请检查网络或手动选择语音识别模式。') from None

    def audio(self, url, folder):
        self._run(['--no-progress', '--quiet', '--no-part', '--no-continue',
                   '--max-filesize', '500M', '-f', 'bestaudio/best',
                   '-o', str(folder / 'audio.%(ext)s'), url], 1800)
        files = [path for path in folder.glob('audio.*') if path.is_file()]
        if not files:
            raise UserError('audio', '没有下载到可用音频，可能超过 500 MiB 或音轨受限。')
        return files[0]

    def study_audio(self, url, folder):
        """Explicit original-audio preparation; never a synthesized replacement."""
        self._run(['--no-progress', '--quiet', '--no-part', '--no-continue',
                   '--max-filesize', '500M', '-f', 'bestaudio[ext=m4a]/bestaudio[ext=webm]',
                   '-o', str(folder / 'audio.%(ext)s'), normalize_youtube_url(url)], 1800)
        files = [path for path in folder.glob('audio.*') if path.is_file() and path.suffix in ('.m4a', '.webm')]
        if len(files) != 1:
            raise UserError('original_audio', '没有取得可播放的原音。音轨可能受限或超过 500 MiB；不会用合成语音替代。')
        return files[0]


@lru_cache(maxsize=1)
def _load_model(name):
    from faster_whisper import WhisperModel
    return WhisperModel(name, device='cpu', compute_type='int8', cpu_threads=max(1, min(8, (os.cpu_count() or 2) - 1)))


def transcribe_media(path, options, report):
    report('model', '正在加载本地语音模型；未缓存时需联网下载，音频不会上传。')
    try:
        model = _load_model(options['model'])
    except ImportError:
        raise UserError('dependency', '本地听写依赖未安装；Windows Core 便携版不包含听写。请改用已有字幕，或按 docs/build.md 安装源码版的 requirements-asr.txt。') from None
    except Exception:
        raise UserError('model', '语音模型加载失败。首次使用需联网下载；已缓存时请检查模型文件和本机运行库。') from None
    try:
        language = None if options['asr_language'] == 'auto' else options['asr_language']
        segments, info = model.transcribe(str(path), language=language, beam_size=5,
                                          vad_filter=True, condition_on_previous_text=False)
        report('recognizing', '正在本地识别语音。', processed=0, duration=info.duration)
        cues = []
        for segment in segments:
            cues.append(Cue(segment.start, segment.end, segment.text))
            report('recognizing', '正在本地识别语音。', processed=min(segment.end, info.duration), duration=info.duration)
        return clean_cues(cues, duration=info.duration), {'language': info.language, 'duration': info.duration}
    except Exception:
        raise UserError('recognition', '音频解码或识别失败。请确认文件可以正常播放，并尝试 WAV、MP3 或 MP4。') from None


class Pipeline:
    def __init__(self, root, tools=None, transcriber=None, *, translator=None, word_writer=None, desktop_dir=None):
        self.root = Path(root)
        self.tools = tools or NativeTools(root)
        self.transcriber = transcriber or transcribe_media
        self.translator = translator
        self.word_writer = word_writer
        self.desktop_dir = desktop_dir
        (self.root / '.work').mkdir(parents=True, exist_ok=True)
        (self.root / 'results').mkdir(parents=True, exist_ok=True)

    def process(self, source_type, value, options, report=lambda *args, **kwargs: None, job_id=None):
        options = validate_options(options)
        bilingual = options['bilingual_word'] or options['bilingual_study']
        if bilingual:
            if source_type != 'youtube':
                raise ValueError('一键中英 Word 当前仅支持单条英文 YouTube 视频。')
            options.update(language='en', asr_language='auto')
        job_id = job_id or uuid.uuid4().hex
        if not isinstance(job_id, str) or not __import__('re').fullmatch(r'[a-f0-9]{32}', job_id):
            raise ValueError('任务编号无效。')
        cues = None
        source_url = None
        detected = {}
        with tempfile.TemporaryDirectory(prefix='job-', dir=self.root / '.work') as directory:
            work = Path(directory)
            if source_type == 'youtube':
                source_url = normalize_youtube_url(value)
                report('metadata', '正在用 yt-dlp 查询视频和原始语言字幕。')
                info = self.tools.metadata(source_url, check_captions=options['mode'] != 'asr')
                title = info.get('title') or 'YouTube video'
                if info.get('is_live'):
                    raise UserError('live', '第一版不处理正在直播的视频，请等待直播结束。')
                detected = {'language': info.get('language'), 'duration': info.get('duration')}
                track = None if options['mode'] == 'asr' else choose_track(info, options['language'])
                if track:
                    report('captions', '找到字幕，正在读取正文与时间轴。')
                    try:
                        cues = parse_subtitles(self.tools.caption(track), track['ext'], strict=bilingual)
                    except (ValueError, KeyError, TypeError):
                        raise UserError('caption_parse', '字幕正文格式无法解析。这不是“没有字幕”，请重试或手动选择语音识别。') from None
                    if not cues:
                        raise UserError('caption_parse', '选中的字幕没有有效时间轴或返回了空正文，不能认定没有字幕。请重试或手动选择语音识别。')
                    if cues:
                        source = track['kind']
                        detected['language'] = track['code'].split('-')[0]
                        cues = clean_cues(cues, rolling=source == 'platform_auto')
                if not cues:
                    if options['mode'] == 'captions':
                        raise UserError('no_captions', '没有找到所选语言的可用原始字幕。可选择“自动”或“语音识别”；本工具不会用自动翻译冒充原文。')
                    report('audio', '没有合适字幕，正在获取音频。' if options['mode'] == 'auto' else '已选择语音识别，正在获取音频。')
                    path = self.tools.audio(source_url, work)
                    cues, detected = self.transcriber(path, options, report)
                    source = 'local_asr'
            elif source_type == 'file':
                path = Path(value)
                title = path.stem
                if path.suffix.lower() in ('.vtt', '.srt'):
                    report('captions', '正在导入本地字幕，不改写原文。')
                    try:
                        cues = parse_subtitles(path.read_text(encoding='utf-8-sig'), path.suffix[1:].lower())
                    except (ValueError, UnicodeError):
                        raise UserError('caption_parse', '请使用 UTF-8 编码的 SRT 或 VTT 字幕文件。') from None
                    source = 'local_caption'
                else:
                    cues, detected = self.transcriber(path, options, report)
                    source = 'local_asr'
            else:
                raise ValueError('无效的输入类型。')
            cues = clean_cues(cues or [], duration=detected.get('duration') if source == 'local_asr' else None)
            if not cues:
                raise UserError('empty', '未得到有效字幕。音频可能静音、没有可识别语音，或字幕格式不受支持。')
            if bilingual and source == 'local_asr' and detected.get('language') != 'en':
                raise UserError('english_required', '识别到音频不是英文。本按钮用于英文原文与中文对照，不会把其他语言冒充英文；可使用普通字幕整理。')
            report('exporting', '正在生成 SRT、VTT 和 TXT。')
            destination = self.root / 'results' / job_id
            destination.mkdir(exist_ok=False)
            (destination / 'study-cues.json').write_text(json.dumps([asdict(cue) for cue in cues], ensure_ascii=False), encoding='utf-8')
            filename = safe_filename(title)
            files = {}
            for ext in ('srt', 'vtt', 'txt'):
                files[ext] = f'{filename}.{ext}'
                (destination / files[ext]).write_text(render_subtitles(cues, ext), encoding='utf-8', newline='\n')
            result = {'id': job_id, 'title': title, 'source': source, 'url': source_url,
                      'language': detected.get('language'), 'duration': detected.get('duration'),
                      'model': options['model'] if source == 'local_asr' else None,
                      'created_at': datetime.now(timezone.utc).isoformat(), 'count': len(cues),
                      'files': files, 'output_dir': str(destination.resolve()),
                      'preview': [asdict(cue) for cue in cues[:200]],
                      'warning': '语音识别可能误听人名、数字与专业词，请对照音频复核。' if source == 'local_asr' else '保留字幕内容；上传字幕也可能存在错漏。'}
            if options['sentence_study']:
                from .sentence_study import prepare_sentences
                (destination / 'metadata.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
                result=prepare_sentences(self.root,job_id,translator=self.translator,report=report)
                if options['bilingual_word']:
                    from .study_export import export_study_word
                    result=export_study_word(self.root,job_id,word_writer=self.word_writer,desktop_dir=self.desktop_dir)
            elif options['bilingual_word']:
                self._export_word(result, cues, info, destination, report)
            elif options['bilingual_study']:
                blocks, _ = self._prepare_bilingual(result, cues, info, destination, report)
                result['bilingual_count'] = len(blocks)
                result['bilingual_preview'] = blocks[:200]
                result['warning'] += ' 中文为对照学习材料，可能存在错译，尤其需复核人名、数字和专业术语。'
            (destination / 'metadata.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
            return result

    def _prepare_bilingual(self, result, cues, info, destination, report):
        """One complete English/Chinese workflow, without Word or Desktop writes."""
        from .bilingual import GoogleWebTranslator, TranslationError, align_captions, choose_chinese_track, complete_chinese
        track = choose_chinese_track(info)
        chinese = []
        note = ''
        labels = {'uploaded_chinese': '视频上传的中文字幕（未逐字校对）',
                  'auto_chinese': 'YouTube 中文自动字幕',
                  'youtube_translation': 'YouTube 自动翻译中文字幕'}
        if track:
            report('chinese', '正在读取现有中文字幕并按时间轴对齐。')
            try:
                chinese = clean_cues(parse_subtitles(self.tools.caption(track), track['ext'], strict=True),
                                     rolling=track['kind'] != 'uploaded_chinese')
                if chinese:
                    note = labels[track['kind']]
            except (UserError, ValueError, KeyError, TypeError):
                result['warning'] += ' 中文字幕未能读取，改用在线文字翻译。'
        blocks = align_captions(cues, chinese)
        if not any(block['chinese'] for block in blocks):
            note = ''
        report('translating', '正在补齐中文译文；仅发送缺失部分的英文字幕文字，不上传音视频。')
        try:
            translated = complete_chinese(blocks, self.translator or GoogleWebTranslator(),
                lambda done, total: report('translating', f'正在在线翻译字幕：{done} / {total} 段。', translated=done, translation_total=total))
        except TranslationError as error:
            raise UserError('translation', str(error)) from None
        if translated:
            note = (note + '；缺失部分使用 ' if note else '') + 'Google 网页机器翻译（非官方通路，需复核）'
        result['chinese_source'] = note
        (destination / 'bilingual.json').write_text(json.dumps({'blocks': blocks, 'chinese_source': note}, ensure_ascii=False, indent=2), encoding='utf-8')
        return blocks, note

    def _export_word(self, result, cues, info, destination, report):
        from .word_document import write_word_document, save_to_desktop
        blocks, note = self._prepare_bilingual(result, cues, info, destination, report)
        report('word', '中英对照已齐全，正在排版 Word 文档。')
        filename = safe_filename(result['title']) + ' 中英对照.docx'
        path = destination / filename
        english_note = {'uploaded_caption': '视频上传的英文字幕', 'platform_auto': 'YouTube 英文自动字幕',
                        'local_asr': f'本地 Whisper 语音识别（{result["model"]} 模型）'}.get(result['source'], result['source'])
        english_note += '；' + result['warning']
        try:
            (self.word_writer or write_word_document)(path, result['title'], result['url'], blocks, note, english_note)
        except (OSError, RuntimeError, ValueError):
            raise UserError('word', 'Word 文档生成失败；英文字幕保留在 results 文件夹，请检查本地文档运行库。') from None
        report('desktop', '正在将完整 Word 保存到桌面；同名文件会自动编号。')
        try:
            saved = save_to_desktop(path, self.desktop_dir)
        except OSError:
            raise UserError('desktop_save', f'Word 已生成，但桌面保存失败。请检查权限或文件占用；文件保留在 {path}。') from None
        result['files']['docx'] = filename
        result['desktop_path'] = str(saved)
        result['bilingual_count'] = len(blocks)
        result['bilingual_preview'] = blocks[:200]
        result['warning'] += ' 中文为对照学习材料，可能存在错译，尤其需复核人名、数字和专业术语。'


class JobManager:
    def __init__(self, pipeline):
        self.pipeline = pipeline
        self.jobs = {}
        self.lock = threading.Lock()
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='subtitle-job')

    def submit(self, source_type, value, options, cleanup=None):
        options = validate_options(options)
        if source_type == 'youtube':
            value = normalize_youtube_url(value)
        with self.lock:
            if sum(job['status'] in ('queued', 'running') for job in self.jobs.values()) >= 8:
                raise UserError('busy', '队列已满，请等待现有任务完成。')
            job_id = uuid.uuid4().hex
            self.jobs[job_id] = {'id': job_id, 'status': 'queued', 'stage': 'queued',
                                 'message': '等待处理。', 'events': []}
        self.executor.submit(self._run, job_id, source_type, value, options, cleanup)
        return job_id

    def _run(self, job_id, source_type, value, options, cleanup):
        def report(stage, message, **extra):
            with self.lock:
                job = self.jobs[job_id]
                job.update(status='running', stage=stage, message=message, **extra)
                if not job['events'] or job['events'][-1]['stage'] != stage:
                    job['events'].append({'stage': stage, 'message': message})
        try:
            result = self.pipeline.process(source_type, value, options, report, job_id)
            with self.lock:
                message = '中英 Word 已保存到桌面。' if result.get('desktop_path') else '字幕已整理完成。'
                self.jobs[job_id].update(status='done', stage='done', message=message, result=result)
        except (UserError, ValueError) as error:
            with self.lock:
                self.jobs[job_id].update(status='error', stage='error', message=str(error),
                                         error_code=getattr(error, 'code', 'input'))
        except Exception:
            logging.exception('Job %s failed', job_id)
            with self.lock:
                self.jobs[job_id].update(status='error', stage='error',
                                         message='处理出现意外错误，请重试。启动日志已记录错误类型。', error_code='internal')
        finally:
            if cleanup:
                try:
                    cleanup()
                except OSError:
                    logging.warning('Could not remove temporary upload for %s', job_id)

    def snapshot(self, job_id):
        with self.lock:
            job = self.jobs.get(job_id)
            return json.loads(json.dumps(job, ensure_ascii=False)) if job else None

    def close(self):
        self.executor.shutdown(wait=True)

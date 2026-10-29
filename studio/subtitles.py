"""Pure subtitle transformations. No network, subprocesses, or translation."""

from dataclasses import dataclass
import html
import json
import math
import re
from urllib.parse import parse_qs, urlparse


@dataclass(frozen=True)
class Cue:
    start: float
    end: float
    text: str


def normalize_youtube_url(value):
    try:
        url = urlparse(str(value).strip())
        if (url.scheme not in ('http', 'https') or url.username or url.password
                or url.port not in (None, 80, 443)):
            raise ValueError
        host = (url.hostname or '').lower()
        parts = url.path.strip('/').split('/')
        if host in ('youtu.be', 'www.youtu.be'):
            video_id = parts[0]
        elif host in ('youtube.com', 'www.youtube.com', 'm.youtube.com', 'music.youtube.com'):
            if url.path == '/watch':
                video_id = parse_qs(url.query).get('v', [''])[0]
            elif len(parts) == 2 and parts[0] in ('shorts', 'live', 'embed'):
                video_id = parts[1]
            else:
                raise ValueError
        else:
            raise ValueError
        if not re.fullmatch(r'[A-Za-z0-9_-]{11}', video_id):
            raise ValueError
    except (ValueError, TypeError):
        raise ValueError('请填写单个 YouTube 视频链接，不支持频道、播放列表或其他网站。') from None
    return f'https://www.youtube.com/watch?v={video_id}'


def _base_language(code):
    return str(code).lower().split('-')[0]


def _translated(track):
    return ('tlang' in parse_qs(urlparse(track.get('url', '')).query)
            or ' from ' in track.get('name', '').lower())


def choose_track(info, language='auto'):
    """Prefer source-language uploaded captions, never automatic translations."""
    desired = (info.get('original_language') or info.get('language')) if language == 'auto' else language
    if not desired:
        originals = {_base_language(code) for code in (info.get('automatic_captions') or {}) if code.endswith('-orig')}
        if len(originals) == 1:
            desired = originals.pop()
    if not desired:
        languages = set()
        for field in ('subtitles', 'automatic_captions'):
            for code, formats in (info.get(field) or {}).items():
                if code != 'live_chat' and any(
                    track.get('ext') in ('json3', 'vtt', 'srt') and track.get('url')
                    and not (field == 'automatic_captions' and _translated(track)) for track in formats
                ):
                    languages.add(_base_language(code))
        if len(languages) != 1:
            return None  # Original language is ambiguous; never choose by insertion order.
        desired = languages.pop()
    desired = _base_language(desired) if desired else None
    candidates = []
    for field, kind in [('subtitles', 'uploaded_caption'), ('automatic_captions', 'platform_auto')]:
        for code, formats in (info.get(field) or {}).items():
            if code == 'live_chat' or (desired and _base_language(code) != desired):
                continue
            for track in formats:
                ext = track.get('ext')
                if ext not in ('json3', 'vtt', 'srt') or not track.get('url'):
                    continue
                if kind == 'platform_auto' and _translated(track):
                    continue
                rank = (0 if kind == 'uploaded_caption' else 1,
                        0 if code.endswith('-orig') else 1,
                        {'json3': 0, 'vtt': 1, 'srt': 2}[ext])
                candidates.append((rank, dict(track, code=code, kind=kind)))
    return min(candidates, key=lambda item: item[0])[1] if candidates else None


def _clean_text(text):
    return ' '.join(str(text).split())


def _decode_markup(text):
    # Decode exactly once. Literal &lt;name&gt; must not disappear on revalidation.
    markup = r'</?(?:b|i|u|c(?:\.[\w-]+)*|v|lang|ruby|rt)(?:\s+[^>]*)?>|<(?:\d+:)?\d{2}:\d{2}\.\d{3}>'
    return html.unescape(re.sub(markup, '', text, flags=re.IGNORECASE))


def _seconds(value):
    parts = value.replace(',', '.').split(':')
    return sum(float(part) * 60 ** i for i, part in enumerate(reversed(parts)))


def parse_subtitles(text, ext, *, strict=False):
    cues = []
    if ext == 'json3':
        for event in json.loads(text).get('events', []):
            content = ''.join(seg.get('utf8', '') for seg in event.get('segs', []))
            if strict and content.strip() and ('tStartMs' not in event or 'dDurationMs' not in event):
                raise ValueError('非空字幕缺少完整时间轴，不能保证导出全文。')
            start = float(event.get('tStartMs', 0)) / 1000
            end = start + float(event.get('dDurationMs', 0)) / 1000
            cues.append(Cue(start, end, content))
    elif ext in ('vtt', 'srt'):
        timing = re.compile(r'((?:\d+:)?\d{2}:\d{2}[.,]\d{3})\s+-->\s+((?:\d+:)?\d{2}:\d{2}[.,]\d{3})')
        for block in re.split(r'\n\s*\n', text.lstrip('\ufeff').replace('\r\n', '\n')):
            if block.lstrip().startswith(('NOTE', 'STYLE', 'REGION')):
                continue
            lines = block.splitlines()
            found = False
            for index, line in enumerate(lines):
                match = timing.search(line)
                if strict and '-->' in line and not match:
                    raise ValueError('字幕存在无法解析的时间轴，不能跳过后导出。')
                if match:
                    if strict and line[:match.start()].strip():
                        raise ValueError('字幕时间轴格式不正确。')
                    cues.append(Cue(_seconds(match[1]), _seconds(match[2]), _decode_markup(' '.join(lines[index + 1:]))))
                    found = True
                    break
            if strict and not found and block.strip() and not block.lstrip().startswith('WEBVTT'):
                raise ValueError('字幕存在没有时间轴的非空段，不能跳过后导出。')
    else:
        raise ValueError('仅支持 SRT、VTT 和 JSON3 字幕。')
    if strict and any(cue.text.strip() and (not math.isfinite(cue.start) or not math.isfinite(cue.end)
                       or cue.start < 0 or cue.end <= cue.start) for cue in cues):
        raise ValueError('字幕存在无效的非空时间段，不能保证导出全文。')
    return clean_cues(cues)


def _rolling_suffix(old, new):
    unspaced = bool(re.search(r'[\u2e80-\u9fff\u3040-\u30ff]', old + new)) and ' ' not in old + new
    if old == new:
        return '', '' if unspaced else ' '
    if new.startswith(old) and (unspaced or new[len(old):].startswith(' ')):
        return new[len(old):].strip(), '' if unspaced else ' '
    if unspaced:
        overlap = next((n for n in range(min(len(old), len(new)), 1, -1) if old[-n:] == new[:n]), 0)
        return (new[overlap:], '') if overlap else (None, '')
    before, after = old.split(), new.split()
    overlap = next((n for n in range(min(len(before), len(after)), 1, -1) if before[-n:] == after[:n]), 0)
    return (' '.join(after[overlap:]), ' ') if overlap else (None, ' ')


def clean_cues(cues, rolling=False, duration=None):
    result = []
    previous_raw = None
    for cue in cues:
        text = _clean_text(cue.text)
        if (not text or not math.isfinite(cue.start) or not math.isfinite(cue.end)
                or cue.end <= cue.start):
            continue
        end = min(cue.end, duration) if duration is not None else cue.end
        current = Cue(max(0.0, cue.start), end, text)
        if current.end <= current.start:
            continue
        if rolling and result and previous_raw and current.start < previous_raw.end:
            previous = result[-1]
            suffix, separator = _rolling_suffix(previous_raw.text, current.text)
            raw = current
            if suffix is not None:
                merged = previous.text + (separator + suffix if suffix else '')
                if max(previous.end, current.end) - previous.start <= 8 and len(merged) <= 180:
                    result[-1] = Cue(previous.start, max(previous.end, current.end), merged)
                elif suffix:
                    # Retain supplied timing windows instead of inventing word timings.
                    result.append(Cue(current.start, current.end, suffix))
                previous_raw = raw
                continue
        result.append(current)
        previous_raw = current
    return result


def _timestamp(seconds, separator):
    milliseconds = max(0, round(seconds * 1000))
    hours, milliseconds = divmod(milliseconds, 3600000)
    minutes, milliseconds = divmod(milliseconds, 60000)
    secs, milliseconds = divmod(milliseconds, 1000)
    return f'{hours:02}:{minutes:02}:{secs:02}{separator}{milliseconds:03}'


def render_subtitles(cues, ext):
    if ext == 'txt':
        return '\n'.join(cue.text for cue in cues) + '\n'
    if ext not in ('srt', 'vtt'):
        raise ValueError('不支持的导出格式。')
    separator = ',' if ext == 'srt' else '.'
    blocks = []
    for index, cue in enumerate(cues, 1):
        prefix = f'{index}\n' if ext == 'srt' else ''
        content = cue.text if ext == 'srt' else html.escape(cue.text, quote=False)
        blocks.append(f'{prefix}{_timestamp(cue.start, separator)} --> {_timestamp(cue.end, separator)}\n{content}\n')
    return ('WEBVTT\n\n' if ext == 'vtt' else '') + '\n'.join(blocks)


def safe_filename(value):
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', str(value)).strip(' .')[:90] or 'subtitles'
    if name.split('.')[0].upper() in {'CON', 'PRN', 'AUX', 'NUL', *(f'COM{i}' for i in range(1, 10)), *(f'LPT{i}' for i in range(1, 10))}:
        name = '_' + name
    return name

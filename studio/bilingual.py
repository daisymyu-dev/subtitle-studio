"""Explicit bilingual export only; never changes source-language captions."""

import json
import time
from bisect import bisect_left, bisect_right
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, parse_qs, urlparse
from urllib.request import Request, urlopen


class TranslationError(Exception):
    pass


def choose_chinese_track(info):
    candidates = []
    for field in ('subtitles', 'automatic_captions'):
        for code, tracks in (info.get(field) or {}).items():
            if code.split('-')[0].lower() != 'zh':
                continue
            for track in tracks:
                if not track.get('url') or track.get('ext') not in ('json3', 'vtt', 'srt'):
                    continue
                translated = ('tlang' in parse_qs(urlparse(track['url']).query)
                              or ' from ' in track.get('name', '').lower())
                kind = 'youtube_translation' if translated else 'uploaded_chinese' if field == 'subtitles' else 'auto_chinese'
                rank = (2 if translated else 0 if field == 'subtitles' else 1,
                        0 if code.lower() in ('zh-hans', 'zh-cn', 'zh') else 1,
                        {'json3': 0, 'vtt': 1, 'srt': 2}[track['ext']])
                candidates.append((rank, dict(track, code=code, kind=kind)))
    return min(candidates, key=lambda x: x[0])[1] if candidates else None


def align_captions(english, chinese):
    """Bounded chronological groups; partial Chinese is sent for translation.

    Every English cue is retained once. A Chinese track is reusable only when
    its interval union covers at least 90% of *each* English cue in the group,
    and it does not extend far beyond the group. Timestamp coverage is a
    conservative alignment check, not a guarantee of semantic accuracy.
    """
    en = sorted(english, key=lambda x: (x.start, x.end))
    zh = sorted(chinese, key=lambda x: (x.start, x.end))
    starts = [x.start for x in zh]
    prefix_end, furthest = [], -1
    for cue in zh:
        furthest = max(furthest, cue.end)
        prefix_end.append(furthest)
    blocks, group, end, size = [], [], -1, 0

    def flush():
        if not group:
            return
        start = group[0].start
        candidates = [x for x in zh[bisect_right(prefix_end, start):bisect_left(starts, end)] if x.end > start]
        def covered(cue):
            cursor, total = cue.start, 0
            for caption in candidates:
                left, right = max(cursor, caption.start), min(cue.end, caption.end)
                if right > left:
                    total += right - left
                    cursor = right
            return total >= .9 * (cue.end - cue.start)
        reusable = (candidates and all(covered(cue) for cue in group)
                    and all(x.start >= start - .5 and x.end <= end + .5 for x in candidates))
        blocks.append({'start': start, 'end': end, 'english': ' '.join(x.text for x in group),
                       'chinese': ' '.join(x.text for x in candidates) if reusable else ''})
    for cue in en:
        bridge_index = bisect_left(starts, end) - 1
        bridged = bridge_index >= 0 and prefix_end[bridge_index] > cue.start
        bounded = group and max(end, cue.end) - group[0].start <= 30 and size + len(cue.text) <= 1500
        if group and not (bounded and (cue.start < end or bridged)):
            flush()
            group, end, size = [], -1, 0
        group.append(cue)
        end, size = max(end, cue.end), size + len(cue.text)
    flush()
    return blocks


def complete_chinese(blocks, translator, progress=None):
    missing = [block for block in blocks if not block['chinese'].strip()]
    if not missing:
        return 0
    translated = translator.translate_many([block['english'] for block in missing], progress)
    if len(translated) != len(missing) or any(not isinstance(x, str) or not x.strip() for x in translated):
        raise TranslationError('中文翻译不完整，未生成不完整的 Word；英文字幕已保留。')
    for block, chinese in zip(missing, translated):
        block['chinese'] = chinese.strip()
    return len(missing)


class GoogleWebTranslator:
    """No-key public web translation, not Google's paid Cloud Translation API.

    This is an unofficial web route and has no availability guarantee. Only
    explicit opt-in export jobs call it. Fixed destination, bounded bodies,
    timeouts and retries; no cookies, audio, arbitrary endpoints or text logging.
    """
    limit = 2200

    def __init__(self, opener=None, sleep=None):
        self.opener = opener or urlopen
        self.sleep = sleep or time.sleep

    def _request(self, text):
        query = urlencode({'client': 'gtx', 'sl': 'en', 'tl': 'zh-CN', 'dt': 't', 'q': text})
        request = Request('https://translate.googleapis.com/translate_a/single?' + query,
                          headers={'User-Agent': 'SubtitleStudio/1.0'})
        for attempt in range(3):
            try:
                with self.opener(request, timeout=30) as response:
                    raw = response.read(2 * 1024 * 1024 + 1)
                if len(raw) > 2 * 1024 * 1024:
                    raise TranslationError('在线翻译响应过大，请稍后重试。')
                data = json.loads(raw)
                if not isinstance(data, list) or not isinstance(data[0], list):
                    raise ValueError
                if not data[0] or any(not isinstance(item, list) or not item or not isinstance(item[0], str) or not item[0]
                                      for item in data[0]):
                    raise ValueError
                if any(not item[0].strip() and (len(item) < 2 or not isinstance(item[1], str) or item[1].strip())
                       for item in data[0]):
                    raise ValueError
                result = ''.join(item[0] for item in data[0]).strip()
                if not result:
                    raise ValueError
                return result
            except HTTPError as error:
                if error.code in (429, 500, 502, 503, 504) and attempt < 2:
                    self.sleep(2 ** (attempt + 1))
                    continue
                raise TranslationError('Google 网页翻译暂时不可用或被限流；未生成不完整的 Word，请稍后重试。') from None
            except (URLError, TimeoutError, OSError):
                if attempt < 2:
                    self.sleep(2 ** (attempt + 1))
                    continue
                raise TranslationError('在线翻译连接失败；英文字幕已保留，请检查网络后重试。') from None
            except (ValueError, TypeError, IndexError, KeyError, UnicodeError):
                raise TranslationError('在线翻译返回了无法验证的内容；未生成不完整的 Word。') from None

    def _batch(self, texts):
        if len(texts) == 1 and len(texts[0]) > self.limit:
            remaining, pieces = texts[0], []
            while remaining:
                cut = self.limit
                if len(remaining) > cut:
                    space = remaining.rfind(' ', 0, cut)
                    if space > cut // 2:
                        cut = space
                pieces.append(self._request(remaining[:cut]))
                remaining = remaining[cut:].lstrip()
            return [' '.join(pieces)]
        translated = self._request('\n'.join(texts)).splitlines()
        if len(translated) == len(texts) and all(x.strip() for x in translated):
            return [x.strip() for x in translated]
        if len(texts) == 1:
            return [' '.join(translated)]
        middle = len(texts) // 2
        return self._batch(texts[:middle]) + self._batch(texts[middle:])

    def translate_many(self, texts, progress=None):
        if not texts:
            return []
        cache, batch, size = {}, [], 0
        unique = list(dict.fromkeys(texts))
        def flush():
            if not batch:
                return
            cache.update(zip(batch, self._batch(batch)))
            if progress:
                progress(sum(text in cache for text in texts), len(texts))
        for text in unique:
            if not isinstance(text, str) or not text.strip():
                raise TranslationError('字幕存在空白段，无法生成完整中英对照。')
            if batch and size + len(text) + 1 > self.limit:
                flush()
                batch, size = [], 0
            batch.append(text)
            size += len(text) + 1
        flush()
        return [cache[text] for text in texts]

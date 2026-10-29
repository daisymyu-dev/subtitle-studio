"""Lossless, local sentence alignment. Offsets are Python character offsets.

Marks are (exclusive source offset, inserted punctuation) pairs, not replacement
text. Validation returns True or raises ValueError; it never repairs input.
"""

import math
import re
import unicodedata


def _cues(cues):
    result = []
    for cue in cues:
        get = cue.__getitem__ if isinstance(cue, dict) else lambda k: getattr(cue, k)
        start, end, text = get('start'), get('end'), get('text')
        if (not isinstance(text, str) or not _time(start) or not _time(end)
                or start < 0 or end < start):
            raise ValueError('Invalid source cue')
        result.append((float(start), float(end), text))
    return sorted(result, key=lambda c: (c[0], c[1]))


def _time(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def source_text(cues):
    """Join chronological raw cue text with exactly one separator space."""
    return ' '.join(c[2] for c in _cues(cues))


_CLOSERS = '\"\'”’)]}'
_ABBREVIATIONS = {'dr', 'mr', 'mrs', 'ms', 'prof', 'sr', 'jr', 'st',
                  'vs', 'etc', 'e.g', 'i.e', 'no', 'fig', 'inc', 'ltd'}


def _ends(text, restored_positions=()):
    """Yield exclusive sentence ends, including adjacent closing quotes."""
    for i, char in enumerate(text):
        if char not in '.!?':
            continue
        if char == '.' and i not in restored_positions:
            if i and i + 1 < len(text) and text[i-1].isdigit() and text[i+1].isdigit():
                continue
            token = re.search(r'([A-Za-z.]+)$', text[:i])
            word = token.group(1) if token else ''
            pronoun = word == 'I' and not re.search(r'\b[A-Z]\.\s+I$', text[:i])
            if (word.lower() in _ABBREVIATIONS
                    or not pronoun and re.fullmatch(r'(?:[A-Za-z]\.)*[A-Za-z]', word)):
                continue
        j = i + 1
        while j < len(text) and text[j] in '.!?' + _CLOSERS:
            j += 1
        if j == len(text) or text[j].isspace():
            yield j


def build_sentences(cues, marks=None):
    """Build bilingual-ready rows without altering any original character."""
    ordered = _cues(cues)
    raw = ' '.join(c[2] for c in ordered)
    insertions = {}
    for offset, punctuation in marks or ():
        if (type(offset) is not int or not 0 < offset <= len(raw)
                or not isinstance(punctuation, str) or not punctuation
                or any(not unicodedata.category(c).startswith('P') for c in punctuation)
                or (offset < len(raw) and raw[offset-1].isalnum() and raw[offset].isalnum())):
            raise ValueError('Invalid punctuation mark')
        # Punctuator suggestions cannot override existing punctuation, including
        # suggestions immediately before or after an original terminal mark.
        left = raw[:offset].rstrip(_CLOSERS + ' ')
        right = raw[offset:].lstrip(_CLOSERS + ' ')
        if (left and unicodedata.category(left[-1]).startswith('P')
                or right and unicodedata.category(right[0]).startswith('P')):
            continue
        if offset in insertions and insertions[offset] != punctuation:
            raise ValueError('Conflicting punctuation marks')
        insertions[offset] = punctuation

    rendered, origins, restored_positions = [], [], set()
    for i, char in enumerate(raw):
        rendered.append(char)
        origins.append(i)
        for added in insertions.get(i + 1, ''):
            restored_positions.add(len(rendered))
            rendered.append(added)
            origins.append(i)
    text = ''.join(rendered)
    ranges, previous = [], 0
    for end in sorted(set(_ends(text, restored_positions)) | {len(text)}):
        start = previous
        previous = end
        while start < end and text[start].isspace():
            start += 1
        while end > start and text[end-1].isspace():
            end -= 1
        if start < end:
            ranges.append((start, end))

    rows = []
    for index, (a, b) in enumerate(ranges):
        lo, hi = origins[a], origins[b-1] + 1
        start, end, estimated = _span_timing(ordered, lo, hi)
        english = text[a:b]
        reason = _fragment_reason(english, raw[lo:hi], index == 0,
                                  index == len(ranges) - 1)
        rows.append(dict(start=start, end=end, english=english, chinese='',
                         source_start=lo, source_end=hi, fragment=bool(reason),
                         fragment_reason=reason,
                         restored=any(lo < offset <= hi for offset in insertions),
                         timing_estimated=estimated))
    validate_sentences(cues, rows)
    return rows


def _fragment_reason(english, original, first, is_last):
    reasons = []
    first_letter = next((c for c in english if c.isalpha()), '')
    if first and first_letter.islower():
        reasons.append('clipped_start')
    if not english.rstrip(_CLOSERS).endswith(('.', '!', '?')):
        reasons.append('missing_terminal_punctuation')
    elif is_last and not original.rstrip(_CLOSERS).endswith(('.', '!', '?')):
        # Model punctuation expresses a boundary, not evidence that the video
        # contains the complete final thought. Keep that uncertainty explicit.
        reasons.append('restored_tail_uncertain')
    return ';'.join(reasons)


def _span_timing(ordered, lo, hi):
    """Envelope of character-proportional contributions, even for nested cues.

    Source-ordered rows can overlap or move backward in time when source cues
    overlap; never invent monotonic times at the expense of source provenance.
    """
    intervals, pos, estimated = [], 0, False
    for start, end, text in ordered:
        stop = pos + len(text)
        a, b = max(lo, pos), min(hi, stop)
        if a < b:
            duration = end - start
            intervals.append((start + duration * (a-pos) / len(text),
                              start + duration * (b-pos) / len(text)))
            estimated |= a != pos or b != stop
        pos = stop + 1
    if not intervals:
        raise ValueError('Source span has no cue contribution')
    return min(a for a, _ in intervals), max(b for _, b in intervals), estimated


def _punctuation_only_extension(original, rendered):
    # Greedy matching preserves every original character, including punctuation.
    # Insertions may only occur between words, never inside an original word.
    i = 0
    for char in rendered:
        if i < len(original) and char == original[i]:
            i += 1
        elif (not unicodedata.category(char).startswith('P')
              or 0 < i < len(original) and original[i-1].isalnum() and original[i].isalnum()):
            return False
    return i == len(original)


def validate_sentences(cues, rows):
    """Require ordered full source coverage and punctuation-only additions."""
    raw = source_text(cues)
    ordered = _cues(cues)
    cursor = 0
    for index, row in enumerate(rows):
        try:
            lo, hi = row['source_start'], row['source_end']
            start, end, english = row['start'], row['end'], row['english']
            if (type(lo) is not int or type(hi) is not int
                    or not cursor <= lo < hi <= len(raw)
                    or raw[cursor:lo].strip() or raw[lo:hi] != raw[lo:hi].strip()
                    or not isinstance(english, str)
                    or not _punctuation_only_extension(raw[lo:hi], english)
                    or not _time(start) or not _time(end)
                    or start < 0 or end < start):
                raise ValueError('Invalid sentence coverage, text, or timing')
            expected_start, expected_end, estimated = _span_timing(ordered, lo, hi)
            reason = _fragment_reason(english, raw[lo:hi], index == 0,
                                      index == len(rows) - 1)
            if (not math.isclose(start, expected_start, rel_tol=0, abs_tol=1e-7)
                    or not math.isclose(end, expected_end, rel_tol=0, abs_tol=1e-7)
                    or any(type(row[k]) is not bool for k in
                           ('fragment', 'restored', 'timing_estimated'))
                    or row['timing_estimated'] != estimated
                    or row['restored'] != (english != raw[lo:hi])
                    or type(row['fragment_reason']) is not str
                    or row['fragment_reason'] != reason
                    or row['fragment'] != bool(reason)):
                raise ValueError('Invalid sentence timing or metadata')
        except (KeyError, TypeError) as exc:
            raise ValueError('Invalid sentence row') from exc
        cursor = hi
    if raw[cursor:].strip():
        raise ValueError('Incomplete source coverage')
    return True

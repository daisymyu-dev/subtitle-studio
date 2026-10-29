"""Local, probabilistic English punctuation; never generates replacement text.

Primary interfaces/provenance (Apache-2.0):
https://huggingface.co/1-800-BAD-CODE/punctuation_fullstop_truecase_english
https://huggingface.co/inference4j/punctuation-fullstop-truecase-english

The official ONNX and mirror's SentencePiece-converted tokenizer are pinned
below. Only these static assets are downloaded, without credentials. Transcript
text is used exclusively by local tokenizers/ONNXRuntime CPU inference. No torch,
transformers, remote Python, true-casing, or acronym expansion is used.
"""

import hashlib
import os
import re
import tempfile
import threading
import time
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from numbers import Integral
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener


class PunctuationError(RuntimeError):
    """A local model could not be obtained, validated, or run; no fake success."""


@dataclass(frozen=True)
class _Asset:
    repo: str
    revision: str
    filename: str
    size: int
    sha256: str

    @property
    def url(self):
        return f'https://huggingface.co/{self.repo}/resolve/{self.revision}/{self.filename}'


_ASSETS = (
    _Asset('1-800-BAD-CODE/punctuation_fullstop_truecase_english',
           'b26fd1c40e88678859048898218ea4edcc24c84a', 'punct_cap_seg_en.onnx',
           209532928, 'dd922d459da618cd324280889740608b76fb3e9e61d3f402291be1251f91421b'),
    _Asset('inference4j/punctuation-fullstop-truecase-english',
           '22c0534d66a225dc97f1023b2777e948436bb9b7', 'tokenizer.json',
           2115592, 'a1b67b97efeaaad756567df7c1c41213d6572caf517cf57b5b4658c4af5a6a33'),
)
_DOWNLOAD_HOSTS = frozenset({
    'huggingface.co', 'cdn-lfs.huggingface.co', 'cdn-lfs-us-1.huggingface.co',
    'cas-bridge.xethub.hf.co', 'us.aws.cdn.hf.co',
})
_DOWNLOAD_SECONDS = 300
_WINDOW_TOKENS = 254  # The documented limit is 256 including BOS=1 and EOS=2.
_OVERLAP_TOKENS = 64
_POST_MARKS = {0: '', 1: '', 2: '.', 3: ',', 4: '?'}
_QUOTES = frozenset('\"\'“”‘’«»‹›')
_ABBREVIATIONS = frozenset({
    'mr', 'mrs', 'ms', 'dr', 'prof', 'sr', 'jr', 'st', 'vs', 'etc',
    'eg', 'ie', 'fig', 'inc', 'ltd',
})
_LOAD_LOCK = threading.RLock()


class _ModelRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        parsed = urlsplit(newurl)
        if (parsed.scheme != 'https' or parsed.hostname not in _DOWNLOAD_HOSTS
                or parsed.username is not None or parsed.password is not None
                or parsed.port not in (None, 443)):
            raise PunctuationError('标点模型下载跳转到了非许可地址，已停止。')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _open_download(request, timeout):
    # No cookies, HF helpers/tokens, ambient proxy credentials or auth handlers.
    return build_opener(ProxyHandler({}), _ModelRedirects()).open(request, timeout=timeout)


def _download(asset, target):
    temporary = None
    try:
        deadline = time.monotonic() + _DOWNLOAD_SECONDS
        request = Request(asset.url, headers={'User-Agent': 'SubtitleStudio/1.0',
                                              'Accept-Encoding': 'identity'})
        with _open_download(request, timeout=30) as response:
            headers = getattr(response, 'headers', {})
            length = headers.get('Content-Length')
            if length is not None and int(length) != asset.size:
                raise PunctuationError('标点模型下载大小与固定版本不符，已停止。')
            with tempfile.NamedTemporaryFile(dir=target.parent, suffix='.part', delete=False) as output:
                temporary = Path(output.name)
                digest, count = hashlib.sha256(), 0
                read = getattr(response, 'read1', response.read)
                while True:
                    if time.monotonic() > deadline:
                        raise PunctuationError('标点模型下载超时，请检查网络后重试。')
                    block = read(min(1024 * 1024, asset.size - count + 1))
                    if not block:
                        break
                    count += len(block)
                    if count > asset.size:
                        raise PunctuationError('标点模型下载超过大小上限，已停止。')
                    digest.update(block)
                    output.write(block)
            if count != asset.size or digest.hexdigest() != asset.sha256:
                raise PunctuationError('标点模型下载不完整或校验失败，请重试。')
        temporary.replace(target)
    except PunctuationError:
        raise
    except Exception:
        raise PunctuationError('标点模型下载失败，请检查网络后重试。') from None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _ensure_asset(directory, asset):
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / asset.filename
    if not target.exists():
        _download(asset, target)
    digest = hashlib.sha256()
    if target.is_symlink() or target.stat().st_size != asset.size:
        raise PunctuationError('标点模型缓存大小或路径无效，请清理该模型缓存后重试。')
    with target.open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(block)
    if digest.hexdigest() != asset.sha256:
        raise PunctuationError('标点模型缓存校验失败，请清理该模型缓存后重试。')
    return target


class _OnnxBackend:
    def __init__(self, tokenizer, session):
        self.tokenizer = tokenizer
        self.session = session

    def encode(self, text):
        encoded = self.tokenizer.encode(text, add_special_tokens=False)
        return encoded.ids, encoded.offsets

    def predict(self, ids):
        import numpy as np
        inputs = np.asarray([[1, *ids, 2]], dtype=np.int64)
        # This graph returns hard int64 punctuation and bool boundary labels,
        # NOT standard logits. Never read cap_preds or rewrite source casing.
        outputs = self.session.run(['post_preds', 'seg_preds'], {'input_ids': inputs})
        if len(outputs) != 2 or any(not isinstance(item, np.ndarray) for item in outputs):
            raise PunctuationError('本地标点模型返回的数据格式无效，未使用该结果。')
        result, boundaries = outputs
        if (result.shape != inputs.shape or result.dtype.kind not in 'iu'
                or boundaries.shape != inputs.shape or boundaries.dtype.kind != 'b'):
            raise PunctuationError('本地标点模型返回的数据格式无效，未使用该结果。')
        # A positive SBD head supplies a missing terminal mark; a negative one
        # does not overrule punctuation. Keep ? and ignore acronym expansion.
        # Existing SOURCE punctuation is protected later, after source mapping.
        return [2 if boundary and label in (0, 3) else label for label, boundary in
                zip(result[0, 1:-1].tolist(), boundaries[0, 1:-1].tolist())]


@lru_cache(maxsize=2)
def _cached_backend(root):
    try:
        import onnxruntime as ort
        from tokenizers import Tokenizer
    except ImportError:
        raise PunctuationError('本地补标点需要 ONNXRuntime CPU 和 tokenizers，请检查项目依赖。') from None
    directory = Path(root) / '.models' / 'punctuation-en' / _ASSETS[0].revision
    if not directory.resolve().is_relative_to(Path(root)):
        raise PunctuationError('标点模型缓存必须位于项目目录内。')
    model, tokenizer_file = [_ensure_asset(directory, asset) for asset in _ASSETS]
    tokenizer = Tokenizer.from_file(str(tokenizer_file))
    tokenizer.no_truncation()
    tokenizer.no_padding()
    if any(tokenizer.token_to_id(token) != expected for token, expected in
           (('<unk>', 0), ('<s>', 1), ('</s>', 2), ('<pad>', 3))):
        raise PunctuationError('本地标点分词器与固定模型不匹配。')
    options = ort.SessionOptions()
    options.intra_op_num_threads = min(4, os.cpu_count() or 1)
    session = ort.InferenceSession(str(model), sess_options=options, providers=['CPUExecutionProvider'])
    if ([item.name for item in session.get_inputs()] != ['input_ids']
            or session.get_inputs()[0].type != 'tensor(int64)'
            or not {'post_preds', 'seg_preds'}.issubset({item.name for item in session.get_outputs()})):
        raise PunctuationError('本地标点模型接口不匹配，未使用该模型。')
    return _OnnxBackend(tokenizer, session)


def _load_backend(root):
    # lru_cache alone permits duplicate cold loads in simultaneous jobs.
    with _LOAD_LOCK:
        return _cached_backend(str(Path(root).resolve()))


def _prepare(text):
    """Normalize only the model's private copy; map whole tokens to the source.

    A whitespace token is atomic, so predictions cannot land inside a decimal,
    contraction, dotted initial, hyphenation, URL, or other unspaced source token.
    Wrapping quotes are excluded from the insertion offset. Existing punctuation
    after the token, including after closing quotes, always takes precedence.
    Keep internal apostrophes, mapping curly ones to the model's ASCII token,
    so contractions are not confused with unrelated words (we'll -> well).
    """
    words, spans, size = [], [], 0
    for match in re.finditer(r'\S+', text):
        positions = [i for i, char in enumerate(match.group()) if char.isalnum()]
        if not positions:
            continue
        original_start = match.start() + positions[0]
        original_end = match.start() + positions[-1] + 1
        while original_end < match.end() and unicodedata.category(text[original_end]).startswith('M'):
            original_end += 1
        token, characters = match.group(), []
        for i, char in enumerate(token):
            if char.isalnum() or unicodedata.category(char).startswith('M'):
                characters.append(char)
            elif (char in "'’" and 0 < i < len(token) - 1
                  and (token[i - 1].isalnum() or unicodedata.category(token[i - 1]).startswith('M'))
                  and token[i + 1].isalnum()):
                characters.append("'")
        word = ''.join(characters).lower()
        start = size + bool(words)
        size = start + len(word)
        words.append(word)
        spans.append((size, original_start, original_end, word))
    return ' '.join(words), spans


def _labels(backend, ids):
    """Fuse overlapping predictions, including NULL, by available context.

    Interior windows have artificial start/end context. The most central
    observation wins, not the first non-NULL label; in particular a full stop
    forced at a window's end must lose to the next window's interior NULL.
    """
    total = len(ids)
    labels, scores = [None] * total, [-1] * total
    step = _WINDOW_TOKENS - _OVERLAP_TOKENS
    for start in range(0, total, step):
        end = min(start + _WINDOW_TOKENS, total)
        predictions = backend.predict(ids[start:end])
        if (len(predictions) != end - start
                or any(isinstance(label, bool) or not isinstance(label, Integral)
                       or label not in _POST_MARKS for label in predictions)):
            raise PunctuationError('本地标点模型返回的标签无效，未使用该结果。')
        for local, label in enumerate(predictions):
            index = start + local
            score = min(local if start else total, end - index - 1 if end < total else total)
            if score > scores[index]:
                scores[index], labels[index] = score, int(label)
        if end == total:
            break
    return labels


def punctuation_marks(text, *, root, report=None):
    """Return sorted ``(source_character_offset, punctuation)`` insertions.

    Offsets count Python Unicode characters, immediately after an original
    token's last letter/digit and combining marks (before closing quotes). Only missing
    ``. , ?`` may be added. Apply insertions right-to-left; no source characters,
    whitespace, words, casing or existing punctuation are replaced. Results are
    probabilistic model estimates, not certified sentence boundaries. Empty or
    punctuation-only input returns [] without loading a model. Other model,
    download, dependency or inference failures raise PunctuationError.

    First use downloads ~212 MB of pinned, hash-verified public assets under
    ``root/.models``. Later calls reuse local assets/session. ``report`` uses
    the service convention ``report('punctuation', message, **extra)`` and never
    receives transcript text. No input text is sent to the download host.
    """
    if not isinstance(text, str):
        raise TypeError('补标点输入必须为文本。')
    normalized, spans = _prepare(text)
    if not spans:
        return []
    if report:
        report('punctuation', '正在加载本地英语标点模型（概率估计）；首次下载约 212 MB，缓存于项目 .models；不上传字幕或音频。')
    try:
        backend = _load_backend(root)
        ids, offsets = backend.encode(normalized)
        if (not ids or len(ids) != len(offsets)
                or any(isinstance(i, bool) or not isinstance(i, Integral) or i < 0 or i in (1, 2, 3)
                       for i in ids)):
            raise PunctuationError('本地标点分词器返回的词元无效，未使用该结果。')
        previous = (0, 0)
        for start, end in offsets:
            if (not isinstance(start, Integral) or not isinstance(end, Integral)
                    or not 0 <= start < end <= len(normalized)
                    or start < previous[0] or end < previous[1]):
                raise PunctuationError('本地标点分词器返回的原文位置无效，未使用该结果。')
            previous = (start, end)
        if not {span[0] for span in spans}.issubset({end for _, end in offsets}):
            raise PunctuationError('本地标点分词未覆盖全部原文，未使用不完整结果。')
        labels = _labels(backend, ids)
        # The final subword alone may label a whole source token. The acronym
        # class and all internal subword predictions are deliberately ignored.
        by_end = {end: label for (_, end), label in zip(offsets, labels)}
        marks = []
        for i, (end, _, source_end, word) in enumerate(spans):
            mark = _POST_MARKS[by_end.get(end, 0)]
            next_start = spans[i + 1][1] if i + 1 < len(spans) else len(text)
            if (mark and word not in _ABBREVIATIONS
                    and not any(char not in _QUOTES and unicodedata.category(char).startswith('P')
                                and unicodedata.category(char) not in ('Ps', 'Pe', 'Pi', 'Pf')
                                for char in text[source_end:next_start])):
                marks.append((source_end, mark))
    except PunctuationError:
        raise
    except Exception:
        raise PunctuationError('本地补标点失败；未返回部分结果，请检查模型缓存后重试。') from None
    if report:
        report('punctuation', '本地补标点完成（概率估计）；保留原词、大小写和现有标点。',
               punctuation_count=len(marks))
    return marks

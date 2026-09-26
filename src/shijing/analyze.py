"""字频与词频统计。

统计一律在繁简归一后的字形上进行（见 clean.normalize），篇名/分组等展示信息保留原文。
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass

from .clean import han_only, normalize
from .corpus import Corpus

# 《诗经》里高频出现的虚词与套语，进词频榜只会挤掉有信息量的词
STOPWORDS = frozenset(
    '之 兮 其 于 以 而 不 我 尔 彼 此 何 如 是 有 无 言 思 载 孔 则 且 也 矣 唯 予 女 '
    '君子 所谓 如何 之子 于嗟 嗟'.split())


@dataclass
class Stat:
    token: str
    freq: int
    poems: int          # 出现在多少篇中
    total: int          # 语料总字数/总词数
    n_poems: int

    @property
    def rate(self) -> float:
        return self.freq / self.total

    @property
    def cover(self) -> float:
        """篇目覆盖率：多少篇用到了它。"""
        return self.poems / self.n_poems

    def row(self) -> dict:
        return {'token': self.token, 'freq': self.freq, 'rate': round(self.rate, 6),
                'poems': self.poems, 'cover': round(self.cover, 4)}


def _tables(text_by_poem: dict[str, str], kind: str) -> list[Stat]:
    """text_by_poem: 篇标识 -> 已归一的文本；kind 为 char 或 word。"""
    freq: Counter[str] = Counter()
    docs: dict[str, set[str]] = defaultdict(set)
    for key, text in text_by_poem.items():
        toks = _tokens(text, kind)
        freq.update(toks)
        docs[key] = set(toks)
    total = sum(freq.values())
    n = len(text_by_poem)
    return sorted(
        (Stat(t, f, sum(1 for k in docs if t in docs[k]), total, n)
         for t, f in freq.items()),
        key=lambda s: (-s.freq, s.token))


def _tokens(text: str, kind: str) -> list[str]:
    if kind == 'char':
        return han_only(text)
    import jieba
    return [w for w in jieba.cut(text) if w.strip() and not w.isspace()]


def char_stats(corpus: Corpus) -> list[Stat]:
    by_poem = {f'{p.group}·{p.title}': normalize(''.join(p.stanzas)) for p in corpus.poems}
    return _tables(by_poem, 'char')


def word_stats(corpus: Corpus, drop_stopwords: bool = True) -> list[Stat]:
    by_poem = {f'{p.group}·{p.title}': normalize(''.join(p.stanzas)) for p in corpus.poems}
    out = _tables(by_poem, 'word')
    if drop_stopwords:
        out = [s for s in out if s.token not in STOPWORDS and len(s.token) > 1]
    return out


def frequencies(stats: list[Stat]) -> dict[str, int]:
    """给 wordcloud 用的词 -> 频数字典。"""
    return {s.token: s.freq for s in stats}


def coverage(stats: list[Stat], shares: tuple[float, ...] = (0.5, 0.8)) -> list[tuple[float, int]]:
    """Zipf 式集中度：前多少个高频词累计占到多少比例。"""
    total = sum(s.freq for s in stats) or 1
    out, acc = [], 0
    target = list(shares)
    idx = 0
    for n, s in enumerate(stats, 1):
        acc += s.freq
        while idx < len(target) and acc / total >= target[idx]:
            out.append((target[idx], n))
            idx += 1
        if idx >= len(target):
            break
    return out


def zipf_r2(stats: list[Stat]) -> float:
    """频次-排名关系的决定系数（log-log），用来判断语料是否符合自然语言长尾。"""
    pts = [(i, s.freq) for i, s in enumerate(stats, 1) if s.freq > 0]
    if len(pts) < 3:
        return float('nan')
    import math
    x = [math.log(i) for i, _ in pts]
    y = [math.log(f) for _, f in pts]
    n = len(x)
    mx, my = sum(x) / n, sum(y) / n
    sxx = sum((a - mx) ** 2 for a in x)
    sxy = sum((a - mx) * (b - my) for a, b in zip(x, y, strict=False))
    if sxx == 0:
        return float('nan')
    b = sxy / sxx
    a = my - b * mx
    sse = sum((yy - (a + b * xx)) ** 2 for xx, yy in zip(x, y, strict=False))
    sst = sum((yy - my) ** 2 for yy in y)
    return 1 - sse / sst if sst else float('nan')

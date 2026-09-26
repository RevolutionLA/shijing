"""复沓与重章叠句。

这是《诗经》最标志性的结构手法，原仓库的三个脚本完全没有触及。这里做三件可计算的
事：叠字、篇内章与章的平行度、跨篇复现的句子。
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass

from .clean import normalize
from .corpus import Corpus, Poem

SENT_SPLIT = re.compile(r'[，。！？；：、]')
AA = re.compile(r'([一-鿿])\1')


@dataclass
class Reduplication:
    token: str
    freq: int
    poems: int

    def row(self) -> dict:
        return {'token': self.token, 'freq': self.freq, 'poems': self.poems}


@dataclass
class Parallelism:
    poem: Poem
    score: float              # 最相似的两章之间的字位一致率
    best: tuple[int, int]     # 是哪两章（0-based）
    stanzas: int

    def row(self) -> dict:
        return {'idx': self.poem.idx, 'group': self.poem.group, 'title': self.poem.title,
                'stanzas': self.stanzas, 'best': f'{self.best[0] + 1}↔{self.best[1] + 1}',
                'score': round(self.score, 4)}


def sentences(stanza: str) -> list[str]:
    return [s for s in (normalize(x) for x in SENT_SPLIT.split(stanza)) if s]


def _similarity(a: list[str], b: list[str]) -> float:
    """逐句对齐后的字位一致率；句数不同则为 0。"""
    if len(a) != len(b) or not a:
        return 0.0
    same = tot = 0
    for x, y in zip(a, b, strict=False):
        for c1, c2 in zip(x, y, strict=False):
            tot += 1
            same += c1 == c2
        tot += abs(len(x) - len(y))
    return same / tot if tot else 0.0


def parallelism(corpus: Corpus) -> list[Parallelism]:
    """每篇取其最平行的一对章，用来给「重章叠句」强度排序。"""
    out: list[Parallelism] = []
    for p in corpus.poems:
        sts = [sentences(s) for s in p.stanzas]
        best, pair = 0.0, (0, 0)
        for i in range(len(sts)):
            for j in range(i + 1, len(sts)):
                s = _similarity(sts[i], sts[j])
                if s > best:
                    best, pair = s, (i, j)
        out.append(Parallelism(p, best, pair, len(sts)))
    return sorted(out, key=lambda r: (-r.score, r.poem.idx))


def reduplications(corpus: Corpus) -> list[Reduplication]:
    """叠字（AA 式），按频次排序。"""
    freq: Counter[str] = Counter()
    docs: dict[str, set[int]] = defaultdict(set)
    for p in corpus.poems:
        text = normalize(''.join(p.stanzas))
        for m in AA.finditer(text):
            w = m.group(0)
            freq[w] += 1
            docs[w].add(p.idx)
    return sorted((Reduplication(w, c, len(docs[w])) for w, c in freq.items()),
                  key=lambda r: (-r.freq, r.token))


def shared_lines(corpus: Corpus, min_poems: int = 2) -> list[tuple[str, int, list[str]]]:
    """跨篇复现的句子：诗经的套语（如「之子于归」）在这里能被量化出来。"""
    owners: dict[str, list[str]] = defaultdict(list)
    for p in corpus.poems:
        seen: set[str] = set()
        for s in p.stanzas:
            for sent in sentences(s):
                if len(sent) >= 3 and sent not in seen:
                    seen.add(sent)
                    owners[sent].append(f'{p.group}·{p.title}')
    out = [(k, len(v), sorted(set(v))) for k, v in owners.items() if len(v) >= min_poems]
    return sorted(out, key=lambda r: (-r[1], r[0]))


def summary(corpus: Corpus) -> dict:
    par = parallelism(corpus)
    strong = [r for r in par if r.score >= 0.6]
    sh = shared_lines(corpus)
    return {
        'poems': len(par),
        'parallel_poems': len(strong),
        'mean_parallelism': round(sum(r.score for r in par) / len(par), 4) if par else 0.0,
        'top_parallel': [r.row() for r in par[:5]],
        'reduplication_total': sum(r.freq for r in reduplications(corpus)),
        'reduplication_kinds': len(reduplications(corpus)),
        'shared_line_kinds': len(sh),
    }

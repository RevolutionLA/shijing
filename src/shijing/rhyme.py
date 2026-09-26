"""韵脚分析（今音口径）。

必须说清楚的边界：《诗经》押的是上古音，此模块用现代汉语韵母归类，因此
「今音不同韵而上古同韵」的字会被判成不押韵，「今音同韵而上古不同部」的会被
误判为押韵。它适合用来找模式、做对比，不能当作上古音结论。
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from .clean import normalize
from .corpus import Corpus, Poem
from .refrain import sentences

# 语助字收尾不参与押韵，是《诗经》用韵的通例（「关关雎鸠」押鸠而非「之」）
PARTICLES = set('之兮只思蔼阿矣也哉夫而其')


@dataclass
class RhymeScheme:
    poem: Poem
    finals: list[str]                 # 每个句末字的韵母（去声调）
    scheme: str = ''                  # ABBAC… 型标记
    groups: int = 0                   # 用到多少个韵部
    turns: int = 0                    # 换韵次数

    def row(self) -> dict:
        return {'idx': self.poem.idx, 'group': self.poem.group, 'title': self.poem.title,
                'lines': len(self.finals), 'groups': self.groups,
                'turns': self.turns, 'scheme': self.scheme}


def _finals_loader():
    from pypinyin import Style, lazy_pinyin

    def finals(ch: str) -> str:
        r = lazy_pinyin(ch, style=Style.FINALS, strict=False)
        return r[0] if r else ''
    return finals


def line_endings(poem: Poem, skip_particles: bool = True) -> list[str]:
    """每句的韵脚字。整篇按章序展开，章内按句序。

    skip_particles=True 时跳过句末语助字（之/兮/只…），取前一个实字作韵脚。
    """
    out = []
    for stanza in poem.stanzas:
        for s in sentences(normalize(stanza)):
            if not s:
                continue
            i = len(s) - 1
            if skip_particles:
                while i > 0 and s[i] in PARTICLES:
                    i -= 1
            out.append(s[i])
    return out


def label_scheme(finals: list[str]) -> tuple[str, int, int]:
    letters: dict[str, str] = {}
    order: list[str] = []
    for f in finals:
        if f not in letters:
            letters[f] = chr(ord('A') + len(letters) % 26)
            order.append(f)
    scheme = ''.join(letters[f] for f in finals)
    turns = sum(1 for a, b in zip(scheme, scheme[1:], strict=False) if a != b)
    return scheme, len(order), turns


def schemes(corpus: Corpus, skip_particles: bool = True) -> list[RhymeScheme]:
    finals = _finals_loader()
    out: list[RhymeScheme] = []
    for p in corpus.poems:
        fs = [f for f in (finals(c) for c in line_endings(p, skip_particles)) if f]
        if not fs:
            continue
        sch, n, turns = label_scheme(fs)
        out.append(RhymeScheme(p, fs, sch, n, turns))
    return out


def summary(corpus: Corpus, skip_particles: bool = True) -> dict:
    rs = schemes(corpus, skip_particles)
    total_lines = sum(len(r.finals) for r in rs)
    one_rhyme = [r for r in rs if r.groups == 1]
    dist = Counter(f for r in rs for f in r.finals)
    return {
        'poems': len(rs),
        'rhyming_lines': total_lines,
        'one_rhyme_poems': len(one_rhyme),
        'one_rhyme_rate': round(len(one_rhyme) / len(rs), 4) if rs else 0.0,
        'mean_groups_per_10_lines': round(
            10 * sum(r.groups for r in rs) / total_lines, 2) if total_lines else 0.0,
        'top_finals': dist.most_common(10),
        'most_stable': [r.row() for r in sorted(
            (x for x in rs if len(x.finals) >= 6), key=lambda x: x.groups)[:5]],
    }

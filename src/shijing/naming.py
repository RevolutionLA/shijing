"""候选名的可核验材料：出处、语境、用字档位、读音。

这个模块只回答能被语料证实的问题——某组字在《诗经》里连用没有、出现在哪句、
那几个字有多常用、今天读起来是什么声调。名字"好不好"是语义与语域的判断，
必须由人读完整首诗之后自己下，代码不做这件事，也不假装能做。
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from . import analyze
from .clean import normalize
from .corpus import Corpus

# 单字虚词：统计上最高频，但它们进名字只起连接作用，档位要另眼看待
FUNCTION = frozenset(
    '之乎者也以而于其且则兮矣哉惟维思亦何罔无既孔伊斯止尔女予汝彼此莫匪敢'
    '言载式来斯只')

# (篇数下界, 档位名)——按本库 305 篇的分布取档，不是通用频率
TIERS = ((120, '极常见'), (50, '常见'), (15, '中等'), (1, '较少'), (0, '未见'))


def tier(poems: int) -> str:
    for lower, name in TIERS:
        if poems >= lower:
            return name
    return '未见'


@dataclass
class Syllable:
    char: str
    syllable: str   # 带调拼音，如 lìng
    tone: int       # 1-5，5 为轻声
    initial: str
    final: str
    also: tuple[str, ...] = ()   # 又读：姓名用音常与常用词不同（乐/单/传）

    def row(self) -> dict:
        return {'char': self.char, 'pinyin': self.syllable, 'tone': self.tone,
                'initial': self.initial, 'final': self.final,
                'also': list(self.also)}


def reading(query: str) -> list[Syllable]:
    """普通话读音。多音字取 pypinyin 的词组默认读法，并把又读一并列出。"""
    from pypinyin import Style, lazy_pinyin, pinyin

    chars = [ch for ch in query if re.search(r'[一-鿿]', ch)]
    if not chars:
        return []
    word = ''.join(chars)
    tones = pinyin(word, style=Style.TONE3, heteronym=True)
    inits = lazy_pinyin(word, style=Style.INITIALS, strict=False)
    fins = lazy_pinyin(word, style=Style.FINALS, strict=False)
    out = []
    for ch, opts, ini, fin in zip(chars, tones, inits, fins, strict=True):
        py = opts[0]
        digit = next((t for t in reversed(py) if t.isdigit()), '5')
        out.append(Syllable(ch, py, int(digit), ini, fin,
                            tuple(dict.fromkeys(opts[1:]))))
    return out


def links(sylls: list[Syllable]) -> list[str]:
    """相邻两字的语音关系：双声、叠韵、同调。都是事实描述，不是好坏判断。"""
    out = []
    for a, b in zip(sylls, sylls[1:], strict=False):
        pair = f'{a.char}{b.char}'
        if a.initial and a.initial == b.initial:
            out.append(f'{pair} 双声（声母同 {a.initial}）')
        if a.final == b.final:
            out.append(f'{pair} 叠韵（韵母同 {a.final}）')
        if a.tone == b.tone:
            out.append(f'{pair} 同调（都是 {a.tone} 声）')
    return out


def hits(corpus: Corpus, query: str) -> list[dict]:
    """query 作为连续字符串命中的分句，繁简通搜。"""
    q = normalize(query)
    rows = []
    for p in corpus.poems:
        for n, st in enumerate(p.stanzas, 1):
            if q in normalize(st):
                rows.append({'group': p.group, 'title': p.title, 'poem_idx': p.idx,
                             'stanza': n, 'line': st.strip()})
    return rows


def char_facts(corpus: Corpus, query: str) -> list[dict]:
    """逐字的词频、所见篇数与档位。"""
    stats = {s.token: s for s in analyze.char_stats(corpus)}
    out = []
    for ch in dict.fromkeys(re.findall(r'[一-鿿]', normalize(query))):
        s = stats.get(ch)
        poems = s.poems if s else 0
        out.append({'char': ch, 'freq': s.freq if s else 0, 'poems': poems,
                    'tier': tier(poems), 'function': ch in FUNCTION})
    return out


def contexts(corpus: Corpus, rows: list[dict]) -> list[dict]:
    """命中所在篇的全文——判断语域唯一的依据，也是本模块存在的理由。"""
    seen = {}
    for r in rows:
        seen.setdefault(r['poem_idx'], None)
    out = []
    for p in corpus.poems:
        if p.idx in seen:
            out.append({'group': p.group, 'title': p.title, 'idx': p.idx,
                        'stanzas': [s.strip() for s in p.stanzas]})
    return out


def inspect(corpus: Corpus, query: str, with_context: bool = True) -> dict:
    rows = hits(corpus, query)
    syls = reading(query)
    cs = contexts(corpus, rows) if with_context else []
    note = ('本命令只给可核验的出处与读音，不给吉凶评分；'
            + ('请读 contexts 里的整首诗。' if with_context
               else '整首语境请用 shijing show（本次未打印，去掉 --no-context 即出）。'))
    return {
        'query': query,
        'hit_count': len(rows),
        'hits': rows,
        'chars': char_facts(corpus, query),
        'reading': [s.row() for s in syls],
        'links': links(syls),
        'contexts': cs,
        'note': note,
    }

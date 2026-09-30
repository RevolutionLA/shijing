"""候选名的可核验材料：出处、语境、用字档位、读音。

这个模块只回答能被语料证实的问题——某组字连用过没有、出现在哪一句、那几个字有多
常用、今天读起来是什么声调。默认检索范围是诗经加四书（`--book all`），因为取名时的
出处习惯（"女诗经、男楚辞、文论语、武周易"）本来就横跨几部书，只查一半等于说谎。
名字"好不好"是语义与语域的判断，必须由人读完整篇之后自己下，代码不做这件事，
也不假装能做。
"""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass

from . import analyze
from .clean import normalize
from .corpus import Corpus

# 单字虚词：统计上最高频，但它们进名字只起连接作用，档位要另眼看待
FUNCTION = frozenset(
    '之乎者也以而于其且则兮矣哉惟维思亦何罔无既孔伊斯止尔女予汝彼此莫匪敢'
    '言载式来斯只')

# (篇数下界, 档位名)——按诗经单库 305 篇的分布取档；合并检索时篇数的分母变成 341 篇，
# 同一字的档位可能上调一档，跨口径比较要先固定 --book
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


def _scan(corpus: Corpus) -> list[tuple[str, str, str, int, int, str, str]]:
    """(典籍, 分组, 篇名, 全库唯一键, 章号, 原文, 归一文)。整库归一只做一次。

    键用 `uid` 而不是 `idx`：合并多本典籍时，《论语》第 1 篇和《诗经》第 1 篇的
    idx 都是 1，靠 idx 会把语境挂到错的篇上。
    """
    out = []
    for p in corpus.poems:
        for n, st in enumerate(p.stanzas, 1):
            out.append((p.book, p.group, p.title, p.uid, n, st.strip(), normalize(st)))
    return out


def hits(corpus: Corpus, query: str,
         lines: list[tuple] | None = None) -> list[dict]:
    """query 作为连续字符串命中的分句，繁简通搜。"""
    q = normalize(query)
    return [{'book': b, 'group': g, 'title': t, 'poem': u, 'stanza': n, 'line': raw}
            for b, g, t, u, n, raw, ns in (lines or _scan(corpus)) if q in ns]


def char_facts(corpus: Corpus, query: str,
               stats: dict[str, analyze.Stat] | None = None) -> list[dict]:
    """逐字的词频、所见篇数与档位。"""
    stats = stats if stats is not None else {s.token: s for s in analyze.char_stats(corpus)}
    out = []
    for ch in dict.fromkeys(re.findall(r'[一-鿿]', normalize(query))):
        s = stats.get(ch)
        poems = s.poems if s else 0
        out.append({'char': ch, 'freq': s.freq if s else 0, 'poems': poems,
                    'tier': tier(poems), 'function': ch in FUNCTION})
    return out


def contexts(corpus: Corpus, rows: list[dict]) -> list[dict]:
    """命中所在篇的全文——判断语域唯一的依据，也是本模块存在的理由。

    `matched` 记下哪些章/段真的命中，供展示层在一整篇几千字的散文典籍上只印
    命中段；数据层仍给全文，`--format json` 拿到的永远是整篇。
    """
    seen = {r['poem'] for r in rows}
    marks: dict[str, set[int]] = defaultdict(set)
    for r in rows:
        marks[r['poem']].add(r['stanza'])
    out = []
    for p in corpus.poems:
        if p.uid in seen:
            out.append({'book': p.book, 'group': p.group, 'title': p.title,
                        'uid': p.uid, 'stanzas': [s.strip() for s in p.stanzas],
                        'matched': sorted(marks[p.uid])})
    return out


def char_sources(corpus: Corpus, query: str, limit: int | None = None,
                 lines: list[tuple] | None = None) -> list[dict]:
    """组合不成句时，逐字给出它自己的出处——拼凑的名字全靠这栏来判。

    limit 默认不限：数据层给全量，截断是展示层的事。
    """
    lines = lines if lines is not None else _scan(corpus)
    out = []
    for ch in dict.fromkeys(re.findall(r'[一-鿿]', normalize(query))):
        rows = hits(corpus, ch, lines)
        out.append({'char': ch, 'count': len(rows),
                    'examples': rows if limit is None else rows[:limit]})
    return out


def inspect(corpus: Corpus, query: str, with_context: bool = True) -> dict:
    lines = _scan(corpus)
    rows = hits(corpus, query, lines)
    syls = reading(query)
    cs = contexts(corpus, rows) if with_context else []
    if not rows:
        note = '无连用命中，故无语境可读；单字出处见 char_sources。'
    elif with_context:
        note = '本命令只给可核验的出处与读音，不给吉凶评分；请读 contexts 里的整篇原文。'
    else:
        note = ('本命令只给可核验的出处与读音，不给吉凶评分；'
                '整首语境请用 shijing show（本次未打印，去掉 --no-context 即出）。')
    return {
        'query': query,
        'corpus': {'books': corpus.books, 'poems': len(corpus.poems),
                   'chars': corpus.total_chars},
        'hit_count': len(rows),
        'hits': rows,
        'chars': char_facts(corpus, query),
        'char_sources': [] if rows else char_sources(corpus, query, lines=lines),
        'reading': [s.row() for s in syls],
        'links': links(syls),
        'contexts': cs,
        'note': note,
    }

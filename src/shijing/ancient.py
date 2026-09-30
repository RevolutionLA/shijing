"""韵脚分析（上古音口径）。

数据来自 Baxter《上古音手册》(1992) 附录的《诗经》押韵字表，经 CLDF 转换后
随本仓库分发（CC-BY-4.0，见 `data/README.md`）。这份表是**逐句标好的**：哪一句
入韵、韵脚字是哪一个、同篇内哪些字互押。所以本模块不做推断，只做转录与汇总。

与今音口径（`rhyme.py`）的关键差别有三条，都是今音口径系统做不到的：
1. 韵脚字不必在句末——「薄言捋之」押「捋」而非「之」，句中双韵的句子数以
   `shijing rhyme --what summary` 的实测为准；
2. 约四分之一的句子根本不参与押韵，无需猜语助字白名单；
3. 互押关系直接给出上古韵部归并的证据，不受今音演变干扰。
"""
from __future__ import annotations

import csv
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from .clean import HAN
from .corpus import Corpus
from .paths import locate
from .rhyme import _LABELS, _finals_loader

DEFAULT_PATH = 'data/rhyme_baxter1992.csv'


@dataclass
class Clause:
    idx: int
    stanza: int
    line: int
    text: str
    rhyme_chars: tuple[str, ...] = ()
    positions: tuple[int, ...] = ()
    keys: tuple[str, ...] = ()      # 同篇内的局部韵标，如 12-a

    @property
    def rhymes(self) -> bool:
        return bool(self.rhyme_chars)


@dataclass
class AncientScheme:
    poem_idx: int
    title: str
    group: str
    clauses: list[Clause] = field(repr=False, default_factory=list)
    scheme: str = ''          # 与 clauses 等长：A/B/… 表示韵部，'·' 表示不入韵
    internal: int = 0         # 句中韵（一句两个韵脚字）数

    @property
    def lines(self) -> int:
        return len(self.clauses)

    @property
    def rhyming(self) -> int:
        return sum(1 for c in self.clauses if c.rhymes)

    @property
    def groups(self) -> int:
        return len({(c.stanza, c.keys[0]) for c in self.clauses if c.keys})

    @property
    def turns(self) -> int:
        keys = [(c.stanza, c.keys[0]) for c in self.clauses if c.keys]
        return sum(1 for a, b in zip(keys, keys[1:], strict=False) if a != b)

    @property
    def rate(self) -> float:
        return self.rhyming / self.lines if self.lines else 0.0

    def row(self) -> dict:
        return {'idx': self.poem_idx, 'group': self.group, 'title': self.title,
                'lines': self.lines, 'rhyming': self.rhyming,
                'rate': round(self.rate, 4), 'groups': self.groups,
                'turns': self.turns, 'internal': self.internal,
                'scheme': self.scheme}


@lru_cache(maxsize=4)
def _read(path: Path) -> dict[int, list[Clause]]:
    out: dict[int, list[Clause]] = defaultdict(list)
    with path.open(encoding='utf-8', newline='') as fh:
        for r in csv.DictReader(fh):
            text = r['clause']
            if len(HAN.findall(text)) != len(text):
                raise SystemExit(
                    f'韵脚表 {path.name} 的分句含非汉字字符（{text!r}）：'
                    '表内应当只留汉字，句末位置比较依赖这一点')
            out[int(r['poem'])].append(Clause(
                idx=int(r['idx']), stanza=int(r['stanza']), line=int(r['line']),
                text=text,
                rhyme_chars=tuple(r['rhyme_chars']),
                positions=tuple(int(x) for x in r['rhyme_pos'].split()),
                keys=tuple(x for x in r['rhyme_ids'].split('|') if x)))
    for v in out.values():
        v.sort(key=lambda c: c.idx)
    return dict(out)


def load(path: str | Path = DEFAULT_PATH) -> dict[int, list[Clause]]:
    """读入逐句韵脚表，按篇序号分组。静态表，同一路径只读盘一次。"""
    p = locate(path)
    if not p.exists():
        raise SystemExit(f'找不到韵脚数据 {p}；它应随仓库一起提供（见 data/README.md）')
    return _read(p)


def schemes(corpus: Corpus, path: str | Path = DEFAULT_PATH) -> list[AncientScheme]:
    """把局部韵标 a/b/x 重写成 A/B/…，与语料的篇序一一对应。"""
    data = load(path)
    out: list[AncientScheme] = []
    for poem in corpus.poems:
        clauses = data.get(poem.idx, [])
        if not clauses:
            continue
        letters: dict[tuple[int, str], str] = {}
        marks = []
        internal = 0
        prev_stanza = None
        for c in clauses:
            if prev_stanza is not None and c.stanza != prev_stanza:
                marks.append('|')            # 章界：韵标在每章内重新起用
            prev_stanza = c.stanza
            if not c.keys:
                marks.append('·')
                continue
            key = (c.stanza, c.keys[0])
            if key not in letters:
                # 与 rhyme.label_scheme 同一套 62 个标签、同样不取模：两个不同的
                # 局部韵类撞进同一个字母，就等于把不同的韵说成同一个
                letters[key] = _LABELS[len(letters)]
            marks.append(letters[key])
            if len(c.rhyme_chars) > 1:
                internal += 1
        out.append(AncientScheme(poem_idx=poem.idx, title=poem.title,
                                 group=poem.group, clauses=clauses,
                                 scheme=''.join(marks), internal=internal))
    return out


def rhyme_classes(path: str | Path = DEFAULT_PATH):
    """局部韵类：(篇, 章, 标签) -> 该类的韵脚字序列。

    标签是**每章重新起用**的——《葛覃》第一章 a=谷/木、b=萋/飛/喈，第二章的
    a 又是另一组韵。所以绝不能按篇归组，否则不同章的同名标签会被并成一类。
    """
    out: dict[tuple[int, int, str], list[str]] = defaultdict(list)
    for pidx, clauses in load(path).items():
        for c in clauses:
            for ch, k in zip(c.rhyme_chars, c.keys, strict=True):
                out[(pidx, c.stanza, k)].append(ch)
    return out


def co_rhymes(path: str | Path = DEFAULT_PATH) -> Counter:
    """同章互押的字对——韵部归并的证据。"""
    pairs: Counter = Counter()
    for chars in rhyme_classes(path).values():
        for i, a in enumerate(chars):
            for b in chars[i + 1:]:
                pairs[tuple(sorted((a, b)))] += 1
    return pairs


def compare_modern(corpus: Corpus, path: str | Path = DEFAULT_PATH) -> dict:
    """量化今音口径的失真：上古互押的字，今天还同韵吗？"""
    final = _finals_loader()
    both_same = anc_only = 0
    for chars in rhyme_classes(path).values():
        for a, b in zip(chars, chars[1:], strict=False):
            if final(a) == final(b):
                both_same += 1
            else:
                anc_only += 1
    total = both_same + anc_only
    # 只看「整章同一韵类」的情况：今音口径会把它们误判成换韵
    cls = list(rhyme_classes(path).values())
    intact = sum(1 for c in cls if len({final(x) for x in c}) == 1)
    return {
        'adjacent_pairs': total,
        'still_rhyme': both_same,
        'lost': anc_only,
        'lost_rate': round(anc_only / total, 4) if total else 0,
        'classes': len(cls),
        'classes_intact_in_modern': intact,
        'class_intact_rate': round(intact / len(cls), 4) if cls else 0,
    }


def summary(corpus: Corpus, path: str | Path = DEFAULT_PATH) -> dict:
    ss = schemes(corpus, path)
    lines = sum(s.lines for s in ss)
    rhyming = sum(s.rhyming for s in ss)
    return {
        'poems': len(ss),
        'clauses': lines,
        'rhyming_lines': rhyming,
        'rhyming_rate': round(rhyming / lines, 4) if lines else 0,
        'internal_rhyme_lines': sum(s.internal for s in ss),
        'off_position_rhymes': sum(
            1 for s in ss for c in s.clauses
            if c.positions and c.positions[0] != len(c.text)),
        'one_rhyme_poems': sum(1 for s in ss if s.groups == 1),
        'mean_groups_per_poem': round(
            sum(s.groups for s in ss) / len(ss), 2) if ss else 0,
        'classes': len(rhyme_classes(path)),
        'top_pairs': [[f'{a}{b}', n] for (a, b), n in co_rhymes(path).most_common(10)],
    }

"""《诗经》语料的清洗与结构化解析。

原始 data/raw/shijing.txt 是从网页表格抓取的，存在整段重复粘贴、分组标题丢失、
HTML 残留与脱字。本模块以「正文内容」而非「标题」为唯一键来去重归位，并把无法
自动修复的损伤作为 findings 报出来，交给人工核对。
"""
from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

# 汉字字符类：基本区 + 扩展 A–G（U+3400–U+4DBF、U+4E00–U+9FFF、U+20000–U+33FFF）。
# 只写基本区会漏账：归一表里有 634 条映射的简体目标落在扩展区，于是〈縨〉归一成𫄨、
# 〈道〉相关字归一成𬤊 之类会整体逃出字频，导致 `report` 里「字数」与「字频合计」
# 自相矛盾（实测差 120 处 / 52 个字形）。原文侧没有扩展区字形，所以总字数不受影响。
HAN_RANGE = '㐀-䶿一-鿿\U00020000-\U00033fff'
HAN = re.compile(rf'[{HAN_RANGE}]')
# 诗经篇名最长者〈昊天有成命〉五字；放宽到 6 以容纳繁简混排下的写法。
# 这里刻意只用基本区：它解析的是已冻结的 data/raw/shijing.txt，该文件不含扩展区字，
# 放宽只会让「一行像篇名」的误判变多。
TITLE_MAX = 6
TITLE = re.compile(rf'[一-鿿]{{1,{TITLE_MAX}}}$')
PU = re.compile(r'[，。！？；：、,.!?;:]')
HTML_RESIDUE = re.compile(r'</?[a-zA-Z][^>]*>?|/td>|/tr>|&#\d+;')

# 分组标题的繁体写法
GROUP_NORM = str.maketrans({'頌': '颂', '魯': '鲁', '國': '国', '風': '风'})
MIN_BODY_CHARS = 8

# 脱字签名：原文件的抓取损伤会把丢掉的字留成一个句内空洞，表现为连续两个标点。
DROPPED = re.compile(r'[。，]{2}')
# 能确证缺什么的才补。《野有死麕》第2章原文件作「林有朴。，」，Baxter《上古音手册》
# 押韵字表同一句作「林有朴樕」（CC-BY-4.0，见 data/README.md），缺的字有据可依。
# 《新台》第1章原文件把渲染不出的「泚」拆成部件「氵此」写了出来，同一句韵脚表作
# 「新台有泚」——这类拆写若不改回来，字频表里就会多出一个不是字的「氵」。
# 另外两处（定之方中、维鹈在梁）只以 `?/td>` 留下残迹，无法确定缺的是什么，不补。
REPAIRS = (('林有朴。，', '林有朴樕，', '据 Baxter 韵脚表同句作「林有朴樕」'),
           ('新台有氵此', '新台有泚', '据 Baxter 韵脚表同句作「新台有泚」，'
                                     '原文件的「氵此」是把一个渲染不出的字拆成了部件'))


@dataclass(frozen=True)
class Poem:
    idx: int
    group: str
    part: str          # 国风 / 小雅 / 大雅 / 周颂 / 鲁颂 / 商颂；散文典籍为书名
    title: str
    stanzas: tuple[str, ...]
    versions: int = 1  # 合并进来的重复版本数
    book: str = '诗经'  # 典籍名；idx 是「书内序号」，跨书会重号

    @property
    def chars(self) -> int:
        return sum(len(HAN.findall(s)) for s in self.stanzas)

    @property
    def uid(self) -> str:
        """跨典籍唯一的键。凡把 idx 当文档 id 用的地方都要用它，否则《论语》第 1 篇
        会和《诗经》第 1 篇撞在一起。"""
        return f'{self.book}#{self.idx}'

    def __hash__(self):
        return hash((self.book, self.group, self.title))


@dataclass
class Corpus:
    poems: list[Poem]
    findings: list[str] = field(default_factory=list)

    @property
    def total_chars(self) -> int:
        return sum(p.chars for p in self.poems)

    @property
    def books(self) -> list[str]:
        """按出现顺序列典籍名（合并语料时不止一本）。"""
        out: list[str] = []
        for p in self.poems:
            if p.book not in out:
                out.append(p.book)
        return out

    def groups(self) -> dict[str, list[Poem]]:
        out: dict[str, list[Poem]] = {}
        for p in self.poems:
            out.setdefault(p.group, []).append(p)
        return out

    def text(self) -> str:
        return '\n'.join(s for p in self.poems for s in p.stanzas)


def part_of(group: str) -> str:
    return group.split('·')[0]


def clean_line(raw: str) -> tuple[str, bool]:
    """去掉表格残留标签。返回 (清洗后文本, 是否有残留)。"""
    damaged = bool(HTML_RESIDUE.search(raw))
    if damaged:
        stripped = HTML_RESIDUE.sub('', raw).strip()
        if stripped != raw.strip():
            return stripped, True
        return raw, True
    return raw, False


def _is_group(line: str) -> bool:
    return '·' in line or line.translate(GROUP_NORM) in ('商颂', '周颂', '鲁颂')


def _norm_group(line: str) -> str:
    return line.translate(GROUP_NORM)


def _is_title(line: str) -> bool:
    """篇名行：纯汉字、无标点、不超过 TITLE_MAX 字。"""
    return (not _is_group(line) and not PU.search(line)
            and TITLE.match(line) is not None)


def _split_blocks(lines: list[str]) -> list[dict]:
    """按「分组标题 / 篇名 / 正文」切成块；同一篇会出现多次（重复粘贴）。"""
    blocks: list[dict] = []
    group = None
    i, n = 0, len(lines)
    while i < n:
        line = lines[i]
        if _is_group(line):
            group = _norm_group(line)
            i += 1
            continue
        if _is_title(line):
            nxt = lines[i + 1] if i + 1 < n else ''
            if PU.search(nxt) or len(HAN.findall(nxt)) > 4 or _is_group(nxt):
                body = []
                j = i + 1
                while j < n and not _is_title(lines[j]) and not _is_group(lines[j]):
                    body.append(lines[j])
                    j += 1
                blocks.append({'group': group, 'title': line, 'body': body, 'at': i})
                i = j
                continue
        i += 1
    return blocks


def _signature(body: tuple[str, ...]) -> str:
    """正文指纹：只取汉字序列，繁简不归一（同一份粘贴的繁简是一致的）。"""
    return ''.join(HAN.findall(''.join(body)))


def parse(raw_text: str, overrides: dict[str, str] | None = None) -> Corpus:
    """把原始抓取文本还原成结构化语料。

    overrides: 篇名 -> 分组，用于登记自动归组判不准、需人工裁定的篇。文件里
    存在「整段粘贴挂到另一组尾部」的串台，纯启发式无法穷尽，故留此显式入口。
    """
    overrides = overrides or {}
    lines: list[str] = []
    residue: list[str] = []
    for ln in raw_text.splitlines():
        s = ln.strip()
        if not s:
            continue
        c, damaged = clean_line(s)
        if damaged:
            residue.append(s)
        lines.append(c)

    blocks = _split_blocks(lines)
    findings: list[str] = [
        f'原始文件 {len(lines)} 行被切成 {len(blocks)} 个诗篇块，'
        f'按正文指纹去重后保留 '
        f'{len({_signature(tuple(b["body"])) for b in blocks})} 篇'
    ]
    if residue:
        findings.append(f'{len(residue)} 行含表格/HTML 残留，已剥离标签，但脱字无法自动补全：'
                        + ' / '.join(r[:24] for r in residue[:5]))

    # 同一正文指纹 = 同一篇。正文过短无法定位的块不参与归并。
    usable = [b for b in blocks
              if len(_signature(tuple(b['body']))) >= MIN_BODY_CHARS]
    by_sig: dict[str, list[dict]] = {}
    for b in usable:
        by_sig.setdefault(_signature(tuple(b['body'])), []).append(b)

    # 第一级：正文指纹 -> 分组。跨粘贴多数表决；平票的交给覆盖表裁定。
    tied: list[str] = []
    rows: list[dict] = []
    for sig, occ in by_sig.items():
        votes = Counter(o['group'] for o in occ)
        ranked = votes.most_common()
        longest = max(occ, key=lambda o: len(_signature(tuple(o['body']))))
        name = longest['title']
        tie = len(ranked) > 1 and ranked[0][1] == ranked[1][1]
        # 覆盖表只在真正平票时生效：同名篇目（齐风《甫田》与小雅《甫田》）互不受影响
        if tie and name in overrides:
            group = overrides[name]
        else:
            group = ranked[0][0]
            if tie:
                tied.append(name)
        rows.append({'group': group, 'title': name, 'body': longest['body'],
                     'sig': sig, 'at': min(o['at'] for o in occ),
                     'groups': {o['group'] for o in occ}})

    if tied:
        findings.append('自动裁定失败、需登记覆盖表的平票篇目：' + '、'.join(tied))

    # 第二级：(分组, 篇名) 才是《诗经》真正的唯一篇目。同一篇在文件里有若干
    # 截断程度不同的版本，指纹互异，只能在这一层合并。
    merged: dict[tuple[str, str], dict] = {}
    for r in rows:
        key = (r['group'], r['title'])
        prev = merged.get(key)
        if prev is None:
            merged[key] = {**r, 'versions': 1}
        else:
            prev['versions'] += 1
            prev['at'] = min(prev['at'], r['at'])
            if len(r['sig']) > len(prev['sig']):
                prev.update(body=r['body'], sig=r['sig'])
    n_versions = sum(m['versions'] - 1 for m in merged.values())
    if n_versions:
        findings.append(f'{n_versions} 个重复版本已并入对应篇目'
                        f'（同一篇的截断版本指纹不同，按 (分组, 篇名) 合并取最长）')

    poems = list(merged.values())

    # 顺序：分组按其在文件中首次出现的次序，组内按最早出现位置
    group_order: dict[str | None, int] = {}
    for b in blocks:
        group_order.setdefault(b['group'], b['at'])
    poems.sort(key=lambda p: (group_order.get(p['group'], 1 << 30), p['at']))

    out: list[Poem] = []
    for i, p in enumerate(poems, 1):
        body = tuple(x for x in p['body'] if HAN.search(x))
        out.append(Poem(idx=i, group=p['group'], part=part_of(p['group']),
                        title=p['title'], stanzas=body,
                        versions=p['versions']))

    out, stitched = drop_stitched_stanzas(out)
    if stitched:
        findings.append('剔除跨篇粘贴串台的整章：' + '；'.join(
            f'《{t}》{n} 章（{why}）' for t, n, why in stitched))

    holes = [f'{p.title} 第{n}章「{s}」'
             for p in out for n, s in enumerate(p.stanzas, 1) if DROPPED.search(s)]
    if holes:
        findings.append(f'{len(holes)} 处连续标点，是原文件脱字留下的空洞：'
                        + ' / '.join(holes))
    repaired = _repair_dropped(out)
    findings += ['补字：' + r for r in repaired]

    return Corpus(poems=_renumber(out), findings=findings)


def _repair_dropped(poems: list[Poem]) -> list[str]:
    """按 REPAIRS 登记表补字，逐笔返回说明文字。原句片段不在了就什么都不做。"""
    done: list[str] = []
    for i, p in enumerate(poems):
        stanzas = list(p.stanzas)
        for find, repl, why in REPAIRS:
            for n, s in enumerate(stanzas):
                if find in s:
                    stanzas[n] = s.replace(find, repl)
                    done.append(f'{p.group}·{p.title} 第{n + 1}章：'
                                f'「{find}」→「{repl}」（{why}）')
        if stanzas != list(p.stanzas):
            poems[i] = Poem(p.idx, p.group, p.part, p.title, tuple(stanzas),
                            p.versions, p.book)
    return done


def _norm_stanza(stanza: str) -> str:
    from .clean import normalize
    return ''.join(HAN.findall(normalize(stanza)))


def _parallel(stanza: str, others: list[str]) -> float:
    """与同篇其他章的最高相似度——重章叠句的判据。"""
    a = _norm_stanza(stanza)
    best = 0.0
    for other in others:
        b = _norm_stanza(other)
        if not b:
            continue
        n = max(len(a), len(b))
        best = max(best, sum(1 for x, y in zip(a, b, strict=False) if x == y) / n)
    return best


MIN_STITCH_CHARS = 12
MIN_STITCH_PARALLEL = 0.5


def drop_stitched_stanzas(poems: list[Poem]) -> tuple[list[Poem], list[tuple[str, int, str]]]:
    """剔除"整章被粘到另一篇尾部"的串台。

    判定要同时满足三条，缺一即保留：同一整章（≥12 字）逐字出现在两篇之中；
    在待剔篇里位于结尾的连续段上；且与该篇自身的其他章不构成重章叠句。
    第三条是关键——《候人》三、四章与本篇第二章同框平行，是正本；
    《蓼莪》末二章与本篇父子之辞毫无平行，才是外来的。
    """
    keys: dict[str, set[int]] = {}
    for pi, p in enumerate(poems):
        for st in p.stanzas:
            key = _norm_stanza(st)
            if len(key) >= MIN_STITCH_CHARS:
                keys.setdefault(key, set()).add(pi)
    # 与他篇逐字相同的章，才可能是被粘过来的
    shared: dict[int, set[int]] = {}
    for key, pos in keys.items():
        if len(pos) >= 2:
            for pi in pos:
                shared.setdefault(pi, set()).add(key)

    drop: dict[int, set[int]] = {}
    notes: list[tuple[str, int, str]] = []
    for pi, p in enumerate(poems):
        if len(p.stanzas) < 3:
            continue  # 章数太少无从判断平行，一律保留
        foreign = {i for i, st in enumerate(p.stanzas)
                   if _norm_stanza(st) in shared.get(pi, set())}
        # 取结尾的连续外来段——粘贴串台的形态就是整段追加在后面
        run: list[int] = []
        for i in range(len(p.stanzas) - 1, -1, -1):
            if i in foreign:
                run.append(i)
            else:
                break
        if not run or len(run) == len(p.stanzas):
            continue  # 全篇与另一篇相同的是被粘的那本（如《大东》），保留
        rest = [st for i, st in enumerate(p.stanzas) if i not in run]
        if max(_parallel(p.stanzas[i], rest) for i in run) >= MIN_STITCH_PARALLEL:
            continue  # 与本篇构成重章叠句，是正本不是外来
        donors = '、'.join(sorted({poems[q].title
                                  for i in run
                                  for q in keys[_norm_stanza(p.stanzas[i])]
                                  if q != pi}))
        drop[pi] = set(run)
        notes.append((p.title, len(run),
                      f'与《{donors}》逐字相同、位于本篇尾部、且与本篇诸章无平行'))

    if not drop:
        return poems, notes
    out = []
    for pi, p in enumerate(poems):
        bad = drop.get(pi)
        if bad:
            p = Poem(p.idx, p.group, p.part, p.title,
                     tuple(s for k, s in enumerate(p.stanzas) if k not in bad),
                     p.versions)
        out.append(p)
    return out, notes


def _renumber(poems: list[Poem]) -> list[Poem]:
    return [Poem(i, p.group, p.part, p.title, p.stanzas, p.versions)
            for i, p in enumerate(poems, 1)]


def load_raw(path: str | Path = 'data/raw/shijing.txt') -> str:
    return Path(path).read_text(encoding='utf-8')


def load_overrides(path: str | Path = 'data/overrides.json') -> dict[str, str]:
    """读覆盖表；`_` 开头的键是说明文字，不作为篇名。"""
    if not Path(path).exists():
        return {}
    raw = json.loads(Path(path).read_text(encoding='utf-8'))
    return {k: v['group'] for k, v in raw.items()
            if not k.startswith('_') and isinstance(v, dict) and 'group' in v}


def build(raw_path: str | Path = 'data/raw/shijing.txt',
          overrides_path: str | Path = 'data/overrides.json') -> Corpus:
    return parse(load_raw(raw_path), load_overrides(overrides_path))


def to_dict(c: Corpus) -> dict:
    return {
        'poems': [{'idx': p.idx, 'group': p.group, 'part': p.part, 'title': p.title,
                   'stanzas': list(p.stanzas), 'versions': p.versions, 'book': p.book}
                  for p in c.poems],
        'findings': c.findings,
        'stats': {'poems': len(c.poems), 'chars': c.total_chars,
                  'books': c.books},
    }


def save(c: Corpus, path: str | Path) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(to_dict(c), ensure_ascii=False, indent=1),
                          encoding='utf-8')


def load(path: str | Path) -> Corpus:
    d = json.loads(Path(path).read_text(encoding='utf-8'))
    return Corpus(
        poems=[Poem(idx=p['idx'], group=p['group'], part=p['part'], title=p['title'],
                    stanzas=tuple(p['stanzas']), versions=p.get('versions', 1),
                    book=p.get('book', '诗经'))
               for p in d['poems']],
        findings=d.get('findings', []),
    )

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

HAN = re.compile(r'[一-鿿]')
# 诗经篇名最长者〈昊天有成命〉五字；放宽到 6 以容纳繁简混排下的写法
TITLE_MAX = 6
TITLE = re.compile(rf'[一-鿿]{{1,{TITLE_MAX}}}$')
PU = re.compile(r'[，。！？；：、,.!?;:]')
HTML_RESIDUE = re.compile(r'</?[a-zA-Z][^>]*>?|/td>|/tr>|&#\d+;')

# 分组标题的繁体写法
GROUP_NORM = str.maketrans({'頌': '颂', '魯': '鲁', '國': '国', '風': '风'})
MIN_BODY_CHARS = 8


@dataclass(frozen=True)
class Poem:
    idx: int
    group: str
    part: str          # 国风 / 小雅 / 大雅 / 周颂 / 鲁颂 / 商颂
    title: str
    stanzas: tuple[str, ...]
    versions: int = 1  # 合并进来的重复版本数

    @property
    def chars(self) -> int:
        return sum(len(HAN.findall(s)) for s in self.stanzas)

    def __hash__(self):
        return hash((self.group, self.title))


@dataclass
class Corpus:
    poems: list[Poem]
    findings: list[str] = field(default_factory=list)

    @property
    def total_chars(self) -> int:
        return sum(p.chars for p in self.poems)

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
    return Corpus(poems=out, findings=findings)


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
                   'stanzas': list(p.stanzas), 'versions': p.versions}
                  for p in c.poems],
        'findings': c.findings,
        'stats': {'poems': len(c.poems), 'chars': c.total_chars},
    }


def save(c: Corpus, path: str | Path) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(to_dict(c), ensure_ascii=False, indent=1),
                          encoding='utf-8')


def load(path: str | Path) -> Corpus:
    d = json.loads(Path(path).read_text(encoding='utf-8'))
    return Corpus(
        poems=[Poem(idx=p['idx'], group=p['group'], part=p['part'], title=p['title'],
                    stanzas=tuple(p['stanzas']), versions=p.get('versions', 1))
               for p in d['poems']],
        findings=d.get('findings', []),
    )

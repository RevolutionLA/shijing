"""文本规范化：繁简归一与标点处理。

统计口径一律走归一后的字形（否则「風」与「风」会被记成两个字），而语料存档与展示
一律保留原文。归一表是冻结在 data/t2s.tsv 里的静态文件，覆盖 CJK 基本区全部繁简
有别的常用字，因此运行时不需要 opencc / zhconv 之类的依赖，繁体输入的检索也能
命中简体正文，且每一个映射都可人工核对。
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from .corpus import HAN
from .paths import DATA_DIR

PUNCT = '，。！？；：、》《「」『』（）·…—～'


@lru_cache(maxsize=1)
def _table() -> dict[str, str]:
    p = DATA_DIR / 't2s.tsv'
    if not p.exists():
        return {}
    out = {}
    for line in p.read_text(encoding='utf-8').splitlines():
        if not line or line.startswith('#'):
            continue
        src, dst = line.split('\t')
        if src != dst:
            out[src] = dst
    return out


def normalize(text: str) -> str:
    """繁体 -> 简体（仅语料用字表内）。表外的字原样返回。"""
    t = _table()
    return ''.join(t.get(c, c) for c in text)


def strip_punct(text: str) -> str:
    """只留汉字，用于统计与指纹。"""
    return ''.join(HAN.findall(text))


def han_only(text: str) -> list[str]:
    return HAN.findall(text)


def regenerate_table(corpus_text: str = '', out: str | Path = 'data/t2s.tsv',
                     full: bool = True) -> int:
    """生成繁->简映射并冻结到仓库。这是构建期脚本，不是运行期依赖。

    full=True 覆盖 CJK 基本区全部字符（繁体检索才能命中简体正文）；
    否则只覆盖语料实际用字。改语料后重跑一次，产出可 diff、可人工审。
    """
    from zhconv import convert  # 仅构建期需要
    chars = ([chr(i) for i in range(0x4e00, 0x9FFF + 1)] if full
             else sorted(set(han_only(corpus_text))))
    rows = []
    for c in chars:
        s = convert(c, 'zh-hans')
        rows.append((c, s if len(s) == 1 else c))
    rows = [(a, b) for a, b in rows if a != b]
    Path(out).write_text(
        '# 繁->简归一表，由 `shijing build --regen-t2s` 生成，运行时不依赖 zhconv。\n'
        '# 只登记繁简有别的字；identity 映射不写入。人工核对即可整表审读。\n'
        + ''.join(f'{a}\t{b}\n' for a, b in rows),
        encoding='utf-8')
    _table.cache_clear()
    return len(rows)

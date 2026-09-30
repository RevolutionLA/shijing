"""多典籍注册表，以及散文典籍（四书）的解析。

《诗经》那一套 build 是从「脏网页表格」里逆向修复出 305 篇，启发式全部为四言诗定制；
四书用的是 chinese-poetry 已经结构化的 JSON（篇 → 段列表），不需要任何修复，只需要
落进同一个模型：`title` 是篇名、`stanzas` 是段。两者共用 `Poem`/`Corpus`，但能做的
分析不同，所以每本典籍都标了文体（verse 韵文 / prose 散文），由 CLI 门控。
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .corpus import Corpus, Poem
from .paths import DATA_DIR

VERSE = 'verse'   # 韵文：重章叠句、韵脚这类结构分析才有意义
PROSE = 'prose'   # 散文：只有篇章、字频、检索、读音


@dataclass(frozen=True)
class Book:
    name: str            # 典籍名，语料里 Poem.book 用它
    slug: str            # 目录名 / 命令行可写的英文名
    kind: str            # VERSE | PROSE
    corpus_rel: str      # 结构化语料（相对 data/）
    raw_rel: str | None = None    # 重建输入；None 表示只能从结构化语料读

    @property
    def is_verse(self) -> bool:
        return self.kind == VERSE


BOOKS: dict[str, Book] = {
    b.name: b for b in (
        Book('诗经', 'shijing', VERSE, 'corpus.json', 'raw/shijing.txt'),
        Book('论语', 'lunyu', PROSE, 'books/lunyu/corpus.json', 'books/lunyu/raw.json'),
        Book('孟子', 'mengzi', PROSE, 'books/mengzi/corpus.json', 'books/mengzi/raw.json'),
        Book('大学', 'daxue', PROSE, 'books/daxue/corpus.json', 'books/daxue/raw.json'),
        Book('中庸', 'zhongyong', PROSE, 'books/zhongyong/corpus.json',
             'books/zhongyong/raw.json'),
    )
}

# 语料里已有、但还没并进来的典籍不在此表；四书齐了之后五经仍受许可限制（见 data/README.md）
ALIASES = {b.slug: b.name for b in BOOKS.values()}


def get(sel: str) -> Book:
    """按典籍名或 slug 取书目。取不到就把可选清单报出来，别让人猜。"""
    key = (sel or '').strip()
    book = BOOKS.get(key) or BOOKS.get(ALIASES.get(key, ''))
    if book is None:
        raise SystemExit(f'不认识的典籍 {sel!r}；可选：'
                         + '、'.join(f'{b.name}({b.slug})' for b in BOOKS.values()))
    return book


def corpus_path(book: Book) -> Path:
    return DATA_DIR / book.corpus_rel


def raw_path(book: Book) -> Path:
    if not book.raw_rel:
        raise SystemExit(f'{book.name} 没有登记重建输入')
    return DATA_DIR / book.raw_rel


def parse_prose(name: str, data: object) -> Corpus:
    """把 {"chapter": 篇名, "paragraphs": [段…]} 的列表（或单篇对象）读成语料。

    段就是这里的「章」——沿用上游数据的分段，不重新切句：《孟子》上游分 690 段，
    与赵岐注的传统 261 章不是一回事，口径差异记在 README 的诚实边界里。
    """
    items = data if isinstance(data, list) else [data]
    poems = []
    for i, it in enumerate(items, 1):
        title = str(it['chapter']).strip()
        stanzas = tuple(s.strip() for s in it['paragraphs'] if s and s.strip())
        if not stanzas:
            raise SystemExit(f'{name}·{title} 没有正文，数据可能有缺')
        poems.append(Poem(idx=i, group=name, part=name, title=title,
                          stanzas=stanzas, book=name))
    return Corpus(poems=poems, findings=[f'{name}：{len(poems)} 篇，'
                                        f'{sum(len(p.stanzas) for p in poems)} 段'])


def build(book: Book) -> Corpus:
    """按典籍重建结构化语料。诗经仍走 corpus.build（表格修复）。"""
    if book.is_verse:
        from . import corpus as corpus_mod
        # 走 DATA_DIR 绝对路径：pytest 的 cwd 不是仓库根，相对默认值会找不到原文件
        return corpus_mod.build(raw_path(book), DATA_DIR / 'overrides.json')
    raw = json.loads(raw_path(book).read_text(encoding='utf-8'))
    return parse_prose(book.name, raw)


def load(book: Book) -> Corpus:
    from . import corpus as corpus_mod
    return corpus_mod.load(corpus_path(book))


def load_all(names: list[str] | None = None) -> Corpus:
    """合并多本典籍，供跨书检索与候选名核验使用。

    只合并已构建好的典籍；缺哪本就跳过并在 findings 里说明，不硬要求一次备齐。
    """
    from . import corpus as corpus_mod
    poems, findings = [], []
    for book in (BOOKS[n] for n in names) if names else BOOKS.values():
        p = corpus_path(book)
        if not p.exists():
            findings.append(f'{book.name}：语料未构建（`shijing --book {book.slug} build`）')
            continue
        poems.extend(corpus_mod.load(p).poems)
    if not poems:
        raise SystemExit('没有任何已构建的典籍可合并；先跑 `shijing build`')
    return Corpus(poems=poems, findings=findings)


def need_verse(c: Corpus, feature: str) -> None:
    """非纯诗经语料上拒绝跑韵文专属分析，并说清原因。

    判据看的是语料本身而不是命令行参数：`--corpus` 指到别的文件、或 `--book all`
    合并过多本时同样拦得住，避免「参数说诗经、数据是散文」这种错配静默出数。
    """
    if c.books != ['诗经']:
        raise SystemExit(
            f'{feature}是韵文口径的分析，当前语料是{"、".join(c.books)}；'
            '诗经的重章叠句结构与逐句韵脚标注（按 305 篇键控）在散文典籍上都不成立。')

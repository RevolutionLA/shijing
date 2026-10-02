"""命令行入口。"""
from __future__ import annotations

import argparse
import csv
import io
import json
import sys
from pathlib import Path

from . import __version__, analyze, ancient, books, clean, naming, paths, refrain, rhyme, visuals
from . import corpus as corpus_mod

CORPUS = Path('data/corpus.json')
RAW = Path('data/raw/shijing.txt')
OVERRIDES = Path('data/overrides.json')


def locate(rel: str | Path) -> Path:
    """先按当前目录找，再回退到仓库根，使 CLI 在任意工作目录下都可用。"""
    return paths.locate(rel)


def load_corpus(args, default_book: str = '诗经') -> corpus_mod.Corpus:
    """按 `--book` 取语料；`--corpus` 显式给路径时以路径为准（老用法不变）。

    兜底书名必须由调用方给，不能用子命令 `set_defaults(book=...)`：argparse 会把
    子命令的默认值盖到父级已显式传入的 `--book` 上，用户就再也限不回单本了。
    """
    sel = getattr(args, 'book', None) or default_book
    if sel == 'all':
        return books.load_all()
    book = books.get(sel)
    path = locate(args.corpus) if getattr(args, 'corpus', None) else books.corpus_path(book)
    if path.exists():
        return corpus_mod.load(path)
    print(f'{path} 不存在，先重建《{book.name}》。', file=sys.stderr)
    return books.build(book)


def emit(rows, fmt: str, columns: list[str] | None = None) -> None:
    if fmt == 'json':
        print(json.dumps(rows, ensure_ascii=False, indent=1))
        return
    if fmt == 'csv':
        buf = io.StringIO()
        cols = columns or (list(rows[0].keys()) if rows else [])
        w = csv.DictWriter(buf, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
        print(buf.getvalue(), end='')
        return
    cols = columns or (list(rows[0].keys()) if rows else [])
    if not rows or not cols:
        return
    widths = [max(len(c), *(len(str(r.get(c, ''))) for r in rows)) for c in cols]
    print('  '.join(str(c).ljust(w) for c, w in zip(cols, widths, strict=False)))
    print('  '.join('-' * w for w in widths))
    for r in rows:
        print('  '.join(str(r.get(c, '')).ljust(w) for c, w in zip(cols, widths, strict=False)))


def cmd_build(args) -> int:
    book = books.get(args.book or '诗经')
    if book.is_verse:
        c = corpus_mod.build(locate(args.raw), locate(args.overrides))
    else:
        c = books.build(book)
    out = Path(args.out) if args.out else books.corpus_path(book)
    corpus_mod.save(c, out)
    print(f'已写出 {out}：{len(c.poems)} 篇，{c.total_chars} 字')
    if args.regen_t2s:
        n = clean.regenerate_table(c.text(), args.t2s_out)
        print(f'已重建繁简归一表 {args.t2s_out}：{n} 条映射')
    for f in c.findings:
        print(' ·', f)
    return 0


def _scope(c, poem: str | None):
    if not poem:
        return c
    hits = [p for p in c.poems if poem in f'{p.group}·{p.title}' or poem == p.title]
    if not hits:
        raise SystemExit(f'找不到篇目：{poem}')
    return corpus_mod.Corpus(poems=hits, findings=[])


def cmd_chars(args) -> int:
    c = _scope(load_corpus(args), args.poem)
    stats = analyze.char_stats(c)[:args.top]
    emit([s.row() for s in stats], args.format, ['token', 'freq', 'rate', 'poems', 'cover'])
    return 0


def cmd_words(args) -> int:
    c = _scope(load_corpus(args), args.poem)
    stats = analyze.word_stats(c, drop_stopwords=not args.keep_stopwords)[:args.top]
    emit([s.row() for s in stats], args.format, ['token', 'freq', 'rate', 'poems', 'cover'])
    return 0


def cmd_refrain(args) -> int:
    c = load_corpus(args)
    if args.what == 'parallel':
        books.need_verse(c, '重章叠句')
        rows = [r.row() for r in refrain.parallelism(c)[:args.top]]
        cols = ['idx', 'group', 'title', 'stanzas', 'best', 'score']
    elif args.what == 'redup':
        rows = [r.row() for r in refrain.reduplications(c)[:args.top]]
        cols = ['token', 'freq', 'poems']
    else:
        rows = [{'line': k, 'poems': n, 'where': '、'.join(v[:6])}
                for k, n, v in refrain.shared_lines(c, args.min_poems)[:args.top]]
        cols = ['line', 'poems', 'where']
    emit(rows, args.format, cols)
    return 0


def cmd_rhyme(args) -> int:
    c = load_corpus(args)
    books.need_verse(c, '韵脚')
    if args.system == 'ancient':
        return cmd_rhyme_ancient(args, c)
    skip = not args.keep_particles
    if args.poem:
        p = _scope(c, args.poem).poems[0]
        one = corpus_mod.Corpus(poems=[p], findings=[])
        sch = rhyme.schemes(one, skip)
        if not sch:
            raise SystemExit('该篇未能取到句末字')
        print(f'{p.group}·{p.title}  韵式 {sch[0].scheme}  '
              f'韵部 {sch[0].groups}  换韵 {sch[0].turns}')
        for ch, f, letter in zip(rhyme.line_endings(p, skip), sch[0].finals, sch[0].scheme, strict=True):
            print(f'  {ch}  {f:<8} {letter}')
        return 0
    if args.what == 'summary':
        print(json.dumps(rhyme.summary(c, skip), ensure_ascii=False, indent=1))
        return 0
    rs = sorted(rhyme.schemes(c, skip), key=lambda r: (-r.turns, r.poem.idx))
    emit([r.row() for r in rs[:args.top]], args.format,
         ['idx', 'group', 'title', 'lines', 'groups', 'turns', 'scheme'])
    return 0


def cmd_rhyme_ancient(args, c) -> int:
    """上古音口径：韵脚取自 Baxter《上古音手册》押韵字表，不是推断。"""
    path = args.rhyme_data
    if args.poem:
        p = _scope(c, args.poem).poems[0]
        one = corpus_mod.Corpus(poems=[p], findings=[])
        sch = ancient.schemes(one, path)
        if not sch:
            raise SystemExit('该篇在韵脚表中没有对应记录')
        s = sch[0]
        print(f'{p.group}·{p.title}  韵式 {s.scheme}')
        print(f'  {s.lines} 句 / 入韵 {s.rhyming} 句 ({s.rate:.1%}) / '
              f'韵类 {s.groups} / 换韵 {s.turns} / 句中韵 {s.internal}')
        for cl, letter in zip(s.clauses,
                              [m for m in s.scheme if m != '|'], strict=False):
            if cl.rhyme_chars:
                where = ''.join(f'{c}@{i}' for c, i in
                                zip(cl.rhyme_chars, cl.positions, strict=True))
                print(f'  {letter}  {cl.text}   韵脚 {where}')
            else:
                print(f'  ·  {cl.text}   （不入韵）')
        return 0
    if args.what == 'verify':
        print(json.dumps(ancient.verify(c, path), ensure_ascii=False, indent=1))
        return 0
    if args.what == 'compare':
        print(json.dumps(ancient.compare_modern(c, path),
                         ensure_ascii=False, indent=1))
        return 0
    if args.what == 'summary':
        print(json.dumps(ancient.summary(c, path), ensure_ascii=False, indent=1))
        return 0
    rs = sorted(ancient.schemes(c, path), key=lambda r: (-r.turns, r.poem_idx))
    emit([r.row() for r in rs[:args.top]], args.format,
         ['idx', 'group', 'title', 'lines', 'rhyming', 'rate', 'groups',
          'turns', 'internal', 'scheme'])
    return 0


def cmd_cloud(args) -> int:
    c = load_corpus(args)
    stats = (analyze.char_stats(c) if args.kind == 'char'
             else analyze.word_stats(c))
    freq = analyze.frequencies(stats[:args.top])
    out = visuals.make_cloud(freq, args.out, font=args.font, max_words=args.top,
                             title=f'《{"、".join(c.books)}》'
                                   f'{"字云" if args.kind == "char" else "词云"}'
                                   f'（{len(c.poems)} 篇，{c.total_chars} 字）')
    print(f'已写出 {out}')
    return 0


def _window(line: str, query: str, width: int = 60) -> str:
    """命中处的展示窗口。

    诗经一句最多十几字，四书一段能有几百字，直接进表格会糊成一片。归一表是逐字
    一对一映射，所以归一文与原文的下标对齐，可以放心用命中位置切原文。
    """
    if len(line) <= width:
        return line
    ns, nq = clean.normalize(line), clean.normalize(query)
    i = ns.find(nq)
    if i < 0:
        return line[:width] + '…'
    half = max((width - len(nq)) // 2, 1)
    lo, hi = max(0, i - half), min(len(line), i + len(nq) + half)
    return ('…' if lo > 0 else '') + line[lo:hi] + ('…' if hi < len(line) else '')


def cmd_search(args) -> int:
    c = load_corpus(args)
    q = clean.normalize(args.query)
    rows = []
    for p in c.poems:
        for n, s in enumerate(p.stanzas, 1):
            if q in clean.normalize(s):
                rows.append({'book': p.book, 'group': p.group, 'title': p.title,
                             'stanza': n, 'line': s.strip()})
    cols = ['book', 'group', 'title', 'stanza', 'line']
    if not rows:
        # 机器口径必须仍是合法结构：json 出 []，csv 出表头，只有 table 说人话
        if args.format == 'json':
            emit([], 'json')
        elif args.format == 'csv':
            emit([], 'csv', cols)
        else:
            print('没有命中。')
        return 0
    if args.format == 'table':
        rows = [{**r, 'line': _window(r['line'], args.query)} for r in rows]
    emit(rows[:args.top], args.format, cols)
    return 0


def _zh(rows: list[dict], mapping: dict) -> list[dict]:
    """表格输出用中文表头，--format json 仍保留英文键供脚本使用。"""
    return [{mapping[k]: v for k, v in r.items() if k in mapping} for r in rows]


def _where(row: dict) -> str:
    """命中位置的书名标记。散文典籍的分组名就是书名，不再重复一遍。"""
    part = f'{row["group"]}·{row["title"]}'
    return part if part.startswith(row['book']) else f'{row["book"]}·{part}'


# 诗经最长的一篇《閟宫》613 字，超过这个长度的一定是散文典籍的整篇（四书最短的
# 一《篇》也有 482 字，但《孟子》平均 3100 字）。语境只印命中章，否则终端刷不完。
FULL_CONTEXT = 650


def _context_lines(cx: dict) -> tuple[str, ...]:
    if sum(len(s) for s in cx['stanzas']) <= FULL_CONTEXT:
        return tuple(cx['stanzas'])
    return tuple(f'第{n}章：{cx["stanzas"][n - 1]}' for n in cx['matched'])


def cmd_name(args) -> int:
    # 取名默认跨典籍查出处：「论语 + 诗经」本来就是姓名的两大来源，只查一半会说谎
    c = load_corpus(args, 'all')
    data = naming.inspect(c, args.query, with_context=not args.no_context)
    scope = '、'.join(data['corpus']['books'])
    if args.format != 'table':
        emit(data, args.format)
        return 0
    print(f'候选：{data["query"]}    连用命中 {data["hit_count"]} 处'
          f'    检索范围：{scope}（{data["corpus"]["poems"]} 篇）')
    hits = _zh(data['hits'], {'book': '典籍', 'group': '分组', 'title': '篇名',
                              'stanza': '章', 'line': '原句'})
    for r, raw in zip(hits, data['hits'], strict=True):
        r['原句'] = _window(raw['line'], args.query)
    emit(hits[:args.top], 'table', ['典籍', '分组', '篇名', '章', '原句'])
    if not data['hits']:
        print(f'  {scope}里没有这两个字连用的句子——单字都有，也可能只是拼凑。')
        print('\n单字出处：')
        for cs in data['char_sources']:
            if not cs['count']:
                print(f'  {cs["char"]}：{scope}全库未见此字。')
                continue
            shown = cs['examples'][:args.top]
            if cs['count'] > len(shown):
                print(f'  {cs["char"]}：（共 {cs["count"]} 处，列前 {len(shown)}）')
            else:
                print(f'  {cs["char"]}：')
            for r in shown:
                print(f'    {_where(r)} 第{r["stanza"]}章：'
                      f'{_window(r["line"], cs["char"])}')
    print('\n用字：')
    chars = _zh(data['chars'], {'char': '字', 'freq': '次数', 'poems': '所见篇数',
                                'tier': '档位'})
    for r, raw in zip(chars, data['chars'], strict=True):
        r['备注'] = '虚词' if raw['function'] else ''
    emit(chars, 'table', ['字', '次数', '所见篇数', '档位', '备注'])
    print('\n读音（普通话）：')
    syls = _zh(data['reading'], {'char': '字', 'pinyin': '拼音', 'tone': '声调',
                                 'initial': '声母', 'final': '韵母'})
    for r, raw in zip(syls, data['reading'], strict=True):
        r['又读'] = '、'.join(raw['also'])
    emit(syls, 'table', ['字', '拼音', '声调', '声母', '韵母', '又读'])
    for link in data['links']:
        print(' ', link)
    if data['contexts']:
        shown = data['contexts'][:args.max_context]
        left = len(data['contexts']) - len(shown)
        head = f'\n语境（必须自己读，代码不判吉凶，共 {len(data["contexts"])} 篇）：'
        print(head)
        for cx in shown:
            print(f'  {_where(cx)}')
            for s in _context_lines(cx):
                print(f'    {s}')
            whole = sum(len(s) for s in cx['stanzas'])
            if whole > FULL_CONTEXT:
                print(f'    （{_where(cx)} 全篇 {len(cx["stanzas"])} 章 {whole} 字，'
                      f'此处只印命中章；通读请用 shijing --book {cx["book"]} '
                      f'show {cx["title"]}）')
        if left:
            print(f'  …余 {left} 篇请用 shijing show 篇名 读，或加大 --max-context')
    print(f'\n{data["note"]}')
    return 0


def cmd_show(args) -> int:
    c = load_corpus(args)
    for p in _scope(c, args.poem).poems:
        print(f'{p.group}·{p.title}  （{len(p.stanzas)} 章）')
        for s in p.stanzas:
            print(' ', s)
    return 0


def cmd_report(args) -> int:
    c = load_corpus(args)
    per: dict[str, int] = {}
    for p in c.poems:
        per[p.group] = per.get(p.group, 0) + 1
    cs = analyze.char_stats(c)
    out = {
        '典籍': c.books,
        '篇数': len(c.poems),
        '字数': c.total_chars,
        '不重复单字': len(cs),
        '分组': per,
        '高频字前10': [s.token for s in cs[:10]],
        '集中度': [f'{int(k * 100)}% 由前 {n} 个字覆盖' for k, n in analyze.coverage(cs)],
        'Zipf决定系数': round(analyze.zipf_r2(cs), 4),
    }
    if c.books == ['诗经']:
        # 复沓与韵脚都建立在诗经的重章叠句结构上，散文典籍跑这些只会得出无意义数字
        out['复沓'] = refrain.summary(c)
        out['韵脚_上古音'] = ancient.summary(c)
        out['韵脚_今音对照'] = ancient.compare_modern(c)
        out['韵脚_今音口径'] = rhyme.summary(c)
    else:
        red = refrain.reduplications(c)
        out['叠字'] = {'总次': sum(r.freq for r in red), '种类': len(red)}
        out['跨篇复现句'] = len(refrain.shared_lines(c))
    out['语料修复记录'] = c.findings
    print(json.dumps(out, ensure_ascii=False, indent=1))
    return 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog='shijing',
                                 description='《诗经》与四书的语料与统计分析')
    ap.add_argument('--version', action='version', version=f'shijing {__version__}')
    ap.add_argument('--book', default=None, metavar='典籍',
                    help='语料范围：诗经（默认）、论语/孟子/大学/中庸、all 合并全部已构建；'
                         'name 命令默认 all')
    ap.add_argument('--corpus', default=None, help='直接指定结构化语料 JSON 路径（覆盖 --book）')
    sub = ap.add_subparsers(dest='cmd', required=True)

    def common(sp, top=30, poem=True):
        sp.add_argument('--format', choices=['table', 'json', 'csv'], default='table')
        sp.add_argument('--top', type=int, default=top)
        if poem:
            sp.add_argument('--poem', help='限定到某篇（可用 国风·周南·关雎 或 关雎）')

    b = sub.add_parser('build', help='从原始文本重建语料')
    b.add_argument('--raw', default=str(RAW))
    b.add_argument('--overrides', default='data/overrides.json')
    b.add_argument('--out', default=None, help='默认写到该典籍自己的语料路径')
    b.add_argument('--regen-t2s', action='store_true', help='重建繁简归一表（需 zhconv）')
    b.add_argument('--t2s-out', default='data/t2s.tsv')
    b.set_defaults(fn=cmd_build)

    sp = sub.add_parser('chars', help='字频')
    common(sp)
    sp.set_defaults(fn=cmd_chars)

    sp = sub.add_parser('words', help='词频（jieba 分词）')
    common(sp)
    sp.add_argument('--keep-stopwords', action='store_true', help='保留虚词与套语')
    sp.set_defaults(fn=cmd_words)

    sp = sub.add_parser('refrain', help='复沓：重章叠句 / 叠字 / 跨篇套语')
    sp.add_argument('--what', choices=['parallel', 'redup', 'shared'], default='parallel')
    sp.add_argument('--min-poems', type=int, default=2)
    common(sp, poem=False)
    sp.set_defaults(fn=cmd_refrain)

    sp = sub.add_parser('rhyme', help='韵脚：上古音口径（默认，取权威标注）或今音口径')
    sp.add_argument('--system', choices=['ancient', 'modern'], default='ancient',
                    help='ancient=Baxter《上古音手册》押韵字表；modern=今音韵母归类')
    sp.add_argument('--what', choices=['summary', 'table', 'compare', 'verify'],
                    default='table',
                    help='compare 与 verify 仅上古口径：前者量化今音失真，'
                         '后者把语料与韵脚表原文逐字对照')
    sp.add_argument('--rhyme-data', default=str(ancient.DEFAULT_PATH),
                    help='韵脚表路径（CC-BY-4.0，见 data/README.md）')
    sp.add_argument('--keep-particles', action='store_true',
                    help='仅今音口径：句末语助字（之/兮…）也当韵脚，默认跳过')
    common(sp)
    sp.set_defaults(fn=cmd_rhyme)

    sp = sub.add_parser('cloud', help='字云 / 词云出图')
    sp.add_argument('--kind', choices=['char', 'word'], default='word')
    sp.add_argument('--out', default='out/cloud.png')
    sp.add_argument('--font', help='中文字体路径，默认自动探测')
    sp.add_argument('--top', type=int, default=300)
    sp.set_defaults(fn=cmd_cloud)

    sp = sub.add_parser('search', help='全文检索')
    sp.add_argument('query')
    common(sp, top=50, poem=False)
    sp.set_defaults(fn=cmd_search)

    sp = sub.add_parser('name', help='候选名核验：出处、语境、用字档位、普通话读音')
    sp.add_argument('query', help='候选的名字，如 令仪 / 之恒 / 德棣')
    sp.add_argument('--format', choices=['table', 'json'], default='table')
    sp.add_argument('--top', type=int, default=3,
                    help='命中句与单字出处各最多列几条（默认 3）')
    sp.add_argument('--no-context', action='store_true', help='不打印整首诗')
    sp.add_argument('--max-context', type=int, default=3,
                    help='最多打印几首命中诗的全文（默认 3）')
    sp.set_defaults(fn=cmd_name)

    sp = sub.add_parser('show', help='打印篇目原文')
    sp.add_argument('poem')
    sp.set_defaults(fn=cmd_show)

    rp = sub.add_parser('report', help='一次性输出全部指标')
    rp.set_defaults(fn=cmd_report, format='json', top=30)
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.fn(args)
    except KeyboardInterrupt:
        return 130


if __name__ == '__main__':
    raise SystemExit(main())

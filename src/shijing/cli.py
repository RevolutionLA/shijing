"""命令行入口。"""
from __future__ import annotations

import argparse
import csv
import io
import json
import sys
from pathlib import Path

from . import analyze, clean, refrain, rhyme, visuals
from . import corpus as corpus_mod

CORPUS = Path('data/corpus.json')
RAW = Path('data/raw/shijing.txt')
OVERRIDES = Path('data/overrides.json')


def locate(rel: str | Path) -> Path:
    """先按当前目录找，再回退到仓库根，使 CLI 在任意工作目录下都可用。"""
    rel = Path(rel)
    if rel.is_absolute():
        return rel
    here = Path(__file__).resolve()
    for base in [Path.cwd(), *here.parents[2:4]]:
        cand = base / rel
        if cand.exists():
            return cand
    return Path.cwd() / rel


def load_corpus(args) -> corpus_mod.Corpus:
    path = locate(args.corpus)
    if path.exists():
        return corpus_mod.load(path)
    print(f'{path} 不存在，先从 {locate(RAW)} 重建。', file=sys.stderr)
    return corpus_mod.build(locate(RAW), locate(OVERRIDES))


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
    if not cols:
        return
    widths = [max(len(c), *(len(str(r.get(c, ''))) for r in rows)) for c in cols]
    print('  '.join(str(c).ljust(w) for c, w in zip(cols, widths, strict=False)))
    print('  '.join('-' * w for w in widths))
    for r in rows:
        print('  '.join(str(r.get(c, '')).ljust(w) for c, w in zip(cols, widths, strict=False)))


def cmd_build(args) -> int:
    c = corpus_mod.build(locate(args.raw), locate(args.overrides))
    out = Path(args.out)
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


def cmd_cloud(args) -> int:
    c = load_corpus(args)
    stats = (analyze.char_stats(c) if args.kind == 'char'
             else analyze.word_stats(c))
    freq = analyze.frequencies(stats[:args.top])
    out = visuals.make_cloud(freq, args.out, font=args.font, max_words=args.top,
                             title=f'《诗经》{args.kind == "char" and "字云" or "词云"}'
                                   f'（{len(c.poems)} 篇，{c.total_chars} 字）')
    print(f'已写出 {out}')
    return 0


def cmd_search(args) -> int:
    c = load_corpus(args)
    q = clean.normalize(args.query)
    rows = []
    for p in c.poems:
        for n, s in enumerate(p.stanzas, 1):
            ns = clean.normalize(s)
            if q in ns:
                rows.append({'group': p.group, 'title': p.title, 'stanza': n,
                             'line': s.strip()})
    if not rows:
        print('没有命中。')
    emit(rows[:args.top], args.format, ['group', 'title', 'stanza', 'line'])
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
        '篇数': len(c.poems),
        '字数': c.total_chars,
        '不重复单字': len({ch for ch in clean.normalize(c.text()) if '一' <= ch <= '鿿'}),
        '分组': per,
        '高频字前10': [s.token for s in cs[:10]],
        '集中度': [f'{int(k * 100)}% 由前 {n} 个字覆盖' for k, n in analyze.coverage(cs)],
        'Zipf决定系数': round(analyze.zipf_r2(cs), 4),
        '复沓': refrain.summary(c),
        '韵脚': rhyme.summary(c),
        '语料修复记录': c.findings,
    }
    print(json.dumps(out, ensure_ascii=False, indent=1))
    return 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog='shijing', description='《诗经》语料与统计分析')
    ap.add_argument('--corpus', default=str(CORPUS), help='结构化语料 JSON 路径')
    sub = ap.add_subparsers(dest='cmd', required=True)

    def common(sp, top=30, poem=True):
        sp.add_argument('--format', choices=['table', 'json', 'csv'], default='table')
        sp.add_argument('--top', type=int, default=top)
        if poem:
            sp.add_argument('--poem', help='限定到某篇（可用 国风·周南·关雎 或 关雎）')

    b = sub.add_parser('build', help='从原始文本重建语料')
    b.add_argument('--raw', default=str(RAW))
    b.add_argument('--overrides', default='data/overrides.json')
    b.add_argument('--out', default=str(CORPUS))
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

    sp = sub.add_parser('rhyme', help='韵脚（今音口径，见模块说明的边界）')
    sp.add_argument('--what', choices=['summary', 'table'], default='table')
    sp.add_argument('--keep-particles', action='store_true',
                    help='句末语助字（之/兮…）也当韵脚，默认跳过')
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

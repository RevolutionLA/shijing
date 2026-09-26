from __future__ import annotations

from shijing import analyze, refrain, rhyme


def test_之是最高频字(corpus):
    top = analyze.char_stats(corpus)[0]
    assert top.token == '之'
    assert top.freq > 900


def test_字频按频次降序(corpus):
    stats = analyze.char_stats(corpus)
    assert all(a.freq >= b.freq for a, b in zip(stats, stats[1:], strict=False))


def test_频率求和为一(corpus):
    stats = analyze.char_stats(corpus)
    assert abs(sum(s.rate for s in stats) - 1) < 1e-6


def test_篇目覆盖率在零一之间(corpus):
    for s in analyze.char_stats(corpus)[:20]:
        assert 0 < s.cover <= 1


def test_符合字频长尾分布(corpus):
    # Zipf 拟合优度：自然语言字频应高度线性；数据被重复污染时这个值会明显变差
    assert analyze.zipf_r2(analyze.char_stats(corpus)) > 0.93


def test_高频字集中度单调(corpus):
    cov = analyze.coverage(analyze.char_stats(corpus))
    assert [n for _, n in cov] == sorted(n for _, n in cov)


def test_词频过滤虚词(corpus):
    words = analyze.word_stats(corpus)
    toks = {w.token for w in words[:50]}
    assert not (toks & analyze.STOPWORDS)
    assert all(len(t) > 1 for t in toks)


def test_词频保留实义套语(corpus):
    toks = {w.token for w in analyze.word_stats(corpus, drop_stopwords=False)}
    assert {'君子', '我心'} <= toks


def test_叠字表有结果(corpus):
    rd = refrain.reduplications(corpus)
    top = {r.token for r in rd[:8]}
    assert {'悠悠', '肃肃'} <= top
    assert all(len(r.token) == 2 and r.token[0] == r.token[1] for r in rd)


def test_跨篇套语可量化(corpus):
    shared = dict((k, n) for k, n, _ in refrain.shared_lines(corpus))
    assert shared['心之忧矣'] >= 10
    assert shared['既见君子'] >= 8
    assert shared['之子于归'] >= 5


def test_重章平行度取值合法(corpus):
    par = refrain.parallelism(corpus)
    assert len(par) == len(corpus.poems)
    assert all(0 <= r.score <= 1 for r in par)
    # 黍离三章高度平行，应排在前列
    top10 = {r.poem.title for r in par[:10]}
    assert '黍离' in top10


def test_单章诗篇平行度为零(corpus):
    one = [r for r in refrain.parallelism(corpus) if r.stanzas < 2]
    assert all(r.score == 0 for r in one)


def test_韵式字母从A开始递增(corpus):
    for r in rhyme.schemes(corpus)[:30]:
        assert r.scheme[0] == 'A'
        assert set(r.scheme) <= set('ABCDEFGHIJKLMNOPQRSTUVWXYZ')
        assert r.groups == len(set(r.scheme))


def test_关雎押今音尤侯韵(corpus):
    p = next(x for x in corpus.poems if x.title == '关雎')
    ends = rhyme.line_endings(p)
    assert ends[:4] == ['鸠', '洲', '女', '逑']
    # 语助字被跳过：第二句取「洲」而不是「之」
    assert '之' not in ends[:4]


def test_跳过语助字会改变韵脚(corpus):
    with_p = sum(len(r.finals) for r in rhyme.schemes(corpus, True))
    without = sum(len(r.finals) for r in rhyme.schemes(corpus, False))
    assert with_p == without > 0
    a = rhyme.line_endings(corpus.poems[0], True)
    b = rhyme.line_endings(corpus.poems[0], False)
    assert a != b, '两种口径应能对比'


def test_统计走归一字形(corpus):
    # 归一后不应再出现繁体高频字，否则同一个字被拆成两笔账
    top = {s.token for s in analyze.char_stats(corpus)[:100]}
    assert not (top & set('風雅頌馬車無來'))
    assert '兮' in top and '之' in top

"""语料重建的回归防线。

这些断言的意义在于「不许退回旧状态」：旧数据 84455 字里六成是重复粘贴，
任何让字数重新膨胀或让篇目数漂移的改动都会被这里拦下。
"""
from __future__ import annotations

import re

from shijing import clean
from shijing import corpus as C

PART_COUNTS = {'国风': 160, '小雅': 74, '大雅': 31, '周颂': 31, '鲁颂': 4, '商颂': 5}


def test_诗经三百零五篇(corpus):
    assert len(corpus.poems) == 305


def test_各部分篇数(corpus):
    got: dict[str, int] = {}
    for p in corpus.poems:
        got[p.part] = got.get(p.part, 0) + 1
    assert got == PART_COUNTS


def test_字数必须落在三万量级而非八万(corpus):
    # 原始文件 84455 字；去重后应在 2.9-3.1 万之间
    assert 29000 <= corpus.total_chars <= 31500
    assert corpus.total_chars < 40000


def test_分组篇名唯一(corpus):
    keys = [(p.group, p.title) for p in corpus.poems]
    assert len(set(keys)) == len(keys) == 305


def test_顺序首尾(corpus):
    assert (corpus.poems[0].group, corpus.poems[0].title) == ('国风·周南', '关雎')
    assert (corpus.poems[-1].group, corpus.poems[-1].title) == ('商颂', '殷武')


def test_输出不含表格残留标签(corpus):
    assert '<' not in corpus.text() and '/td>' not in corpus.text()


def test_每篇都有正文(corpus):
    assert all(p.chars > 0 for p in corpus.poems)
    assert all(len(p.stanzas) >= 1 for p in corpus.poems)


def test_重建可复现(rebuilt, corpus):
    assert C.to_dict(rebuilt)['poems'] == C.to_dict(corpus)['poems']


def test_同名篇目不互相吞并(corpus):
    # 齐风《甫田》与小雅《甫田》是两篇，覆盖表只作用于平票的那一次
    futian = {p.group for p in corpus.poems if p.title == '甫田'}
    assert futian == {'国风·齐风', '小雅·甫田之什'}
    bai = {p.group for p in corpus.poems if p.title == '柏舟'}
    assert bai == {'国风·邶风', '国风·鄘风'}


def test_串台篇目已归位(corpus):
    by_title = {p.title: p.group for p in corpus.poems}
    assert by_title['鳲鸠'] == '国风·曹风'
    assert by_title['下泉'] == '国风·曹风'
    assert by_title['南山'] == '国风·齐风'
    assert by_title['玄鸟'] == '商颂'
    cao = [p.title for p in corpus.poems if p.group == '国风·曹风']
    assert cao == ['蜉蝣', '候人', '鳲鸠', '下泉']


def test_五字篇名不被丢弃(corpus):
    assert any(p.title == '昊天有成命' for p in corpus.poems)


def test_归一表覆盖全字表(corpus):
    table = clean._table()
    assert len(table) > 4000, 'data/t2s.tsv 太小，繁体检索会落空'
    for ch in '風頌馬車來無':
        assert ch in table, f'{ch} 不在归一表内'
    assert clean.normalize('周頌·清廟之什') == '周颂·清庙之什'


def test_归一确实减少了分裂计数(corpus):
    raw = set(re.findall(r'[一-鿿]', corpus.text()))
    merged = set(clean.normalize(corpus.text()))
    assert len(merged) < len(raw), '繁简混排未被归一，字频会被拆成两笔账'


def test_篇内重复句被保留(corpus):
    """去重只能在篇之间做。诗经的复沓本来就有完全相同的章句，整行去重会把它抹掉。"""
    dup = [p for p in corpus.poems
           if len(set(p.stanzas)) < len(p.stanzas)]
    assert dup, '没有任何一篇含完全相同的章，疑似误用了整行去重'
    assert any(p.title == '园有桃' for p in dup)


def test_跨篇粘贴串台已剔除(corpus):
    """《大东》全篇 7 章、《候人》末 2 章曾被整段粘到别的篇目尾部。"""
    by = {p.title: p for p in corpus.poems}
    assert len(by['殷武'].stanzas) == 6
    assert len(by['蓼莪'].stanzas) == 5
    # 正本不受影响
    assert len(by['大东'].stanzas) == 7
    assert len(by['候人'].stanzas) == 4


def test_语料内不再有整章跨篇重复(corpus):
    from shijing.corpus import MIN_STITCH_CHARS, _norm_stanza
    seen: dict[str, set[int]] = {}
    for p in corpus.poems:
        for st in p.stanzas:
            k = _norm_stanza(st)
            if len(k) >= MIN_STITCH_CHARS:
                seen.setdefault(k, set()).add(p.idx)
    assert not [k for k, v in seen.items() if len(v) > 1]


def test_串台判定要求本篇无平行章(corpus):
    """《候人》三四章与本篇第二章同框平行，属正本；不得被误删。"""
    hou = [p for p in corpus.poems if p.title == '候人'][0]
    assert len(hou.stanzas) == 4
    from shijing.corpus import _parallel
    assert _parallel(hou.stanzas[2], list(hou.stanzas[:2])) >= 0.5


def test_字数含串台剔除后仍接近三万(corpus):
    assert 29000 <= corpus.total_chars <= 31500

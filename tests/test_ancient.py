from __future__ import annotations

import pytest

from shijing import ancient


def test_韵脚表覆盖305篇():
    data = ancient.load()
    assert len(data) == 305
    assert min(data) == 1 and max(data) == 305


def test_韵脚表与语料篇名逐一对应(corpus):
    data = ancient.load()
    assert all(p.idx in data for p in corpus.poems)


def test_关雎韵脚是鸠而非之():
    """权威标注直接给出韵脚字，不需要语助字白名单——这是今音口径做不到的。"""
    data = ancient.load()
    first = data[1][0]
    assert first.text == '关关雎鸠'
    assert first.rhyme_chars == ('鳩',)
    assert first.positions == (4,)


def test_韵脚可不在句末():
    data = ancient.load()
    off = [c for cs in data.values() for c in cs
           if c.positions and c.positions[0] != len(c.text)]
    assert off, '韵脚位置不应一律在句末'
    # 「左右流之」押「流」(第3字) 而非「之」
    liu = [c for c in data[1] if c.text == '左右流之'][0]
    assert liu.rhyme_chars == ('流',) and liu.positions == (3,)


def test_约四分之一的句子不入韵(corpus):
    s = ancient.summary(corpus)
    assert 0.6 < s['rhyming_rate'] < 0.9
    assert s['clauses'] == 7286


def test_局部韵标在每章内重新起用():
    """按篇归组会把不同章的同名标签并错——曾导致韵类簇塌成一个巨簇。"""
    cls = ancient.rhyme_classes()
    one = ancient.load()[1]
    st1 = [c.keys[0] for c in one if c.stanza == 1 and c.rhyme_chars]
    st2 = [c.keys[0] for c in one if c.stanza == 2 and c.rhyme_chars]
    assert set(st1) == set(st2) == {'1-a'}          # 标签重用了
    assert cls[(1, 1, '1-a')] != cls[(1, 2, '1-a')]  # 但不是一个韵类
    assert cls[(1, 1, '1-a')] == ['鳩', '洲', '逑']
    assert cls[(1, 2, '1-a')] == ['流', '求']


def test_今音口径显著失真(corpus):
    cmp = ancient.compare_modern(corpus)
    assert cmp['lost_rate'] > 0.4, '今音丢失了大半上古韵类，不能当结论用'
    assert cmp['class_intact_rate'] < 0.5


def test_互押字对是可直接核验的证据():
    pairs = ancient.co_rhymes()
    assert pairs[('人', '天')] >= 10          # 真部
    assert all(a <= b for a, b in pairs)      # 键已规范化，无向重复
    # 同一句里的叠字会形成自对（「悠哉悠哉」），这是数据本来的样子
    assert any(a == b for a, b in pairs)


def test_缺失韵脚表时报错清楚(tmp_path):
    with pytest.raises(SystemExit) as e:
        ancient.load(tmp_path / 'nope.csv')
    assert 'CC-BY' in str(e.value) or 'data/README' in str(e.value)


def test_静态韵脚表只读盘一次(corpus, monkeypatch):
    """summary 内部三处取表；表是静态的，不该重复打开。"""
    from pathlib import Path
    ancient._read.cache_clear()
    opens: list[str] = []
    real = Path.open

    def counted(self, *a, **k):
        opens.append(self.name)
        return real(self, *a, **k)

    monkeypatch.setattr(Path, 'open', counted)
    ancient.summary(corpus)
    ancient.compare_modern(corpus)
    assert opens.count('rhyme_baxter1992.csv') == 1

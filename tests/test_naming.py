from __future__ import annotations

import json

import pytest

from shijing import cli, naming


@pytest.fixture(scope='module')
def corpus():
    from shijing import corpus as corpus_mod
    path = cli.locate(cli.CORPUS)
    if not path.exists():
        pytest.skip('语料未构建')
    return corpus_mod.load(path)


def test_连用命中给出处(corpus):
    d = naming.inspect(corpus, '令仪')
    assert d['hit_count'] == 3
    assert {h['title'] for h in d['hits']} == {'湛露', '宾之初筵', '烝民'}


def test_单字都有但从不连用(corpus):
    d = naming.inspect(corpus, '德棣')
    assert d['hit_count'] == 0
    assert {c['char'] for c in d['chars']} == {'德', '棣'}


def test_组合无命中时给单字出处(corpus):
    d = naming.inspect(corpus, '徐铎')
    src = {s['char']: s for s in d['char_sources']}
    assert src['徐']['count'] > 0 and src['铎']['count'] == 0
    assert any('常武' == r['title'] for r in src['徐']['examples'])
    assert 'char_sources' in d['note']
    assert d['contexts'] == []


def test_命中原句是完整章(corpus):
    d = naming.inspect(corpus, '之恒')
    assert d['hit_count'] == 1
    assert '如月之恒' in d['hits'][0]['line']
    assert d['hits'][0]['title'] == '天保'


def test_繁简通搜一致(corpus):
    assert (naming.inspect(corpus, '令仪')['hit_count']
            == naming.inspect(corpus, '令儀')['hit_count'])


def test_用字档位与虚词标注(corpus):
    chars = {c['char']: c for c in naming.inspect(corpus, '之恒')['chars']}
    assert chars['之']['tier'] == '极常见'
    assert chars['之']['function'] is True
    assert chars['恒']['tier'] == '较少'
    assert chars['恒']['function'] is False


def test_语料未见的字(corpus):
    chars = {c['char']: c for c in naming.char_facts(corpus, '旸珪')}
    assert all(c['freq'] == 0 and c['tier'] == '未见' for c in chars.values())


def test_读音给出声母韵母与声调():
    syls = naming.reading('令仪')
    assert [(s.char, s.tone, s.initial, s.final) for s in syls] == [
        ('令', 4, 'l', 'ing'), ('仪', 2, 'y', 'i')]
    assert naming.reading('') == []


def test_多音字列出又读():
    syls = {s.char: s for s in naming.reading('和乐')}
    assert syls['乐'].syllable == 'le4'
    lone = naming.reading('乐')[0]
    assert 'yue4' in lone.also          # 单字成名字时音乐一读要看得见
    assert 'shan4' in naming.reading('单')[0].also   # 姓氏读法
    assert all(s.syllable not in s.also for s in naming.reading('德棣'))


def test_双声叠韵被标出():
    assert any('双声' in s for s in naming.links(naming.reading('德棣')))
    assert '和乐 叠韵（韵母同 e）' in naming.links(naming.reading('和乐'))
    assert naming.links(naming.reading('令仪')) == []


def test_整首语境随命中给出(corpus):
    d = naming.inspect(corpus, '令仪')
    assert {c['title'] for c in d['contexts']} == {'湛露', '宾之初筵', '烝民'}
    assert any('岂弟君子' in s for s in d['contexts'][0]['stanzas'])
    off = naming.inspect(corpus, '令仪', with_context=False)
    assert off['contexts'] == []
    assert '--no-context' in off['note']


def test_name命令的两种口径(capsys):
    out = cli.main(['name', '令仪', '--no-context'])
    assert out == 0
    text = capsys.readouterr().out
    assert '连用命中 3 处' in text and '极常见' not in text
    assert cli.main(['name', '德棣', '--format', 'json']) == 0
    data = json.loads(capsys.readouterr().out)
    assert data['hit_count'] == 0 and len(data['chars']) == 2


def test_top与max_context各自截断(capsys):
    assert cli.main(['name', '君子', '--top', '2', '--max-context', '1']) == 0
    text = capsys.readouterr().out
    hits = [ln for ln in text.splitlines()
            if ln.startswith(('国风·', '小雅·', '大雅·'))]
    assert len(hits) == 2                       # 命中句按 --top 截
    assert '共 62 首' in text and '余 61 首' in text   # 语境按 --max-context 截


def test_整库归一只做一遍(corpus):
    """inspect 曾对每个字各扫全库并重复 normalize，这里钉住它只扫一次。"""
    calls = []
    real = naming._scan
    naming._scan = lambda c: (calls.append(1), real(c))[1]
    try:
        naming.inspect(corpus, '德棣')
    finally:
        naming._scan = real
    assert len(calls) == 1

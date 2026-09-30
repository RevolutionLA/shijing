"""多典籍层：注册表、散文解析、跨书合并与文体门控。"""
from __future__ import annotations

import json

import pytest

from shijing import books, cli, naming
from shijing import corpus as corpus_mod

# 每本典籍的自证式常数（篇/段/汉字），来自上游 chinese-poetry 的实测计数
SIZING = {
    '论语': (20, 512, 15917),
    '孟子': (14, 690, 35388),
    '大学': (1, 16, 1753),
    '中庸': (1, 39, 3566),
}


def _corpus(name: str):
    p = books.corpus_path(books.get(name))
    if not p.exists():
        pytest.skip(f'{name} 语料未构建')
    return corpus_mod.load(p)


def test_注册表认名字也认拼音():
    assert books.get('论语').slug == 'lunyu'
    assert books.get('lunyu').name == '论语'
    assert books.get('诗经').is_verse and not books.get('孟子').is_verse
    with pytest.raises(SystemExit) as e:
        books.get('卿云')
    assert '诗经(shijing)' in str(e.value)      # 报错要给出可选清单


def test_每本典籍的篇章字数都对得上():
    for name, (poems, stanzas, chars) in SIZING.items():
        c = _corpus(name)
        assert len(c.poems) == poems, name
        assert sum(len(p.stanzas) for p in c.poems) == stanzas, name
        assert c.total_chars == chars, name
        assert c.books == [name], name


def test_散文篇名落在group与part上():
    c = _corpus('论语')
    assert c.poems[0].group == '论语' and c.poems[0].part == '论语'
    assert c.poems[0].title.startswith('学而')


def test_单篇对象也能读_空段要报错():
    c = books.parse_prose('大学', {'chapter': '大學', 'paragraphs': ['在明明德。', '  ']})
    assert len(c.poems) == 1 and c.poems[0].stanzas == ('在明明德。',)
    with pytest.raises(SystemExit):
        books.parse_prose('大学', {'chapter': '大學', 'paragraphs': ['', '   ']})


def test_跨书idx会重号_uid不会():
    """《论语》第 1 篇与《诗经》第 1 篇的 idx 都是 1；凡拿 idx 当文档键的地方都会撞。"""
    merged = books.load_all()
    firsts = [p for p in merged.poems if p.idx == 1]
    assert len(firsts) == len(merged.books)
    assert len({p.uid for p in merged.poems}) == len(merged.poems)


def test_合并语料只收已构建的典籍():
    merged = books.load_all()
    assert set(merged.books) >= {'诗经', '论语'}
    for name in merged.books:
        assert name in books.BOOKS


def test_诗经常数没被四书带偏():
    c = _corpus('诗经')
    assert len(c.poems) == 305 and c.total_chars == 29645
    assert all(p.book == '诗经' for p in c.poems)


def test_散文上韵脚与重章叠句被挡住(capsys):
    for argv in (['--book', '论语', 'rhyme', '--poem', '学而'],
                 ['--book', '论语', 'refrain', '--what', 'parallel']):
        with pytest.raises(SystemExit) as e:
            cli.main(argv)
        assert '韵文口径' in str(e.value)
    capsys.readouterr()


def test_散文仍可跑通用分析(capsys):
    assert cli.main(['--book', '论语', 'chars', '--top', '3', '--format', 'json']) == 0
    out = json.loads(capsys.readouterr().out)
    assert out[0]['token'] == '子'


def test_散文的report不含韵脚栏(capsys):
    assert cli.main(['--book', '孟子', 'report']) == 0
    rep = json.loads(capsys.readouterr().out)
    assert rep['典籍'] == ['孟子'] and rep['篇数'] == 14
    assert '韵脚_上古音' not in rep and '复沓' not in rep
    assert rep['叠字']['总次'] > 0


def test_检索带典籍列且跨书命中(capsys):
    assert cli.main(['--book', 'all', 'search', '仁者', '--format', 'json']) == 0
    rows = json.loads(capsys.readouterr().out)
    assert rows and {'book', 'group', 'title', 'stanza', 'line'} <= set(rows[0])
    assert '孟子' in {r['book'] for r in rows}


def test_散文长段只截展示窗口_json留全文(capsys):
    """中庸一段几百字，直接进表格会糊成一片；机器口径必须仍是原文。"""
    assert cli.main(['name', '择善', '--top', '1', '--no-context']) == 0
    row = next(ln for ln in capsys.readouterr().out.splitlines()
               if ln.startswith('中庸'))
    assert len(row) < 90 and '…' in row
    assert cli.main(['name', '择善', '--format', 'json', '--no-context']) == 0
    line = json.loads(capsys.readouterr().out)['hits'][0]['line']
    assert len(line) > 200 and '擇善而固執之者也' in line
    assert cli.main(['name', '择善', '--format', 'json', '--no-context']) == 0
    line = json.loads(capsys.readouterr().out)['hits'][0]['line']
    assert len(line) > 200 and '擇善而固執之者也' in line


def test_取名默认跨典籍_可单本收回(capsys):
    wide = naming.inspect(books.load_all(), '君子')
    solo = naming.inspect(_corpus('诗经'), '君子')
    assert wide['hit_count'] > solo['hit_count']
    assert cli.main(['name', '君子', '--top', '1', '--no-context']) == 0
    text = capsys.readouterr().out
    assert '检索范围：诗经、论语、孟子、大学、中庸（341 篇）' in text
    assert cli.main(['--book', '诗经', 'name', '君子',
                     '--top', '1', '--no-context']) == 0
    assert '检索范围：诗经（305 篇）' in capsys.readouterr().out


def test_散文语境只印命中章_json仍是全篇(capsys):
    """《孟子》一篇平均 3100 字，整篇打进终端等于没打；数据层不能跟着裁。"""
    assert cli.main(['name', '仁政', '--max-context', '1']) == 0
    text = capsys.readouterr().out
    assert '此处只印命中章' in text and len(text) < 3000
    assert cli.main(['name', '仁政', '--format', 'json']) == 0
    cx = json.loads(capsys.readouterr().out)['contexts'][0]
    assert sum(len(s) for s in cx['stanzas']) > 2000
    assert cx['matched'] and all(0 < n <= len(cx['stanzas']) for n in cx['matched'])


def test_诗经语境仍是整篇(capsys):
    assert cli.main(['--book', '诗经', 'name', '之恒']) == 0
    text = capsys.readouterr().out
    assert '天保定尔' in text and '此处只印命中章' not in text


UPSTREAM = {          # chinese-poetry @ b8594f81a89752241442f2ce267d6f66f96704ee
    'lunyu': '5b45b298f4e42917b94a2687399fa8307b044ffc',
    'mengzi': '8a19e260abadf2c8a0ce274c22c9a2b59c136749',
    'daxue': '14cbc1ef8fbab503703b3f6d6edf019abb8b1ff0',
    'zhongyong': '9ef84a1c656f313308cefcbc14dea15d694996e4',
}


def _blob(path) -> str:
    """git 的对象校验和：sha1("blob <字节数>\0" + 内容)，与 GitHub API 的 sha 同式。"""
    import hashlib
    data = path.read_bytes()
    return hashlib.sha1(b'blob %d\x00' % len(data) + data).hexdigest()


def test_四书原文存档与上游逐字节一致():
    """"一字不改地存档"必须是可验的，否则上游有什么错字我们都说不清。"""
    from shijing.paths import DATA_DIR
    for slug, sha in UPSTREAM.items():
        assert _blob(DATA_DIR / 'books' / slug / 'raw.json') == sha, slug


def test_四书数据带得上游MIT署名():
    from shijing.paths import DATA_DIR
    lic = (DATA_DIR / 'books' / 'LICENSE.chinese-poetry.txt').read_text('utf-8')
    assert 'The MIT License' in lic and 'JackeyGao' in lic
    for slug in ('lunyu', 'mengzi', 'daxue', 'zhongyong'):
        assert (DATA_DIR / 'books' / slug / 'raw.json').exists()
        assert (DATA_DIR / 'books' / slug / 'corpus.json').exists()

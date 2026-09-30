from __future__ import annotations

import json

import pytest

from shijing import cli


def run(capsys, *argv):
    code = cli.main(list(argv))
    cap = capsys.readouterr()
    assert code == 0
    run.last_err = cap.err
    return cap.out


def test_帮助可用(capsys):
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args(['--help'])
    assert 'shijing' in capsys.readouterr().out


def test_字频输出json(capsys):
    rows = json.loads(run(capsys, 'chars', '--top', '3', '--format', 'json'))
    assert [r['token'] for r in rows] == ['之', '不', '我']


def test_词频输出csv(capsys):
    out = run(capsys, 'words', '--top', '5', '--format', 'csv')
    assert out.splitlines()[0] == 'token,freq,rate,poems,cover'
    assert len(out.splitlines()) == 6


def test_限定单篇(capsys):
    rows = json.loads(run(capsys, 'chars', '--poem', '关雎', '--format', 'json'))
    assert sum(r['freq'] for r in rows) < 200


def test_找不到篇目时报错(capsys):
    with pytest.raises(SystemExit) as e:
        cli.main(['chars', '--poem', '不存在的篇'])
    assert '找不到篇目' in str(e.value)


def test_检索命中(capsys):
    out = run(capsys, 'search', '辗转反侧')
    assert '关雎' in out


def test_检索支持繁简通搜(capsys):
    a = run(capsys, 'search', '辗转反侧', '--format', 'json')
    b = run(capsys, 'search', '輾轉反側', '--format', 'json')
    assert json.loads(a) == json.loads(b)


def test_检索无命中不报错(capsys):
    out = run(capsys, 'search', '如珪')
    assert '没有命中' in out


def test_检索无命中的机器口径仍是合法结构(capsys):
    assert json.loads(run(capsys, 'search', '如珪', '--format', 'json')) == []
    assert run(capsys, 'search', '如珪', '--format', 'csv').strip() == \
        'book,group,title,stanza,line'


def test_韵脚表在任意工作目录都能找到(tmp_path, capsys, monkeypatch):
    """--rhyme-data 是相对路径，必须与 --corpus 一样能回退到仓库根。"""
    (tmp_path / 'elsewhere').mkdir()
    monkeypatch.chdir(tmp_path / 'elsewhere')
    out = run(capsys, 'rhyme', '--poem', '关雎')
    assert '韵式' in out and '关关雎鸠' in out


def test_版本号只有一个来源():
    import re

    from shijing import __version__
    toml = cli.locate('pyproject.toml').read_text('utf-8')
    # tomllib 要 3.11+，CI 跑 3.10；顶格 version 只有 [project] 那一条
    declared = re.search(r'^version\s*=\s*"([^"]+)"', toml, re.M).group(1)
    assert __version__ == declared


def test_打印原文(capsys):
    out = run(capsys, 'show', '桃夭')
    assert '桃之夭夭' in out and '灼灼其华' in out


def test_复沓三种口径(capsys):
    for what in ('parallel', 'redup', 'shared'):
        assert run(capsys, 'refrain', '--what', what, '--top', '2')


def test_韵脚汇总(capsys):
    s = json.loads(run(capsys, 'rhyme', '--what', 'summary'))
    assert s['poems'] == 305


def test_报告含修复记录(capsys):
    rep = json.loads(run(capsys, 'report'))
    assert rep['篇数'] == 305
    assert rep['字数'] < 31500
    assert rep['语料修复记录']


def test_出图落盘(tmp_path, capsys):
    from shijing.visuals import find_font

    try:
        font = find_font()
    except SystemExit:
        # 出图必须有中文字体，否则全是方框。CI 会显式装 fonts-noto-cjk，
        # 本地缺字体时跳过而不是报一个与环境无关的失败。
        pytest.skip('无可用中文字体')
    out = tmp_path / 'cloud.png'
    run(capsys, 'cloud', '--kind', 'char', '--top', '80',
        '--font', font, '--out', str(out))
    assert out.exists() and out.stat().st_size > 1000


def test_语料缺失时自动重建(tmp_path, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)
    rows = json.loads(run(capsys, '--corpus', 'nope.json', 'chars',
                          '--top', '1', '--format', 'json'))
    assert rows[0]['token'] == '之'
    assert '不存在' in run.last_err

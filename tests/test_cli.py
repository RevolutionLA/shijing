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
    out = tmp_path / 'cloud.png'
    run(capsys, 'cloud', '--kind', 'char', '--top', '80', '--out', str(out))
    assert out.exists() and out.stat().st_size > 1000


def test_语料缺失时自动重建(tmp_path, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)
    rows = json.loads(run(capsys, '--corpus', 'nope.json', 'chars',
                          '--top', '1', '--format', 'json'))
    assert rows[0]['token'] == '之'
    assert '不存在' in run.last_err

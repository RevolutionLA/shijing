"""数据文件的定位。包与仓库之间的层数关系只在这里假设一次。

解析顺序（第一处存在的胜出）：

1. 环境变量 ``SHIJING_DATA``：把语料放在任意位置的人（打包、离线机、只读挂载）用它；
2. 包内 ``shijing/data``：为 ``pip install shijing`` 准备的布局，wheel 里带语料时走这条；
3. 仓库根 ``data/``：``pip install -e .`` 与源码运行的现行布局。

这样「源码运行」与「装好的包」用同一份代码，不需要在发布时改路径。
"""
from __future__ import annotations

import os
from pathlib import Path

PKG_DIR = Path(__file__).resolve().parent
REPO_ROOT = PKG_DIR.parents[1]          # src/shijing -> src -> 仓库根


def _resolve_data_dir() -> Path:
    env = os.environ.get('SHIJING_DATA')
    if env:
        return Path(env).expanduser().resolve()
    bundled = PKG_DIR / 'data'
    if bundled.is_dir():
        return bundled
    return REPO_ROOT / 'data'


DATA_DIR = _resolve_data_dir()


def locate(rel: str | Path) -> Path:
    """把相对路径按「当前目录 → 数据目录 → 仓库根」依次尝试；都不存在就原样返回给调用方报错。"""
    rel = Path(rel)
    if rel.is_absolute():
        return rel
    for base in (Path.cwd(), DATA_DIR, REPO_ROOT):
        cand = base / rel
        if cand.exists():
            return cand
    return rel

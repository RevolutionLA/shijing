"""《诗经》语料与统计分析。"""
from __future__ import annotations

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _dist_version

from .clean import normalize
from .corpus import Corpus, Poem, build, load, parse

try:
    # 版本号只有一个来源：pyproject.toml。改版本后需重装（pip install -e .）才生效
    __version__ = _dist_version('shijing')
except PackageNotFoundError:          # 未安装，直接从源码树跑
    __version__ = '0.0.0+unknown'
__all__ = ['Corpus', 'Poem', 'build', 'load', 'normalize', 'parse', '__version__']

"""《诗经》语料与统计分析。"""
from __future__ import annotations

from .clean import normalize
from .corpus import Corpus, Poem, build, load, parse

__version__ = '0.2.0'
__all__ = ['Corpus', 'Poem', 'build', 'load', 'normalize', 'parse', '__version__']

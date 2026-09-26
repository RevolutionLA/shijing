from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

from shijing import corpus as corpus_mod  # noqa: E402


@pytest.fixture(scope='session')
def corpus():
    return corpus_mod.load(ROOT / 'data' / 'corpus.json')


@pytest.fixture(scope='session')
def rebuilt():
    return corpus_mod.build(ROOT / 'data' / 'raw' / 'shijing.txt',
                            ROOT / 'data' / 'overrides.json')

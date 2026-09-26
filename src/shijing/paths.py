"""数据文件的定位。包与仓库之间的层数关系只在这里假设一次。"""
from __future__ import annotations

from pathlib import Path

PKG_DIR = Path(__file__).resolve().parent
REPO_ROOT = PKG_DIR.parents[1]          # src/shijing -> src -> 仓库根
DATA_DIR = REPO_ROOT / 'data'


def locate(rel: str | Path) -> Path:
    """把相对路径按「当前目录 → 仓库根」依次尝试；都不存在就原样返回给调用方报错。"""
    rel = Path(rel)
    if rel.is_absolute():
        return rel
    for base in (Path.cwd(), REPO_ROOT):
        cand = base / rel
        if cand.exists():
            return cand
    return rel

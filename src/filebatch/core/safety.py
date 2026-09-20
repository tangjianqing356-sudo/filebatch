"""防误操作的公共规则。

两条硬性约定，所有任务都必须遵守：
  1. 原文件默认不动，结果写到新的输出目录；
  2. 绝不覆盖已存在的文件，重名自动加 _1 _2 …
"""
from __future__ import annotations

from pathlib import Path

MAX_DEDUP_TRIES = 9999


def unique_path(target: Path, taken: set[Path] | None = None) -> Path:
    """返回一个不会覆盖任何已存在文件的路径。

    同时考虑磁盘上已有的文件，以及本次计划里已经占用的目标路径（taken），
    否则同一批里两个文件算出同样的新名字时会互相覆盖。
    """
    taken = taken if taken is not None else set()
    if not target.exists() and target not in taken:
        return target

    stem, suffix = target.stem, target.suffix
    for n in range(1, MAX_DEDUP_TRIES + 1):
        candidate = target.with_name(f"{stem}_{n}{suffix}")
        if not candidate.exists() and candidate not in taken:
            return candidate
    raise RuntimeError(f"无法为 {target} 找到不重名的路径（已尝试 {MAX_DEDUP_TRIES} 次）")


def is_inside(child: Path, parent: Path) -> bool:
    """child 是否在 parent 目录内（用于阻止把输出目录设在源目录里造成自己处理自己）。"""
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except (ValueError, OSError):
        return False


def validate_output_dir(output_dir: Path, sources: list[Path]) -> str | None:
    """检查输出目录是否安全。返回 None 表示没问题，否则返回中文错误原因。"""
    if output_dir is None:
        return "没有指定输出目录"
    for src in sources:
        base = src if src.is_dir() else src.parent
        if output_dir.resolve() == base.resolve():
            return f"输出目录不能和源目录相同（{base}），请换一个新目录，避免覆盖原文件"
    return None

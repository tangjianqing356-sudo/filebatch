"""把用户拖进来的东西（文件/文件夹混在一起）整理成一份干净的文件清单。"""
from __future__ import annotations

from pathlib import Path
from typing import Callable

# 常见的系统垃圾文件，扫描时直接忽略
IGNORED_NAMES = {".DS_Store", "Thumbs.db", "desktop.ini", ".localized"}

# 扫描时每处理这么多项回报一次进度并检查取消
PROGRESS_EVERY = 200

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp", ".tiff", ".tif"}
TABLE_SUFFIXES = {".csv", ".xlsx", ".xlsm"}
PDF_SUFFIXES = {".pdf"}
TEXT_SUFFIXES = {".txt", ".md", ".csv", ".log", ".json", ".xml", ".html", ".css", ".js", ".py"}


def collect_files(
    paths: list[Path],
    recursive: bool = True,
    suffixes: set[str] | None = None,
    on_progress: Callable[[int], None] | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> list[Path]:
    """展开成文件清单。

    :param paths: 用户拖入的路径，文件和文件夹可以混在一起
    :param recursive: 文件夹是否递归展开子目录
    :param suffixes: 只保留这些扩展名（小写，带点），None 表示全要
    :param on_progress: 每找到若干个文件回调一次已找到的数量，供界面显示"正在扫描…"
    :param should_cancel: 返回 True 表示用户要求取消扫描，已找到的部分照常返回
    """
    found: list[Path] = []
    seen: set[Path] = set()
    cancelled = False

    def accept(f: Path) -> None:
        if f.name in IGNORED_NAMES or f.name.startswith("._"):
            return
        if suffixes is not None and f.suffix.lower() not in suffixes:
            return
        resolved = f.resolve()
        if resolved in seen:
            return
        seen.add(resolved)
        found.append(f)

    def 要停了() -> bool:
        return should_cancel is not None and should_cancel()

    for p in paths:
        if 要停了():
            cancelled = True
            break
        if not p.exists():
            continue
        if p.is_file():
            accept(p)
        elif p.is_dir():
            it = p.rglob("*") if recursive else p.glob("*")
            for f in it:
                # 大目录可能有几十万项，每隔一批才查一次取消和回报进度，
                # 不然回调本身的开销比扫描还大
                if len(seen) % PROGRESS_EVERY == 0:
                    if 要停了():
                        cancelled = True
                        break
                    if on_progress is not None:
                        on_progress(len(found))
                try:
                    if f.is_file():
                        accept(f)
                except OSError:
                    # 断开的软链接、权限不足的条目，跳过就好，不能让整次扫描挂掉
                    continue
            if cancelled:
                break

    if on_progress is not None:
        on_progress(len(found))

    # 按路径排序，保证编号顺序对用户是可预期的
    found.sort(key=lambda f: (str(f.parent).lower(), f.name.lower()))
    return found


def human_size(num_bytes: int) -> str:
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"

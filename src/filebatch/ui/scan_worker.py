"""文件扫描的后台线程。

5000 个文件在主线程扫要 1.4 秒，界面会明显卡一下；几万个文件就没法用了。
扫描本身仍然是 core.scan.collect_files，这里只负责搬到子线程 + 转成信号。
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QThread, Signal

from ..core.scan import collect_files
from .messages import humanize, technical_detail


class ScanWorker(QThread):
    progress = Signal(int)        # 已找到的文件数
    finished_files = Signal(list)  # list[Path]
    failed = Signal(str, str)      # 人话, 技术细节

    def __init__(self, paths: list[Path], suffixes: set[str] | None = None, parent=None) -> None:  # noqa: ANN001
        super().__init__(parent)
        self._paths = paths
        self._suffixes = suffixes
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    @property
    def cancelled(self) -> bool:
        return self._cancelled

    def run(self) -> None:  # noqa: D102
        try:
            files = collect_files(
                self._paths,
                recursive=True,
                suffixes=self._suffixes,
                on_progress=lambda n: self.progress.emit(n),
                should_cancel=lambda: self._cancelled,
            )
            self.finished_files.emit(files)
        except Exception as e:
            self.failed.emit(humanize(e), technical_detail(e))

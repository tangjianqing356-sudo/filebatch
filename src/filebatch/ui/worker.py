"""后台执行线程。

GUI 这一层只负责把 core 的 execute 放到子线程里跑、把进度转成信号，
不重新实现任何业务逻辑。处理几万个文件时主界面也不会卡住。
"""
from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QThread, Signal

from ..core.result import JobReport
from .messages import humanize, technical_detail


class JobWorker(QThread):
    """把一个 execute 调用搬到子线程。

    execute 必须接受 on_progress(done, total, name) 和 should_cancel() 两个回调，
    这是 core 层统一的约定。
    """

    progress = Signal(int, int, str)      # 已完成, 总数, 当前文件名
    finished_report = Signal(object)      # JobReport
    failed = Signal(str, str)             # 人话, 技术细节

    def __init__(
        self,
        execute_fn: Callable[..., JobReport],
        parent=None,  # noqa: ANN001
    ) -> None:
        super().__init__(parent)
        self._execute_fn = execute_fn
        self._cancelled = False

    def cancel(self) -> None:
        """请求中断。已经处理完的文件不会回滚，只是不再开始新的。"""
        self._cancelled = True

    @property
    def cancelled(self) -> bool:
        return self._cancelled

    def run(self) -> None:  # noqa: D102
        try:
            report = self._execute_fn(
                on_progress=lambda done, total, name: self.progress.emit(done, total, name),
                should_cancel=lambda: self._cancelled,
            )
            self.finished_report.emit(report)
        except Exception as e:  # 子线程里出任何意外都不能让程序整个崩掉
            self.failed.emit(humanize(e), technical_detail(e))

"""中间省略的路径标签。

长路径直接显示会把界面撑高好几行。这里在中间打省略号，完整路径放 tooltip。
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QResizeEvent
from PySide6.QtWidgets import QLabel, QWidget


class ElidedLabel(QLabel):
    def __init__(self, text: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._full_text = text
        self.setMinimumWidth(80)
        self.setText(text)

    def setFullText(self, text: str) -> None:  # noqa: N802
        self._full_text = text
        self.setToolTip(text)
        self._apply_elide()

    def fullText(self) -> str:  # noqa: N802
        return self._full_text

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._apply_elide()

    def _apply_elide(self) -> None:
        metrics = self.fontMetrics()
        available = max(40, self.width() - 4)
        # 省略号打在中间：路径的开头（盘符/用户名）和结尾（目标文件夹）都是有用信息
        super().setText(
            metrics.elidedText(self._full_text, Qt.TextElideMode.ElideMiddle, available)
        )

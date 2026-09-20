"""顶部四步指引。

不做一次性教程弹窗——那种东西用户点掉就再也看不到了。
改成常驻的步骤条，当前该做哪一步一直高亮着，第一次用和第一百次用都有用。
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget

STEPS = ["① 添加文件", "② 设置规则", "③ 生成预览", "④ 确认执行"]

_DONE = "color:#16a34a; font-weight:600;"
_CURRENT = "color:#2563eb; font-weight:600;"
_TODO = "color:#9ca3af;"
_ARROW = "color:#d1d5db; padding:0 2px;"


class StepIndicator(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._labels: list[QLabel] = []
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 2, 0, 2)
        lay.setSpacing(4)

        for i, text in enumerate(STEPS):
            if i:
                arrow = QLabel("›")
                arrow.setStyleSheet(_ARROW)
                lay.addWidget(arrow)
            lbl = QLabel(text)
            lbl.setAlignment(Qt.AlignmentFlag.AlignVCenter)
            lay.addWidget(lbl)
            self._labels.append(lbl)

        lay.addStretch(1)
        self.set_current(0)

    def set_current(self, index: int) -> None:
        """index 之前的算完成，index 是当前，之后是待办。"""
        for i, lbl in enumerate(self._labels):
            if i < index:
                lbl.setStyleSheet(_DONE)
            elif i == index:
                lbl.setStyleSheet(_CURRENT)
            else:
                lbl.setStyleSheet(_TODO)

"""可折叠区块。高级选项默认收起来，普通用户第一次打开不会被一堆技术选项吓到。"""
from __future__ import annotations

from PySide6.QtWidgets import QFrame, QToolButton, QVBoxLayout, QWidget
from PySide6.QtCore import Qt


class CollapsibleSection(QWidget):
    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._title = title

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(6)

        self.toggle = QToolButton()
        self.toggle.setText(f"  {title}")
        self.toggle.setCheckable(True)
        self.toggle.setChecked(False)
        self.toggle.setArrowType(Qt.ArrowType.RightArrow)
        self.toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.toggle.setStyleSheet(
            "QToolButton { border: none; color: #4b5563; font-weight: 600; padding: 4px 0; }"
            "QToolButton:hover { color: #2563eb; }"
        )
        root.addWidget(self.toggle, alignment=Qt.AlignmentFlag.AlignLeft)

        self.content = QFrame()
        self.content.setVisible(False)
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(16, 4, 0, 4)
        self.content_layout.setSpacing(8)
        root.addWidget(self.content)

        self.toggle.toggled.connect(self._on_toggled)

    def _on_toggled(self, checked: bool) -> None:
        self.content.setVisible(checked)
        self.toggle.setArrowType(Qt.ArrowType.DownArrow if checked else Qt.ArrowType.RightArrow)

    def add_widget(self, widget: QWidget) -> None:
        self.content_layout.addWidget(widget)

    def add_layout(self, layout) -> None:  # noqa: ANN001
        self.content_layout.addLayout(layout)

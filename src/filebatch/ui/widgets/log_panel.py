"""实时日志面板。执行过程中一行行往里追加，完成后可以整份存成文件。"""
from __future__ import annotations

import time

from PySide6.QtWidgets import QPlainTextEdit, QWidget


class LogPanel(QPlainTextEdit):
    MAX_LINES = 5000   # 处理几万个文件时不能让日志把内存吃光

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setReadOnly(True)
        self.setMaximumBlockCount(self.MAX_LINES)
        self.setPlaceholderText("执行日志会显示在这里")

    def log(self, message: str) -> None:
        stamp = time.strftime("%H:%M:%S")
        self.appendPlainText(f"[{stamp}] {message}")
        self.verticalScrollBar().setValue(self.verticalScrollBar().maximum())

    def log_lines(self, text: str) -> None:
        for line in text.splitlines():
            self.appendPlainText(line)
        self.verticalScrollBar().setValue(self.verticalScrollBar().maximum())

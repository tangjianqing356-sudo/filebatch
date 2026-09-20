"""应用入口。"""
from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from .main_window import MainWindow
from .theme import STYLESHEET


def create_app(argv: list[str] | None = None) -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication(argv if argv is not None else sys.argv)
    app.setApplicationName("文件批量处理工具")
    app.setOrganizationName("filebatch")
    app.setStyleSheet(STYLESHEET)
    return app


def main() -> int:
    app = create_app()
    window = MainWindow()
    window.show()
    return app.exec()

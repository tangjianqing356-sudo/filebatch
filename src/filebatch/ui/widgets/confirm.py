"""危险操作的二次确认框。

两条硬要求：
  1. 确认按钮必须是用户**主动点**的，文案写清楚后果；
  2. 回车不能误触确认——把"取消"设成默认按钮，Enter 和 Esc 都走取消。
"""
from __future__ import annotations

from PySide6.QtWidgets import QMessageBox, QPushButton, QWidget


def confirm_dangerous(
    parent: QWidget | None,
    title: str,
    body: str,
    confirm_text: str,
    cancel_text: str = "取消",
) -> bool:
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Warning)
    box.setWindowTitle(title)
    box.setText(title)
    box.setInformativeText(body)

    btn_confirm = box.addButton(confirm_text, QMessageBox.ButtonRole.DestructiveRole)
    btn_cancel = box.addButton(cancel_text, QMessageBox.ButtonRole.RejectRole)

    # 关键：默认按钮是"取消"，这样敲回车不会误触发危险操作
    box.setDefaultButton(btn_cancel)
    box.setEscapeButton(btn_cancel)

    box.exec()
    return box.clickedButton() is btn_confirm


def show_error(parent: QWidget | None, title: str, human_message: str, detail: str = "") -> None:
    """错误弹窗只说人话，技术细节收进"详细信息"里，不直接糊用户一脸。"""
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Critical)
    box.setWindowTitle(title)
    box.setText(human_message)
    if detail:
        box.setDetailedText(detail)
    box.addButton("知道了", QMessageBox.ButtonRole.AcceptRole)
    box.exec()


def show_info(parent: QWidget | None, title: str, message: str) -> None:
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Information)
    box.setWindowTitle(title)
    box.setText(message)
    box.addButton("知道了", QMessageBox.ButtonRole.AcceptRole)
    box.exec()

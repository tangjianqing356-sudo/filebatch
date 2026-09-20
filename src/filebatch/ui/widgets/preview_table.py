"""预览表：把计划(PlannedAction)摆出来给用户过目。

颜色区分三种状态，用户扫一眼就知道会发生什么：
  绿色 = 会执行    灰色 = 会跳过（附原因）    橙色 = 有需要注意的地方（比如自动改名避让）
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QTableWidget,
    QTableWidgetItem,
)

from ...core.result import JobReport, PlannedAction

COLOR_SKIP = QColor("#9ca3af")
COLOR_FAIL = QColor("#dc2626")
COLOR_OK = QColor("#16a34a")
BG_FAIL = QColor("#fef2f2")
COLOR_NOTE = QColor("#c2410c")
COLOR_NORMAL = QColor("#111827")
BG_SKIP = QColor("#f9fafb")


class PreviewTable(QTableWidget):
    def __init__(self, parent=None) -> None:  # noqa: ANN001
        super().__init__(0, 4, parent)
        self.setHorizontalHeaderLabels(["原文件名", "", "处理后", "说明"])
        self.verticalHeader().setVisible(False)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        header = self.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.setColumnWidth(1, 28)

    def show_actions(self, actions: list[PlannedAction]) -> None:
        self.setRowCount(len(actions))
        for row, act in enumerate(actions):
            if act.will_run:
                target_text = act.target.name if act.target else ""
                note = act.note
                color = COLOR_NOTE if act.note else COLOR_NORMAL
                arrow = "→"
            else:
                target_text = "不处理"
                note = act.skip_reason or ""
                color = COLOR_SKIP
                arrow = ""

            cells = [
                QTableWidgetItem(act.source.name),
                QTableWidgetItem(arrow),
                QTableWidgetItem(target_text),
                QTableWidgetItem(note),
            ]
            cells[1].setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            cells[0].setToolTip(str(act.source))
            if act.target:
                cells[2].setToolTip(str(act.target))
            # 说明列容易被挤窄（"1600x1200 -> 800x600" 这种），完整内容放 tooltip
            if note:
                cells[3].setToolTip(note)

            for col, item in enumerate(cells):
                if not act.will_run:
                    item.setForeground(QBrush(COLOR_SKIP))
                    item.setBackground(QBrush(BG_SKIP))
                elif col == 3 and note:
                    item.setForeground(QBrush(color))
                self.setItem(row, col, item)

    def show_results(self, report: JobReport) -> None:
        """执行完之后换成"本次执行结果"，显示真正发生了什么。

        和预览共用同一张表，但语义不同：预览是"将要发生"，这里是"已经发生"。
        标题会同步切换，避免用户以为还停在预览状态。
        """
        rows = [(i.source, i.target, i.ok, i.message) for i in report.items]
        rows += [(p, None, None, reason) for p, reason in report.skipped]

        self.setHorizontalHeaderLabels(["原文件名", "", "结果", "说明"])
        self.setRowCount(len(rows))

        for row, (source, target, ok, message) in enumerate(rows):
            if ok is None:
                status, color, bg = "已跳过", COLOR_SKIP, BG_SKIP
                arrow = ""
            elif ok:
                status, color, bg = (target.name if target else "完成"), COLOR_OK, None
                arrow = "→"
            else:
                status, color, bg = "失败", COLOR_FAIL, BG_FAIL
                arrow = ""

            cells = [
                QTableWidgetItem(source.name),
                QTableWidgetItem(arrow),
                QTableWidgetItem(status),
                QTableWidgetItem(message or ""),
            ]
            cells[1].setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            cells[0].setToolTip(str(source))
            if target:
                cells[2].setToolTip(str(target))
            if message:
                cells[3].setToolTip(message)

            for col, item in enumerate(cells):
                if col in (2, 3):
                    item.setForeground(QBrush(color))
                if bg is not None:
                    item.setBackground(QBrush(bg))
                self.setItem(row, col, item)

    def reset_to_preview_mode(self) -> None:
        self.setHorizontalHeaderLabels(["原文件名", "", "处理后", "说明"])
        self.setRowCount(0)

"""按规则把文件分类到不同文件夹。"""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox, QFormLayout, QLabel, QVBoxLayout

from ...core import classify_job
from ...core.classify_job import ClassifyMode
from ...core.result import JobReport, PlannedAction
from .base_page import BaseJobPage

MODE_ITEMS = [
    ("按文件类型（图片 / 文档 / 表格…）", ClassifyMode.BY_TYPE),
    ("按扩展名（jpg / pdf / xlsx…）", ClassifyMode.BY_EXTENSION),
    ("按修改月份（2026-09）", ClassifyMode.BY_DATE_MONTH),
    ("按修改年份（2026）", ClassifyMode.BY_DATE_YEAR),
    ("按文件名首字", ClassifyMode.BY_FIRST_LETTER),
]


class ClassifyPage(BaseJobPage):
    TITLE = "文件分类整理"
    SUBTITLE = "把一堆杂乱文件自动分到不同文件夹。默认复制，原文件保留在原处。"

    DANGER_LABEL = "移动文件（原位置不再保留）"
    DANGER_WARNING = "⚠ 移动会把文件从原位置拿走，无法自动撤销，请谨慎使用"
    DANGER_CONFIRM_TITLE = "确认移动文件？"
    DANGER_CONFIRM_BODY = (
        "你开启了「移动文件」。\n\n"
        "文件会从原位置被拿走，本工具不会保留副本，也无法自动撤销。\n"
        "如果只是想试一下分类效果，建议关掉这个开关，改成复制。\n\n"
        "确定要继续吗？"
    )
    DANGER_CONFIRM_OK = "我确认移动文件"

    def build_options(self, layout: QVBoxLayout) -> None:
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setSpacing(8)

        self.cb_mode = QComboBox()
        for text, mode in MODE_ITEMS:
            self.cb_mode.addItem(text, mode)
        form.addRow("分类方式", self.cb_mode)

        self.lbl_hint = QLabel()
        self.lbl_hint.setObjectName("Hint")
        self.lbl_hint.setWordWrap(True)
        form.addRow("", self.lbl_hint)

        layout.addLayout(form)
        self._sync_hint()

    def register_invalidators(self) -> None:
        self.cb_mode.currentIndexChanged.connect(self._invalidate_preview)
        self.cb_mode.currentIndexChanged.connect(self._sync_hint)

    def _sync_hint(self) -> None:
        mode = ClassifyMode(self.cb_mode.currentData())
        examples = {
            ClassifyMode.BY_TYPE: "会生成「图片」「文档」「表格」「视频」等文件夹",
            ClassifyMode.BY_EXTENSION: "会按扩展名生成「jpg」「pdf」「xlsx」等文件夹",
            ClassifyMode.BY_DATE_MONTH: "会按文件修改时间生成「2026-09」这样的文件夹",
            ClassifyMode.BY_DATE_YEAR: "会按文件修改时间生成「2026」这样的文件夹",
            ClassifyMode.BY_FIRST_LETTER: "会按文件名第一个字生成文件夹，英文归到大写字母",
        }
        self.lbl_hint.setText(examples.get(mode, ""))

    def build_plan(self, files: list[Path], output: Path | None) -> list[PlannedAction]:
        assert output is not None
        return classify_job.plan_classify(
            files, ClassifyMode(self.cb_mode.currentData()), output, self.danger_enabled()
        )

    def make_executor(self, actions: list[PlannedAction]) -> Callable[..., JobReport]:
        move = self.danger_enabled()
        return lambda on_progress, should_cancel: classify_job.execute(
            actions, move, on_progress=on_progress, should_cancel=should_cancel
        )

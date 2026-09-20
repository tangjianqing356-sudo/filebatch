"""文本文件批量查找替换。"""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QCheckBox, QFormLayout, QLabel, QLineEdit, QVBoxLayout, QWidget

from ...core import text_job
from ...core.result import JobReport, PlannedAction
from ...core.text_job import ReplaceOptions
from ..widgets.collapsible import CollapsibleSection
from .base_page import BaseJobPage


class TextPage(BaseJobPage):
    TITLE = "文本查找替换"
    SUBTITLE = "在一批文本文件里统一替换内容。会自动跳过图片、程序等非文本文件。"

    DANGER_LABEL = "直接修改原文件（不保留副本）"
    DANGER_WARNING = "⚠ 将直接改写原文件，改完无法自动撤销，请谨慎使用"
    DANGER_CONFIRM_TITLE = "确认直接修改原文件？"
    DANGER_CONFIRM_BODY = (
        "你开启了「直接修改原文件」。\n\n"
        "替换会写回原文件，本工具不会保留副本，也无法自动撤销。\n"
        "如果只是想试一下效果，建议关掉这个开关，让结果输出到新文件夹。\n\n"
        "确定要继续吗？"
    )
    DANGER_CONFIRM_OK = "我确认修改原文件"

    def build_options(self, layout: QVBoxLayout) -> None:
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setSpacing(8)

        self.ed_find = QLineEdit()
        self.ed_find.setPlaceholderText("要被替换掉的内容")
        form.addRow("查找", self.ed_find)

        self.ed_replace = QLineEdit()
        self.ed_replace.setPlaceholderText("换成什么（留空表示删掉）")
        form.addRow("替换为", self.ed_replace)

        layout.addLayout(form)

        hint = QLabel("生成预览时会先数一遍每个文件有多少处匹配，没有匹配的文件会自动跳过。")
        hint.setObjectName("Hint")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        adv = CollapsibleSection("高级选项（正则表达式、区分大小写）")
        adv_form = QFormLayout()
        adv_form.setSpacing(8)
        self.chk_regex = QCheckBox("按正则表达式匹配")
        adv_form.addRow("", self.chk_regex)
        self.chk_case = QCheckBox("区分大小写")
        self.chk_case.setChecked(True)
        adv_form.addRow("", self.chk_case)
        adv_wrap = QWidget()
        adv_wrap.setLayout(adv_form)
        adv.add_widget(adv_wrap)
        layout.addWidget(adv)

    def register_invalidators(self) -> None:
        self.ed_find.textChanged.connect(self._invalidate_preview)
        self.ed_replace.textChanged.connect(self._invalidate_preview)
        self.chk_regex.toggled.connect(self._invalidate_preview)
        self.chk_case.toggled.connect(self._invalidate_preview)

    def current_options(self) -> ReplaceOptions:
        return ReplaceOptions(
            find=self.ed_find.text(),
            replace=self.ed_replace.text(),
            use_regex=self.chk_regex.isChecked(),
            case_sensitive=self.chk_case.isChecked(),
            in_place=self.danger_enabled(),
        )

    def validate_options(self) -> str | None:
        return self.current_options().validate()

    def build_plan(self, files: list[Path], output: Path | None) -> list[PlannedAction]:
        return text_job.plan_replace(files, self.current_options(), output)

    def make_executor(self, actions: list[PlannedAction]) -> Callable[..., JobReport]:
        options = self.current_options()
        return lambda on_progress, should_cancel: text_job.execute(
            actions, options, on_progress=on_progress, should_cancel=should_cancel
        )

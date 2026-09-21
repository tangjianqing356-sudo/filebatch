"""Excel 去重。"""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox, QFormLayout, QLabel, QVBoxLayout

from ...core.excel import dedupe_job
from ...core.excel.dedupe_job import DedupeOptions, KeepMode
from ...core.excel.workbook import SUPPORTED_SUFFIXES
from ...core.result import JobReport, PlannedAction
from .columns import ColumnAwarePage, ColumnCheckList


class DedupePage(ColumnAwarePage):
    TITLE = "Excel 去重"
    SUBTITLE = "按你指定的列找出重复记录，每组只留一条。原文件不动，结果写到新文件。"
    FILE_SUFFIXES = SUPPORTED_SUFFIXES
    OUTPUT_LABEL = "选择输出文件夹"

    def build_options(self, layout: QVBoxLayout) -> None:
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setSpacing(8)
        form.addRow("", self.make_header_checkbox())

        self.cb_keep = QComboBox()
        self.cb_keep.addItem("保留第一条", KeepMode.FIRST.value)
        self.cb_keep.addItem("保留最后一条", KeepMode.LAST.value)
        form.addRow("重复时", self.cb_keep)

        self.cb_format = QComboBox()
        self.cb_format.addItem("Excel (.xlsx)", "xlsx")
        self.cb_format.addItem("CSV (.csv)", "csv")
        form.addRow("输出格式", self.cb_format)
        layout.addLayout(form)

        layout.addWidget(QLabel("按哪些列判断重复（都不勾 = 整行完全相同才算重复）"))
        self.list_keys = ColumnCheckList()
        layout.addWidget(self.list_keys)
        self.make_column_hint(layout)

        from ..widgets.collapsible import CollapsibleSection
        from PySide6.QtWidgets import QCheckBox, QLineEdit, QWidget

        adv = CollapsibleSection("高级选项（比较方式、文件名后缀）")
        av = QFormLayout()
        av.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self.chk_trim = QCheckBox("比较时忽略首尾空格（“张三 ”和“张三”算同一个）")
        self.chk_trim.setChecked(True)
        av.addRow("", self.chk_trim)
        self.chk_case = QCheckBox("比较时忽略英文大小写")
        av.addRow("", self.chk_case)
        self.ed_suffix = QLineEdit("_去重")
        av.addRow("文件名后缀", self.ed_suffix)
        wrap = QWidget()
        wrap.setLayout(av)
        adv.add_widget(wrap)
        layout.addWidget(adv)

    def register_invalidators(self) -> None:
        super().register_invalidators()
        self.cb_keep.currentIndexChanged.connect(self._invalidate_preview)
        self.cb_format.currentIndexChanged.connect(self._invalidate_preview)
        self.list_keys.itemChanged.connect(lambda *_: self._invalidate_preview())
        self.chk_trim.toggled.connect(self._invalidate_preview)
        self.chk_case.toggled.connect(self._invalidate_preview)
        self.ed_suffix.textChanged.connect(self._invalidate_preview)

    def on_columns_ready(self, columns: list[str]) -> None:
        self.list_keys.set_columns(columns)

    def required_columns(self) -> list[str]:
        return self.list_keys.checked()

    def current_options(self) -> DedupeOptions:
        return DedupeOptions(
            has_header=self.chk_header.isChecked(),
            key_columns=self.list_keys.checked(),
            keep=KeepMode(str(self.cb_keep.currentData())),
            ignore_case=self.chk_case.isChecked(),
            trim_spaces=self.chk_trim.isChecked(),
            output_format=str(self.cb_format.currentData()),
            name_suffix=self.ed_suffix.text() or "_去重",
        )

    def validate_options(self) -> str | None:
        return self.current_options().validate()

    def build_plan(self, files: list[Path], output: Path | None) -> list[PlannedAction]:
        assert output is not None
        return dedupe_job.plan(files, self.current_options(), output)

    def make_executor(self, actions: list[PlannedAction]) -> Callable[..., JobReport]:
        options = self.current_options()
        return lambda on_progress, should_cancel: dedupe_job.execute(
            actions, options, on_progress=on_progress, should_cancel=should_cancel
        )

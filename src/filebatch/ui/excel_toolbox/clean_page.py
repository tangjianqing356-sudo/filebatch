"""数据清洗。只做确定安全的事，不碰数据类型。"""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QCheckBox, QComboBox, QFormLayout, QLabel, QLineEdit, QVBoxLayout, QWidget

from ...core.excel import clean_job
from ...core.excel.clean_job import CleanOptions
from ...core.excel.workbook import SUPPORTED_SUFFIXES
from ...core.result import JobReport, PlannedAction
from ..pages.base_page import BaseJobPage
from ..widgets.collapsible import CollapsibleSection


class CleanPage(BaseJobPage):
    TITLE = "数据清洗"
    SUBTITLE = "删空行、去掉多余空格和换行。只做这些确定安全的整理，不改数据类型。"
    FILE_SUFFIXES = SUPPORTED_SUFFIXES

    def build_options(self, layout: QVBoxLayout) -> None:
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setSpacing(8)
        self.chk_header = QCheckBox("第一行是表头")
        self.chk_header.setChecked(True)
        form.addRow("", self.chk_header)
        self.cb_format = QComboBox()
        self.cb_format.addItem("Excel (.xlsx)", "xlsx")
        self.cb_format.addItem("CSV (.csv)", "csv")
        form.addRow("输出格式", self.cb_format)
        layout.addLayout(form)

        layout.addWidget(QLabel("清洗内容"))
        self.chk_blank_rows = QCheckBox("删除整行都是空的行")
        self.chk_blank_rows.setChecked(True)
        self.chk_trim = QCheckBox("去掉单元格首尾空格")
        self.chk_trim.setChecked(True)
        self.chk_collapse = QCheckBox("把中间连续多个空格并成一个")
        self.chk_collapse.setChecked(True)
        self.chk_newline = QCheckBox("把单元格里的换行换成空格")
        self.chk_newline.setChecked(True)
        for c in (self.chk_blank_rows, self.chk_trim, self.chk_collapse, self.chk_newline):
            layout.addWidget(c)

        warn = QLabel(
            "不会做数据类型转换：身份证号、以 0 开头的编号、“3-5”这类文本都原样保留，"
            "不会变成科学计数法或日期。"
        )
        warn.setObjectName("Hint")
        warn.setWordWrap(True)
        layout.addWidget(warn)

        adv = CollapsibleSection("高级选项（删空列、整行去重、文件名后缀）")
        av = QFormLayout()
        av.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self.chk_blank_cols = QCheckBox("删除表头和数据都为空的列")
        av.addRow("", self.chk_blank_cols)
        self.chk_dup_rows = QCheckBox("整行完全相同的只留一条")
        av.addRow("", self.chk_dup_rows)
        self.ed_suffix = QLineEdit("_清洗")
        av.addRow("文件名后缀", self.ed_suffix)
        wrap = QWidget()
        wrap.setLayout(av)
        adv.add_widget(wrap)
        layout.addWidget(adv)

    def register_invalidators(self) -> None:
        for c in (self.chk_header, self.chk_blank_rows, self.chk_trim, self.chk_collapse,
                  self.chk_newline, self.chk_blank_cols, self.chk_dup_rows):
            c.toggled.connect(self._invalidate_preview)
        self.cb_format.currentIndexChanged.connect(self._invalidate_preview)
        self.ed_suffix.textChanged.connect(self._invalidate_preview)

    def current_options(self) -> CleanOptions:
        return CleanOptions(
            has_header=self.chk_header.isChecked(),
            drop_blank_rows=self.chk_blank_rows.isChecked(),
            drop_blank_cols=self.chk_blank_cols.isChecked(),
            trim_spaces=self.chk_trim.isChecked(),
            collapse_spaces=self.chk_collapse.isChecked(),
            remove_newlines=self.chk_newline.isChecked(),
            drop_duplicate_rows=self.chk_dup_rows.isChecked(),
            output_format=str(self.cb_format.currentData()),
            name_suffix=self.ed_suffix.text() or "_清洗",
        )

    def validate_options(self) -> str | None:
        return self.current_options().validate()

    def build_plan(self, files: list[Path], output: Path | None) -> list[PlannedAction]:
        assert output is not None
        return clean_job.plan(files, self.current_options(), output)

    def make_executor(self, actions: list[PlannedAction]) -> Callable[..., JobReport]:
        options = self.current_options()
        return lambda on_progress, should_cancel: clean_job.execute(
            actions, options, on_progress=on_progress, should_cancel=should_cancel
        )

"""Excel / CSV 批量合并。"""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

from ...core import table_job
from ...core.result import JobReport, PlannedAction
from ...core.scan import TABLE_SUFFIXES
from ...core.table_job import MergeOptions
from ..widgets.collapsible import CollapsibleSection
from .base_page import BaseJobPage


class TablePage(BaseJobPage):
    TITLE = "Excel / CSV 合并"
    SUBTITLE = "把多个表格合并成一个。按列名对齐，某个表缺列会补空，不会丢数据。"
    FILE_SUFFIXES = TABLE_SUFFIXES
    OUTPUT_IS_FILE = True
    OUTPUT_FILE_FILTER = "Excel 文件 (*.xlsx);;CSV 文件 (*.csv)"
    DEFAULT_OUTPUT_NAME = "合并结果.xlsx"
    OUTPUT_LABEL = "选择保存位置"

    def build_options(self, layout: QVBoxLayout) -> None:
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setSpacing(8)

        self.chk_header = QCheckBox("第一行是表头")
        self.chk_header.setChecked(True)
        form.addRow("", self.chk_header)

        self.chk_source = QCheckBox("加一列记录数据来自哪个文件")
        self.chk_source.setChecked(True)
        form.addRow("", self.chk_source)

        self.cb_format = QComboBox()
        self.cb_format.addItem("Excel (.xlsx)", "xlsx")
        self.cb_format.addItem("CSV (.csv)", "csv")
        form.addRow("输出格式", self.cb_format)

        layout.addLayout(form)

        hint = QLabel(
            "有表头时按**列名**对齐：两个表的列顺序不一样也能正确合并。\n"
            "旧版 .xls 不支持，请先用 Excel 另存为 .xlsx。"
        )
        hint.setObjectName("Hint")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        adv = CollapsibleSection("高级选项（来源列名、工作表名）")
        adv_form = QFormLayout()
        adv_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        adv_form.setSpacing(8)
        self.ed_source_col = QLineEdit("来源文件")
        adv_form.addRow("来源列名", self.ed_source_col)
        self.ed_sheet = QLineEdit("合并结果")
        adv_form.addRow("工作表名", self.ed_sheet)
        adv_wrap = QWidget()
        adv_wrap.setLayout(adv_form)
        adv.add_widget(adv_wrap)
        layout.addWidget(adv)

    def register_invalidators(self) -> None:
        self.chk_header.toggled.connect(self._invalidate_preview)
        self.chk_source.toggled.connect(self._invalidate_preview)
        self.cb_format.currentIndexChanged.connect(self._invalidate_preview)
        self.cb_format.currentIndexChanged.connect(self._sync_default_name)
        self.ed_source_col.textChanged.connect(self._invalidate_preview)
        self.ed_sheet.textChanged.connect(self._invalidate_preview)

    def _sync_default_name(self) -> None:
        self.DEFAULT_OUTPUT_NAME = f"合并结果.{self.cb_format.currentData()}"

    def current_options(self) -> MergeOptions:
        return MergeOptions(
            has_header=self.chk_header.isChecked(),
            add_source_column=self.chk_source.isChecked(),
            source_column_name=self.ed_source_col.text(),
            output_format=self.cb_format.currentData(),
            sheet_name=self.ed_sheet.text() or "合并结果",
        )

    def validate_options(self) -> str | None:
        return self.current_options().validate()

    def build_plan(self, files: list[Path], output: Path | None) -> list[PlannedAction]:
        assert output is not None
        return table_job.plan_merge(files, self.current_options(), output)

    def make_executor(self, actions: list[PlannedAction]) -> Callable[..., JobReport]:
        options = self.current_options()
        output = self._output_path
        assert output is not None
        return lambda on_progress, should_cancel: table_job.execute(
            actions, options, output, on_progress=on_progress, should_cancel=should_cancel
        )

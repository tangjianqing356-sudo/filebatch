"""批量拆表：按某一列的值把一张表拆成多张。"""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ...core.excel import split_job
from ...core.excel.split_job import DEFAULT_MAX_FILES, HARD_MAX_FILES, SplitOptions
from ...core.excel.workbook import SUPPORTED_SUFFIXES
from ...core.result import JobReport, PlannedAction
from ..widgets.collapsible import CollapsibleSection
from .columns import ColumnAwarePage


class SplitPage(ColumnAwarePage):
    TITLE = "批量拆表"
    SUBTITLE = "按某一列的值把表拆开，每个值一个文件。比如按“部门”拆成各部门的表。"
    FILE_SUFFIXES = SUPPORTED_SUFFIXES

    def build_options(self, layout: QVBoxLayout) -> None:
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setSpacing(8)
        form.addRow("", self.make_header_checkbox())

        self.cb_column = QComboBox()
        self.cb_column.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        form.addRow("按哪一列拆", self.cb_column)

        self.cb_format = QComboBox()
        self.cb_format.addItem("Excel (.xlsx)", "xlsx")
        self.cb_format.addItem("CSV (.csv)", "csv")
        form.addRow("输出格式", self.cb_format)
        layout.addLayout(form)

        self.make_column_hint(layout)

        hint = QLabel(
            "请挑一个取值不多的列（部门、地区、月份）。\n"
            "按订单号、身份证这类几乎每行都不同的列拆，会生成成千上万个文件。"
        )
        hint.setObjectName("Hint")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        adv = CollapsibleSection("高级选项（文件名模板、数量上限）")
        av = QFormLayout()
        av.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self.ed_template = QLineEdit("{原名}_{值}")
        self.ed_template.setToolTip("{原名} = 原文件名，{值} = 这一组的列值")
        av.addRow("文件名模板", self.ed_template)
        self.sp_max = QSpinBox()
        self.sp_max.setRange(1, HARD_MAX_FILES)
        self.sp_max.setValue(DEFAULT_MAX_FILES)
        av.addRow("最多拆出", self.sp_max)
        wrap = QWidget()
        wrap.setLayout(av)
        adv.add_widget(wrap)
        layout.addWidget(adv)

    def register_invalidators(self) -> None:
        super().register_invalidators()
        self.cb_column.currentIndexChanged.connect(self._invalidate_preview)
        self.cb_format.currentIndexChanged.connect(self._invalidate_preview)
        self.ed_template.textChanged.connect(self._invalidate_preview)
        self.sp_max.valueChanged.connect(self._invalidate_preview)

    def on_columns_ready(self, columns: list[str]) -> None:
        旧 = self.cb_column.currentText()
        self.cb_column.clear()
        self.cb_column.addItems(columns)
        if 旧 in columns:
            self.cb_column.setCurrentText(旧)

    def required_columns(self) -> list[str]:
        名 = self.cb_column.currentText().strip()
        return [名] if 名 else []

    def current_options(self) -> SplitOptions:
        return SplitOptions(
            split_column=self.cb_column.currentText(),
            has_header=self.chk_header.isChecked(),
            output_format=str(self.cb_format.currentData()),
            max_files=self.sp_max.value(),
            name_template=self.ed_template.text(),
        )

    def validate_options(self) -> str | None:
        return self.current_options().validate()

    def build_plan(self, files: list[Path], output: Path | None) -> list[PlannedAction]:
        assert output is not None
        return split_job.plan(files, self.current_options(), output)

    def make_executor(self, actions: list[PlannedAction]) -> Callable[..., JobReport]:
        options = self.current_options()
        return lambda on_progress, should_cancel: split_job.execute(
            actions, options, on_progress=on_progress, should_cancel=should_cancel
        )

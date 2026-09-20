"""PDF 批量拆分 / 合并。

一个页面两种模式：拆分输出到文件夹，合并输出成单个文件。
输出类型靠 output_is_file() 动态切换，基类会自己换对应的文件对话框。
"""
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
)

from ...core import pdf_job
from ...core.pdf_job import SplitMode, SplitOptions
from ...core.result import JobReport, PlannedAction
from ...core.scan import PDF_SUFFIXES
from .base_page import BaseJobPage

MODE_SPLIT = "split"
MODE_MERGE = "merge"

SPLIT_ITEMS = [
    ("每页拆成一个文件", SplitMode.EVERY_PAGE),
    ("每 N 页拆成一个文件", SplitMode.FIXED_SIZE),
    ("按指定页码范围拆分", SplitMode.RANGES),
]


class PdfPage(BaseJobPage):
    TITLE = "PDF 拆分 / 合并"
    SUBTITLE = "把 PDF 按页拆开，或把多个 PDF 合成一个。加密和损坏的文件会自动跳过并说明原因。"
    FILE_SUFFIXES = PDF_SUFFIXES
    OUTPUT_FILE_FILTER = "PDF 文件 (*.pdf)"
    DEFAULT_OUTPUT_NAME = "合并结果.pdf"

    def output_is_file(self) -> bool:
        # 合并输出的是一个 PDF 文件，拆分输出的是一堆文件所以选文件夹
        return self.cb_mode.currentData() == MODE_MERGE

    def build_options(self, layout: QVBoxLayout) -> None:
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setSpacing(8)

        self.cb_mode = QComboBox()
        self.cb_mode.addItem("拆分 PDF", MODE_SPLIT)
        self.cb_mode.addItem("合并 PDF", MODE_MERGE)
        form.addRow("要做什么", self.cb_mode)

        self.cb_split = QComboBox()
        for text, mode in SPLIT_ITEMS:
            self.cb_split.addItem(text, mode)
        form.addRow("拆分方式", self.cb_split)

        self.sp_pages = QSpinBox()
        self.sp_pages.setRange(1, 9999)
        self.sp_pages.setValue(1)
        self.sp_pages.setMaximumWidth(90)
        form.addRow("每份页数", self.sp_pages)

        self.ed_ranges = QLineEdit()
        self.ed_ranges.setPlaceholderText("例如：1-3,5,8-10")
        form.addRow("页码范围", self.ed_ranges)

        layout.addLayout(form)

        self.lbl_hint = QLabel()
        self.lbl_hint.setObjectName("Hint")
        self.lbl_hint.setWordWrap(True)
        layout.addWidget(self.lbl_hint)

        self._sync_rows()

    def register_invalidators(self) -> None:
        self.cb_mode.currentIndexChanged.connect(self._invalidate_preview)
        self.cb_mode.currentIndexChanged.connect(self._on_mode_changed)
        self.cb_split.currentIndexChanged.connect(self._invalidate_preview)
        self.cb_split.currentIndexChanged.connect(self._sync_rows)
        self.sp_pages.valueChanged.connect(self._invalidate_preview)
        self.ed_ranges.textChanged.connect(self._invalidate_preview)

    def _on_mode_changed(self) -> None:
        # 输出目标的含义变了（文件夹 <-> 单个文件），之前选的那个不再适用
        self._output_path = None
        self.lbl_output.setFullText("未选择")
        self.btn_output.setText("选择输出文件" if self.output_is_file() else "选择输出文件夹")
        self._sync_rows()

    def _sync_rows(self) -> None:
        merging = self.cb_mode.currentData() == MODE_MERGE
        mode = SplitMode(self.cb_split.currentData())
        self.cb_split.setEnabled(not merging)
        self.sp_pages.setEnabled(not merging and mode is SplitMode.FIXED_SIZE)
        self.ed_ranges.setEnabled(not merging and mode is SplitMode.RANGES)
        if merging:
            self.lbl_hint.setText("按左侧列表的顺序依次合并。想调整顺序，先移除再按需要的顺序添加。")
        else:
            self.lbl_hint.setText("拆出来的文件会命名成「原名_第1页.pdf」这样，放在你选的输出文件夹里。")

    def current_split_options(self) -> SplitOptions:
        return SplitOptions(
            mode=SplitMode(self.cb_split.currentData()),
            pages_per_file=self.sp_pages.value(),
            ranges_text=self.ed_ranges.text(),
        )

    def validate_options(self) -> str | None:
        if self.cb_mode.currentData() == MODE_MERGE:
            return None
        return self.current_split_options().validate()

    def build_plan(self, files: list[Path], output: Path | None) -> list[PlannedAction]:
        assert output is not None
        if self.cb_mode.currentData() == MODE_MERGE:
            return pdf_job.plan_merge(files, output)
        return pdf_job.plan_split(files, self.current_split_options(), output)

    def make_executor(self, actions: list[PlannedAction]) -> Callable[..., JobReport]:
        if self.cb_mode.currentData() == MODE_MERGE:
            output = self._output_path
            assert output is not None
            return lambda on_progress, should_cancel: pdf_job.execute_merge(
                actions, output, on_progress=on_progress, should_cancel=should_cancel
            )
        return lambda on_progress, should_cancel: pdf_job.execute_split(
            actions, on_progress=on_progress, should_cancel=should_cancel
        )

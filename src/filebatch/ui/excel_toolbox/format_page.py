"""格式统一：表头、字体、对齐、边框、列宽、数字格式。"""
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
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ...core.excel import format_job
from ...core.excel.format_job import FONT_CHOICES, FormatOptions
from ...core.excel.workbook import EXCEL_SUFFIXES
from ...core.result import JobReport, PlannedAction
from ..pages.base_page import BaseJobPage
from ..widgets.collapsible import CollapsibleSection

# 第一项是"不改"。和字体一个道理：用户没主动选，就别动人家的对齐。
_对齐 = [
    ("保留原对齐（不修改）", None),
    ("左对齐", "left"),
    ("居中", "center"),
    ("右对齐", "right"),
]

# 字体和字号的"不改"选项。默认就是不改——
# 用户没点名要换字体，我们就不该动人家表格里的字体。
保留字体 = "保留原字体（不修改）"
# 字号用 QSpinBox 的特殊值表示"不改"。5 在合法字号范围（6~72）之外，
# 不会和真实字号混淆。
保留字号 = 5


class FormatPage(BaseJobPage):
    TITLE = "格式统一"
    SUBTITLE = "把多个表格刷成同一套样式：表头加粗、字体统一、加边框、列宽自适应。"
    FILE_SUFFIXES = EXCEL_SUFFIXES

    def build_options(self, layout: QVBoxLayout) -> None:
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setSpacing(8)

        self.chk_header = QCheckBox("第一行是表头")
        self.chk_header.setChecked(True)
        form.addRow("", self.chk_header)

        self.cb_font = QComboBox()
        self.cb_font.setEditable(True)      # 列表里没有的字体可以直接打
        self.cb_font.addItem(保留字体)
        for 名 in FONT_CHOICES:
            self.cb_font.addItem(名)
        self.cb_font.setCurrentIndex(0)
        form.addRow("字体", self.cb_font)

        self.sp_size = QSpinBox()
        self.sp_size.setRange(保留字号, 72)
        self.sp_size.setSpecialValueText("保留原字号（不修改）")
        self.sp_size.setValue(保留字号)
        form.addRow("字号", self.sp_size)

        self.cb_body_align = QComboBox()
        for 名, 值 in _对齐:
            self.cb_body_align.addItem(名, 值)
        self.cb_body_align.setCurrentIndex(0)
        form.addRow("正文对齐", self.cb_body_align)
        layout.addLayout(form)

        self.chk_bold = QCheckBox("表头加粗并加底色")
        self.chk_bold.setChecked(True)
        self.chk_freeze = QCheckBox("冻结表头（往下翻时表头一直可见）")
        self.chk_freeze.setChecked(True)
        self.chk_border = QCheckBox("给所有单元格加细边框")
        self.chk_border.setChecked(True)
        self.chk_width = QCheckBox("列宽按内容自动调整")
        self.chk_width.setChecked(True)
        for c in (self.chk_bold, self.chk_freeze, self.chk_border, self.chk_width):
            layout.addWidget(c)

        warn = QLabel(
            "只支持 .xlsx / .xlsm，CSV 没有格式可设。\n"
            "字体和对齐默认都不改：只有你明确挑了，才会去动表格里对应的设置。\n"
            "在原文件的副本上改样式，不重建工作簿，所以多个工作表和数字/日期类型不受影响。\n"
            "图表、图片、条件格式等对象在验收样例中已验证可保留，但复杂 Excel "
            "仍可能存在兼容性差异；数据透视表很可能保不住。遇到时预览里会标出来，"
            "重要文件请先备份。"
        )
        warn.setObjectName("Hint")
        warn.setWordWrap(True)
        layout.addWidget(warn)

        adv = CollapsibleSection("高级选项（表头底色、数字格式、最大列宽）")
        av = QFormLayout()
        av.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self.ed_fill = QLineEdit("DDEBF7")
        self.ed_fill.setToolTip("6 位十六进制颜色，留空表示不填充")
        av.addRow("表头底色", self.ed_fill)
        # 表头对齐单独设，不跟正文绑死
        self.cb_head_align = QComboBox()
        for 名, 值 in _对齐:
            self.cb_head_align.addItem(名, 值)
        self.cb_head_align.setCurrentIndex(0)
        av.addRow("表头对齐", self.cb_head_align)
        self.ed_number = QLineEdit("")
        self.ed_number.setPlaceholderText("留空表示不动，例如 #,##0.00")
        av.addRow("数字格式", self.ed_number)
        self.sp_max_width = QSpinBox()
        self.sp_max_width.setRange(10, 200)
        self.sp_max_width.setValue(50)
        av.addRow("最大列宽", self.sp_max_width)
        self.ed_suffix = QLineEdit("_格式化")
        av.addRow("文件名后缀", self.ed_suffix)
        wrap = QWidget()
        wrap.setLayout(av)
        adv.add_widget(wrap)
        layout.addWidget(adv)

    def register_invalidators(self) -> None:
        for c in (self.chk_header, self.chk_bold, self.chk_freeze, self.chk_border, self.chk_width):
            c.toggled.connect(self._invalidate_preview)
        for e in (self.ed_fill, self.ed_number, self.ed_suffix):
            e.textChanged.connect(self._invalidate_preview)
        for s in (self.sp_size, self.sp_max_width):
            s.valueChanged.connect(self._invalidate_preview)
        for cb in (self.cb_body_align, self.cb_head_align, self.cb_font):
            cb.currentIndexChanged.connect(self._invalidate_preview)
        self.cb_font.currentTextChanged.connect(lambda *_: self._invalidate_preview())

    def selected_font(self) -> str | None:
        """None 表示"保留原字体"。"""
        文字 = self.cb_font.currentText().strip()
        if not 文字 or 文字 == 保留字体:
            return None
        return 文字

    def selected_size(self) -> int | None:
        """None 表示"保留原字号"。"""
        值 = self.sp_size.value()
        return None if 值 == 保留字号 else 值

    @staticmethod
    def selected_align(cb: QComboBox) -> str | None:
        """None 表示"保留原对齐"。

        注意不能 str() 一下就完事——Qt 会把 None 变成字符串 "None"，
        那就成了一个非法的对齐值。
        """
        值 = cb.currentData()
        return None if 值 is None else str(值)

    def current_options(self) -> FormatOptions:
        return FormatOptions(
            has_header=self.chk_header.isChecked(),
            header_bold=self.chk_bold.isChecked(),
            header_fill=self.ed_fill.text().strip() if self.chk_bold.isChecked() else "",
            freeze_header=self.chk_freeze.isChecked(),
            font_name=self.selected_font(),
            font_size=self.selected_size(),
            body_align=self.selected_align(self.cb_body_align),
            header_align=self.selected_align(self.cb_head_align),
            add_borders=self.chk_border.isChecked(),
            auto_width=self.chk_width.isChecked(),
            max_col_width=self.sp_max_width.value(),
            number_format=self.ed_number.text().strip(),
            name_suffix=self.ed_suffix.text() or "_格式化",
        )

    def validate_options(self) -> str | None:
        return self.current_options().validate()

    def build_plan(self, files: list[Path], output: Path | None) -> list[PlannedAction]:
        assert output is not None
        return format_job.plan(files, self.current_options(), output)

    def make_executor(self, actions: list[PlannedAction]) -> Callable[..., JobReport]:
        options = self.current_options()
        return lambda on_progress, should_cancel: format_job.execute(
            actions, options, on_progress=on_progress, should_cancel=should_cancel
        )

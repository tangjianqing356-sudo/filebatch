"""图片批量改名、编号、尺寸调整、格式转换。"""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ...core import image_job
from ...core.image_job import ImageOptions, ResizeMode
from ...core.naming import NameRule, NumberPosition
from ...core.result import JobReport, PlannedAction
from ...core.scan import IMAGE_SUFFIXES
from ..widgets.collapsible import CollapsibleSection
from .base_page import BaseJobPage

RESIZE_ITEMS = [
    ("不改尺寸", ResizeMode.NONE),
    ("限制最长边", ResizeMode.MAX_SIDE),
    ("指定宽度（高度按比例）", ResizeMode.WIDTH),
    ("指定高度（宽度按比例）", ResizeMode.HEIGHT),
    ("按百分比缩放", ResizeMode.PERCENT),
    ("放进指定的宽×高框内", ResizeMode.FIT_BOX),
]


class ImagePage(BaseJobPage):
    TITLE = "图片批处理"
    SUBTITLE = "批量改名编号、压缩尺寸、转换格式。只处理图片文件，结果输出到新文件夹。"
    FILE_SUFFIXES = IMAGE_SUFFIXES

    def build_options(self, layout: QVBoxLayout) -> None:
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setSpacing(8)

        self.ed_base = QLineEdit()
        self.ed_base.setPlaceholderText("留空则保留原文件名")
        form.addRow("统一改名为", self.ed_base)

        self.cb_number = QComboBox()
        self.cb_number.addItem("不编号", NumberPosition.NONE)
        self.cb_number.addItem("加在名字后面", NumberPosition.SUFFIX)
        self.cb_number.addItem("加在名字前面", NumberPosition.PREFIX)
        form.addRow("自动编号", self.cb_number)

        self.sp_digits = QSpinBox()
        self.sp_digits.setRange(1, 10)
        self.sp_digits.setValue(3)
        self.sp_digits.setMaximumWidth(70)
        form.addRow("编号位数", self.sp_digits)

        self.cb_resize = QComboBox()
        for text, mode in RESIZE_ITEMS:
            self.cb_resize.addItem(text, mode)
        form.addRow("尺寸调整", self.cb_resize)

        size_row = QHBoxLayout()
        size_row.setContentsMargins(0, 0, 0, 0)
        size_row.setSpacing(4)
        self.sp_value = QSpinBox()
        self.sp_value.setRange(1, 30000)
        self.sp_value.setValue(1920)
        self.sp_value.setMaximumWidth(100)
        self.lbl_unit = QLabel("像素")
        size_row.addWidget(self.sp_value)
        size_row.addWidget(self.lbl_unit)
        size_row.addStretch(1)
        self.size_widget = QWidget()
        self.size_widget.setLayout(size_row)
        self.size_widget.setMinimumHeight(self.sp_value.sizeHint().height() + 6)
        form.addRow("", self.size_widget)

        box_row = QHBoxLayout()
        box_row.setContentsMargins(0, 0, 0, 0)
        box_row.setSpacing(4)
        self.sp_box_w = QSpinBox()
        self.sp_box_w.setRange(1, 30000)
        self.sp_box_w.setValue(1920)
        self.sp_box_w.setMaximumWidth(90)
        self.sp_box_h = QSpinBox()
        self.sp_box_h.setRange(1, 30000)
        self.sp_box_h.setValue(1080)
        self.sp_box_h.setMaximumWidth(90)
        box_row.addWidget(QLabel("宽"))
        box_row.addWidget(self.sp_box_w)
        box_row.addWidget(QLabel("高"))
        box_row.addWidget(self.sp_box_h)
        box_row.addStretch(1)
        self.box_widget = QWidget()
        self.box_widget.setLayout(box_row)
        self.box_widget.setMinimumHeight(self.sp_box_w.sizeHint().height() + 6)
        form.addRow("", self.box_widget)

        layout.addLayout(form)

        adv = CollapsibleSection("高级选项（格式转换、JPEG 质量、允许放大）")
        adv_form = QFormLayout()
        adv_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        adv_form.setSpacing(8)

        self.cb_format = QComboBox()
        self.cb_format.addItem("保持原格式", "")
        for fmt in ("jpg", "png", "webp", "bmp"):
            self.cb_format.addItem(fmt.upper(), fmt)
        adv_form.addRow("转换为", self.cb_format)

        self.sp_quality = QSpinBox()
        self.sp_quality.setRange(1, 100)
        self.sp_quality.setValue(90)
        self.sp_quality.setMaximumWidth(80)
        adv_form.addRow("JPEG 质量", self.sp_quality)

        self.chk_upscale = QCheckBox("允许把小图放大（默认不放大，放大只会变糊）")
        adv_form.addRow("", self.chk_upscale)

        adv_wrap = QWidget()
        adv_wrap.setLayout(adv_form)
        adv.add_widget(adv_wrap)
        layout.addWidget(adv)

        self._sync_size_rows()

    def register_invalidators(self) -> None:
        self.ed_base.textChanged.connect(self._invalidate_preview)
        for w in (self.cb_number, self.cb_resize, self.cb_format):
            w.currentIndexChanged.connect(self._invalidate_preview)
        for w in (self.sp_digits, self.sp_value, self.sp_box_w, self.sp_box_h, self.sp_quality):
            w.valueChanged.connect(self._invalidate_preview)
        self.chk_upscale.toggled.connect(self._invalidate_preview)
        self.cb_resize.currentIndexChanged.connect(self._sync_size_rows)

    def _sync_size_rows(self) -> None:
        mode = ResizeMode(self.cb_resize.currentData())
        needs_value = mode in (ResizeMode.MAX_SIDE, ResizeMode.WIDTH,
                               ResizeMode.HEIGHT, ResizeMode.PERCENT)
        self.size_widget.setEnabled(needs_value)
        self.box_widget.setEnabled(mode is ResizeMode.FIT_BOX)
        self.lbl_unit.setText("%" if mode is ResizeMode.PERCENT else "像素")
        if mode is ResizeMode.PERCENT:
            self.sp_value.setRange(1, 1000)
            if self.sp_value.value() > 1000:
                self.sp_value.setValue(50)
        else:
            self.sp_value.setRange(1, 30000)

    def current_options(self) -> ImageOptions:
        return ImageOptions(
            rule=NameRule(
                base_name=self.ed_base.text().strip(),
                number_position=NumberPosition(self.cb_number.currentData()),
                number_digits=self.sp_digits.value(),
            ),
            resize_mode=ResizeMode(self.cb_resize.currentData()),
            resize_value=self.sp_value.value(),
            box_width=self.sp_box_w.value(),
            box_height=self.sp_box_h.value(),
            allow_upscale=self.chk_upscale.isChecked(),
            output_format=self.cb_format.currentData() or "",
            jpeg_quality=self.sp_quality.value(),
        )

    def validate_options(self) -> str | None:
        return self.current_options().validate()

    def build_plan(self, files: list[Path], output: Path | None) -> list[PlannedAction]:
        assert output is not None
        return image_job.plan_images(files, self.current_options(), output)

    def make_executor(self, actions: list[PlannedAction]) -> Callable[..., JobReport]:
        options = self.current_options()
        return lambda on_progress, should_cancel: image_job.execute(
            actions, options, on_progress=on_progress, should_cancel=should_cancel
        )

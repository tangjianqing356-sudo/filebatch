"""批量重命名 / 自动编号。"""
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

from ...core import rename_job
from ...core.naming import CaseMode, NameRule, NumberPosition
from ...core.result import JobReport, PlannedAction
from ..messages import TEXT
from ..presets import CUSTOM, RENAME_PRESETS
from ..widgets.collapsible import CollapsibleSection
from .base_page import BaseJobPage


class RenamePage(BaseJobPage):
    TITLE = "批量重命名 / 自动编号"
    SUBTITLE = "给一批文件统一改名、加前后缀、自动编号。默认输出到新文件夹，原文件不动。"

    DANGER_LABEL = "直接重命名原文件（不保留副本）"
    DANGER_WARNING = TEXT["in_place_warning"]
    DANGER_CONFIRM_TITLE = TEXT["in_place_confirm_title"]
    DANGER_CONFIRM_BODY = TEXT["in_place_confirm_body"]
    DANGER_CONFIRM_OK = TEXT["in_place_confirm_ok"]

    # ---- 兼容旧名字，界面测试里用的是这些 ----
    @property
    def chk_in_place(self) -> QCheckBox:
        assert self.chk_danger is not None
        return self.chk_danger

    @property
    def lbl_in_place_warn(self) -> QLabel:
        assert self.lbl_danger_warn is not None
        return self.lbl_danger_warn

    @property
    def _output_dir(self) -> Path | None:
        return self._output_path

    @_output_dir.setter
    def _output_dir(self, value: Path | None) -> None:
        self._output_path = value

    # ---- 参数区 ----

    def build_options(self, layout: QVBoxLayout) -> None:
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setSpacing(8)

        self.cb_preset = QComboBox()
        for preset in RENAME_PRESETS:
            self.cb_preset.addItem(preset.name, preset)
        form.addRow("常用预设", self.cb_preset)
        self.lbl_preset_hint = QLabel(CUSTOM.hint)
        self.lbl_preset_hint.setObjectName("Hint")
        self.lbl_preset_hint.setWordWrap(True)
        form.addRow("", self.lbl_preset_hint)

        self.ed_base = QLineEdit()
        self.ed_base.setPlaceholderText("留空则保留原文件名")
        form.addRow("统一改名为", self.ed_base)

        self.ed_prefix = QLineEdit()
        self.ed_prefix.setPlaceholderText("例如：2026_")
        form.addRow("前缀", self.ed_prefix)

        self.ed_suffix = QLineEdit()
        self.ed_suffix.setPlaceholderText("例如：_终稿")
        form.addRow("后缀", self.ed_suffix)

        self.cb_number = QComboBox()
        self.cb_number.addItem("不编号", NumberPosition.NONE)
        self.cb_number.addItem("加在名字后面", NumberPosition.SUFFIX)
        self.cb_number.addItem("加在名字前面", NumberPosition.PREFIX)
        form.addRow("自动编号", self.cb_number)

        num_row = QHBoxLayout()
        num_row.setContentsMargins(0, 0, 0, 0)
        num_row.setSpacing(4)
        self.sp_start = QSpinBox()
        self.sp_start.setRange(0, 999999)
        self.sp_start.setValue(1)
        self.sp_start.setMaximumWidth(90)
        self.sp_digits = QSpinBox()
        self.sp_digits.setRange(1, 10)
        self.sp_digits.setValue(3)
        self.sp_digits.setMaximumWidth(70)
        num_row.addWidget(QLabel("从"))
        num_row.addWidget(self.sp_start)
        num_row.addWidget(QLabel("起，"))
        num_row.addWidget(self.sp_digits)
        num_row.addWidget(QLabel("位"))
        num_row.addStretch(1)
        self.num_row_widget = QWidget()
        self.num_row_widget.setLayout(num_row)
        self.num_row_widget.setMinimumHeight(self.sp_start.sizeHint().height() + 6)
        form.addRow("", self.num_row_widget)

        layout.addLayout(form)

        adv = CollapsibleSection("高级选项（查找替换、大小写、编号分隔符）")
        adv_form = QFormLayout()
        adv_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        adv_form.setSpacing(8)

        self.ed_find = QLineEdit()
        self.ed_find.setPlaceholderText("在原文件名中查找")
        adv_form.addRow("查找", self.ed_find)
        self.ed_replace = QLineEdit()
        self.ed_replace.setPlaceholderText("替换成")
        adv_form.addRow("替换为", self.ed_replace)
        self.chk_regex = QCheckBox("按正则表达式匹配")
        adv_form.addRow("", self.chk_regex)

        self.cb_case = QComboBox()
        self.cb_case.addItem("保持不变", CaseMode.KEEP)
        self.cb_case.addItem("全部小写", CaseMode.LOWER)
        self.cb_case.addItem("全部大写", CaseMode.UPPER)
        adv_form.addRow("英文大小写", self.cb_case)

        self.ed_sep = QLineEdit("_")
        self.ed_sep.setMaximumWidth(80)
        adv_form.addRow("编号分隔符", self.ed_sep)

        adv_wrap = QWidget()
        adv_wrap.setLayout(adv_form)
        adv.add_widget(adv_wrap)
        layout.addWidget(adv)

    def register_invalidators(self) -> None:
        for w in (self.ed_base, self.ed_prefix, self.ed_suffix, self.ed_find,
                  self.ed_replace, self.ed_sep):
            w.textChanged.connect(self._invalidate_preview)
        for w in (self.cb_number, self.cb_case):
            w.currentIndexChanged.connect(self._invalidate_preview)
        for w in (self.sp_start, self.sp_digits):
            w.valueChanged.connect(self._invalidate_preview)
        self.chk_regex.toggled.connect(self._invalidate_preview)
        self.cb_preset.currentIndexChanged.connect(self._apply_preset)
        self.cb_number.currentIndexChanged.connect(self._sync_number_row)
        self._sync_number_row()

    def _sync_number_row(self) -> None:
        on = NumberPosition(self.cb_number.currentData()) is not NumberPosition.NONE
        self.num_row_widget.setEnabled(on)

    def _apply_preset(self) -> None:
        preset = self.cb_preset.currentData()
        if preset is None:
            return
        self.lbl_preset_hint.setText(preset.hint)
        if not preset.values:
            return

        v = preset.values
        self.ed_base.setText(v.get("base_name", ""))
        self.ed_prefix.setText(v.get("prefix", ""))
        self.ed_suffix.setText(v.get("suffix", ""))
        if "number_separator" in v:
            self.ed_sep.setText(v["number_separator"])
        if "number_start" in v:
            self.sp_start.setValue(v["number_start"])
        if "number_digits" in v:
            self.sp_digits.setValue(v["number_digits"])
        pos = v.get("number_position")
        if pos is not None:
            idx = self.cb_number.findData(pos)
            if idx >= 0:
                self.cb_number.setCurrentIndex(idx)
        case = v.get("case_mode")
        if case is not None:
            idx = self.cb_case.findData(case)
            if idx >= 0:
                self.cb_case.setCurrentIndex(idx)

    # ---- 业务 ----

    def current_rule(self) -> NameRule:
        return NameRule(
            base_name=self.ed_base.text().strip(),
            find=self.ed_find.text(),
            replace=self.ed_replace.text(),
            use_regex=self.chk_regex.isChecked(),
            prefix=self.ed_prefix.text(),
            suffix=self.ed_suffix.text(),
            # 显式转回枚举：Qt 的 currentData() 会把 str 子类枚举退化成普通字符串
            case_mode=CaseMode(self.cb_case.currentData()),
            number_position=NumberPosition(self.cb_number.currentData()),
            number_start=self.sp_start.value(),
            number_digits=self.sp_digits.value(),
            number_separator=self.ed_sep.text(),
        )

    def validate_options(self) -> str | None:
        return self.current_rule().validate()

    def build_plan(self, files: list[Path], output: Path | None) -> list[PlannedAction]:
        return rename_job.plan_rename(files, self.current_rule(), output, self.danger_enabled())

    def make_executor(self, actions: list[PlannedAction]) -> Callable[..., JobReport]:
        in_place = self.danger_enabled()
        return lambda on_progress, should_cancel: rename_job.execute(
            actions, in_place, on_progress=on_progress, should_cancel=should_cancel
        )

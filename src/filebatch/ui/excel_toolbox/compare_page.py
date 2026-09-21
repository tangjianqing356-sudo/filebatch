"""两表对比：找出两张表之间的差异。

A 表和 B 表由用户**明确选**，不靠文件清单的顺序猜。
清单里可以放一堆文件，挑其中两个来比。
"""
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
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ...core.excel import compare_job
from ...core.excel.compare_job import CompareOptions
from ...core.excel.workbook import SUPPORTED_SUFFIXES
from ...core.result import JobReport, PlannedAction
from ..widgets.collapsible import CollapsibleSection
from .columns import ColumnAwarePage, ColumnCheckList


class ComparePage(ColumnAwarePage):
    TITLE = "两表对比"
    SUBTITLE = "比较两张表，输出「仅A表有 / 仅B表有 / 内容不同 / 汇总」四张工作表。"
    FILE_SUFFIXES = SUPPORTED_SUFFIXES
    OUTPUT_IS_FILE = True
    OUTPUT_FILE_FILTER = "Excel 文件 (*.xlsx)"
    DEFAULT_OUTPUT_NAME = "对比结果.xlsx"
    OUTPUT_LABEL = "选择保存位置"
    # A/B 是用户自己挑的，清单一变由 _sync_choices 统一决定要不要重读列名
    REFRESH_ON_FILE_CHANGE = False

    def build_options(self, layout: QVBoxLayout) -> None:
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setSpacing(8)

        self.cb_a = QComboBox()
        self.cb_b = QComboBox()
        for cb in (self.cb_a, self.cb_b):
            cb.setSizeAdjustPolicy(
                QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
            )
            cb.setMinimumContentsLength(12)
        form.addRow("A 表", self.cb_a)
        form.addRow("B 表", self.cb_b)
        form.addRow("", self.make_header_checkbox())
        layout.addLayout(form)

        bar = QHBoxLayout()
        self.btn_swap = QPushButton("交换 A / B")
        bar.addWidget(self.btn_swap)
        bar.addStretch(1)
        layout.addLayout(bar)

        self.lbl_ab = QLabel("请在上面选出要比较的两个文件")
        self.lbl_ab.setObjectName("Hint")
        self.lbl_ab.setWordWrap(True)
        layout.addWidget(self.lbl_ab)

        layout.addWidget(QLabel("关键列（用来确定两表里哪两行是同一条记录）"))
        self.list_keys = ColumnCheckList()
        layout.addWidget(self.list_keys)
        self.make_column_hint(layout)

        adv = CollapsibleSection("高级选项（比较方式、只比部分列）")
        av = QVBoxLayout()
        self.chk_trim = QCheckBox("比较时忽略首尾空格")
        self.chk_trim.setChecked(True)
        self.chk_case = QCheckBox("比较时忽略英文大小写")
        av.addWidget(self.chk_trim)
        av.addWidget(self.chk_case)
        av.addWidget(QLabel("只比较这些列（都不勾 = 比较除关键列外的所有共有列）"))
        self.list_compare = ColumnCheckList()
        av.addWidget(self.list_compare)
        wrap = QWidget()
        wrap.setLayout(av)
        adv.add_widget(wrap)
        layout.addWidget(adv)

    def register_invalidators(self) -> None:
        super().register_invalidators()
        self.list_keys.itemChanged.connect(lambda *_: self._invalidate_preview())
        self.list_compare.itemChanged.connect(lambda *_: self._invalidate_preview())
        self.chk_trim.toggled.connect(self._invalidate_preview)
        self.chk_case.toggled.connect(self._invalidate_preview)
        self.btn_swap.clicked.connect(self._swap)
        # 文件清单一变，两个下拉要跟着同步
        self.file_list.changed.connect(self._sync_choices)
        self.cb_a.currentIndexChanged.connect(lambda *_: self._on_pick(self.cb_a, self.cb_b))
        self.cb_b.currentIndexChanged.connect(lambda *_: self._on_pick(self.cb_b, self.cb_a))
        self._sync_choices()

    # ---------------- A / B 选择 ----------------

    def _paths(self) -> list[Path]:
        return self.file_list.files()

    def _current(self, cb: QComboBox) -> Path | None:
        data = cb.currentData()
        return Path(data) if data else None

    def _select(self, cb: QComboBox, path: Path | None) -> None:
        """选中某个路径，不触发一串连锁信号。"""
        idx = cb.findData(str(path)) if path is not None else -1
        if idx == cb.currentIndex():
            return
        blocked = cb.blockSignals(True)
        cb.setCurrentIndex(idx)
        cb.blockSignals(blocked)

    def _sync_choices(self) -> None:
        """清单变了（加文件、删文件、清空）就重建两个下拉。

        原则：用户选过的文件只要还在清单里就保持不动；
        没了才自动挑一个，挑不出来就留空，由 validate_options 去拦。
        """
        files = self._paths()
        旧A, 旧B = self._current(self.cb_a), self._current(self.cb_b)

        for cb in (self.cb_a, self.cb_b):
            blocked = cb.blockSignals(True)
            cb.clear()
            for f in files:
                cb.addItem(f.name, str(f))
            cb.blockSignals(blocked)

        存在 = set(files)
        新A = 旧A if 旧A in 存在 else (files[0] if files else None)
        新B = 旧B if 旧B in 存在 else None
        if 新B is None or 新B == 新A:
            新B = next((f for f in files if f != 新A), None)

        self._select(self.cb_a, 新A)
        self._select(self.cb_b, 新B)
        self._after_choice_changed()

    def _on_pick(self, 改的: QComboBox, 另一个: QComboBox) -> None:
        """两边不能选同一个文件：撞上了就把另一边挪到别的文件去。"""
        选中 = self._current(改的)
        if 选中 is not None and 选中 == self._current(另一个):
            别的 = next((f for f in self._paths() if f != 选中), None)
            self._select(另一个, 别的)
        self._after_choice_changed()

    def _swap(self) -> None:
        a, b = self._current(self.cb_a), self._current(self.cb_b)
        self._select(self.cb_a, b)
        self._select(self.cb_b, a)
        self._after_choice_changed()

    def _after_choice_changed(self) -> None:
        a, b = self._current(self.cb_a), self._current(self.cb_b)
        if a is not None and b is not None:
            self.lbl_ab.setText(f"将比较：A = {a.name}　→　B = {b.name}")
        elif len(self._paths()) < 2:
            self.lbl_ab.setText(
                f"当前只有 {len(self._paths())} 个文件，两表对比需要在清单里至少放 2 个"
            )
        else:
            self.lbl_ab.setText("请在上面选出要比较的两个文件")
        # 换了要比的文件，列名和表头体检都得重来
        self.refresh_columns()
        self._invalidate_preview()

    # ---------------- 列 ----------------

    def target_files(self) -> list[Path]:
        """只看 A、B 两个文件：清单里其它文件跟这次对比无关。"""
        return [p for p in (self._current(self.cb_a), self._current(self.cb_b)) if p is not None]

    def required_columns(self) -> list[str]:
        return self.list_keys.checked() + self.list_compare.checked()

    def on_columns_ready(self, columns: list[str]) -> None:
        self.list_keys.set_columns(columns)
        self.list_compare.set_columns(columns)

    # ---------------- 参数与执行 ----------------

    def current_options(self) -> CompareOptions:
        return CompareOptions(
            key_columns=self.list_keys.checked(),
            has_header=self.chk_header.isChecked(),
            ignore_case=self.chk_case.isChecked(),
            trim_spaces=self.chk_trim.isChecked(),
            compare_columns=self.list_compare.checked(),
        )

    def selected_pair(self) -> tuple[Path | None, Path | None]:
        return self._current(self.cb_a), self._current(self.cb_b)

    def validate_options(self) -> str | None:
        a, b = self.selected_pair()
        files = set(self._paths())
        if a is None or b is None:
            return "请分别选好 A 表和 B 表（清单里至少要有 2 个文件）。"
        if a == b:
            return "A 表和 B 表不能是同一个文件。"
        if a not in files or b not in files:
            return "选中的文件已经不在清单里了，请重新选择 A 表和 B 表。"
        return self.current_options().validate()

    def build_plan(self, files: list[Path], output: Path | None) -> list[PlannedAction]:
        assert output is not None
        a, b = self.selected_pair()
        assert a is not None and b is not None
        return compare_job.plan([a, b], self.current_options(), output)

    def make_executor(self, actions: list[PlannedAction]) -> Callable[..., JobReport]:
        options = self.current_options()
        output = self._output_path
        assert output is not None
        return lambda on_progress, should_cancel: compare_job.execute(
            actions, options, output, on_progress=on_progress, should_cancel=should_cancel
        )

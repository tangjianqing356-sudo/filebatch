"""所有功能页的公共骨架。

批量重命名那条链路已经验证过了，剩下五个功能走的是同一套流程：
拖拽添加 → 参数设置 → 生成预览 → 用户确认 → 后台执行 → 进度 → 日志 → 完成摘要。

把它抽成基类，子类只需要回答四个问题：
  1. 参数控件长什么样        build_options()
  2. 参数合不合法            validate_options()
  3. 计划怎么算              build_plan()
  4. 计划怎么执行            make_executor()

安全规则（预览前不许执行、参数一改预览作废、危险开关二次确认、中断不回滚）
统一在基类里实现，子类想绕过都绕不过去。
"""
from __future__ import annotations

import time
from abc import abstractmethod
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QUrl, Qt
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from ...core.pathlimits import PathLimit, annotate_over_limit, probe_path_limit
from ...core.result import JobReport, PlannedAction
from ...core.safety import validate_output_dir
from ..messages import TEXT, humanize, technical_detail
from ..widgets.confirm import confirm_dangerous, show_error, show_info
from ..widgets.drop_area import FileListWidget
from ..widgets.elided_label import ElidedLabel
from ..widgets.log_panel import LogPanel
from ..widgets.preview_table import PreviewTable
from ..widgets.step_indicator import StepIndicator
from ..worker import JobWorker


class BaseJobPage(QWidget):
    # ---- 子类用这些常量描述自己 ----
    TITLE = ""
    SUBTITLE = ""
    FILE_SUFFIXES: set[str] | None = None      # 只接受这些扩展名，None 表示不限
    NEEDS_OUTPUT_DIR = True
    OUTPUT_IS_FILE = False                     # True 表示输出是单个文件（PDF/表格合并）
    OUTPUT_FILE_FILTER = ""
    DEFAULT_OUTPUT_NAME = ""
    OUTPUT_LABEL = "选择输出文件夹"

    # 危险开关（不需要就保持 None）
    DANGER_LABEL: str | None = None
    DANGER_WARNING = ""
    DANGER_CONFIRM_TITLE = ""
    DANGER_CONFIRM_BODY = ""
    DANGER_CONFIRM_OK = ""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._actions: list[PlannedAction] = []
        self._worker: JobWorker | None = None
        self._last_report: JobReport | None = None
        self._output_path: Path | None = None
        # 路径长度上限按输出目录缓存：探测要建删一堆临时目录，不能每次预览都跑
        self._path_limit: tuple[str, PathLimit] | None = None
        self._build()
        self.register_invalidators()
        self._invalidate_preview()

    # ================= 子类必须/可以实现 =================

    @abstractmethod
    def build_options(self, layout: QVBoxLayout) -> None:
        """把参数控件塞进 layout。"""

    def validate_options(self) -> str | None:
        """返回中文错误说明，None 表示没问题。"""
        return None

    @abstractmethod
    def build_plan(self, files: list[Path], output: Path | None) -> list[PlannedAction]:
        """只读地算出计划，绝不能写文件。"""

    @abstractmethod
    def make_executor(self, actions: list[PlannedAction]) -> Callable[..., JobReport]:
        """返回一个接受 on_progress / should_cancel 的可调用对象。"""

    def annotate_plan(self, actions: list[PlannedAction]) -> None:
        """计划算完、还没渲染到预览表之前的钩子。

        子类可以在这里往 note 里补充提示，但**不要**在这里做文件 I/O——
        这个方法跑在界面线程上。
        """

    def register_invalidators(self) -> None:
        """把自己的参数控件接到 _invalidate_preview 上。"""

    def danger_enabled(self) -> bool:
        return bool(self.chk_danger and self.chk_danger.isChecked())

    def output_is_file(self) -> bool:
        """输出的是单个文件还是文件夹。

        做成方法而不是常量，是因为 PDF 页里"拆分"输出到文件夹、"合并"输出到单个文件，
        同一个页面会来回切。
        """
        return self.OUTPUT_IS_FILE

    def output_dialog_title(self) -> str:
        return "保存到" if self.output_is_file() else "选择输出文件夹"

    # ================= 界面骨架 =================

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 14, 18, 14)
        root.setSpacing(10)

        title = QLabel(self.TITLE)
        title.setObjectName("SectionTitle")
        root.addWidget(title)
        subtitle = QLabel(self.SUBTITLE)
        subtitle.setObjectName("Hint")
        subtitle.setWordWrap(True)
        root.addWidget(subtitle)

        self.steps = StepIndicator()
        root.addWidget(self.steps)

        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.addWidget(self._build_top())
        splitter.addWidget(self._build_bottom())
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        root.addWidget(splitter, 1)

    def _build_top(self) -> QWidget:
        wrap = QWidget()
        lay = QHBoxLayout(wrap)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)

        box_files = QGroupBox("① 选择文件")
        v = QVBoxLayout(box_files)
        self.file_list = FileListWidget(suffixes=self.FILE_SUFFIXES)
        self.file_list.changed.connect(self._invalidate_preview)
        self.file_list.scanning_changed.connect(self._on_scanning_changed)
        self.file_list.scan_failed.connect(
            lambda human, detail: show_error(self, "扫描文件失败", human, detail)
        )
        v.addWidget(self.file_list)
        lay.addWidget(box_files, 5)

        box_opts = QGroupBox("② 设置规则")
        box_opts_layout = QVBoxLayout(box_opts)
        box_opts_layout.setContentsMargins(0, 6, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(
            "QScrollArea, QScrollArea > QWidget > QWidget { background: transparent; }"
        )
        opts_content = QWidget()
        ov = QVBoxLayout(opts_content)
        ov.setContentsMargins(12, 6, 12, 6)
        ov.setSpacing(8)
        self.build_options(ov)
        ov.addStretch(1)
        scroll.setWidget(opts_content)
        box_opts_layout.addWidget(scroll)

        # 输出位置和危险开关固定在底部，不进滚动区：这两个是必须做的决定
        pinned = QWidget()
        pv = QVBoxLayout(pinned)
        pv.setContentsMargins(12, 6, 12, 8)
        pv.setSpacing(6)

        self.btn_output = QPushButton(self.OUTPUT_LABEL)
        self.lbl_output = ElidedLabel("未选择")
        self.lbl_output.setObjectName("Hint")
        if self.NEEDS_OUTPUT_DIR:
            out_row = QHBoxLayout()
            out_row.addWidget(self.btn_output)
            out_row.addWidget(self.lbl_output, 1)
            pv.addLayout(out_row)
            self.btn_output.clicked.connect(self._pick_output)

        self.chk_danger: QCheckBox | None = None
        self.lbl_danger_warn: QLabel | None = None
        if self.DANGER_LABEL:
            self.chk_danger = QCheckBox(self.DANGER_LABEL)
            pv.addWidget(self.chk_danger)
            self.lbl_danger_warn = QLabel(self.DANGER_WARNING)
            self.lbl_danger_warn.setObjectName("WarningText")
            self.lbl_danger_warn.setWordWrap(True)
            self.lbl_danger_warn.setVisible(False)
            pv.addWidget(self.lbl_danger_warn)
            self.chk_danger.toggled.connect(self._on_danger_toggled)

        box_opts_layout.addWidget(pinned)
        lay.addWidget(box_opts, 4)
        return wrap

    def _build_bottom(self) -> QWidget:
        wrap = QWidget()
        lay = QVBoxLayout(wrap)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)

        bar = QHBoxLayout()
        self.btn_preview = QPushButton("生成预览")
        self.btn_preview.setObjectName("Primary")
        self.btn_execute = QPushButton("开始执行")
        self.btn_execute.setObjectName("Primary")
        self.btn_cancel = QPushButton("中断")
        self.btn_cancel.setObjectName("Danger")
        self.btn_cancel.setVisible(False)
        bar.addWidget(self.btn_preview)
        bar.addWidget(self.btn_execute)
        bar.addWidget(self.btn_cancel)
        bar.addSpacing(10)
        self.lbl_status = QLabel(TEXT["preview_first"])
        self.lbl_status.setObjectName("Hint")
        bar.addWidget(self.lbl_status, 1)
        lay.addLayout(bar)

        self.progress = QProgressBar()
        self.progress.setVisible(False)
        lay.addWidget(self.progress)

        split = QSplitter(Qt.Orientation.Horizontal)
        self.box_preview = QGroupBox("③ 预览（确认无误后再执行）")
        pv = QVBoxLayout(self.box_preview)
        self.preview = PreviewTable()
        pv.addWidget(self.preview)
        split.addWidget(self.box_preview)

        box_log = QGroupBox("④ 执行日志")
        lv = QVBoxLayout(box_log)
        self.log = LogPanel()
        lv.addWidget(self.log)
        log_bar = QHBoxLayout()
        self.btn_open_output = QPushButton("打开输出文件夹")
        self.btn_save_log = QPushButton("保存日志")
        self.btn_open_output.setEnabled(False)
        self.btn_save_log.setEnabled(False)
        log_bar.addWidget(self.btn_open_output)
        log_bar.addWidget(self.btn_save_log)
        log_bar.addStretch(1)
        lv.addLayout(log_bar)
        split.addWidget(box_log)
        # 预览比日志更需要宽度：文件名 + 目标名 + 说明三列都要看得清
        split.setSizes([680, 340])
        lay.addWidget(split, 1)

        self.btn_preview.clicked.connect(self.generate_preview)
        self.btn_execute.clicked.connect(self.start_execute)
        self.btn_cancel.clicked.connect(self._cancel)
        self.btn_open_output.clicked.connect(self._open_output_dir)
        self.btn_save_log.clicked.connect(self._save_log)
        return wrap

    # ================= 状态管理 =================

    def _on_danger_toggled(self, checked: bool) -> None:
        if self.lbl_danger_warn:
            self.lbl_danger_warn.setVisible(checked)
        if self.NEEDS_OUTPUT_DIR:
            self.btn_output.setEnabled(not checked)
            self.lbl_output.setEnabled(not checked)
        self._invalidate_preview()

    def _invalidate_preview(self) -> None:
        self._actions = []
        self.preview.reset_to_preview_mode()
        self.box_preview.setTitle("③ 预览（确认无误后再执行）")
        self.btn_execute.setEnabled(False)
        self._update_steps()
        if self.btn_cancel.isVisible():
            return
        self.lbl_status.setText(TEXT["preview_first"])

    def _update_steps(self) -> None:
        if not self.file_list.files():
            self.steps.set_current(0)
        elif not self._actions:
            self.steps.set_current(1)
        elif self.btn_execute.isEnabled():
            self.steps.set_current(3)
        else:
            self.steps.set_current(2)

    def _on_scanning_changed(self, scanning: bool) -> None:
        self.btn_preview.setEnabled(not scanning)
        self.lbl_status.setText("正在扫描文件…" if scanning else TEXT["preview_first"])

    # ================= 预览 =================

    def generate_preview(self) -> bool:
        files = self.file_list.files()
        if not files:
            show_info(self, "还没有文件", "请先拖入或添加要处理的文件。")
            return False

        err = self.validate_options()
        if err:
            show_error(self, "设置有误", err)
            return False

        output = self._output_path
        if self.NEEDS_OUTPUT_DIR and not self.danger_enabled():
            if output is None:
                show_error(self, "还没选输出位置", TEXT["output_not_set"])
                return False
            check_dir = output.parent if self.output_is_file() else output
            bad = validate_output_dir(check_dir, files)
            if bad:
                show_error(self, "输出位置不合适", bad)
                return False

        try:
            self._actions = self.build_plan(files, output)
        except Exception as e:
            show_error(self, "生成预览失败", humanize(e), technical_detail(e))
            return False

        # 子类可以在这里往计划项上补自己的提示（例如表头不一致）
        self.annotate_plan(self._actions)

        # 路径过长在 Windows 上很常见。实测当前输出位置的上限，
        # 在预览阶段就把会失败的项拦下来，而不是执行到一半甩系统错误。
        过长 = self._annotate_path_limits(self._actions)

        self.preview.show_actions(self._actions)
        runnable = sum(1 for a in self._actions if a.will_run)
        skipped = len(self._actions) - runnable
        if 过长:
            self.log.log(f"有 {过长} 项因为路径过长被拦下，已在预览里标出原因")

        if runnable == 0:
            self.btn_execute.setEnabled(False)
            self.lbl_status.setText(TEXT["preview_empty"])
            self._update_steps()
            return False

        self.btn_execute.setEnabled(True)
        msg = f"预览完成：{runnable} 项将被处理"
        if skipped:
            msg += f"，{skipped} 项将跳过"
        msg += "。确认无误后点「开始执行」"
        self.lbl_status.setText(msg)
        self.log.log(msg)
        self._update_steps()
        return True

    def _annotate_path_limits(self, actions: list[PlannedAction]) -> int:
        """实测输出位置的路径长度上限，把会超限的计划项标成跳过。"""
        if not any(a.will_run and a.target is not None for a in actions):
            return 0
        if self._path_limit is None:
            # 在系统临时目录里测，不碰输出目录——预览阶段必须一个文件都不写
            limit = probe_path_limit()
            self._path_limit = ("", limit)
            self.log.log(limit.describe())
        return annotate_over_limit(actions, self._path_limit[1])

    # ================= 执行 =================

    def start_execute(self) -> bool:
        if not self._actions:
            show_info(self, "请先预览", TEXT["preview_first"])
            return False

        if self.danger_enabled() and not confirm_dangerous(
            self,
            self.DANGER_CONFIRM_TITLE,
            self.DANGER_CONFIRM_BODY,
            self.DANGER_CONFIRM_OK,
            TEXT["cancel"],
        ):
            self.log.log("用户取消了危险操作")
            return False

        total = sum(1 for a in self._actions if a.will_run)
        self.log.log(f"开始执行，共 {total} 项……")
        self._set_running(True)
        self.progress.setRange(0, len(self._actions))
        self.progress.setValue(0)

        self._worker = JobWorker(self.make_executor(self._actions))
        self._worker.progress.connect(self._on_progress)
        self._worker.finished_report.connect(self._on_finished)
        self._worker.failed.connect(self._on_failed)
        self._worker.start()
        return True

    def _cancel(self) -> None:
        if self._worker:
            self._worker.cancel()
            self.lbl_status.setText("正在中断……将在当前文件处理完成后停止，已完成的会保留")
            self.log.log("收到中断请求：将在当前文件处理完成后停止，已完成的文件保留不变")
            self.btn_cancel.setEnabled(False)

    def _set_running(self, running: bool) -> None:
        self.progress.setVisible(running)
        self.btn_cancel.setVisible(running)
        self.btn_cancel.setEnabled(running)
        self.btn_preview.setEnabled(not running)
        self.btn_execute.setEnabled(False)
        self.file_list.setEnabled(not running)

    def _on_progress(self, done: int, total: int, name: str) -> None:
        self.progress.setValue(done)
        self.lbl_status.setText(f"正在处理 {done}/{total}：{name}")

    def _on_finished(self, report: JobReport) -> None:
        self._last_report = report
        self._set_running(False)
        self.progress.setVisible(False)

        self.log.log(report.summary())
        self.log.log_lines("\n".join(report.to_brief_lines()))

        self.btn_save_log.setEnabled(True)
        self.btn_open_output.setEnabled(True)
        self.lbl_status.setText(report.summary())
        self._actions = []
        self.box_preview.setTitle("③ 本次执行结果（如需再次处理，请重新生成预览）")
        self.preview.show_results(report)
        self.steps.set_current(3)

        body = report.summary()
        if report.failed:
            body += "\n\n有文件处理失败，具体原因见下方日志。"
        show_info(self, "处理完成", body)

    def _on_failed(self, human: str, detail: str) -> None:
        self._set_running(False)
        self.progress.setVisible(False)
        self.lbl_status.setText("执行失败")
        self.log.log(f"执行失败：{human}")
        self.log.log(f"技术细节：{detail}")
        show_error(self, "执行失败", human, detail)

    # ================= 收尾 =================

    def is_busy(self) -> bool:
        """是否有任务正在执行（扫描不算，扫描停掉没有副作用）。"""
        return self._worker is not None and self._worker.isRunning()

    def active_workers(self) -> list:
        """正在跑的后台线程。主窗口等待安全退出时按这个列表逐个 wait。

        做成列表而不是直接暴露 `_worker`，是因为 Excel 工具箱那种容器页面
        底下挂着好几个子页面，可能同时有多个线程在跑。
        """
        if self._worker is not None and self._worker.isRunning():
            return [self._worker]
        return []

    def request_stop(self) -> None:
        """请求停止，不阻塞等待。真正的等待交给主窗口统一处理。"""
        self.file_list.stop_scan()
        if self._worker is not None and self._worker.isRunning():
            self._worker.cancel()

    def stop_background_work(self) -> None:
        """请求停止并等它收尾。

        等待是必须的：worker 是在两个文件之间检查取消标志的，
        如果不等当前这个文件写完就让进程退出，会留下一个残缺文件。
        """
        self.request_stop()
        if self._worker is not None and self._worker.isRunning():
            self._worker.wait(30000)

    def _pick_output(self) -> None:
        if self.output_is_file():
            name, _ = QFileDialog.getSaveFileName(
                self, self.output_dialog_title(), self.DEFAULT_OUTPUT_NAME, self.OUTPUT_FILE_FILTER
            )
        else:
            name = QFileDialog.getExistingDirectory(self, self.output_dialog_title())
        if name:
            self._output_path = Path(name)
            self.lbl_output.setFullText(str(self._output_path))
            self._path_limit = None      # 换了位置，之前测的上限不作数了
            self._invalidate_preview()

    def _open_output_dir(self) -> None:
        target = self._output_path
        if target is not None and self.output_is_file():
            target = target.parent
        if target is None or not target.exists():
            files = self.file_list.files()
            target = files[0].parent if files else None
        if target is None or not target.exists():
            show_info(self, "打不开", "输出位置还不存在。")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(target)))

    def _save_log(self) -> None:
        if self._last_report is None:
            return
        default = f"处理日志_{time.strftime('%Y%m%d_%H%M%S')}.txt"
        name, _ = QFileDialog.getSaveFileName(self, "保存日志", default, "文本文件 (*.txt)")
        if not name:
            return
        try:
            Path(name).write_text(self._last_report.to_log_text(), encoding="utf-8")
            show_info(self, "已保存", f"日志已保存到：\n{name}")
        except Exception as e:
            show_error(self, "保存失败", humanize(e), technical_detail(e))

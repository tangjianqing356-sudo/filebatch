"""列名从哪来。

去重、对比、拆表都要让用户"选一列"，而列名只能从文件里读。
读表头这件事不能放在主线程：一个十万行的 xlsx 读下来要好几秒，界面会假死。
所以沿用扫描那套做法——丢到 QThread，读完用信号回来填下拉框。
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QDeadlineTimer, QElapsedTimer, Qt, QThread, Signal
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QProgressDialog,
    QVBoxLayout,
)

from ...core.excel.inspect import (
    HeaderReport,
    SheetInfo,
    all_columns,
    check_headers,
    common_columns,
    inspect_file,
)
from ...core.result import PlannedAction
from ..pages.base_page import BaseJobPage

# 填列下拉时只读前几个文件：批量处理时各文件的表头通常一致，
# 全读一遍在几百个文件的场景会白等很久。
#
# 但"只读前 20 个"意味着用户可能选到一个只有前面几个文件才有的列，
# 所以**预览阶段会对全部文件再体检一遍**（同样在后台线程里），
# 缺列、表头不一致的文件在执行前就摆出来，不留到 execute 才失败。
MAX_INSPECT_FILES = 20


class InspectWorker(QThread):
    """后台读表头。"""

    progress = Signal(int, int, str)   # 已读, 总数, 当前文件名
    finished_infos = Signal(list)      # list[SheetInfo]

    def __init__(self, files: list[Path], has_header: bool, parent=None) -> None:  # noqa: ANN001
        super().__init__(parent)
        self._files = files
        self._has_header = has_header
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    @property
    def cancelled(self) -> bool:
        return self._cancelled

    def run(self) -> None:  # noqa: D102
        infos: list[SheetInfo] = []
        总数 = len(self._files)
        for i, path in enumerate(self._files, start=1):
            if self._cancelled:
                return
            try:
                infos.append(inspect_file(path, self._has_header))
            except Exception as e:      # inspect_file 自己兜了底，这里是双保险
                infos.append(SheetInfo(path=path, error=f"读取失败：{e}"))
            self.progress.emit(i, 总数, path.name)
        if not self._cancelled:
            self.finished_infos.emit(infos)


class ColumnCheckList(QListWidget):
    """可以勾多列的列表。重新填充时保留用户已经勾上的列。"""

    def __init__(self, parent=None) -> None:  # noqa: ANN001
        super().__init__(parent)
        self.setMaximumHeight(120)
        self.setSelectionMode(QListWidget.SelectionMode.NoSelection)

    def set_columns(self, columns: list[str]) -> None:
        已勾 = set(self.checked())
        self.clear()
        for name in columns:
            item = QListWidgetItem(name)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(
                Qt.CheckState.Checked if name in 已勾 else Qt.CheckState.Unchecked
            )
            self.addItem(item)

    def checked(self) -> list[str]:
        return [
            self.item(i).text()
            for i in range(self.count())
            if self.item(i).checkState() == Qt.CheckState.Checked
        ]

    def set_checked(self, names: list[str]) -> None:
        want = set(names)
        for i in range(self.count()):
            item = self.item(i)
            item.setCheckState(
                Qt.CheckState.Checked if item.text() in want else Qt.CheckState.Unchecked
            )


class ColumnAwarePage(BaseJobPage):
    """需要用户选列的页面的公共部分。

    子类只要把 `self.chk_header` 和列控件摆进界面，
    剩下的（什么时候刷新、线程怎么收尾）都在这里。
    """

    # "common" = 只给所有文件都有的列（跨文件批处理时唯一安全的选择）
    # "all"    = 任一文件出现过的列
    COLUMN_MODE = "common"

    # 文件清单一变就重读列名。两表对比那种"清单里放一堆、只挑两个比"的页面
    # 自己管刷新时机，设成 False 免得白读一遍。
    REFRESH_ON_FILE_CHANGE = True

    def __init__(self, parent=None) -> None:  # noqa: ANN001
        self._infos: list[SheetInfo] = []
        self._columns: list[str] = []
        self._inspect_worker: InspectWorker | None = None
        # 全量体检的结果，以及它是针对哪一批文件、哪些必需列算出来的。
        # 文件或选的列一变，旧结果就不作数了。
        self._header_report: HeaderReport | None = None
        self._checked_key: tuple | None = None
        self._full_worker: InspectWorker | None = None
        super().__init__(parent)

    # ---- 子类用 ----

    def make_header_checkbox(self) -> QCheckBox:
        self.chk_header = QCheckBox("第一行是表头")
        self.chk_header.setChecked(True)
        return self.chk_header

    def make_column_hint(self, layout: QVBoxLayout) -> QLabel:
        self.lbl_columns = QLabel("添加文件后会自动读出列名")
        self.lbl_columns.setObjectName("Hint")
        self.lbl_columns.setWordWrap(True)
        layout.addWidget(self.lbl_columns)
        return self.lbl_columns

    def on_columns_ready(self, columns: list[str]) -> None:
        """列名读好了，子类把它填进自己的控件。"""

    def required_columns(self) -> list[str]:
        """这次操作**必须**存在的列。子类按自己的参数返回。"""
        return []

    def target_files(self) -> list[Path]:
        """这次操作真正会碰的文件。列名从这里读，表头也体检这一批。

        默认就是清单里的全部文件；两表对比只关心选中的 A、B 两个。
        """
        return self.file_list.files()

    # ---- 机制 ----

    def register_invalidators(self) -> None:
        super().register_invalidators()
        if self.REFRESH_ON_FILE_CHANGE:
            self.file_list.changed.connect(self.refresh_columns)
        if getattr(self, "chk_header", None) is not None:
            self.chk_header.toggled.connect(self._invalidate_preview)
            self.chk_header.toggled.connect(self.refresh_columns)

    def refresh_columns(self) -> None:
        files = self.target_files()
        self._stop_inspect()
        # 换了文件，之前的全量体检作废
        self._header_report = None
        self._checked_key = None
        if not files:
            self._infos = []
            self._columns = []
            self.on_columns_ready([])
            self._say("添加文件后会自动读出列名")
            return

        取样 = files[:MAX_INSPECT_FILES]
        self._say("正在读取列名…")
        has_header = bool(getattr(self, "chk_header", None) is None
                          or self.chk_header.isChecked())
        self._inspect_worker = InspectWorker(取样, has_header, self)
        self._inspect_worker.finished_infos.connect(self._on_infos)
        self._inspect_worker.start()

    def _on_infos(self, infos: list[SheetInfo]) -> None:
        self._infos = infos
        self._columns = (
            common_columns(infos) if self.COLUMN_MODE == "common" else all_columns(infos)
        )
        self.on_columns_ready(self._columns)
        self._say(self._describe(infos))
        self._invalidate_preview()

    def _describe(self, infos: list[SheetInfo]) -> str:
        坏 = [i for i in infos if not i.ok]
        行数 = sum(i.row_count for i in infos if i.ok)
        部分 = []
        if self._columns:
            词 = "共有列" if self.COLUMN_MODE == "common" else "列"
            部分.append(f"读到 {len(self._columns)} 个{词}，{行数} 行数据")
        elif any(i.ok for i in infos):
            部分.append("这些文件没有共同的列名，请检查表头是否一致")
        if len(self.target_files()) > MAX_INSPECT_FILES:
            部分.append(f"（先读了前 {MAX_INSPECT_FILES} 个，生成预览时会检查全部）")
        if 坏:
            部分.append(f"{len(坏)} 个文件读不了：{坏[0].path.name} — {坏[0].error}")
        return "；".join(部分) or "没读到可用的列"

    def _say(self, text: str) -> None:
        if getattr(self, "lbl_columns", None) is not None:
            self.lbl_columns.setText(text)

    def _stop_inspect(self) -> None:
        if self._inspect_worker is not None:
            self._inspect_worker.cancel()
            self._inspect_worker.wait(3000)
            self._inspect_worker = None

    def _stop_full_check(self) -> None:
        if self._full_worker is not None:
            self._full_worker.cancel()
            self._full_worker.wait(5000)
            self._full_worker = None

    def request_stop(self) -> None:
        super().request_stop()
        self._stop_inspect()
        self._stop_full_check()

    def bad_files(self) -> list[SheetInfo]:
        return [i for i in self._infos if not i.ok]

    # ================= 预览前的全量表头体检 =================

    def generate_preview(self) -> bool:
        """先把全部文件的表头体检一遍，再走正常的预览流程。

        列下拉只读了前 20 个文件，用户完全可能选到一个"后面的文件没有"的列。
        这个体检在后台线程里跑，把缺列、读不了、表头不一致的文件全部摆到台面上，
        绝不留到 execute 时一个个失败。
        """
        files = self.target_files()
        if files and not self._ensure_header_check(files):
            return False        # 用户中途取消了体检
        return super().generate_preview()

    def _check_key(self, files: list[Path]) -> tuple:
        has_header = bool(getattr(self, "chk_header", None) is None
                          or self.chk_header.isChecked())
        return (tuple(str(f) for f in files), tuple(self.required_columns()), has_header)

    def _ensure_header_check(self, files: list[Path]) -> bool:
        """跑完全量体检并把结果写进日志。返回 False 表示用户取消。"""
        key = self._check_key(files)
        if self._checked_key == key and self._header_report is not None:
            self._log_header_report(self._header_report)
            return True

        infos = self._inspect_all(files, key[2])
        if infos is None:
            self.log.log("已取消表头检查，未生成预览")
            return False

        report = check_headers(infos, self.required_columns())
        self._header_report = report
        self._checked_key = key
        self._log_header_report(report)
        return True

    def _inspect_all(self, files: list[Path], has_header: bool) -> list[SheetInfo] | None:
        """在后台线程里读全部文件的表头，主线程只管转进度。None 表示被取消。"""
        self._stop_full_check()
        结果: list[SheetInfo] = []

        dlg = QProgressDialog(f"正在检查 {len(files)} 个文件的表头…", "取消", 0, len(files), self)
        dlg.setWindowTitle("检查表头")
        dlg.setWindowModality(Qt.WindowModality.WindowModal)
        # 文件少的时候一眨眼就完了，别闪一下弹窗吓人
        dlg.setMinimumDuration(400)

        worker = InspectWorker(files, has_header, self)
        self._full_worker = worker
        worker.progress.connect(
            lambda done, total, name: (dlg.setValue(done), dlg.setLabelText(f"正在检查表头 {done}/{total}：{name}"))
        )
        worker.finished_infos.connect(结果.extend)
        worker.start()

        timer = QElapsedTimer()
        timer.start()
        try:
            while worker.isRunning():
                if dlg.wasCanceled():
                    worker.cancel()
                    worker.wait(5000)
                    return None
                QApplication.processEvents()
                worker.wait(QDeadlineTimer(20))
            QApplication.processEvents()      # 让 finished_infos 投递到主线程
        finally:
            dlg.close()
            self._full_worker = None

        if worker.cancelled:
            return None
        self.log.log(f"表头检查完成，用时 {timer.elapsed()} 毫秒")
        return 结果

    def _log_header_report(self, report: HeaderReport) -> None:
        self.log.log(report.summary())
        for 行 in report.describe_lines():
            self.log.log(行)

    def annotate_plan(self, actions: list[PlannedAction]) -> None:
        """表头和基准不一致的文件，在预览里单独标一笔。

        这些文件需要的列都在，照常处理，但用户应该知道它们的表头不一样——
        很多时候这就是"选错文件"或"上个月的模板改过"的信号。
        """
        report = self._header_report
        if report is None or not report.mismatched:
            return
        不一致 = set(report.mismatched)
        for act in actions:
            if act.source in 不一致 and act.will_run:
                提示 = "⚠ 表头和其它文件不一致"
                act.note = f"{act.note}；{提示}" if act.note else 提示

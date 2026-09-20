"""文件区：支持拖拽和按钮添加，下面用表格列出来。"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...core.scan import human_size
from ..messages import TEXT
from ..scan_worker import ScanWorker


class FileListWidget(QWidget):
    """拖进来的文件清单。内容一变就发 changed，让外面把预览作废。"""

    changed = Signal()
    scanning_changed = Signal(bool)
    scan_failed = Signal(str, str)

    def __init__(self, suffixes: set[str] | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._suffixes = suffixes
        self._files: list[Path] = []
        self._scanner: ScanWorker | None = None
        self.setAcceptDrops(True)
        self._build()

    # ---------- 界面 ----------

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)

        bar = QHBoxLayout()
        bar.setSpacing(6)
        self.btn_add_files = QPushButton("添加文件")
        self.btn_add_folder = QPushButton("添加文件夹")
        self.btn_remove = QPushButton("移除")
        self.btn_clear = QPushButton("清空")
        for b in (self.btn_add_files, self.btn_add_folder, self.btn_remove, self.btn_clear):
            # 布局空间不够时 QHBoxLayout 会把按钮压到文字被截断，锁住最小宽度
            b.setMinimumWidth(b.sizeHint().width())
            bar.addWidget(b)
        bar.addStretch(1)
        self.lbl_count = QLabel("共 0 个文件")
        self.lbl_count.setObjectName("Hint")
        bar.addWidget(self.lbl_count)
        root.addLayout(bar)

        self.stack = QStackedWidget()

        self.empty_hint = QLabel(TEXT["no_files"])
        self.empty_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_hint.setObjectName("Hint")
        self.empty_hint.setStyleSheet(
            "border: 2px dashed #cbd5e1; border-radius: 10px; background: #ffffff; padding: 30px;"
        )

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["文件名", "大小", "所在文件夹"])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)

        self.stack.addWidget(self.empty_hint)
        self.stack.addWidget(self.table)
        root.addWidget(self.stack, 1)

        # 扫描状态条：平时藏着，扫大目录时出现
        self.scan_bar = QWidget()
        sb = QHBoxLayout(self.scan_bar)
        sb.setContentsMargins(0, 0, 0, 0)
        self.lbl_scanning = QLabel("正在扫描…")
        self.lbl_scanning.setObjectName("Hint")
        self.btn_cancel_scan = QPushButton("取消扫描")
        sb.addWidget(self.lbl_scanning, 1)
        sb.addWidget(self.btn_cancel_scan)
        self.scan_bar.setVisible(False)
        root.addWidget(self.scan_bar)
        self.btn_cancel_scan.clicked.connect(self._cancel_scan)

        self.btn_add_files.clicked.connect(self._pick_files)
        self.btn_add_folder.clicked.connect(self._pick_folder)
        self.btn_remove.clicked.connect(self._remove_selected)
        self.btn_clear.clicked.connect(self.clear)
        self._refresh()

    # ---------- 拖拽 ----------

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self.empty_hint.setStyleSheet(
                "border: 2px dashed #2563eb; border-radius: 10px; background: #eff6ff; padding: 30px;"
            )

    def dragLeaveEvent(self, event) -> None:  # noqa: N802, ANN001
        self._reset_hint_style()

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802
        self._reset_hint_style()
        paths = [
            Path(url.toLocalFile())
            for url in event.mimeData().urls()
            if url.isLocalFile() and url.toLocalFile()
        ]
        if paths:
            self.add_paths(paths)
            event.acceptProposedAction()

    def _reset_hint_style(self) -> None:
        self.empty_hint.setStyleSheet(
            "border: 2px dashed #cbd5e1; border-radius: 10px; background: #ffffff; padding: 30px;"
        )

    # ---------- 数据 ----------

    def add_paths(self, paths: list[Path]) -> None:
        """在后台线程扫描并加入清单。扫描期间界面不会卡住。"""
        if self._scanner is not None and self._scanner.isRunning():
            return
        self._set_scanning(True)
        self._scanner = ScanWorker(paths, self._suffixes)
        self._scanner.progress.connect(
            lambda n: self.lbl_scanning.setText(f"正在扫描…已找到 {n} 个文件")
        )
        self._scanner.finished_files.connect(self._on_scan_done)
        self._scanner.failed.connect(self._on_scan_failed)
        self._scanner.start()

    def add_paths_sync(self, paths: list[Path]) -> int:
        """同步版本，给测试和脚本用，避免为了几个文件去等线程。"""
        from ...core.scan import collect_files

        before = len(self._files)
        self._merge(collect_files(paths, recursive=True, suffixes=self._suffixes))
        return len(self._files) - before

    def _merge(self, found: list[Path]) -> None:
        known = {f.resolve() for f in self._files}
        for f in found:
            r = f.resolve()
            if r not in known:
                known.add(r)
                self._files.append(f)
        self._refresh()

    def _set_scanning(self, scanning: bool) -> None:
        self.scan_bar.setVisible(scanning)
        self.btn_cancel_scan.setEnabled(scanning)
        self.lbl_scanning.setText("正在扫描…")
        for b in (self.btn_add_files, self.btn_add_folder, self.btn_remove, self.btn_clear):
            b.setEnabled(not scanning)
        self.scanning_changed.emit(scanning)

    def _cancel_scan(self) -> None:
        if self._scanner is not None:
            self._scanner.cancel()
            self.lbl_scanning.setText("正在停止扫描…")
            self.btn_cancel_scan.setEnabled(False)

    def _on_scan_done(self, found: list) -> None:
        self._set_scanning(False)
        self._merge([Path(f) for f in found])

    def _on_scan_failed(self, human: str, detail: str) -> None:
        self._set_scanning(False)
        self.scan_failed.emit(human, detail)

    def is_scanning(self) -> bool:
        return self._scanner is not None and self._scanner.isRunning()

    def stop_scan(self) -> None:
        if self._scanner is not None and self._scanner.isRunning():
            self._scanner.cancel()
            self._scanner.wait(3000)

    def files(self) -> list[Path]:
        return list(self._files)

    def clear(self) -> None:
        self._files.clear()
        self._refresh()

    def _pick_files(self) -> None:
        names, _ = QFileDialog.getOpenFileNames(self, "选择文件")
        if names:
            self.add_paths([Path(n) for n in names])

    def _pick_folder(self) -> None:
        name = QFileDialog.getExistingDirectory(self, "选择文件夹")
        if name:
            self.add_paths([Path(name)])

    def _remove_selected(self) -> None:
        rows = sorted({i.row() for i in self.table.selectedIndexes()}, reverse=True)
        for r in rows:
            if 0 <= r < len(self._files):
                del self._files[r]
        self._refresh()

    def _refresh(self) -> None:
        self.table.setRowCount(len(self._files))
        for row, f in enumerate(self._files):
            try:
                size = human_size(f.stat().st_size)
            except OSError:
                size = "读取失败"
            self.table.setItem(row, 0, QTableWidgetItem(f.name))
            item_size = QTableWidgetItem(size)
            item_size.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.table.setItem(row, 1, item_size)
            self.table.setItem(row, 2, QTableWidgetItem(str(f.parent)))

        self.stack.setCurrentIndex(1 if self._files else 0)
        self.lbl_count.setText(f"共 {len(self._files)} 个文件")
        if not self.is_scanning():
            self.btn_remove.setEnabled(bool(self._files))
            self.btn_clear.setEnabled(bool(self._files))
        self.changed.emit()

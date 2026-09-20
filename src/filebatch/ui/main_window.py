"""主窗口：左边功能列表，右边对应的页面。"""
from __future__ import annotations

from PySide6.QtCore import QDeadlineTimer, QElapsedTimer, Qt
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QProgressDialog,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .messages import TEXT
from .pages.classify_page import ClassifyPage
from .pages.image_page import ImagePage
from .pages.pdf_page import PdfPage
from .pages.rename_page import RenamePage
from .pages.table_page import TablePage
from .pages.text_page import TextPage

# (显示名, 页面类)
FEATURES = [
    ("批量重命名 / 编号", RenamePage),
    ("文件分类整理", ClassifyPage),
    ("图片批处理", ImagePage),
    ("Excel / CSV 合并", TablePage),
    ("PDF 拆分 / 合并", PdfPage),
    ("文本查找替换", TextPage),
]


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(TEXT["app_title"])
        self.resize(1160, 780)
        self.setMinimumSize(960, 640)
        # 页面按需创建：一次性建六个页面会把冷启动从 0.7 秒拖到 1.4 秒，
        # 而用户打开后通常只用其中一个。
        self._page_classes = [cls for _, cls in FEATURES]
        self.pages: list[QWidget | None] = [None] * len(FEATURES)
        self._build()

    def _build(self) -> None:
        central = QWidget()
        lay = QHBoxLayout(central)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        side = QWidget()
        side.setObjectName("SideBar")
        side.setFixedWidth(210)
        sv = QVBoxLayout(side)
        sv.setContentsMargins(0, 0, 0, 0)
        sv.setSpacing(0)

        title = QLabel(TEXT["app_title"])
        title.setObjectName("SideBarTitle")
        sv.addWidget(title)

        self.nav = QListWidget()
        self.nav.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.nav.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.nav.setWordWrap(False)

        self.stack = QStackedWidget()
        for name, _ in FEATURES:
            self.nav.addItem(QListWidgetItem(name))
            # 先放一个占位空页，真正的页面等用户点进来再建
            self.stack.addWidget(QWidget())

        self.nav.setCurrentRow(0)
        self._ensure_page(0)
        self.stack.setCurrentIndex(0)
        sv.addWidget(self.nav, 1)

        version = QLabel("V1 · 全部功能已就绪")
        version.setObjectName("Hint")
        version.setContentsMargins(16, 8, 16, 14)
        sv.addWidget(version)

        lay.addWidget(side)
        lay.addWidget(self.stack, 1)
        self.setCentralWidget(central)
        self.nav.currentRowChanged.connect(self._on_nav)

    def _ensure_page(self, index: int) -> QWidget:
        """第一次切到某个功能时才真正把页面建出来。"""
        existing = self.pages[index]
        if existing is not None:
            return existing
        page = self._page_classes[index]()
        self.pages[index] = page
        placeholder = self.stack.widget(index)
        self.stack.insertWidget(index, page)
        self.stack.removeWidget(placeholder)
        placeholder.deleteLater()
        # insertWidget 会把占位页往后挤，当前索引跟着它跑偏，
        # 不显式设回来的话用户会看到一片空白。
        if self.nav.currentRow() == index:
            self.stack.setCurrentIndex(index)
        return page

    def page_at(self, index: int) -> QWidget:
        return self._ensure_page(index)

    def _on_nav(self, row: int) -> None:
        if row < 0:
            return
        self._ensure_page(row)
        self.stack.setCurrentIndex(row)

    # 兼容早期代码和测试里直接拿重命名页的写法
    @property
    def rename_page(self) -> RenamePage:
        return self._ensure_page(0)  # type: ignore[return-value]

    # ---------------- 安全退出 ----------------

    def _busy_pages(self) -> list:
        return [p for p in self.pages if p is not None and getattr(p, "is_busy", lambda: False)()]

    def closeEvent(self, event) -> None:  # noqa: N802, ANN001
        """关窗时如果还有任务在跑，必须先问用户，并等当前文件写完再退出。

        直接退出是危险的：worker 在两个文件之间才检查取消标志，
        进程如果这时候没了，正在写的那个文件会变成残缺的半截文件。
        """
        忙碌 = self._busy_pages()
        if 忙碌:
            box = QMessageBox(self)
            box.setIcon(QMessageBox.Icon.Warning)
            box.setWindowTitle("任务正在执行")
            box.setText("当前任务仍在执行，是否停止任务并退出？")
            box.setInformativeText(
                "已经处理完的文件会保留，不会被撤销。\n"
                "正在处理的这一个文件会先写完，再安全退出。"
            )
            停止 = box.addButton("停止任务并退出", QMessageBox.ButtonRole.DestructiveRole)
            继续 = box.addButton("继续执行", QMessageBox.ButtonRole.RejectRole)
            # 默认是"继续执行"：回车和 Esc 都不应该把用户的任务弄没
            box.setDefaultButton(继续)
            box.setEscapeButton(继续)
            box.exec()

            if box.clickedButton() is not 停止:
                event.ignore()
                return

            if not self._wait_for_safe_stop(忙碌):
                # 等太久了，让用户自己决定要不要硬退
                再问 = QMessageBox(self)
                再问.setIcon(QMessageBox.Icon.Critical)
                再问.setWindowTitle("任务还没停下来")
                再问.setText("当前文件处理时间较长，还没能安全停止。")
                再问.setInformativeText(
                    "现在强制退出，正在写入的那个文件可能会不完整。\n建议再等一会儿。"
                )
                强退 = 再问.addButton("仍然强制退出", QMessageBox.ButtonRole.DestructiveRole)
                等待 = 再问.addButton("继续等待", QMessageBox.ButtonRole.RejectRole)
                再问.setDefaultButton(等待)
                再问.setEscapeButton(等待)
                再问.exec()
                if 再问.clickedButton() is not 强退:
                    event.ignore()
                    return

        for page in self.pages:
            if page is None:
                continue
            stop = getattr(page, "stop_background_work", None)
            if stop is not None:
                stop()
        event.accept()

    def _wait_for_safe_stop(self, 忙碌: list, 超时毫秒: int = 15000) -> bool:
        """请求停止并等它们收尾，期间给用户一个"正在安全停止"的提示。

        :return: True 表示都停下来了
        """
        for page in 忙碌:
            page.request_stop()

        dlg = QProgressDialog("正在安全停止，等当前文件处理完…", "", 0, 0, self)
        dlg.setWindowTitle("正在退出")
        dlg.setCancelButton(None)          # 这一步不能取消，取消就等于强退
        dlg.setWindowModality(Qt.WindowModality.WindowModal)
        dlg.setMinimumDuration(0)
        dlg.show()

        timer = QElapsedTimer()
        timer.start()
        try:
            while timer.elapsed() < 超时毫秒:
                if not self._busy_pages():
                    return True
                QApplication.processEvents()
                for page in self._busy_pages():
                    worker = getattr(page, "_worker", None)
                    if worker is not None:
                        worker.wait(QDeadlineTimer(50))
            return not self._busy_pages()
        finally:
            dlg.close()

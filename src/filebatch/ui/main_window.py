"""主窗口：左边功能列表，右边对应的页面。"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
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

    def closeEvent(self, event) -> None:  # noqa: N802, ANN001
        """关窗前把所有页面的后台线程都收干净。"""
        for page in self.pages:
            if page is None:
                continue
            stop = getattr(page, "stop_background_work", None)
            if stop is not None:
                stop()
        event.accept()

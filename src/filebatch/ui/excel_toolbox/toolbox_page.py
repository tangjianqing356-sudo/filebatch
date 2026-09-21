"""Excel 工具箱：左边导航里的一个入口，里面是六个独立功能。

它本身不做任何业务，只是个容器：每个标签页都是一个完整的 BaseJobPage，
各自有自己的文件清单、预览、执行线程和日志，互不干扰。

子页面按需创建。六个页面一次性建出来会把切到工具箱的那一下拖慢将近一倍，
而用户通常只用其中一个。
"""
from __future__ import annotations

from typing import Callable

from PySide6.QtWidgets import QLabel, QTabWidget, QVBoxLayout, QWidget

from ..pages.base_page import BaseJobPage
from ..pages.table_page import TablePage
from .clean_page import CleanPage
from .compare_page import ComparePage
from .dedupe_page import DedupePage
from .format_page import FormatPage
from .split_page import SplitPage

# (标签名, 页面类)
SUB_FEATURES: list[tuple[str, type[BaseJobPage]]] = [
    ("合并", TablePage),
    ("去重", DedupePage),
    ("两表对比", ComparePage),
    ("数据清洗", CleanPage),
    ("批量拆表", SplitPage),
    ("格式统一", FormatPage),
]


class _LazySlot(QWidget):
    """标签页的占位容器，第一次显示时才把真正的页面塞进来。

    做成"容器里换内容"而不是"换标签页"，是因为后者会让标签索引跟着变，
    主窗口那边已经因为同类写法出过一次空白页的问题。
    """

    def __init__(self, factory: Callable[[], BaseJobPage], parent=None) -> None:  # noqa: ANN001
        super().__init__(parent)
        self._factory = factory
        self._page: BaseJobPage | None = None
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)

    def page(self) -> BaseJobPage:
        if self._page is None:
            self._page = self._factory()
            self._layout.addWidget(self._page)
        return self._page

    @property
    def created(self) -> BaseJobPage | None:
        return self._page


class ExcelToolboxPage(QWidget):
    TITLE = "Excel 工具箱"
    SUBTITLE = "表格相关的功能都在这里。每个标签页都是独立的一套：参数 → 预览 → 执行 → 日志。"

    def __init__(self, parent=None) -> None:  # noqa: ANN001
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 14, 18, 8)
        root.setSpacing(6)

        title = QLabel(self.TITLE)
        title.setObjectName("SectionTitle")
        root.addWidget(title)
        subtitle = QLabel(self.SUBTITLE)
        subtitle.setObjectName("Hint")
        subtitle.setWordWrap(True)
        root.addWidget(subtitle)

        self.tabs = QTabWidget()
        self._slots: list[_LazySlot] = []
        for name, cls in SUB_FEATURES:
            slot = _LazySlot(cls)
            self._slots.append(slot)
            self.tabs.addTab(slot, name)
        root.addWidget(self.tabs, 1)

        self.tabs.currentChanged.connect(self._on_tab)
        self.sub_page(0)

    # ---------------- 子页面 ----------------

    def _on_tab(self, index: int) -> None:
        if index >= 0:
            self.sub_page(index)

    def sub_page(self, index: int) -> BaseJobPage:
        """拿到第 index 个子页面，需要的话现建。"""
        return self._slots[index].page()

    def created_pages(self) -> list[BaseJobPage]:
        """已经建出来的子页面。没建出来的不可能在跑任务。"""
        return [s.created for s in self._slots if s.created is not None]

    # ---------------- 主窗口要的那套收尾接口 ----------------
    # 主窗口按"页面"统一处理关窗逻辑，工具箱必须把这些转发给子页面，
    # 否则子页面里正在跑的任务会被当成不存在，进程直接退出。

    def is_busy(self) -> bool:
        return any(p.is_busy() for p in self.created_pages())

    def active_workers(self) -> list:
        workers: list = []
        for p in self.created_pages():
            workers.extend(p.active_workers())
        return workers

    def request_stop(self) -> None:
        for p in self.created_pages():
            p.request_stop()

    def stop_background_work(self) -> None:
        for p in self.created_pages():
            p.stop_background_work()

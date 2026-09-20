"""主窗口：导航、懒加载、线程收尾。"""
import pytest


@pytest.fixture
def win(qapp):
    from filebatch.ui.main_window import MainWindow

    w = MainWindow()
    yield w
    w.close()
    w.deleteLater()


def test_打开就能看到首页而不是空白(win):
    """回归测试：改成懒加载后 insertWidget 会让当前索引跑偏，用户会看到一片空白。"""
    assert win.stack.currentIndex() == 0
    assert win.stack.currentWidget() is win.pages[0]
    assert win.pages[0] is not None


def test_页面按需创建(win):
    from filebatch.ui.main_window import FEATURES

    assert win.pages[0] is not None, "首页要立刻可用"
    assert all(p is None for p in win.pages[1:]), "其余页面开机时不该创建"
    assert len(win.pages) == len(FEATURES)


def test_切换导航会创建并显示对应页面(win):
    for row in range(1, len(win.pages)):
        win.nav.setCurrentRow(row)
        assert win.pages[row] is not None, f"第 {row} 个页面应被创建"
        assert win.stack.currentWidget() is win.pages[row], f"第 {row} 个页面应被显示"


def test_每个页面标题都能对上导航项(win):
    from filebatch.ui.main_window import FEATURES

    for row, (name, cls) in enumerate(FEATURES):
        page = win.page_at(row)
        assert isinstance(page, cls)
        assert win.nav.item(row).text() == name


def test_关窗会收掉所有页面的后台线程(win, qapp):
    win.page_at(2)
    win.page_at(4)
    win.close()          # 不应抛异常，也不该留下跑着的线程
    for page in win.pages:
        if page is None:
            continue
        worker = getattr(page, "_worker", None)
        assert worker is None or not worker.isRunning()

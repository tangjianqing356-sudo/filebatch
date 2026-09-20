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


# ---------------- 执行中关窗口的安全退出 ----------------

@pytest.fixture
def 慢任务窗口(qapp, monkeypatch, tmp_path):
    """造一个正在执行任务的窗口，任务故意跑得慢，方便测关窗口。"""
    from filebatch.ui.main_window import MainWindow
    from filebatch.ui.pages import base_page as bp

    monkeypatch.setattr(bp, "show_info", lambda *a, **k: None)
    monkeypatch.setattr(bp, "show_error", lambda *a, **k: None)

    win = MainWindow()
    page = win.page_at(0)

    src = tmp_path / "源"
    src.mkdir()
    files = []
    for i in range(30):
        f = src / f"f{i:03d}.txt"
        f.write_text("x", encoding="utf-8")
        files.append(f)

    page.file_list.add_paths_sync(files)
    page._output_path = tmp_path / "输出"
    page.ed_prefix.setText("新_")
    page.generate_preview()

    # 让每个文件慢一点，这样窗口关的时候任务确实还在跑
    from filebatch.core import rename_job

    原execute = rename_job.execute

    def 慢execute(actions, in_place=False, on_progress=None, should_cancel=None):
        import time

        def 慢进度(done, total, name):
            time.sleep(0.03)
            if on_progress:
                on_progress(done, total, name)

        return 原execute(actions, in_place, on_progress=慢进度, should_cancel=should_cancel)

    monkeypatch.setattr(rename_job, "execute", 慢execute)
    page.start_execute()
    yield win, page, files
    page.stop_background_work()
    win.deleteLater()


def test_执行中关窗口会先问用户(慢任务窗口, qapp, monkeypatch):
    from PySide6.QtGui import QCloseEvent
    from filebatch.ui import main_window as mw

    win, page, _ = 慢任务窗口
    assert page.is_busy(), "任务应该正在跑"

    问过 = {"n": 0}
    原MessageBox = mw.QMessageBox

    class 假MessageBox(原MessageBox):
        def exec(self):
            问过["n"] += 1
            return 0

        def clickedButton(self):
            return self._继续          # 模拟用户点了"继续执行"

        def addButton(self, text, role):
            btn = 原MessageBox.addButton(self, text, role)
            if "继续" in text:
                self._继续 = btn
            return btn

    monkeypatch.setattr(mw, "QMessageBox", 假MessageBox)

    event = QCloseEvent()
    win.closeEvent(event)

    assert 问过["n"] == 1, "必须弹确认框，不能静默退出"
    assert not event.isAccepted(), "用户选了继续执行，窗口不该关"
    assert page.is_busy(), "任务必须还在跑"


def test_确认停止后会等当前文件写完再退出(慢任务窗口, qapp, monkeypatch):
    from PySide6.QtGui import QCloseEvent
    from filebatch.ui import main_window as mw

    win, page, files = 慢任务窗口

    原MessageBox = mw.QMessageBox

    class 假MessageBox(原MessageBox):
        def exec(self):
            return 0

        def clickedButton(self):
            return self._停止

        def addButton(self, text, role):
            btn = 原MessageBox.addButton(self, text, role)
            if "停止" in text:
                self._停止 = btn
            return btn

    monkeypatch.setattr(mw, "QMessageBox", 假MessageBox)

    event = QCloseEvent()
    win.closeEvent(event)

    assert event.isAccepted(), "确认停止后应该允许关闭"
    assert not page.is_busy(), "退出前必须等线程真的停下来"

    # 已完成的文件保留且完整，原文件一个不少
    out = page._output_path
    if out.exists():
        for p in out.iterdir():
            assert p.stat().st_size > 0, f"{p.name} 是残缺文件"
    for f in files:
        assert f.exists(), "中断不能破坏原文件"


def test_没有任务时关窗口不打扰用户(win, qapp, monkeypatch):
    from PySide6.QtGui import QCloseEvent
    from filebatch.ui import main_window as mw

    弹过 = {"n": 0}
    原MessageBox = mw.QMessageBox

    class 假MessageBox(原MessageBox):
        def exec(self):
            弹过["n"] += 1
            return 0

    monkeypatch.setattr(mw, "QMessageBox", 假MessageBox)

    event = QCloseEvent()
    win.closeEvent(event)
    assert event.isAccepted()
    assert 弹过["n"] == 0, "空闲时关窗口不该弹任何东西"

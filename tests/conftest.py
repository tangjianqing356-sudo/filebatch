"""测试的全局配置。

GUI 测试必须在无头模式下跑，否则 CI 上没有显示器会直接崩。
这句必须在任何 Qt 模块被 import 之前执行，所以放在 conftest 最顶上。
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402


@pytest.fixture(scope="session")
def qapp():
    from filebatch.ui.app import create_app

    app = create_app([])
    yield app


@pytest.fixture
def 样例文件(tmp_path):
    """三个待处理文件，放在独立的源目录里。"""
    src = tmp_path / "源目录"
    src.mkdir()
    files = []
    for name in ["IMG_001.jpg", "IMG_002.jpg", "IMG_003.jpg"]:
        f = src / name
        f.write_bytes(b"fake")
        files.append(f)
    return files


def 等待线程结束(app, worker, timeout_ms: int = 10000) -> None:
    """自旋事件循环直到后台线程跑完，让信号能正常投递到主线程。"""
    from PySide6.QtCore import QDeadlineTimer, QElapsedTimer

    timer = QElapsedTimer()
    timer.start()
    while worker.isRunning() and timer.elapsed() < timeout_ms:
        app.processEvents()
        worker.wait(QDeadlineTimer(20))
    app.processEvents()
    app.processEvents()

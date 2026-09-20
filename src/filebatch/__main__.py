"""python -m filebatch 启动界面。

带 --selftest 参数时改为跑打包产物自检，用来验证打出来的可执行文件是否完整。
"""
import os
import sys
import time

_T0 = time.perf_counter()


def _measure_startup() -> int:
    """测冷启动：从进程起来到主窗口可见。打包后跑这个才算数。"""
    import resource

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from filebatch.ui.app import create_app
    from filebatch.ui.main_window import MainWindow

    app = create_app([])
    win = MainWindow()
    win.show()
    for _ in range(5):
        app.processEvents()
    用时 = (time.perf_counter() - _T0) * 1000

    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    内存 = rss / (1024 * 1024) if sys.platform == "darwin" else rss / 1024
    print(f"冷启动 {用时:.0f} ms | 空闲内存 {内存:.1f} MB")

    for i in range(len(win.pages)):
        win.page_at(i)
        app.processEvents()
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    内存全 = rss / (1024 * 1024) if sys.platform == "darwin" else rss / 1024
    print(f"六页全开后内存 {内存全:.1f} MB")
    return 0


def _screenshot(path: str) -> int:
    """用**真实**平台插件（macOS 上是 cocoa）渲染窗口并自截图。

    offscreen 只能证明布局逻辑没问题；只有真实插件跑起来才能验证
    字体回退、DPI 缩放、原生控件这些打包后最容易出问题的地方。
    自己 grab 自己不需要系统的屏幕录制权限。
    """
    from filebatch.ui.app import create_app
    from filebatch.ui.main_window import MainWindow

    app = create_app([])
    win = MainWindow()
    win.show()
    for _ in range(20):
        app.processEvents()
        time.sleep(0.02)
    ok = win.grab().save(path)
    print(f"平台插件={app.platformName()} 截图={'成功' if ok else '失败'} -> {path}")
    return 0 if ok else 1


def main() -> int:
    if "--screenshot" in sys.argv:
        i = sys.argv.index("--screenshot")
        return _screenshot(sys.argv[i + 1])
    if "--measure-startup" in sys.argv:
        return _measure_startup()
    if "--acceptance" in sys.argv:
        from filebatch.acceptance import run

        return run("--open-output" in sys.argv)
    if "--selftest" in sys.argv:
        # 自检必须无头运行，打包后的程序在 CI 或终端里也能跑
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from filebatch.selftest import run

        return run()

    from filebatch.ui.app import main as gui_main

    return gui_main()


if __name__ == "__main__":
    sys.exit(main())

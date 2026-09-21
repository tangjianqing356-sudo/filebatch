"""python -m filebatch 启动界面。

带 --selftest 参数时改为跑打包产物自检，用来验证打出来的可执行文件是否完整。
"""
import os
import sys
import time

_T0 = time.perf_counter()


def _measure_startup() -> int:
    """测冷启动：从进程起来到主窗口可见。打包后跑这个才算数。"""
    from filebatch.sysinfo import peak_memory_mb

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from filebatch.ui.app import create_app
    from filebatch.ui.main_window import MainWindow

    app = create_app([])
    win = MainWindow()
    win.show()
    for _ in range(5):
        app.processEvents()
    用时 = (time.perf_counter() - _T0) * 1000

    print(f"冷启动 {用时:.0f} ms | 空闲内存 {peak_memory_mb():.1f} MB")

    子页数 = 0
    for i in range(len(win.pages)):
        page = win.page_at(i)
        # Excel 工具箱的子页面也是懒加载的，要报最坏情况就得全建出来
        建子页 = getattr(page, "sub_page", None)
        if 建子页 is not None:
            for j in range(page.tabs.count()):
                建子页(j)
                子页数 += 1
        app.processEvents()
    print(f"{len(win.pages)} 个功能页 + {子页数} 个 Excel 子页全开后内存 "
          f"{peak_memory_mb():.1f} MB")
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


def _env_report() -> int:
    """打印运行环境信息，CI 里用来回答"这台机器到底什么情况"。

    最有价值的是长路径探测结果：它直接告诉我们这台 Windows 有没有开
    LongPathsEnabled，以及程序看到的实际上限是多少。
    """
    import platform

    from filebatch.core.pathlimits import probe_path_limit, reset_cache
    from filebatch.sysinfo import peak_memory_mb

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    print("=" * 56)
    print("运行环境")
    print("=" * 56)
    print(f"系统        {platform.platform()}")
    print(f"架构        {platform.machine()}")
    print(f"Python      {platform.python_version()}")
    print(f"打包运行    {getattr(sys, 'frozen', False)}")
    print(f"标准输出编码 {getattr(sys.stdout, 'encoding', '未知')}")

    try:
        import PySide6
        from PySide6.QtWidgets import QApplication

        app = QApplication.instance() or QApplication([])
        print(f"PySide6     {PySide6.__version__}，platform 插件 = {app.platformName()}")
    except Exception as e:
        print(f"PySide6     读取失败：{e}")

    print()
    print("长路径探测（实测，不是写死 260）")
    reset_cache()
    limit = probe_path_limit()
    print(f"  结论      {limit.describe()}")
    print(f"  max_path  {limit.max_path}（0 表示没测出总路径上限）")
    print(f"  max_name  {limit.max_name}")
    if limit.probe_error:
        print(f"  探测报错  {limit.probe_error}")
    if sys.platform == "win32":
        状态 = "已开启" if not limit.has_limit else "未开启"
        print(f"  推断 Windows 长路径支持：{状态}")

    print()
    print(f"峰值内存    {peak_memory_mb():.1f} MB")
    return 0


def main() -> int:
    # 必须在任何 print 之前：Windows 控制台默认 GBK/cp1252，打中文会直接崩
    from filebatch.console import ensure_utf8_output

    ensure_utf8_output()

    if "--screenshot" in sys.argv:
        i = sys.argv.index("--screenshot")
        return _screenshot(sys.argv[i + 1])
    if "--measure-startup" in sys.argv:
        return _measure_startup()
    if "--env-report" in sys.argv:
        return _env_report()
    if "--acceptance" in sys.argv:
        # 和 --selftest / --platform-check 一样强制无头。
        # Windows CI 上实测：不设这个的话，打包成窗口程序（console=False）的 exe
        # 用真实 windows 平台插件跑起来，所有 print 都消失了，
        # 退出码还是 0——于是 CI 那一步"通过"了却什么都没验证。
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from filebatch.acceptance import run

        return run("--open-output" in sys.argv)
    if "--platform-check" in sys.argv:
        # 平台边界验收：中文/空格/长路径、文件占用、权限、盘符、.xlsm 往返
        from filebatch.platformcheck import run

        文件 = sys.argv[sys.argv.index("--xlsm") + 1] if "--xlsm" in sys.argv else None
        return run(文件)
    if "--selftest" in sys.argv:
        # 自检必须无头运行，打包后的程序在 CI 或终端里也能跑
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from filebatch.selftest import run

        return run()

    from filebatch.ui.app import main as gui_main

    return gui_main()


if __name__ == "__main__":
    sys.exit(main())

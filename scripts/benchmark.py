"""冷启动速度和内存占用测量。

内存用标准库 resource.getrusage 取峰值 RSS，不额外引入 psutil。
注意：ru_maxrss 在 macOS 上单位是字节，在 Linux 上是 KB，这里按平台归一。
"""
from __future__ import annotations

import os
import resource
import sys
import tempfile
import time
from pathlib import Path

T0 = time.perf_counter()

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))


def 峰值内存_MB() -> float:
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return rss / (1024 * 1024) if sys.platform == "darwin" else rss / 1024


def main() -> int:
    t_import0 = time.perf_counter()
    from PySide6.QtCore import QDeadlineTimer  # noqa: F401

    from filebatch.ui.app import create_app
    from filebatch.ui.main_window import MainWindow
    from filebatch.ui.pages import base_page as dialogs
    t_import = time.perf_counter() - t_import0

    # 弹窗统一在基类里；不换掉的话 QMessageBox.exec() 会把无人值守脚本卡死
    dialogs.show_info = lambda *a, **k: None
    dialogs.show_error = lambda *a, **k: None

    t_app0 = time.perf_counter()
    app = create_app([])
    win = MainWindow()
    win.show()
    for _ in range(5):
        app.processEvents()
    t_app = time.perf_counter() - t_app0

    总启动 = time.perf_counter() - T0
    空闲内存 = 峰值内存_MB()

    print("【冷启动】")
    print(f"  导入依赖(PySide6 等)     {t_import * 1000:7.0f} ms")
    print(f"  创建并显示窗口           {t_app * 1000:7.0f} ms")
    print(f"  从进程启动到界面可见     {总启动 * 1000:7.0f} ms")
    print()
    print("【内存】")
    print(f"  空闲状态峰值 RSS         {空闲内存:7.1f} MB")
    建好的 = sum(1 for p in win.pages if p is not None)
    print(f"  （页面按需创建，当前只建了 {建好的}/{len(win.pages)} 个）")

    # 大量文件
    page = win.rename_page
    tmp = Path(tempfile.mkdtemp(prefix="filebatch_bench_"))
    src = tmp / "源"
    src.mkdir()

    for count in (1000, 5000):
        需要 = count - len(list(src.iterdir()))
        for i in range(len(list(src.iterdir())), count):
            (src / f"file_{i:06d}.txt").write_bytes(b"x" * 256)

        page.file_list.clear()
        # 用同步版测纯扫描耗时；界面里这一步现在跑在后台线程，不会卡住主界面
        t0 = time.perf_counter()
        page.file_list.add_paths_sync([src])
        for _ in range(3):
            app.processEvents()
        t_load = time.perf_counter() - t0
        内存_加载 = 峰值内存_MB()

        page._output_dir = tmp / f"输出_{count}"
        page.ed_base.setText("文件")
        page.cb_number.setCurrentIndex(1)
        page.sp_digits.setValue(6)

        t0 = time.perf_counter()
        ok = page.generate_preview()
        for _ in range(3):
            app.processEvents()
        t_preview = time.perf_counter() - t0
        内存_预览 = 峰值内存_MB()

        print()
        print(f"  ── {count} 个文件 ──")
        print(f"  扫描并列出               {t_load:7.2f} s     峰值 {内存_加载:6.1f} MB")
        print(f"  生成预览(含表格渲染)     {t_preview:7.2f} s     峰值 {内存_预览:6.1f} MB   预览成功={ok}")

        if count == 5000:
            t0 = time.perf_counter()
            page.start_execute()
            worker = page._worker
            from PySide6.QtCore import QDeadlineTimer as DL
            while worker is not None and worker.isRunning():
                app.processEvents()
                worker.wait(DL(20))
            for _ in range(5):
                app.processEvents()
            t_exec = time.perf_counter() - t0
            内存_执行 = 峰值内存_MB()
            r = page._last_report
            print(f"  实际执行(复制+改名)      {t_exec:7.2f} s     峰值 {内存_执行:6.1f} MB")
            print(f"  结果：成功 {r.succeeded}，失败 {r.failed}，跳过 {len(r.skipped)}")

    print()
    print(f"（临时目录用完可删：{tmp}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())

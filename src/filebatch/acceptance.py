"""打包产物的完整验收：6 个功能各走一遍真实流程。

走的是**真实界面对象**，不是直接调 core：
添加文件 → 设参数 → 生成预览 → 开始执行 → 等后台线程 → 核对磁盘产物 → 日志。

之所以要在打包后再跑一遍，是因为"开发环境能跑"和"打出来能跑"是两回事：
少一个 Pillow 插件、少一个 Qt plugin，只有在冻结后的环境里才暴露。

用法：FileBatchTool --acceptance [--open-output]
"""
from __future__ import annotations

import csv
import sys
import tempfile
import time
import traceback
from pathlib import Path

结果: list[tuple[str, bool, str]] = []


def _静音弹窗() -> None:
    from filebatch.ui.pages import base_page as bp

    bp.show_info = lambda *a, **k: None
    bp.show_error = lambda *a, **k: None
    bp.confirm_dangerous = lambda *a, **k: True


def _等执行完(app, page, 超时秒: float = 60) -> None:
    from PySide6.QtCore import QDeadlineTimer

    worker = page._worker
    t0 = time.time()
    while worker is not None and worker.isRunning() and time.time() - t0 < 超时秒:
        app.processEvents()
        worker.wait(QDeadlineTimer(20))
    for _ in range(10):
        app.processEvents()


def _跑一个功能(app, win, 序号: int, 名称: str, 准备, 设参数, 校验, open_output: bool) -> None:
    try:
        page = win.page_at(序号)
        win.nav.setCurrentRow(序号)
        for _ in range(3):
            app.processEvents()

        tmp = Path(tempfile.mkdtemp(prefix="fb_acc_"))
        源, 期望数 = 准备(tmp)

        page.file_list.add_paths_sync([源])
        assert page.file_list.files(), "文件清单是空的"
        assert not page.btn_execute.isEnabled(), "预览之前不该能执行"

        设参数(page, tmp)

        assert page.generate_preview() is True, "生成预览失败"
        assert page.btn_execute.isEnabled(), "预览通过后执行按钮应该可用"

        assert page.start_execute() is True, "启动执行失败"
        _等执行完(app, page)

        report = page._last_report
        assert report is not None, "没拿到执行结果"
        assert report.failed == 0, f"有 {report.failed} 项失败：{report.summary()}"
        assert report.succeeded == 期望数, f"期望成功 {期望数}，实际 {report.succeeded}"

        校验(tmp)

        assert page.log.toPlainText().strip(), "日志是空的"
        assert page.btn_save_log.isEnabled(), "保存日志按钮应该可用"
        assert page.btn_open_output.isEnabled(), "打开输出目录按钮应该可用"
        assert "本次执行结果" in page.box_preview.title(), "执行后应切到结果态"

        打开 = ""
        if open_output:
            from PySide6.QtCore import QUrl
            from PySide6.QtGui import QDesktopServices

            目标 = page._output_path
            if 目标 and 目标.is_file():
                目标 = 目标.parent
            ok = QDesktopServices.openUrl(QUrl.fromLocalFile(str(目标)))
            打开 = f"，已打开输出目录={ok}"

        结果.append((名称, True, f"{report.succeeded} 项成功，日志 {len(page.log.toPlainText())} 字{打开}"))
    except Exception as e:
        结果.append((名称, False, f"{type(e).__name__}: {e}"))


# ---------------- 各功能的样例数据与校验 ----------------

def _备重命名(tmp: Path):
    d = tmp / "照片"
    d.mkdir()
    for i in range(6):
        (d / f"IMG_{i:04d}.jpg").write_bytes(b"x" * 1024)
    return d, 6


def _设重命名(page, tmp):
    page._output_path = tmp / "输出"
    page.ed_base.setText("旅行照片")
    page.cb_number.setCurrentIndex(1)
    page.sp_digits.setValue(3)


def _校验重命名(tmp):
    out = tmp / "输出"
    names = sorted(p.name for p in out.iterdir())
    assert names[0] == "旅行照片_001.jpg", names[:3]
    assert len(names) == 6
    assert (tmp / "照片" / "IMG_0000.jpg").exists(), "原文件必须保留"


def _备分类(tmp: Path):
    d = tmp / "杂乱"
    d.mkdir()
    for n in ["图.jpg", "表.xlsx", "文.txt", "包.zip", "片.mp4"]:
        (d / n).write_bytes(b"x" * 512)
    return d, 5


def _设分类(page, tmp):
    page._output_path = tmp / "整理后"


def _校验分类(tmp):
    out = tmp / "整理后"
    for folder, name in [("图片", "图.jpg"), ("表格", "表.xlsx"), ("文档", "文.txt"),
                         ("压缩包", "包.zip"), ("视频", "片.mp4")]:
        assert (out / folder / name).exists(), f"{folder}/{name} 不存在"
    assert (tmp / "杂乱" / "图.jpg").exists(), "默认复制，原文件必须保留"


def _备图片(tmp: Path):
    from PIL import Image

    d = tmp / "原图"
    d.mkdir()
    for i in range(4):
        Image.new("RGB", (1600, 1200), (90, 140, 200)).save(d / f"DSC_{i}.jpg")
    return d, 4


def _设图片(page, tmp):
    from filebatch.core.image_job import ResizeMode

    page._output_path = tmp / "输出"
    page.ed_base.setText("产品图")
    page.cb_number.setCurrentIndex(1)
    page.cb_resize.setCurrentIndex(page.cb_resize.findData(ResizeMode.MAX_SIDE))
    page.sp_value.setValue(800)


def _校验图片(tmp):
    from PIL import Image

    out = tmp / "输出"
    assert len(list(out.iterdir())) == 4
    with Image.open(out / "产品图_001.jpg") as im:
        assert im.size == (800, 600), f"缩放结果不对：{im.size}"


def _备表格(tmp: Path):
    d = tmp / "报表"
    d.mkdir()
    for i, m in enumerate(["一月", "二月", "三月"], start=1):
        with open(d / f"{m}.csv", "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(["姓名", "金额"] if i % 2 else ["金额", "姓名"])
            w.writerow([f"张{i}", str(i * 100)] if i % 2 else [str(i * 100), f"张{i}"])
    return d, 3


def _设表格(page, tmp):
    page._output_path = tmp / "合并结果.xlsx"


def _校验表格(tmp):
    from openpyxl import load_workbook

    ws = load_workbook(tmp / "合并结果.xlsx").active
    assert [c.value for c in ws[1]] == ["姓名", "金额", "来源文件"], [c.value for c in ws[1]]
    assert ws.max_row == 4, f"应有 1 行表头 + 3 行数据，实际 {ws.max_row}"


def _备PDF(tmp: Path):
    from pypdf import PdfWriter

    d = tmp / "合同"
    d.mkdir()
    w = PdfWriter()
    for _ in range(4):
        w.add_blank_page(width=595, height=842)
    with open(d / "采购合同.pdf", "wb") as f:
        w.write(f)
    return d, 4


def _设PDF(page, tmp):
    page._output_path = tmp / "输出"


def _校验PDF(tmp):
    from pypdf import PdfReader

    out = tmp / "输出"
    names = sorted(p.name for p in out.iterdir())
    assert names == [f"采购合同_第{i}页.pdf" for i in range(1, 5)], names
    assert len(PdfReader(str(out / "采购合同_第1页.pdf")).pages) == 1


def _备文本(tmp: Path):
    d = tmp / "文案"
    d.mkdir()
    for i in range(3):
        (d / f"doc{i}.txt").write_text("旧公司名 出品，旧公司名 版权所有", encoding="utf-8")
    return d, 3


def _设文本(page, tmp):
    page._output_path = tmp / "输出"
    page.ed_find.setText("旧公司名")
    page.ed_replace.setText("新公司名")


def _校验文本(tmp):
    out = tmp / "输出"
    内容 = (out / "doc0.txt").read_text(encoding="utf-8")
    assert 内容 == "新公司名 出品，新公司名 版权所有", 内容
    原 = (tmp / "文案" / "doc0.txt").read_text(encoding="utf-8")
    assert "旧公司名" in 原, "原文件必须不变"


任务 = [
    (0, "批量重命名 / 编号", _备重命名, _设重命名, _校验重命名),
    (1, "文件分类整理", _备分类, _设分类, _校验分类),
    (2, "图片批处理", _备图片, _设图片, _校验图片),
    (3, "Excel / CSV 合并", _备表格, _设表格, _校验表格),
    (4, "PDF 拆分", _备PDF, _设PDF, _校验PDF),
    (5, "文本查找替换", _备文本, _设文本, _校验文本),
]


def run(open_output: bool = False) -> int:
    from filebatch.ui.app import create_app
    from filebatch.ui.main_window import MainWindow

    _静音弹窗()
    app = create_app([])
    win = MainWindow()
    win.show()
    for _ in range(10):
        app.processEvents()

    print("=" * 60)
    print(f"打包产物完整验收（平台插件 = {app.platformName()}）")
    print("=" * 60)

    for 序号, 名称, 准备, 设参数, 校验 in 任务:
        # 只对第一个功能真的去打开输出目录，避免弹出一堆访达窗口
        _跑一个功能(app, win, 序号, 名称, 准备, 设参数, 校验,
                   open_output and 序号 == 0)

    失败 = 0
    for 名称, ok, detail in 结果:
        print(f"{'[通过]' if ok else '[失败]'} {名称}")
        print(f"       {detail}")
        if not ok:
            失败 += 1
    print("-" * 60)
    print(f"共 {len(结果)} 个功能，失败 {失败} 个")

    win.close()
    return 1 if 失败 else 0


if __name__ == "__main__":
    try:
        sys.exit(run("--open-output" in sys.argv))
    except Exception:
        traceback.print_exc()
        sys.exit(2)

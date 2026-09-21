"""无头渲染六个功能页并截图，用于文档和验收。

用法：QT_QPA_PLATFORM=offscreen PYTHONPATH=src python scripts/screenshot.py
"""
from __future__ import annotations

import csv
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from filebatch.console import ensure_utf8_output  # noqa: E402

ensure_utf8_output()

from PySide6.QtCore import QDeadlineTimer  # noqa: E402
from PySide6.QtWidgets import QMessageBox  # noqa: E402

from filebatch.core.image_job import ResizeMode  # noqa: E402
from filebatch.ui.app import create_app  # noqa: E402
from filebatch.ui.main_window import MainWindow  # noqa: E402
from filebatch.ui.messages import TEXT  # noqa: E402
from filebatch.ui.pages import base_page as dialogs  # noqa: E402
from filebatch.ui.widgets.collapsible import CollapsibleSection  # noqa: E402

OUT_DIR = ROOT / "docs" / "screenshots"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# 无人值守脚本必须先把模态弹窗换掉，否则 exec() 会永远阻塞
dialogs.show_info = lambda *a, **k: None
dialogs.show_error = lambda *a, **k: None

app = create_app([])
TMP = Path(tempfile.mkdtemp(prefix="filebatch_shot_"))


def 刷新(times: int = 6) -> None:
    for _ in range(times):
        app.processEvents()


已生成: list[str] = []


def 截图(widget, name: str) -> None:
    刷新()
    path = OUT_DIR / f"{name}.png"
    widget.grab().save(str(path))
    已生成.append(name)
    print(f"  {path.relative_to(ROOT)}", flush=True)


def 查过期截图() -> int:
    """目录里有、这次却没生成的，就是界面改过之后留下的旧图。

    旧截图比没有截图更坑：以后维护的人会照着一张早就不存在的界面找控件。
    """
    实际 = {p.stem for p in OUT_DIR.glob("*.png")}
    过期 = sorted(实际 - set(已生成))
    if not 过期:
        return 0
    print("\n⚠ 以下截图这次没有生成，多半是界面改过留下的旧图：", flush=True)
    for n in 过期:
        print(f"    docs/screenshots/{n}.png", flush=True)
    print("  确认不需要就删掉，还需要就在本脚本里补上对应的截图步骤。", flush=True)
    return len(过期)


def 跑完(page) -> None:
    page.start_execute()
    worker = page._worker
    while worker is not None and worker.isRunning():
        app.processEvents()
        worker.wait(QDeadlineTimer(20))
    刷新(12)


def 造照片(base: Path) -> Path:
    from PIL import Image

    d = base / "手机照片"
    d.mkdir(parents=True, exist_ok=True)
    names = [
        "IMG_20260912_084501.jpg", "IMG_20260912_084533.jpg", "IMG_20260912_090210.jpg",
        "IMG_20260913_113045.jpg", "IMG_20260913_154912.jpg", "DSC_0042.jpg",
        "微信图片_20260914.jpg", "截屏2026-09-15.png",
    ]
    for n in names:
        Image.new("RGB", (1600, 1200), (110, 150, 200)).save(d / n)
    return d


def 造杂乱文件(base: Path) -> Path:
    d = base / "下载文件夹"
    d.mkdir(parents=True, exist_ok=True)
    for n in ["合同扫描件.pdf", "季度报表.xlsx", "产品图.jpg", "会议纪要.txt",
              "安装包.zip", "宣传视频.mp4", "名单.csv", "readme.md"]:
        (d / n).write_bytes(b"x" * 4096)
    return d


def 造文本(base: Path) -> Path:
    d = base / "文案"
    d.mkdir(parents=True, exist_ok=True)
    for n in ["首页文案.txt", "产品介绍.txt", "常见问题.txt", "联系方式.txt"]:
        (d / n).write_text("欢迎使用 旧公司名 的产品。\n旧公司名 成立于 2015 年。\n", encoding="utf-8")
    return d


def 造表格(base: Path) -> Path:
    d = base / "月度报表"
    d.mkdir(parents=True, exist_ok=True)
    for i, month in enumerate(["一月", "二月", "三月", "四月"], start=1):
        with open(d / f"{month}销售.csv", "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(["姓名", "金额", "地区"])
            w.writerow([f"销售{i}", str(i * 1000), "华东"])
            w.writerow([f"销售{i + 4}", str(i * 1500), "华南"])
    return d


def 造Excel样例(base: Path) -> Path:
    """Excel 工具箱用的样例：带重复、带空行、带可拆分的列。

    必须是 .xlsx —— 格式统一那一页不收 CSV。
    """
    from openpyxl import Workbook

    d = base / "Excel样例"
    d.mkdir(parents=True, exist_ok=True)

    def 写(name: str, rows: list[list]) -> None:
        wb = Workbook()
        ws = wb.active
        ws.title = "Sheet1"
        for r in rows:
            ws.append(r)
        wb.save(d / name)

    写("3月员工名单.xlsx", [
        ["工号", "姓名", "部门", "金额"],
        ["A001", "张三", "研发部", 12000],
        ["A002", "李四", "销售部", 9000],
        ["A001", "张三", "研发部", 12000],      # 完全重复
        ["A003", "  王五  ", "研发部", 11000],  # 首尾有空格
        ["", "", "", ""],                       # 空行
        ["A004", "赵六", "行政部", 8000],
    ])
    写("4月员工名单.xlsx", [
        ["工号", "姓名", "部门", "金额"],
        ["A001", "张三", "研发部", 13000],      # 金额变了
        ["A002", "李四", "销售部", 9000],        # 没变
        ["A005", "孙七", "销售部", 9500],        # 新人
    ])
    return d


def 造PDF(base: Path) -> Path:
    from pypdf import PdfWriter

    d = base / "合同"
    d.mkdir(parents=True, exist_ok=True)
    for name, pages in [("采购合同.pdf", 5), ("补充协议.pdf", 3), ("附件清单.pdf", 2)]:
        w = PdfWriter()
        for _ in range(pages):
            w.add_blank_page(width=595, height=842)
        with open(d / name, "wb") as f:
            w.write(f)
    return d


def 等读完表头(page, 超时秒: float = 20) -> None:
    """选列的页面表头是后台读的，不等它截出来的图里下拉框是空的。"""
    import time

    worker = getattr(page, "_inspect_worker", None)
    if worker is None:
        return
    t0 = time.time()
    while worker.isRunning() and time.time() - t0 < 超时秒:
        刷新()
        worker.wait(20)
    刷新()


def main() -> int:
    win = MainWindow()
    win.show()
    刷新()
    print("生成截图：", flush=True)

    # ---------- 01 空状态 ----------
    截图(win, "01_空状态")

    # ---------- 02/03 重命名 ----------
    page = win.page_at(0)
    win.nav.setCurrentRow(0)
    page.file_list.add_paths_sync([造照片(TMP)])
    page._output_path = TMP / "重命名结果"
    page.lbl_output.setFullText(str(page._output_path))
    page.ed_base.setText("旅行照片")
    page.cb_number.setCurrentIndex(1)
    page.sp_digits.setValue(3)
    截图(win, "02_重命名_待预览")
    page.generate_preview()
    截图(win, "03_重命名_预览完成")

    for child in page.findChildren(CollapsibleSection):
        child.toggle.setChecked(True)
        break
    截图(win, "04_重命名_高级选项")
    for child in page.findChildren(CollapsibleSection):
        child.toggle.setChecked(False)
        break

    page.chk_danger.setChecked(True)
    截图(win, "05_重命名_危险开关警告")
    page.chk_danger.setChecked(False)
    page._output_path = TMP / "重命名结果"
    page.generate_preview()
    跑完(page)
    截图(win, "06_重命名_执行完成")

    # ---------- 07 分类 ----------
    win.nav.setCurrentRow(1)
    p = win.page_at(1)
    p.file_list.add_paths_sync([造杂乱文件(TMP)])
    p._output_path = TMP / "整理结果"
    p.lbl_output.setFullText(str(p._output_path))
    p.generate_preview()
    截图(win, "07_文件分类整理")

    # ---------- 08 图片 ----------
    win.nav.setCurrentRow(2)
    p = win.page_at(2)
    p.file_list.add_paths_sync([造照片(TMP)])
    p._output_path = TMP / "图片输出"
    p.lbl_output.setFullText(str(p._output_path))
    p.ed_base.setText("产品图")
    p.cb_number.setCurrentIndex(1)
    p.cb_resize.setCurrentIndex(p.cb_resize.findData(ResizeMode.MAX_SIDE))
    p.sp_value.setValue(800)
    p.generate_preview()
    截图(win, "08_图片批处理")

    # ---------- 09 Excel 工具箱：六个标签页各来一张 ----------
    from filebatch.ui.main_window import EXCEL_TOOLBOX_INDEX

    win.nav.setCurrentRow(EXCEL_TOOLBOX_INDEX)
    toolbox = win.page_at(EXCEL_TOOLBOX_INDEX)
    表格源 = 造表格(TMP)
    Excel源 = 造Excel样例(TMP)

    def 截工具箱(标签: int, 文件, 输出, 名称: str, 设参数=None) -> None:
        toolbox.tabs.setCurrentIndex(标签)
        p = toolbox.sub_page(标签)
        p.file_list.add_paths_sync(文件)
        p._output_path = 输出
        p.lbl_output.setFullText(str(输出))
        等读完表头(p)
        if 设参数 is not None:
            设参数(p)
            等读完表头(p)
        p.generate_preview()
        截图(win, 名称)

    截工具箱(0, [表格源], TMP / "合并结果.xlsx", "09a_Excel工具箱_合并")

    截工具箱(1, [Excel源], TMP / "去重结果", "09b_Excel工具箱_去重",
            lambda p: p.list_keys.set_checked(["工号", "姓名"]))

    截工具箱(2, [Excel源], TMP / "对比结果.xlsx", "09c_Excel工具箱_两表对比",
            lambda p: p.list_keys.set_checked(["工号"]))

    截工具箱(3, [Excel源], TMP / "清洗结果", "09d_Excel工具箱_数据清洗")

    截工具箱(4, [Excel源], TMP / "拆表结果", "09e_Excel工具箱_批量拆表",
            lambda p: p.cb_column.setCurrentText("部门"))

    截工具箱(5, [Excel源], TMP / "格式化结果", "09f_Excel工具箱_格式统一")

    # ---------- 10 PDF ----------
    win.nav.setCurrentRow(4)
    p = win.page_at(4)
    p.file_list.add_paths_sync([造PDF(TMP)])
    p._output_path = TMP / "PDF输出"
    p.lbl_output.setFullText(str(p._output_path))
    p.generate_preview()
    截图(win, "10_PDF拆分")

    # ---------- 11 文本 ----------
    win.nav.setCurrentRow(5)
    p = win.page_at(5)
    p.file_list.add_paths_sync([造文本(TMP)])
    p._output_path = TMP / "文本输出"
    p.lbl_output.setFullText(str(p._output_path))
    p.ed_find.setText("旧公司名")
    p.ed_replace.setText("新公司名")
    p.generate_preview()
    截图(win, "11_文本查找替换")

    # ---------- 12 二次确认框 ----------
    box = QMessageBox(win)
    box.setIcon(QMessageBox.Icon.Warning)
    box.setWindowTitle("确认移动文件？")
    box.setText("确认移动文件？")
    box.setInformativeText(win.page_at(1).DANGER_CONFIRM_BODY)
    box.addButton("我确认移动文件", QMessageBox.ButtonRole.DestructiveRole)
    cancel = box.addButton(TEXT["cancel"], QMessageBox.ButtonRole.RejectRole)
    box.setDefaultButton(cancel)
    box.show()
    截图(box, "12_危险操作二次确认")
    box.close()

    过期数 = 查过期截图()
    print(f"\n样例目录（用完可删）：{TMP}", flush=True)
    return 1 if 过期数 else 0


if __name__ == "__main__":
    sys.exit(main())

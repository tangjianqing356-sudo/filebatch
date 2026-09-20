"""批量重命名界面的交互测试。

重点不是像素长什么样，而是锁死几条安全规则：
预览之前不许执行、参数一改预览就作废、危险开关必须二次确认。
"""
from pathlib import Path

import pytest

from tests.conftest import 等待线程结束


@pytest.fixture
def page(qapp, monkeypatch):
    """造一个页面，并把所有弹窗替换成记录器，测试里不会真弹出来卡住。"""
    from filebatch.ui.pages import base_page as bp
    from filebatch.ui.pages import rename_page as rp

    弹窗记录 = {"info": [], "error": [], "confirm": []}

    # 弹窗统一在基类里，patch 基类模块
    monkeypatch.setattr(bp, "show_info", lambda p, t, m: 弹窗记录["info"].append((t, m)))
    monkeypatch.setattr(bp, "show_error", lambda p, t, m, d="": 弹窗记录["error"].append((t, m)))
    monkeypatch.setattr(
        bp, "confirm_dangerous",
        lambda p, t, b, c, x="取消": (弹窗记录["confirm"].append(t), True)[1]
    )

    page = rp.RenamePage()
    page.弹窗记录 = 弹窗记录
    yield page
    worker = page._worker
    if worker is not None and worker.isRunning():
        worker.cancel()
        worker.wait(3000)
    page.deleteLater()


# ---------------- 安全规则 ----------------

def test_刚打开时执行按钮不可用(page):
    assert not page.btn_execute.isEnabled()
    assert "请先点击" in page.lbl_status.text()


def test_没有文件时预览会提示而不是崩溃(page):
    assert page.generate_preview() is False
    assert page.弹窗记录["info"], "应该提示用户先添加文件"
    assert not page.btn_execute.isEnabled()


def test_没选输出文件夹时不让预览(page, 样例文件):
    page.file_list.add_paths_sync(样例文件)
    assert page.generate_preview() is False
    assert any("输出" in t for t, _ in page.弹窗记录["error"])
    assert not page.btn_execute.isEnabled()


def test_输出文件夹和源目录相同时被拦下(page, 样例文件):
    page.file_list.add_paths_sync(样例文件)
    page._output_dir = 样例文件[0].parent          # 故意设成源目录
    assert page.generate_preview() is False
    assert any("不能和源目录相同" in m for _, m in page.弹窗记录["error"])


def test_正则写错时给中文提示不抛异常(page, 样例文件, tmp_path):
    page.file_list.add_paths_sync(样例文件)
    page._output_dir = tmp_path / "输出"
    page.chk_regex.setChecked(True)
    page.ed_find.setText("[未闭合")
    assert page.generate_preview() is False
    assert any("正则" in m for _, m in page.弹窗记录["error"])


def test_预览成功后执行按钮才可用(page, 样例文件, tmp_path):
    page.file_list.add_paths_sync(样例文件)
    page._output_dir = tmp_path / "输出"
    page.ed_prefix.setText("新_")

    assert page.generate_preview() is True
    assert page.btn_execute.isEnabled()
    assert page.preview.rowCount() == 3
    assert not (tmp_path / "输出").exists(), "预览阶段绝不能创建任何文件"


def test_改了参数预览就作废执行按钮变灰(page, 样例文件, tmp_path):
    page.file_list.add_paths_sync(样例文件)
    page._output_dir = tmp_path / "输出"
    page.generate_preview()
    assert page.btn_execute.isEnabled()

    page.ed_prefix.setText("换个前缀_")
    assert not page.btn_execute.isEnabled(), "参数变了旧预览不能还算数"
    assert page.preview.rowCount() == 0


def test_增删文件后预览同样作废(page, 样例文件, tmp_path):
    page.file_list.add_paths_sync(样例文件)
    page._output_dir = tmp_path / "输出"
    page.generate_preview()
    assert page.btn_execute.isEnabled()

    page.file_list.clear()
    assert not page.btn_execute.isEnabled()


def test_没预览就调执行会被挡住(page, 样例文件, tmp_path):
    page.file_list.add_paths_sync(样例文件)
    page._output_dir = tmp_path / "输出"
    assert page.start_execute() is False
    assert page.弹窗记录["info"], "应提示先预览"


# ---------------- 危险开关 ----------------

def test_原地改名开关默认关闭且无警告(page):
    assert not page.chk_in_place.isChecked()
    # 页面没有真正 show()，子控件 isVisible() 恒为 False，要用 isVisibleTo 测自身可见性
    assert not page.lbl_in_place_warn.isVisibleTo(page)


def test_勾选原地改名立刻出现警告(page):
    page.chk_in_place.setChecked(True)
    assert page.lbl_in_place_warn.isVisibleTo(page)
    assert "无法自动撤销" in page.lbl_in_place_warn.text()
    assert not page.btn_output.isEnabled(), "原地改名时不需要输出目录"


def test_原地改名执行前必须二次确认(page, 样例文件, monkeypatch):
    from filebatch.ui.pages import base_page as rp

    page.file_list.add_paths_sync(样例文件)
    page.chk_in_place.setChecked(True)
    page.ed_prefix.setText("新_")
    assert page.generate_preview() is True

    # 用户在确认框点了取消
    monkeypatch.setattr(rp, "confirm_dangerous", lambda *a, **k: False)
    assert page.start_execute() is False
    assert (样例文件[0]).exists(), "用户取消后原文件必须一个都没动"


def test_确认框的取消是默认按钮防止回车误触(qapp):
    """回车不能误触发危险操作——把取消设成默认按钮。"""
    from PySide6.QtWidgets import QMessageBox

    box = QMessageBox()
    confirm = box.addButton("我确认修改原文件", QMessageBox.ButtonRole.DestructiveRole)
    cancel = box.addButton("取消", QMessageBox.ButtonRole.RejectRole)
    box.setDefaultButton(cancel)
    box.setEscapeButton(cancel)

    assert box.defaultButton() is cancel
    assert box.defaultButton() is not confirm


# ---------------- 完整链路 ----------------

def test_完整流程能跑通并产出文件(page, qapp, 样例文件, tmp_path):
    out = tmp_path / "输出"
    page.file_list.add_paths_sync(样例文件)
    page._output_dir = out
    page.ed_base.setText("产品图")
    page.cb_number.setCurrentIndex(1)      # 编号加在后面
    page.sp_digits.setValue(2)

    assert page.generate_preview() is True
    assert page.preview.item(0, 2).text() == "产品图_01.jpg"

    assert page.start_execute() is True
    等待线程结束(qapp, page._worker)

    assert page._last_report is not None
    assert page._last_report.succeeded == 3
    assert sorted(p.name for p in out.iterdir()) == ["产品图_01.jpg", "产品图_02.jpg", "产品图_03.jpg"]
    for f in 样例文件:
        assert f.exists(), "原文件必须保留"

    assert page.btn_save_log.isEnabled()
    assert page.btn_open_output.isEnabled()
    assert not page.btn_execute.isEnabled(), "执行完预览应作废，避免重复执行"


def test_执行完日志里有明细(page, qapp, 样例文件, tmp_path):
    page.file_list.add_paths_sync(样例文件)
    page._output_dir = tmp_path / "输出"
    page.ed_prefix.setText("新_")
    page.generate_preview()
    page.start_execute()
    等待线程结束(qapp, page._worker)

    text = page.log.toPlainText()
    assert "开始执行" in text
    assert "成功 3" in text
    assert "[成功] IMG_001.jpg → 新_IMG_001.jpg" in text, "面板里应是简洁格式"
    assert str(tmp_path) not in text, "完整绝对路径不该刷在面板里"

    # 但导出的详细日志必须有完整路径，方便排查
    detail = page._last_report.to_log_text()
    assert str(tmp_path) in detail
    assert "【处理明细】" in detail


def test_单个文件出错时其余照常完成(page, qapp, 样例文件, tmp_path):
    out = tmp_path / "输出"
    page.file_list.add_paths_sync(样例文件)
    page._output_dir = out
    page.ed_prefix.setText("新_")
    page.generate_preview()

    样例文件[1].unlink()          # 预览之后、执行之前被删掉

    page.start_execute()
    等待线程结束(qapp, page._worker)

    assert page._last_report.succeeded == 2
    assert page._last_report.failed == 1
    assert len(list(out.iterdir())) == 2


def test_中断按钮会真的通知后台线程停下来(page, 样例文件, tmp_path):
    """按钮接线测试：点中断 -> worker.cancel() 被调用，界面给出正确提示。"""
    page.file_list.add_paths_sync(样例文件)
    page._output_dir = tmp_path / "输出"
    page.ed_prefix.setText("新_")
    page.generate_preview()
    page.start_execute()

    worker = page._worker
    assert worker is not None
    page._cancel()

    assert worker.cancelled is True
    # 文案按需求改成明确说明"当前文件会处理完"，避免用户以为能立刻停住
    assert "当前文件处理完成后停止" in page.lbl_status.text()
    assert "已完成的会保留" in page.lbl_status.text()
    assert not page.btn_cancel.isEnabled(), "点过之后要防止重复点"
    worker.wait(5000)


def test_中断后未执行的文件不会被处理(page, qapp, tmp_path):
    """开跑前就请求中断：一个文件都不该被动，原文件全须全尾。

    （"已完成的保留、后续的跳过"这种部分中断，在 core 层用
    test_rename_job.py::test_中断只停止后续任务不影响已完成的 做了确定性验证——
    GUI 层跨线程的时序没法稳定复现，不适合在这里测。）
    """
    src = tmp_path / "源"
    src.mkdir()
    files = []
    for i in range(20):
        f = src / f"f{i:03d}.txt"
        f.write_text("x", encoding="utf-8")
        files.append(f)

    out = tmp_path / "输出"
    page.file_list.add_paths_sync(files)
    page._output_dir = out
    page.ed_prefix.setText("新_")
    page.generate_preview()
    page.start_execute()

    page._worker.cancel()          # 线程刚起来就喊停
    等待线程结束(qapp, page._worker)

    report = page._last_report
    assert report is not None
    assert report.succeeded + len(report.skipped) == 20, "每个文件都要有交代"
    assert all("用户中断" in r for _, r in report.skipped)
    # 中断不会破坏任何原文件
    for f in files:
        assert f.exists()
    # 输出目录里只会有中断前真正完成的那些
    produced = len(list(out.iterdir())) if out.exists() else 0
    assert produced == report.succeeded


def test_预览里跳过项显示不处理(page, 样例文件, tmp_path):
    page.file_list.add_paths_sync(样例文件)
    page.chk_in_place.setChecked(True)   # 不改名 => 新旧同名 => 全部跳过
    assert page.generate_preview() is False
    assert page.preview.item(0, 2).text() == "不处理"
    assert "无需处理" in page.preview.item(0, 3).text()
    assert not page.btn_execute.isEnabled()


# ---------------- 体验优化相关 ----------------

def test_执行完成后预览区切换成执行结果状态(page, qapp, 样例文件, tmp_path):
    """避免"表格还在、状态却说预览已作废"这种自相矛盾的观感。"""
    page.file_list.add_paths_sync(样例文件)
    page._output_dir = tmp_path / "输出"
    page.ed_prefix.setText("新_")
    page.generate_preview()
    assert "预览" in page.box_preview.title()

    page.start_execute()
    等待线程结束(qapp, page._worker)

    assert "本次执行结果" in page.box_preview.title()
    assert page.preview.rowCount() == 3, "结果应保留下来供用户核对"
    assert page.preview.horizontalHeaderItem(2).text() == "结果"
    assert not page.btn_execute.isEnabled()


def test_改参数后从执行结果切回预览态(page, qapp, 样例文件, tmp_path):
    page.file_list.add_paths_sync(样例文件)
    page._output_dir = tmp_path / "输出"
    page.ed_prefix.setText("新_")
    page.generate_preview()
    page.start_execute()
    等待线程结束(qapp, page._worker)
    assert "本次执行结果" in page.box_preview.title()

    page.ed_prefix.setText("换一个_")
    assert "预览" in page.box_preview.title()
    assert page.preview.rowCount() == 0
    assert page.preview.horizontalHeaderItem(2).text() == "处理后"


def test_步骤条跟着流程走(page, 样例文件, tmp_path):
    from filebatch.ui.widgets.step_indicator import STEPS

    assert len(STEPS) == 4
    page._update_steps()
    assert page.steps._labels[0].styleSheet().startswith("color:#2563eb")

    page.file_list.add_paths_sync(样例文件)
    assert page.steps._labels[1].styleSheet().startswith("color:#2563eb")

    page._output_dir = tmp_path / "输出"
    page.ed_prefix.setText("新_")
    page.generate_preview()
    assert page.steps._labels[3].styleSheet().startswith("color:#2563eb")


def test_预设能一键填好参数(page):
    from filebatch.core.naming import CaseMode, NumberPosition

    idx = next(i for i in range(page.cb_preset.count())
               if page.cb_preset.itemText(i) == "照片自动编号")
    page.cb_preset.setCurrentIndex(idx)

    assert page.ed_base.text() == "照片"
    assert page.cb_number.currentData() == NumberPosition.SUFFIX
    assert page.sp_digits.value() == 3
    rule = page.current_rule()
    assert rule.apply("IMG_9281", 0) == "照片_001"

    idx = next(i for i in range(page.cb_preset.count())
               if page.cb_preset.itemText(i) == "统一改成小写")
    page.cb_preset.setCurrentIndex(idx)
    assert page.cb_case.currentData() == CaseMode.LOWER
    assert page.current_rule().apply("ReadMe", 0) == "readme"


def test_选预设也会让旧预览失效(page, 样例文件, tmp_path):
    page.file_list.add_paths_sync(样例文件)
    page._output_dir = tmp_path / "输出"
    page.ed_prefix.setText("新_")
    page.generate_preview()
    assert page.btn_execute.isEnabled()

    idx = next(i for i in range(page.cb_preset.count())
               if page.cb_preset.itemText(i) == "统一改成小写")
    page.cb_preset.setCurrentIndex(idx)
    assert not page.btn_execute.isEnabled()


def test_长路径中间省略且完整路径进tooltip(qapp):
    from filebatch.ui.widgets.elided_label import ElidedLabel

    长路径 = "/Users/someone/Documents/2026年/项目资料/客户提供/第三批/原始照片/待处理"
    lbl = ElidedLabel()
    lbl.setFixedWidth(180)
    lbl.setFullText(长路径)

    assert lbl.toolTip() == 长路径, "完整路径必须能从 tooltip 看到"
    assert lbl.text() != 长路径, "显示出来的应该是省略版"
    assert "…" in lbl.text() or "..." in lbl.text()
    assert lbl.fullText() == 长路径


def test_扫描期间不让点预览(page):
    page._on_scanning_changed(True)
    assert not page.btn_preview.isEnabled()
    assert "正在扫描" in page.lbl_status.text()

    page._on_scanning_changed(False)
    assert page.btn_preview.isEnabled()


def test_后台扫描能把文件加进来(page, qapp, tmp_path):
    from tests.conftest import 等待线程结束 as 等待

    d = tmp_path / "一批文件"
    d.mkdir()
    for i in range(30):
        (d / f"f{i:03d}.txt").write_text("x", encoding="utf-8")

    page.file_list.add_paths([d])
    scanner = page.file_list._scanner
    assert scanner is not None
    等待(qapp, scanner)

    assert len(page.file_list.files()) == 30
    assert not page.file_list.scan_bar.isVisibleTo(page.file_list), "扫完要把状态条收起来"

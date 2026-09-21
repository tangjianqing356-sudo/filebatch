"""OSError 的中文说明：绝不把 errno / WinError 甩给普通用户。

这个是在 Windows 验收准备阶段发现的：指向一个不存在的盘符时，
界面上会出现 `系统错误：[Errno 30] Read-only file system: '/xxx'`。
用户既看不懂也不知道该怎么办。
"""
import errno
import os
from pathlib import Path

import pytest

from filebatch.core.oserrors import describe


def 造(code: int, 文本: str = "boom") -> OSError:
    return OSError(code, 文本, "/某个路径")


@pytest.mark.parametrize("code, 关键词", [
    (errno.ENOSPC, "磁盘空间"),
    (errno.ENAMETOOLONG, "太长"),
    (errno.EROFS, "只读"),
    (errno.EACCES, "权限"),
    (errno.ENOENT, "找不到"),
    (errno.ENOTDIR, "文件夹"),
    (errno.ENODEV, "断开"),
    (errno.EXDEV, "复制"),
])
def test_常见错误码都有人话(code, 关键词):
    说法 = describe(造(code))
    assert 关键词 in 说法, 说法
    assert "Errno" not in 说法 and "errno" not in 说法
    assert str(code) not in 说法, f"错误码泄漏了：{说法}"


def test_没见过的错误码也不泄漏细节():
    说法 = describe(造(99999, "something weird"))
    assert "99999" not in 说法
    assert "weird" not in 说法
    assert "磁盘" in 说法 or "系统" in 说法


def test_没有errno的OSError也能处理():
    说法 = describe(OSError("说不清的错误"))
    assert 说法 and "说不清的错误" not in 说法


def test_界面层和核心层说法一致():
    """两套措辞飘了的话，日志和弹窗会对不上。"""
    from filebatch.ui.messages import humanize

    e = 造(errno.EROFS)
    assert humanize(e) == describe(e)


# ---------------- 真跑一遍，确认执行循环里也不泄漏 ----------------

def 写表(path: Path, rows):
    from openpyxl import Workbook

    path.parent.mkdir(parents=True, exist_ok=True)
    wb = Workbook()
    ws = wb.active
    for r in rows:
        ws.append(r)
    wb.save(path)
    return path


def test_输出位置不存在时的失败原因是人话(tmp_path):
    from filebatch.core.excel import dedupe_job
    from filebatch.core.excel.dedupe_job import DedupeOptions

    src = 写表(tmp_path / "源" / "数据.xlsx", [["A"], ["1"], ["1"]])
    不存在 = Path("Z:/没有这个盘/输出") if os.name == "nt" else Path("/没有这个挂载点/输出")

    opts = DedupeOptions()
    report = dedupe_job.execute(dedupe_job.plan([src], opts, 不存在), opts)

    assert report.failed == 1
    消息 = report.items[0].message
    for 脏东西 in ("Errno", "WinError", "Traceback", "OSError"):
        assert 脏东西 not in 消息, f"错误信息里漏出了 {脏东西}：{消息}"


@pytest.mark.parametrize("模块名", [
    "rename_job", "classify_job", "image_job", "pdf_job", "text_job",
])
def test_六个功能的执行循环都不再拼原始OSError(模块名):
    """防回归：以后谁再写回 f"系统错误：{e}"，这里会炸。"""
    import inspect
    import importlib

    模块 = importlib.import_module(f"filebatch.core.{模块名}")
    源码 = inspect.getsource(模块)
    assert '系统错误：{e}' not in 源码, f"{模块名} 又在往用户面前拼原始异常"
    assert "说明错误" in 源码 or "describe" in 源码, f"{模块名} 没有走统一的错误说明"


def test_Excel执行循环也不拼原始OSError():
    import inspect

    from filebatch.core.excel import runner

    源码 = inspect.getsource(runner)
    assert '系统错误：{e}' not in 源码
    assert "说明错误" in 源码


# ---------------- Windows 错误码（CI 上暴露出来的） ----------------
#
# Windows 的 winerror 和 POSIX errno 对不上：文件名超长 Windows 给 winerror 206，
# 而 errno 只是个笼统的 22。只看 errno 会掉进兜底文案，
# 用户看到的就变成"系统在读写文件时出错了"这种没法操作的话。

def 造win(winerror: int, errno_: int = 22) -> OSError:
    e = OSError(errno_, "windows boom", "C:/某个路径")
    e.winerror = winerror
    return e


@pytest.mark.parametrize("win, 关键词", [
    (2, "找不到"),
    (3, "不存在"),
    (5, "权限"),
    (15, "盘符"),
    (32, "占用"),
    (33, "锁住"),
    (112, "磁盘空间"),
    (123, "不允许"),
    (206, "太长"),
])
def test_Windows错误码都有人话(win, 关键词):
    说法 = describe(造win(win))
    assert 关键词 in 说法, 说法
    assert "WinError" not in 说法 and str(win) not in 说法


def test_winerror优先于errno():
    """同一个异常两个码都有时，Windows 的那个更具体。"""
    e = 造win(206, errno_=errno.EINVAL)
    assert "太长" in describe(e)


def test_没见过的winerror回落到errno():
    e = 造win(99999, errno_=errno.ENOSPC)
    assert "磁盘空间" in describe(e)


def test_Windows上的EINVAL不再掉进兜底文案(monkeypatch):
    """CI 上"超长文件名"那条就是栽在这里：Windows 只给了 EINVAL。"""
    import filebatch.core.oserrors as mod

    monkeypatch.setattr(mod.sys, "platform", "win32")
    说法 = mod.describe(OSError(errno.EINVAL, "Invalid argument"))
    assert "太长" in 说法, 说法
    assert "系统在读写文件时出错了" not in 说法


def test_非Windows的EINVAL仍然走兜底(monkeypatch):
    """EINVAL 在 POSIX 上含义不同，不能套用 Windows 的说法。"""
    import filebatch.core.oserrors as mod

    monkeypatch.setattr(mod.sys, "platform", "darwin")
    说法 = mod.describe(OSError(errno.EINVAL, "Invalid argument"))
    assert "太长" not in 说法


def test_分得清源文件没了和输出位置没了():
    """Windows CI 实测：输出指向不存在的盘符时，原来会说"文件已不存在"，
    把矛头指向源文件，用户按提示去找源文件是白费功夫。
    """
    源 = Path("/某处/源文件.xlsx")

    没源文件 = OSError(errno.ENOENT, "No such file", str(源))
    assert "找不到这个文件" in describe(没源文件, source=源)

    没输出位置 = OSError(errno.ENOENT, "No such file", "/不存在的盘/输出/结果.xlsx")
    说法 = describe(没输出位置, source=源)
    assert "输出位置" in 说法, 说法
    assert "移动、重命名或删除" not in 说法, "别把矛头指向源文件"


def test_Windows上也分得清():
    源 = Path("C:/某处/源文件.xlsx")
    e = OSError(2, "not found", "Z:/没有这个盘/输出/结果.xlsx")
    e.winerror = 3
    assert "输出位置" in describe(e, source=源)


def test_不给source时保持原来的行为():
    e = OSError(errno.ENOENT, "No such file", "/某处/x.txt")
    assert "找不到这个文件" in describe(e)


def test_输出位置真跑一遍给对提示(tmp_path):
    import os as _os

    from filebatch.core.excel import dedupe_job
    from filebatch.core.excel.dedupe_job import DedupeOptions

    src = 写表(tmp_path / "源" / "数据.xlsx", [["A"], ["1"], ["1"]])
    不存在 = Path("Z:/没有这个盘/输出") if _os.name == "nt" else Path("/没有这个挂载点/输出")

    opts = DedupeOptions()
    report = dedupe_job.execute(dedupe_job.plan([src], opts, 不存在), opts)
    assert report.failed == 1
    消息 = report.items[0].message
    assert "移动、重命名或删除" not in 消息, f"矛头指错了：{消息}"

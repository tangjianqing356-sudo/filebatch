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
    (errno.ENOENT, "不存在"),
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

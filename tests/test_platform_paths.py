"""路径与编码的平台相关行为。

这些用例在 Mac 上也能跑，但真正的价值在 Windows CI 上：
中文路径、emoji、空格、深目录、长路径、只读、占用、大小写重命名，
Windows 的表现和 POSIX 差别很大，必须在真 Windows 上跑一遍才算数。
"""
import os
import stat
import sys
from pathlib import Path

import pytest

from filebatch.core import rename_job
from filebatch.core.naming import CaseMode, NameRule, NumberPosition

IS_WIN = sys.platform == "win32"


def _建文件(d: Path, name: str, content: str = "内容") -> Path:
    d.mkdir(parents=True, exist_ok=True)
    f = d / name
    f.write_text(content, encoding="utf-8")
    return f


def _跑一次(files, rule, out, in_place=False):
    return rename_job.execute(rename_job.plan_rename(files, rule, out, in_place), in_place)


# ---------------- 中文 / emoji / 空格 ----------------

def test_中文路径和中文文件名(tmp_path):
    src = tmp_path / "我的 项目资料" / "2026年 第一季度"
    f = _建文件(src, "季度总结报告.txt")
    out = tmp_path / "输出 目录"

    report = _跑一次([f], NameRule(prefix="已归档_"), out)
    assert report.succeeded == 1
    assert (out / "已归档_季度总结报告.txt").exists()
    assert (out / "已归档_季度总结报告.txt").read_text(encoding="utf-8") == "内容"


def test_emoji文件名(tmp_path):
    f = _建文件(tmp_path / "源", "会议纪要 🎉 最终版 ✅.txt")
    out = tmp_path / "输出"

    report = _跑一次([f], NameRule(prefix="2026_"), out)
    assert report.succeeded == 1, report.items[0].message if report.items else ""
    assert (out / "2026_会议纪要 🎉 最终版 ✅.txt").exists()


def test_路径里有空格(tmp_path):
    src = tmp_path / "Program Files Like" / "My Documents"
    f = _建文件(src, "file with spaces.txt")
    out = tmp_path / "out put"

    report = _跑一次([f], NameRule(base_name="重命名后"), out)
    assert report.succeeded == 1
    assert (out / "重命名后.txt").exists()


def test_很深的目录(tmp_path):
    深 = tmp_path
    for i in range(15):
        深 = 深 / f"第{i}层"
    f = _建文件(深, "深处的文件.txt")
    out = tmp_path / "输出"

    report = _跑一次([f], NameRule(prefix="x_"), out)
    assert report.succeeded == 1


def test_混合极端文件名(tmp_path):
    src = tmp_path / "源"
    names = [
        "普通.txt", "有 空 格.txt", "中文名字.txt", "emoji 🚀.txt",
        "UPPER.TXT", "点.在.中间.txt", "-开头的横杠.txt", "括号(1).txt",
    ]
    files = [_建文件(src, n) for n in names]
    out = tmp_path / "输出"

    report = _跑一次(files, NameRule(number_position=NumberPosition.PREFIX), out)
    assert report.succeeded == len(names), [i.message for i in report.items if not i.ok]
    assert len(list(out.iterdir())) == len(names)


# ---------------- 大小写 ----------------

def test_只改大小写的重命名(tmp_path):
    """macOS 和 Windows 的文件系统都不区分大小写，这种改名最容易被误判成重名冲突。"""
    f = _建文件(tmp_path / "源", "ReadMe.TXT")
    report = _跑一次([f], NameRule(case_mode=CaseMode.LOWER), None, in_place=True)

    assert report.succeeded == 1
    names = [p.name for p in (tmp_path / "源").iterdir()]
    assert names == ["readme.TXT"], names


# ---------------- 权限与占用 ----------------

def test_只读文件能被复制出来(tmp_path):
    """只读源文件只是读，复制应该正常。"""
    f = _建文件(tmp_path / "源", "只读.txt")
    os.chmod(f, stat.S_IREAD)
    out = tmp_path / "输出"
    try:
        report = _跑一次([f], NameRule(prefix="副本_"), out)
        assert report.succeeded == 1
        assert (out / "副本_只读.txt").exists()
    finally:
        os.chmod(f, stat.S_IWRITE | stat.S_IREAD)


@pytest.mark.skipif(IS_WIN, reason="Windows 上目录只读位不阻止写入，行为不同")
def test_输出目录没有写权限时给出可读的失败原因(tmp_path):
    f = _建文件(tmp_path / "源", "a.txt")
    out = tmp_path / "不可写"
    out.mkdir()
    os.chmod(out, stat.S_IREAD | stat.S_IEXEC)
    try:
        report = _跑一次([f], NameRule(), out)
        assert report.failed == 1
        msg = report.items[0].message
        assert "权限" in msg or "系统错误" in msg
        assert "Traceback" not in msg
    finally:
        os.chmod(out, stat.S_IRWXU)


@pytest.mark.skipif(not IS_WIN, reason="只有 Windows 会锁住正在打开的文件")
def test_Windows上被其他程序占用的文件(tmp_path):
    """Windows 独占打开的文件无法被改名，必须给中文提示而不是系统异常。"""
    f = _建文件(tmp_path / "源", "占用中.txt")
    handle = open(f, "r+b")
    try:
        report = _跑一次([f], NameRule(prefix="新_"), None, in_place=True)
        if report.failed:
            msg = report.items[0].message
            assert "权限" in msg or "占用" in msg or "系统错误" in msg
            assert "Traceback" not in msg
    finally:
        handle.close()


# ---------------- 冲突与长度 ----------------

def test_输出重名冲突时逐个避让(tmp_path):
    src = tmp_path / "源"
    files = [_建文件(src / f"子{i}", "同名.txt", f"内容{i}") for i in range(4)]
    out = tmp_path / "输出"
    out.mkdir()
    (out / "同名.txt").write_text("原有内容", encoding="utf-8")

    report = _跑一次(files, NameRule(), out)
    assert report.succeeded == 4
    assert (out / "同名.txt").read_text(encoding="utf-8") == "原有内容", "已有文件绝不能被覆盖"
    assert sorted(p.name for p in out.iterdir()) == [
        "同名.txt", "同名_1.txt", "同名_2.txt", "同名_3.txt", "同名_4.txt"
    ]


def test_超长文件名给中文提示而不是系统异常(tmp_path):
    f = _建文件(tmp_path / "源", "a.txt")
    out = tmp_path / "输出"
    report = _跑一次([f], NameRule(prefix="超长前缀" * 80), out)

    if report.failed:
        msg = report.items[0].message
        assert "Traceback" not in msg and "Errno" not in msg, msg
        assert "WinError" not in msg, msg
        # 失败时把真实消息带出来：Windows 的错误码和 POSIX 对不上，
        # 看不到原文就只能靠猜
        assert any(k in msg for k in ("太长", "过长", "不被系统接受", "权限", "不允许")), (
            f"超长文件名应该给出可操作的中文提示，实际是：{msg}"
        )


def test_路径长度上限在当前平台能被测出来():
    from filebatch.core.pathlimits import probe_path_limit, reset_cache

    reset_cache()
    limit = probe_path_limit()
    assert limit.probe_error is None, limit.probe_error
    if IS_WIN and limit.has_limit:
        # 没开长路径支持的 Windows 应该落在 260 附近
        assert 200 < limit.max_path < 300, f"Windows 实测上限 {limit.max_path} 不太对"


# ---------------- 扫描规模 ----------------

@pytest.mark.parametrize("数量", [1000])
def test_大批量扫描(tmp_path, 数量):
    from filebatch.core.scan import collect_files

    d = tmp_path / "很多文件"
    d.mkdir()
    for i in range(数量):
        (d / f"文件_{i:05d}.txt").write_bytes(b"x")

    files = collect_files([d])
    assert len(files) == 数量
    # 顺序必须稳定，否则自动编号的结果每次都不一样
    assert files == collect_files([d])

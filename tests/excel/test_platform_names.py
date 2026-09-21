"""Excel 工具箱在 Windows / macOS 上的文件名与工作表名兼容性。

拆表功能会拿**用户数据里的列值**去当文件名和工作表名，这是整个工具箱里
最容易在换台机器时炸掉的地方：Mac 上能存的名字 Windows 上未必能存。
所以统一按 Windows 那套更严的规则生成，两边拆出来的名字保持一致。
"""
import sys

import pytest

from filebatch.core.excel import split_job
from filebatch.core.excel.split_job import SplitOptions, make_filename
from filebatch.core.excel.workbook import SHEET_NAME_MAX, safe_sheet_name
from filebatch.core.naming import sanitize_filename

# Windows 不允许出现在文件名里的字符
WIN_非法 = '\\/:*?"<>|'


@pytest.mark.parametrize("值", [
    "华东/华南", "研发:一组", "问号?", "星号*", "引号\"里\"", "竖线|", "小于<大于>",
    "反斜杠\\路径",
])
def test_列值里的非法字符都会被换掉(值):
    名 = make_filename("{原名}_{值}", "源表", 值, ".xlsx")
    assert not any(c in 名 for c in WIN_非法), f"{值!r} → {名!r} 里还有非法字符"
    assert 名.endswith(".xlsx")


@pytest.mark.parametrize("保留名", ["CON", "con", "NUL", "PRN", "AUX", "COM1", "LPT9"])
def test_Windows保留设备名不会被原样当成文件名(保留名):
    """模板只有 {值} 时，列值恰好是 CON 会让 Windows 直接拒绝建文件。"""
    名 = make_filename("{值}", "源表", 保留名, ".xlsx")
    assert 名.split(".")[0].upper() not in {"CON", "NUL", "PRN", "AUX", "COM1", "LPT9"}, 名
    assert 保留名 in 名, "只是加个后缀区分，不该把原值弄没"


def test_结尾的点和空格会被去掉():
    """Windows 会把结尾的点和空格悄悄吃掉，导致文件名和预期对不上。"""
    assert make_filename("{值}", "x", "部门.", ".xlsx") == "部门.xlsx"
    assert make_filename("{值}", "x", "部门 ", ".xlsx") == "部门.xlsx"


def test_整串都是非法字符时有兜底名():
    名 = make_filename("{值}", "x", "///", ".xlsx")
    assert 名 and not 名.startswith("."), 名


@pytest.mark.parametrize("超长", ["部" * 300, "a" * 300, "混合abc中文" * 50])
def test_超长列值按字符和字节双重截断(超长):
    """字符数管 Windows / macOS，字节数管 Linux 和网络共享，两道都要过。"""
    名 = make_filename("{原名}_{值}", "表", 超长, ".xlsx")
    assert len(名) <= 130, f"字符数超了：{len(名)}"
    assert len(名.encode("utf-8")) < 255, f"UTF-8 字节数超了：{len(名.encode('utf-8'))}"
    assert 名.endswith(".xlsx")
    # 不能把多字节字符从中间切开
    名.encode("utf-8").decode("utf-8")


def test_超长列值真的写得下去(写xlsx, tmp_path):
    src = 写xlsx(tmp_path / "源" / "表.xlsx", [["名", "组"], ["a", "部" * 300]])
    out = tmp_path / "输出"
    opts = SplitOptions(split_column="组")
    report = split_job.execute(split_job.plan([src], opts, out), opts)
    assert report.failed == 0, report.summary()
    产物 = list(out.iterdir())
    assert len(产物) == 1 and 产物[0].stat().st_size > 0


def test_中文空格emoji的列值能真的落盘(写xlsx, tmp_path):
    src = 写xlsx(tmp_path / "源" / "表.xlsx", [
        ["名", "分组"],
        ["a", "中文 分组"],
        ["b", "emoji 😀 组"],
        ["c", "English Group"],
    ])
    out = tmp_path / "输出"
    opts = SplitOptions(split_column="分组")
    report = split_job.execute(split_job.plan([src], opts, out), opts)

    assert report.failed == 0, report.summary()
    assert len(list(out.iterdir())) == 3
    for p in out.iterdir():
        assert p.stat().st_size > 0


def test_非法字符的两个组不会相互覆盖(写xlsx, tmp_path):
    """"a/b" 和 "a\\b" 清洗后都是 "a_b"，必须靠避让机制分开。"""
    src = 写xlsx(tmp_path / "源" / "表.xlsx", [
        ["名", "组"], ["x", "a/b"], ["y", "a\\b"],
    ])
    out = tmp_path / "输出"
    opts = SplitOptions(split_column="组")
    report = split_job.execute(split_job.plan([src], opts, out), opts)

    assert report.failed == 0, report.summary()
    names = sorted(p.name for p in out.iterdir())
    assert len(names) == 2, f"两个组不该合成一个文件：{names}"


# ---------------- 工作表名 ----------------

@pytest.mark.parametrize("名", ["华东/华南", "a:b", "x[1]", "问?号", "星*号", "反\\斜杠"])
def test_工作表名里的非法字符被换掉(名):
    清 = safe_sheet_name(名)
    assert not any(c in 清 for c in '\\/?*[]:'), f"{名!r} → {清!r}"
    assert 清


def test_工作表名超过31字会被截断():
    assert len(safe_sheet_name("部" * 50)) == SHEET_NAME_MAX


def test_空工作表名有兜底():
    assert safe_sheet_name("") == "结果"
    assert safe_sheet_name("   ") == "结果"


# ---------------- 输出路径 ----------------

def test_输出目录不存在时会被建出来(写xlsx, tmp_path):
    src = 写xlsx(tmp_path / "源" / "表.xlsx", [["名", "组"], ["a", "一"]])
    out = tmp_path / "还" / "没" / "建" / "的" / "深目录"
    opts = SplitOptions(split_column="组")
    report = split_job.execute(split_job.plan([src], opts, out), opts)
    assert report.failed == 0, report.summary()
    assert out.exists()


@pytest.mark.skipif(sys.platform != "win32", reason="只有 Windows 有盘符和反斜杠分隔符")
def test_Windows上输出路径用反斜杠也正常(写xlsx, tmp_path):
    from pathlib import Path

    src = 写xlsx(tmp_path / "源" / "表.xlsx", [["名", "组"], ["a", "一"]])
    out = Path(str(tmp_path) + "\\输出")
    opts = SplitOptions(split_column="组")
    report = split_job.execute(split_job.plan([src], opts, out), opts)
    assert report.failed == 0, report.summary()


def test_源文件名本身带非法字符时不影响输出(写xlsx, tmp_path):
    """macOS 上文件名可以有冒号（Finder 显示成斜杠），拿去拼输出名要清掉。"""
    src = 写xlsx(tmp_path / "源" / "表.xlsx", [["名", "组"], ["a", "一"]])
    out = tmp_path / "输出"
    opts = SplitOptions(split_column="组", name_template="{原名}:{值}")
    report = split_job.execute(split_job.plan([src], opts, out), opts)
    assert report.failed == 0, report.summary()
    assert not any(":" in p.name for p in out.iterdir())


def test_sanitize保持两个平台结果一致():
    """同一份数据在 Mac 和 Windows 拆出来的文件名必须一样。"""
    assert sanitize_filename("华东/华南") == "华东_华南"
    assert sanitize_filename("a:b") == "a_b"          # macOS 本可以保留，但统一按 Windows 来
    assert sanitize_filename("CON") == "CON_"

"""共用的读写层与格式识别。"""
from pathlib import Path

import pytest

from filebatch.core.excel.workbook import (
    TableData,
    describe_unsupported,
    is_blank_row,
    list_sheets,
    read_table,
    sniff_format,
    write_sheets,
    write_table,
)


def test_识别正常xlsx(写xlsx, tmp_path):
    p = 写xlsx(tmp_path / "a.xlsx", [["A"], ["1"]])
    assert sniff_format(p) == "zip"
    assert describe_unsupported(p) is None


def test_旧版xls给明确提示(tmp_path):
    p = tmp_path / "老表.xls"
    p.write_bytes(b"\xd0\xcf\x11\xe0old excel")
    reason = describe_unsupported(p)
    assert reason and "另存为" in reason and ".xlsx" in reason


def test_加密或改名的xlsx被识别出来(tmp_path):
    """加密的 xlsx 外层是 OLE2 容器，和 .xls 一模一样，不能静默当成正常文件读。"""
    p = tmp_path / "加密的.xlsx"
    p.write_bytes(b"\xd0\xcf\x11\xe0" + b"\x00" * 100)
    reason = describe_unsupported(p)
    assert reason is not None
    assert "密码" in reason or "改名" in reason


def test_空文件被识别(tmp_path):
    p = tmp_path / "空.xlsx"
    p.write_bytes(b"")
    assert "空" in (describe_unsupported(p) or "")


def test_xlsb给明确提示(tmp_path):
    p = tmp_path / "二进制.xlsb"
    p.write_bytes(b"PK\x03\x04")
    assert "另存为" in (describe_unsupported(p) or "")


def test_损坏的xlsx不会被当成正常文件(tmp_path):
    p = tmp_path / "坏.xlsx"
    p.write_bytes(b"this is definitely not excel")
    assert describe_unsupported(p) is not None


def test_读表头和数据行(写xlsx, tmp_path):
    p = 写xlsx(tmp_path / "a.xlsx", [["姓名", "金额"], ["张三", 100]])
    data = read_table(p)
    assert data.header == ["姓名", "金额"]
    assert data.rows == [["张三", "100"]]
    assert data.row_count == 1


def test_无表头时所有行都是数据(写xlsx, tmp_path):
    p = 写xlsx(tmp_path / "a.xlsx", [["张三", "100"], ["李四", "200"]])
    data = read_table(p, has_header=False)
    assert data.header == []
    assert len(data.rows) == 2


def test_按列名取值(写xlsx, tmp_path):
    p = 写xlsx(tmp_path / "a.xlsx", [["姓名", "金额"], ["张三", "100"]])
    data = read_table(p)
    assert data.value(data.rows[0], "金额") == "100"
    assert data.value(data.rows[0], "不存在的列") == ""


def test_读GBK编码的csv(写csv, tmp_path):
    p = 写csv(tmp_path / "gbk.csv", [["姓名", "城市"], ["张三", "北京"]], encoding="gb18030")
    data = read_table(p)
    assert data.header == ["姓名", "城市"]
    assert data.rows == [["张三", "北京"]]


def test_列出工作表(写xlsx, tmp_path):
    from openpyxl import Workbook

    p = tmp_path / "多表.xlsx"
    wb = Workbook()
    wb.active.title = "一月"
    wb.create_sheet("二月")
    wb.save(p)
    assert list_sheets(p) == ["一月", "二月"]


def test_空行判定():
    assert is_blank_row(["", "  ", "\t"])
    assert not is_blank_row(["", "x"])


def test_写xlsx和csv(tmp_path):
    data = TableData(header=["姓名"], rows=[["张三"], ["李四"]])

    x = tmp_path / "out.xlsx"
    write_table(data, x, "xlsx")
    assert read_table(x).rows == [["张三"], ["李四"]]

    c = tmp_path / "out.csv"
    write_table(data, c, "csv")
    assert c.read_text(encoding="utf-8-sig").splitlines() == ["姓名", "张三", "李四"]


def test_工作表名超长会被截断(tmp_path):
    """Excel 的工作表名上限 31 字符，超了 openpyxl 会直接报错。"""
    data = TableData(header=["A"], rows=[["1"]])
    p = tmp_path / "out.xlsx"
    write_table(data, p, "xlsx", sheet_name="非常长的工作表名字" * 10)
    assert list_sheets(p)[0] != ""


def test_一次写多张工作表(tmp_path):
    p = tmp_path / "多表.xlsx"
    write_sheets(p, [
        ("汇总", TableData(header=["项"], rows=[["1"]])),
        ("明细", TableData(header=["项"], rows=[["2"]])),
    ])
    assert list_sheets(p) == ["汇总", "明细"]


# ---- 工作表名：比文件名限制更多，容易踩 ----

def test_清洗工作表名里的非法字符():
    from filebatch.core.excel.workbook import safe_sheet_name

    for 非法 in ["A/B", "A\\B", "A?B", "A*B", "A[B", "A]B", "A:B"]:
        名 = safe_sheet_name(非法)
        assert not (set(名) & set('\\/?*[]:')), f"{非法} 没清干净：{名}"


def test_工作表名超长被截断():
    from filebatch.core.excel.workbook import SHEET_NAME_MAX, safe_sheet_name

    assert len(safe_sheet_name("很长的名字" * 20)) <= SHEET_NAME_MAX


def test_工作表名为空时用兜底名():
    from filebatch.core.excel.workbook import safe_sheet_name

    assert safe_sheet_name("") == "结果"
    assert safe_sheet_name("   ") == "结果"
    # 全是非法字符时替换成下划线即可，保留区分度比统一回退成"结果"更好——
    # 否则两个不同的组会挤到同一个名字上
    assert safe_sheet_name("///") == "___"


def test_带斜杠的工作表名能真的写出去(tmp_path):
    """回归测试：openpyxl 会直接拒绝含 / 的工作表名，拆表按地区拆时就会踩到。"""
    data = TableData(header=["A"], rows=[["1"]])
    p = tmp_path / "out.xlsx"
    write_table(data, p, "xlsx", sheet_name="华东/华南")
    assert list_sheets(p) == ["华东_华南"]


def test_多张工作表同名时自动避让(tmp_path):
    p = tmp_path / "多表.xlsx"
    write_sheets(p, [
        ("A/B", TableData(header=["x"], rows=[["1"]])),
        ("A_B", TableData(header=["x"], rows=[["2"]])),
    ])
    names = list_sheets(p)
    assert len(names) == 2 and len(set(names)) == 2, f"两张表必须有不同的名字：{names}"


def test_文件类型两处定义不能走散():
    """合并页用 scan.TABLE_SUFFIXES 过滤，其它五页用 workbook.SUPPORTED_SUFFIXES。

    这两个集合必须相等，否则同一个文件夹拖进不同标签页会出现"这里认、那里不认"。
    """
    from filebatch.core.scan import TABLE_SUFFIXES
    from filebatch.core.excel.workbook import SUPPORTED_SUFFIXES

    assert TABLE_SUFFIXES == SUPPORTED_SUFFIXES, (
        f"合并页收 {sorted(TABLE_SUFFIXES)}，其它页收 {sorted(SUPPORTED_SUFFIXES)}"
    )

"""表格概况：界面的列下拉靠它。"""
from filebatch.core.excel.inspect import all_columns, common_columns, inspect_file


def test_读出列名和行数(写xlsx, tmp_path):
    p = 写xlsx(tmp_path / "a.xlsx", [["姓名", "金额"], ["张三", "1"], ["李四", "2"]])
    info = inspect_file(p)
    assert info.ok
    assert info.columns == ["姓名", "金额"]
    assert info.row_count == 2
    assert info.sheets == ["Sheet1"]


def test_坏文件不抛异常而是写进error(tmp_path):
    p = tmp_path / "坏.xlsx"
    p.write_bytes(b"not excel")
    info = inspect_file(p)
    assert not info.ok and info.error


def test_旧xls给出明确提示(tmp_path):
    p = tmp_path / "老.xls"
    p.write_bytes(b"\xd0\xcf\x11\xe0")
    info = inspect_file(p)
    assert not info.ok and "另存为" in info.error


def test_多个文件的共有列(写xlsx, tmp_path):
    a = 写xlsx(tmp_path / "a.xlsx", [["工号", "姓名", "部门"], ["1", "张三", "研发"]])
    b = 写xlsx(tmp_path / "b.xlsx", [["工号", "姓名", "城市"], ["1", "张三", "北京"]])
    infos = [inspect_file(a), inspect_file(b)]

    assert common_columns(infos) == ["工号", "姓名"]
    assert all_columns(infos) == ["工号", "姓名", "部门", "城市"]


def test_有坏文件时共有列只看好的(写xlsx, tmp_path):
    a = 写xlsx(tmp_path / "a.xlsx", [["工号"], ["1"]])
    坏 = tmp_path / "坏.xlsx"
    坏.write_bytes(b"x")
    infos = [inspect_file(a), inspect_file(坏)]
    assert common_columns(infos) == ["工号"]


def test_没有可用文件时返回空():
    assert common_columns([]) == []
    assert all_columns([]) == []


# ---------------- 表头一致性体检 ----------------

def 概况(名: str, 列: list[str] | None = None, 错: str | None = None):
    from pathlib import Path

    from filebatch.core.excel.inspect import SheetInfo

    return SheetInfo(path=Path(名), columns=列 or [], error=错)


def test_全都一致时没有问题():
    from filebatch.core.excel.inspect import check_headers

    infos = [概况("a.xlsx", ["工号", "姓名"]), 概况("b.xlsx", ["工号", "姓名"])]
    r = check_headers(infos, ["工号"])
    assert not r.has_problems
    assert len(r.ok) == 2
    assert r.blocked == []
    assert "没有问题" in r.summary()


def test_缺列的文件会被单独列出来():
    from filebatch.core.excel.inspect import check_headers

    infos = [概况("a.xlsx", ["工号", "姓名"]), 概况("b.xlsx", ["姓名"])]
    r = check_headers(infos, ["工号", "姓名"])

    assert len(r.missing) == 1
    路径, 缺 = r.missing[0]
    assert 路径.name == "b.xlsx" and 缺 == ["工号"]
    assert [p.name for p in r.blocked] == ["b.xlsx"]
    assert any("缺少「工号」" in 行 for 行 in r.describe_lines())


def test_表头不一致但必需列都在仍然会处理():
    from filebatch.core.excel.inspect import check_headers

    infos = [概况("a.xlsx", ["工号", "姓名", "部门"]), 概况("b.xlsx", ["工号", "姓名", "城市"])]
    r = check_headers(infos, ["工号"])

    assert [p.name for p in r.mismatched] == ["b.xlsx"]
    assert r.blocked == [], "表头不一样不是拦截理由，需要的列在就能处理"
    assert any("会照常处理" in 行 for 行 in r.describe_lines())


def test_读不了的文件算进被跳过的那一批():
    from filebatch.core.excel.inspect import check_headers

    infos = [概况("a.xlsx", ["工号"]), 概况("老.xls", 错="旧版 .xls 不支持")]
    r = check_headers(infos, ["工号"])

    assert len(r.unreadable) == 1
    assert [p.name for p in r.blocked] == ["老.xls"]
    assert any("旧版 .xls 不支持" in 行 for 行 in r.describe_lines())


def test_基准是第一个能读的文件():
    from filebatch.core.excel.inspect import check_headers

    infos = [概况("坏.xlsx", 错="读不了"), 概况("b.xlsx", ["工号"]), 概况("c.xlsx", ["单号"])]
    r = check_headers(infos, [])

    assert r.baseline_path.name == "b.xlsx"
    assert r.baseline == ["工号"]
    assert [p.name for p in r.mismatched] == ["c.xlsx"]


def test_不要求特定列时只看表头一不一致():
    from filebatch.core.excel.inspect import check_headers

    infos = [概况("a.xlsx", ["A", "B"]), 概况("b.xlsx", ["A", "C"])]
    r = check_headers(infos, [])

    assert r.missing == [], "没要求列就谈不上缺列"
    assert len(r.mismatched) == 1


def test_例子太多时不会刷屏():
    from filebatch.core.excel.inspect import check_headers

    infos = [概况("好.xlsx", ["工号"])] + [概况(f"坏{i}.xlsx", ["别的"]) for i in range(30)]
    r = check_headers(infos, ["工号"])

    行 = r.describe_lines(max_examples=3)
    assert any("还有 27 个" in x for x in 行), 行
    assert len(行) < 10, "日志不该被几十行刷屏"


def test_全部文件都读不了时的汇总():
    from filebatch.core.excel.inspect import check_headers

    r = check_headers([概况("a.xls", 错="旧版"), 概况("b.xls", 错="旧版")], ["工号"])
    assert r.total == 2
    assert len(r.blocked) == 2
    assert r.baseline == []

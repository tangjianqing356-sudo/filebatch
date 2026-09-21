"""数据清洗。重点是「只做安全的事」。"""
from filebatch.core.excel import clean_job
from filebatch.core.excel.clean_job import CleanOptions, clean_cell, clean_table
from filebatch.core.excel.workbook import TableData, read_table


def _表(header, rows):
    return TableData(header=header, rows=rows)


def test_去首尾空格():
    assert clean_cell("  张三  ", CleanOptions()) == "张三"


def test_合并多余空白():
    assert clean_cell("张三    李四", CleanOptions()) == "张三 李四"


def test_去掉单元格内换行():
    assert clean_cell("第一行\n第二行", CleanOptions()) == "第一行 第二行"
    assert clean_cell("a\r\nb", CleanOptions()) == "a b"


def test_全角空格也算空白():
    assert clean_cell("张三　　李四", CleanOptions()) == "张三 李四"


def test_不做类型转换():
    """这是有意为之：身份证号、前导零、'3-5' 这类值一转就毁。"""
    for 原值 in ["001", "3-5", "1.20", "２０２６", "110101199001011234"]:
        assert clean_cell(原值, CleanOptions()) == 原值


def test_删除空行():
    data = _表(["A"], [["1"], ["  "], ["2"], [""]])
    cleaned, stats = clean_table(data, CleanOptions())
    assert cleaned.rows == [["1"], ["2"]]
    assert stats.blank_rows_removed == 2


def test_删除空列():
    data = _表(["姓名", "", "金额"], [["张三", "", "100"], ["李四", "  ", "200"]])
    cleaned, stats = clean_table(data, CleanOptions(drop_blank_cols=True))
    assert cleaned.header == ["姓名", "金额"]
    assert cleaned.rows == [["张三", "100"], ["李四", "200"]]
    assert stats.blank_cols_removed == 1


def test_有表头的列不会被当成空列删掉():
    """列里没数据但有表头，说明是有意留的字段，不能删。"""
    data = _表(["姓名", "备注"], [["张三", ""], ["李四", ""]])
    cleaned, stats = clean_table(data, CleanOptions(drop_blank_cols=True))
    assert cleaned.header == ["姓名", "备注"]
    assert stats.blank_cols_removed == 0


def test_删除完全重复行():
    data = _表(["A"], [["1"], ["2"], ["1"]])
    cleaned, stats = clean_table(data, CleanOptions(drop_duplicate_rows=True))
    assert cleaned.rows == [["1"], ["2"]]
    assert stats.duplicate_rows_removed == 1


def test_默认不删重复行():
    data = _表(["A"], [["1"], ["1"]])
    cleaned, stats = clean_table(data, CleanOptions())
    assert len(cleaned.rows) == 2
    assert stats.duplicate_rows_removed == 0


def test_表头也会被清洗():
    data = _表(["  姓名  ", "金\n额"], [["张三", "1"]])
    cleaned, _ = clean_table(data, CleanOptions())
    assert cleaned.header == ["姓名", "金 额"]


def test_统计描述是人话():
    data = _表(["A"], [[" 1 "], ["  "], ["2"]])
    _, stats = clean_table(data, CleanOptions())
    desc = stats.describe()
    assert "单元格" in desc and "空行" in desc


def test_参数校验():
    assert "至少要勾选" in (CleanOptions(
        drop_blank_rows=False, drop_blank_cols=False, trim_spaces=False,
        collapse_spaces=False, remove_newlines=False, drop_duplicate_rows=False,
    ).validate() or "")
    assert CleanOptions().validate() is None


def test_没有需要清洗的内容就跳过(写xlsx, tmp_path):
    p = 写xlsx(tmp_path / "干净.xlsx", [["姓名"], ["张三"], ["李四"]])
    actions = clean_job.plan([p], CleanOptions(), tmp_path / "out")
    assert not actions[0].will_run
    assert "没有需要清洗" in actions[0].skip_reason


def test_完整执行(销售表, tmp_path):
    out = tmp_path / "输出"
    opts = CleanOptions()
    report = clean_job.execute(clean_job.plan([销售表], opts, out), opts)

    assert report.succeeded == 1
    结果 = read_table(out / "销售_清洗.xlsx")
    assert all(r != ["", "", ""] for r in 结果.rows), "空行应该没了"
    assert any("王五" == r[0] for r in 结果.rows), "尾随空格应该被去掉"
    assert 销售表.exists(), "原文件必须保留"


def test_计划阶段不写文件(销售表, tmp_path):
    out = tmp_path / "输出"
    clean_job.plan([销售表], CleanOptions(), out)
    assert not out.exists()

"""批量拆表。重点是文件名安全和数量失控防护。"""
from filebatch.core.excel import split_job
from filebatch.core.excel.split_job import (
    EMPTY_GROUP_NAME,
    SplitOptions,
    group_rows,
    make_filename,
)
from filebatch.core.excel.workbook import TableData, read_table


def test_按列分组保持原顺序():
    data = TableData(header=["姓名", "地区"],
                     rows=[["张三", "华东"], ["李四", "华南"], ["王五", "华东"]])
    groups = group_rows(data, "地区")
    assert list(groups.keys()) == ["华东", "华南"]
    assert len(groups["华东"]) == 2


def test_空值单独成组():
    data = TableData(header=["姓名", "地区"], rows=[["张三", ""], ["李四", "  "]])
    groups = group_rows(data, "地区")
    assert list(groups.keys()) == [EMPTY_GROUP_NAME]
    assert len(groups[EMPTY_GROUP_NAME]) == 2


def test_文件名里的非法字符被清掉():
    """列值直接当文件名最危险：斜杠会被当成目录。"""
    name = make_filename("{原名}_{值}", "销售", "华东/华南", ".xlsx")
    assert "/" not in name and "\\" not in name
    assert name.endswith(".xlsx")


def test_各种非法字符都能处理():
    for 值 in ['a/b', 'a\\b', 'a:b', 'a*b', 'a?b', 'a"b', 'a<b', 'a>b', 'a|b']:
        name = make_filename("{值}", "x", 值, ".xlsx")
        assert not (set(name) & set('/\\:*?"<>|')), f"{值} 没清干净：{name}"


def test_超长的列值会被截断():
    name = make_filename("{值}", "x", "很长的名字" * 100, ".xlsx")
    assert len(name) <= 130


def test_全是非法字符时不会变成空文件名():
    name = make_filename("{值}", "x", "///", ".xlsx")
    assert name != ".xlsx" and len(name) > 5


def test_参数校验():
    assert "请选择要按哪一列" in (SplitOptions().validate() or "")
    assert "表头" in (SplitOptions(split_column="地区", has_header=False).validate() or "")
    assert "{值}" in (SplitOptions(split_column="地区", name_template="固定名").validate() or "")
    assert SplitOptions(split_column="地区").validate() is None


def test_完整拆分(销售表, tmp_path):
    out = tmp_path / "输出"
    opts = SplitOptions(split_column="地区")
    actions = split_job.plan([销售表], opts, out)
    assert len(actions) == 3, "华东/华南/华北 三组"
    assert not out.exists(), "计划阶段不写文件"

    report = split_job.execute(actions, opts)
    assert report.succeeded == 3
    名字 = sorted(p.name for p in out.iterdir())
    assert 名字 == ["销售_华东.xlsx", "销售_华北.xlsx", "销售_华南.xlsx"]

    华东 = read_table(out / "销售_华东.xlsx")
    assert 华东.header == ["姓名", "地区", "金额"]
    assert len(华东.rows) == 3
    assert 销售表.exists()


def test_清洗后文件名相撞时自动避让(写xlsx, tmp_path):
    """"A/B" 和 "A_B" 清洗后会变成同一个名字。"""
    p = 写xlsx(tmp_path / "t.xlsx", [["名", "组"], ["1", "A/B"], ["2", "A_B"]])
    out = tmp_path / "输出"
    opts = SplitOptions(split_column="组")
    report = split_job.execute(split_job.plan([p], opts, out), opts)

    assert report.succeeded == 2
    assert len(list(out.iterdir())) == 2, "两组必须落成两个文件，不能互相覆盖"


def test_拆出太多文件会被提前拦住(写xlsx, tmp_path):
    p = 写xlsx(tmp_path / "订单.xlsx",
               [["订单号", "金额"]] + [[f"NO{i:05d}", "1"] for i in range(50)])
    opts = SplitOptions(split_column="订单号", max_files=10)
    actions = split_job.plan([p], opts, tmp_path / "out")

    assert len(actions) == 1 and not actions[0].will_run
    reason = actions[0].skip_reason
    assert "50 个文件" in reason and "上限 10" in reason
    assert "选错了列" in reason, "要提示用户可能是选错列了"


def test_列不存在给可读提示(销售表, tmp_path):
    actions = split_job.plan([销售表], SplitOptions(split_column="不存在"), tmp_path / "out")
    assert not actions[0].will_run
    assert "找不到列" in actions[0].skip_reason
    assert "地区" in actions[0].skip_reason


def test_可以不带表头输出(销售表, tmp_path):
    out = tmp_path / "输出"
    opts = SplitOptions(split_column="地区", keep_header=False)
    split_job.execute(split_job.plan([销售表], opts, out), opts)
    华东 = read_table(out / "销售_华东.xlsx", has_header=False)
    assert 华东.rows[0][0] == "张三", "第一行应该直接是数据"

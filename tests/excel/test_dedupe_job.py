"""Excel 去重。"""
from filebatch.core.excel import dedupe_job
from filebatch.core.excel.dedupe_job import DedupeOptions, KeepMode, dedupe_rows
from filebatch.core.excel.workbook import TableData, read_table


def _表(header, rows):
    return TableData(header=header, rows=rows)


# ---------------- 纯逻辑 ----------------

def test_整行相同才算重复():
    data = _表(["姓名", "地区"], [["张三", "华东"], ["张三", "华北"], ["张三", "华东"]])
    kept, removed = dedupe_rows(data, DedupeOptions())
    assert removed == 1
    assert kept == [["张三", "华东"], ["张三", "华北"]]


def test_按指定列去重():
    data = _表(["姓名", "地区"], [["张三", "华东"], ["张三", "华北"], ["李四", "华南"]])
    kept, removed = dedupe_rows(data, DedupeOptions(key_columns=["姓名"]))
    assert removed == 1
    assert kept == [["张三", "华东"], ["李四", "华南"]]


def test_保留最后一条():
    data = _表(["姓名", "金额"], [["张三", "100"], ["张三", "999"]])
    kept, _ = dedupe_rows(data, DedupeOptions(key_columns=["姓名"], keep=KeepMode.LAST))
    assert kept == [["张三", "999"]]


def test_保留最后一条时位置不变():
    """后来的覆盖先前的，但顺序按第一次出现算，否则用户会觉得行乱了。"""
    data = _表(["姓名", "序"], [["张三", "1"], ["李四", "2"], ["张三", "3"]])
    kept, _ = dedupe_rows(data, DedupeOptions(key_columns=["姓名"], keep=KeepMode.LAST))
    assert kept == [["张三", "3"], ["李四", "2"]]


def test_默认忽略首尾空格():
    data = _表(["姓名"], [["张三"], ["张三 "], [" 张三"]])
    kept, removed = dedupe_rows(data, DedupeOptions(key_columns=["姓名"]))
    assert removed == 2 and len(kept) == 1


def test_可以关掉空格忽略():
    data = _表(["姓名"], [["张三"], ["张三 "]])
    kept, removed = dedupe_rows(data, DedupeOptions(key_columns=["姓名"], trim_spaces=False))
    assert removed == 0 and len(kept) == 2


def test_忽略大小写():
    data = _表(["邮箱"], [["A@x.com"], ["a@X.COM"]])
    kept, removed = dedupe_rows(data, DedupeOptions(key_columns=["邮箱"], ignore_case=True))
    assert removed == 1 and len(kept) == 1


def test_默认区分大小写():
    data = _表(["邮箱"], [["A@x.com"], ["a@x.com"]])
    _, removed = dedupe_rows(data, DedupeOptions(key_columns=["邮箱"]))
    assert removed == 0


def test_空行不参与去重也不输出():
    data = _表(["姓名"], [["张三"], ["  "], [""], ["张三"]])
    kept, removed = dedupe_rows(data, DedupeOptions())
    assert kept == [["张三"]]
    assert removed == 1, "空行不该被算成重复"


def test_多列联合去重():
    data = _表(["姓名", "地区", "金额"],
               [["张三", "华东", "1"], ["张三", "华东", "2"], ["张三", "华北", "3"]])
    kept, removed = dedupe_rows(data, DedupeOptions(key_columns=["姓名", "地区"]))
    assert removed == 1 and len(kept) == 2


def test_参数校验():
    assert "xlsx 或 csv" in (DedupeOptions(output_format="txt").validate() or "")
    assert "表头" in (DedupeOptions(has_header=False, key_columns=["A"]).validate() or "")
    assert DedupeOptions().validate() is None


def test_枚举被Qt退化成字符串也能用():
    """QComboBox.currentData() 会把 str 子类枚举变成普通字符串。"""
    o = DedupeOptions(keep="last")
    assert o.keep is KeepMode.LAST
    assert DedupeOptions(keep="乱写").keep is KeepMode.FIRST


# ---------------- 计划与执行 ----------------

def test_计划阶段只读不写文件(销售表, tmp_path):
    out = tmp_path / "输出"
    actions = dedupe_job.plan([销售表], DedupeOptions(), out)
    assert len(actions) == 1
    assert actions[0].will_run
    assert "1 行重复" in actions[0].note
    assert not out.exists(), "计划阶段绝不能创建输出目录"


def test_没有重复时跳过(写xlsx, tmp_path):
    p = 写xlsx(tmp_path / "干净.xlsx", [["姓名"], ["张三"], ["李四"]])
    actions = dedupe_job.plan([p], DedupeOptions(), tmp_path / "out")
    assert not actions[0].will_run
    assert "没有发现重复行" in actions[0].skip_reason


def test_列不存在时给出可读提示(销售表, tmp_path):
    actions = dedupe_job.plan([销售表], DedupeOptions(key_columns=["不存在的列"]), tmp_path / "out")
    assert not actions[0].will_run
    assert "找不到列" in actions[0].skip_reason
    assert "姓名" in actions[0].skip_reason, "要把实际有哪些列告诉用户"


def test_完整执行并保留原文件(销售表, tmp_path):
    out = tmp_path / "输出"
    opts = DedupeOptions()
    report = dedupe_job.execute(dedupe_job.plan([销售表], opts, out), opts)

    assert report.succeeded == 1 and report.failed == 0
    产物 = list(out.iterdir())
    assert len(产物) == 1 and 产物[0].name == "销售_去重.xlsx"
    结果 = read_table(产物[0])
    assert 结果.header == ["姓名", "地区", "金额"]
    assert len(结果.rows) == 4      # 6 行数据 - 1 重复 - 1 空行
    assert 销售表.exists(), "原文件必须保留"


def test_输出重名自动避让(销售表, tmp_path):
    out = tmp_path / "输出"
    out.mkdir()
    (out / "销售_去重.xlsx").write_bytes(b"original")

    opts = DedupeOptions()
    report = dedupe_job.execute(dedupe_job.plan([销售表], opts, out), opts)
    assert report.succeeded == 1
    assert (out / "销售_去重.xlsx").read_bytes() == b"original", "已有文件绝不能被覆盖"
    assert (out / "销售_去重_1.xlsx").exists()


def test_坏文件被跳过其余照常(销售表, tmp_path):
    坏 = tmp_path / "坏.xlsx"
    坏.write_bytes(b"not excel")
    opts = DedupeOptions()
    report = dedupe_job.execute(dedupe_job.plan([销售表, 坏], opts, tmp_path / "out"), opts)
    assert report.succeeded == 1
    assert len(report.skipped) == 1


def test_中断只停止后续项(写xlsx, tmp_path):
    files = [写xlsx(tmp_path / f"t{i}.xlsx", [["A"], ["1"], ["1"]]) for i in range(5)]
    out = tmp_path / "输出"
    opts = DedupeOptions()
    actions = dedupe_job.plan(files, opts, out)

    已处理 = []
    report = dedupe_job.execute(
        actions, opts,
        on_progress=lambda d, t, n: 已处理.append(n),
        should_cancel=lambda: len(已处理) >= 2,
    )
    assert report.succeeded == 2
    assert len(report.skipped) == 3
    assert all("用户中断" in r for _, r in report.skipped)

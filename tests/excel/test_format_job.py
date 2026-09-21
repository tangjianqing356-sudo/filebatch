"""格式统一。重点是「能力边界要说清楚」。"""
from openpyxl import Workbook, load_workbook
from openpyxl.chart import BarChart, Reference

from filebatch.core.excel import format_job
from filebatch.core.excel.format_job import FormatOptions, column_width
from filebatch.core.excel.inspect import detect_unsupported_features


def test_列宽按内容估算():
    assert column_width(["abc"], 50) >= 5
    # 中文占两个字符宽
    assert column_width(["中文中文"], 50) > column_width(["abcd"], 50)


def test_列宽有上限():
    assert column_width(["很长的内容" * 50], 30) == 30


def test_默认就是不改字体():
    """核心约定：用户没点名要换字体，就一个字节都不动。"""
    opts = FormatOptions()
    assert opts.font_name is None
    assert opts.font_size is None
    assert opts.validate() is None


def test_参数校验():
    assert "字号" in (FormatOptions(font_size=200).validate() or "")
    assert "字体名" in (FormatOptions(font_name="  ").validate() or "")
    assert FormatOptions(font_size=None).validate() is None, "None 表示不改，不该被当成非法字号"
    assert "对齐" in (FormatOptions(body_align="middle").validate() or "")
    assert "表头对齐" in (FormatOptions(header_align="middle").validate() or "")
    assert FormatOptions(body_align=None, header_align=None).validate() is None
    assert "十六进制" in (FormatOptions(header_fill="红色").validate() or "")
    assert "列宽" in (FormatOptions(max_col_width=5).validate() or "")
    assert FormatOptions().validate() is None


def test_CSV被明确拒绝而不是静默处理(写csv, tmp_path):
    p = 写csv(tmp_path / "a.csv", [["A"], ["1"]])
    actions = format_job.plan([p], FormatOptions(), tmp_path / "out")
    assert not actions[0].will_run
    assert "CSV 没有格式" in actions[0].skip_reason


def test_完整格式化(写xlsx, tmp_path):
    p = 写xlsx(tmp_path / "表.xlsx", [["姓名", "金额"], ["张三", 100], ["李四", 200]])
    out = tmp_path / "输出"
    opts = FormatOptions()

    actions = format_job.plan([p], opts, out)
    assert actions[0].will_run
    assert not out.exists(), "计划阶段不写文件"

    report = format_job.execute(actions, opts)
    assert report.succeeded == 1

    wb = load_workbook(out / "表_格式化.xlsx")
    ws = wb.active
    assert ws["A1"].value == "姓名"
    assert ws["A1"].font.bold is True, "表头应该加粗"
    assert ws["A1"].fill.fgColor.rgb.endswith("DDEBF7"), "表头应该有底色"
    assert ws["A2"].border.left.style == "thin", "应该有边框"
    assert ws.freeze_panes == "A2", "表头应该冻结"
    assert ws.column_dimensions["A"].width > 0, "列宽应该被设置"
    assert p.exists(), "原文件必须保留"


def test_可以关掉各项格式(写xlsx, tmp_path):
    p = 写xlsx(tmp_path / "表.xlsx", [["A"], ["1"]])
    out = tmp_path / "输出"
    opts = FormatOptions(header_bold=False, header_fill="", add_borders=False,
                         auto_width=False, freeze_header=False)
    format_job.execute(format_job.plan([p], opts, out), opts)

    ws = load_workbook(out / "表_格式化.xlsx").active
    assert ws["A1"].font.bold is False
    assert ws["A1"].border.left.style is None
    assert ws.freeze_panes is None


# ---- 能力边界：这些东西会丢，必须提前告诉用户 ----

def test_检测出图表(tmp_path):
    p = tmp_path / "带图表.xlsx"
    wb = Workbook()
    ws = wb.active
    for r in [["月份", "销量"], ["一月", 10], ["二月", 20]]:
        ws.append(r)
    chart = BarChart()
    chart.add_data(Reference(ws, min_col=2, min_row=1, max_row=3), titles_from_data=True)
    ws.add_chart(chart, "D2")
    wb.save(p)

    assert "图表" in detect_unsupported_features(p)


def test_检测出条件格式(tmp_path):
    from openpyxl.formatting.rule import CellIsRule
    from openpyxl.styles import PatternFill

    p = tmp_path / "带条件格式.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.append(["值"]); ws.append([5])
    ws.conditional_formatting.add(
        "A2:A10",
        CellIsRule(operator="greaterThan", formula=["3"],
                   fill=PatternFill(start_color="FFC7CE", end_color="FFC7CE", fill_type="solid")),
    )
    wb.save(p)

    assert "条件格式" in detect_unsupported_features(p)


def test_普通表格不会误报(写xlsx, tmp_path):
    p = 写xlsx(tmp_path / "普通.xlsx", [["A"], ["1"]])
    assert detect_unsupported_features(p) == []


def 造带图表(path):
    from openpyxl.chart import BarChart, Reference

    path.parent.mkdir(parents=True, exist_ok=True)
    wb = Workbook()
    ws = wb.active
    for r in [["月份", "销量"], ["一月", 10], ["二月", 20]]:
        ws.append(r)
    chart = BarChart()
    chart.add_data(Reference(ws, min_col=2, min_row=1, max_row=3), titles_from_data=True)
    ws.add_chart(chart, "D2")
    wb.save(path)
    return path


def test_图表现在能活下来(tmp_path):
    """就地刷样式（而不是另建工作簿）之后，图表是保得住的。

    这条测试同时锁住"能力边界的说法必须和实际行为对得上"——
    如果哪天实现又退回重建工作簿，这里会先炸。
    """
    src = 造带图表(tmp_path / "源" / "带图表.xlsx")
    out = tmp_path / "输出"
    opts = FormatOptions()
    report = format_job.execute(format_job.plan([src], opts, out), opts)

    assert report.succeeded == 1
    ws = load_workbook(out / "带图表_格式化.xlsx").active
    assert ws._charts, "图表应该还在"
    assert ws["A1"].font.bold is True, "格式也确实刷上了"


def test_图片和条件格式也能活下来(tmp_path):
    from openpyxl.formatting.rule import CellIsRule
    from openpyxl.styles import PatternFill

    src = tmp_path / "源" / "带条件格式.xlsx"
    src.parent.mkdir(parents=True, exist_ok=True)
    wb = Workbook()
    ws = wb.active
    ws.append(["值"]); ws.append([5]); ws.append([20])
    ws.conditional_formatting.add("A2:A10", CellIsRule(
        operator="greaterThan", formula=["15"],
        fill=PatternFill(start_color="FFC7CE", end_color="FFC7CE", fill_type="solid")))
    wb.save(src)

    out = tmp_path / "输出"
    opts = FormatOptions()
    format_job.execute(format_job.plan([src], opts, out), opts)

    ws = load_workbook(out / "带条件格式_格式化.xlsx").active
    assert list(ws.conditional_formatting), "条件格式应该还在"


def test_图表的提示既不吓人也不打包票(tmp_path):
    """两个方向都要防：

    说"你的图表一定会丢"会把用户吓得不敢用一个多半能用的功能；
    说"一定不丢"同样不负责任——复杂工作簿我们没法保证。
    """
    src = 造带图表(tmp_path / "源" / "带图表.xlsx")
    actions = format_job.plan([src], FormatOptions(), tmp_path / "out")
    note = actions[0].note

    assert actions[0].will_run
    assert "图表" in note
    assert "已验证可保留" in note, note
    assert "兼容性差异" in note, "不能打包票，要说明仍可能有差异"
    assert "一定" not in note and "保证" not in note, f"别做绝对承诺：{note}"
    assert actions[0].payload["lossy"] == [], "图表不属于高风险那一类"


def test_特殊内容的分类():
    from filebatch.core.excel.format_job import classify_features

    高, 留意 = classify_features(["图表", "图片", "数据透视表", "条件格式"])
    assert 高 == ["数据透视表"], "透视表是高风险那一档"
    assert 留意 == ["图表", "图片", "条件格式"], "其余的走「已验证可保留、仍需留意」那一档"

    assert classify_features([]) == ([], [])


def test_高风险内容的提示措辞不打包票(tmp_path, 写xlsx):
    """数据透视表这类只能说"很可能保不住"，也要提醒备份。"""
    from filebatch.core.excel.format_job import LOSSY_HINT, RISKY_HINT

    提示 = LOSSY_HINT.format("数据透视表")
    assert "很可能" in 提示 and "备份" in 提示
    assert "一定" not in 提示

    提示2 = RISKY_HINT.format("图表")
    assert "已验证可保留" in 提示2 and "兼容性差异" in 提示2
    assert "一定" not in 提示2 and "保证" not in 提示2


def test_普通表格不会有任何警告(写xlsx, tmp_path):
    src = 写xlsx(tmp_path / "源" / "普通.xlsx", [["A"], ["1"]])
    actions = format_job.plan([src], FormatOptions(), tmp_path / "out")
    assert "⚠" not in actions[0].note and "ℹ" not in actions[0].note, actions[0].note


def test_xlsm输出仍然是xlsm(写xlsx, tmp_path):
    """存成 .xlsx 会把宏弄没，扩展名必须跟着源文件走。"""
    src = tmp_path / "源" / "带宏.xlsm"
    src.parent.mkdir(parents=True, exist_ok=True)
    wb = Workbook()
    wb.active.append(["A"])
    wb.active.append(["1"])
    wb.save(src)

    actions = format_job.plan([src], FormatOptions(), tmp_path / "out")
    assert actions[0].target.suffix == ".xlsm", actions[0].target.name



# ---------------- 字体：默认保留，明确选了才改 ----------------
#
# 这一组是产品约定，不是实现细节：
# 「格式统一」不该顺手把人家表格里的字体全换掉。

def 写带字体(path, rows, 字体表: dict | None = None, sheet="Sheet1"):
    """rows 照写，字体表 {"A2": ("宋体", 14)} 指定某些单元格的字体。"""
    from openpyxl.styles import Font

    wb = Workbook()
    ws = wb.active
    ws.title = sheet
    for r in rows:
        ws.append(r)
    for 坐标, (名, 号) in (字体表 or {}).items():
        ws[坐标].font = Font(name=名, size=号)
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
    return path


def 跑格式(src, tmp_path, opts):
    out = tmp_path / "输出"
    report = format_job.execute(format_job.plan([src], opts, out), opts)
    assert report.failed == 0, report.summary()
    return load_workbook(out / f"{src.stem}{opts.name_suffix}.xlsx")


def test_默认执行后原字体保持不变(tmp_path):
    src = 写带字体(
        tmp_path / "源" / "表.xlsx",
        [["姓名", "金额"], ["张三", 100]],
        {"A1": ("Times New Roman", 13), "A2": ("宋体", 14), "B2": ("Arial", 9)},
    )
    ws = 跑格式(src, tmp_path, FormatOptions())[ "Sheet1" ]

    assert ws["A2"].font.name == "宋体" and ws["A2"].font.size == 14
    assert ws["B2"].font.name == "Arial" and ws["B2"].font.size == 9
    assert ws["A1"].font.name == "Times New Roman", "表头加粗也不该顺手换字体"
    assert ws["A1"].font.size == 13
    assert ws["A1"].font.bold is True, "加粗是用户要的，这个该改"


def test_同一个工作簿里不同字体默认都能保留(tmp_path):
    """一张表里混着好几种字体是常态，不能被一把抹平。"""
    src = 写带字体(
        tmp_path / "源" / "混排.xlsx",
        [["标题"], ["宋体行"], ["黑体行"], ["Arial 行"], ["等线行"]],
        {"A2": ("宋体", 12), "A3": ("黑体", 16), "A4": ("Arial", 10), "A5": ("等线", 11)},
    )
    ws = 跑格式(src, tmp_path, FormatOptions())["Sheet1"]

    得到 = [(ws[f"A{i}"].font.name, ws[f"A{i}"].font.size) for i in range(2, 6)]
    assert 得到 == [("宋体", 12), ("黑体", 16), ("Arial", 10), ("等线", 11)], 得到


def test_明确选了微软雅黑才统一成微软雅黑(tmp_path):
    src = 写带字体(
        tmp_path / "源" / "表.xlsx",
        [["姓名"], ["张三"], ["李四"]],
        {"A2": ("宋体", 14), "A3": ("Arial", 9)},
    )
    ws = 跑格式(src, tmp_path, FormatOptions(font_name="微软雅黑"))["Sheet1"]

    assert ws["A1"].font.name == "微软雅黑"
    assert ws["A2"].font.name == "微软雅黑"
    assert ws["A3"].font.name == "微软雅黑"
    # 只选了字体没选字号，字号就该保持原样
    assert ws["A2"].font.size == 14 and ws["A3"].font.size == 9


def test_字体和字号可以分开改(tmp_path):
    src = 写带字体(tmp_path / "源" / "表.xlsx", [["A"], ["1"]], {"A2": ("宋体", 14)})

    只改字号 = 跑格式(src, tmp_path, FormatOptions(font_size=11, name_suffix="_只字号"))["Sheet1"]
    assert 只改字号["A2"].font.name == "宋体", "没选字体就不该动字体名"
    assert 只改字号["A2"].font.size == 11

    两个都改 = 跑格式(
        src, tmp_path, FormatOptions(font_name="Arial", font_size=12, name_suffix="_都改")
    )["Sheet1"]
    assert (两个都改["A2"].font.name, 两个都改["A2"].font.size) == ("Arial", 12)


def test_不改字体时其它格式照样生效(tmp_path):
    """"保留原字体"不等于"什么都不做"——边框、列宽、冻结该做还得做。"""
    src = 写带字体(tmp_path / "源" / "表.xlsx", [["姓名", "金额"], ["张三", 100]],
                 {"A2": ("宋体", 14)})
    ws = 跑格式(src, tmp_path, FormatOptions())["Sheet1"]

    assert ws["A2"].font.name == "宋体"
    assert ws["A2"].border.left.style == "thin"
    assert ws.freeze_panes == "A2"
    assert ws.column_dimensions["A"].width > 0
    assert ws["A1"].fill.fgColor.rgb.endswith("DDEBF7")


def test_merged_font在没有要改的东西时返回None():
    """返回 None 是"这个单元格别碰"的信号，不是"用默认字体"。"""
    from openpyxl.styles import Font

    from filebatch.core.excel.format_job import merged_font

    原 = Font(name="宋体", size=14)
    assert merged_font(原, FormatOptions(), 加粗=False) is None

    新 = merged_font(原, FormatOptions(font_name="Arial"), 加粗=False)
    assert 新 is not None and 新.name == "Arial" and 新.size == 14


def test_已经加粗的表头不会被重复改写():
    from openpyxl.styles import Font

    from filebatch.core.excel.format_job import merged_font

    已粗 = Font(name="宋体", size=14, bold=True)
    assert merged_font(已粗, FormatOptions(), 加粗=True) is None


# ---------------- 不重建工作簿带来的另外两个保障 ----------------

def test_多个工作表不会被弄丢(tmp_path):
    """早期实现是"读出值另建一个新工作簿"，那样会只剩一个表。"""
    src = tmp_path / "源" / "多表.xlsx"
    src.parent.mkdir(parents=True, exist_ok=True)
    wb = Workbook()
    ws = wb.active
    ws.title = "一月"
    ws.append(["姓名"]); ws.append(["张三"])
    for 名 in ("二月", "三月"):
        w = wb.create_sheet(名)
        w.append(["姓名"]); w.append(["李四"])
    wb.save(src)

    得到 = 跑格式(src, tmp_path, FormatOptions())
    assert 得到.sheetnames == ["一月", "二月", "三月"], 得到.sheetnames
    assert 得到["三月"]["A1"].font.bold is True, "每个表的表头都要刷到"


def test_数字不会被变成文本(tmp_path):
    """和数据清洗一个道理：格式统一也不该悄悄改数据类型。"""
    from datetime import datetime

    src = tmp_path / "源" / "表.xlsx"
    src.parent.mkdir(parents=True, exist_ok=True)
    wb = Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    ws.append(["编号", "金额", "比例", "日期"])
    ws.append(["001", 1234, 0.35, datetime(2026, 9, 21)])
    wb.save(src)

    ws = 跑格式(src, tmp_path, FormatOptions())["Sheet1"]
    assert ws["A2"].value == "001", "以 0 开头的编号要原样留着"
    assert ws["B2"].value == 1234 and isinstance(ws["B2"].value, int)
    assert ws["C2"].value == 0.35 and isinstance(ws["C2"].value, float)
    assert isinstance(ws["D2"].value, datetime)


def test_数字格式只落在数字上(tmp_path):
    src = tmp_path / "源" / "表.xlsx"
    src.parent.mkdir(parents=True, exist_ok=True)
    wb = Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    ws.append(["编号", "金额"])
    ws.append(["001", 1234])
    wb.save(src)

    ws = 跑格式(src, tmp_path, FormatOptions(number_format="#,##0.00"))["Sheet1"]
    assert ws["B2"].number_format == "#,##0.00"
    assert ws["A2"].number_format != "#,##0.00", "文本列不该被套数字格式"


# ---------------- 对齐：和字体同一套规矩，默认不改 ----------------

def 写带对齐(path, rows, 对齐表: dict):
    """对齐表 {"A2": Alignment(...)}。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    wb = Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    for r in rows:
        ws.append(r)
    for 坐标, 对齐 in 对齐表.items():
        ws[坐标].alignment = 对齐
    wb.save(path)
    return path


def test_默认就是不改对齐():
    opts = FormatOptions()
    assert opts.body_align is None
    assert opts.header_align is None


def test_默认执行后左中右混排的对齐全部不变(tmp_path):
    from openpyxl.styles import Alignment

    src = 写带对齐(
        tmp_path / "源" / "混排.xlsx",
        [["表头"], ["左"], ["中"], ["右"]],
        {
            "A1": Alignment(horizontal="right"),
            "A2": Alignment(horizontal="left"),
            "A3": Alignment(horizontal="center"),
            "A4": Alignment(horizontal="right"),
        },
    )
    ws = 跑格式(src, tmp_path, FormatOptions())["Sheet1"]

    得到 = [ws[f"A{i}"].alignment.horizontal for i in range(1, 5)]
    assert 得到 == ["right", "left", "center", "right"], 得到


def test_只改正文对齐不碰表头(tmp_path):
    from openpyxl.styles import Alignment

    src = 写带对齐(
        tmp_path / "源" / "表.xlsx",
        [["表头"], ["正文1"], ["正文2"]],
        {"A1": Alignment(horizontal="right"),
         "A2": Alignment(horizontal="right"),
         "A3": Alignment(horizontal="right")},
    )
    ws = 跑格式(src, tmp_path, FormatOptions(body_align="center"))["Sheet1"]

    assert ws["A1"].alignment.horizontal == "right", "没设表头对齐就不该动表头"
    assert ws["A2"].alignment.horizontal == "center"
    assert ws["A3"].alignment.horizontal == "center"


def test_只改表头对齐不碰正文(tmp_path):
    from openpyxl.styles import Alignment

    src = 写带对齐(
        tmp_path / "源" / "表.xlsx",
        [["表头"], ["正文"]],
        {"A1": Alignment(horizontal="left"), "A2": Alignment(horizontal="left")},
    )
    ws = 跑格式(src, tmp_path, FormatOptions(header_align="center"))["Sheet1"]

    assert ws["A1"].alignment.horizontal == "center"
    assert ws["A2"].alignment.horizontal == "left", "没设正文对齐就不该动正文"


def test_改对齐不会误伤垂直对齐和自动换行(tmp_path):
    """用户要的是"改水平对齐"，不是"把整个 Alignment 推倒重来"。"""
    from openpyxl.styles import Alignment

    src = 写带对齐(
        tmp_path / "源" / "表.xlsx",
        [["表头"], ["正文"]],
        {"A2": Alignment(horizontal="left", vertical="top", wrap_text=True, indent=2)},
    )
    ws = 跑格式(src, tmp_path, FormatOptions(body_align="right"))["Sheet1"]

    对齐 = ws["A2"].alignment
    assert 对齐.horizontal == "right"
    assert 对齐.vertical == "top", "垂直对齐被动了"
    assert 对齐.wrap_text is True, "自动换行被关掉了"
    assert 对齐.indent == 2, "缩进被清了"


def test_改对齐不会顺手改字体(tmp_path):
    """两件事互不干扰：选了对齐不等于同意换字体。"""
    from openpyxl.styles import Alignment, Font

    src = tmp_path / "源" / "表.xlsx"
    src.parent.mkdir(parents=True, exist_ok=True)
    wb = Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    ws.append(["表头"]); ws.append(["正文"])
    ws["A2"].font = Font(name="宋体", size=14)
    ws["A2"].alignment = Alignment(horizontal="left")
    wb.save(src)

    ws = 跑格式(src, tmp_path, FormatOptions(body_align="center"))["Sheet1"]
    assert ws["A2"].alignment.horizontal == "center"
    assert (ws["A2"].font.name, ws["A2"].font.size) == ("宋体", 14)


def test_改字体不会顺手改对齐(tmp_path):
    from openpyxl.styles import Alignment

    src = 写带对齐(
        tmp_path / "源" / "表.xlsx",
        [["表头"], ["正文"]],
        {"A2": Alignment(horizontal="right", vertical="bottom")},
    )
    ws = 跑格式(src, tmp_path, FormatOptions(font_name="Arial"))["Sheet1"]

    assert ws["A2"].font.name == "Arial"
    assert ws["A2"].alignment.horizontal == "right"
    assert ws["A2"].alignment.vertical == "bottom"


def test_merged_alignment在没有要改的东西时返回None():
    from openpyxl.styles import Alignment

    from filebatch.core.excel.format_job import merged_alignment

    原 = Alignment(horizontal="right", vertical="top", wrap_text=True)
    assert merged_alignment(原, None) is None, "没选对齐 = 别碰"
    assert merged_alignment(原, "right") is None, "已经是这个对齐 = 不用改"

    新 = merged_alignment(原, "center")
    assert 新.horizontal == "center"
    assert 新.vertical == "top" and 新.wrap_text is True


def test_没设过对齐的单元格默认也不会被动(tmp_path, 写xlsx):
    """原本就是"未设置"的单元格，默认跑完还得是"未设置"。"""
    src = 写xlsx(tmp_path / "源" / "表.xlsx", [["表头"], ["正文"]])
    ws = 跑格式(src, tmp_path, FormatOptions())["Sheet1"]

    assert ws["A1"].alignment.horizontal is None
    assert ws["A2"].alignment.horizontal is None


def test_默认参数下其它格式照样生效但对齐和字体不动(tmp_path):
    """默认 = 保守，但不是"什么都不做"。"""
    from openpyxl.styles import Alignment, Font

    src = tmp_path / "源" / "表.xlsx"
    src.parent.mkdir(parents=True, exist_ok=True)
    wb = Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    ws.append(["姓名", "金额"]); ws.append(["张三", 100])
    ws["A2"].font = Font(name="宋体", size=14)
    ws["A2"].alignment = Alignment(horizontal="right")
    wb.save(src)

    ws = 跑格式(src, tmp_path, FormatOptions())["Sheet1"]
    # 不该动的
    assert (ws["A2"].font.name, ws["A2"].font.size) == ("宋体", 14)
    assert ws["A2"].alignment.horizontal == "right"
    # 该做的
    assert ws["A1"].font.bold is True
    assert ws["A1"].fill.fgColor.rgb.endswith("DDEBF7")
    assert ws["A2"].border.left.style == "thin"
    assert ws.freeze_panes == "A2"
    assert ws.column_dimensions["A"].width > 0


def test_全部关掉时不会动任何格式(tmp_path):
    """把所有开关关掉 + 四项都选"保留"，应该一个样式属性都不改。

    这条是防回归的总闸：以后谁再往 _format_sheet 里加一句无条件赋值，
    这里会先炸。
    """
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

    src = tmp_path / "源" / "表.xlsx"
    src.parent.mkdir(parents=True, exist_ok=True)
    wb = Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    ws.append(["表头", "数字"]); ws.append(["正文", 100])
    点 = Side(style="dotted", color="FF0000")
    ws["A2"].font = Font(name="宋体", size=14, italic=True, color="00FF00")
    ws["A2"].alignment = Alignment(horizontal="right", vertical="top", wrap_text=True)
    ws["A2"].border = Border(left=点, right=点)
    ws["A2"].fill = PatternFill("solid", fgColor="FFFF00")
    ws["B2"].number_format = "0.000"
    ws.column_dimensions["A"].width = 33
    wb.save(src)

    全关 = FormatOptions(
        header_bold=False, header_fill="", freeze_header=False,
        font_name=None, font_size=None, body_align=None, header_align=None,
        add_borders=False, auto_width=False, number_format="",
    )
    ws = 跑格式(src, tmp_path, 全关)["Sheet1"]

    assert (ws["A2"].font.name, ws["A2"].font.size) == ("宋体", 14)
    assert ws["A2"].font.italic is True
    assert ws["A2"].alignment.horizontal == "right"
    assert ws["A2"].alignment.vertical == "top"
    assert ws["A2"].alignment.wrap_text is True
    assert ws["A2"].border.left.style == "dotted", "边框被覆盖了"
    assert ws["A2"].fill.fgColor.rgb.endswith("FFFF00"), "填充被覆盖了"
    assert ws["B2"].number_format == "0.000", "数字格式被覆盖了"
    assert ws.column_dimensions["A"].width == 33, "列宽被覆盖了"
    assert ws.freeze_panes is None
    assert ws["A1"].font.bold is False

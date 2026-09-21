"""格式统一：把一批表格的外观整成一致的样子。

只做**稳定的基础格式**：表头、字体、对齐、边框、列宽、数字格式。

**只改用户明确要求改的东西，没要求的一律不动。**
字体、字号、对齐默认都是"保留原设置"——用户没点名要换，我们就不该动。
实现上靠的是：打开原工作簿在上面改样式，而不是读出值另建一个新工作簿。
（早期版本是另建新工作簿，那样做会顺手毁掉三样东西：原字体、
多出来的工作表、以及数字的类型——数字会变成文本。现在都不会了。）

**关于"保留"的准确含义**：指的是"不修改该单元格对应的那个属性"，
不是"文件字节级不变"。openpyxl 打开再保存会重新序列化整个 xlsx
（内部 XML 结构、压缩方式都可能变），这一点没法也不该承诺。

**能力边界**：验收样例里的图表、图片、条件格式、表格对象、宏经过一轮
打开→保存是能保住的，有测试盯着。但 Excel 的对象模型很大，
复杂工作簿仍可能出现兼容性差异——尤其是数据透视表、切片器、
ActiveX / 窗体控件、外部链接和复杂宏工作簿。
计划阶段会检测并在预览里写清楚，让用户自己决定要不要继续，绝不静默处理。
重要文件建议先留备份。
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from ..result import JobReport, PlannedAction
from ..safety import unique_path
from .inspect import detect_unsupported_features
from .runner import plan_unsupported, run_per_file
from .workbook import EXCEL_SUFFIXES, describe_unsupported, read_table

ACTION = "格式统一"

# 改成"打开原文件就地刷样式"之后，验收样例里的图表、图片、条件格式、
# 表格对象经过一轮打开→保存都能保住（tests/excel/test_format_job.py 里有断言）。
# 但这只说明"我们验过的这些样例可以"，不等于任何 Excel 都一定保留——
# 复杂工作簿仍可能有兼容性差异，所以提示措辞不做绝对保证。
#
# 分两档提示：高风险的明确警告，其余的说明"已验证样例可保留，复杂对象可能有差异"。
# 乱喊"你的图表一定会丢"会把用户吓得不敢用一个多半能用的功能，
# 反过来打包票说"一定不丢"同样不负责任。
高风险 = {"数据透视表"}          # openpyxl 支持不完整，很可能保不住
需留意 = {"图表", "图片", "条件格式", "表格对象"}

LOSSY_HINT = "⚠ {} 很可能保不住，openpyxl 对它的支持不完整。请先备份原文件。"
RISKY_HINT = "ℹ {}：验收样例已验证可保留，复杂对象仍可能有兼容性差异，建议执行后核对"


def classify_features(features: list[str]) -> tuple[list[str], list[str]]:
    """把检测到的特殊内容分成"高风险"和"需留意"两类。

    注意措辞：两类都不做绝对保证。前者是"很可能保不住"，
    后者是"验收样例验证过可以，但复杂对象仍可能有差异"。
    """
    高 = [f for f in features if f in 高风险]
    留意 = [f for f in features if f in 需留意]
    return 高, 留意

# 字体 / 字号的默认值是 None，意思是**保留原样**，不是"用某个默认字体"。
# 只有用户在界面上明确挑了一个字体，才会去改单元格的字体名。
#
# 也**不按平台自动切**：同样的参数在 Mac 和 Windows 上必须产出同样的文件。
# Mac 上没装某个字体时 Excel 会自己回退显示，但文件里记的还是用户选的那个。
KEEP_FONT = None            # font_name=None / font_size=None 表示不改

# 界面下拉里给的常用字体，用户也可以直接打别的名字
FONT_CHOICES = ("微软雅黑", "宋体", "黑体", "等线", "Arial", "Calibri", "Times New Roman")

# 对齐和字体一样：None = 保留原对齐，用户主动选了才改。
# 而且只改 horizontal 一项——vertical、自动换行、缩进这些都是单元格原来的样子，
# 用户要的是"改水平对齐"，不是"把整个对齐属性推倒重来"。
ALIGN_CHOICES = ("left", "center", "right")
KEEP_ALIGN = None


@dataclass
class FormatOptions:
    has_header: bool = True
    # 表头
    header_bold: bool = True
    header_fill: str = "DDEBF7"        # 淡蓝，留空表示不填充
    freeze_header: bool = True
    # 正文字体：None = 保留原字体 / 原字号，不做任何改动
    font_name: str | None = None
    font_size: int | None = None
    # None = 保留原对齐，不动这个单元格的 Alignment
    body_align: str | None = None
    header_align: str | None = None
    # 表格
    add_borders: bool = True
    auto_width: bool = True
    max_col_width: int = 50
    number_format: str = ""            # 留空表示不动，例如 "#,##0.00"
    name_suffix: str = "_格式化"

    def validate(self) -> str | None:
        if self.font_name is not None and not self.font_name.strip():
            return "字体名不能是空的；不想改字体请选「保留原字体」"
        if self.font_size is not None and not (6 <= self.font_size <= 72):
            return "字号需要在 6~72 之间"
        for 名, 值 in (("正文", self.body_align), ("表头", self.header_align)):
            if 值 is not None and 值 not in ALIGN_CHOICES:
                return f"{名}对齐只支持 左 / 居中 / 右；不想改请选「保留原对齐」"
        if self.header_fill and len(self.header_fill.strip("#")) not in (6, 8):
            return "表头底色要填 6 位十六进制颜色，例如 DDEBF7"
        if not (10 <= self.max_col_width <= 200):
            return "最大列宽需要在 10~200 之间"
        return None


def column_width(values: list[str], max_width: int) -> float:
    """按内容估列宽。中文字符占两个字符宽。"""
    最宽 = 0
    for v in values:
        s = str(v)
        宽 = sum(2 if ord(ch) > 0x2E80 else 1 for ch in s)
        最宽 = max(最宽, 宽)
    return min(max(最宽 + 2, 8), max_width)


def plan(files: list[Path], options: FormatOptions, output_dir: Path) -> list[PlannedAction]:
    actions: list[PlannedAction] = []
    taken: set[Path] = set()

    for src in files:
        问题 = describe_unsupported(src)
        if 问题:
            actions.append(plan_unsupported(src, ACTION, 问题))
            continue
        if src.suffix.lower() not in EXCEL_SUFFIXES:
            actions.append(plan_unsupported(
                src, ACTION, "格式统一只能处理 .xlsx / .xlsm；CSV 没有格式可言，请先转成 Excel"
            ))
            continue
        try:
            data = read_table(src, options.has_header)
            if not data.rows and not data.header:
                actions.append(plan_unsupported(src, ACTION, "表格是空的"))
                continue

            # 扩展名跟着源文件走：.xlsm 存成 .xlsx 会把宏弄没
            raw = output_dir / f"{src.stem}{options.name_suffix}{src.suffix.lower()}"
            target = unique_path(raw, taken)
            taken.add(target)

            note = f"{data.row_count} 行 × {len(data.header) or data.col_count} 列"
            丢失, 风险 = classify_features(detect_unsupported_features(src))
            if 丢失:
                note += "；" + LOSSY_HINT.format("、".join(丢失))
            if 风险:
                note += "；" + RISKY_HINT.format("、".join(风险))
            if target.name != raw.name:
                note += f"；目标重名，自动改为 {target.name}"

            actions.append(PlannedAction(src, target, ACTION, note,
                                         payload={"lossy": 丢失}))
        except ValueError as e:
            actions.append(plan_unsupported(src, ACTION, str(e)))
        except Exception as e:
            actions.append(plan_unsupported(src, ACTION, f"读取失败：{type(e).__name__} {e}"))

    return actions


def merged_font(原字体, options: FormatOptions, 加粗: bool):
    """在单元格**原来的**字体上，只改用户明确指定的那几项。

    返回 None 表示这个单元格的字体属性一项都不用改——
    调用方就不去给它赋值，而不是"重新写一遍同样的值"。
    """
    from copy import copy

    要改: dict = {}
    if options.font_name is not None:
        要改["name"] = options.font_name
    if options.font_size is not None:
        要改["size"] = options.font_size
    if 加粗 and not 原字体.bold:
        要改["bold"] = True
    if not 要改:
        return None

    新 = copy(原字体)
    for 名, 值 in 要改.items():
        setattr(新, 名, 值)
    return 新


def merged_alignment(原对齐, horizontal: str | None):
    """在单元格**原来的**对齐上，只改水平对齐这一项。

    返回 None 表示这个单元格的对齐一点都不用动。
    和字体一样：用户没选对齐方式，就不该顺手把人家的垂直居中、
    自动换行、缩进这些设置抹掉。
    """
    from copy import copy

    if horizontal is None or 原对齐.horizontal == horizontal:
        return None
    新 = copy(原对齐)
    新.horizontal = horizontal
    return 新


def _sheet_column_widths(ws, options: FormatOptions) -> dict[int, float]:
    """按每一列的实际内容估宽。"""
    列值: dict[int, list[str]] = {}
    for row in ws.iter_rows():
        for cell in row:
            if cell.value is None:
                continue
            列值.setdefault(cell.column, []).append(str(cell.value))
    return {
        col: column_width(值, options.max_col_width)
        for col, 值 in 列值.items()
    }


def _format_sheet(ws, options: FormatOptions) -> int:
    """给一个工作表刷样式，返回处理了多少行。就地改，不重建。"""
    from openpyxl.styles import Border, PatternFill, Side
    from openpyxl.utils import get_column_letter

    细线 = Side(style="thin", color="D0D0D0")
    边框 = Border(left=细线, right=细线, top=细线, bottom=细线)
    填充 = (PatternFill("solid", fgColor=options.header_fill.strip("#").upper())
            if options.header_fill else None)

    行数 = 0
    for row in ws.iter_rows():
        行数 += 1
        是表头 = options.has_header and row and row[0].row == 1
        for cell in row:
            新字体 = merged_font(cell.font, options, 加粗=bool(是表头 and options.header_bold))
            if 新字体 is not None:
                cell.font = 新字体
            新对齐 = merged_alignment(
                cell.alignment, options.header_align if 是表头 else options.body_align
            )
            if 新对齐 is not None:
                cell.alignment = 新对齐
            if options.add_borders:
                cell.border = 边框
            if 是表头 and 填充 is not None:
                cell.fill = 填充
            elif (options.number_format and not 是表头
                  and isinstance(cell.value, (int, float))
                  and not isinstance(cell.value, bool)):
                cell.number_format = options.number_format

    if options.auto_width:
        for col, 宽 in _sheet_column_widths(ws, options).items():
            ws.column_dimensions[get_column_letter(col)].width = 宽

    if options.freeze_header and options.has_header and 行数:
        ws.freeze_panes = "A2"

    return 行数


def _apply_format(src: Path, target: Path, options: FormatOptions) -> str:
    """打开原工作簿、在上面改样式、另存为新文件。

    关键是**不重建**：值、类型、工作表数量、以及用户没要求改的那些属性
    都不去动它。原文件本身不做任何修改，改的是另存出去的那一份。

    注意"不动"指的是不修改对应的属性，不是文件字节级不变——
    openpyxl 保存时会重新序列化整个 xlsx，这没法承诺。
    """
    from openpyxl import load_workbook

    # .xlsm 必须带上 keep_vba，否则另存出来的文件里宏就没了
    wb = load_workbook(src, keep_vba=src.suffix.lower() == ".xlsm")
    try:
        总行 = sum(_format_sheet(ws, options) for ws in wb.worksheets)
        表数 = len(wb.worksheets)
        target.parent.mkdir(parents=True, exist_ok=True)
        wb.save(target)
    finally:
        wb.close()

    数据行 = max(总行 - (表数 if options.has_header else 0), 0)
    if 表数 > 1:
        return f"{表数} 个工作表、共 {数据行} 行已统一格式"
    return f"{数据行} 行已统一格式"


def execute(
    actions: list[PlannedAction],
    options: FormatOptions,
    on_progress: Callable[[int, int, str], None] | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> JobReport:
    def handle(act: PlannedAction) -> str:
        assert act.target is not None
        note = _apply_format(act.source, act.target, options)
        丢失 = act.payload.get("lossy") or []
        if 丢失:
            note += f"（已丢失：{'、'.join(丢失)}）"
        return note

    return run_per_file(actions, "格式统一", handle, on_progress, should_cancel)

"""批量拆表：按某一列的值把一张表拆成多个文件。

三个容易出事的地方专门处理了：
  1. 列里的值直接拿来当文件名——"华东/华南"里的斜杠会变成目录，必须清洗；
  2. 清洗之后不同的值可能撞成同一个文件名（"A/B" 和 "A_B"），要避让；
  3. 一不小心按"订单号"拆，能拆出几万个文件，必须有上限并提前拦住。
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from ..naming import sanitize_filename
from ..result import JobReport, PlannedAction
from ..safety import unique_path
from .runner import plan_unsupported, run_per_file
from .workbook import (
    TableData,
    describe_unsupported,
    is_blank_row,
    read_table,
    write_table,
)

ACTION = "拆表"

# 拆出这么多个文件就不让继续了：多半是选错了列
DEFAULT_MAX_FILES = 200
HARD_MAX_FILES = 2000

EMPTY_GROUP_NAME = "（空值）"


@dataclass
class SplitOptions:
    split_column: str = ""
    has_header: bool = True
    output_format: str = "xlsx"
    keep_header: bool = True          # 每个小表都带上表头
    max_files: int = DEFAULT_MAX_FILES
    name_template: str = "{原名}_{值}"

    def validate(self) -> str | None:
        if not self.split_column.strip():
            return "请选择要按哪一列拆分"
        if not self.has_header:
            return "按列拆分需要表格有表头，请勾选「第一行是表头」"
        if self.output_format not in ("xlsx", "csv"):
            return "输出格式只支持 xlsx 或 csv"
        if not (1 <= self.max_files <= HARD_MAX_FILES):
            return f"文件数上限需要在 1~{HARD_MAX_FILES} 之间"
        if "{值}" not in self.name_template:
            return "文件名模板里必须包含 {值}，否则拆出来的文件会重名"
        return None


def group_rows(data: TableData, column: str) -> dict[str, list[list[str]]]:
    """按列值分组。纯函数，保持原始顺序（Python 的 dict 有序）。"""
    groups: dict[str, list[list[str]]] = {}
    for row in data.rows:
        if is_blank_row(row):
            continue
        值 = str(data.value(row, column)).strip() or EMPTY_GROUP_NAME
        groups.setdefault(值, []).append(row)
    return groups


# 单个文件名的两道上限，取较严的那个：
#   · 字符数：Windows / macOS 按字符算，255 是硬上限，留足余量到 120，文件名才好认
#   · 字节数：Linux（ext4）和很多网络共享按 UTF-8 字节算，同样是 255。
#     一个中文字占 3 字节，120 个中文就是 360 字节，已经超了——
#     所以光截字符数不够，必须再按字节截一次。
MAX_NAME_CHARS = 120
MAX_NAME_BYTES = 180        # 余下的留给扩展名和防重名的 _1 _2 后缀


def _truncate(名字: str) -> str:
    """按字符数和 UTF-8 字节数双重截断，且不切坏多字节字符。"""
    名字 = 名字[:MAX_NAME_CHARS]
    while len(名字.encode("utf-8")) > MAX_NAME_BYTES:
        名字 = 名字[:-1]
    return 名字


def make_filename(template: str, 原名: str, 值: str, ext: str) -> str:
    """把分组值变成安全的文件名。"""
    名字 = template.replace("{原名}", 原名).replace("{值}", 值)
    名字 = sanitize_filename(名字)
    名字 = _truncate(名字)
    # 截断后可能又冒出结尾的点或空格（Windows 会悄悄吃掉），再清一次
    名字 = sanitize_filename(名字)
    return f"{名字}{ext}"


def plan(files: list[Path], options: SplitOptions, output_dir: Path) -> list[PlannedAction]:
    """一个源文件会拆出多条计划，每条对应一个输出文件。"""
    actions: list[PlannedAction] = []
    taken: set[Path] = set()
    ext = ".csv" if options.output_format == "csv" else ".xlsx"

    for src in files:
        问题 = describe_unsupported(src)
        if 问题:
            actions.append(plan_unsupported(src, ACTION, 问题))
            continue
        try:
            data = read_table(src, options.has_header)
            if not data.rows:
                actions.append(plan_unsupported(src, ACTION, "表格里没有数据行"))
                continue
            if data.column_index(options.split_column) is None:
                actions.append(plan_unsupported(
                    src, ACTION,
                    f"找不到列「{options.split_column}」（该表的列是：{'、'.join(data.header) or '无表头'}）"
                ))
                continue

            groups = group_rows(data, options.split_column)
            if not groups:
                actions.append(plan_unsupported(src, ACTION, "没有可拆分的数据"))
                continue
            if len(groups) > options.max_files:
                actions.append(plan_unsupported(
                    src, ACTION,
                    f"按「{options.split_column}」会拆出 {len(groups)} 个文件，"
                    f"超过上限 {options.max_files}。多半是选错了列——"
                    f"请换一个取值较少的列，或在高级选项里调高上限。"
                ))
                continue

            for 值, rows in groups.items():
                raw = output_dir / make_filename(options.name_template, src.stem, 值, ext)
                target = unique_path(raw, taken)
                taken.add(target)
                note = f"「{值}」共 {len(rows)} 行"
                if target.name != raw.name:
                    note += f"；文件名冲突，自动改为 {target.name}"
                actions.append(PlannedAction(
                    src, target, ACTION, note,
                    payload={"group": 值, "rows": len(rows)},
                ))
        except ValueError as e:
            actions.append(plan_unsupported(src, ACTION, str(e)))
        except Exception as e:
            actions.append(plan_unsupported(src, ACTION, f"读取失败：{type(e).__name__} {e}"))

    return actions


def execute(
    actions: list[PlannedAction],
    options: SplitOptions,
    on_progress: Callable[[int, int, str], None] | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> JobReport:
    # 同一个源文件会被拆成很多条计划，读一次缓存起来，别重复读盘
    cache: dict[Path, dict[str, list[list[str]]]] = {}
    headers: dict[Path, list[str]] = {}

    def handle(act: PlannedAction) -> str:
        assert act.target is not None
        if act.source not in cache:
            data = read_table(act.source, options.has_header)
            cache[act.source] = group_rows(data, options.split_column)
            headers[act.source] = data.header

        值 = act.payload.get("group")
        if 值 is None:
            raise ValueError("内部错误：计划里缺少分组信息")
        rows = cache[act.source].get(值)
        if rows is None:
            raise ValueError(f"源文件里已经找不到分组「{值}」，可能在处理过程中被改动")

        write_table(
            TableData(
                header=headers[act.source] if options.keep_header else [],
                rows=rows, source=act.source,
            ),
            act.target, options.output_format, str(值),   # 工作表名由 write_table 统一清洗
        )
        return f"「{值}」{len(rows)} 行"

    return run_per_file(actions, "批量拆表", handle, on_progress, should_cancel)

"""数据清洗：只做安全、可预期的整理。

刻意**不做**类型转换（文本转数字、猜日期格式之类）。
那类操作看着聪明，实际最容易悄悄改坏数据：
身份证号会被转成科学计数法、"001" 会变成 1、"3-5" 会被当成日期。
这一版只做"删掉明显是脏数据的东西"和"把空白规整一下"。
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

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

ACTION = "数据清洗"

_多余空白 = re.compile(r"[ \t　]{2,}")
_换行 = re.compile(r"[\r\n]+")


@dataclass
class CleanOptions:
    has_header: bool = True
    drop_blank_rows: bool = True       # 删除整行都是空的
    drop_blank_cols: bool = False      # 删除整列都是空的
    trim_spaces: bool = True           # 去掉每个单元格的首尾空格
    collapse_spaces: bool = True       # 中间连续多个空格并成一个
    remove_newlines: bool = True       # 单元格里的换行换成空格
    drop_duplicate_rows: bool = False  # 整行完全相同的只留一条
    output_format: str = "xlsx"
    name_suffix: str = "_清洗"

    def validate(self) -> str | None:
        if self.output_format not in ("xlsx", "csv"):
            return "输出格式只支持 xlsx 或 csv"
        if not any([
            self.drop_blank_rows, self.drop_blank_cols, self.trim_spaces,
            self.collapse_spaces, self.remove_newlines, self.drop_duplicate_rows,
        ]):
            return "至少要勾选一项清洗内容"
        return None


def clean_cell(value: str, options: CleanOptions) -> str:
    """清洗一个单元格。纯函数，好测。"""
    v = str(value)
    if options.remove_newlines:
        v = _换行.sub(" ", v)
    if options.collapse_spaces:
        v = _多余空白.sub(" ", v)
    if options.trim_spaces:
        v = v.strip()
    return v


@dataclass
class CleanStats:
    cells_changed: int = 0
    blank_rows_removed: int = 0
    blank_cols_removed: int = 0
    duplicate_rows_removed: int = 0

    @property
    def total_changes(self) -> int:
        return (self.cells_changed + self.blank_rows_removed
                + self.blank_cols_removed + self.duplicate_rows_removed)

    def describe(self) -> str:
        部分 = []
        if self.cells_changed:
            部分.append(f"整理 {self.cells_changed} 个单元格")
        if self.blank_rows_removed:
            部分.append(f"删除 {self.blank_rows_removed} 个空行")
        if self.blank_cols_removed:
            部分.append(f"删除 {self.blank_cols_removed} 个空列")
        if self.duplicate_rows_removed:
            部分.append(f"删除 {self.duplicate_rows_removed} 个重复行")
        return "，".join(部分) or "没有需要清洗的内容"


def clean_table(data: TableData, options: CleanOptions) -> tuple[TableData, CleanStats]:
    """清洗整张表。纯函数，不碰文件。"""
    stats = CleanStats()
    需要整理单元格 = options.trim_spaces or options.collapse_spaces or options.remove_newlines

    def 处理一行(row: list[str]) -> list[str]:
        if not 需要整理单元格:
            return list(row)
        新行 = []
        for cell in row:
            新值 = clean_cell(cell, options)
            if 新值 != str(cell):
                stats.cells_changed += 1
            新行.append(新值)
        return 新行

    header = 处理一行(data.header) if data.header else []
    rows = [处理一行(r) for r in data.rows]

    if options.drop_blank_rows:
        保留 = [r for r in rows if not is_blank_row(r)]
        stats.blank_rows_removed = len(rows) - len(保留)
        rows = 保留

    if options.drop_duplicate_rows:
        seen: set[tuple] = set()
        保留 = []
        for r in rows:
            key = tuple(r)
            if key in seen:
                continue
            seen.add(key)
            保留.append(r)
        stats.duplicate_rows_removed = len(rows) - len(保留)
        rows = 保留

    if options.drop_blank_cols:
        宽度 = max([len(header)] + [len(r) for r in rows], default=0)
        空列 = []
        for i in range(宽度):
            头空 = i >= len(header) or not str(header[i]).strip()
            列空 = all(i >= len(r) or not str(r[i]).strip() for r in rows)
            if 头空 and 列空:
                空列.append(i)
        if 空列:
            保留列 = [i for i in range(宽度) if i not in set(空列)]
            header = [header[i] for i in 保留列 if i < len(header)]
            rows = [[r[i] if i < len(r) else "" for i in 保留列] for r in rows]
            stats.blank_cols_removed = len(空列)

    return TableData(header=header, rows=rows, source=data.source, sheet=data.sheet), stats


def plan(files: list[Path], options: CleanOptions, output_dir: Path) -> list[PlannedAction]:
    actions: list[PlannedAction] = []
    taken: set[Path] = set()

    for src in files:
        问题 = describe_unsupported(src)
        if 问题:
            actions.append(plan_unsupported(src, ACTION, 问题))
            continue
        try:
            data = read_table(src, options.has_header)
            if not data.rows and not data.header:
                actions.append(plan_unsupported(src, ACTION, "表格是空的"))
                continue

            _, stats = clean_table(data, options)
            if stats.total_changes == 0:
                actions.append(plan_unsupported(src, ACTION, "没有需要清洗的内容"))
                continue

            ext = ".csv" if options.output_format == "csv" else ".xlsx"
            raw = output_dir / f"{src.stem}{options.name_suffix}{ext}"
            target = unique_path(raw, taken)
            taken.add(target)

            note = stats.describe()
            if target.name != raw.name:
                note += f"；目标重名，自动改为 {target.name}"
            actions.append(PlannedAction(src, target, ACTION, note))
        except ValueError as e:
            actions.append(plan_unsupported(src, ACTION, str(e)))
        except Exception as e:
            actions.append(plan_unsupported(src, ACTION, f"读取失败：{type(e).__name__} {e}"))

    return actions


def execute(
    actions: list[PlannedAction],
    options: CleanOptions,
    on_progress: Callable[[int, int, str], None] | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> JobReport:
    def handle(act: PlannedAction) -> str:
        assert act.target is not None
        data = read_table(act.source, options.has_header)
        cleaned, stats = clean_table(data, options)
        write_table(cleaned, act.target, options.output_format, "清洗结果")
        return stats.describe()

    return run_per_file(actions, "数据清洗", handle, on_progress, should_cancel)

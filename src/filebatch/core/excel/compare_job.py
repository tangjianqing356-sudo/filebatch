"""两表对比：按关键列匹配，输出仅 A、仅 B、内容不同和汇总。

和其它功能不一样的地方：它要的是**正好两个文件**，而且顺序有意义
（列表里第一个是 A、第二个是 B），所以参数校验要单独把这件事说清楚。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from ..result import JobReport, PlannedAction
from ..safety import unique_path
from .runner import run_per_file
from .workbook import (
    TableData,
    describe_unsupported,
    is_blank_row,
    read_table,
    write_sheets,
)

ACTION = "两表对比"

SHEET_ONLY_A = "仅A表有"
SHEET_ONLY_B = "仅B表有"
SHEET_DIFF = "内容不同"
SHEET_SUMMARY = "汇总"


@dataclass
class CompareOptions:
    key_columns: list[str] = field(default_factory=list)
    has_header: bool = True
    ignore_case: bool = False
    trim_spaces: bool = True
    # 留空表示"除关键列外的所有共有列都比"
    compare_columns: list[str] = field(default_factory=list)

    def validate(self) -> str | None:
        if not self.has_header:
            return "两表对比需要表格有表头，请勾选「第一行是表头」"
        if not self.key_columns:
            return "请至少选择一个关键列，用来确定两张表里哪两行是同一条记录"
        return None


@dataclass
class CompareResult:
    only_a: list[list[str]] = field(default_factory=list)
    only_b: list[list[str]] = field(default_factory=list)
    diff_rows: list[list[str]] = field(default_factory=list)
    diff_header: list[str] = field(default_factory=list)
    same_count: int = 0
    duplicate_keys_a: int = 0
    duplicate_keys_b: int = 0

    def summary_rows(self, a_name: str, b_name: str) -> list[list[str]]:
        return [
            ["A 表", a_name],
            ["B 表", b_name],
            ["仅 A 表有", str(len(self.only_a))],
            ["仅 B 表有", str(len(self.only_b))],
            ["内容不同", str(len(self.diff_rows))],
            ["完全相同", str(self.same_count)],
            ["A 表中关键列重复的行", str(self.duplicate_keys_a)],
            ["B 表中关键列重复的行", str(self.duplicate_keys_b)],
        ]


def _norm(value: str, options: CompareOptions) -> str:
    v = str(value)
    if options.trim_spaces:
        v = v.strip()
    if options.ignore_case:
        v = v.lower()
    return v


def _index_by_key(data: TableData, options: CompareOptions) -> tuple[dict[tuple, list[str]], int]:
    """按关键列建索引。返回 (索引, 关键列重复的行数)。

    关键列重复时保留第一条并计数——静默丢掉会让用户以为数据没了。
    """
    index: dict[tuple, list[str]] = {}
    重复 = 0
    for row in data.rows:
        if is_blank_row(row):
            continue
        key = tuple(_norm(data.value(row, c), options) for c in options.key_columns)
        if key in index:
            重复 += 1
            continue
        index[key] = row
    return index, 重复


def compare_tables(a: TableData, b: TableData, options: CompareOptions) -> CompareResult:
    """核心比对。纯函数，不碰文件。"""
    result = CompareResult()

    index_a, result.duplicate_keys_a = _index_by_key(a, options)
    index_b, result.duplicate_keys_b = _index_by_key(b, options)

    # 要比哪些列：没指定就比两张表共有的、且不是关键列的那些
    if options.compare_columns:
        待比列 = [c for c in options.compare_columns
                  if a.column_index(c) is not None and b.column_index(c) is not None]
    else:
        待比列 = [c for c in a.header
                  if c in b.header and c not in options.key_columns]

    result.diff_header = list(options.key_columns) + ["差异列", "A 表的值", "B 表的值"]

    for key, row_a in index_a.items():
        row_b = index_b.get(key)
        if row_b is None:
            result.only_a.append(row_a)
            continue

        差异 = [
            (col, a.value(row_a, col), b.value(row_b, col))
            for col in 待比列
            if _norm(a.value(row_a, col), options) != _norm(b.value(row_b, col), options)
        ]
        if not 差异:
            result.same_count += 1
            continue
        for col, va, vb in 差异:
            result.diff_rows.append(list(key) + [col, va, vb])

    for key, row_b in index_b.items():
        if key not in index_a:
            result.only_b.append(row_b)

    return result


def plan(files: list[Path], options: CompareOptions, output_file: Path) -> list[PlannedAction]:
    """对比的计划只有一条：两张表 → 一个结果文件。"""
    if len(files) != 2:
        return [PlannedAction(
            files[0] if files else Path("（未选择）"), None, ACTION,
            skip_reason=f"两表对比需要正好 2 个文件，当前选了 {len(files)} 个。"
                        f"列表里第一个是 A 表，第二个是 B 表。",
        )]

    a_path, b_path = files
    for p in (a_path, b_path):
        问题 = describe_unsupported(p)
        if 问题:
            return [PlannedAction(p, None, ACTION, skip_reason=问题)]

    try:
        a = read_table(a_path, options.has_header)
        b = read_table(b_path, options.has_header)
    except ValueError as e:
        return [PlannedAction(a_path, None, ACTION, skip_reason=str(e))]

    缺 = [c for c in options.key_columns if a.column_index(c) is None]
    if 缺:
        return [PlannedAction(a_path, None, ACTION,
                              skip_reason=f"A 表里找不到关键列：{'、'.join(缺)}（A 表的列：{'、'.join(a.header)}）")]
    缺 = [c for c in options.key_columns if b.column_index(c) is None]
    if 缺:
        return [PlannedAction(b_path, None, ACTION,
                              skip_reason=f"B 表里找不到关键列：{'、'.join(缺)}（B 表的列：{'、'.join(b.header)}）")]

    result = compare_tables(a, b, options)
    note = (f"仅A表 {len(result.only_a)} 行，仅B表 {len(result.only_b)} 行，"
            f"内容不同 {len(result.diff_rows)} 处，完全相同 {result.same_count} 行")
    if result.duplicate_keys_a or result.duplicate_keys_b:
        note += f"；关键列有重复（A {result.duplicate_keys_a} / B {result.duplicate_keys_b} 行，只取第一条）"

    return [PlannedAction(a_path, output_file, ACTION, note,
                          payload={"b": str(b_path)})]


def execute(
    actions: list[PlannedAction],
    options: CompareOptions,
    output_file: Path,
    on_progress: Callable[[int, int, str], None] | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> JobReport:
    写入的路径: list[Path] = []

    def handle(act: PlannedAction) -> str:
        b_path = Path(act.payload["b"])
        a = read_table(act.source, options.has_header)
        b = read_table(b_path, options.has_header)
        result = compare_tables(a, b, options)

        final = unique_path(output_file)
        写入的路径.append(final)
        write_sheets(final, [
            (SHEET_SUMMARY, TableData(header=["项目", "数值"],
                                      rows=result.summary_rows(act.source.name, b_path.name))),
            (SHEET_ONLY_A, TableData(header=a.header, rows=result.only_a)),
            (SHEET_ONLY_B, TableData(header=b.header, rows=result.only_b)),
            (SHEET_DIFF, TableData(header=result.diff_header, rows=result.diff_rows)),
        ])
        return (f"仅A表 {len(result.only_a)}，仅B表 {len(result.only_b)}，"
                f"不同 {len(result.diff_rows)}，相同 {result.same_count} → {final.name}")

    report = run_per_file(actions, "两表对比", handle, on_progress, should_cancel)
    # 实际写入的文件名可能因为防覆盖改过，回填给结果
    if 写入的路径:
        for item in report.items:
            if item.ok:
                item.target = 写入的路径[0]
    return report

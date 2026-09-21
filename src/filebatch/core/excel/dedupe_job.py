"""Excel 去重：按指定列去掉重复行。"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
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

ACTION = "去重"


class KeepMode(str, Enum):
    FIRST = "first"   # 重复的保留第一条
    LAST = "last"     # 重复的保留最后一条


@dataclass
class DedupeOptions:
    has_header: bool = True
    # 留空表示"整行完全相同才算重复"
    key_columns: list[str] = field(default_factory=list)
    keep: KeepMode = KeepMode.FIRST
    ignore_case: bool = False
    trim_spaces: bool = True      # 比较前去掉首尾空格，"张三 " 和 "张三" 算同一个
    output_format: str = "xlsx"
    name_suffix: str = "_去重"

    def __post_init__(self) -> None:
        # Qt 的 currentData() 会把 str 子类枚举退化成普通字符串
        if not isinstance(self.keep, KeepMode):
            try:
                self.keep = KeepMode(self.keep)
            except ValueError:
                self.keep = KeepMode.FIRST

    def validate(self) -> str | None:
        if self.output_format not in ("xlsx", "csv"):
            return "输出格式只支持 xlsx 或 csv"
        if self.key_columns and not self.has_header:
            return "按列去重需要表格有表头，请勾选「第一行是表头」"
        return None


def _normalize(value: str, options: DedupeOptions) -> str:
    v = str(value)
    if options.trim_spaces:
        v = v.strip()
    if options.ignore_case:
        v = v.lower()
    return v


def build_key(data: TableData, row: list[str], options: DedupeOptions) -> tuple:
    """算出这一行的去重键。纯函数，好测。"""
    if not options.key_columns:
        return tuple(_normalize(c, options) for c in row)
    return tuple(_normalize(data.value(row, col), options) for col in options.key_columns)


def dedupe_rows(data: TableData, options: DedupeOptions) -> tuple[list[list[str]], int]:
    """返回 (去重后的行, 被删掉的行数)。纯函数。"""
    seen: dict[tuple, int] = {}
    kept: list[list[str]] = []

    for row in data.rows:
        if is_blank_row(row):
            continue
        key = build_key(data, row, options)
        if key in seen:
            if options.keep is KeepMode.LAST:
                kept[seen[key]] = row     # 后来的覆盖先前的，位置不变
            continue
        seen[key] = len(kept)
        kept.append(row)

    有效行数 = sum(1 for r in data.rows if not is_blank_row(r))
    return kept, 有效行数 - len(kept)


def missing_columns(data: TableData, options: DedupeOptions) -> list[str]:
    return [c for c in options.key_columns if data.column_index(c) is None]


def plan(files: list[Path], options: DedupeOptions, output_dir: Path) -> list[PlannedAction]:
    """只读：读表、算出会删多少行，不写任何文件。"""
    actions: list[PlannedAction] = []
    taken: set[Path] = set()

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

            缺列 = missing_columns(data, options)
            if 缺列:
                actions.append(plan_unsupported(
                    src, ACTION, f"找不到列：{'、'.join(缺列)}（该表的列是：{'、'.join(data.header) or '无表头'}）"
                ))
                continue

            kept, removed = dedupe_rows(data, options)
            if removed == 0:
                actions.append(plan_unsupported(src, ACTION, "没有发现重复行，无需处理"))
                continue

            ext = ".csv" if options.output_format == "csv" else ".xlsx"
            raw = output_dir / f"{src.stem}{options.name_suffix}{ext}"
            target = unique_path(raw, taken)
            taken.add(target)

            依据 = "整行相同" if not options.key_columns else f"按列 {'、'.join(options.key_columns)}"
            note = f"{依据}，发现 {removed} 行重复，去重后剩 {len(kept)} 行"
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
    options: DedupeOptions,
    on_progress: Callable[[int, int, str], None] | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> JobReport:
    def handle(act: PlannedAction) -> str:
        assert act.target is not None
        data = read_table(act.source, options.has_header)
        kept, removed = dedupe_rows(data, options)
        write_table(
            TableData(header=data.header, rows=kept, source=act.source),
            act.target, options.output_format, "去重结果",
        )
        return f"删除 {removed} 行重复，输出 {len(kept)} 行"

    return run_per_file(actions, "Excel 去重", handle, on_progress, should_cancel)

"""看一眼表格里有什么：列名、工作表、以及"有没有我们处理不了的东西"。

界面上的"列"下拉要靠它填；格式统一之前也要靠它警告用户会丢什么。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .workbook import (
    EXCEL_SUFFIXES,
    describe_unsupported,
    list_sheets,
    read_table,
)


@dataclass
class SheetInfo:
    """一个表格文件的概况。"""

    path: Path
    columns: list[str] = field(default_factory=list)
    row_count: int = 0
    sheets: list[str] = field(default_factory=list)
    error: str | None = None
    # 我们重写文件时会丢掉的东西
    unsupported_features: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.error is None

    def describe_features(self) -> str:
        if not self.unsupported_features:
            return ""
        return "、".join(self.unsupported_features)


def inspect_file(path: Path, has_header: bool = True) -> SheetInfo:
    """读表头和行数。出错不抛异常，写进 error 字段。"""
    问题 = describe_unsupported(path)
    if 问题:
        return SheetInfo(path=path, error=问题)

    try:
        data = read_table(path, has_header)
        info = SheetInfo(
            path=path,
            columns=list(data.header),
            row_count=data.row_count,
            sheets=list_sheets(path) if path.suffix.lower() in EXCEL_SUFFIXES else [],
        )
        info.unsupported_features = detect_unsupported_features(path)
        return info
    except Exception as e:
        return SheetInfo(path=path, error=f"读取失败：{type(e).__name__} {e}")


def detect_unsupported_features(path: Path) -> list[str]:
    """检测这个工作簿里有没有我们重写时保不住的内容。

    openpyxl 重新保存会丢掉图表、图片、数据透视表、条件格式和宏。
    这不是 bug 而是能力边界，必须提前告诉用户，不能等文件被写出来才发现东西没了。
    """
    if path.suffix.lower() not in EXCEL_SUFFIXES:
        return []

    发现: list[str] = []
    try:
        from openpyxl import load_workbook

        wb = load_workbook(path, data_only=False)
        try:
            if getattr(wb, "vba_archive", None) is not None:
                发现.append("宏（VBA）")
            for ws in wb.worksheets:
                if getattr(ws, "_charts", None):
                    发现.append("图表")
                if getattr(ws, "_images", None):
                    发现.append("图片")
                if getattr(ws, "_pivots", None):
                    发现.append("数据透视表")
                cf = getattr(ws, "conditional_formatting", None)
                if cf is not None and list(cf):
                    发现.append("条件格式")
                if getattr(ws, "_tables", None):
                    发现.append("表格对象")
        finally:
            wb.close()
    except Exception:
        # 检测本身失败不应该影响主流程，最多是少一条警告
        return 发现

    # 去重并保持顺序
    去重 = []
    for f in 发现:
        if f not in 去重:
            去重.append(f)
    return 去重


def common_columns(infos: list[SheetInfo]) -> list[str]:
    """多个文件共有的列，供界面的列下拉使用。"""
    可用 = [i for i in infos if i.ok and i.columns]
    if not 可用:
        return []
    共有 = list(可用[0].columns)
    for info in 可用[1:]:
        其它 = set(info.columns)
        共有 = [c for c in 共有 if c in 其它]
    return 共有


def all_columns(infos: list[SheetInfo]) -> list[str]:
    """所有文件里出现过的列，保持首次出现顺序。"""
    出现: list[str] = []
    for info in infos:
        if not info.ok:
            continue
        for c in info.columns:
            if c and c not in 出现:
                出现.append(c)
    return 出现


# ---------------- 表头一致性检查 ----------------
#
# 界面上的列下拉只读前若干个文件（读全部在几百个文件时会明显卡），
# 所以用户完全可能选到一个"只有前面几个文件才有"的列。
# 这个检查在预览阶段对**全部**选中文件跑一遍，把问题文件提前列出来，
# 不能等 execute 才一个个失败。


@dataclass
class HeaderReport:
    """一批文件的表头体检结果。"""

    baseline: list[str] = field(default_factory=list)          # 基准表头（第一个能读的文件）
    baseline_path: Path | None = None
    ok: list[Path] = field(default_factory=list)
    missing: list[tuple[Path, list[str]]] = field(default_factory=list)   # 缺必需列
    mismatched: list[Path] = field(default_factory=list)       # 表头和基准不一样，但必需列都在
    unreadable: list[tuple[Path, str]] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.ok) + len(self.missing) + len(self.mismatched) + len(self.unreadable)

    @property
    def blocked(self) -> list[Path]:
        """执行时一定会被跳过的文件。"""
        return [p for p, _ in self.missing] + [p for p, _ in self.unreadable]

    @property
    def has_problems(self) -> bool:
        return bool(self.missing or self.mismatched or self.unreadable)

    def describe_lines(self, max_examples: int = 5) -> list[str]:
        """给日志用的中文说明，每条一行。"""
        行: list[str] = []
        if self.unreadable:
            名字 = "、".join(p.name for p, _ in self.unreadable[:max_examples])
            尾 = f" 等 {len(self.unreadable)} 个" if len(self.unreadable) > max_examples else ""
            行.append(f"{len(self.unreadable)} 个文件读不了，将被跳过：{名字}{尾}")
            for path, 原因 in self.unreadable[:max_examples]:
                行.append(f"    {path.name} —— {原因}")
        if self.missing:
            行.append(f"{len(self.missing)} 个文件缺少需要的列，将被跳过：")
            for path, 缺 in self.missing[:max_examples]:
                行.append(f"    {path.name} —— 缺少「{'、'.join(缺)}」")
            if len(self.missing) > max_examples:
                行.append(f"    …… 还有 {len(self.missing) - max_examples} 个")
        if self.mismatched:
            基准 = self.baseline_path.name if self.baseline_path else "第一个文件"
            名字 = "、".join(p.name for p in self.mismatched[:max_examples])
            尾 = f" 等 {len(self.mismatched)} 个" if len(self.mismatched) > max_examples else ""
            行.append(
                f"{len(self.mismatched)} 个文件的表头和「{基准}」不一致，"
                f"但需要的列都在，会照常处理：{名字}{尾}"
            )
        return 行

    def summary(self) -> str:
        if not self.has_problems:
            return f"{self.total} 个文件的表头都检查过了，没有问题"
        部分 = [f"共 {self.total} 个文件"]
        if self.ok:
            部分.append(f"{len(self.ok)} 个正常")
        if self.mismatched:
            部分.append(f"{len(self.mismatched)} 个表头不一致（仍会处理）")
        if self.missing:
            部分.append(f"{len(self.missing)} 个缺列（会跳过）")
        if self.unreadable:
            部分.append(f"{len(self.unreadable)} 个读不了（会跳过）")
        return "，".join(部分)


def check_headers(infos: list[SheetInfo], required_columns: list[str]) -> HeaderReport:
    """对着必需列体检一批文件的表头。

    :param infos: 每个文件的概况，来自 inspect_file
    :param required_columns: 用户选的那些列；留空表示不要求特定列
    """
    report = HeaderReport()
    required = [c for c in required_columns if c]

    for info in infos:
        if not info.ok:
            report.unreadable.append((info.path, info.error or "读取失败"))
            continue
        if report.baseline_path is None:
            report.baseline = list(info.columns)
            report.baseline_path = info.path

        有 = set(info.columns)
        缺 = [c for c in required if c not in 有]
        if 缺:
            report.missing.append((info.path, 缺))
        elif list(info.columns) != report.baseline:
            report.mismatched.append(info.path)
        else:
            report.ok.append(info.path)

    return report

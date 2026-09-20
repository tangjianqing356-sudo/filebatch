"""任务的计划与结果模型。

整个工具的核心约定：**任何操作都先生成计划(plan)，界面展示预览，用户确认后才执行。**
这样"操作前预览"和"防误操作"不是额外功能，而是架构本身决定的。
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class PlannedAction:
    """一条计划中的操作。target 为 None 表示这条不会产生新文件。"""

    source: Path
    target: Path | None
    action: str                      # 复制 / 重命名 / 转换 / 合并 …
    note: str = ""
    skip_reason: str | None = None   # 非 None 表示这条会被跳过，不执行
    # 执行阶段需要的结构化参数（例如 PDF 拆分的页码区间）。
    # 不要把这类信息编码进 note 再正则解析出来——那样改一句提示文案就会出错。
    payload: dict[str, Any] = field(default_factory=dict)

    @property
    def will_run(self) -> bool:
        return self.skip_reason is None


@dataclass
class ItemResult:
    source: Path
    target: Path | None
    ok: bool
    message: str = ""

    @property
    def status(self) -> str:
        return "成功" if self.ok else "失败"


@dataclass
class JobReport:
    """一次批处理的完整结果，也是写日志的数据源。"""

    job_name: str
    started_at: float = field(default_factory=time.time)
    finished_at: float | None = None
    items: list[ItemResult] = field(default_factory=list)
    skipped: list[tuple[Path, str]] = field(default_factory=list)

    def add_ok(self, source: Path, target: Path | None, message: str = "") -> None:
        self.items.append(ItemResult(source, target, True, message))

    def add_fail(self, source: Path, message: str) -> None:
        self.items.append(ItemResult(source, None, False, message))

    def add_skip(self, source: Path, reason: str) -> None:
        self.skipped.append((source, reason))

    def finish(self) -> "JobReport":
        self.finished_at = time.time()
        return self

    @property
    def succeeded(self) -> int:
        return sum(1 for i in self.items if i.ok)

    @property
    def failed(self) -> int:
        return sum(1 for i in self.items if not i.ok)

    @property
    def total(self) -> int:
        return len(self.items) + len(self.skipped)

    @property
    def elapsed(self) -> float:
        return (self.finished_at or time.time()) - self.started_at

    def summary(self) -> str:
        return (
            f"{self.job_name}：共 {self.total} 项，"
            f"成功 {self.succeeded}，失败 {self.failed}，跳过 {len(self.skipped)}，"
            f"耗时 {self.elapsed:.1f} 秒"
        )

    def to_brief_lines(self) -> list[str]:
        """给界面日志面板用的简洁版：只有文件名和结果。

        完整绝对路径留在 [to_log_text] 里——那是用户点"保存日志"导出的详细版本。
        窄面板里刷一堆 /Users/xxx/... 没人看得下去。
        """
        lines: list[str] = []
        for i in self.items:
            arrow = f" → {i.target.name}" if i.target else ""
            extra = f"  {i.message}" if i.message else ""
            lines.append(f"[{i.status}] {i.source.name}{arrow}{extra}")
        for path, reason in self.skipped:
            lines.append(f"[跳过] {path.name}  {reason}")
        return lines

    def to_log_text(self) -> str:
        """生成可直接保存给用户看的中文日志。"""
        lines = [
            "=" * 60,
            f"任务：{self.job_name}",
            f"时间：{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(self.started_at))}",
            self.summary(),
            "=" * 60,
        ]
        if self.items:
            lines.append("")
            lines.append("【处理明细】")
            for i in self.items:
                arrow = f" -> {i.target}" if i.target else ""
                extra = f"  ({i.message})" if i.message else ""
                lines.append(f"  [{i.status}] {i.source}{arrow}{extra}")
        if self.skipped:
            lines.append("")
            lines.append("【跳过的项目】")
            for path, reason in self.skipped:
                lines.append(f"  [跳过] {path}  原因：{reason}")
        if self.failed:
            lines.append("")
            lines.append("【失败汇总】")
            for i in self.items:
                if not i.ok:
                    lines.append(f"  {i.source}：{i.message}")
        lines.append("")
        return "\n".join(lines)

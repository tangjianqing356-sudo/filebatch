"""按规则把文件分类到不同文件夹。

规则都做成纯函数：给一个文件，算出它该进哪个子文件夹名。
这样分类规则可以单独测试，界面预览用的也是同一份逻辑。
"""
from __future__ import annotations

import shutil
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Callable

from .naming import sanitize_filename
from .oserrors import describe as 说明错误
from .result import JobReport, PlannedAction
from .safety import unique_path

# 常见扩展名的中文归类
TYPE_GROUPS: dict[str, tuple[str, ...]] = {
    "图片": (".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tiff", ".tif", ".heic", ".svg"),
    "文档": (".doc", ".docx", ".pdf", ".txt", ".md", ".rtf", ".odt", ".pages"),
    "表格": (".xls", ".xlsx", ".xlsm", ".csv", ".numbers"),
    "演示": (".ppt", ".pptx", ".key"),
    "音频": (".mp3", ".wav", ".flac", ".aac", ".m4a", ".ogg"),
    "视频": (".mp4", ".mov", ".avi", ".mkv", ".wmv", ".flv", ".webm"),
    "压缩包": (".zip", ".rar", ".7z", ".tar", ".gz", ".bz2"),
    "程序": (".exe", ".dmg", ".pkg", ".apk", ".msi", ".app"),
}

_SUFFIX_TO_GROUP = {suf: group for group, sufs in TYPE_GROUPS.items() for suf in sufs}


class ClassifyMode(str, Enum):
    BY_TYPE = "type"            # 按文件类型（图片/文档/表格…）
    BY_EXTENSION = "extension"  # 按扩展名（jpg/png/pdf…）
    BY_DATE_MONTH = "month"     # 按修改月份 2026-09
    BY_DATE_YEAR = "year"       # 按修改年份 2026
    BY_FIRST_LETTER = "letter"  # 按文件名首字符


def folder_for(path: Path, mode: ClassifyMode) -> str:
    """算出这个文件应该进哪个子文件夹。纯函数，不碰文件系统（除了读修改时间）。"""
    if mode is ClassifyMode.BY_TYPE:
        return _SUFFIX_TO_GROUP.get(path.suffix.lower(), "其它")

    if mode is ClassifyMode.BY_EXTENSION:
        ext = path.suffix.lower().lstrip(".")
        return ext if ext else "无扩展名"

    if mode in (ClassifyMode.BY_DATE_MONTH, ClassifyMode.BY_DATE_YEAR):
        try:
            mtime = datetime.fromtimestamp(path.stat().st_mtime)
        except OSError:
            return "日期未知"
        return mtime.strftime("%Y-%m") if mode is ClassifyMode.BY_DATE_MONTH else mtime.strftime("%Y")

    if mode is ClassifyMode.BY_FIRST_LETTER:
        name = path.stem.strip()
        if not name:
            return "其它"
        first = name[0]
        if first.isascii() and first.isalpha():
            return first.upper()
        if first.isdigit():
            return "数字"
        return first  # 中文等直接用首字本身

    return "其它"


def plan_classify(
    files: list[Path],
    mode: ClassifyMode,
    output_dir: Path,
    move: bool = False,
) -> list[PlannedAction]:
    actions: list[PlannedAction] = []
    taken: set[Path] = set()
    verb = "移动到分类文件夹" if move else "复制到分类文件夹"

    for src in files:
        try:
            folder = sanitize_filename(folder_for(src, mode))
            raw_target = output_dir / folder / src.name
            target = unique_path(raw_target, taken)
            taken.add(target)
            note = "" if target.name == raw_target.name else f"目标重名，自动改为 {target.name}"
            actions.append(PlannedAction(src, target, verb, note))
        except Exception as e:
            actions.append(PlannedAction(src, None, verb, skip_reason=f"分类失败：{e}"))

    return actions


def execute(
    actions: list[PlannedAction],
    move: bool = False,
    on_progress: Callable[[int, int, str], None] | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> JobReport:
    """执行分类计划。每个文件独立 try，一个出错不影响其余。

    :param on_progress: 每处理完一项回调 (已完成数, 总数, 当前文件名)，供界面显示进度
    :param should_cancel: 返回 True 表示用户要求中断。
        中断只影响**尚未执行**的项目，已经处理完的文件原样保留，不做任何回滚。
    """
    report = JobReport("按规则分类" + ("（移动）" if move else "（复制，原文件保留）"))
    total = len(actions)

    for done, act in enumerate(actions):
        if should_cancel is not None and should_cancel():
            for rest in actions[done:]:
                report.add_skip(rest.source, "用户中断任务，此项未执行")
            break
        if not act.will_run:
            report.add_skip(act.source, act.skip_reason or "未说明")
            continue
        try:
            assert act.target is not None
            act.target.parent.mkdir(parents=True, exist_ok=True)
            if move:
                shutil.move(str(act.source), str(act.target))
            else:
                shutil.copy2(act.source, act.target)
            report.add_ok(act.source, act.target, act.note)
        except PermissionError:
            report.add_fail(act.source, "没有权限访问该文件，可能被其它程序占用")
        except FileNotFoundError as e:
            report.add_fail(act.source, 说明错误(e, act.source))
        except shutil.Error as e:
            report.add_fail(act.source, f"移动/复制失败：{e}")
        except OSError as e:
            report.add_fail(act.source, 说明错误(e, act.source))
        except Exception as e:
            report.add_fail(act.source, f"未知错误：{type(e).__name__} {e}")

        if on_progress is not None:
            on_progress(done + 1, total, act.source.name)

    return report.finish()

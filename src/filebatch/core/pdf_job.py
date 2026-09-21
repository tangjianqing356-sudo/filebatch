"""PDF 批量拆分与合并。

加密、损坏的 PDF 都会被单独跳过并说明原因，不会让整批任务失败。
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Callable

from .naming import sanitize_filename
from .oserrors import describe as 说明错误
from .result import JobReport, PlannedAction
from .safety import unique_path


class SplitMode(str, Enum):
    EVERY_PAGE = "every_page"   # 每页拆成一个文件
    FIXED_SIZE = "fixed_size"   # 每 N 页一个文件
    RANGES = "ranges"           # 按指定页码范围，如 1-3,5,8-10


@dataclass
class SplitOptions:
    mode: SplitMode = SplitMode.EVERY_PAGE
    pages_per_file: int = 1
    ranges_text: str = ""

    def validate(self) -> str | None:
        if self.mode is SplitMode.FIXED_SIZE and self.pages_per_file < 1:
            return "每个文件的页数至少为 1"
        if self.mode is SplitMode.RANGES:
            if not self.ranges_text.strip():
                return "请填写页码范围，例如 1-3,5,8-10"
            try:
                parse_ranges(self.ranges_text, 10_000)
            except ValueError as e:
                return str(e)
        return None


def parse_ranges(text: str, page_count: int) -> list[tuple[int, int]]:
    """把 "1-3, 5, 8-10" 解析成 [(0,2),(4,4),(7,9)]（0 起的闭区间）。

    页码对用户是 1 起的，内部统一转成 0 起，避免到处 ±1 出错。
    """
    result: list[tuple[int, int]] = []
    for chunk in re.split(r"[,，]", text):
        chunk = chunk.strip()
        if not chunk:
            continue
        m = re.fullmatch(r"(\d+)\s*[-—~]\s*(\d+)", chunk)
        if m:
            start, end = int(m.group(1)), int(m.group(2))
        elif chunk.isdigit():
            start = end = int(chunk)
        else:
            raise ValueError(f"无法识别的页码范围：{chunk}（正确写法如 1-3 或 5）")

        if start < 1 or end < 1:
            raise ValueError(f"页码必须从 1 开始：{chunk}")
        if start > end:
            raise ValueError(f"起始页不能大于结束页：{chunk}")
        if start > page_count:
            raise ValueError(f"起始页 {start} 超过总页数 {page_count}")
        result.append((start - 1, min(end, page_count) - 1))

    if not result:
        raise ValueError("没有解析出任何有效页码范围")
    return result


def _open_reader(path: Path):
    """打开 PDF，返回 (reader, 错误说明)。两者必有一个为 None。"""
    try:
        from pypdf import PdfReader
        from pypdf.errors import PdfReadError
    except ImportError:
        return None, "缺少 pypdf 库，无法处理 PDF"

    try:
        reader = PdfReader(str(path))
        if reader.is_encrypted:
            # 有些 PDF 是空密码加密，能解开就继续
            try:
                if reader.decrypt("") == 0:
                    return None, "PDF 已加密，需要密码才能打开"
            except Exception:
                return None, "PDF 已加密，需要密码才能打开"
        if len(reader.pages) == 0:
            return None, "PDF 没有任何页面"
        return reader, None
    except PdfReadError as e:
        return None, f"PDF 已损坏或格式不正确：{e}"
    except Exception as e:
        return None, f"无法打开 PDF：{type(e).__name__} {e}"


def plan_split(files: list[Path], options: SplitOptions, output_dir: Path) -> list[PlannedAction]:
    actions: list[PlannedAction] = []
    taken: set[Path] = set()

    for src in files:
        if src.suffix.lower() != ".pdf":
            actions.append(PlannedAction(src, None, "拆分 PDF", skip_reason="不是 PDF 文件"))
            continue

        reader, err = _open_reader(src)
        if reader is None:
            actions.append(PlannedAction(src, None, "拆分 PDF", skip_reason=err or "无法打开"))
            continue

        page_count = len(reader.pages)
        try:
            if options.mode is SplitMode.EVERY_PAGE:
                segments = [(i, i) for i in range(page_count)]
            elif options.mode is SplitMode.FIXED_SIZE:
                step = options.pages_per_file
                segments = [(i, min(i + step - 1, page_count - 1)) for i in range(0, page_count, step)]
            else:
                segments = parse_ranges(options.ranges_text, page_count)
        except ValueError as e:
            actions.append(PlannedAction(src, None, "拆分 PDF", skip_reason=str(e)))
            continue

        stem = sanitize_filename(src.stem)
        for start, end in segments:
            label = f"{start + 1}" if start == end else f"{start + 1}-{end + 1}"
            raw_target = output_dir / f"{stem}_第{label}页.pdf"
            target = unique_path(raw_target, taken)
            taken.add(target)
            actions.append(
                PlannedAction(
                    src, target, "拆分 PDF",
                    f"取第 {label} 页（原文件共 {page_count} 页）",
                    payload={"start": start, "end": end},
                )
            )

    return actions


def execute_split(
    actions: list[PlannedAction],
    on_progress: Callable[[int, int, str], None] | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> JobReport:
    """执行拆分计划。每段独立 try，一段失败不影响其余。

    :param on_progress: 每处理完一项回调 (已完成数, 总数, 当前文件名)，供界面显示进度
    :param should_cancel: 返回 True 表示用户要求中断。
        中断只影响**尚未执行**的项目，已经处理完的原样保留。
    """
    report = JobReport("PDF 批量拆分")
    try:
        from pypdf import PdfReader, PdfWriter
    except ImportError:
        for act in actions:
            report.add_fail(act.source, "缺少 pypdf 库，无法处理 PDF")
        return report.finish()

    # 同一个源文件会拆出多段，缓存 reader 避免反复打开
    cache: dict[Path, object] = {}
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
            if act.source not in cache:
                reader, err = _open_reader(act.source)
                if reader is None:
                    report.add_fail(act.source, err or "无法打开")
                    continue
                cache[act.source] = reader
            reader = cache[act.source]

            start = act.payload.get("start")
            end = act.payload.get("end")
            if start is None or end is None:
                report.add_fail(act.source, "内部错误：计划里缺少页码信息")
                continue

            writer = PdfWriter()
            for i in range(start, end + 1):
                writer.add_page(reader.pages[i])  # type: ignore[attr-defined]

            act.target.parent.mkdir(parents=True, exist_ok=True)
            with open(act.target, "wb") as f:
                writer.write(f)
            report.add_ok(act.source, act.target, act.note)
        except PermissionError:
            report.add_fail(act.source, "没有权限访问该文件，可能被其它程序占用")
        except IndexError:
            report.add_fail(act.source, "页码超出范围，PDF 可能在处理过程中被改动")
        except OSError as e:
            report.add_fail(act.source, 说明错误(e))
        except Exception as e:
            report.add_fail(act.source, f"未知错误：{type(e).__name__} {e}")

        if on_progress is not None:
            on_progress(done + 1, total, act.source.name)

    return report.finish()


def plan_merge(files: list[Path], output_file: Path) -> list[PlannedAction]:
    """合并的"计划"是每个输入文件一条，目标都指向同一个输出文件。"""
    actions: list[PlannedAction] = []
    for src in files:
        if src.suffix.lower() != ".pdf":
            actions.append(PlannedAction(src, None, "合并 PDF", skip_reason="不是 PDF 文件"))
            continue
        reader, err = _open_reader(src)
        if reader is None:
            actions.append(PlannedAction(src, None, "合并 PDF", skip_reason=err or "无法打开"))
            continue
        actions.append(
            PlannedAction(src, output_file, "合并 PDF", f"贡献 {len(reader.pages)} 页")
        )
    return actions


def execute_merge(
    actions: list[PlannedAction],
    output_file: Path,
    on_progress: Callable[[int, int, str], None] | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> JobReport:
    """把多个 PDF 合成一个。

    中断语义和别处略有不同：合并是一次性写出的，中断后**已经读进来的部分仍会写出**，
    不会留下一个半截文件。这样用户拿到的结果始终是完整可用的 PDF。

    :param on_progress: 每处理完一项回调 (已完成数, 总数, 当前文件名)，供界面显示进度
    :param should_cancel: 返回 True 表示用户要求中断。
        中断只影响**尚未执行**的项目，已经处理完的原样保留。
    """
    report = JobReport("PDF 批量合并")
    try:
        from pypdf import PdfWriter
    except ImportError:
        for act in actions:
            report.add_fail(act.source, "缺少 pypdf 库，无法处理 PDF")
        return report.finish()

    writer = PdfWriter()
    merged_any = False
    total = len(actions)

    for done, act in enumerate(actions):
        if should_cancel is not None and should_cancel():
            for rest in actions[done:]:
                report.add_skip(rest.source, "用户中断任务，此项未合并")
            break
        if not act.will_run:
            report.add_skip(act.source, act.skip_reason or "未说明")
            continue
        try:
            reader, err = _open_reader(act.source)
            if reader is None:
                report.add_fail(act.source, err or "无法打开")
                continue
            for page in reader.pages:
                writer.add_page(page)
            merged_any = True
            report.add_ok(act.source, act.target, act.note)
        except Exception as e:
            report.add_fail(act.source, f"合并失败：{type(e).__name__} {e}")

        if on_progress is not None:
            on_progress(done + 1, total, act.source.name)

    if merged_any:
        try:
            final = unique_path(output_file)
            final.parent.mkdir(parents=True, exist_ok=True)
            with open(final, "wb") as f:
                writer.write(f)
            # 实际落盘的文件名可能因为防覆盖改过，回填给每条结果
            for item in report.items:
                if item.ok:
                    item.target = final
        except Exception as e:
            for item in report.items:
                if item.ok:
                    item.ok = False
                    item.message = f"写入合并结果失败：{e}"

    return report.finish()

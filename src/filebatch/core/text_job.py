"""文本文件批量查找替换。

两个容易踩坑的地方专门处理了：
  1. 编码——中文环境里 UTF-8 和 GBK 混着出现，按顺序试探，测不出来就跳过而不是写出乱码；
  2. 二进制文件——用户很可能把整个文件夹拖进来，混进 exe/图片，必须识别出来跳过。
"""
from __future__ import annotations

import codecs
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .oserrors import describe as 说明错误
from .result import JobReport, PlannedAction
from .safety import unique_path

# 试探顺序：中文环境下最常见的几种。
# 注意不要把 utf-8-sig 放进来试探——它能成功解码没有 BOM 的普通 UTF-8 文件，
# 于是写回时会凭空加上一个 BOM。BOM 必须靠字节头显式判断。
CANDIDATE_ENCODINGS = ("utf-8", "gb18030", "big5", "shift_jis", "latin-1")

# 超过这个大小就不处理了，避免把几百 MB 的日志一次读进内存
MAX_TEXT_BYTES = 50 * 1024 * 1024


@dataclass
class ReplaceOptions:
    find: str = ""
    replace: str = ""
    use_regex: bool = False
    case_sensitive: bool = True
    in_place: bool = False

    def validate(self) -> str | None:
        if not self.find:
            return "请填写要查找的内容"
        if self.use_regex:
            try:
                re.compile(self.find)
            except re.error as e:
                return f"正则表达式有误：{e}"
        return None


def looks_binary(data: bytes) -> bool:
    """含有 NUL 字节基本可以断定是二进制文件。"""
    return b"\x00" in data[:8192]


def read_text(path: Path) -> tuple[str, str] | None:
    """读成文本，返回 (内容, 用的编码)。识别不了返回 None。"""
    raw = path.read_bytes()
    if looks_binary(raw):
        return None
    if raw.startswith(codecs.BOM_UTF8):
        # 有 BOM 才用 utf-8-sig，写回时才会把 BOM 原样保留
        try:
            return raw.decode("utf-8-sig"), "utf-8-sig"
        except UnicodeDecodeError:
            pass
    for enc in CANDIDATE_ENCODINGS:
        try:
            return raw.decode(enc), enc
        except (UnicodeDecodeError, LookupError):
            continue
    return None


def count_and_replace(content: str, options: ReplaceOptions) -> tuple[str, int]:
    """返回 (替换后的内容, 替换次数)。纯函数，方便测试。"""
    if not options.find:
        return content, 0

    if options.use_regex:
        flags = 0 if options.case_sensitive else re.IGNORECASE
        pattern = re.compile(options.find, flags)
        new_content, count = pattern.subn(options.replace, content)
        return new_content, count

    if options.case_sensitive:
        count = content.count(options.find)
        return (content.replace(options.find, options.replace), count) if count else (content, 0)

    # 不区分大小写的纯文本替换，用正则转义来实现
    pattern = re.compile(re.escape(options.find), re.IGNORECASE)
    new_content, count = pattern.subn(options.replace.replace("\\", "\\\\"), content)
    return new_content, count


def plan_replace(
    files: list[Path],
    options: ReplaceOptions,
    output_dir: Path | None,
) -> list[PlannedAction]:
    """计划阶段真的会读文件、数出会替换多少处，预览里直接告诉用户"将替换 3 处"。"""
    actions: list[PlannedAction] = []
    taken: set[Path] = set()

    for src in files:
        try:
            if src.stat().st_size > MAX_TEXT_BYTES:
                actions.append(
                    PlannedAction(src, None, "查找替换",
                                  skip_reason=f"文件超过 {MAX_TEXT_BYTES // 1024 // 1024}MB，跳过")
                )
                continue

            loaded = read_text(src)
            if loaded is None:
                actions.append(
                    PlannedAction(src, None, "查找替换",
                                  skip_reason="不是文本文件，或编码无法识别")
                )
                continue

            content, encoding = loaded
            _, count = count_and_replace(content, options)
            if count == 0:
                actions.append(
                    PlannedAction(src, None, "查找替换", skip_reason="没有匹配到要替换的内容")
                )
                continue

            if options.in_place:
                target = src
            else:
                raw_target = (output_dir or src.parent) / src.name
                target = unique_path(raw_target, taken)
                taken.add(target)

            note = f"将替换 {count} 处（编码 {encoding}）"
            actions.append(PlannedAction(src, target, "查找替换", note))
        except PermissionError:
            actions.append(PlannedAction(src, None, "查找替换", skip_reason="没有权限读取该文件"))
        except Exception as e:
            actions.append(PlannedAction(src, None, "查找替换", skip_reason=f"读取失败：{e}"))

    return actions


def execute(
    actions: list[PlannedAction],
    options: ReplaceOptions,
    on_progress: Callable[[int, int, str], None] | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> JobReport:
    """执行替换计划。每个文件独立 try，一个出错不影响其余。

    :param on_progress: 每处理完一项回调 (已完成数, 总数, 当前文件名)，供界面显示进度
    :param should_cancel: 返回 True 表示用户要求中断。
        中断只影响**尚未执行**的项目，已经处理完的文件原样保留，不做任何回滚。
    """
    report = JobReport("文本批量查找替换" + ("（直接修改原文件）" if options.in_place else "（输出到新目录）"))
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
            loaded = read_text(act.source)
            if loaded is None:
                report.add_fail(act.source, "执行时无法读取文本内容")
                continue
            content, encoding = loaded
            new_content, count = count_and_replace(content, options)

            act.target.parent.mkdir(parents=True, exist_ok=True)
            # 统一按原编码写回，避免把 GBK 文件悄悄变成 UTF-8
            write_encoding = "utf-8-sig" if encoding == "utf-8-sig" else encoding
            act.target.write_text(new_content, encoding=write_encoding)
            report.add_ok(act.source, act.target, f"替换 {count} 处")
        except PermissionError:
            report.add_fail(act.source, "没有权限写入，文件可能是只读的或被占用")
        except FileNotFoundError:
            report.add_fail(act.source, "文件已不存在，可能在处理过程中被移动或删除")
        except UnicodeEncodeError as e:
            report.add_fail(act.source, f"替换后的内容无法用原编码({encoding})保存：{e}")
        except OSError as e:
            report.add_fail(act.source, 说明错误(e))
        except Exception as e:
            report.add_fail(act.source, f"未知错误：{type(e).__name__} {e}")

        if on_progress is not None:
            on_progress(done + 1, total, act.source.name)

    return report.finish()

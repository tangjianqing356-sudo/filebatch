"""批量重命名 / 自动编号。

默认行为是**复制到新目录**而不是原地改名——这是最不容易让用户后悔的选择。
需要原地改名时要显式 in_place=True。
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Callable

from .naming import NameRule, sanitize_filename
from .oserrors import describe as 说明错误
from .result import JobReport, PlannedAction
from .safety import unique_path


def _is_same_file(a: Path, b: Path) -> bool:
    """两个路径是否指向同一个文件。

    macOS 和 Windows 的文件系统大小写不敏感：把 ReadMe.TXT 改成 readme.TXT 时，
    目标"已存在"其实就是它自己。不识别这种情况就会误判成重名冲突，
    生成 readme_1.TXT——而"全部改小写"恰恰是很常用的操作。
    """
    try:
        return a.exists() and b.exists() and os.path.samefile(a, b)
    except OSError:
        return False


def plan_rename(
    files: list[Path],
    rule: NameRule,
    output_dir: Path | None,
    in_place: bool = False,
) -> list[PlannedAction]:
    """先算出完整计划，供界面预览。这一步不碰任何文件。"""
    actions: list[PlannedAction] = []
    taken: set[Path] = set()

    for index, src in enumerate(files):
        try:
            new_stem = sanitize_filename(rule.apply(src.stem, index))
            new_suffix = rule.resolve_extension(src.suffix)
            dest_dir = src.parent if in_place else (output_dir or src.parent)
            raw_target = dest_dir / f"{new_stem}{new_suffix}"

            same_file = _is_same_file(raw_target, src)

            if same_file and not in_place:
                # 复制模式下源和目标是同一个文件，复制过去会把原文件清空，绝对不能做
                actions.append(
                    PlannedAction(src, None, "复制并重命名",
                                  skip_reason="目标位置就是原文件本身，请换一个输出文件夹")
                )
                continue

            if same_file and raw_target.name == src.name:
                actions.append(
                    PlannedAction(src, None, "重命名", skip_reason="新旧文件名相同，无需处理")
                )
                continue

            if same_file:
                # 只改了大小写：目标就是自己，不算冲突，直接 rename 即可
                target = raw_target
                note = "仅更改大小写"
            else:
                target = unique_path(raw_target, taken)
                note = "" if target.name == raw_target.name else f"目标重名，自动改为 {target.name}"
            taken.add(target)
            actions.append(
                PlannedAction(src, target, "重命名" if in_place else "复制并重命名", note)
            )
        except Exception as e:  # 单个文件算不出来不能拖垮整批
            actions.append(PlannedAction(src, None, "重命名", skip_reason=f"生成新名字失败：{e}"))

    return actions


def execute(
    actions: list[PlannedAction],
    in_place: bool = False,
    on_progress: Callable[[int, int, str], None] | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> JobReport:
    """执行计划。每个文件独立 try，一个出错不影响其余。

    :param on_progress: 每处理完一项回调 (已完成数, 总数, 当前文件名)，供界面显示进度
    :param should_cancel: 返回 True 表示用户要求中断。
        中断只影响**尚未执行**的项目，已经处理完的文件原样保留，不做任何回滚。
    """
    report = JobReport("批量重命名" if in_place else "批量重命名（输出到新目录）")
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
            if in_place:
                act.source.rename(act.target)
            else:
                shutil.copy2(act.source, act.target)
            report.add_ok(act.source, act.target, act.note)
        except PermissionError:
            report.add_fail(act.source, "没有权限访问该文件，可能被其它程序占用")
        except FileNotFoundError:
            report.add_fail(act.source, "文件已不存在，可能在处理过程中被移动或删除")
        except OSError as e:
            report.add_fail(act.source, 说明错误(e))
        except Exception as e:
            report.add_fail(act.source, f"未知错误：{type(e).__name__} {e}")

        if on_progress is not None:
            on_progress(done + 1, total, act.source.name)

    return report.finish()

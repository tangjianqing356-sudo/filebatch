"""Excel 各 Job 共用的执行循环。

取消、进度、逐项异常隔离这三件事每个 job 都要做，而且必须做得一模一样，
所以抽出来一份。各 job 只写"这一项具体怎么处理"，
其余交给这里——既少抄代码，也保证行为一致。
"""
from __future__ import annotations

from typing import Callable

from ..oserrors import describe as 说明错误
from ..result import JobReport, PlannedAction

# handle(act) 处理一项，返回写进结果里的备注；失败就抛异常
Handler = Callable[[PlannedAction], str]


def run_per_file(
    actions: list[PlannedAction],
    job_name: str,
    handle: Handler,
    on_progress: Callable[[int, int, str], None] | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> JobReport:
    """逐项执行。一项出错不影响其余，中断只影响尚未执行的项目。"""
    report = JobReport(job_name)
    total = len(actions)

    for done, act in enumerate(actions):
        if should_cancel is not None and should_cancel():
            for rest in actions[done:]:
                report.add_skip(rest.source, "用户中断任务，此项未执行")
            break

        if not act.will_run:
            report.add_skip(act.source, act.skip_reason or "未说明")
        else:
            try:
                note = handle(act) or act.note
                report.add_ok(act.source, act.target, note)
            except PermissionError:
                report.add_fail(act.source, "没有权限访问该文件，可能正在被 Excel 打开")
            except FileNotFoundError:
                report.add_fail(act.source, "文件已不存在，可能在处理过程中被移动或删除")
            except ValueError as e:
                report.add_fail(act.source, str(e))
            except OSError as e:
                report.add_fail(act.source, 说明错误(e))
            except Exception as e:
                report.add_fail(act.source, f"未知错误：{type(e).__name__} {e}")

        if on_progress is not None:
            on_progress(done + 1, total, act.source.name)

    return report.finish()


def plan_unsupported(source, action: str, reason: str) -> PlannedAction:
    """生成一条"跳过并说明原因"的计划。"""
    return PlannedAction(source, None, action, skip_reason=reason)

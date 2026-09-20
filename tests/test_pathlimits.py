"""路径长度上限：实测而不是写死 260。"""
from pathlib import Path

from filebatch.core.pathlimits import (
    PathLimit,
    annotate_over_limit,
    probe_path_limit,
    too_long_reason,
)
from filebatch.core.result import PlannedAction


def test_实测本机上限并且不留垃圾(tmp_path):
    from filebatch.core.pathlimits import reset_cache

    reset_cache()
    limit = probe_path_limit()
    assert limit.probe_error is None
    # POSIX 系统单文件名一般是 255；Windows 上这个值可能不同，只要测出个正数就行
    assert limit.max_name > 0


def test_探测绝不碰用户目录(tmp_path):
    """预览阶段必须只读：探测只能在系统临时目录里做。"""
    from filebatch.core.pathlimits import reset_cache

    reset_cache()
    目标 = tmp_path / "还没创建的输出目录"
    probe_path_limit(目标)
    assert not 目标.exists(), "探测不能把输出目录创建出来"
    assert list(tmp_path.iterdir()) == [], "用户目录里不能留下任何东西"


def test_探测结果有中文描述():
    desc = probe_path_limit().describe()
    assert "路径" in desc


def test_没测出限制时措辞要保守():
    """不能说"没有限制"——探测只证明试到 400 字符还能建，不代表所有情况都行。"""
    limit = PathLimit(max_path=0, max_name=255)
    desc = limit.describe()
    assert "可支持较长路径" in desc
    assert "没有限制" not in desc and "无限制" not in desc


def test_没有限制时不拦任何路径():
    limit = PathLimit(max_path=0, max_name=255)
    assert too_long_reason(Path("/a/" + "b" * 100 + "/c.txt"), limit) is None


def test_超过总路径上限时给中文提示():
    limit = PathLimit(max_path=260, max_name=255)
    长路径 = Path("C:/" + "目录/" * 120 + "文件.txt")
    assert len(str(长路径)) > 260, "测试数据本身要够长"
    reason = too_long_reason(长路径, limit)
    assert reason is not None
    assert "路径过长" in reason
    assert "缩短文件名" in reason
    assert "靠近磁盘根目录" in reason
    assert "Errno" not in reason and "OSError" not in reason, "不能把系统异常甩给用户"


def test_文件名超长单独给提示():
    limit = PathLimit(max_path=0, max_name=255)
    reason = too_long_reason(Path("/tmp") / ("超长" * 200 + ".txt"), limit)
    assert reason is not None
    assert "文件名过长" in reason


def test_探测失败时不拦截交给执行阶段处理():
    limit = PathLimit(probe_error="磁盘不可用")
    assert too_long_reason(Path("/a" * 500), limit) is None


def test_把超长的计划项改成跳过():
    limit = PathLimit(max_path=100, max_name=255)
    actions = [
        PlannedAction(Path("/src/a.txt"), Path("/out/短.txt"), "复制"),
        PlannedAction(Path("/src/b.txt"), Path("/out/" + "长" * 200 + ".txt"), "复制"),
    ]
    拦下 = annotate_over_limit(actions, limit)

    assert 拦下 == 1
    assert actions[0].will_run, "正常的不该被动"
    assert not actions[1].will_run
    assert "路径过长" in actions[1].skip_reason


def test_已经跳过的项不会被重复标注():
    limit = PathLimit(max_path=10, max_name=255)
    act = PlannedAction(Path("/src/a.txt"), None, "复制", skip_reason="原本的原因")
    annotate_over_limit([act], limit)
    assert act.skip_reason == "原本的原因"

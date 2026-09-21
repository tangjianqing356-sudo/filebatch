from pathlib import Path

import pytest

from filebatch.core import rename_job
from filebatch.core.naming import NameRule, NumberPosition


@pytest.fixture
def 样例文件(tmp_path: Path) -> list[Path]:
    src = tmp_path / "源目录"
    src.mkdir()
    files = []
    for name in ["IMG_001.jpg", "IMG_002.jpg", "IMG_003.jpg"]:
        f = src / name
        f.write_bytes(b"fake image")
        files.append(f)
    return files


def test_复制到新目录时原文件保持不动(样例文件, tmp_path):
    out = tmp_path / "输出"
    rule = NameRule(base_name="产品图", number_position=NumberPosition.SUFFIX, number_digits=2)
    actions = rename_job.plan_rename(样例文件, rule, out)
    report = rename_job.execute(actions)

    assert report.succeeded == 3
    assert report.failed == 0
    for f in 样例文件:
        assert f.exists(), "原文件必须还在"
    assert sorted(p.name for p in out.iterdir()) == ["产品图_01.jpg", "产品图_02.jpg", "产品图_03.jpg"]


def test_计划阶段不会碰任何文件(样例文件, tmp_path):
    out = tmp_path / "输出"
    actions = rename_job.plan_rename(样例文件, NameRule(prefix="新_"), out)
    assert len(actions) == 3
    assert not out.exists(), "只做计划时不应该创建输出目录"


def test_目标重名时自动加后缀而不是覆盖(样例文件, tmp_path):
    out = tmp_path / "输出"
    out.mkdir()
    (out / "统一名字.jpg").write_bytes("已存在的文件".encode("utf-8"))

    rule = NameRule(base_name="统一名字")   # 三个文件会算出同一个名字
    actions = rename_job.plan_rename(样例文件, rule, out)
    report = rename_job.execute(actions)

    assert report.succeeded == 3
    assert (out / "统一名字.jpg").read_bytes() == "已存在的文件".encode("utf-8"), "已有文件绝不能被覆盖"
    names = sorted(p.name for p in out.iterdir())
    assert names == ["统一名字.jpg", "统一名字_1.jpg", "统一名字_2.jpg", "统一名字_3.jpg"]


def test_单个文件出错不影响其它文件(样例文件, tmp_path):
    out = tmp_path / "输出"
    actions = rename_job.plan_rename(样例文件, NameRule(prefix="新_"), out)
    # 模拟第二个文件在执行前被删掉
    样例文件[1].unlink()

    report = rename_job.execute(actions)
    assert report.succeeded == 2
    assert report.failed == 1
    # 断意思别断措辞：这句话现在由 core/oserrors 统一给，
    # 六个功能共用一份，措辞改了不该让这条无关的用例跟着炸
    失败消息 = [i.message for i in report.items if not i.ok][0]
    assert any(k in 失败消息 for k in ("找不到这个文件", "文件已不存在")), 失败消息
    assert "Errno" not in 失败消息 and "Traceback" not in 失败消息, 失败消息


def test_原地改名时新旧同名会被跳过(样例文件, tmp_path):
    actions = rename_job.plan_rename(样例文件, NameRule(), None, in_place=True)
    report = rename_job.execute(actions, in_place=True)
    assert report.succeeded == 0
    assert len(report.skipped) == 3
    assert "无需处理" in report.skipped[0][1]


def test_原地改名确实改掉了原文件(样例文件, tmp_path):
    actions = rename_job.plan_rename(样例文件, NameRule(prefix="新_"), None, in_place=True)
    report = rename_job.execute(actions, in_place=True)
    assert report.succeeded == 3
    assert not 样例文件[0].exists()
    assert (样例文件[0].parent / "新_IMG_001.jpg").exists()


def test_日志内容包含成功失败明细(样例文件, tmp_path):
    out = tmp_path / "输出"
    actions = rename_job.plan_rename(样例文件, NameRule(prefix="新_"), out)
    样例文件[0].unlink()
    report = rename_job.execute(actions)

    text = report.to_log_text()
    assert "批量重命名" in text
    assert "【处理明细】" in text
    assert "【失败汇总】" in text
    assert "成功 2" in text and "失败 1" in text


def test_执行过程中会回调进度(样例文件, tmp_path):
    out = tmp_path / "输出"
    actions = rename_job.plan_rename(样例文件, NameRule(prefix="新_"), out)

    记录 = []
    rename_job.execute(actions, on_progress=lambda done, total, name: 记录.append((done, total, name)))

    assert len(记录) == 3
    assert 记录[0][:2] == (1, 3)
    assert 记录[-1][:2] == (3, 3)


def test_中断只停止后续任务不影响已完成的(样例文件, tmp_path):
    out = tmp_path / "输出"
    actions = rename_job.plan_rename(样例文件, NameRule(prefix="新_"), out)

    已处理 = []

    def 处理完第一个就中断():
        return len(已处理) >= 1

    report = rename_job.execute(
        actions,
        on_progress=lambda d, t, n: 已处理.append(n),
        should_cancel=处理完第一个就中断,
    )

    assert report.succeeded == 1, "已完成的必须保留"
    assert len(report.skipped) == 2
    assert "用户中断" in report.skipped[0][1]
    assert (out / "新_IMG_001.jpg").exists(), "中断前完成的文件不能被回滚"
    assert not (out / "新_IMG_002.jpg").exists()


# ---- 大小写不敏感文件系统（macOS / Windows）的边界情况 ----

def test_只改大小写的原地重命名不会变成加后缀(tmp_path):
    """macOS/Windows 上 target.exists() 会命中文件自己，早期版本因此产出 readme_1.TXT。"""
    from filebatch.core.naming import CaseMode

    f = tmp_path / "ReadMe.TXT"
    f.write_text("x", encoding="utf-8")

    actions = rename_job.plan_rename([f], NameRule(case_mode=CaseMode.LOWER), None, in_place=True)
    assert actions[0].target is not None
    assert actions[0].target.name == "readme.TXT", "不能被当成重名冲突"

    report = rename_job.execute(actions, in_place=True)
    assert report.succeeded == 1
    names = [p.name for p in tmp_path.iterdir()]
    assert names == ["readme.TXT"]


def test_复制模式下目标就是原文件本身会被拦住(tmp_path):
    """输出目录等于源目录且文件名不变时，复制会把原文件清空，必须跳过。"""
    f = tmp_path / "数据.txt"
    f.write_text("重要内容", encoding="utf-8")

    actions = rename_job.plan_rename([f], NameRule(), tmp_path, in_place=False)
    report = rename_job.execute(actions)

    assert report.succeeded == 0
    assert len(report.skipped) == 1
    assert "原文件本身" in report.skipped[0][1]
    assert f.read_text(encoding="utf-8") == "重要内容", "原文件内容必须完好"

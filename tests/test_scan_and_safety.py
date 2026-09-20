from pathlib import Path

from filebatch.core.safety import is_inside, unique_path, validate_output_dir
from filebatch.core.scan import collect_files, human_size


def test_文件夹和文件混着拖进来能正确展开(tmp_path):
    d = tmp_path / "文件夹"
    (d / "子目录").mkdir(parents=True)
    (d / "a.txt").write_text("a", encoding="utf-8")
    (d / "子目录" / "b.txt").write_text("b", encoding="utf-8")
    单独文件 = tmp_path / "c.txt"
    单独文件.write_text("c", encoding="utf-8")

    files = collect_files([d, 单独文件])
    assert sorted(f.name for f in files) == ["a.txt", "b.txt", "c.txt"]


def test_不递归时只取一层(tmp_path):
    d = tmp_path / "文件夹"
    (d / "子目录").mkdir(parents=True)
    (d / "a.txt").write_text("a", encoding="utf-8")
    (d / "子目录" / "b.txt").write_text("b", encoding="utf-8")

    files = collect_files([d], recursive=False)
    assert [f.name for f in files] == ["a.txt"]


def test_忽略系统垃圾文件(tmp_path):
    (tmp_path / ".DS_Store").write_text("x", encoding="utf-8")
    (tmp_path / "Thumbs.db").write_text("x", encoding="utf-8")
    (tmp_path / "._隐藏").write_text("x", encoding="utf-8")
    (tmp_path / "正常.txt").write_text("x", encoding="utf-8")

    files = collect_files([tmp_path])
    assert [f.name for f in files] == ["正常.txt"]


def test_按扩展名过滤(tmp_path):
    for name in ["a.jpg", "b.PNG", "c.txt"]:
        (tmp_path / name).write_text("x", encoding="utf-8")
    files = collect_files([tmp_path], suffixes={".jpg", ".png"})
    assert sorted(f.name for f in files) == ["a.jpg", "b.PNG"]


def test_同一个文件被拖进来两次只算一次(tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("x", encoding="utf-8")
    assert len(collect_files([f, f, tmp_path])) == 1


def test_不存在的路径直接忽略(tmp_path):
    assert collect_files([tmp_path / "根本没有这个文件"]) == []


def test_重名时自动加后缀而不覆盖(tmp_path):
    target = tmp_path / "a.txt"
    assert unique_path(target) == target

    target.write_text("已存在", encoding="utf-8")
    assert unique_path(target).name == "a_1.txt"


def test_同一批计划内部也不会互相覆盖(tmp_path):
    target = tmp_path / "a.txt"
    taken = {target}
    assert unique_path(target, taken).name == "a_1.txt"
    taken.add(tmp_path / "a_1.txt")
    assert unique_path(target, taken).name == "a_2.txt"


def test_输出目录不能和源目录相同(tmp_path):
    src = tmp_path / "源"
    src.mkdir()
    f = src / "a.txt"
    f.write_text("x", encoding="utf-8")

    assert validate_output_dir(src, [f]) is not None
    assert "不能和源目录相同" in validate_output_dir(src, [f])
    assert validate_output_dir(tmp_path / "输出", [f]) is None


def test_判断路径包含关系(tmp_path):
    child = tmp_path / "a" / "b"
    child.mkdir(parents=True)
    assert is_inside(child, tmp_path)
    assert not is_inside(tmp_path, child)


def test_文件大小显示成人话():
    assert human_size(500) == "500 B"
    assert human_size(2048) == "2.0 KB"
    assert human_size(5 * 1024 * 1024) == "5.0 MB"


def test_扫描时会回报进度(tmp_path):
    d = tmp_path / "很多文件"
    d.mkdir()
    for i in range(500):
        (d / f"f{i:04d}.txt").write_text("x", encoding="utf-8")

    记录 = []
    files = collect_files([d], on_progress=记录.append)
    assert len(files) == 500
    assert 记录, "应该回报过进度"
    assert 记录[-1] == 500, "最后一次进度必须是最终数量"


def test_扫描可以被取消且已找到的照常返回(tmp_path):
    d = tmp_path / "很多文件"
    d.mkdir()
    for i in range(1000):
        (d / f"f{i:04d}.txt").write_text("x", encoding="utf-8")

    调用次数 = {"n": 0}

    def 立刻取消():
        调用次数["n"] += 1
        return 调用次数["n"] > 1

    files = collect_files([d], should_cancel=立刻取消)
    assert len(files) < 1000, "取消后不应该扫完全部"


def test_扫描遇到坏链接不会整个挂掉(tmp_path):
    d = tmp_path / "目录"
    d.mkdir()
    (d / "正常.txt").write_text("x", encoding="utf-8")
    坏链接 = d / "断掉的链接"
    坏链接.symlink_to(tmp_path / "根本不存在的目标")

    files = collect_files([d])
    assert "正常.txt" in [f.name for f in files]

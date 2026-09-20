from datetime import datetime
from pathlib import Path

from filebatch.core import classify_job
from filebatch.core.classify_job import ClassifyMode, folder_for


def _touch(tmp_path: Path, name: str, mtime: datetime | None = None) -> Path:
    f = tmp_path / name
    f.write_bytes(b"x")
    if mtime:
        ts = mtime.timestamp()
        import os
        os.utime(f, (ts, ts))
    return f


def test_按类型分类(tmp_path):
    assert folder_for(_touch(tmp_path, "a.jpg"), ClassifyMode.BY_TYPE) == "图片"
    assert folder_for(_touch(tmp_path, "b.PDF"), ClassifyMode.BY_TYPE) == "文档"
    assert folder_for(_touch(tmp_path, "c.xlsx"), ClassifyMode.BY_TYPE) == "表格"
    assert folder_for(_touch(tmp_path, "d.zip"), ClassifyMode.BY_TYPE) == "压缩包"
    assert folder_for(_touch(tmp_path, "e.unknown"), ClassifyMode.BY_TYPE) == "其它"


def test_按扩展名分类(tmp_path):
    assert folder_for(_touch(tmp_path, "a.JPG"), ClassifyMode.BY_EXTENSION) == "jpg"
    assert folder_for(_touch(tmp_path, "无扩展名文件"), ClassifyMode.BY_EXTENSION) == "无扩展名"


def test_按日期分类(tmp_path):
    f = _touch(tmp_path, "a.txt", datetime(2026, 3, 15, 10, 0))
    assert folder_for(f, ClassifyMode.BY_DATE_MONTH) == "2026-03"
    assert folder_for(f, ClassifyMode.BY_DATE_YEAR) == "2026"


def test_按首字母分类(tmp_path):
    assert folder_for(_touch(tmp_path, "apple.txt"), ClassifyMode.BY_FIRST_LETTER) == "A"
    assert folder_for(_touch(tmp_path, "9号文件.txt"), ClassifyMode.BY_FIRST_LETTER) == "数字"
    assert folder_for(_touch(tmp_path, "报告.txt"), ClassifyMode.BY_FIRST_LETTER) == "报"


def test_分类复制会自动建文件夹且保留原文件(tmp_path):
    files = [
        _touch(tmp_path, "照片.jpg"),
        _touch(tmp_path, "报表.xlsx"),
        _touch(tmp_path, "说明.txt"),
    ]
    out = tmp_path / "分类结果"
    actions = classify_job.plan_classify(files, ClassifyMode.BY_TYPE, out)
    report = classify_job.execute(actions)

    assert report.succeeded == 3
    assert (out / "图片" / "照片.jpg").exists()
    assert (out / "表格" / "报表.xlsx").exists()
    assert (out / "文档" / "说明.txt").exists()
    for f in files:
        assert f.exists(), "复制模式下原文件必须保留"


def test_分类时同名文件不会互相覆盖(tmp_path):
    d1, d2 = tmp_path / "一月", tmp_path / "二月"
    d1.mkdir(); d2.mkdir()
    files = [_touch(d1, "发票.pdf"), _touch(d2, "发票.pdf")]
    out = tmp_path / "输出"

    report = classify_job.execute(
        classify_job.plan_classify(files, ClassifyMode.BY_TYPE, out)
    )
    assert report.succeeded == 2
    names = sorted(p.name for p in (out / "文档").iterdir())
    assert names == ["发票.pdf", "发票_1.pdf"]

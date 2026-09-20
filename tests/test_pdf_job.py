from pathlib import Path

import pytest
from pypdf import PdfReader, PdfWriter

from filebatch.core import pdf_job
from filebatch.core.pdf_job import SplitMode, SplitOptions, parse_ranges


def make_pdf(path: Path, pages: int) -> Path:
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=200, height=200)
    with open(path, "wb") as f:
        writer.write(f)
    return path


# ---------- 纯函数：页码范围解析 ----------

def test_解析单页和区间():
    assert parse_ranges("1-3,5,8-10", 20) == [(0, 2), (4, 4), (7, 9)]


def test_解析容忍空格和中文逗号():
    assert parse_ranges(" 1 - 3 ，  5 ", 10) == [(0, 2), (4, 4)]


def test_结束页超过总页数时自动截断():
    assert parse_ranges("1-100", 5) == [(0, 4)]


def test_非法页码范围报中文错误():
    with pytest.raises(ValueError, match="无法识别"):
        parse_ranges("abc", 10)
    with pytest.raises(ValueError, match="起始页不能大于结束页"):
        parse_ranges("5-2", 10)
    with pytest.raises(ValueError, match="页码必须从 1 开始"):
        parse_ranges("0-3", 10)
    with pytest.raises(ValueError, match="超过总页数"):
        parse_ranges("99", 5)


def test_拆分参数校验():
    assert "至少为 1" in (SplitOptions(mode=SplitMode.FIXED_SIZE, pages_per_file=0).validate() or "")
    assert "请填写页码范围" in (SplitOptions(mode=SplitMode.RANGES).validate() or "")
    assert SplitOptions().validate() is None


# ---------- 拆分 ----------

def test_每页拆一个文件(tmp_path):
    src = make_pdf(tmp_path / "合同.pdf", 3)
    out = tmp_path / "输出"
    report = pdf_job.execute_split(
        pdf_job.plan_split([src], SplitOptions(SplitMode.EVERY_PAGE), out)
    )
    assert report.succeeded == 3
    names = sorted(p.name for p in out.iterdir())
    assert names == ["合同_第1页.pdf", "合同_第2页.pdf", "合同_第3页.pdf"]
    assert len(PdfReader(str(out / "合同_第1页.pdf")).pages) == 1
    assert src.exists(), "原 PDF 必须保留"


def test_每两页拆一个文件(tmp_path):
    src = make_pdf(tmp_path / "手册.pdf", 5)
    out = tmp_path / "输出"
    report = pdf_job.execute_split(
        pdf_job.plan_split([src], SplitOptions(SplitMode.FIXED_SIZE, pages_per_file=2), out)
    )
    assert report.succeeded == 3   # 1-2, 3-4, 5
    assert len(PdfReader(str(out / "手册_第1-2页.pdf")).pages) == 2
    assert len(PdfReader(str(out / "手册_第5页.pdf")).pages) == 1


def test_按指定范围拆分(tmp_path):
    src = make_pdf(tmp_path / "报告.pdf", 10)
    out = tmp_path / "输出"
    opts = SplitOptions(SplitMode.RANGES, ranges_text="1-2,5,9-10")
    report = pdf_job.execute_split(pdf_job.plan_split([src], opts, out))
    assert report.succeeded == 3
    assert len(PdfReader(str(out / "报告_第1-2页.pdf")).pages) == 2
    assert len(PdfReader(str(out / "报告_第9-10页.pdf")).pages) == 2


def test_损坏的PDF被跳过不影响其它(tmp_path):
    good = make_pdf(tmp_path / "正常.pdf", 2)
    bad = tmp_path / "损坏.pdf"
    bad.write_bytes(b"%PDF-1.4 this is broken")
    out = tmp_path / "输出"

    report = pdf_job.execute_split(
        pdf_job.plan_split([good, bad], SplitOptions(SplitMode.EVERY_PAGE), out)
    )
    assert report.succeeded == 2
    assert len(report.skipped) == 1
    assert "损坏" in report.skipped[0][1] or "无法打开" in report.skipped[0][1]


def test_加密PDF被跳过并说明原因(tmp_path):
    src = tmp_path / "加密.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    writer.encrypt("secret")
    with open(src, "wb") as f:
        writer.write(f)

    actions = pdf_job.plan_split([src], SplitOptions(SplitMode.EVERY_PAGE), tmp_path / "out")
    assert actions[0].skip_reason and "加密" in actions[0].skip_reason


def test_非PDF文件被跳过(tmp_path):
    f = tmp_path / "说明.txt"
    f.write_text("hi", encoding="utf-8")
    actions = pdf_job.plan_split([f], SplitOptions(), tmp_path / "out")
    assert actions[0].skip_reason == "不是 PDF 文件"


# ---------- 合并 ----------

def test_合并多个PDF(tmp_path):
    a = make_pdf(tmp_path / "第一部分.pdf", 2)
    b = make_pdf(tmp_path / "第二部分.pdf", 3)
    target = tmp_path / "输出" / "合并结果.pdf"

    report = pdf_job.execute_merge(pdf_job.plan_merge([a, b], target), target)
    assert report.succeeded == 2
    assert len(PdfReader(str(target)).pages) == 5
    assert a.exists() and b.exists()


def test_合并时跳过坏文件但其余照常合并(tmp_path):
    a = make_pdf(tmp_path / "a.pdf", 2)
    bad = tmp_path / "坏.pdf"
    bad.write_bytes(b"not a pdf at all")
    c = make_pdf(tmp_path / "c.pdf", 1)
    target = tmp_path / "输出" / "合并.pdf"

    report = pdf_job.execute_merge(pdf_job.plan_merge([a, bad, c], target), target)
    assert report.succeeded == 2
    assert len(report.skipped) == 1
    assert len(PdfReader(str(target)).pages) == 3


def test_合并时不覆盖已存在的输出文件(tmp_path):
    a = make_pdf(tmp_path / "a.pdf", 1)
    out = tmp_path / "输出"
    out.mkdir()
    existing = out / "合并.pdf"
    existing.write_bytes(b"original content")

    report = pdf_job.execute_merge(pdf_job.plan_merge([a], existing), existing)
    assert report.succeeded == 1
    assert existing.read_bytes() == b"original content", "已有文件绝不能被覆盖"
    assert (out / "合并_1.pdf").exists()
    assert report.items[0].target == out / "合并_1.pdf", "结果里要回填真正写入的文件名"


def test_预览显示每个文件贡献多少页(tmp_path):
    a = make_pdf(tmp_path / "a.pdf", 7)
    actions = pdf_job.plan_merge([a], tmp_path / "out.pdf")
    assert "贡献 7 页" in actions[0].note

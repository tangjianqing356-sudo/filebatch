from pathlib import Path

from filebatch.core import text_job
from filebatch.core.text_job import ReplaceOptions, count_and_replace, looks_binary, read_text


def test_普通替换计数():
    content = "价格 100 元，原价 100 元"
    new, n = count_and_replace(content, ReplaceOptions(find="100", replace="200"))
    assert new == "价格 200 元，原价 200 元"
    assert n == 2


def test_没有匹配时计数为零():
    new, n = count_and_replace("abc", ReplaceOptions(find="xyz", replace="1"))
    assert n == 0 and new == "abc"


def test_不区分大小写():
    new, n = count_and_replace("Hello HELLO hello", ReplaceOptions(find="hello", replace="hi", case_sensitive=False))
    assert n == 3 and new == "hi hi hi"


def test_区分大小写是默认行为():
    new, n = count_and_replace("Hello HELLO hello", ReplaceOptions(find="hello", replace="hi"))
    assert n == 1 and new == "Hello HELLO hi"


def test_正则替换():
    opts = ReplaceOptions(find=r"\d{4}-\d{2}-\d{2}", replace="[日期]", use_regex=True)
    new, n = count_and_replace("2026-01-01 和 2026-12-31", opts)
    assert n == 2 and new == "[日期] 和 [日期]"


def test_正则分组引用():
    opts = ReplaceOptions(find=r"(\w+)@(\w+)\.com", replace=r"\2 的 \1", use_regex=True)
    new, n = count_and_replace("联系 zhang@abc.com", opts)
    assert n == 1 and "abc 的 zhang" in new


def test_参数校验():
    assert "请填写要查找的内容" in (ReplaceOptions().validate() or "")
    assert "正则表达式有误" in (ReplaceOptions(find="[未闭合", use_regex=True).validate() or "")
    assert ReplaceOptions(find="a").validate() is None


def test_识别二进制文件():
    assert looks_binary(b"PK\x03\x04\x00\x00")
    assert not looks_binary("纯中文文本".encode("utf-8"))


def test_读取utf8和gbk文件(tmp_path):
    u = tmp_path / "utf8.txt"
    u.write_text("你好世界", encoding="utf-8")
    assert read_text(u) == ("你好世界", "utf-8")

    g = tmp_path / "gbk.txt"
    g.write_bytes("你好世界".encode("gb18030"))
    content, enc = read_text(g)
    assert content == "你好世界" and enc == "gb18030"


def test_替换后输出到新目录且保留原文件(tmp_path):
    src = tmp_path / "源"
    src.mkdir()
    f = src / "说明.txt"
    f.write_text("旧公司名 出品", encoding="utf-8")

    out = tmp_path / "输出"
    opts = ReplaceOptions(find="旧公司名", replace="新公司名")
    report = text_job.execute(text_job.plan_replace([f], opts, out), opts)

    assert report.succeeded == 1
    assert f.read_text(encoding="utf-8") == "旧公司名 出品", "原文件必须不变"
    assert (out / "说明.txt").read_text(encoding="utf-8") == "新公司名 出品"


def test_预览显示将替换多少处(tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("x x x", encoding="utf-8")
    actions = text_job.plan_replace([f], ReplaceOptions(find="x", replace="y"), tmp_path / "out")
    assert "将替换 3 处" in actions[0].note


def test_没有匹配的文件在计划阶段就被跳过(tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("完全无关的内容", encoding="utf-8")
    actions = text_job.plan_replace([f], ReplaceOptions(find="找不到", replace="y"), tmp_path / "out")
    assert actions[0].skip_reason == "没有匹配到要替换的内容"


def test_二进制文件被跳过不会写坏(tmp_path):
    f = tmp_path / "程序.bin"
    f.write_bytes(b"\x00\x01\x02binary\x00data")
    actions = text_job.plan_replace([f], ReplaceOptions(find="binary", replace="x"), tmp_path / "out")
    assert actions[0].skip_reason and "不是文本文件" in actions[0].skip_reason


def test_gbk文件替换后仍然是gbk(tmp_path):
    f = tmp_path / "gbk.txt"
    f.write_bytes("旧名称 报告".encode("gb18030"))
    out = tmp_path / "输出"
    opts = ReplaceOptions(find="旧名称", replace="新名称")
    report = text_job.execute(text_job.plan_replace([f], opts, out), opts)

    assert report.succeeded == 1
    written = (out / "gbk.txt").read_bytes()
    assert written.decode("gb18030") == "新名称 报告"


def test_原地替换会改动原文件(tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("原内容", encoding="utf-8")
    opts = ReplaceOptions(find="原内容", replace="新内容", in_place=True)
    report = text_job.execute(text_job.plan_replace([f], opts, None), opts)
    assert report.succeeded == 1
    assert f.read_text(encoding="utf-8") == "新内容"


def test_一个文件失败不影响其它(tmp_path):
    out = tmp_path / "输出"
    files = []
    for i in range(3):
        f = tmp_path / f"{i}.txt"
        f.write_text("目标词", encoding="utf-8")
        files.append(f)
    opts = ReplaceOptions(find="目标词", replace="新词")
    actions = text_job.plan_replace(files, opts, out)
    files[1].unlink()

    report = text_job.execute(actions, opts)
    assert report.succeeded == 2 and report.failed == 1


def test_普通utf8文件不会被凭空加上BOM(tmp_path):
    """回归测试：utf-8-sig 能解码无 BOM 的 UTF-8，早期版本因此给每个文件都加了 BOM。"""
    f = tmp_path / "a.txt"
    f.write_text("目标词", encoding="utf-8")
    assert not f.read_bytes().startswith(b"\xef\xbb\xbf")

    out = tmp_path / "输出"
    opts = ReplaceOptions(find="目标词", replace="新词")
    text_job.execute(text_job.plan_replace([f], opts, out), opts)

    written = (out / "a.txt").read_bytes()
    assert not written.startswith(b"\xef\xbb\xbf"), "不能给原本没有 BOM 的文件加上 BOM"
    assert written.decode("utf-8") == "新词"


def test_原本有BOM的文件写回后保留BOM(tmp_path):
    f = tmp_path / "b.txt"
    f.write_bytes(b"\xef\xbb\xbf" + "目标词".encode("utf-8"))
    out = tmp_path / "输出"
    opts = ReplaceOptions(find="目标词", replace="新词")
    text_job.execute(text_job.plan_replace([f], opts, out), opts)

    written = (out / "b.txt").read_bytes()
    assert written.startswith(b"\xef\xbb\xbf"), "原本有 BOM 的要保留"
    assert written.decode("utf-8-sig") == "新词"

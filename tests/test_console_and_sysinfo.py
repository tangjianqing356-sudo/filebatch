"""控制台编码与跨平台内存读取。

这两项都是"在 Mac 上跑得好好的、一到 Windows CI 就崩"的典型：
  - Windows 控制台默认 GBK/cp1252，打印中文抛 UnicodeEncodeError；
  - resource 模块是 POSIX 专属的，Windows 上 import 就失败。
"""
import io
import os
import subprocess
import sys
from pathlib import Path

import pytest

from filebatch.console import ensure_utf8_output
from filebatch.sysinfo import peak_memory_mb

ROOT = Path(__file__).resolve().parent.parent


# ---------------- 控制台编码 ----------------

def test_把非UTF8的流切成UTF8(monkeypatch):
    buf = io.TextIOWrapper(io.BytesIO(), encoding="cp1252")
    monkeypatch.setattr(sys, "stdout", buf)

    ensure_utf8_output()
    assert buf.encoding.lower().replace("-", "") == "utf8"


def test_已经是UTF8就不动(monkeypatch):
    buf = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
    monkeypatch.setattr(sys, "stdout", buf)

    ensure_utf8_output()
    assert buf.encoding.lower().replace("-", "") == "utf8"


def test_stdout是None时不崩溃(monkeypatch):
    """打包成窗口程序时 sys.stdout 可能是 None，这个函数自己绝不能成为崩溃点。"""
    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "stderr", None)
    ensure_utf8_output()      # 不抛异常就算过


def test_流不支持reconfigure时不崩溃(monkeypatch):
    class 老式流:
        encoding = "cp936"

    monkeypatch.setattr(sys, "stdout", 老式流())
    ensure_utf8_output()


@pytest.mark.parametrize("编码", ["cp1252", "cp936"])
def test_子进程在Windows典型编码下能正常输出中文(编码):
    """直接复现 CI 场景：输出被重定向到管道，且控制台编码不是 UTF-8。

    修之前 cp1252 会 UnicodeEncodeError 崩掉，cp936 会输出乱码。
    """
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = 编码
    env["QT_QPA_PLATFORM"] = "offscreen"
    env["PYTHONPATH"] = str(ROOT / "src")

    r = subprocess.run(
        [sys.executable, "-m", "filebatch", "--selftest"],
        env=env, capture_output=True, cwd=str(ROOT), timeout=180,
    )
    out = r.stdout.decode("utf-8", errors="replace")

    assert r.returncode == 0, f"退出码 {r.returncode}\n{r.stderr.decode('utf-8', 'replace')[-800:]}"
    assert "UnicodeEncodeError" not in r.stderr.decode("utf-8", errors="replace")
    assert "打包产物自检" in out, "中文必须原样输出，不能是乱码"
    assert "失败 0 项" in out


# ---------------- 跨平台内存 ----------------

def test_能读到内存占用():
    mb = peak_memory_mb()
    assert mb > 0, "应该能读到一个正数"
    assert mb < 100_000, f"数值明显不合理：{mb} MB"


def test_不依赖POSIX专属的resource模块():
    """sysinfo 必须能在没有 resource 模块的环境（Windows）里工作。"""
    src = (ROOT / "src" / "filebatch" / "sysinfo.py").read_text(encoding="utf-8")
    顶层导入 = [
        l for l in src.splitlines()
        if l.startswith("import resource") or l.startswith("from resource")
    ]
    assert not 顶层导入, "resource 只能在 POSIX 分支里按需导入，不能放在模块顶层"


def test_主入口不在顶层导入resource():
    src = (ROOT / "src" / "filebatch" / "__main__.py").read_text(encoding="utf-8")
    assert "import resource" not in src, "__main__ 不能再直接用 POSIX 专属的 resource"

"""控制台输出编码修正。

Windows 的控制台默认编码是 GBK(cp936) 或 cp1252，Python 往管道里打中文时
会直接抛 UnicodeEncodeError 把程序搞崩，或者输出一堆乱码。

这在两个场景会真实发生：
  1. CI 里跑 --selftest / --acceptance，输出被重定向到管道；
  2. 用户在 cmd.exe 里运行 exe 排查问题。

所以修在程序自己身上，而不是只在 CI 里加个环境变量——后者只能救 CI 救不了用户。
"""
from __future__ import annotations

import sys


def ensure_utf8_output() -> None:
    """把 stdout / stderr 切成 UTF-8。已经是 UTF-8 就什么都不做。

    打包成窗口程序时 sys.stdout 可能是 None，所以每一步都要能容错——
    这个函数自己绝不能成为崩溃点。
    """
    for name in ("stdout", "stderr"):
        stream = getattr(sys, name, None)
        if stream is None:
            continue
        编码 = (getattr(stream, "encoding", "") or "").lower().replace("-", "").replace("_", "")
        if 编码 == "utf8":
            continue
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            # errors="replace"：万一某个字符还是写不出去，也只是显示成问号，
            # 绝不能因为打日志把主流程弄崩
            reconfigure(encoding="utf-8", errors="replace")
        except (OSError, ValueError):
            pass

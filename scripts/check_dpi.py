"""不同缩放比例下的布局检查 + 截图。

Windows 常见 125% / 150%，Mac Retina 相当于 2x。
用 QT_SCALE_FACTOR 模拟，检查关键控件有没有被压到文字截断，并各存一张图。

默认用当前解释器跑源码；传 --exe <可执行文件> 就改成驱动**打包后的程序**，
这样 CI 里能直接拿到 Windows 真实渲染的各 DPI 截图。
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from filebatch.console import ensure_utf8_output  # noqa: E402

ensure_utf8_output()
OUT = ROOT / "docs" / "screenshots" / "dpi"
OUT.mkdir(parents=True, exist_ok=True)

CHILD = r'''
import os, sys
sys.path.insert(0, %r)
from filebatch.ui.app import create_app
from filebatch.ui.main_window import MainWindow
app = create_app([])
win = MainWindow(); win.show()
for _ in range(8): app.processEvents()
page = win.page_at(0)

问题 = []
def 检查(name, w):
    if w is None: return
    需要 = w.sizeHint().width()
    实际 = w.width()
    if 实际 > 0 and 实际 + 1 < 需要:
        问题.append(f"{name}: 实际 {实际}px < 需要 {需要}px")

for name, w in [
    ("添加文件按钮", page.file_list.btn_add_files),
    ("添加文件夹按钮", page.file_list.btn_add_folder),
    ("移除按钮", page.file_list.btn_remove),
    ("清空按钮", page.file_list.btn_clear),
    ("生成预览按钮", page.btn_preview),
    ("开始执行按钮", page.btn_execute),
    ("选择输出文件夹", page.btn_output),
]:
    检查(name, w)

scale = os.environ.get("QT_SCALE_FACTOR", "1")
win.grab().save(%r + f"/dpi_{scale.replace('.','_')}x.png")
print(f"缩放 {scale}x | 窗口 {win.width()}x{win.height()} | 问题 {len(问题)}")
for p in 问题:
    print("   ! " + p)
'''

def main() -> int:
    exe = None
    if "--exe" in sys.argv:
        exe = sys.argv[sys.argv.index("--exe") + 1]

    src = str(ROOT / "src")
    失败 = 0
    for scale in ("1", "1.25", "1.5", "2"):
        env = dict(os.environ)
        env["QT_QPA_PLATFORM"] = "offscreen"
        env["QT_SCALE_FACTOR"] = scale
        env["QT_ENABLE_HIGHDPI_SCALING"] = "1"

        if exe:
            # 驱动打包后的程序：拿到的是真实运行环境的渲染结果
            shot = str(OUT / f"packaged_{scale.replace('.', '_')}x.png")
            cmd = [exe, "--screenshot", shot]
        else:
            # 用当前解释器，不要硬编码 .venv/bin/python——
            # Windows 上虚拟环境的解释器在 .venv/Scripts/python.exe，写死会直接挂掉
            cmd = [sys.executable, "-c", CHILD % (src, str(OUT))]

        r = subprocess.run(cmd, env=env, capture_output=True, text=True)
        out = "\n".join(
            l for l in (r.stdout + r.stderr).splitlines()
            if "qt.qpa" not in l and "propagateSizeHints" not in l and "IMKCF" not in l
        ).strip()
        print(f"[{scale}x] {out}")
        if r.returncode != 0:
            失败 += 1
    return 1 if 失败 else 0


if __name__ == "__main__":
    sys.exit(main())

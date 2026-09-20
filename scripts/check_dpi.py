"""不同缩放比例下的布局检查。

Windows 常见 125% / 150%，Mac Retina 相当于 2x。
用 QT_SCALE_FACTOR 模拟，检查关键控件有没有被压到文字截断。
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
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
    src = str(ROOT / "src")
    for scale in ("1", "1.25", "1.5", "2"):
        env = dict(os.environ)
        env["QT_QPA_PLATFORM"] = "offscreen"
        env["QT_SCALE_FACTOR"] = scale
        env["QT_ENABLE_HIGHDPI_SCALING"] = "1"
        code = CHILD % (src, str(OUT))
        r = subprocess.run(
            [str(ROOT / ".venv/bin/python"), "-c", code],
            env=env, capture_output=True, text=True,
        )
        out = "\n".join(
            l for l in (r.stdout + r.stderr).splitlines()
            if "qt.qpa" not in l and "propagateSizeHints" not in l
        )
        print(out.strip())
    return 0


if __name__ == "__main__":
    sys.exit(main())

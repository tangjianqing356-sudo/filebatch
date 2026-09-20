"""生成应用图标。

用 Pillow 画一张 1024 的母图，再切出 macOS 的 .icns 和 Windows 的 .ico。
不引入额外依赖，也不需要设计软件。

图形含义：一叠文件 + 一个向右的箭头 = 批量处理。
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from filebatch.console import ensure_utf8_output  # noqa: E402

ensure_utf8_output()
ICON_DIR = ROOT / "packaging" / "icon"
ICON_DIR.mkdir(parents=True, exist_ok=True)

BG_TOP = (59, 130, 246)     # 蓝
BG_BOTTOM = (37, 99, 235)
PAPER = (255, 255, 255)
PAPER_DIM = (219, 234, 254)
ACCENT = (250, 204, 21)     # 箭头用暖色，和蓝底拉开对比


def 圆角矩形遮罩(size: int, radius: int) -> Image.Image:
    mask = Image.new("L", (size, size), 0)
    d = ImageDraw.Draw(mask)
    d.rounded_rectangle([0, 0, size - 1, size - 1], radius=radius, fill=255)
    return mask


def 画母图(size: int = 1024) -> Image.Image:
    # 竖直渐变底
    bg = Image.new("RGB", (1, size))
    for y in range(size):
        t = y / max(1, size - 1)
        bg.putpixel((0, y), tuple(
            round(BG_TOP[i] + (BG_BOTTOM[i] - BG_TOP[i]) * t) for i in range(3)
        ))
    bg = bg.resize((size, size))

    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    img.paste(bg, (0, 0), 圆角矩形遮罩(size, int(size * 0.22)))

    d = ImageDraw.Draw(img)
    u = size / 100.0   # 便于按百分比布局

    # 后面两张纸（错开露出边缘，表示"一批"）
    d.rounded_rectangle([22 * u, 20 * u, 58 * u, 72 * u], radius=3 * u, fill=PAPER_DIM)
    d.rounded_rectangle([17 * u, 25 * u, 53 * u, 77 * u], radius=3 * u, fill=PAPER_DIM)
    # 最前面一张
    d.rounded_rectangle([12 * u, 30 * u, 48 * u, 82 * u], radius=3 * u, fill=PAPER)

    # 纸上的文字线条
    for i, (x0, x1) in enumerate([(18, 42), (18, 40), (18, 43), (18, 36)]):
        y = (39 + i * 8) * u
        d.rounded_rectangle([x0 * u, y, x1 * u, y + 2.6 * u], radius=1.3 * u, fill=(148, 163, 184))

    # 向右的箭头
    ay = 56 * u
    d.rounded_rectangle([54 * u, ay - 4 * u, 78 * u, ay + 4 * u], radius=4 * u, fill=ACCENT)
    d.polygon([(74 * u, ay - 13 * u), (90 * u, ay), (74 * u, ay + 13 * u)], fill=ACCENT)

    return img


def 生成icns(master: Image.Image) -> Path | None:
    iconset = ICON_DIR / "app.iconset"
    if iconset.exists():
        for f in iconset.iterdir():
            f.unlink()
    iconset.mkdir(parents=True, exist_ok=True)

    for px in (16, 32, 64, 128, 256, 512, 1024):
        master.resize((px, px), Image.LANCZOS).save(iconset / f"icon_{px}x{px}.png")
        if px <= 512:
            master.resize((px * 2, px * 2), Image.LANCZOS).save(
                iconset / f"icon_{px}x{px}@2x.png"
            )

    icns = ICON_DIR / "app.icns"
    r = subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", str(icns)],
                       capture_output=True, text=True)
    if r.returncode != 0:
        print("  iconutil 失败：", r.stderr.strip())
        return None
    return icns


def 生成ico(master: Image.Image) -> Path:
    ico = ICON_DIR / "app.ico"
    master.save(ico, format="ICO",
                sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    return ico


def main() -> int:
    master = 画母图()
    png = ICON_DIR / "app_1024.png"
    master.save(png)
    print(f"  母图     {png.relative_to(ROOT)}")

    ico = 生成ico(master)
    print(f"  Windows  {ico.relative_to(ROOT)}  ({ico.stat().st_size / 1024:.0f} KB)")

    if sys.platform == "darwin":
        icns = 生成icns(master)
        if icns:
            print(f"  macOS    {icns.relative_to(ROOT)}  ({icns.stat().st_size / 1024:.0f} KB)")
    else:
        print("  macOS    .icns 需要在 Mac 上用 iconutil 生成，已跳过")
    return 0


if __name__ == "__main__":
    sys.exit(main())

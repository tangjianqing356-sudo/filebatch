"""图片批量改名、编号、尺寸调整、格式转换。

尺寸计算做成纯函数 compute_target_size，不依赖 Pillow，可以单独测；
真正开图只在计划阶段读一次尺寸（为了预览能显示 1920x1080 -> 800x450）和执行阶段做一次。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Callable

from .naming import NameRule, sanitize_filename
from .oserrors import describe as 说明错误
from .result import JobReport, PlannedAction
from .safety import unique_path

# Pillow 能认、我们也愿意处理的格式
SUPPORTED_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp", ".tiff", ".tif"}

# 输出格式 -> Pillow 的 format 名和扩展名
OUTPUT_FORMATS: dict[str, tuple[str, str]] = {
    "jpg": ("JPEG", ".jpg"),
    "png": ("PNG", ".png"),
    "webp": ("WEBP", ".webp"),
    "bmp": ("BMP", ".bmp"),
}


class ResizeMode(str, Enum):
    NONE = "none"            # 不改尺寸
    MAX_SIDE = "max_side"    # 限制最长边
    WIDTH = "width"          # 指定宽度，高度按比例
    HEIGHT = "height"        # 指定高度，宽度按比例
    PERCENT = "percent"      # 按百分比缩放
    FIT_BOX = "fit_box"      # 等比缩放到刚好放进 宽x高 的框里


@dataclass
class ImageOptions:
    rule: NameRule = field(default_factory=NameRule)
    resize_mode: ResizeMode = ResizeMode.NONE
    resize_value: int = 0        # 像素或百分比，看 resize_mode
    box_width: int = 0
    box_height: int = 0
    allow_upscale: bool = False  # 默认不放大：放大只会糊，没意义
    output_format: str = ""      # 留空保持原格式
    jpeg_quality: int = 90

    def __post_init__(self) -> None:
        # 同 NameRule：防止 Qt 的 QVariant 把 str 枚举退化成普通字符串
        if not isinstance(self.resize_mode, ResizeMode):
            try:
                self.resize_mode = ResizeMode(self.resize_mode)
            except ValueError:
                self.resize_mode = ResizeMode.NONE

    def validate(self) -> str | None:
        rule_err = self.rule.validate()
        if rule_err:
            return rule_err
        if self.resize_mode in (ResizeMode.MAX_SIDE, ResizeMode.WIDTH, ResizeMode.HEIGHT):
            if self.resize_value <= 0:
                return "请填写大于 0 的像素值"
            if self.resize_value > 30000:
                return "像素值过大（上限 30000）"
        if self.resize_mode is ResizeMode.PERCENT:
            if not (1 <= self.resize_value <= 1000):
                return "缩放百分比需要在 1~1000 之间"
        if self.resize_mode is ResizeMode.FIT_BOX:
            if self.box_width <= 0 or self.box_height <= 0:
                return "请填写大于 0 的宽和高"
        if self.output_format and self.output_format.lower() not in OUTPUT_FORMATS:
            return f"不支持的输出格式：{self.output_format}"
        if not (1 <= self.jpeg_quality <= 100):
            return "JPEG 质量需要在 1~100 之间"
        return None


def compute_target_size(
    width: int,
    height: int,
    mode: ResizeMode,
    value: int,
    allow_upscale: bool = False,
    box_width: int = 0,
    box_height: int = 0,
) -> tuple[int, int]:
    """算出目标尺寸。纯函数，不碰图片文件。始终保持宽高比，边长至少为 1。"""
    if width <= 0 or height <= 0:
        return width, height
    if mode is ResizeMode.NONE:
        return width, height

    if mode is ResizeMode.PERCENT:
        ratio = value / 100.0
    elif mode is ResizeMode.MAX_SIDE:
        longest = max(width, height)
        ratio = value / longest
    elif mode is ResizeMode.WIDTH:
        ratio = value / width
    elif mode is ResizeMode.HEIGHT:
        ratio = value / height
    elif mode is ResizeMode.FIT_BOX:
        ratio = min(box_width / width, box_height / height)
    else:
        return width, height

    if not allow_upscale and ratio > 1:
        return width, height

    return max(1, round(width * ratio)), max(1, round(height * ratio))


def _read_size(path: Path) -> tuple[int, int] | None:
    try:
        from PIL import Image

        with Image.open(path) as im:
            return im.size
    except Exception:
        return None


def plan_images(
    files: list[Path],
    options: ImageOptions,
    output_dir: Path,
) -> list[PlannedAction]:
    """计划阶段会读一次图片尺寸，这样预览里能直接看到 1920x1080 -> 800x450。"""
    actions: list[PlannedAction] = []
    taken: set[Path] = set()

    for index, src in enumerate(files):
        if src.suffix.lower() not in SUPPORTED_SUFFIXES:
            actions.append(
                PlannedAction(src, None, "处理图片", skip_reason=f"不支持的图片格式：{src.suffix}")
            )
            continue

        size = _read_size(src)
        if size is None:
            actions.append(
                PlannedAction(src, None, "处理图片", skip_reason="无法读取，可能不是图片或文件已损坏")
            )
            continue

        try:
            new_stem = sanitize_filename(options.rule.apply(src.stem, index))
            if options.output_format:
                new_suffix = OUTPUT_FORMATS[options.output_format.lower()][1]
            else:
                new_suffix = options.rule.resolve_extension(src.suffix)

            raw_target = output_dir / f"{new_stem}{new_suffix}"
            target = unique_path(raw_target, taken)
            taken.add(target)

            w, h = size
            tw, th = compute_target_size(
                w, h, options.resize_mode, options.resize_value,
                options.allow_upscale, options.box_width, options.box_height,
            )
            if (tw, th) == (w, h):
                note = f"{w}x{h}（尺寸不变）"
            else:
                note = f"{w}x{h} -> {tw}x{th}"
            if target.name != raw_target.name:
                note += f"；目标重名，自动改为 {target.name}"

            actions.append(PlannedAction(src, target, "处理图片", note))
        except Exception as e:
            actions.append(PlannedAction(src, None, "处理图片", skip_reason=f"生成计划失败：{e}"))

    return actions


def execute(
    actions: list[PlannedAction],
    options: ImageOptions,
    on_progress: Callable[[int, int, str], None] | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> JobReport:
    """执行图片处理计划。每张图独立 try，一张坏图不影响其余。

    :param on_progress: 每处理完一项回调 (已完成数, 总数, 当前文件名)，供界面显示进度
    :param should_cancel: 返回 True 表示用户要求中断。
        中断只影响**尚未执行**的项目，已经处理完的文件原样保留，不做任何回滚。
    """
    report = JobReport("图片批量处理")
    try:
        from PIL import Image, ImageOps
    except ImportError:
        for act in actions:
            report.add_fail(act.source, "缺少 Pillow 库，无法处理图片")
        return report.finish()
    total = len(actions)

    for done, act in enumerate(actions):
        if should_cancel is not None and should_cancel():
            for rest in actions[done:]:
                report.add_skip(rest.source, "用户中断任务，此项未执行")
            break
        if not act.will_run:
            report.add_skip(act.source, act.skip_reason or "未说明")
            continue
        try:
            assert act.target is not None
            act.target.parent.mkdir(parents=True, exist_ok=True)

            with Image.open(act.source) as im:
                # 手机照片常带 EXIF 旋转信息，不处理会导致输出图片躺倒
                im = ImageOps.exif_transpose(im)
                w, h = im.size
                tw, th = compute_target_size(
                    w, h, options.resize_mode, options.resize_value,
                    options.allow_upscale, options.box_width, options.box_height,
                )
                if (tw, th) != (w, h):
                    im = im.resize((tw, th), Image.LANCZOS)

                fmt = None
                save_kwargs: dict = {}
                if options.output_format:
                    fmt = OUTPUT_FORMATS[options.output_format.lower()][0]

                target_is_jpeg = act.target.suffix.lower() in (".jpg", ".jpeg") or fmt == "JPEG"
                if target_is_jpeg:
                    # JPEG 不支持透明通道，带 alpha 的图直接存会报错
                    if im.mode in ("RGBA", "LA", "P"):
                        background = Image.new("RGB", im.size, (255, 255, 255))
                        converted = im.convert("RGBA")
                        background.paste(converted, mask=converted.split()[-1])
                        im = background
                    elif im.mode != "RGB":
                        im = im.convert("RGB")
                    save_kwargs["quality"] = options.jpeg_quality
                    save_kwargs["optimize"] = True

                im.save(act.target, format=fmt, **save_kwargs)

            report.add_ok(act.source, act.target, act.note)
        except PermissionError:
            report.add_fail(act.source, "没有权限访问该文件，可能被其它程序占用")
        except FileNotFoundError as e:
            report.add_fail(act.source, 说明错误(e, act.source))
        except OSError as e:
            report.add_fail(act.source, f"图片读写失败：{说明错误(e, act.source)}")
        except Exception as e:
            report.add_fail(act.source, f"未知错误：{type(e).__name__} {e}")

        if on_progress is not None:
            on_progress(done + 1, total, act.source.name)

    return report.finish()

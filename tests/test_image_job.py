from pathlib import Path

import pytest
from PIL import Image

from filebatch.core import image_job
from filebatch.core.image_job import ImageOptions, ResizeMode, compute_target_size
from filebatch.core.naming import NameRule, NumberPosition


# ---------- 纯函数：尺寸计算 ----------

def test_不改尺寸():
    assert compute_target_size(1920, 1080, ResizeMode.NONE, 0) == (1920, 1080)


def test_限制最长边():
    assert compute_target_size(1920, 1080, ResizeMode.MAX_SIDE, 800) == (800, 450)
    assert compute_target_size(1080, 1920, ResizeMode.MAX_SIDE, 800) == (450, 800)


def test_指定宽度高度按比例():
    assert compute_target_size(1920, 1080, ResizeMode.WIDTH, 960) == (960, 540)
    assert compute_target_size(1920, 1080, ResizeMode.HEIGHT, 540) == (960, 540)


def test_百分比缩放():
    assert compute_target_size(1000, 500, ResizeMode.PERCENT, 50) == (500, 250)


def test_默认不放大():
    # 原图 400 宽，要求 800，默认不放大所以保持原样
    assert compute_target_size(400, 300, ResizeMode.WIDTH, 800) == (400, 300)
    assert compute_target_size(400, 300, ResizeMode.WIDTH, 800, allow_upscale=True) == (800, 600)


def test_放进指定框里保持比例():
    assert compute_target_size(1920, 1080, ResizeMode.FIT_BOX, 0, box_width=800, box_height=800) == (800, 450)
    assert compute_target_size(1080, 1920, ResizeMode.FIT_BOX, 0, box_width=800, box_height=800) == (450, 800)


def test_极端缩小时边长至少为1():
    w, h = compute_target_size(1000, 10, ResizeMode.PERCENT, 1)
    assert w >= 1 and h >= 1


def test_参数校验():
    assert "大于 0" in (ImageOptions(resize_mode=ResizeMode.WIDTH, resize_value=0).validate() or "")
    assert "百分比" in (ImageOptions(resize_mode=ResizeMode.PERCENT, resize_value=0).validate() or "")
    assert "不支持的输出格式" in (ImageOptions(output_format="tga").validate() or "")
    assert "JPEG 质量" in (ImageOptions(jpeg_quality=0).validate() or "")
    assert ImageOptions().validate() is None


# ---------- 真实图片处理 ----------

@pytest.fixture
def 样例图片(tmp_path: Path) -> list[Path]:
    src = tmp_path / "照片"
    src.mkdir()
    files = []
    for i, (w, h) in enumerate([(1200, 800), (800, 1200), (400, 400)], start=1):
        f = src / f"IMG_{i:04d}.jpg"
        Image.new("RGB", (w, h), (120, 160, 200)).save(f)
        files.append(f)
    return files


def test_批量改名编号并缩放(样例图片, tmp_path):
    out = tmp_path / "输出"
    opts = ImageOptions(
        rule=NameRule(base_name="产品图", number_position=NumberPosition.SUFFIX, number_digits=2),
        resize_mode=ResizeMode.MAX_SIDE,
        resize_value=600,
    )
    report = image_job.execute(image_job.plan_images(样例图片, opts, out), opts)

    assert report.succeeded == 3
    assert report.failed == 0
    assert sorted(p.name for p in out.iterdir()) == ["产品图_01.jpg", "产品图_02.jpg", "产品图_03.jpg"]
    with Image.open(out / "产品图_01.jpg") as im:
        assert im.size == (600, 400)
    for f in 样例图片:
        assert f.exists(), "原图必须保留"


def test_预览里能看到尺寸变化(样例图片, tmp_path):
    opts = ImageOptions(resize_mode=ResizeMode.MAX_SIDE, resize_value=600)
    actions = image_job.plan_images(样例图片, opts, tmp_path / "输出")
    assert "1200x800 -> 600x400" in actions[0].note
    assert "400x400（尺寸不变）" in actions[2].note, "小图默认不放大"


def test_带透明通道的png转jpg不会报错(tmp_path):
    src = tmp_path / "logo.png"
    Image.new("RGBA", (100, 100), (255, 0, 0, 128)).save(src)
    out = tmp_path / "输出"
    opts = ImageOptions(output_format="jpg")
    report = image_job.execute(image_job.plan_images([src], opts, out), opts)
    assert report.succeeded == 1
    assert (out / "logo.jpg").exists()


def test_损坏的图片被跳过而不是让整批失败(样例图片, tmp_path):
    坏图 = 样例图片[0].parent / "坏掉的.jpg"
    坏图.write_bytes(b"this is not an image")
    out = tmp_path / "输出"
    opts = ImageOptions()
    report = image_job.execute(image_job.plan_images(样例图片 + [坏图], opts, out), opts)

    assert report.succeeded == 3
    assert len(report.skipped) == 1
    assert "无法读取" in report.skipped[0][1]


def test_非图片文件被跳过(tmp_path):
    f = tmp_path / "说明.txt"
    f.write_text("hi", encoding="utf-8")
    opts = ImageOptions()
    actions = image_job.plan_images([f], opts, tmp_path / "out")
    assert actions[0].skip_reason and "不支持的图片格式" in actions[0].skip_reason

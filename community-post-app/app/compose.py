"""投稿画像の加工。収集した画像を投稿サイズに切って、帯と文字を乗せる。"""
from __future__ import annotations

import io
from datetime import datetime

from PIL import Image, ImageDraw, ImageFont

from . import censor, config
from .censor import Box

PRESETS: dict[str, tuple[int, int]] = {
    "square": (1080, 1080),   # コミュニティ投稿の定番
    "wide": (1280, 720),      # 16:9
    "portrait": (1080, 1350),# 4:5
}
FOCUS_OFFSETS = {"top": 0.0, "center": 0.5, "bottom": 1.0}


def _font(size: int) -> ImageFont.FreeTypeFont:
    path = config.resolve_font()
    if path:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            pass
    return ImageFont.load_default()


def _wrap(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    """日本語向けの折り返し。単語境界がないので1文字ずつ幅を測って詰める。"""
    lines: list[str] = []
    for paragraph in text.splitlines():
        if not paragraph:
            lines.append("")
            continue
        current = ""
        for char in paragraph:
            trial = current + char
            if font.getlength(trial) <= max_width or not current:
                current = trial
            else:
                lines.append(current)
                current = char
        lines.append(current)
    return lines


def cover_crop(im: Image.Image, size: tuple[int, int], focus: str = "center") -> Image.Image:
    """アスペクト比を保ったまま指定サイズいっぱいに切り抜く（余白なし）。"""
    target_w, target_h = size
    src_w, src_h = im.size
    scale = max(target_w / src_w, target_h / src_h)
    new_w, new_h = max(1, round(src_w * scale)), max(1, round(src_h * scale))
    im = im.resize((new_w, new_h), Image.LANCZOS)
    offset = FOCUS_OFFSETS.get(focus, 0.5)
    left = round((new_w - target_w) / 2)
    top = round((new_h - target_h) * offset)
    return im.crop((left, top, left + target_w, top + target_h))


def _draw_band(
    im: Image.Image,
    text: str,
    *,
    height_ratio: float = 0.22,
    bg=(0, 0, 0, 255),
    fg=(255, 255, 255),
) -> Image.Image:
    """下部に半透明の帯を敷いてキャプションを書く。"""
    width, height = im.size
    band_h = max(80, int(height * height_ratio))
    font_size = max(22, int(band_h * 0.26))
    font = _font(font_size)
    padding = int(width * 0.045)

    lines = _wrap(text, font, width - padding * 2)
    line_h = int(font_size * 1.35)
    # 行数が多いときは帯を伸ばす
    band_h = max(band_h, line_h * len(lines) + padding * 2)

    overlay = Image.new("RGBA", (width, band_h), bg)
    draw = ImageDraw.Draw(overlay)
    y = (band_h - line_h * len(lines)) // 2
    for line in lines:
        draw.text((padding, y), line, font=font, fill=fg)
        y += line_h

    base = im.convert("RGBA")
    base.alpha_composite(overlay, (0, height - band_h))
    return base


def _draw_badge(im: Image.Image, text: str) -> Image.Image:
    """左上に作品名・話数のバッジを置く。"""
    width, _ = im.size
    font_size = max(20, int(width * 0.038))
    font = _font(font_size)
    pad_x, pad_y = int(font_size * 0.6), int(font_size * 0.35)
    text_w = int(font.getlength(text))
    box = (int(width * 0.035), int(width * 0.035))
    badge = Image.new("RGBA", (text_w + pad_x * 2, font_size + pad_y * 2), (255, 92, 0, 235))
    ImageDraw.Draw(badge).text((pad_x, pad_y), text, font=font, fill=(255, 255, 255))
    base = im.convert("RGBA")
    base.alpha_composite(badge, box)
    return base


class CompositionError(ValueError):
    """必須の工程が満たされていないときに投げる。"""


def crop_image(image_bytes: bytes, preset: str = "square", focus: str = "center") -> Image.Image:
    """元画像を投稿サイズに切り抜いた Image を返す（検閲・帯の前段）。"""
    size = PRESETS.get(preset, PRESETS["square"])
    with Image.open(io.BytesIO(image_bytes)) as src:
        src.load()
        if src.mode not in ("RGB", "RGBA"):
            src = src.convert("RGB")
        return cover_crop(src, size, focus)


def compose(
    image_bytes: bytes,
    *,
    preset: str = "square",
    focus: str = "center",
    caption: str = "",
    badge: str = "",
    censor_boxes: list[Box] | None = None,
    censor_mode: str = "black",
    fmt: str = "JPEG",
) -> tuple[bytes, str]:
    """加工済み画像のバイト列と保存ファイル名を返す。

    トリミング → 露出部分の黒モザイク → 下部の黒帯解説文、の順で必ず通す。
    解説文が空のときは CompositionError（黒帯は必須工程のため）。
    """
    if not caption.strip():
        raise CompositionError("黒帯に入れる解説文は必須です。")

    im = crop_image(image_bytes, preset, focus)

    # 1. 露出部分を潰す（帯や バッジを描く前にやる＝帯の上から塗られないように）
    if censor_boxes:
        im = censor.apply(im, censor_boxes, mode=censor_mode)

    # 2. バッジ
    if badge:
        im = _draw_badge(im, badge)

    # 3. 下部の黒帯（必須）
    im = _draw_band(im, caption)

    buf = io.BytesIO()
    if fmt.upper() == "PNG":
        im.save(buf, "PNG", optimize=True)
        ext = "png"
    else:
        im.convert("RGB").save(buf, "JPEG", quality=92, optimize=True)
        ext = "jpg"

    name = f"post_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{preset}.{ext}"
    return buf.getvalue(), name

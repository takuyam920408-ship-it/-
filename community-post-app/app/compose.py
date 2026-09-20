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


MAX_CAPTION_LINES = 2  # 黒帯の解説文は2行まで


def _fit_lines(
    text: str,
    font_path_size: int,
    max_width: int,
    min_size: int,
    max_lines: int = MAX_CAPTION_LINES,
) -> tuple[ImageFont.FreeTypeFont, list[str], bool]:
    """max_lines 行に収まるまで文字を縮める。

    縮めても収まらなければ、最終行の末尾を「…」で詰める。
    戻り値は (フォント, 行のリスト, 詰めたかどうか)。
    """
    size = font_path_size
    while size >= min_size:
        font = _font(size)
        lines = _wrap(text, font, max_width)
        if len(lines) <= max_lines:
            return font, lines, False
        size -= 2

    font = _font(min_size)
    lines = _wrap(text, font, max_width)[:max_lines]
    if lines:
        last = lines[-1]
        while last and font.getlength(last + "…") > max_width:
            last = last[:-1]
        lines[-1] = last + "…"
    return font, lines, True


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
) -> tuple[Image.Image, bool]:
    """下部に黒帯を敷いて解説文を書く。文字は最大2行。

    2行に収まらない場合はフォントを段階的に縮め、それでも溢れたら
    末尾を「…」で詰める。戻り値は (画像, 詰めたかどうか)。
    """
    width, height = im.size
    band_h = max(80, int(height * height_ratio))
    base_size = max(22, int(band_h * 0.26))
    padding = int(width * 0.045)

    font, lines, truncated = _fit_lines(
        text, base_size, width - padding * 2, min_size=max(16, int(base_size * 0.55))
    )
    font_size = getattr(font, "size", base_size)
    line_h = int(font_size * 1.35)
    band_h = max(band_h, line_h * len(lines) + padding * 2)

    overlay = Image.new("RGBA", (width, band_h), bg)
    draw = ImageDraw.Draw(overlay)
    y = (band_h - line_h * len(lines)) // 2
    for line in lines:
        draw.text((padding, y), line, font=font, fill=fg)
        y += line_h

    base = im.convert("RGBA")
    base.alpha_composite(overlay, (0, height - band_h))
    return base, truncated


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


def measure_caption(text: str, image_width: int, height_ratio: float = 0.22) -> dict:
    """解説文が2行に収まるかを、実際の描画と同じ計算で測る（UI の事前確認用）。"""
    if not text.strip():
        return {"lines": 0, "truncated": False, "shrunk": False, "max_lines": MAX_CAPTION_LINES}
    band_h = max(80, int(image_width * height_ratio))
    base_size = max(22, int(band_h * 0.26))
    padding = int(image_width * 0.045)
    font, lines, truncated = _fit_lines(
        text, base_size, image_width - padding * 2, min_size=max(16, int(base_size * 0.55))
    )
    return {
        "lines": len(lines),
        "truncated": truncated,
        "shrunk": getattr(font, "size", base_size) < base_size,
        "max_lines": MAX_CAPTION_LINES,
        "preview": lines,
    }


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
) -> tuple[bytes, str, bool]:
    """加工済み画像のバイト列・保存ファイル名・解説文を詰めたかどうかを返す。

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

    # 3. 下部の黒帯（必須・最大2行）
    im, truncated = _draw_band(im, caption)

    buf = io.BytesIO()
    if fmt.upper() == "PNG":
        im.save(buf, "PNG", optimize=True)
        ext = "png"
    else:
        im.convert("RGB").save(buf, "JPEG", quality=92, optimize=True)
        ext = "jpg"

    name = f"post_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{preset}.{ext}"
    return buf.getvalue(), name, truncated

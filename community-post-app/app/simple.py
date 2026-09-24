"""シンプルな画像加工：スクエア変換と手動モザイク。

やることを絞ってある。
  1. 正方形に切り抜く（位置と大きさは利用者が指定する）
  2. 指定された矩形を黒／グレーで塗るか、モザイクにする
自動検出はしない。どこを隠すかは人が決める。

座標はすべて「元画像のピクセル」で受け取る。切り抜き位置を動かしても
モザイクの位置が絵からずれないよう、モザイクを先に適用してから切り抜く。
"""
from __future__ import annotations

import io
from dataclasses import dataclass

from PIL import Image, ImageFilter

OUT_SIZE = 1080          # 書き出す正方形の一辺
MIN_BOX = 2              # これ未満の矩形は無視
MOSAIC_STRENGTH = 18     # モザイクの粗さ（大きいほど粗い）

COLORS = {
    "black": (0, 0, 0),
    "gray": (128, 128, 128),
}


class RenderError(ValueError):
    """加工できないときに UI へ返すエラー。"""


@dataclass
class Crop:
    """切り抜く正方形。元画像のピクセル座標。"""

    x: int = 0
    y: int = 0
    size: int = 0

    @classmethod
    def from_dict(cls, d: dict | None, width: int, height: int) -> "Crop":
        if not d:
            return cls.centered(width, height)
        crop = cls(int(d.get("x", 0)), int(d.get("y", 0)), int(d.get("size", 0)))
        return crop.clamped(width, height)

    @classmethod
    def centered(cls, width: int, height: int) -> "Crop":
        """既定は、中央に取れる最大の正方形。"""
        size = min(width, height)
        return cls((width - size) // 2, (height - size) // 2, size)

    def clamped(self, width: int, height: int) -> "Crop":
        """画像からはみ出さない位置・大きさに収める。"""
        size = max(16, min(self.size or min(width, height), width, height))
        x = max(0, min(self.x, width - size))
        y = max(0, min(self.y, height - size))
        return Crop(x, y, size)

    def as_dict(self) -> dict:
        return {"x": self.x, "y": self.y, "size": self.size}


@dataclass
class Box:
    """隠す矩形。元画像のピクセル座標。"""

    x: int = 0
    y: int = 0
    w: int = 0
    h: int = 0

    @classmethod
    def from_dict(cls, d: dict) -> "Box":
        return cls(int(d.get("x", 0)), int(d.get("y", 0)),
                   int(d.get("w", 0)), int(d.get("h", 0)))


def _apply_boxes(
    im: Image.Image, boxes: list[Box], color: str = "black", style: str = "solid"
) -> Image.Image:
    """指定された矩形を塗りつぶすか、モザイクにする。"""
    if not boxes:
        return im
    fill = COLORS.get(color, COLORS["black"])
    out = im.convert("RGB").copy()
    width, height = out.size

    for box in boxes:
        x0 = max(0, min(width, box.x))
        y0 = max(0, min(height, box.y))
        x1 = max(0, min(width, box.x + box.w))
        y1 = max(0, min(height, box.y + box.h))
        if x1 - x0 < MIN_BOX or y1 - y0 < MIN_BOX:
            continue
        region = (x0, y0, x1, y1)

        if style == "solid":
            out.paste(fill, region)
            continue

        # モザイク: 一度縮めてから拡大し、指定色に寄せて視認性を落とす
        patch = out.crop(region)
        small_w = max(1, (x1 - x0) // MOSAIC_STRENGTH)
        small_h = max(1, (y1 - y0) // MOSAIC_STRENGTH)
        patch = patch.resize((small_w, small_h), Image.BILINEAR).resize(
            (x1 - x0, y1 - y0), Image.NEAREST
        )
        patch = Image.blend(patch, Image.new("RGB", patch.size, fill), 0.55)
        out.paste(patch, region)

    return out


def open_image(image_bytes: bytes) -> Image.Image:
    try:
        im = Image.open(io.BytesIO(image_bytes))
        im.load()
    except Exception as exc:
        raise RenderError(f"画像として読めませんでした: {exc}") from exc
    if im.mode not in ("RGB", "RGBA"):
        im = im.convert("RGB")
    return im


def render(
    image_bytes: bytes,
    *,
    crop: dict | None = None,
    boxes: list[dict] | None = None,
    color: str = "black",
    style: str = "solid",
    out_size: int = OUT_SIZE,
    fmt: str = "JPEG",
) -> tuple[bytes, str]:
    """モザイク → 正方形に切り抜き → 指定サイズ、の順で書き出す。"""
    src = open_image(image_bytes)
    width, height = src.size

    im = _apply_boxes(src, [Box.from_dict(b) for b in (boxes or [])], color, style)

    c = Crop.from_dict(crop, width, height)
    im = im.crop((c.x, c.y, c.x + c.size, c.y + c.size))
    if im.size != (out_size, out_size):
        im = im.resize((out_size, out_size), Image.LANCZOS)

    buf = io.BytesIO()
    if fmt.upper() == "PNG":
        im.convert("RGB").save(buf, "PNG", optimize=True)
        ext = "png"
    else:
        im.convert("RGB").save(buf, "JPEG", quality=92, optimize=True)
        ext = "jpg"
    return buf.getvalue(), ext

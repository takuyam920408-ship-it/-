"""露出（肌色）領域の検出と黒モザイク処理。

AI は使わない。YCbCr 色空間のしきい値処理という古典的な画像処理で
「肌色のかたまり」を探し、粗いグリッドに落としてから矩形に束ねる。

重要な限界:
  顔も肌色なので顔も検出される。逆に、影が濃い・色味が特殊な絵は
  検出を外す。だから **自動検出は候補出しにすぎず、UI で人間が
  足し引きすること** を前提にした設計にしている。
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from PIL import Image, ImageFilter

# YCbCr における肌色のおおよその範囲。実写・アニメ塗りの両方をだいたい拾う。
CB_MIN, CB_MAX = 77, 135
CR_MIN, CR_MAX = 133, 180
Y_MIN, Y_MAX = 40, 250

GRID = 40              # 画像を何分割して判定するか（粗いほど大きな塊だけ拾う）
CELL_SKIN_RATIO = 0.6  # セル内の肌色率がこれ以上なら「肌セル」
MIN_CELLS = 6          # これ未満の小さな塊は無視（ノイズ・指先など）
PAD_RATIO = 0.12       # 枠を外側に広げる割合。検閲用途なので「隠しすぎ」に倒す


@dataclass
class Box:
    """検閲する矩形。ピクセル座標（加工後の画像を基準にする）。"""

    x: int
    y: int
    w: int
    h: int
    source: str = "auto"  # auto | manual

    def as_dict(self) -> dict:
        return {"x": self.x, "y": self.y, "w": self.w, "h": self.h, "source": self.source}

    @classmethod
    def from_dict(cls, d: dict) -> "Box":
        return cls(
            x=int(d.get("x", 0)),
            y=int(d.get("y", 0)),
            w=int(d.get("w", 0)),
            h=int(d.get("h", 0)),
            source=str(d.get("source", "manual")),
        )


def skin_mask(im: Image.Image) -> np.ndarray:
    """肌色ピクセルの真偽マスクを返す。"""
    ycbcr = np.asarray(im.convert("YCbCr"), dtype=np.int16)
    y, cb, cr = ycbcr[:, :, 0], ycbcr[:, :, 1], ycbcr[:, :, 2]
    return (
        (y >= Y_MIN) & (y <= Y_MAX)
        & (cb >= CB_MIN) & (cb <= CB_MAX)
        & (cr >= CR_MIN) & (cr <= CR_MAX)
    )


def _pad(box: Box, width: int, height: int, ratio: float = PAD_RATIO) -> Box:
    """枠を外側に広げる。グリッド量子化で肌の端が枠から漏れるのを防ぐ。"""
    dx = int(box.w * ratio)
    dy = int(box.h * ratio)
    x0 = max(0, box.x - dx)
    y0 = max(0, box.y - dy)
    x1 = min(width, box.x + box.w + dx)
    y1 = min(height, box.y + box.h + dy)
    return Box(x=x0, y=y0, w=x1 - x0, h=y1 - y0, source=box.source)


def _cells_to_boxes(cells: np.ndarray, cell_w: float, cell_h: float) -> list[Box]:
    """隣接する肌セルを連結成分にまとめ、外接矩形を返す（4近傍の反復ラベリング）。"""
    rows, cols = cells.shape
    labels = np.zeros((rows, cols), dtype=np.int32)
    current = 0
    boxes: list[Box] = []

    for r in range(rows):
        for c in range(cols):
            if not cells[r, c] or labels[r, c]:
                continue
            current += 1
            stack = [(r, c)]
            labels[r, c] = current
            cell_list = []
            while stack:
                cr_, cc_ = stack.pop()
                cell_list.append((cr_, cc_))
                for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    nr, nc = cr_ + dr, cc_ + dc
                    if 0 <= nr < rows and 0 <= nc < cols and cells[nr, nc] and not labels[nr, nc]:
                        labels[nr, nc] = current
                        stack.append((nr, nc))
            if len(cell_list) < MIN_CELLS:
                continue
            rs = [p[0] for p in cell_list]
            cs = [p[1] for p in cell_list]
            x0, y0 = int(min(cs) * cell_w), int(min(rs) * cell_h)
            x1, y1 = int((max(cs) + 1) * cell_w), int((max(rs) + 1) * cell_h)
            boxes.append(Box(x=x0, y=y0, w=x1 - x0, h=y1 - y0, source="auto"))

    boxes.sort(key=lambda b: b.w * b.h, reverse=True)
    return boxes


def detect(im: Image.Image, grid: int = GRID, ratio: float = CELL_SKIN_RATIO) -> list[Box]:
    """肌色の塊を検出して矩形のリストで返す。顔も含まれる点に注意。"""
    mask = skin_mask(im)
    height, width = mask.shape
    cell_h, cell_w = height / grid, width / grid

    cells = np.zeros((grid, grid), dtype=bool)
    for r in range(grid):
        y0, y1 = int(r * cell_h), int((r + 1) * cell_h)
        for c in range(grid):
            x0, x1 = int(c * cell_w), int((c + 1) * cell_w)
            block = mask[y0:y1, x0:x1]
            if block.size and block.mean() >= ratio:
                cells[r, c] = True

    boxes = _cells_to_boxes(cells, cell_w, cell_h)
    return [_pad(b, width, height) for b in boxes]


def apply(
    im: Image.Image, boxes: list[Box], mode: str = "black", strength: int = 18
) -> Image.Image:
    """矩形を黒モザイク / モザイク / ぼかしで潰す。

    mode:
      black  … 黒のベタ塗り（一番確実に隠れる。既定）
      mosaic … 黒寄りに沈めたモザイク（元の形はうっすら残る）
      blur   … ぼかし
    """
    if not boxes:
        return im
    out = im.convert("RGB").copy()
    width, height = out.size

    for box in boxes:
        x0 = max(0, min(width, box.x))
        y0 = max(0, min(height, box.y))
        x1 = max(0, min(width, box.x + box.w))
        y1 = max(0, min(height, box.y + box.h))
        if x1 - x0 < 2 or y1 - y0 < 2:
            continue
        region = (x0, y0, x1, y1)

        if mode == "black":
            out.paste((0, 0, 0), region)
            continue

        patch = out.crop(region)
        if mode == "blur":
            patch = patch.filter(ImageFilter.GaussianBlur(radius=max(4, strength)))
        else:  # mosaic
            small_w = max(1, (x1 - x0) // max(4, strength))
            small_h = max(1, (y1 - y0) // max(4, strength))
            patch = patch.resize((small_w, small_h), Image.BILINEAR).resize(
                (x1 - x0, y1 - y0), Image.NEAREST
            )
            # 「黒モザイク」なので暗く沈めて視認性を落とす
            patch = Image.blend(patch, Image.new("RGB", patch.size, (0, 0, 0)), 0.55)
        out.paste(patch, region)

    return out

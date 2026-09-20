"""アプリ全体の設定。パスとフォント解決だけを持つ。"""
from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
OUTPUT_DIR = BASE_DIR / "output"
CACHE_DIR = BASE_DIR / ".cache" / "images"
DB_PATH = DATA_DIR / "history.db"
TEMPLATES_YAML = DATA_DIR / "templates.yaml"
DICTIONARY_YAML = DATA_DIR / "dictionary.yaml"

for _d in (DATA_DIR, OUTPUT_DIR, CACHE_DIR):
    _d.mkdir(parents=True, exist_ok=True)

USER_AGENT = os.environ.get(
    "CPA_USER_AGENT",
    "CommunityPostAssistant/1.0 (personal semi-automation tool; contact via channel)",
)
HTTP_TIMEOUT = float(os.environ.get("CPA_HTTP_TIMEOUT", "15"))
# robots.txt を無視したい場合のみ 1 にする。既定では従う。
IGNORE_ROBOTS = os.environ.get("CPA_IGNORE_ROBOTS", "0") == "1"
# 取得して実寸を測る画像の上限枚数（多すぎると遅くなる）
MAX_IMAGE_PROBES = int(os.environ.get("CPA_MAX_IMAGE_PROBES", "24"))

# OS ごとの日本語フォント候補。上から順に存在するものを使う。
FONT_CANDIDATES = [
    os.environ.get("CPA_FONT", ""),
    # macOS
    "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc",
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/Library/Fonts/Arial Unicode.ttf",
    # Windows
    "C:/Windows/Fonts/meiryob.ttc",
    "C:/Windows/Fonts/YuGothB.ttc",
    "C:/Windows/Fonts/msgothic.ttc",
    # Linux
    "/usr/share/fonts/truetype/fonts-japanese-gothic.ttf",
    "/usr/share/fonts/opentype/ipafont-gothic/ipagp.ttf",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
]


def resolve_font() -> str | None:
    """使える日本語フォントの絶対パスを返す。無ければ None。"""
    for path in FONT_CANDIDATES:
        if path and Path(path).exists():
            return path
    return None

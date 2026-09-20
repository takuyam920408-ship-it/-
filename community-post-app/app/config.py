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

# 画像に焼き込む文字は「けいふぉんと」を使う。
# 同梱していないので（配布元が Apache License 2.0 なので同梱自体は可能だが、
# この環境からダウンロードできなかった）、下記のいずれかに置けば自動で使われる。
FONTS_DIR = BASE_DIR / "assets" / "fonts"
KEIFONT_NAMES = ("keifont.ttf", "keifont.TTF", "けいふぉんと.ttf")

KEIFONT_CANDIDATES = [
    *[str(FONTS_DIR / n) for n in KEIFONT_NAMES],
    # Mac: フォントをダブルクリックして入れた場合
    *[str(Path.home() / "Library" / "Fonts" / n) for n in KEIFONT_NAMES],
    *[f"/Library/Fonts/{n}" for n in KEIFONT_NAMES],
    # Windows
    *[f"C:/Windows/Fonts/{n}" for n in KEIFONT_NAMES],
    *[str(Path.home() / "AppData/Local/Microsoft/Windows/Fonts" / n) for n in KEIFONT_NAMES],
]

# けいふぉんとが見つからないときの代替。文字が出ないよりはマシ、という位置づけ。
FALLBACK_CANDIDATES = [
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

KEIFONT_DOWNLOAD_URL = "https://font.sumomo.ne.jp/font_1.html"


def find_keifont() -> str | None:
    """けいふぉんとのパスを返す。無ければ None。"""
    for path in KEIFONT_CANDIDATES:
        if Path(path).exists():
            return path
    # assets/fonts に別名で置かれた場合の救済（kei を含むフォントファイル）
    if FONTS_DIR.exists():
        for path in sorted(FONTS_DIR.iterdir()):
            if path.suffix.lower() in (".ttf", ".otf", ".ttc") and "kei" in path.stem.lower():
                return str(path)
    return None


def resolve_font() -> str | None:
    """実際に描画に使うフォントの絶対パス。けいふぉんとを最優先。"""
    override = os.environ.get("CPA_FONT", "")
    if override and Path(override).exists():
        return override

    kei = find_keifont()
    if kei:
        return kei

    # assets/fonts に入っている任意の日本語フォント
    if FONTS_DIR.exists():
        for path in sorted(FONTS_DIR.iterdir()):
            if path.suffix.lower() in (".ttf", ".otf", ".ttc"):
                return str(path)

    for path in FALLBACK_CANDIDATES:
        if Path(path).exists():
            return path
    return None


def font_status() -> dict:
    """UI に出すフォントの状態。"""
    path = resolve_font()
    kei = find_keifont()
    return {
        "path": path or "",
        "is_keifont": bool(path and kei and path == kei),
        "fonts_dir": str(FONTS_DIR),
        "download_url": KEIFONT_DOWNLOAD_URL,
    }

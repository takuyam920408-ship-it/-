"""画像候補のスコアリング。AI は使わず、ルールと辞書だけで並べ替える。

狙い: 「投稿に使えそうな一番大きい本命画像」を上位に、
ロゴ・アイコン・バナー・広告を下位または除外に落とすこと。
"""
from __future__ import annotations

import re
from urllib.parse import urlparse

from .models import ImageCandidate, PageMeta

# URL / ファイル名にこれが含まれたら投稿画像ではない可能性が高い
EXCLUDE_PATTERNS = [
    "logo", "icon", "favicon", "avatar", "sprite", "banner", "bnr",
    "/ad/", "/ads/", "adsense", "doubleclick", "spacer", "blank.gif",
    "1x1", "pixel", "btn_", "button", "arrow", "bullet", "share",
    "sns_", "profile_images", "emoji", "loading", "dummy", "noimage",
]
# 逆に本命画像でよく使われる語
BOOST_PATTERNS = ["main", "key", "visual", "kv_", "hero", "eyecatch", "ogp", "thumb", "still"]

MIN_SIDE = 200          # これ未満は除外（アイコン/装飾とみなす）
MIN_AREA = 120_000      # おおよそ 400x300 未満は投稿画像として弱い
MAX_ASPECT = 3.0        # 極端な横長/縦長（バナー）は除外


def _normalized(text: str) -> str:
    return text.lower()


def score_candidate(
    cand: ImageCandidate, meta: PageMeta, work_keywords: list[str]
) -> ImageCandidate:
    score = 0.0
    reasons: list[str] = []
    url_l = _normalized(cand.url)
    path = _normalized(urlparse(cand.url).path)

    # --- 除外判定 ---------------------------------------------------
    for pattern in EXCLUDE_PATTERNS:
        if pattern in url_l:
            cand.score = -999.0
            cand.reasons = [f"除外: URL に '{pattern}'"]
            return cand

    width = cand.width or cand.declared_width
    height = cand.height or cand.declared_height
    if width and height:
        if min(width, height) < MIN_SIDE:
            cand.score = -999.0
            cand.reasons = [f"除外: 小さすぎる ({width}x{height})"]
            return cand
        aspect = max(width / height, height / width)
        if aspect > MAX_ASPECT:
            cand.score = -999.0
            cand.reasons = [f"除外: 極端な縦横比 ({width}x{height})"]
            return cand
        # --- 面積 ---
        area = width * height
        area_score = min(40.0, area / 1_500_000 * 40.0)
        score += area_score
        reasons.append(f"解像度 {width}x{height} (+{area_score:.0f})")
        if area < MIN_AREA:
            score -= 20.0
            reasons.append("面積が小さめ (-20)")
        # 投稿向きの縦横比（1:1〜16:9 あたり）に加点
        if 1.0 <= aspect <= 1.9:
            score += 10.0
            reasons.append("投稿向きの縦横比 (+10)")
    elif cand.source in ("og", "twitter"):
        reasons.append("実寸未取得だが OGP 指定")
    else:
        score -= 30.0
        reasons.append("実寸を取得できず (-30)")

    # --- 出所 -------------------------------------------------------
    if cand.source == "og":
        score += 50.0
        reasons.append("og:image (+50)")
    elif cand.source == "twitter":
        score += 40.0
        reasons.append("twitter:image (+40)")

    # --- 文脈テキスト -----------------------------------------------
    if cand.alt:
        score += 5.0
        reasons.append("alt あり (+5)")
    if cand.caption:
        score += 8.0
        reasons.append("キャプションあり (+8)")

    haystack = _normalized(cand.context_text + " " + path)
    for keyword in work_keywords:
        if keyword and _normalized(keyword) in haystack:
            score += 20.0
            reasons.append(f"作品名 '{keyword}' に一致 (+20)")
            break

    for pattern in BOOST_PATTERNS:
        if pattern in path:
            score += 12.0
            reasons.append(f"本命らしいファイル名 '{pattern}' (+12)")
            break

    # 記事タイトルの語が alt に入っていれば、その記事の本文画像である可能性が高い
    title_words = [w for w in re.split(r"[\s　|｜\-–—【】\[\]「」]+", meta.og_title or meta.title) if len(w) >= 3]
    if any(_normalized(w) in _normalized(cand.context_text) for w in title_words):
        score += 10.0
        reasons.append("記事タイトルと文脈が一致 (+10)")

    cand.score = score
    cand.reasons = reasons
    return cand


def rank(
    cands: list[ImageCandidate], meta: PageMeta, work_keywords: list[str]
) -> list[ImageCandidate]:
    """スコア順に並べ替え、除外されたものは落とす。"""
    scored = [score_candidate(c, meta, work_keywords) for c in cands]
    kept = [c for c in scored if c.score > -900]
    kept.sort(key=lambda c: c.score, reverse=True)
    return kept

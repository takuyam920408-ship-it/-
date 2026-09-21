"""画像のダウンロードとローカルキャッシュ。実寸を測るために使う。"""
from __future__ import annotations

import hashlib
import io
from concurrent.futures import ThreadPoolExecutor

import httpx
from PIL import Image

from . import config
from .models import ImageCandidate

_HEADERS = {"User-Agent": config.USER_AGENT, "Accept": "image/*,*/*;q=0.8"}
MAX_BYTES = 12 * 1024 * 1024


def cache_id(url: str) -> str:
    return hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]


def cache_path(cid: str):
    return config.CACHE_DIR / f"{cid}.bin"


def load_cached(cid: str) -> bytes | None:
    path = cache_path(cid)
    return path.read_bytes() if path.exists() else None


def probe(cand: ImageCandidate, referer: str = "") -> ImageCandidate:
    """1枚ダウンロードして実寸を測り、キャッシュに保存する。

    失敗しても例外は投げず、width/height を None のままにして返す
    （1枚コケただけでページ全体の解析を落とさない）。
    """
    cid = cache_id(cand.url)
    cand.cache_id = cid
    blob = load_cached(cid)
    if blob is None:
        headers = dict(_HEADERS)
        if referer:
            headers["Referer"] = referer
        try:
            resp = httpx.get(
                cand.url, headers=headers, timeout=config.HTTP_TIMEOUT, follow_redirects=True
            )
            resp.raise_for_status()
            blob = resp.content
            cand.content_type = resp.headers.get("content-type", "")
        except Exception as exc:  # 1枚の失敗でページ全体の解析を落とさない
            cand.error = str(exc)
            return cand
        if len(blob) > MAX_BYTES:
            cand.error = "画像が大きすぎます"
            return cand
        # HTML などが返ってきた場合は画像キャッシュに残さない
        if "html" in cand.content_type.lower() or "text/" in cand.content_type.lower():
            cand.error = "画像ではなく Web ページが返ってきました"
            return cand
        cache_path(cid).write_bytes(blob)
    try:
        with Image.open(io.BytesIO(blob)) as im:
            cand.width, cand.height = im.size
            cand.content_type = cand.content_type or Image.MIME.get(im.format or "", "")
    except Exception:
        cand.width = cand.height = None
        cand.error = cand.error or "画像として読めませんでした"
        cache_path(cid).unlink(missing_ok=True)
    return cand


def probe_all(cands: list[ImageCandidate], referer: str = "") -> list[ImageCandidate]:
    """並列に実寸を測る。上限は config.MAX_IMAGE_PROBES 枚。"""
    targets = cands[: config.MAX_IMAGE_PROBES]
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda c: probe(c, referer), targets))
    for cand in cands[config.MAX_IMAGE_PROBES :]:
        cand.cache_id = cache_id(cand.url)
    return cands

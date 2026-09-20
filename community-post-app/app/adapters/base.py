"""URL からページを取り、画像候補とメタ情報を返すアダプタ層。

今は汎用ニュース/アニメ公式サイト用の1本だけ。サイト固有の癖が出てきたら
`ADAPTERS` にドメイン別アダプタを足して差し替える。
"""
from __future__ import annotations

from urllib.parse import urlparse

from ..models import ImageCandidate, PageMeta
from . import generic_news


class AdapterError(RuntimeError):
    """取得・解析に失敗したときに UI へ返すエラー。"""


# (ホスト判定関数, アダプタモジュール) の並び。上から最初にマッチしたものを使う。
ADAPTERS: list[tuple[callable, object]] = []


def pick_adapter(url: str):
    host = (urlparse(url).hostname or "").lower()
    for matches, adapter in ADAPTERS:
        if matches(host):
            return adapter
    return generic_news


def fetch_page(url: str) -> tuple[PageMeta, list[ImageCandidate]]:
    if not url.lower().startswith(("http://", "https://")):
        raise AdapterError("http(s) の URL を貼ってください。")
    return pick_adapter(url).fetch(url)

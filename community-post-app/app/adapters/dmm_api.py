"""DMM アフィリエイト API（DMM Web サービス）のクライアント。

スクレイピングではなく公式 API を叩く。商品情報と一緒にサンプル画像の URL が
正式に取得できるため、年齢認証ゲートもページ解析も関係しない。

認証情報は data/dmm_api.json か環境変数 DMM_API_ID / DMM_AFFILIATE_ID から読む。
（このファイルは .gitignore 済み。リポジトリには入れない）

注意: このコードは公開仕様にもとづいて書いているが、実際の応答で項目名が
違っていた場合に備え、値の取り出しはすべて防御的にしてある。UI から生の
JSON を確認できるので、ズレていたら _item_to_dict() を直せばよい。
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field

import httpx

from .. import config

API_BASE = "https://api.dmm.com/affiliate/v3"
ITEM_LIST = f"{API_BASE}/ItemList"
FLOOR_LIST = f"{API_BASE}/FloorList"
CREDENTIALS_PATH = config.DATA_DIR / "dmm_api.json"


class DmmApiError(RuntimeError):
    """API 呼び出しに失敗したときに UI へ返すエラー。"""


@dataclass
class Credentials:
    api_id: str = ""
    affiliate_id: str = ""

    @property
    def ready(self) -> bool:
        return bool(self.api_id and self.affiliate_id)


def load_credentials() -> Credentials:
    """環境変数を優先し、無ければ data/dmm_api.json から読む。"""
    api_id = os.environ.get("DMM_API_ID", "")
    affiliate_id = os.environ.get("DMM_AFFILIATE_ID", "")
    if not (api_id and affiliate_id) and CREDENTIALS_PATH.exists():
        try:
            saved = json.loads(CREDENTIALS_PATH.read_text(encoding="utf-8"))
            api_id = api_id or saved.get("api_id", "")
            affiliate_id = affiliate_id or saved.get("affiliate_id", "")
        except (OSError, json.JSONDecodeError):
            pass
    return Credentials(api_id.strip(), affiliate_id.strip())


def save_credentials(api_id: str, affiliate_id: str) -> Credentials:
    """認証情報をローカルに保存する（この PC の中だけ）。"""
    creds = Credentials(api_id.strip(), affiliate_id.strip())
    CREDENTIALS_PATH.write_text(
        json.dumps({"api_id": creds.api_id, "affiliate_id": creds.affiliate_id}, indent=2),
        encoding="utf-8",
    )
    try:  # 認証情報なので、読めるのは自分だけにしておく
        CREDENTIALS_PATH.chmod(0o600)
    except OSError:
        pass
    return creds


# 商品ページの URL から商品ID（cid）を取り出すための並び。上から順に試す。
# クエリ文字列は先に捨てる。?cid=... はアフィリエイトの追跡用パラメータであって
# 商品ID ではないため、拾うと別物を検索してしまう。
CID_PATTERNS = [
    re.compile(r"/cid=([A-Za-z0-9_]+)"),             # .../detail/=/cid=abcd00123/
    re.compile(r"/product/[^/]+/([A-Za-z0-9_]+)"),   # book.dmm.co.jp/product/123/xxxx/
    re.compile(r"/detail/([A-Za-z0-9_]+)"),
]


def extract_cid(text: str) -> str:
    """商品ID そのものか、商品ページの URL から商品ID を取り出す。

    URL を貼られても使えるようにするためのもの。API を叩く前の下ごしらえで、
    ページを取得したりはしない（URL の文字列を見るだけ）。
    """
    value = (text or "").strip()
    if not value:
        return ""
    if not value.lower().startswith(("http://", "https://")):
        return value  # すでに cid が入力されている
    path = value.split("?", 1)[0].split("#", 1)[0]
    for pattern in CID_PATTERNS:
        m = pattern.search(path)
        if m:
            return m.group(1)
    return ""


@dataclass
class DmmItem:
    """API が返した1商品。サンプル画像は大きい方を優先して並べる。"""

    content_id: str = ""
    title: str = ""
    url: str = ""
    affiliate_url: str = ""
    date: str = ""
    maker: str = ""
    genres: list[str] = field(default_factory=list)
    cover: str = ""
    samples: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "content_id": self.content_id,
            "title": self.title,
            "url": self.url,
            "affiliate_url": self.affiliate_url,
            "date": self.date,
            "maker": self.maker,
            "genres": self.genres,
            "cover": self.cover,
            "samples": self.samples,
            "sample_count": len(self.samples),
        }


def _first_str(container: dict, *keys: str) -> str:
    """大文字小文字の揺れに強い取り出し（URL / url / Url など）。"""
    lowered = {str(k).lower(): v for k, v in container.items()}
    for key in keys:
        value = lowered.get(key.lower())
        if isinstance(value, str) and value:
            return value
    return ""


def _image_list(node) -> list[str]:
    """{"image": [...]} でも ["..."] でも文字列単体でも拾えるようにする。"""
    if isinstance(node, dict):
        inner = node.get("image") or node.get("Image") or []
        return _image_list(inner)
    if isinstance(node, list):
        return [x for x in node if isinstance(x, str) and x]
    if isinstance(node, str) and node:
        return [node]
    return []


def _item_to_dict(raw: dict) -> DmmItem:
    """API の1件をアプリ内の形に落とす。項目名がズレたらここを直す。"""
    images = raw.get("imageURL") or raw.get("imageUrl") or {}
    cover = ""
    if isinstance(images, dict):
        cover = _first_str(images, "large", "list", "small")

    samples_node = raw.get("sampleImageURL") or raw.get("sampleImageUrl") or {}
    large: list[str] = []
    small: list[str] = []
    if isinstance(samples_node, dict):
        for key, value in samples_node.items():
            target = large if "l" in str(key).lower().replace("sample", "") else small
            target.extend(_image_list(value))
    # 大きい方を先に。重複は落とす。
    seen: set[str] = set()
    samples = [u for u in large + small if not (u in seen or seen.add(u))]

    info = raw.get("iteminfo") or {}
    def names(key: str) -> list[str]:
        node = info.get(key) or []
        if isinstance(node, dict):
            node = [node]
        return [n.get("name", "") for n in node if isinstance(n, dict) and n.get("name")]

    makers = names("maker")
    return DmmItem(
        content_id=_first_str(raw, "content_id", "contentId", "product_id"),
        title=_first_str(raw, "title"),
        url=_first_str(raw, "URL", "url"),
        affiliate_url=_first_str(raw, "affiliateURL", "affiliateUrl"),
        date=_first_str(raw, "date"),
        maker=makers[0] if makers else "",
        genres=names("genre"),
        cover=cover,
        samples=samples,
    )


def _call(url: str, params: dict) -> dict:
    creds = load_credentials()
    if not creds.ready:
        raise DmmApiError(
            "API ID とアフィリエイト ID が未設定です。画面の設定欄に入力してください。"
        )
    query = {
        "api_id": creds.api_id,
        "affiliate_id": creds.affiliate_id,
        "output": "json",
        **{k: v for k, v in params.items() if v not in (None, "")},
    }
    try:
        resp = httpx.get(
            url,
            params=query,
            timeout=config.HTTP_TIMEOUT,
            headers={"User-Agent": config.USER_AGENT},
        )
    except httpx.HTTPError as exc:
        raise DmmApiError(f"API に接続できませんでした: {exc}") from exc

    try:
        data = resp.json()
    except ValueError as exc:
        raise DmmApiError(
            f"API の応答を JSON として読めませんでした（HTTP {resp.status_code}）: "
            f"{resp.text[:200]}"
        ) from exc

    result = data.get("result") or {}
    status = result.get("status")
    # DMM は HTTP 200 のまま result.status にエラーを入れてくることがある
    if resp.status_code >= 400 or (status not in (None, 200, "200")):
        message = result.get("message") or data.get("message") or resp.text[:200]
        raise DmmApiError(f"API がエラーを返しました（status={status}）: {message}")
    return data


def search(
    *,
    keyword: str = "",
    cid: str = "",
    site: str = "FANZA",
    service: str = "",
    floor: str = "",
    hits: int = 20,
    offset: int = 1,
    sort: str = "rank",
) -> tuple[list[DmmItem], dict]:
    """商品を検索して、サンプル画像つきの一覧を返す。

    戻り値は (商品リスト, 生の応答)。生の応答は UI のデバッグ表示に使う。
    """
    data = _call(
        ITEM_LIST,
        {
            "site": site,
            "service": service,
            "floor": floor,
            "hits": max(1, min(int(hits), 100)),
            "offset": max(1, int(offset)),
            "sort": sort,
            "keyword": keyword,
            "cid": cid,
        },
    )
    raw_items = (data.get("result") or {}).get("items") or []
    if isinstance(raw_items, dict):  # 1件のときに配列でなく来る場合への保険
        raw_items = [raw_items]
    return [_item_to_dict(r) for r in raw_items if isinstance(r, dict)], data


def floors(site: str = "FANZA") -> tuple[list[dict], dict]:
    """service / floor の一覧を取る。指定値が分からないときの確認用。"""
    data = _call(FLOOR_LIST, {})
    out: list[dict] = []
    for s in (data.get("result") or {}).get("site") or []:
        if not isinstance(s, dict):
            continue
        site_name = s.get("name", "")
        if site and site.lower() not in site_name.lower().replace(".", ""):
            continue
        for svc in s.get("service") or []:
            if not isinstance(svc, dict):
                continue
            for fl in svc.get("floor") or []:
                if isinstance(fl, dict):
                    out.append({
                        "site": site_name,
                        "service": svc.get("code", ""),
                        "service_name": svc.get("name", ""),
                        "floor": fl.get("code", ""),
                        "floor_name": fl.get("name", ""),
                    })
    return out, data

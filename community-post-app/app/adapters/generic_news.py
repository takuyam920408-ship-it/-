"""汎用アダプタ: アニメ公式サイト / ニュース記事から画像とテキストを集める。

方針:
  1. OGP / twitter:image を最優先で拾う（本命画像である確率が高い）
  2. 本文中の <img> を、周辺テキスト付きで全部拾う
  3. srcset / data-src(遅延ロード) にも対応して最大解像度を選ぶ
画像の「中身」は見ない。alt / figcaption / 直前の見出しだけが文面の手がかり。
"""
from __future__ import annotations

import re
import urllib.robotparser
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from .. import config
from ..models import ImageCandidate, PageMeta

_HEADERS = {
    "User-Agent": config.USER_AGENT,
    "Accept-Language": "ja,en;q=0.8",
}
_LAZY_ATTRS = ("data-src", "data-original", "data-lazy-src", "data-echo", "data-url")
_robots_cache: dict[str, urllib.robotparser.RobotFileParser | None] = {}


def _pick_parser() -> str:
    """lxml があれば使い、無ければ標準の html.parser に落ちる。

    lxml は環境によってはソースからのビルドが必要で、インストールが重い。
    必須にはせず、入っていれば速い方を使う、という扱いにしている。
    """
    try:
        BeautifulSoup("<i></i>", "lxml")
        return "lxml"
    except Exception:
        return "html.parser"


PARSER = _pick_parser()


def _robots_allows(url: str) -> bool:
    """robots.txt を尊重する。取得できなければ許可扱い。"""
    if config.IGNORE_ROBOTS:
        return True
    parsed = urlparse(url)
    root = f"{parsed.scheme}://{parsed.netloc}"
    if root not in _robots_cache:
        rp = urllib.robotparser.RobotFileParser()
        try:
            resp = httpx.get(
                urljoin(root, "/robots.txt"),
                headers=_HEADERS,
                timeout=config.HTTP_TIMEOUT,
                follow_redirects=True,
            )
            if resp.status_code == 200:
                rp.parse(resp.text.splitlines())
            else:
                rp = None
        except httpx.HTTPError:
            rp = None
        _robots_cache[root] = rp
    rp = _robots_cache[root]
    return True if rp is None else rp.can_fetch(config.USER_AGENT, url)


def _pick_from_srcset(srcset: str) -> str:
    """srcset から一番大きい候補の URL を返す。"""
    best, best_w = "", -1.0
    for part in srcset.split(","):
        bits = part.strip().split()
        if not bits:
            continue
        url = bits[0]
        width = 1.0
        if len(bits) > 1:
            m = re.match(r"(\d+(?:\.\d+)?)([wx])", bits[1])
            if m:
                width = float(m.group(1)) * (1000 if m.group(2) == "x" else 1)
        if width > best_w:
            best, best_w = url, width
    return best


def _nearby_heading(tag) -> str:
    """<img> から見て直前にある見出しテキスト。文面の手がかりになる。"""
    for prev in tag.find_all_previous(["h1", "h2", "h3", "h4"], limit=1):
        return prev.get_text(" ", strip=True)[:200]
    return ""


def _caption(tag) -> str:
    """figcaption や直後の小さなテキストをキャプションとして拾う。"""
    fig = tag.find_parent("figure")
    if fig:
        cap = fig.find("figcaption")
        if cap:
            return cap.get_text(" ", strip=True)[:200]
    nxt = tag.find_next_sibling()
    if nxt and nxt.name in ("figcaption", "p", "span", "small"):
        text = nxt.get_text(" ", strip=True)
        if 0 < len(text) <= 120:
            return text
    return ""


def _int_or_none(value) -> int | None:
    try:
        return int(str(value).strip().rstrip("px"))
    except (TypeError, ValueError):
        return None


def _meta(soup: BeautifulSoup, *names: str) -> str:
    for name in names:
        tag = soup.find("meta", attrs={"property": name}) or soup.find(
            "meta", attrs={"name": name}
        )
        if tag and tag.get("content"):
            return tag["content"].strip()
    return ""


def fetch(url: str) -> tuple[PageMeta, list[ImageCandidate]]:
    from .base import AdapterError

    if not _robots_allows(url):
        raise AdapterError(
            "このサイトの robots.txt がこの URL の自動取得を許可していません。"
            "手動で画像を保存するか、CPA_IGNORE_ROBOTS=1 で明示的に上書きしてください。"
        )
    try:
        resp = httpx.get(
            url, headers=_HEADERS, timeout=config.HTTP_TIMEOUT, follow_redirects=True
        )
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        raise AdapterError(f"ページを取得できませんでした: {exc}") from exc

    soup = BeautifulSoup(resp.text, PARSER)
    base = str(resp.url)
    # <base href> があればそれを相対URL解決の基準にする
    base_tag = soup.find("base", href=True)
    if base_tag:
        base = urljoin(base, base_tag["href"])

    meta = PageMeta(
        url=url,
        final_url=str(resp.url),
        title=(soup.title.get_text(strip=True) if soup.title else ""),
        og_title=_meta(soup, "og:title", "twitter:title"),
        og_description=_meta(soup, "og:description", "twitter:description", "description"),
        site_name=_meta(soup, "og:site_name", "application-name"),
        published_at=_meta(soup, "article:published_time", "date", "pubdate"),
        path_segments=[s for s in urlparse(str(resp.url)).path.split("/") if s],
    )

    candidates: list[ImageCandidate] = []
    seen: set[str] = set()

    def add(raw_url: str, **kwargs) -> None:
        if not raw_url or raw_url.startswith("data:"):
            return
        absolute = urljoin(base, raw_url.strip())
        if absolute in seen:
            return
        seen.add(absolute)
        candidates.append(ImageCandidate(url=absolute, **kwargs))

    # 1. OGP / twitter card — 本命である可能性が最も高い
    for prop, source in (
        ("og:image:secure_url", "og"),
        ("og:image", "og"),
        ("twitter:image", "twitter"),
        ("twitter:image:src", "twitter"),
    ):
        for tag in soup.find_all("meta", attrs={"property": prop}) + soup.find_all(
            "meta", attrs={"name": prop}
        ):
            add(
                tag.get("content", ""),
                source=source,
                alt=meta.og_title,
                nearby_heading=meta.title,
            )

    # 2. 本文中の <img>（srcset / 遅延ロード属性も見る）
    for img in soup.find_all("img"):
        raw = ""
        if img.get("srcset"):
            raw = _pick_from_srcset(img["srcset"])
        if not raw:
            for attr in _LAZY_ATTRS:
                if img.get(attr):
                    raw = img[attr]
                    break
        if not raw:
            raw = img.get("src", "")
        add(
            raw,
            source="img",
            alt=(img.get("alt") or "").strip()[:200],
            caption=_caption(img),
            nearby_heading=_nearby_heading(img),
            declared_width=_int_or_none(img.get("width")),
            declared_height=_int_or_none(img.get("height")),
        )

    # 3. <picture><source srcset> — <img> が小さい版しか持っていない場合の保険
    for source_tag in soup.find_all("source"):
        if source_tag.get("srcset"):
            add(
                _pick_from_srcset(source_tag["srcset"]),
                source="srcset",
                nearby_heading=_nearby_heading(source_tag),
            )

    return meta, candidates

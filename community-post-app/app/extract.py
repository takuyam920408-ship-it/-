"""ページのテキストから「作品名 / 話数 / キャラ名」を取り出す。

AI は使わない。辞書マッチと正規表現だけ。取れなかったスロットは空のままにし、
そのスロットを requires に持つテンプレートは候補から外す（＝嘘を書かない）。
"""
from __future__ import annotations

import functools
import re

import yaml

from . import config
from .models import ImageCandidate, PageMeta, Slots

# 「第12話」「12話」「#12」「ep12」「/12/」などを拾う
EPISODE_PATTERNS = [
    re.compile(r"第\s*(\d{1,4})\s*話"),
    re.compile(r"(?<![\d.])(\d{1,4})\s*話(?!題|数)"),
    re.compile(r"[#＃]\s*(\d{1,4})(?!\d)"),
    re.compile(r"\bep(?:isode)?[\s._-]*(\d{1,4})\b", re.IGNORECASE),
]
EPISODE_PATH_PATTERN = re.compile(r"/(?:ep|episode|story|no)?[\s._-]*(\d{1,4})(?:/|\.|$)", re.IGNORECASE)


@functools.lru_cache(maxsize=1)
def load_dictionary() -> dict:
    if not config.DICTIONARY_YAML.exists():
        return {"works": [], "generic_phrases": [], "title_noise": []}
    with config.DICTIONARY_YAML.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def reload_dictionary() -> dict:
    load_dictionary.cache_clear()
    return load_dictionary()


def work_keywords() -> list[str]:
    """スコアリングで使う、全作品の名前と別名のフラットなリスト。"""
    out: list[str] = []
    for work in load_dictionary().get("works", []):
        out.append(work.get("name", ""))
        out.extend(work.get("aliases", []) or [])
    return [k for k in out if k]


def match_work(text: str) -> dict | None:
    """テキストに最初にヒットした作品を返す。長い名前から先に試す。"""
    lowered = text.lower()
    hits: list[tuple[int, dict]] = []
    for work in load_dictionary().get("works", []):
        names = [work.get("name", "")] + list(work.get("aliases", []) or [])
        for name in names:
            if name and name.lower() in lowered:
                hits.append((len(name), work))
                break
    if not hits:
        return None
    # 「かぐや姫」より「超かぐや姫」を優先したいので、一致した名前が長い方を採る
    hits.sort(key=lambda pair: pair[0], reverse=True)
    return hits[0][1]


def match_episode(text: str, path_segments: list[str]) -> str | None:
    for pattern in EPISODE_PATTERNS:
        m = pattern.search(text)
        if m:
            return str(int(m.group(1)))
    joined = "/" + "/".join(path_segments) + "/"
    m = EPISODE_PATH_PATTERN.search(joined)
    if m:
        number = int(m.group(1))
        # 西暦や日付と見分けがつかない数字は採用しない
        if 1 <= number <= 999:
            return str(number)
    return None


def match_characters(text: str, work: dict | None) -> list[str]:
    if not work:
        return []
    return [c for c in (work.get("characters") or []) if c and c in text]


def clean_title(raw: str) -> str:
    """記事タイトルからサイト名や定型ノイズを落とす。"""
    title = re.split(r"\s*[|｜–—]\s*", raw)[0]
    for noise in load_dictionary().get("title_noise", []) or []:
        title = title.replace(noise, "")
    return re.sub(r"\s+", " ", title).strip(" -‐−　")


def extract_slots(
    meta: PageMeta, cand: ImageCandidate | None = None, video_url: str = ""
) -> Slots:
    """ページメタ（＋選択中の画像の文脈）からスロットを埋める。"""
    parts = [meta.context_text]
    if cand:
        parts.append(cand.context_text)
        parts.append(cand.url)
    parts.append("/".join(meta.path_segments))
    haystack = " ".join(p for p in parts if p)

    work = match_work(haystack)
    # 話数は URL より本文・タイトルの方が信用できるので、そちらを先に見る
    episode = match_episode(
        " ".join(p for p in (meta.og_title, meta.title, cand.context_text if cand else "") if p),
        meta.path_segments,
    )
    if episode is None:
        episode = match_episode(haystack, meta.path_segments)

    return Slots(
        work=work.get("name") if work else None,
        work_tag=(work.get("tag") or work.get("name")) if work else None,
        work_id=work.get("id") if work else None,
        episode=episode,
        characters=match_characters(haystack, work),
        title=clean_title(meta.og_title or meta.title),
        source_url=meta.final_url or meta.url,
        video_url=video_url,
        site_name=meta.site_name,
    )

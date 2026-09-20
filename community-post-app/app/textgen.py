"""テンプレート差し込みによる投稿文生成。LLM は使わない。

やっていること:
  1. 埋まっているスロットで使えるテンプレートだけに絞る
  2. 直近で使ったテンプレ / フレーズを避けて重み付き抽選
  3. 未使用の {スロット} が残った行は落として文を整える
"""
from __future__ import annotations

import functools
import random
import re

import yaml

from . import config, db, extract
from .models import Draft, Slots

PLACEHOLDER = re.compile(r"\{([^{}]+)\}")


@functools.lru_cache(maxsize=1)
def load_templates() -> list[dict]:
    if not config.TEMPLATES_YAML.exists():
        return []
    with config.TEMPLATES_YAML.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    return data.get("templates", []) or []


def reload_templates() -> list[dict]:
    load_templates.cache_clear()
    return load_templates()


def usable_templates(slots: Slots) -> list[dict]:
    filled = slots.filled_keys()
    return [
        t for t in load_templates() if all(req in filled for req in (t.get("requires") or []))
    ]


def pick_phrase(slots: Slots, rng: random.Random) -> str:
    """作品専用フレーズを優先。直近で使ったものは避ける。"""
    dic = extract.load_dictionary()
    pool: list[str] = []
    if slots.work_id:
        for work in dic.get("works", []):
            if work.get("id") == slots.work_id:
                pool = list(work.get("phrases") or [])
                break
    if not pool:
        pool = list(dic.get("generic_phrases") or [])
    if not pool:
        return ""
    used = set(db.recent_phrases(slots.work_id))
    fresh = [p for p in pool if p not in used]
    return rng.choice(fresh or pool)


def _strip_unfilled(text: str) -> str:
    """値が入らなかった {スロット} を含む行を落として、空行を詰める。"""
    lines = [line for line in text.splitlines() if not PLACEHOLDER.search(line)]
    out = "\n".join(lines)
    return re.sub(r"\n{3,}", "\n\n", out).strip()


def render(template: dict, slots: Slots, phrase: str) -> Draft:
    values = slots.as_dict()
    values["感想フレーズ"] = phrase
    text = template.get("text", "")
    for key, value in values.items():
        if value:
            text = text.replace("{" + key + "}", value)
    missing = sorted(set(PLACEHOLDER.findall(text)))
    return Draft(
        template_id=template.get("id", ""),
        template_type=template.get("type", ""),
        text=_strip_unfilled(text),
        phrase=phrase,
        missing=missing,
    )


def generate(slots: Slots, count: int = 3, seed: int | None = None) -> list[Draft]:
    """投稿文の候補を count 件返す。重複テンプレは選ばない。"""
    rng = random.Random(seed)
    pool = usable_templates(slots)
    if not pool:
        return []

    recent = db.recent_template_ids()
    # 直近で使ったテンプレは重みを下げる（0 にはしない＝候補が枯れないように）
    def weight(t: dict) -> float:
        base = float(t.get("weight", 1))
        return base * 0.2 if t.get("id") in recent else base

    drafts: list[Draft] = []
    remaining = list(pool)
    for _ in range(min(count, len(remaining))):
        weights = [weight(t) for t in remaining]
        if sum(weights) <= 0:
            weights = [1.0] * len(remaining)
        chosen = rng.choices(remaining, weights=weights, k=1)[0]
        remaining.remove(chosen)
        drafts.append(render(chosen, slots, pick_phrase(slots, rng)))
    return drafts

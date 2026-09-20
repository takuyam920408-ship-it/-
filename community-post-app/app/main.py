"""FastAPI アプリ本体。ローカルで動かす半自動コミュニティ投稿アシスタント。

フロー: URL 貼り付け → 画像収集 → 1枚選ぶ → 加工 → 文面生成 → コピーして
YouTube Studio に貼る。最後の「投稿する」だけは人間の仕事（公式 API に
コミュニティ投稿の作成エンドポイントが無いため）。
"""
from __future__ import annotations

import mimetypes
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import compose as compose_mod
from . import config, db, extract, imagefetch, scoring, textgen
from .adapters import AdapterError, fetch_page
from .models import ImageCandidate, PageMeta, Slots

app = FastAPI(title="Community Post Assistant", version="1.0")
db.init()

WEB_DIR = config.BASE_DIR / "web"
app.mount("/static", StaticFiles(directory=WEB_DIR / "static"), name="static")
app.mount("/output", StaticFiles(directory=config.OUTPUT_DIR), name="output")

# 直近の解析結果を保持する。ローカル単独利用なのでプロセス内メモリで十分。
_analyses: dict[str, dict[str, Any]] = {}


# --------------------------------------------------------------------------
# リクエスト/レスポンス
# --------------------------------------------------------------------------
class AnalyzeRequest(BaseModel):
    url: str
    video_url: str = ""


class DraftRequest(BaseModel):
    analysis_id: str
    cache_id: str = ""
    video_url: str = ""
    overrides: dict[str, str] = Field(default_factory=dict)
    count: int = 3


class ComposeRequest(BaseModel):
    cache_id: str
    preset: str = "square"
    focus: str = "center"
    caption: str = ""
    badge: str = ""
    fmt: str = "JPEG"


class RecordRequest(BaseModel):
    source_url: str
    text: str
    image_url: str = ""
    image_file: str = ""
    template_id: str = ""
    template_type: str = ""
    phrase: str = ""
    work_id: str = ""
    episode: str = ""


# --------------------------------------------------------------------------
# ヘルパ
# --------------------------------------------------------------------------
def _candidate_json(cand: ImageCandidate) -> dict[str, Any]:
    return {
        "cache_id": cand.cache_id,
        "url": cand.url,
        "source": cand.source,
        "alt": cand.alt,
        "caption": cand.caption,
        "nearby_heading": cand.nearby_heading,
        "width": cand.width,
        "height": cand.height,
        "score": round(cand.score, 1),
        "reasons": cand.reasons,
        "preview": f"/img/{cand.cache_id}" if cand.cache_id else "",
        "already_used": bool(db.image_used(cand.url)),
    }


def _slots_json(slots: Slots) -> dict[str, Any]:
    data = slots.as_dict()
    data["_work_id"] = slots.work_id or ""
    return data


def _apply_overrides(slots: Slots, overrides: dict[str, str]) -> Slots:
    mapping = {
        "作品名": "work",
        "作品名タグ": "work_tag",
        "話数": "episode",
        "タイトル": "title",
        "動画URL": "video_url",
        "元記事URL": "source_url",
        "サイト名": "site_name",
    }
    for key, value in overrides.items():
        attr = mapping.get(key)
        if not attr:
            continue
        cleaned = value.strip()
        # title と source_url は空文字を許すが、他のスロットは空なら None（未確定）
        setattr(slots, attr, cleaned if attr in ("title", "source_url") else (cleaned or None))
    if overrides.get("キャラ名"):
        slots.characters = [overrides["キャラ名"].strip()]
    if slots.work and not slots.work_tag:
        slots.work_tag = slots.work
    return slots


# --------------------------------------------------------------------------
# ルート
# --------------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    return HTMLResponse((WEB_DIR / "templates" / "index.html").read_text(encoding="utf-8"))


@app.post("/api/analyze")
def analyze(req: AnalyzeRequest) -> dict[str, Any]:
    try:
        meta, candidates = fetch_page(req.url.strip())
    except AdapterError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    imagefetch.probe_all(candidates, referer=meta.final_url or meta.url)
    ranked = scoring.rank(candidates, meta, extract.work_keywords())
    slots = extract.extract_slots(meta, ranked[0] if ranked else None, req.video_url)

    analysis_id = imagefetch.cache_id(meta.final_url or meta.url)
    _analyses[analysis_id] = {"meta": meta, "candidates": ranked}

    return {
        "analysis_id": analysis_id,
        "meta": {
            "title": meta.title,
            "og_title": meta.og_title,
            "og_description": meta.og_description,
            "site_name": meta.site_name,
            "final_url": meta.final_url,
        },
        "slots": _slots_json(slots),
        "candidates": [_candidate_json(c) for c in ranked],
        "dropped": len(candidates) - len(ranked),
        "duplicate_warning": db.source_used(meta.final_url or meta.url),
    }


@app.get("/img/{cache_id}")
def serve_cached(cache_id: str) -> Response:
    blob = imagefetch.load_cached(cache_id)
    if blob is None:
        raise HTTPException(status_code=404, detail="キャッシュにありません")
    return Response(content=blob, media_type="image/jpeg")


@app.post("/api/drafts")
def drafts(req: DraftRequest) -> dict[str, Any]:
    entry = _analyses.get(req.analysis_id)
    if not entry:
        raise HTTPException(status_code=404, detail="解析結果が見つかりません。再解析してください。")
    meta: PageMeta = entry["meta"]
    cand = next((c for c in entry["candidates"] if c.cache_id == req.cache_id), None)

    slots = extract.extract_slots(meta, cand, req.video_url)
    slots = _apply_overrides(slots, req.overrides)
    generated = textgen.generate(slots, count=req.count)

    return {
        "slots": _slots_json(slots),
        "usable_templates": [t.get("id") for t in textgen.usable_templates(slots)],
        "drafts": [
            {
                "template_id": d.template_id,
                "template_type": d.template_type,
                "text": d.text,
                "phrase": d.phrase,
                "missing": d.missing,
            }
            for d in generated
        ],
    }


@app.post("/api/compose")
def compose_image(req: ComposeRequest) -> dict[str, Any]:
    blob = imagefetch.load_cached(req.cache_id)
    if blob is None:
        raise HTTPException(status_code=404, detail="元画像がキャッシュにありません")
    try:
        data, name = compose_mod.compose(
            blob,
            preset=req.preset,
            focus=req.focus,
            caption=req.caption,
            badge=req.badge,
            fmt=req.fmt,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"画像を加工できませんでした: {exc}") from exc

    (config.OUTPUT_DIR / name).write_bytes(data)
    return {
        "file": name,
        "url": f"/output/{name}",
        "bytes": len(data),
        "content_type": mimetypes.guess_type(name)[0] or "image/jpeg",
    }


@app.post("/api/record")
def record(req: RecordRequest) -> dict[str, Any]:
    post_id = db.record_post(**req.model_dump())
    return {"id": post_id}


@app.get("/api/history")
def get_history(limit: int = 50) -> dict[str, Any]:
    return {"posts": db.history(limit)}


@app.delete("/api/history/{post_id}")
def remove_history(post_id: int) -> dict[str, Any]:
    db.delete_post(post_id)
    return {"ok": True}


@app.post("/api/reload")
def reload_config() -> dict[str, Any]:
    """templates.yaml / dictionary.yaml を編集したあと、再起動せず反映する。"""
    dic = extract.reload_dictionary()
    tpl = textgen.reload_templates()
    return {"works": len(dic.get("works", [])), "templates": len(tpl)}


@app.get("/api/presets")
def presets() -> dict[str, Any]:
    return {
        "presets": {k: list(v) for k, v in compose_mod.PRESETS.items()},
        "font": config.resolve_font() or "",
    }

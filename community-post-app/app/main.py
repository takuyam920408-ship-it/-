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
from . import censor, config, db, extract, imagefetch, scoring, textgen
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


class PrepareRequest(BaseModel):
    """トリミングして、露出部分の候補を自動検出する（黒モザイクを置く前段）。"""

    cache_id: str
    preset: str = "square"
    focus: str = "center"
    grid: int = censor.GRID
    ratio: float = censor.CELL_SKIN_RATIO


class ComposeRequest(BaseModel):
    cache_id: str
    preset: str = "square"
    focus: str = "center"
    caption: str = ""          # 黒帯の解説文。必須
    badge: str = ""
    boxes: list[dict] = Field(default_factory=list)   # 黒モザイクをかける矩形
    censor_mode: str = "black"                         # black | mosaic | blur
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
def _jpeg_bytes(im) -> bytes:
    import io

    buf = io.BytesIO()
    im.convert("RGB").save(buf, "JPEG", quality=88)
    return buf.getvalue()


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
        # ダウンロードに失敗した画像はサムネが出せない。壊れた画像を見せる代わりに
        # 「取得できなかった」と明示するためのフラグ。
        "fetched": bool(cand.cache_id and imagefetch.cache_path(cand.cache_id).exists()),
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
    ranked, dropped = scoring.rank(candidates, meta, extract.work_keywords())
    slots = extract.extract_slots(meta, ranked[0] if ranked else None, req.video_url)

    analysis_id = imagefetch.cache_id(meta.final_url or meta.url)
    # 除外分も保持しておく。UI から「やっぱりこれを使う」と選べるようにするため。
    _analyses[analysis_id] = {"meta": meta, "candidates": ranked + dropped}

    fetched_ok = sum(
        1 for c in candidates if c.cache_id and imagefetch.cache_path(c.cache_id).exists()
    )

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
        "excluded": [_candidate_json(c) for c in dropped],
        "dropped": len(dropped),
        "diagnostics": {
            "found_in_html": len(candidates),
            "downloaded": fetched_ok,
            "kept": len(ranked),
            "excluded": len(dropped),
        },
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


@app.post("/api/prepare")
def prepare_image(req: PrepareRequest) -> dict[str, Any]:
    """指定サイズに切り抜いたプレビューを作り、露出（肌色）候補を自動検出する。

    検出結果はあくまで候補。顔も肌色なので顔も拾うし、影の濃い絵は外す。
    UI 側で人間が足し引きする前提。
    """
    blob = imagefetch.load_cached(req.cache_id)
    if blob is None:
        raise HTTPException(status_code=404, detail="元画像がキャッシュにありません")
    try:
        cropped = compose_mod.crop_image(blob, req.preset, req.focus)
        boxes = censor.detect(cropped, grid=req.grid, ratio=req.ratio)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"解析できませんでした: {exc}") from exc

    # 枠を描く前の素のトリミング画像をプレビュー用に保存する
    name = f"crop_{req.cache_id}_{req.preset}_{req.focus}.jpg"
    (config.OUTPUT_DIR / name).write_bytes(_jpeg_bytes(cropped))

    return {
        "url": f"/output/{name}",
        "width": cropped.width,
        "height": cropped.height,
        "boxes": [b.as_dict() for b in boxes],
    }


@app.post("/api/compose")
def compose_image(req: ComposeRequest) -> dict[str, Any]:
    blob = imagefetch.load_cached(req.cache_id)
    if blob is None:
        raise HTTPException(status_code=404, detail="元画像がキャッシュにありません")
    try:
        data, name, truncated = compose_mod.compose(
            blob,
            preset=req.preset,
            focus=req.focus,
            caption=req.caption,
            badge=req.badge,
            censor_boxes=[censor.Box.from_dict(b) for b in req.boxes],
            censor_mode=req.censor_mode,
            fmt=req.fmt,
        )
    except compose_mod.CompositionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"画像を加工できませんでした: {exc}") from exc

    (config.OUTPUT_DIR / name).write_bytes(data)
    return {
        "file": name,
        "url": f"/output/{name}",
        "bytes": len(data),
        "censored": len(req.boxes),
        "censor_mode": req.censor_mode,
        "truncated": truncated,
        "max_lines": compose_mod.MAX_CAPTION_LINES,
        "content_type": mimetypes.guess_type(name)[0] or "image/jpeg",
    }


class CaptionFitRequest(BaseModel):
    caption: str = ""
    preset: str = "square"


@app.post("/api/caption-fit")
def caption_fit(req: CaptionFitRequest) -> dict[str, Any]:
    """実際に使うフォントで測って、解説文が2行に収まるかを返す（入力中の確認用）。"""
    width = compose_mod.PRESETS.get(req.preset, compose_mod.PRESETS["square"])[0]
    return compose_mod.measure_caption(req.caption, width)


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


@app.post("/api/reveal-fonts")
def reveal_fonts() -> dict[str, Any]:
    """フォントの置き場を Finder（Mac）/ エクスプローラー（Windows）で開く。

    ローカル専用ツールなので OS のファイラを直接呼ぶ。開ける場所は
    assets/fonts に固定していて、任意のパスは受け取らない。
    """
    import subprocess
    import sys

    target = config.FONTS_DIR
    target.mkdir(parents=True, exist_ok=True)

    if sys.platform == "darwin":
        cmd = ["open", str(target)]
    elif sys.platform.startswith("win"):
        cmd = ["explorer", str(target)]
    else:
        cmd = ["xdg-open", str(target)]

    try:
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"フォルダを開けませんでした。手動で開いてください: {target}（{exc}）",
        ) from exc
    return {"opened": str(target)}


@app.get("/api/presets")
def presets() -> dict[str, Any]:
    return {
        "presets": {k: list(v) for k, v in compose_mod.PRESETS.items()},
        "censor_modes": ["black", "mosaic", "blur"],
        "max_caption_lines": compose_mod.MAX_CAPTION_LINES,
        "font": config.font_status(),
    }

"""FastAPI アプリ本体。ローカルで動かす半自動コミュニティ投稿アシスタント。

フロー: URL 貼り付け → 画像収集 → 1枚選ぶ → 加工 → 文面生成 → コピーして
YouTube Studio に貼る。最後の「投稿する」だけは人間の仕事（公式 API に
コミュニティ投稿の作成エンドポイントが無いため）。
"""
from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import compose as compose_mod
from . import censor, config, db, extract, imagefetch, scoring, textgen
from .adapters import AdapterError, dmm_api, fetch_page
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
        "error": cand.error,
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


def _register_single(cand: ImageCandidate, meta: PageMeta) -> dict[str, Any]:
    """1枚だけの画像を、解析結果と同じ形で扱えるように登録する。

    ページから取れない画像（JS 描画のサイト、手元のファイル）でも、
    以降のトリミング・黒モザイク・黒帯・文面生成をそのまま使えるようにする。
    """
    analysis_id = imagefetch.cache_id(meta.final_url or cand.url)
    _analyses[analysis_id] = {"meta": meta, "candidates": [cand]}
    slots = extract.extract_slots(meta, cand, "")
    return {
        "analysis_id": analysis_id,
        "meta": {
            "title": meta.title,
            "og_title": meta.og_title,
            "og_description": "",
            "site_name": meta.site_name,
            "final_url": meta.final_url,
        },
        "slots": _slots_json(slots),
        "candidates": [_candidate_json(cand)],
        "excluded": [],
        "dropped": 0,
        "diagnostics": {
            "mode": "single",
            "label": {
                "upload": "手元のファイル",
                "dmm": "DMM API のサンプル画像",
            }.get(cand.source, "直接指定した画像URL"),
            "found_in_html": 1,
            "downloaded": 1,
            "kept": 1,
            "excluded": 0,
        },
        "duplicate_warning": db.image_used(cand.url) if cand.url else None,
    }


@app.post("/api/upload")
async def upload_image(file: UploadFile = File(...)) -> dict[str, Any]:
    """手元の画像ファイルを読み込む。ページから画像が取れないときの入口。"""
    import hashlib
    import io

    from PIL import Image

    blob = await file.read()
    if not blob:
        raise HTTPException(status_code=400, detail="ファイルが空です。")
    if len(blob) > imagefetch.MAX_BYTES:
        raise HTTPException(status_code=400, detail="ファイルが大きすぎます（12MB まで）。")

    try:
        with Image.open(io.BytesIO(blob)) as im:
            width, height = im.size
    except Exception as exc:
        raise HTTPException(
            status_code=400, detail=f"画像として読めませんでした: {exc}"
        ) from exc

    cid = hashlib.sha1(blob).hexdigest()[:16]
    imagefetch.cache_path(cid).write_bytes(blob)

    name = file.filename or "uploaded"
    cand = ImageCandidate(
        url=f"file://{name}",
        source="upload",
        alt=Path(name).stem,
        width=width,
        height=height,
        cache_id=cid,
        score=100.0,
        reasons=[f"手元のファイル ({width}x{height})"],
    )
    meta = PageMeta(url="", final_url="", title=Path(name).stem, path_segments=[])
    return _register_single(cand, meta)


class ImageUrlRequest(BaseModel):
    url: str
    referer: str = ""


IMAGE_SUFFIXES = (".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".avif")


def _looks_like_page(url: str) -> bool:
    """画像URLではなく、Webページの URL を貼られたときに気づくための判定。"""
    path = url.split("?", 1)[0].split("#", 1)[0].lower()
    return not path.endswith(IMAGE_SUFFIXES)


@app.post("/api/image-url")
def add_image_url(req: ImageUrlRequest) -> dict[str, Any]:
    """画像の URL を直接受け取る。ページ解析では拾えない画像の入口。"""
    url = req.url.strip()
    if not url.lower().startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="http(s) の画像 URL を貼ってください。")

    cand = ImageCandidate(url=url, source="direct")
    try:
        imagefetch.probe(cand, referer=req.referer.strip())
    except Exception as exc:  # ここで落とすと UI に「Failed to fetch」しか出ない
        raise HTTPException(status_code=400, detail=f"取得に失敗しました: {exc}") from exc

    if cand.width is None or not imagefetch.cache_path(cand.cache_id).exists():
        hint = ""
        if _looks_like_page(url):
            hint = (
                "貼られたのは画像ではなく Web ページの URL のようです。"
                "この欄には画像そのものの URL（末尾が .jpg や .png のもの）を入れてください。"
                "ブラウザで画像を右クリック →「イメージのアドレスをコピー」で取得できます。"
            )
        elif cand.error:
            hint = cand.error
        else:
            hint = "サイトが外部からの取得を拒否している可能性があります。"
        raise HTTPException(
            status_code=400,
            detail=f"{hint} うまくいかない場合は、画像を手元に保存して①のファイル読み込みを使ってください。",
        )

    cand.score = 100.0
    cand.reasons = [f"直接指定 ({cand.width}x{cand.height})"]
    meta = PageMeta(url=url, final_url=url, title="", path_segments=[])
    return _register_single(cand, meta)


# --------------------------------------------------------------------------
# DMM アフィリエイト API（公式）からの取り込み
# --------------------------------------------------------------------------
class DmmCredentialsRequest(BaseModel):
    api_id: str
    affiliate_id: str


class DmmSearchRequest(BaseModel):
    keyword: str = ""
    cid: str = ""
    site: str = "FANZA"
    service: str = ""
    floor: str = ""
    hits: int = 20
    offset: int = 1
    sort: str = "rank"


class DmmPickRequest(BaseModel):
    image_url: str
    title: str = ""
    page_url: str = ""


@app.get("/api/dmm/status")
def dmm_status() -> dict[str, Any]:
    creds = dmm_api.load_credentials()
    return {
        "ready": creds.ready,
        "api_id_set": bool(creds.api_id),
        "affiliate_id": creds.affiliate_id,
        # API で使えるのは末尾 990〜999 の ID だけ。違うと API が 400 を返す
        "affiliate_id_valid": creds.affiliate_id_valid,
        "credentials_path": str(dmm_api.CREDENTIALS_PATH),
    }


@app.post("/api/dmm/credentials")
def dmm_save_credentials(req: DmmCredentialsRequest) -> dict[str, Any]:
    # 片方だけ直したい場合に備え、空欄は「変更しない」と解釈して既存値を残す
    current = dmm_api.load_credentials()
    api_id = req.api_id.strip() or current.api_id
    affiliate_id = req.affiliate_id.strip() or current.affiliate_id
    if not api_id or not affiliate_id:
        missing = []
        if not api_id:
            missing.append("API ID")
        if not affiliate_id:
            missing.append("アフィリエイト ID")
        raise HTTPException(
            status_code=400, detail=f"{' と '.join(missing)} が未設定です。入力してください。"
        )
    creds = dmm_api.save_credentials(api_id, affiliate_id)
    return {
        "ready": creds.ready,
        "affiliate_id": creds.affiliate_id,
        "affiliate_id_valid": creds.affiliate_id_valid,
    }


@app.post("/api/dmm/search")
def dmm_search(req: DmmSearchRequest) -> dict[str, Any]:
    if not req.keyword.strip() and not req.cid.strip():
        raise HTTPException(
            status_code=400,
            detail="キーワード、または商品ID（cid）か商品ページのURLを入れてください。",
        )
    # 商品ページの URL を貼られた場合は、そこから商品ID を取り出す
    cid = dmm_api.extract_cid(req.cid)
    if req.cid.strip() and not cid:
        raise HTTPException(
            status_code=400,
            detail="この URL から商品ID を読み取れませんでした。"
            "商品ページの URL（.../cid=xxxx/ を含むもの）を貼るか、商品ID を直接入れてください。",
        )
    try:
        items, raw = dmm_api.search(
            keyword=req.keyword.strip(),
            cid=cid,
            site=req.site,
            service=req.service.strip(),
            floor=req.floor.strip(),
            hits=req.hits,
            offset=req.offset,
            sort=req.sort,
        )
    except dmm_api.DmmApiError as exc:
        # 生の応答まで返す。原因の特定を1往復で終わらせるため。
        raise HTTPException(
            status_code=400, detail={"message": str(exc), "debug": exc.debug}
        ) from exc

    result = raw.get("result") or {}
    return {
        "items": [i.as_dict() for i in items],
        "total": result.get("total_count"),
        "returned": result.get("result_count"),
        "cid": cid,
        # 項目名がズレていた場合に画面で確認できるよう、1件目の生データを返す
        "raw_sample": (result.get("items") or [None])[0],
    }


@app.get("/api/dmm/floors")
def dmm_floors(site: str = "FANZA") -> dict[str, Any]:
    try:
        rows, _ = dmm_api.floors(site)
    except dmm_api.DmmApiError as exc:
        raise HTTPException(
            status_code=400, detail={"message": str(exc), "debug": exc.debug}
        ) from exc
    return {"floors": rows}


@app.post("/api/dmm/pick")
def dmm_pick(req: DmmPickRequest) -> dict[str, Any]:
    """選んだサンプル画像を1枚取り込み、以降の加工フローに流す。"""
    cand = ImageCandidate(url=req.image_url.strip(), source="dmm", alt=req.title)
    try:
        imagefetch.probe(cand, referer=req.page_url.strip() or "https://www.dmm.co.jp/")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"取得に失敗しました: {exc}") from exc
    if cand.width is None or not imagefetch.cache_path(cand.cache_id).exists():
        raise HTTPException(
            status_code=400,
            detail=f"この画像をダウンロードできませんでした。{cand.error or ''} "
            "手元に保存して①のファイル読み込みを使ってください。",
        )
    cand.score = 100.0
    cand.reasons = [f"DMM API のサンプル画像 ({cand.width}x{cand.height})"]
    meta = PageMeta(
        url=req.page_url,
        final_url=req.page_url,
        title=req.title,
        site_name="DMM",
        path_segments=[],
    )
    return _register_single(cand, meta)


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

"""DMM API の応答パースの検証。

実 API に接続できない環境でも壊れを検出できるよう、公開仕様にもとづく
模擬応答と、項目名が揺れた場合の応答の両方で確認する。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.adapters import dmm_api

# 公開仕様どおりの形
NORMAL = {
    "request": {},
    "result": {
        "status": 200,
        "result_count": 1,
        "total_count": 42,
        "items": [{
            "service_code": "digital",
            "content_id": "test00123",
            "product_id": "test00123",
            "title": "テスト作品タイトル",
            "URL": "https://www.dmm.co.jp/digital/videoa/-/detail/=/cid=test00123/",
            "affiliateURL": "https://al.dmm.co.jp/?lurl=xxx&af_id=abc-990",
            "date": "2026-09-01 10:00:00",
            "imageURL": {
                "list": "https://pics.example/list.jpg",
                "small": "https://pics.example/small.jpg",
                "large": "https://pics.example/large.jpg",
            },
            "sampleImageURL": {
                "sample_s": {"image": ["https://pics.example/s1.jpg", "https://pics.example/s2.jpg"]},
                "sample_l": {"image": ["https://pics.example/l1.jpg", "https://pics.example/l2.jpg"]},
            },
            "iteminfo": {
                "genre": [{"id": 1, "name": "ジャンルA"}, {"id": 2, "name": "ジャンルB"}],
                "maker": [{"id": 9, "name": "テストメーカー"}],
            },
        }],
    },
}

# 項目名や形が揺れたケース（単体 dict、小文字キー、画像が配列直置き）
WOBBLY = {
    "result": {
        "status": "200",
        "items": {
            "content_id": "wob00001",
            "title": "揺れたレスポンス",
            "url": "https://example.com/item",
            "affiliateUrl": "https://example.com/af",
            "imageUrl": {"small": "https://pics.example/only-small.jpg"},
            "sampleImageUrl": {"sample_l": ["https://pics.example/direct1.jpg"]},
            "iteminfo": {"maker": {"name": "単体メーカー"}},
        },
    },
}


def check(label, payload, expect):
    raw_items = payload["result"]["items"]
    if isinstance(raw_items, dict):
        raw_items = [raw_items]
    items = [dmm_api._item_to_dict(r) for r in raw_items]
    item = items[0]
    got = {
        "content_id": item.content_id,
        "title": item.title,
        "url": item.url,
        "affiliate_url": item.affiliate_url,
        "cover": item.cover,
        "samples": item.samples,
        "maker": item.maker,
        "genres": item.genres,
    }
    for key, want in expect.items():
        assert got[key] == want, f"[{label}] {key}: 期待 {want!r} / 実際 {got[key]!r}"
    print(f"  [{label}] OK  サンプル {len(item.samples)} 枚 / 表紙 {'あり' if item.cover else 'なし'}")


print("パース検証:")
check("公開仕様どおり", NORMAL, {
    "content_id": "test00123",
    "title": "テスト作品タイトル",
    "url": "https://www.dmm.co.jp/digital/videoa/-/detail/=/cid=test00123/",
    "affiliate_url": "https://al.dmm.co.jp/?lurl=xxx&af_id=abc-990",
    "cover": "https://pics.example/large.jpg",
    # 大きい方が先に来る
    "samples": ["https://pics.example/l1.jpg", "https://pics.example/l2.jpg",
                "https://pics.example/s1.jpg", "https://pics.example/s2.jpg"],
    "maker": "テストメーカー",
    "genres": ["ジャンルA", "ジャンルB"],
})
check("項目名・形が揺れた応答", WOBBLY, {
    "content_id": "wob00001",
    "title": "揺れたレスポンス",
    "url": "https://example.com/item",
    "affiliate_url": "https://example.com/af",
    "cover": "https://pics.example/only-small.jpg",
    "samples": ["https://pics.example/direct1.jpg"],
    "maker": "単体メーカー",
    "genres": [],
})

# 認証情報が無いときにきちんと止まるか
import os
os.environ.pop("DMM_API_ID", None)
os.environ.pop("DMM_AFFILIATE_ID", None)
if dmm_api.CREDENTIALS_PATH.exists():
    dmm_api.CREDENTIALS_PATH.unlink()
try:
    dmm_api.search(keyword="x")
    raise SystemExit("NG: 認証情報が無いのに通ってしまった")
except dmm_api.DmmApiError as e:
    print(f"  [認証情報なし] OK  {e}")

# 保存と読み込み
creds = dmm_api.save_credentials(" testapi ", " testaf-990 ")
loaded = dmm_api.load_credentials()
assert loaded.api_id == "testapi" and loaded.affiliate_id == "testaf-990", loaded
assert loaded.ready
print(f"  [認証情報の保存/読込] OK  権限 {oct(dmm_api.CREDENTIALS_PATH.stat().st_mode)[-3:]}")
dmm_api.CREDENTIALS_PATH.unlink()
print("すべて通過")

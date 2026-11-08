# spec と gazou.json の書き方

## テンプレートのファイル（remotion-kotaeawase/）

| ファイル | 中身 |
|---|---|
| `src/theme.ts` | 画面の値（1080×1920・30fps、オレンジの放射線、回る速さ、文字の色、置く範囲） |
| `src/spec.ts` | spec の形（型の定義） |
| `src/parts.tsx`・`src/cuts.tsx`・`src/Short.tsx` | 背景・写真・モザイク・テロップ・効果音・カットの画面 |
| `scripts/render.mjs` | 書き出し（`--stills` でカットごとの静止画） |
| `scripts/gazou.py` | 画像を集めて切り取る（Xの公開の埋め込み用の仕組み） |
| `scripts/xshot.js` | Xの投稿の画面のスクショ |
| `scripts/se.py` | 効果音を作る（自作） |
| `scripts/setup_voicevox.sh`・`scripts/koe.py` | VOICEVOX の用意と、声を作って秒数を合わせる |
| `scripts/predeliver.py` | 納品前チェック |
| `specs/<id>.json`・`specs/<id>.gazou.json` | 回ごとの設計図と画像の集め方（リポジトリに入れる） |
| `public/<id>/` | 回ごとの写真・声（リポジトリに入れない） |
| `public/se/` | 自作の効果音（リポジトリに入れる） |

## spec（specs/<id>.json）

```json
{
  "id": "touma-ami",
  "yomi": { "當真あみ": "とうまあみ", "20歳": "はたち" },
  "cuts": [
    { "type": "title", "pattern": "B", "dur": 3.8,
      "title": "同じポーズの13歳が\n19歳になったら\n大人びすぎやろｗ",
      "before": { "src": "touma-ami/p1_13sai_kao.jpg", "label": "出典：公式X" },
      "after": { "src": "touma-ami/p3_19sai_kao.jpg" }, "mosaic": 40 },
    { "type": "single", "dur": 3.6, "image": { "src": "touma-ami/p1_13sai.jpg" },
      "top": { "text": "スカウト直後の13歳", "color": "green" },
      "bottom": [{ "text": "この時点で\n透明感すごいやん", "color": "red", "at": 1.7 }] },
    { "type": "single", "dur": 3.3, "mosaic": 40, "image": { "src": "touma-ami/p3_19sai_kao.jpg" },
      "top": { "text": "今年また\n同じポーズで撮ったって", "color": "blue" },
      "bottom": [{ "text": "ほな答え合わせや", "color": "red", "at": 2.0 }] },
    { "type": "reveal", "dur": 4.1, "se": "se/kokai_jan.wav", "image": { "src": "touma-ami/p3_19sai.jpg" },
      "top": { "text": "そんで19歳がこれや", "color": "red" },
      "bottom": [{ "text": "6年でこうなるんか", "color": "purple", "at": 1.7 },
                 { "text": "凛としすぎやろ", "color": "red", "at": 3.0 }] },
    { "type": "compare", "layout": "side", "dur": 5.0,
      "images": [{ "src": "touma-ami/p1_13sai_hikaku.jpg" }, { "src": "touma-ami/p3_19sai.jpg" }],
      "top": { "text": "左が13歳\n右が19歳", "color": "green" },
      "bottom": [{ "text": "大人びても\n透明感そのままや", "color": "red", "at": 2.2 }] }
  ]
}
```

- `type`：`title`（冒頭画面。`pattern` A＝縦／B＝横／C＝まるごとモザイク）、`single`、`reveal`（公開。下テロップ2つまで）、`compare`（2枚比較。`layout`: `vertical`＝上下／`side`＝左右）、`wide`（横長のキャプチャ）
- テロップの `color`：`blue` 説明／`green` 日付・年齢・肩書き／`red` 強調・数字・決め／`orange` 強調の2色目／`purple` ツッコミ
- 写真：`src`（public/ からのパス）、`label`（出典の控え。画面には出さない）、`tag`（2枚比較のラベル）、`focusY`（枠いっぱいに切り取るときの縦の中心 0〜1）
- `single` の `mosaic`：溜めのカットで今の写真をモザイクのまま見せる。次の `reveal` で外す
- 一番上に置けるもの：`yomi`（読みの直し）、`sfx`（`title`・`telop`・`cut`・`volume`）、`creditLabels`（true で画面に出典ラベル。ふだんは書かない）
- `voice`・`dur`・`at` は `scripts/koe.py` が書き込む

## gazou.json（specs/<id>.gazou.json）

```json
{
  "id": "touma-ami",
  "sources": [
    { "name": "sanmai", "x_status": "2116473448457511310", "index": 1, "size": [1180, 1884] }
  ],
  "files": [
    { "photo": "写真1", "file": "p1_13sai.jpg", "from": "sanmai", "crop": [88, 0, 585, 852], "what": "2020年10月の宣材写真（カット2）" },
    { "photo": "写真3", "file": "p3_19sai_kao.jpg", "from": "sanmai", "crop": [242, 984, 893, 1745], "what": "19歳の肩から上（冒頭のモザイク）" }
  ],
  "manual": ["写真4：投稿の画面のスクショ（xshot.js）を p4_post.png に置く"]
}
```
- `sources`：Xの投稿（`x_status`）と、何枚目の画像か（`index`）。`size` を書くと、画像の大きさが変わっていたら止まる（切り取り範囲がずれるのを防ぐ）
- `files`：切り取ったファイル。`crop` は [左, 上, 右, 下]（元の画像のピクセル）。書かなければそのまま
- `manual`：手で用意するもの（Instagram・スクショなど）。最後に表示される
- できるもの：`public/<id>/raw/`（元の画像）、`public/<id>/<file>`、`public/<id>/画像の出どころ.json`

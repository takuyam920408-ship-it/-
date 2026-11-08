# remotion-kotaeawase

「答え合わせ速報」のショート動画テンプレート（Remotion）。1本ぶんの中身を `specs/<id>.json` に書くと、デザインどおりの縦動画（1080×1920・30fps）を書き出す。
デザインの値は `../スキル/geinou-beforeafter-daihon/references/edit-design.md` と同じ（`src/theme.ts`）。

## 使い方

```
npm install
node scripts/render.mjs mihon            # out/mihon.mp4 を書き出す
node scripts/render.mjs mihon --stills   # 各カットの終わりの画を out/still/ に書き出す（確認用・サムネ用）
npx remotion studio                      # ブラウザで見ながら調整する
```

- 画像・音声は `public/<id>/` に置き、spec からは `<id>/ファイル名` で指す
- 画像は `python3 scripts/gazou.py <id>` で集める。`specs/<id>.gazou.json` に書いた本人・公式のXの投稿から画像を取り、決めた範囲で切り取って `public/<id>/` に置き、`画像の出どころ.json` を残す（Pillow と curl が必要）。スクショなど手で用意するものは `manual` に書いておくと、最後に表示される
- 見本（`specs/mihon.json`・`public/mihon/`）はグレーの仮画像
- **本番の回の画像・音声はリポジトリに入れない**（`.gitignore` で `public/` は `mihon` 以外を外してある）。芸能人の写真をGitHubに上げないため
- クラウドの環境では入っているヘッドレスのChromeを使う。Macでは Remotion が自分で用意する

## spec の書き方

```json
{
  "id": "arakawa-chika",
  "cuts": [
    { "type": "title", "pattern": "A", "dur": 3.5, "title": "冒頭の文\n2〜3行",
      "before": { "src": "arakawa-chika/mukashi1.jpg", "label": "出典：〇〇" },
      "after":  { "src": "arakawa-chika/ima_kao.jpg" }, "mosaic": 48 },
    { "type": "single", "dur": 3.8, "image": { "src": "...", "label": "出典：本人のInstagram" },
      "top": { "text": "上テロップ", "color": "green" },
      "bottom": [{ "text": "下テロップ", "color": "purple", "at": 2.0 }] },
    { "type": "reveal", "dur": 4.6, "image": { "src": "..." }, "top": { "text": "そんで今がこれや", "color": "red" },
      "bottom": [{ "text": "誰やねん", "color": "purple", "at": 1.6 }, { "text": "垢抜けすぎやろ", "color": "red", "at": 2.8 }],
      "se": "se/odoroki.mp3" },
    { "type": "compare", "dur": 5.0,
      "images": [{ "src": "...", "tag": "10年前", "label": "出典：〇〇" }, { "src": "...", "tag": "今", "label": "出典：〇〇" }],
      "top": { "text": "上が10年前\n下が今", "color": "green" }, "bottom": [{ "text": "締めの一言", "color": "red", "at": 2.4 }] }
  ]
}
```

| カットの type | 中身 |
|---|---|
| `title` | 冒頭画面（サムネも兼ねる）。`pattern` A＝縦に昔→↓→モザイクの今／B＝横に昔→赤い→→モザイクの今／C＝1枚まるごとモザイク。`after` は肩から上に切り取った画像を使う |
| `single` | 写真1枚＋上テロップ＋下テロップ |
| `reveal` | 公開カット。下テロップを2つまで、あとのものを上に積む |
| `compare` | 2枚比較（上＝昔、下＝今。`"layout": "side"` で左＝昔、右＝今）。`tag` で「10年前」「今」のラベル |
| `wide` | 横長のテレビのキャプチャ（下テロップは写真の下に出る） |

- テロップの `color`：`blue` 説明／`green` 日付・年齢・肩書き／`red` 強調・数字・決め／`orange` 強調の2色目／`purple` ツッコミ
- 改行は `\n`。1行11字・1枠2行まで（台本スキルのルール）
- `at`：カットが始まってから何秒後に出すか（下テロップの既定は2.0秒）
- 写真は、`single`・`reveal`・`wide` では枠の中に全体を収め、`title`・`compare` では枠いっぱいに切り取る（顔が上寄りに入るように）
- 写真ごとの `focusY`：枠いっぱいに切り取るとき、縦のどこを中心にするか（0＝上の端〜1＝下の端、既定0.3）。顔が切れるときに使う
- `single` の `mosaic`：公開の直前の溜めのカットで、今の写真をモザイクのまま見せるとき（例：`"mosaic": 40`）。次の `reveal` で同じ写真をモザイクなしで出すと「答え合わせ」になる
- `compare` の `"layout": "side"`：2枚を左右に並べる（縦長の写真向き。上テロップは「左が〇〇 右が〇〇」）。省略すると上下に並べる
- タイトル枠は1行10字まで（画面の幅。数字は半角で2字＝全角1字くらい）。超えると折り返して4行になるので、行の分け方を変える
- 公開より前のカットの出典ラベルに、答えが分かる名前を書かない（例：「出典：本人の公式X」）。公開の後は正式な名前にする

## 声・効果音・BGM（Macで入れる）

- 読み上げは VOICEVOX の青山龍星。カットごとに、テロップを上→下の順に読んだ音声を作り、`public/<id>/voice/cut01.wav` のように置いて、各カットに `"voice": "<id>/voice/cut01.wav"` を足す
- 各カットの `dur` は、音声の長さ＋0.3秒以上にする。下テロップの `at` は、読み上げで下テロップを読み始める秒に合わせる
- 効果音は公開カットに `"se"`、BGMは spec の一番上に `"bgm"`（`"bgmVolume"` で音量、既定0.12）
- 概要欄のクレジット：`VOICEVOX:青山龍星`

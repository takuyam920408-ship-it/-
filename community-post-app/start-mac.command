#!/bin/bash
# ───────────────────────────────────────────────
#  コミュニティ投稿アシスタント（Mac 用 起動ファイル）
#  Finder でこのファイルをダブルクリックすれば、
#  初回は準備、2回目以降はそのまま起動します。
# ───────────────────────────────────────────────

cd "$(dirname "$0")" || exit 1

# エラーで終わるときは、メッセージを読めるように窓を開けたままにする
stop() {
  echo ""
  echo "────────────────────────────────"
  echo "$1"
  echo "────────────────────────────────"
  echo ""
  read -r -p "Enter キーを押すと閉じます: " _
  exit 1
}

echo "コミュニティ投稿アシスタント"
echo ""

# ── 1. Python があるか ────────────────────────
if ! command -v python3 >/dev/null 2>&1; then
  echo "Python が見つかりませんでした。"
  echo "ダウンロードページを開きます。macOS 用の最新版を入れてから、"
  echo "もう一度このファイルをダブルクリックしてください。"
  open "https://www.python.org/downloads/macos/" 2>/dev/null
  stop "Python をインストールしてから、やり直してください。"
fi

PYV=$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null)
echo "Python $PYV を使います"

# ── 2. 初回だけ準備（専用の置き場を作って部品を入れる）──
if [ ! -d ".venv" ]; then
  echo ""
  echo "初回の準備をしています（数分かかります。そのままお待ちください）…"
  python3 -m venv .venv || stop "準備に失敗しました。Python を入れ直すと直ることが多いです。"
fi

# shellcheck disable=SC1091
source .venv/bin/activate || stop "準備した置き場を読み込めませんでした。.venv フォルダを削除してやり直してください。"

if [ ! -f ".venv/.installed" ] || [ requirements.txt -nt ".venv/.installed" ]; then
  echo "必要な部品をインストールしています…"
  python -m pip install --upgrade pip --quiet
  python -m pip install -r requirements.txt --quiet || stop "部品のインストールに失敗しました。ネット接続を確認してやり直してください。"
  touch ".venv/.installed"
  echo "準備できました"
fi

# ── 3. 空いているポートを探す ─────────────────
PORT=$(python - <<'PY'
import socket
for p in range(8000, 8050):
    with socket.socket() as s:
        try:
            s.bind(("127.0.0.1", p))
        except OSError:
            continue
        print(p)
        break
else:
    print(0)
PY
)
[ "$PORT" = "0" ] && stop "空いているポートが見つかりませんでした。Mac を再起動してやり直してください。"

URL="http://127.0.0.1:$PORT"

# ── 4. 起動して、ブラウザを開く ───────────────
echo ""
echo "起動しています…  $URL"
echo ""
echo "  ブラウザが自動で開きます。"
echo "  終わるときは、この黒い窓で  control + C  を押してください。"
echo ""

( sleep 3; open "$URL" 2>/dev/null ) &

python -m uvicorn app.main:app --host 127.0.0.1 --port "$PORT"

echo ""
read -r -p "終了しました。Enter キーを押すと閉じます: " _

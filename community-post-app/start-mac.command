#!/bin/bash
# ───────────────────────────────────────────────
#  コミュニティ投稿アシスタント（Mac 用 起動ファイル）
#  Finder でこのファイルをダブルクリックすれば、
#  初回は準備、2回目以降はそのまま起動します。
# ───────────────────────────────────────────────

cd "$(dirname "$0")" || exit 1

# 何が起きたか必ず残す。窓が一瞬で閉じても、このファイルを見れば原因が分かる。
LOG="start-log.txt"
exec > >(tee "$LOG") 2>&1
echo "=== $(date '+%Y-%m-%d %H:%M:%S') 起動 ==="

# エラーで終わるときは、メッセージを読めるように窓を開けたままにする
stop() {
  echo ""
  echo "────────────────────────────────"
  echo "$1"
  echo ""
  echo "この内容は start-log.txt にも保存してあります。"
  echo "困ったときは、次の1行をターミナルに貼ると中身を表示できます:"
  echo "  cat ~/Desktop/community-post/community-post-app/start-log.txt"
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

# ── 1.5 更新の取り込み ────────────────────────
# 毎回ターミナルで git pull させなくて済むように、ここで自動更新する。
# 自分で編集したファイルがあるときは触らない。失敗しても起動は続ける。
if [ "${CPA_NO_UPDATE:-0}" != "1" ] && command -v git >/dev/null 2>&1 && [ -d ../.git ]; then
  # --untracked-files=no: 置いただけのファイル（フォント等）は編集とみなさない
  if [ -n "$(git status --porcelain --untracked-files=no 2>/dev/null)" ]; then
    echo "追跡中のファイルを編集しているため、更新の取り込みは飛ばします"
  else
    echo "更新を確認しています…"
    BEFORE=$(git rev-parse HEAD 2>/dev/null)
    # 認証を聞かれて固まらないようにする（聞かれたら諦めてそのまま起動する）
    if GIT_TERMINAL_PROMPT=0 GIT_ASKPASS=/usr/bin/true git pull --quiet --ff-only 2>/dev/null; then
      AFTER=$(git rev-parse HEAD 2>/dev/null)
      if [ "$BEFORE" != "$AFTER" ]; then
        echo "新しい版に更新しました"
      else
        echo "すでに最新です"
      fi
    else
      echo "（更新を取得できませんでした。そのまま起動します）"
    fi
  fi
fi

# ── 2. 初回だけ準備（専用の置き場を作って部品を入れる）──
if [ ! -d ".venv" ]; then
  echo ""
  echo "初回の準備をしています（数分かかります。そのままお待ちください）…"
  python3 -m venv .venv || stop "準備に失敗しました。Python を入れ直すと直ることが多いです。"
fi

# shellcheck disable=SC1091
source .venv/bin/activate || stop "準備した置き場を読み込めませんでした。.venv フォルダを削除してやり直してください。"

if [ ! -f ".venv/.installed" ] || [ requirements.txt -nt ".venv/.installed" ]; then
  echo ""
  echo "必要な部品をインストールします。"
  echo "初回や更新後は数分かかります。下に進捗が流れるので、止まって見えても待ってください。"
  echo "────────────────────────────────"
  python -m pip install --upgrade pip --quiet 2>/dev/null
  # 進捗を隠さない（--quiet を付けると固まったように見えるため）。
  # まずビルド済み（wheel）だけで入れる。これならコンパイルが走らず速い。
  if ! python -m pip install -r requirements.txt --only-binary=:all: --progress-bar on; then
    echo ""
    echo "ビルド済みの部品が揃っていませんでした。ソースからのビルドを含めて入れ直します…"
    echo "（ここは時間がかかります。数分〜十数分かかることがあります）"
    if ! python -m pip install -r requirements.txt --progress-bar on; then
      stop "部品のインストールに失敗しました。上に出ているエラーをそのまま貼って相談してください。"
    fi
  fi
  touch ".venv/.installed"
  echo "────────────────────────────────"
  echo "準備できました"
fi

# ── 3. けいふぉんとの確認 ─────────────────────
FONT_FOUND=$(python -c 'import sys; sys.path.insert(0, "."); from app import config; print(config.find_keifont() or "")' 2>/dev/null)
if [ -z "$FONT_FOUND" ]; then
  echo ""
  echo "※ けいふぉんとが見つかりません。いまは代替フォントで描画します。"
  echo "   assets/fonts/ に keifont.ttf を置くと、自動でそちらを使います。"
  if [ ! -f ".venv/.font_notice" ]; then
    echo "   配布ページを開きます（次回からは開きません）"
    open "https://font.sumomo.ne.jp/font_1.html" 2>/dev/null
    touch ".venv/.font_notice"
  fi
else
  echo "けいふぉんとを使います"
fi

# ── 4. 空いているポートを探す ─────────────────
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

# ── 5. 起動して、ブラウザを開く ───────────────
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

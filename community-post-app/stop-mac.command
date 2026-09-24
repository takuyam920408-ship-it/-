#!/bin/bash
# ───────────────────────────────────────────────
#  コミュニティ投稿アシスタント（終了）
#  使い終わってアプリを止めたいときに、このファイルを
#  ダブルクリックしてください。
# ───────────────────────────────────────────────

cd "$(dirname "$0")" || exit 1

PIDFILE=".server.pid"
URLFILE=".server.url"

echo "コミュニティ投稿アシスタント（終了）"
echo ""

if [ ! -f "$PIDFILE" ]; then
  echo "動いていないようです。何もしませんでした。"
  echo ""
  read -r -p "Enter キーを押すと閉じます: " _
  exit 0
fi

PID=$(cat "$PIDFILE" 2>/dev/null)
if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then
  kill "$PID" 2>/dev/null
  # 終わるのを少し待ち、しぶとければ強制的に止める
  for _ in $(seq 1 10); do
    kill -0 "$PID" 2>/dev/null || break
    sleep 1
  done
  kill -0 "$PID" 2>/dev/null && kill -9 "$PID" 2>/dev/null
  echo "アプリを終了しました。"
else
  echo "すでに終了していました。"
fi

rm -f "$PIDFILE" "$URLFILE" ".server.rev"
echo ""
echo "また使うときは start-mac.command をダブルクリックしてください。"
echo ""
read -r -p "Enter キーを押すと閉じます: " _

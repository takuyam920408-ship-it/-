#!/usr/bin/env bash
# ローカルで起動して http://127.0.0.1:8000 を開く
set -euo pipefail
cd "$(dirname "$0")"
python3 -m uvicorn app.main:app --host 127.0.0.1 --port "${PORT:-8000}" --reload

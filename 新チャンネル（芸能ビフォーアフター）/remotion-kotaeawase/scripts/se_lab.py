#!/usr/bin/env python3
"""ベンチマーク（こっそり速報の1位の動画）と同じ効果音を、効果音ラボから取ってくる。
使い方：python3 scripts/se_lab.py  → public/se/bm/ に T.mp3・B.mp3・C.mp3・D.mp3 を置く

どの音かは、ユーザーが送ってくれたベンチマークの動画の音を分析して、効果音ラボの1195個の音と形を照らし合わせて決めた（2026-11-08）：
  T＝和太鼓でドドン（冒頭の画面）／C＝小パンチ（低い声＝bのテロップ）／B＝パフ（bのテロップ。C・B・C・C・Bの順）／D＝きらーん1（公開と最後のカットの上テロップ）
  声a（冒頭の文と同じ声）のテロップは効果音なし。BGMなし
効果音ラボの規約：商用利用無料・クレジット不要・収益化したYouTube動画で使ってよい。ただしファイルそのものを配るのは禁止。
→ ファイルはリポジトリに入れない（.gitignore で public/se/bm/ を外してある）。使う場所でこのスクリプトを1回まわす
通信先：soundeffect-lab.info（直接のダウンロードは断られるので、そのページから来たことを示す Referer を付ける）
"""
import os
import subprocess
import sys

FILES = {
    'T': ('https://soundeffect-lab.info/sound/anime/mp3/drum-japanese2.mp3', 'https://soundeffect-lab.info/sound/anime/', '和太鼓でドドン'),
    'C': ('https://soundeffect-lab.info/sound/battle/mp3/punch-middle2.mp3', 'https://soundeffect-lab.info/sound/battle/', '小パンチ'),
    'B': ('https://soundeffect-lab.info/sound/anime/mp3/pafu1.mp3', 'https://soundeffect-lab.info/sound/anime/', 'パフ'),
    'D': ('https://soundeffect-lab.info/sound/anime/mp3/eye-shine1.mp3', 'https://soundeffect-lab.info/sound/anime/', 'きらーん1'),
}
root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
out = os.path.join(root, 'public', 'se', 'bm')
os.makedirs(out, exist_ok=True)
ng = 0
for k, (url, ref, name) in FILES.items():
    dest = os.path.join(out, f'{k}.mp3')
    if os.path.exists(dest) and os.path.getsize(dest) > 2000:
        print('ある', k, name)
        continue
    subprocess.run(['curl', '-sS', '-L', '--retry', '4', '-A', 'Mozilla/5.0', '-e', ref, '-o', dest, url], check=False)
    ok = os.path.exists(dest) and os.path.getsize(dest) > 2000
    if not ok:
        ng += 1
        if os.path.exists(dest):
            os.remove(dest)
    print('取得' if ok else '失敗', k, name)
sys.exit(1 if ng else 0)

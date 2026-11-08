#!/usr/bin/env python3
"""回ごとの画像を、元の投稿から取って切り取り、public/<id>/ に置く。

使い方：python3 scripts/gazou.py <id>
  specs/<id>.gazou.json を読み、
  - 本人・公式のXの投稿の画像を、埋め込み用の公開の仕組み（cdn.syndication.twimg.com）で取る
  - 決めた範囲で切り取る（写真の中身は加工しない。切り取りだけ）
  - public/<id>/raw/ に元の画像、public/<id>/ に切り取った画像、public/<id>/画像の出どころ.json を書く
  画像は芸能人の写真なので、リポジトリには入れない（.gitignore で public/ を外してある）。
  通信は curl を使う（クラウドのプロキシとMacの両方でそのまま動くように）。Pillow が必要。
"""
import datetime
import json
import math
import os
import subprocess
import sys

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def curl(url, out=None):
    cmd = ['curl', '-sS', '-L', '--compressed', '--fail', '--max-time', '60', url]
    if out:
        cmd += ['-o', out]
        subprocess.run(cmd, check=True)
        return None
    return subprocess.run(cmd, check=True, capture_output=True).stdout


def x_token(status_id):
    # 埋め込み用の仕組みが求める token（status ID から計算する）
    n = (int(status_id) / 1e15) * math.pi
    s = ''
    # JavaScript の Number.prototype.toString(36) に近い形にする（末尾の桁が違っても通ることを2026-11-08に確認）
    whole = int(n)
    frac = n - whole
    digits = '0123456789abcdefghijklmnopqrstuvwxyz'
    w = ''
    while whole:
        w = digits[whole % 36] + w
        whole //= 36
    f = ''
    for _ in range(12):
        frac *= 36
        d = int(frac)
        f += digits[d]
        frac -= d
    s = (w or '0') + '.' + f
    return s.replace('0', '').replace('.', '')


def fetch_x(status_id):
    url = f'https://cdn.syndication.twimg.com/tweet-result?id={status_id}&lang=ja&token={x_token(status_id)}'
    return json.loads(curl(url))


def main():
    if len(sys.argv) < 2:
        sys.exit('使い方：python3 scripts/gazou.py <id>')
    ep = sys.argv[1]
    conf = json.load(open(os.path.join(ROOT, 'specs', f'{ep}.gazou.json'), encoding='utf-8'))
    out = os.path.join(ROOT, 'public', ep)
    raw = os.path.join(out, 'raw')
    os.makedirs(raw, exist_ok=True)
    now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9))).isoformat(timespec='seconds')

    sources = {}
    for src in conf['sources']:
        sid = src['x_status']
        t = fetch_x(sid)
        media = [m for m in t.get('mediaDetails', []) if m.get('type') == 'photo']
        m = media[src.get('index', 1) - 1]
        img_url = m['media_url_https'] + '?name=orig'
        path = os.path.join(raw, f"x_{sid}_{src.get('index', 1)}.jpg")
        curl(img_url, path)
        size = Image.open(path).size
        want = src.get('size')
        if want and list(size) != list(want):
            sys.exit(f"{src['name']}：画像の大きさが {size} で、切り取りの前提 {want} と違う。切り取りの範囲を見直す")
        sources[src['name']] = {
            'path': path,
            'page_url': f"https://x.com/{t['user']['screen_name']}/status/{sid}",
            'image_url': img_url,
            'account': f"{t['user']['name']}（@{t['user']['screen_name']}）",
            'status_id': sid,
            'posted_at': t.get('created_at'),
            'likes_at_fetch': t.get('favorite_count'),
        }
        print('取得', src['name'], size, sources[src['name']]['page_url'])

    record = []
    for f in conf['files']:
        s = sources[f['from']]
        im = Image.open(s['path']).convert('RGB')
        if f.get('crop'):
            im = im.crop(tuple(f['crop']))
        dest = os.path.join(out, f['file'])
        im.save(dest, quality=95)
        record.append({
            '写真': f.get('photo'), 'ファイル': f['file'], '何の写真か': f.get('what'),
            '元のページ': s['page_url'], '画像のURL': s['image_url'], '投稿者': s['account'],
            'status ID': s['status_id'], '投稿日時（UTC）': s['posted_at'],
            '取得時のいいね数': s['likes_at_fetch'], '切り取り': f.get('crop'), '取得日時': now,
        })
        print('切り取り', f['file'], im.size)
    for f in conf.get('manual', []):
        print('手で用意するもの：', f)
    json.dump(record, open(os.path.join(out, '画像の出どころ.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print('出どころ：', os.path.join(out, '画像の出どころ.json'))


if __name__ == '__main__':
    main()

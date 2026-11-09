#!/usr/bin/env python3
"""納品前チェック（答え合わせ速報）。投稿の前に毎回まわす。

使い方：python3 scripts/predeliver.py <id> <プレーン版の台本.txt> [<カット割り版.txt>]
  例：python3 scripts/predeliver.py touma-ami ../當真あみ_台本.txt ../當真あみ_台本_編集カット割り.txt
すべて「OK」なら投稿に進んでよい。「NG」が1つでもあれば直す。「注意」は目で確かめる。
"""
import json
import os
import re
import subprocess
import sys
import wave

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REVEAL_RANGE = {'A': (13, 16), 'B': (7, 12), 'C': (10, 13)}
results = []


def check(ok, msg, level='NG'):
    results.append(('OK' if ok else level, msg))


def n(t):
    """字数：スペース・改行・“”は数えない。半角の文字（英数字・記号）は0.5字"""
    return sum(0.5 if ch.isascii() else 1 for ch in t if ch not in ' \n　“”')


def short(t):
    t = t.replace('\n', '／')
    return t if len(t) <= 14 else t[:14] + '…'


def wav_len(path):
    with wave.open(path) as w:
        return w.getnframes() / w.getframerate()


def texts_of(cut):
    return [cut['title']] if cut['type'] == 'title' else [cut['top']['text']] + [b['text'] for b in cut['bottom']]


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    ep, plain_path = sys.argv[1], sys.argv[2]
    cut_path = sys.argv[3] if len(sys.argv) > 3 else None
    spec = json.load(open(os.path.join(ROOT, 'specs', f'{ep}.json'), encoding='utf-8'))
    plain = open(plain_path, encoding='utf-8').read()
    cutfile = open(cut_path, encoding='utf-8').read() if cut_path else None
    cuts = spec['cuts']
    pub = os.path.join(ROOT, 'public')

    # 1. 素材がそろっているか（仮の画像が残っていないか）
    srcs = []
    for c in cuts:
        for k in ('before', 'after', 'image'):
            if c.get(k):
                srcs.append(c[k]['src'])
        for im in c.get('images', []):
            srcs.append(im['src'])
        for k in ('voice', 'se'):
            if c.get(k):
                srcs.append(c[k])
    if spec.get('bgm'):
        srcs.append(spec['bgm'])
    missing = [s for s in srcs if not os.path.exists(os.path.join(pub, s))]
    check(not missing, f'素材のファイルがそろっている{"（ない：" + ", ".join(missing) + "）" if missing else ""}')
    kari = [s for s in srcs if '_kari' in s]
    check(not kari, f'仮の画像が残っていない{"（" + ", ".join(kari) + "）" if kari else ""}')
    check(all(c.get('voice') for c in cuts), '全カットに声がある')

    # 2. 秒数と公開の位置
    total = sum(c['dur'] for c in cuts)
    check(27 <= total <= 31, f'合計 {total:.1f}秒（27〜31秒。ベンチマーク①1位は29.2秒）')
    check(len(cuts) == 7, f'{len(cuts)}カット（ベンチマーク①1位と同じ7カット）', '注意')
    m = re.search(r'【型】\s*([ABC])', plain)
    t = 0
    for c in cuts:
        if c['type'] == 'reveal':
            break
        t += c['dur']
    if m:
        lo, hi = REVEAL_RANGE[m.group(1)]
        check(lo <= t <= hi, f'公開 {t:.1f}秒（型{m.group(1)}は{lo}〜{hi}秒）')
    first = cuts[0]
    if not first.get('voice'):
        need = n(first['title']) / 7 + 0.3 if first['type'] == 'title' else 0
        check(first['dur'] >= need - 0.01, f'カット1 {first["dur"]}秒（声がないので、冒頭の文の字数÷7＋0.3＝{need:.2f}秒以上）')

    # 3. テロップの字数・行・出すタイミング・声の長さ
    tot_chars = 0
    for i, c in enumerate(cuts, 1):
        for k, tx in enumerate(texts_of(c)):
            tot_chars += n(tx)
            lines = tx.split('\n')
            if c['type'] == 'title':
                check(len(lines) <= 3 and max(n(l) for l in lines) <= 10, f'カット{i} タイトル枠は3行・1行10字まで（{short(tx)}）')
            else:
                check(6 <= n(tx) <= 15, f'カット{i} テロップ{k + 1}は6〜15字（{n(tx)}字：{short(tx)}）')
                check(len(lines) <= 2 and max(n(l) for l in lines) <= 11, f'カット{i} テロップ{k + 1}は2行・1行11字まで')
        if c['type'] != 'title':
            check(len(c['bottom']) <= (2 if c['type'] == 'reveal' else 1), f'カット{i} 下テロップの数（公開だけ2つ）')
            if not c.get('voice'):
                top_end = n(c['top']['text']) / 7
                ends = [(b.get('at', 2), b.get('at', 2) + n(b['text']) / 7) for b in c['bottom']]
                check(ends[0][0] >= top_end - 0.05, f'カット{i} 下は上を読み終えてから出る', '注意')
                check(max(e for _, e in ends) <= c['dur'], f'カット{i} カットの中で読み終わる', '注意')
        if c.get('voice') and os.path.exists(os.path.join(pub, c['voice'])):
            vl = wav_len(os.path.join(pub, c['voice']))
            check(c['dur'] >= vl + 0.25 - 0.01, f'カット{i} 秒数 {c["dur"]} ≥ 声 {vl:.2f}＋0.25（ベンチマークは0.26）')
    n_telops = sum(len(texts_of(c)) for c in cuts)
    check(n_telops == 14, f'テロップ {n_telops}個（ベンチマーク①1位は14個）', '注意')
    check(150 <= tot_chars <= 190, f'テロップ合計 {tot_chars}字（150〜190字。ベンチマーク①1位は約175字。長さは声で測った秒数で決める）', '注意')

    # 4. 2つの台本と設計図のテロップが同じか
    for i, c in enumerate(cuts, 1):
        for tx in texts_of(c):
            check(tx in plain, f'カット{i}「{short(tx)}」がプレーン版にある')
            if cutfile is not None:
                check(tx in cutfile, f'カット{i}「{short(tx)}」がカット割り版にある')

    # 5. 概要欄：出典・クレジット・メモが残っていないか
    desc = plain.split('【概要欄】', 1)[-1].split('【要確認】', 1)[0]
    rec = os.path.join(pub, ep, '画像の出どころ.json')
    if os.path.exists(rec):
        pages = sorted({r['元のページ'] for r in json.load(open(rec, encoding='utf-8'))})
        miss = [p for p in pages if p not in desc]
        check(not miss, f'画像の出どころ.json の元のページが、全部概要欄にある{"（ない：" + ", ".join(miss) + "）" if miss else ""}')
    else:
        check(False, '画像の出どころ.json がない（scripts/gazou.py で作る）', '注意')
    for cr in spec.get('voiceCredits', ['VOICEVOX:青山龍星']):
        check(cr in desc, f'概要欄に「{cr}」')
    check('効果音' in desc, '概要欄に効果音のクレジット')
    memo = re.findall(r'（[^）]*(あとで|要確認|TODO|〇〇)[^）]*）', desc)
    check(not memo, '概要欄にメモ（あとで・〇〇など）が残っていない')

    # 6. 書き出した動画
    out = os.path.join(ROOT, 'out', f'{ep}_kansei.mp4')
    if os.path.exists(out):
        d = float(subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', out], capture_output=True, text=True).stdout or 0)
        check(abs(d - total) < 0.3, f'完成版の長さ {d:.1f}秒が設計図と合う')
        newest = max(os.path.getmtime(os.path.join(ROOT, 'specs', f'{ep}.json')), *[os.path.getmtime(os.path.join(pub, s)) for s in srcs if os.path.exists(os.path.join(pub, s))])
        check(os.path.getmtime(out) >= newest, '完成版が設計図・素材より新しい（直したあとに書き出し直した）')
    else:
        check(False, f'完成版 out/{ep}_kansei.mp4 がない（書き出し→音量をそろえる）')

    for lv, msg in results:
        print(f'[{lv}] {msg}')
    ng = sum(1 for lv, _ in results if lv == 'NG')
    print(f'\nNG {ng}件／注意 {sum(1 for lv, _ in results if lv == "注意")}件')
    sys.exit(1 if ng else 0)


if __name__ == '__main__':
    main()

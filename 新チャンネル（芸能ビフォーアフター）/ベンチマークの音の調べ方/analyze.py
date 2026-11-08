#!/usr/bin/env python3
"""probe.js で記録した「音の特徴」から、ベンチマークの声と効果音を割り出す。

使い方：python3 analyze.py <動画ID>_oto.json [字幕.vtt]
出すもの：
  - 声：話している区間ごとの声の高さ。高さで分けて、声が何種類あるか・どの区間がどの声か
  - 効果音：声とは別に鳴っている短い音（いつ・長さ・高い音か低い音か・音の形）
  - BGM：声がないところにも音がずっと鳴っているか
字幕（.vtt）を渡すと、声の区間を字幕の文と結びつけて表示する
"""
import json
import re
import statistics
import sys


def load_vtt(path):
    s = open(path, encoding='utf-8').read()
    out = []
    for a, b, txt in re.findall(r'(\d\d:\d\d:\d\d\.\d+) --> (\d\d:\d\d:\d\d\.\d+)[^\n]*\n(.*?)(?:\n\n|\Z)', s, re.S):
        def sec(x):
            h, m, r = x.split(':')
            return int(h) * 3600 + int(m) * 60 + float(r)
        t = re.sub(r'<[^>]+>', '', txt).strip().split('\n')[-1]
        if t and (not out or out[-1][2] != t):
            out.append((sec(a), sec(b), t))
    return out


def main():
    d = json.load(open(sys.argv[1], encoding='utf-8'))
    vtt = load_vtt(sys.argv[2]) if len(sys.argv) > 2 else []
    cols = d['cols']
    rows = [dict(zip(cols, r)) for r in d['rows']]
    if not rows:
        sys.exit('記録が空です')
    dt = statistics.median(rows[i + 1]['t'] - rows[i]['t'] for i in range(len(rows) - 1))
    rms = [r['rms'] for r in rows]
    loud = statistics.quantiles(rms, n=10)[8]
    floor = statistics.quantiles(rms, n=10)[0]

    # 1. 音が鳴っている区間（大きさで切り出し、0.12秒以内のすき間はつなぐ）
    thr = max(floor * 3, loud * 0.08)
    act, cur = [], []
    for r in rows:
        if r['rms'] > thr:
            cur.append(r)
        elif cur:
            act.append(cur)
            cur = []
    if cur:
        act.append(cur)
    merged = []
    for a in act:
        if merged and a[0]['t'] - merged[-1][-1]['t'] <= 0.12:
            merged[-1].extend(a)
        else:
            merged.append(a)
    # 声の区間：0.3秒以上で、声の高さが取れるコマが2割以上
    segs, others = [], []
    for a in merged:
        dur = a[-1]['t'] - a[0]['t'] + dt
        voiced_ratio = sum(1 for x in a if x['pitch']) / len(a)
        (segs if dur >= 0.3 and voiced_ratio >= 0.2 else others).append(a)
    info = [(s[0]['t'], s[-1]['t'], statistics.median([x['pitch'] for x in s if x['pitch']] or [0])) for s in segs]

    # 声の高さで2つ（か3つ）に分ける：いちばん大きい隙間で切る
    ps = sorted(p for _, _, p in info)
    groups = 1
    cuts = []
    if len(ps) >= 4:
        gaps = sorted(((ps[i + 1] / ps[i], i) for i in range(len(ps) - 1)), reverse=True)
        for ratio, i in gaps[:2]:
            if ratio >= 1.18:  # 約3半音以上の差を「別の声」とみなす
                cuts.append((ps[i] + ps[i + 1]) / 2)
        cuts.sort()
        groups = len(cuts) + 1

    def voice_of(p):
        return sum(1 for c in cuts if p > c)

    print(f'# {d["id"]}（{d["duration"]:.1f}秒、{len(rows)}コマ）\n')
    print(f'## 声：{groups}種類（声の高さの切れ目：{", ".join(str(round(c)) + "Hz" for c in cuts) or "なし"}）\n')
    for v in range(groups):
        mine = [x for x in info if voice_of(x[2]) == v]
        if mine:
            print(f'- 声{v + 1}：高さの中央 {round(statistics.median(p for *_, p in mine))}Hz、{len(mine)}区間、合計 {sum(b - a for a, b, _ in mine):.1f}秒')
    print('\n| 始まり | 終わり | 高さ | 声 | 字幕 |\n|---|---|---|---|---|')
    for a, b, p in info:
        cap = next((t for s, e, t in vtt if s - 0.4 <= a <= e), '')
        print(f'| {a:.2f} | {b:.2f} | {round(p)}Hz | 声{voice_of(p) + 1} | {cap} |')

    # 2. 効果音：音が急に立ち上がるところ（出だし）を全部拾い、声の出だしと見分ける
    #   - 出だし：帯ごとの強さの増え方の合計が大きく、音も大きいコマ
    #   - 声の出だし：すぐあとに声の高さが続き、300Hz〜1kHz の帯がいちばん強い
    #   - 効果音：最初のコマで高い帯（1k〜6kHz）か低い帯（〜300Hz）がとび出している、または声の高さが続かない
    bands = ['b50_300', 'b300_1k', 'b1k_3k', 'b3k_6k', 'b6k_12k']
    onsets = []
    for i in range(1, len(rows)):
        r, p = rows[i], rows[i - 1]
        flux = sum(max(0.0, r[b] - p[b]) for b in bands)
        if flux > 22 and r['rms'] > thr and r['rms'] > p['rms'] * 1.8:
            if not onsets or r['t'] - onsets[-1] > 0.12:
                onsets.append(r['t'])
    idx = {round(r['t'], 3): k for k, r in enumerate(rows)}
    print('\n## 音の出だし（効果音の候補）\n')
    print('| 時刻 | 見分け | 強い帯 | 音の重心 | 鳴っている長さ | 見立て |\n|---|---|---|---|---|---|')
    n_se = 0
    for t in onsets:
        k = idx[round(t, 3)]
        r = rows[k]
        nxt = rows[k:k + 5]
        voiced_after = sum(1 for x in nxt if x['pitch']) >= 3
        first = {b: r[b] for b in bands}
        top = max(first, key=first.get)
        prev_voiced = any(x['pitch'] for x in rows[max(0, k - 6):k])
        speech_like = voiced_after and (top == 'b300_1k' or prev_voiced) and r['centroid'] < 1800
        # 長さ：大きさが出だしの3割より上の間
        j = k
        while j + 1 < len(rows) and rows[j + 1]['rms'] > r['rms'] * 0.3 and rows[j + 1]['t'] - t < 2.0:
            j += 1
        dur = rows[j]['t'] - t + dt
        if speech_like:
            kind, g = '声の出だし', ''
        else:
            kind = '効果音らしい' + ('（声と重なる）' if voiced_after else '')
            if top == 'b50_300':
                g = 'ドン系（低い）'
            elif r['centroid'] > 2500 and dur > 0.5:
                g = 'キラーン系（高く長い）'
            elif dur <= 0.35:
                g = 'ポン・ピコン系（短い）'
            else:
                g = 'ジャーン系（長い）'
            n_se += 1
        print(f'| {t:.2f} | {kind} | {top} | {r["centroid"]}Hz | {dur:.2f}秒 | {g} |')
    print(f'\n出だし {len(onsets)}個、うち効果音らしいもの {n_se}個')

    # 3. BGM：声がないコマの音の大きさ
    voiced = set(round(x['t'], 3) for s_ in segs for x in s_)
    quiet = [r['rms'] for r in rows if round(r['t'], 3) not in voiced]
    q = statistics.median(quiet) if quiet else 0
    print(f'\n## BGM\n声がないところの音の大きさ（中央）：{q:.4f}（いちばん小さいところ {floor:.4f}、声の大きいところ {loud:.4f}）')
    print('→ BGMあり' if q > loud * 0.05 else '→ BGMなし、か、とても小さい')


if __name__ == '__main__':
    main()

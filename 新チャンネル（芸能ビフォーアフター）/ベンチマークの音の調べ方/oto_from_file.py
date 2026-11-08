#!/usr/bin/env python3
"""手元の動画・音声ファイルから、probe.js と同じ形の「音の特徴」を作る（分析の確かめ用・自分の動画の比較用）。
使い方：python3 oto_from_file.py <動画か音声> <出力.json>
"""
import json, subprocess, sys
import numpy as np
src, out = sys.argv[1], sys.argv[2]
sr = 48000
pcm = subprocess.run(['ffmpeg', '-v', 'error', '-i', src, '-ac', '1', '-ar', str(sr), '-f', 'f32le', '-'], capture_output=True).stdout
x = np.frombuffer(pcm, dtype=np.float32)
N, hop = 4096, int(sr * 0.03)
bands = [(50, 300), (300, 1000), (1000, 3000), (3000, 6000), (6000, 12000)]
win = np.hanning(N)
rows = []
for s in range(0, len(x) - N, hop):
    td = x[s:s + N]
    rms = float(np.sqrt(np.mean(td ** 2)))
    sp = np.abs(np.fft.rfft(td * win)) ** 2 + 1e-12
    f = np.fft.rfftfreq(N, 1 / sr)
    be = [round(10 * np.log10(sp[(f >= a) & (f < b)].sum()), 1) for a, b in bands]
    cen = int((f * np.sqrt(sp)).sum() / np.sqrt(sp).sum())
    lo, hi = int(sr / 600), int(sr / 70)
    ac = np.correlate(td[::2], td[::2], 'full')[len(td[::2]) - 1:]
    e = ac[0]
    pitch = 0
    if e > 0:
        L = lo // 2 + int(np.argmax(ac[lo // 2:hi // 2]))
        if ac[L] / e > 0.3:
            pitch = int(sr / (L * 2))
    rows.append([round((s + N / 2) / sr, 3), round(rms, 4), cen, pitch, *be])
json.dump({'id': src.split('/')[-1], 'url': src, 'duration': len(x) / sr, 'sampleRate': sr,
           'cols': ['t', 'rms', 'centroid', 'pitch', 'b50_300', 'b300_1k', 'b1k_3k', 'b3k_6k', 'b6k_12k'], 'rows': rows},
          open(out, 'w'))
print('ok', len(rows))

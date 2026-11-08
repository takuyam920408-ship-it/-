#!/usr/bin/env python3
"""公開の瞬間の効果音を、数式から作る（自作なので権利の心配がない）。
使い方：python3 scripts/se.py → public/se/ に次を作る
  kokai_kira.wav（公開：明るい「キラーン」）／kokai_jan.wav（公開：驚きの「ジャン」）
  pon.wav（テロップが出るたびの「ポン」）／don.wav（冒頭の「ドン」）／shu.wav（カットの切り替えの「シュッ」。使うかは spec で選ぶ）
"""
import os
import wave
import numpy as np

SR = 44100
root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
out = os.path.join(root, 'public', 'se')
os.makedirs(out, exist_ok=True)


def save(name, x):
    x = x / (np.max(np.abs(x)) + 1e-9) * 0.7
    pcm = (x * 32767).astype(np.int16)
    with wave.open(os.path.join(out, name), 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())
    print('書き出し', name, round(len(x) / SR, 2), '秒')


def bell(f, dur, decay):
    t = np.arange(int(SR * dur)) / SR
    tone = sum(a * np.sin(2 * np.pi * f * m * t) for m, a in [(1, 1.0), (2.0, 0.45), (3.01, 0.25), (4.2, 0.12)])
    return tone * np.exp(-t * decay)


# キラーン：上がっていく鈴の音を4つ重ねる
dur = 1.1
x = np.zeros(int(SR * dur))
for k, f in enumerate([1318.5, 1760.0, 2217.5, 2637.0]):
    s = int(SR * 0.055 * k)
    b = bell(f, dur, 5.5)[: len(x) - s]
    x[s:s + len(b)] += b * (0.9 - 0.12 * k)
x *= np.minimum(1, np.arange(len(x)) / (SR * 0.004))  # 頭のプチ音を消す
save('kokai_kira.wav', x)

# ジャン：明るい和音を短く
dur = 0.9
t = np.arange(int(SR * dur)) / SR
chord = sum(np.sin(2 * np.pi * f * t) + 0.3 * np.sin(2 * np.pi * 2 * f * t) for f in [523.25, 659.25, 783.99, 1046.5])
env = np.minimum(1, t / 0.008) * np.exp(-t * 4.0)
save('kokai_jan.wav', chord * env)


# ポン：テロップが出るときの短い音（高めの音が少し下がる）
dur = 0.16
t = np.arange(int(SR * dur)) / SR
f = 1250 * np.exp(-t * 6)
x = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 28) * np.minimum(1, t / 0.002)
save('pon.wav', x)

# ドン：冒頭の画面が出るときの低い音
dur = 0.7
t = np.arange(int(SR * dur)) / SR
f = 140 * np.exp(-t * 3) + 45
body = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 5.5)
rng = np.random.default_rng(7)
click = rng.standard_normal(len(t)) * np.exp(-t * 60) * 0.35
save('don.wav', (body + click) * np.minimum(1, t / 0.003))

# シュッ：風を切る音（雑音の高さを上げていく）
dur = 0.32
t = np.arange(int(SR * dur)) / SR
rng = np.random.default_rng(3)
noise = rng.standard_normal(len(t))
# 簡単なフィルター：差分をとって高い音を強め、だんだん強くしてから消す
hi = np.diff(noise, prepend=0)
env = np.sin(np.pi * t / dur) ** 2
save('shu.wav', (0.6 * hi + 0.4 * noise) * env * 0.6)

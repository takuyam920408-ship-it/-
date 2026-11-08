#!/usr/bin/env python3
"""読み上げの声（VOICEVOX の青山龍星）を作り、カットの秒数と下テロップを出す時間を声に合わせる。

使い方：python3 scripts/koe.py <id> [--speed 1.25]
  - specs/<id>.json の各カットのテロップを、上→下の順に読んだ声を作る
    （冒頭はタイトル枠の文）。public/<id>/voice/cutNN.wav に置き、spec の "voice" に書く
  - 下テロップの "at" を、その文を読み始める秒にする。カットの "dur" は、声の長さ＋0.35秒にする
  - 読み間違える言葉は、spec の一番上の "yomi"（画面の文字 → 読み）で直す。例：{"20歳": "はたち"}
  - 画面に出さない記号（ｗ、“”、改行）は読まない
  - spec は書き換える（元の spec は specs/<id>.json.bak に残す）

必要なもの（VOICEVOX CORE。環境変数 VOICEVOX_DIR に、次の3つを置いたフォルダを指定する）
  ort/…/libvoicevox_onnxruntime.so（VOICEVOX ONNX Runtime）、dict/（Open JTalk の辞書）、15.vvm（青山龍星が入った音声モデル）
  Python の voicevox_core（0.16以降）
クレジット：概要欄に「VOICEVOX:青山龍星」（個人の利用。企業が携わる形なら、ななはぴへ事前確認）
"""
import glob
import io
import json
import os
import re
import shutil
import sys
import wave

AOYAMA_NORMAL = 13  # 青山龍星（ノーマル）
LEAD = 0.15  # カットの頭の間（秒）
GAP = 0.22  # 文と文の間（秒）
TAIL = 0.35  # 声のあとの余白（秒）。README の「音声の長さ＋0.3秒以上」


def load_synth(vdir):
    from voicevox_core.blocking import Onnxruntime, OpenJtalk, Synthesizer, VoiceModelFile

    lib = glob.glob(os.path.join(vdir, 'ort', '**', 'libvoicevox_onnxruntime.so'), recursive=True)[0]
    syn = Synthesizer(Onnxruntime.load_once(filename=lib), OpenJtalk(os.path.join(vdir, 'dict')))
    vvm = glob.glob(os.path.join(vdir, '**', '15.vvm'), recursive=True)[0]
    with VoiceModelFile.open(vvm) as m:
        syn.load_voice_model(m)
    return syn


def read_wav(b):
    with wave.open(io.BytesIO(b)) as w:
        return w.getframerate(), w.getnchannels(), w.getsampwidth(), w.readframes(w.getnframes())


def main():
    args = sys.argv[1:]
    if not args:
        sys.exit(__doc__)
    ep = args[0]
    speed = float(args[args.index('--speed') + 1]) if '--speed' in args else 1.25
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    spec_path = os.path.join(root, 'specs', f'{ep}.json')
    spec = json.load(open(spec_path, encoding='utf-8'))
    yomi = spec.get('yomi', {})
    vdir = os.environ.get('VOICEVOX_DIR')
    if not vdir:
        sys.exit('VOICEVOX_DIR を指定してください')
    syn = load_synth(vdir)
    out_dir = os.path.join(root, 'public', ep, 'voice')
    os.makedirs(out_dir, exist_ok=True)

    def say(text):
        t = re.sub(r'[ｗw“”\n]', '', text)
        for k, v in yomi.items():
            t = t.replace(k, v)
        q = syn.create_audio_query(t, AOYAMA_NORMAL)
        q.speed_scale = speed
        q.pre_phoneme_length = 0.0
        q.post_phoneme_length = 0.0
        rate, ch, sw, frames = read_wav(syn.synthesis(q, AOYAMA_NORMAL))
        return rate, ch, sw, frames, t

    total = 0.0
    for i, cut in enumerate(spec['cuts'], 1):
        texts = [cut['title']] if cut['type'] == 'title' else [cut['top']['text']] + [b['text'] for b in cut['bottom']]
        pcm = b''
        t = LEAD
        starts = []
        rate = ch = sw = None
        for k, text in enumerate(texts):
            rate, ch, sw, frames, spoken = say(text)
            silence = lambda sec: b'\x00' * (int(rate * sec) * ch * sw)
            if k == 0:
                pcm += silence(LEAD)
            else:
                pcm += silence(GAP)
                t += GAP
            starts.append(round(t, 2))
            pcm += frames
            t += len(frames) / (rate * ch * sw)
            print(f'カット{i}：{spoken}（{len(frames) / (rate * ch * sw):.2f}秒）')
        f = os.path.join(out_dir, f'cut{i:02d}.wav')
        with wave.open(f, 'wb') as w:
            w.setnchannels(ch)
            w.setsampwidth(sw)
            w.setframerate(rate)
            w.writeframes(pcm)
        cut['voice'] = f'{ep}/voice/cut{i:02d}.wav'
        if cut['type'] != 'title':
            for b, s in zip(cut['bottom'], starts[1:]):
                b['at'] = s
        cut['dur'] = round(t + TAIL, 2)
        total += cut['dur']
    shutil.copy(spec_path, spec_path + '.bak')
    json.dump(spec, open(spec_path, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    open(spec_path, 'a').write('\n')
    print(f'合計 {total:.1f}秒（話す速さ {speed}）')
    if not 25 <= total <= 33:
        print('※合計が25〜33秒の外。--speed を変えるか、テロップを削る')


if __name__ == '__main__':
    main()

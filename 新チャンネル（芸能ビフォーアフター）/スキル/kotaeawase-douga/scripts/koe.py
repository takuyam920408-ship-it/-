#!/usr/bin/env python3
"""読み上げの声（VOICEVOX の青山龍星）を作り、カットの秒数と下テロップを出す時間を声に合わせる。

使い方：python3 scripts/koe.py <id> [--speed 1.25]
  - specs/<id>.json の各カットのテロップを、上→下の順に読んだ声を作る
    （冒頭はタイトル枠の文）。public/<id>/voice/cutNN.wav に置き、spec の "voice" に書く
  - 声は2種類（ベンチマークに合わせた。2026-11-08）：冒頭の文と上テロップ（説明）は "setsumei"、下テロップ（ツッコミ）は "tsukkomi"
    spec の一番上の "voices" で声の番号を選ぶ。例：{"setsumei": 13, "tsukkomi": 8}（13＝青山龍星、8＝春日部つむぎ）。書かなければ setsumei 13・tsukkomi 8
  - 下テロップの "at" を、その文を読み始める秒にする。カットの "dur" は、声の長さ＋0.35秒にする
  - 読み間違える言葉は、spec の一番上の "yomi"（画面の文字 → 読み）で直す。例：{"20歳": "はたち"}
  - 画面に出さない記号（ｗ、“”、改行）は読まない
  - spec は書き換える（元の spec は specs/<id>.json.bak に残す）

必要なもの（VOICEVOX CORE。環境変数 VOICEVOX_DIR に、次の3つを置いたフォルダを指定する）
  ort/…/libvoicevox_onnxruntime.so（VOICEVOX ONNX Runtime）、dict/（Open JTalk の辞書）、15.vvm（青山龍星が入った音声モデル）
  Python の voicevox_core（0.16以降）
クレジット：概要欄に、使った声を全部書く（例：「VOICEVOX:青山龍星」「VOICEVOX:春日部つむぎ」）。青山龍星は、企業が携わる形なら、ななはぴへ事前確認
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
DEFAULT_VOICES = {'setsumei': 13, 'tsukkomi': 8}  # 説明＝青山龍星、ツッコミ＝春日部つむぎ
LEAD = 0.15  # カットの頭の間（秒）
GAP = 0.22  # 文と文の間（秒）
TAIL = 0.35  # 声のあとの余白（秒）。README の「音声の長さ＋0.3秒以上」


def load_synth(vdir, style_ids):
    """必要な声の番号が入った音声モデル（.vvm）だけを読み込む"""
    from voicevox_core.blocking import Onnxruntime, OpenJtalk, Synthesizer, VoiceModelFile

    lib = glob.glob(os.path.join(vdir, 'ort', '**', 'libvoicevox_onnxruntime.so'), recursive=True)[0]
    syn = Synthesizer(Onnxruntime.load_once(filename=lib), OpenJtalk(os.path.join(vdir, 'dict')))
    need = set(style_ids)
    names = {}
    for vvm in sorted(glob.glob(os.path.join(vdir, '**', '*.vvm'), recursive=True)):
        if not need:
            break
        with VoiceModelFile.open(vvm) as m:
            ids = {st.id: f'{c.name}（{st.name}）' for c in m.metas for st in c.styles}
            if need & ids.keys():
                syn.load_voice_model(m)
                for i in need & ids.keys():
                    names[i] = ids[i]
                need -= ids.keys()
    if need:
        sys.exit(f'声の番号 {sorted(need)} が入った .vvm が {vdir} にありません（setup_voicevox.sh の VVMS で足す）')
    return syn, names


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
    voices = {**DEFAULT_VOICES, **spec.get('voices', {})}
    syn, names = load_synth(vdir, voices.values())
    print('声：説明＝' + names[voices['setsumei']] + '、ツッコミ＝' + names[voices['tsukkomi']])
    spec['voiceCredits'] = sorted({'VOICEVOX:' + names[v].split('（')[0] for v in voices.values()})
    out_dir = os.path.join(root, 'public', ep, 'voice')
    os.makedirs(out_dir, exist_ok=True)

    def say(text, style):
        t = re.sub(r'[ｗw“”\n]', '', text)
        for k, v in yomi.items():
            t = t.replace(k, v)
        q = syn.create_audio_query(t, style)
        q.speed_scale = speed
        q.pre_phoneme_length = 0.0
        q.post_phoneme_length = 0.0
        rate, ch, sw, frames = read_wav(syn.synthesis(q, style))
        return rate, ch, sw, frames, t

    total = 0.0
    for i, cut in enumerate(spec['cuts'], 1):
        texts = [cut['title']] if cut['type'] == 'title' else [cut['top']['text']] + [b['text'] for b in cut['bottom']]
        pcm = b''
        t = LEAD
        starts = []
        rate = ch = sw = None
        for k, text in enumerate(texts):
            style = voices['tsukkomi'] if (cut['type'] != 'title' and k >= 1) else voices['setsumei']
            rate, ch, sw, frames, spoken = say(text, style)
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

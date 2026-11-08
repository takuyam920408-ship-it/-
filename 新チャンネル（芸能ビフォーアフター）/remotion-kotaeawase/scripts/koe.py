#!/usr/bin/env python3
"""読み上げの声（VOICEVOX の青山龍星）を作り、カットの秒数と下テロップを出す時間を声に合わせる。

使い方：python3 scripts/koe.py <id> [--speed 1.25]
  - specs/<id>.json の各カットのテロップを、上→下の順に読んだ声を作る
    （冒頭はタイトル枠の文）。public/<id>/voice/cutNN.wav に置き、spec の "voice" に書く
  - 声は2種類で、テロップ1つごとに交互にしゃべる（ベンチマーク①1位の動画を測って合わせた。2026-11-08）
    冒頭の文と最初のテロップは "a"、そのあとは b, a, b… と交互。spec の一番上の "voices" で声の番号を選ぶ
    例：{"a": 13, "b": 8}（13＝青山龍星、8＝春日部つむぎ）。書かなければ a 13・b 8
    "voiceMode": "jouge" にすると、上テロップ＝a、下テロップ＝b の分け方になる
  - 効果音もテロップごとに書く（ベンチマークと同じ鳴らし方）：冒頭＝T、公開の上テロップと最後のカットの上テロップ＝D、
    声aのテロップ＝なし、声bのテロップ＝C（小パンチ）・B（パフ）・C・C・B…の順。T＝和太鼓でドドン、D＝きらーん1
    音のファイルは scripts/se_lab.py で効果音ラボから取る（public/se/bm/。リポジトリには入れない）
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
import subprocess
import sys
import wave

AOYAMA_NORMAL = 13  # 青山龍星（ノーマル）
# 声：ベンチマーク（こっそり速報1位）を測って合わせた（2026-11-08）。高さ・抑揚（半音のばらつき）・速さ（1秒の字数）をそろえ、
# 音色（声の響き）がいちばん近い声を選んだ。a＝高い声（ベンチマーク 275Hz・抑揚0.86・1秒8.6音）、b＝低い声（103Hz・0.78・1秒8.8音）
DEFAULT_VOICES = {
    'a': {'id': 16, 'pitch': 0.101, 'intonation': 0.28, 'speed': 1.44},   # 九州そら（ノーマル）
    'b': {'id': 12, 'pitch': -0.5, 'intonation': 0.24, 'speed': 1.12},    # 白上虎太郎（ふつう）
}
LOWPASS = 5800  # ベンチマークの声は5.8kHzより上がない（AquesTalk）。同じこもり方にする
LEAD = 0.03  # カットの頭の間（秒）。ベンチマークはテロップ・効果音・声が同時に出る
GAP = 0.27  # 文と文の間（秒）。ベンチマークは0.26〜0.29秒
TAIL = 0.26  # 声のあとの余白（秒）。ベンチマークは次のカットまで0.26秒
END_HOLD = 1.1  # 最後の声のあとの余白（秒）。ベンチマークは1.14秒
# 効果音（ベンチマーク①1位の動画で、テロップごとに鳴っていた5種類）。ファイルは public/se/bm/ に置く
SE_SET = {'T': 'se/bm/T.mp3', 'A': None, 'B': 'se/bm/B.mp3', 'C': 'se/bm/C.mp3', 'D': 'se/bm/D.mp3'}  # A（声aのテロップ）は鳴らさない
SE_VOL = {'T': 0.23, 'A': 0.0, 'B': 0.22, 'C': 0.23, 'D': 0.22}  # 声との大きさの差を、ベンチマークに合わせた（T -5.7dB／C -15.3dB／B -20.4dB／D -13.1dB）
B_CYCLE = ['C', 'B', 'C', 'C', 'B']


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
    v_in = spec.get('voices', {})
    voices = {}
    for key, old in (('a', 'setsumei'), ('b', 'tsukkomi')):
        v = v_in.get(key, v_in.get(old, DEFAULT_VOICES[key]))
        voices[key] = v if isinstance(v, dict) else {'id': v}  # 番号だけなら、高さ・抑揚・速さはそのまま
    lowpass = spec.get('voiceLowpass', LOWPASS)
    mode = spec.get('voiceMode', 'kougo')
    se_set = {**SE_SET, **spec.get('seSet', {})}
    use_se = spec.get('seMode', 'benchmark') == 'benchmark' and all(os.path.exists(os.path.join(root, 'public', p)) for p in se_set.values() if p)
    if not use_se:
        print('※ベンチマークの効果音（public/se/bm/）がないので、テロップごとの効果音は書かない（scripts/se_lab.py で用意する）')
    line_no = 0  # 本文のテロップの通し番号（交互の声と効果音を決める）
    b_count = 0
    syn, names = load_synth(vdir, [v['id'] for v in voices.values()])
    print('声：a＝' + names[voices['a']['id']] + '、b＝' + names[voices['b']['id']] + '（' + ('テロップごとに交互' if mode == 'kougo' else '上＝a、下＝b') + '）')
    spec['voiceCredits'] = sorted({'VOICEVOX:' + names[v['id']].split('（')[0] for v in voices.values()})
    n_cuts = len(spec['cuts'])
    out_dir = os.path.join(root, 'public', ep, 'voice')
    os.makedirs(out_dir, exist_ok=True)

    def say(text, voice):
        style = voice['id']
        t = re.sub(r'[ｗw“”\n]', '', text)
        for k, v in yomi.items():
            t = t.replace(k, v)
        q = syn.create_audio_query(t, style)
        q.speed_scale = voice.get('speed', speed)
        q.pitch_scale = voice.get('pitch', 0.0)
        q.intonation_scale = voice.get('intonation', 1.0)
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
        telops = [None] if cut['type'] == 'title' else [cut['top']] + list(cut['bottom'])
        for k, text in enumerate(texts):
            if cut['type'] == 'title':
                who = 'a'
            elif mode == 'kougo':
                who = 'a' if line_no % 2 == 0 else 'b'
                line_no += 1
            else:
                who = 'a' if k == 0 else 'b'
            style = voices[who]  # 声の設定（番号・高さ・抑揚・速さ）
            if use_se and telops[k] is not None:
                if k == 0 and (cut['type'] == 'reveal' or i == n_cuts):
                    kind = 'D'
                elif who == 'a':
                    kind = 'A'
                else:
                    kind = B_CYCLE[b_count % len(B_CYCLE)]
                    b_count += 1
                telops[k]['se'] = se_set[kind]
                if se_set[kind]:
                    telops[k]['seVolume'] = SE_VOL[kind]
                else:
                    telops[k].pop('seVolume', None)
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
        if lowpass:
            tmp = f + '.lp.wav'
            subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', f, '-af', ','.join([f'lowpass=f={lowpass}'] * 4), tmp], check=True)
            os.replace(tmp, f)
        cut['voice'] = f'{ep}/voice/cut{i:02d}.wav'
        if cut['type'] != 'title':
            for b, s in zip(cut['bottom'], starts[1:]):
                b['at'] = s
        cut['dur'] = round(t + (END_HOLD if i == n_cuts else TAIL), 2)
        if use_se:
            cut.pop('se', None)  # 公開の効果音は上テロップの D で鳴らす
        total += cut['dur']
    if use_se:
        spec.setdefault('sfx', {})['title'] = se_set['T']
        spec['sfx']['titleVolume'] = SE_VOL['T']
        spec['sfx']['telop'] = None
    shutil.copy(spec_path, spec_path + '.bak')
    json.dump(spec, open(spec_path, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    open(spec_path, 'a').write('\n')
    print(f'合計 {total:.1f}秒（話す速さ {speed}）')
    if not 25 <= total <= 33:
        print('※合計が25〜33秒の外。--speed を変えるか、テロップを削る')


if __name__ == '__main__':
    main()

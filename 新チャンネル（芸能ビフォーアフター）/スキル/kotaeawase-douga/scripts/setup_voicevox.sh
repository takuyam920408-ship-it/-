#!/bin/bash
# VOICEVOX CORE（四国めたん・青山龍星）を組み立てる。クラウドのセッションで声を作るときに1回まわす。
# 使い方：bash scripts/setup_voicevox.sh <置き場所>   例：bash scripts/setup_voicevox.sh ~/voicevox
# できあがり：<置き場所>/venv（voicevox_core 入りの Python）、ort/、dict/、vvms/（0.vvm＝四国めたん、15.vvm＝青山龍星）
# 声を作る：VOICEVOX_DIR=<置き場所> <置き場所>/venv/bin/python scripts/koe.py <id>
#
# 公式のダウンロードツールは GitHub の API を使うため、クラウドでは動かない。代わりに直接取る：
#   - VOICEVOX CORE の wheel と VOICEVOX ONNX Runtime：GitHub のリリース
#   - 音声モデル（0.vvm・15.vvm）：voicevox_vvm リポジトリ（そのファイルだけ取り出す）
#   - Open JTalk の辞書：PyPI の pyopenjtalk-plus に入っているもの
# GitHub のリリースのダウンロードは、混んでいると 504 になることがある（2026-11-08 に何度か出た）。時間をおいてもう一度まわす
# 利用規約：音声モデルは voicevox_vvm の TERMS。概要欄に「VOICEVOX:四国めたん、VOICEVOX:青山龍星」と書けば、どちらも商用（収益化）可
# （青山龍星は、企業が携わる形なら、ななはぴへ事前確認）
set -euo pipefail
DIR=${1:?置き場所を指定してください}
CORE=0.17.1
ORT=1.23.2
mkdir -p "$DIR" && cd "$DIR"

if [ ! -x venv/bin/python ]; then
  curl -sSfL --retry 6 --retry-all-errors --retry-delay 4 -o voicevox_core.whl "https://github.com/VOICEVOX/voicevox_core/releases/download/$CORE/voicevox_core-$CORE-cp310-abi3-manylinux_2_34_x86_64.whl"
  mv voicevox_core.whl "voicevox_core-$CORE-cp310-abi3-manylinux_2_34_x86_64.whl"
  python3 -m venv venv
  venv/bin/pip install -q "voicevox_core-$CORE-cp310-abi3-manylinux_2_34_x86_64.whl"
fi

if [ ! -d ort ]; then
  curl -sSfL --retry 6 --retry-all-errors --retry-delay 4 -o ort.tgz "https://github.com/VOICEVOX/onnxruntime-builder/releases/download/voicevox_onnxruntime-$ORT/voicevox_onnxruntime-linux-x64-$ORT.tgz"
  mkdir -p ort && tar xzf ort.tgz -C ort && rm ort.tgz
fi

# 使う声の音声モデル：15.vvm＝青山龍星（声a）、0.vvm＝四国めたん（声b）。ほかの声を使うときは VVMS で足す（どの声がどの .vvm かは voicevox_vvm の README）
VVMS=${VVMS:-"0 15"}
mkdir -p vvms
missing=""; for v in $VVMS; do [ -f "vvms/$v.vvm" ] || missing="$missing /vvms/$v.vvm"; done
if [ -n "$missing" ]; then
  rm -rf vvm_tmp
  GIT_LFS_SKIP_SMUDGE=1 git clone -q --depth 1 --filter=blob:none --sparse https://github.com/VOICEVOX/voicevox_vvm vvm_tmp
  git -C vvm_tmp sparse-checkout set --no-cone $missing /TERMS.txt /README.md
  for v in $VVMS; do [ -f "vvm_tmp/vvms/$v.vvm" ] && cp "vvm_tmp/vvms/$v.vvm" "vvms/$v.vvm"; done
  cp vvm_tmp/TERMS.txt vvm_TERMS.txt
  cp vvm_tmp/README.md vvm_README.md
  rm -rf vvm_tmp
fi

if [ ! -f dict/sys.dic ]; then
  rm -rf pyoj && mkdir -p pyoj dict
  venv/bin/pip download -q --no-deps -d pyoj pyopenjtalk-plus
  venv/bin/python - <<'PY'
import glob, zipfile
z = zipfile.ZipFile(glob.glob('pyoj/*.whl')[0])
for n in z.namelist():
    if n.startswith('pyopenjtalk/dictionary/') and not n.endswith('/'):
        open('dict/' + n.split('/')[-1], 'wb').write(z.read(n))
PY
  rm -rf pyoj
fi

venv/bin/python - <<PY
from voicevox_core.blocking import Onnxruntime, OpenJtalk, Synthesizer, VoiceModelFile
import glob
syn = Synthesizer(Onnxruntime.load_once(filename=glob.glob('$DIR/ort/**/libvoicevox_onnxruntime.so', recursive=True)[0]), OpenJtalk('$DIR/dict'))
for f in glob.glob('$DIR/vvms/*.vvm'):
    with VoiceModelFile.open(f) as m:
        syn.load_voice_model(m)
print('OK：四国めたん', len(syn.tts('答え合わせ速報', 2)), 'バイト／青山龍星', len(syn.tts('答え合わせ速報', 13)), 'バイト')
PY

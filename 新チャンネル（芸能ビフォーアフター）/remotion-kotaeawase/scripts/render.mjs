// 使い方：
//   node scripts/render.mjs <id>            … specs/<id>.json から out/<id>.mp4 を書き出す
//   node scripts/render.mjs <id> --stills   … 各カットの終わりの画を out/still/<id>_カットNN.png に書き出す（確認用）
import { bundle } from '@remotion/bundler';
import { renderMedia, renderStill, selectComposition } from '@remotion/renderer';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const id = process.argv[2] || 'mihon';
const stills = process.argv.includes('--stills');
const spec = JSON.parse(fs.readFileSync(path.join(root, 'specs', `${id}.json`), 'utf8'));
// BGMの曲（YouTubeのオーディオライブラリから落とす。リポジトリには入れない）がこのPCにないときは、BGMなしで書き出す
if (spec.bgm && !fs.existsSync(path.join(root, 'public', spec.bgm))) {
  console.warn(`※BGMの ${spec.bgm} がないので、BGMなしで書き出す（本番はMacで曲を置いてから書き出す）`);
  delete spec.bgm;
}

// クラウドの環境では入っているヘッドレスのChromeを使う。Macでは Remotion が自分で用意する
const candidates = [
  process.env.REMOTION_BROWSER,
  '/opt/pw-browsers/chromium_headless_shell-1243/chrome-headless-shell-linux64/chrome-headless-shell',
].filter(Boolean);
const browserExecutable = candidates.find((p) => fs.existsSync(p)) ?? null;

const serveUrl = await bundle({ entryPoint: path.join(root, 'src', 'index.ts'), publicDir: path.join(root, 'public') });
const inputProps = { spec };
const composition = await selectComposition({ serveUrl, id: 'kotaeawase', inputProps, browserExecutable });
const fps = composition.fps;
const total = composition.durationInFrames;
console.log(`${id}：${spec.cuts.length}カット、合計${(total / fps).toFixed(1)}秒`);

if (stills) {
  const dir = path.join(root, 'out', 'still');
  fs.mkdirSync(dir, { recursive: true });
  let from = 0;
  for (const [i, cut] of spec.cuts.entries()) {
    const dur = Math.round(cut.dur * fps);
    const frame = from + dur - Math.round(0.3 * fps);
    const output = path.join(dir, `${id}_カット${String(i + 1).padStart(2, '0')}.png`);
    await renderStill({ composition, serveUrl, output, frame, inputProps, browserExecutable });
    console.log('静止画：', output);
    from += dur;
  }
} else {
  const outputLocation = path.join(root, 'out', `${id}.mp4`);
  fs.mkdirSync(path.dirname(outputLocation), { recursive: true });
  await renderMedia({ composition, serveUrl, codec: 'h264', crf: 20, outputLocation, inputProps, browserExecutable });
  console.log('書き出し：', outputLocation);
}

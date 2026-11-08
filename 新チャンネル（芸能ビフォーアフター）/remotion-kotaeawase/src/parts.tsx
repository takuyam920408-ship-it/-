import React, { useContext, useEffect, useState } from 'react';
import {
  AbsoluteFill,
  Audio,
  Img,
  Sequence,
  continueRender,
  delayRender,
  spring,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from 'remotion';
import { BG_DARK, BG_LIGHT, BG_ROTATE_DEG_PER_SEC, FONT, H, INK, TEXT_COLORS } from './theme';
import type { Photo, Telop } from './spec';

export type Rect = { x: number; y: number; w: number; h: number };

// 動画全体の設定（出典ラベルを出すか、テロップの効果音）
export const ShowCredit = React.createContext(false);
export const TelopSfx = React.createContext<{ src: string | null; volume: number }>({ src: null, volume: 0.5 });

// 背景：オレンジの放射線（濃い帯と淡い帯を7.5度ずつ交互に）。動画のあいだ、カットをまたいでずっとゆっくり回す
export const Background: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const angle = ((frame / fps) * BG_ROTATE_DEG_PER_SEC) % 360;
  return (
    <AbsoluteFill
      style={{
        background: `repeating-conic-gradient(from ${angle.toFixed(3)}deg at 50% 46%, ${BG_DARK} 0deg 7.5deg, ${BG_LIGHT} 7.5deg 15deg)`,
      }}
    />
  );
};

// 画像の元の大きさを読む（読み終わるまで書き出しを待つ）
export const useImageSize = (src: string) => {
  const [size, setSize] = useState<{ w: number; h: number } | null>(null);
  const [handle] = useState(() => delayRender(`image size: ${src}`));
  useEffect(() => {
    const img = new Image();
    img.onload = () => {
      setSize({ w: img.naturalWidth, h: img.naturalHeight });
      continueRender(handle);
    };
    img.onerror = () => {
      setSize({ w: 3, h: 4 });
      continueRender(handle);
    };
    img.src = staticFile(src);
  }, [src, handle]);
  return size;
};

// 枠の中に、縦横比を保ったまま収める（はみ出さない）
export const fitContain = (size: { w: number; h: number }, box: Rect): Rect => {
  const s = Math.min(box.w / size.w, box.h / size.h);
  const w = Math.round(size.w * s);
  const h = Math.round(size.h * s);
  return { x: Math.round(box.x + (box.w - w) / 2), y: Math.round(box.y + (box.h - h) / 2), w, h };
};

// 画像のどこを切り出すか（cover のとき。focusY＝縦方向の中心の位置 0〜1、顔が上の方にあるので既定は0.3）
const sourceCrop = (size: { w: number; h: number }, rect: Rect, fit: 'contain' | 'cover', focusY: number) => {
  if (fit === 'contain') return { sx: 0, sy: 0, sw: size.w, sh: size.h };
  const s = Math.max(rect.w / size.w, rect.h / size.h);
  const sw = rect.w / s;
  const sh = rect.h / s;
  const sx = (size.w - sw) / 2;
  const sy = Math.min(Math.max(size.h * focusY - sh / 2, 0), size.h - sh);
  return { sx, sy, sw, sh };
};

// モザイク：小さく縮めてから、ぼかさずに引き伸ばす
const MosaicCanvas: React.FC<{ src: string; rect: Rect; block: number; fit: 'contain' | 'cover'; focusY: number }> = ({
  src,
  rect,
  block,
  fit,
  focusY,
}) => {
  const ref = React.useRef<HTMLCanvasElement>(null);
  const [handle] = useState(() => delayRender(`mosaic: ${src}`));
  useEffect(() => {
    const img = new Image();
    img.onload = () => {
      const c = ref.current;
      if (!c) return continueRender(handle);
      const sw = Math.max(1, Math.ceil(rect.w / block));
      const sh = Math.max(1, Math.ceil(rect.h / block));
      const small = document.createElement('canvas');
      small.width = sw;
      small.height = sh;
      const sc = small.getContext('2d')!;
      sc.imageSmoothingEnabled = true;
      const cr = sourceCrop({ w: img.naturalWidth, h: img.naturalHeight }, rect, fit, focusY);
      sc.drawImage(img, cr.sx, cr.sy, cr.sw, cr.sh, 0, 0, sw, sh);
      const g = c.getContext('2d')!;
      g.imageSmoothingEnabled = false;
      g.drawImage(small, 0, 0, sw, sh, 0, 0, sw * block, sh * block);
      continueRender(handle);
    };
    img.onerror = () => continueRender(handle);
    img.src = staticFile(src);
  }, [src, rect.w, rect.h, block, fit, focusY, handle]);
  // 冒頭画面のズームで引き伸ばされても、マスの境目がぼやけないようにする
  return <canvas ref={ref} width={rect.w} height={rect.h} style={{ display: 'block', imageRendering: 'pixelated' }} />;
};

// 写真＋出典ラベル（＋2枚比較のラベル）。mosaic を渡すとモザイクをかける
// fit：contain＝枠の中に全体を収める（本編の写真）／cover＝枠いっぱいに切り取る（冒頭画面・2枚比較）
export const PhotoBox: React.FC<{
  photo: Photo;
  box: Rect;
  mosaic?: number;
  fit?: 'contain' | 'cover';
  focusY?: number;
  onRect?: (r: Rect) => void;
}> = ({ photo, box, mosaic, fit = 'contain', focusY: focusYProp, onRect }) => {
  const focusY = photo.focusY ?? focusYProp ?? 0.3;
  const showCredit = useContext(ShowCredit);
  const size = useImageSize(photo.src);
  const rect = size ? (fit === 'cover' ? box : fitContain(size, box)) : null;
  useEffect(() => {
    if (rect && onRect) onRect(rect);
  }, [rect?.x, rect?.y, rect?.w, rect?.h]);
  if (!rect || !size) return null;
  const b = mosaic ?? 0;
  return (
    <div style={{ position: 'absolute', left: rect.x, top: rect.y, width: rect.w, height: rect.h, overflow: 'hidden' }}>
      {b > 0 ? (
        <MosaicCanvas src={photo.src} rect={rect} block={b} fit={fit} focusY={focusY} />
      ) : (
        <Img
          src={staticFile(photo.src)}
          style={{
            width: rect.w,
            height: rect.h,
            display: 'block',
            objectFit: fit,
            objectPosition: `50% ${Math.round(focusY * 100)}%`,
          }}
        />
      )}
      {photo.tag ? (
        <div
          style={{
            position: 'absolute', left: 16, top: 16, background: INK, color: '#fff',
            borderRadius: 8, padding: '6px 16px', fontFamily: FONT, fontWeight: 800, fontSize: 32,
          }}
        >
          {photo.tag}
        </div>
      ) : null}
      {photo.label && showCredit ? (
        <div
          style={{
            position: 'absolute', top: 16, ...(photo.tag ? { right: 16 } : { left: 16 }),
            background: 'rgba(20,20,20,0.6)', color: '#fff', borderRadius: 8, padding: '6px 14px',
            fontFamily: FONT, fontWeight: 800, fontSize: 28,
          }}
        >
          {photo.label}
        </div>
      ) : null}
    </div>
  );
};

// テロップの枠（白地・黒枠・角丸）。出るときに少しだけポンと大きくなる
export const TelopBox: React.FC<{ telop: Telop; startFrame: number }> = ({ telop, startFrame }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const p = spring({ frame: frame - startFrame, fps, config: { damping: 14, mass: 0.5 } });
  const sfx = useContext(TelopSfx);
  if (frame < startFrame) return null;
  const seSrc = telop.se === undefined ? sfx.src : telop.se;
  return (
    <>
    {seSrc ? (
      <Sequence from={startFrame} durationInFrames={Math.round(fps * 2.0)} layout="none">
        <Audio src={staticFile(seSrc)} volume={telop.seVolume ?? sfx.volume} />
      </Sequence>
    ) : null}
    <div
      style={{
        background: '#fff', border: `6px solid ${INK}`, borderRadius: 16, padding: '14px 34px',
        fontFamily: FONT, fontWeight: 800, fontSize: 78, lineHeight: 1.22, textAlign: 'center',
        whiteSpace: 'pre-line', color: TEXT_COLORS[telop.color ?? 'blue'],
        transform: `scale(${0.85 + 0.15 * p})`, opacity: Math.min(1, p * 1.5),
      }}
    >
      {telop.text}
    </div>
    </>
  );
};

export const TopTelop: React.FC<{ telop: Telop; y: number }> = ({ telop, y }) => {
  const { fps } = useVideoConfig();
  return (
    <div style={{ position: 'absolute', top: y, left: 0, right: 0, display: 'flex', justifyContent: 'center' }}>
      <TelopBox telop={telop} startFrame={Math.round((telop.at ?? 0) * fps)} />
    </div>
  );
};

// 下テロップ。あとから出たものを上に積む。anchorBottom＝下の端のy、anchorTop＝上の端のy
export const BottomTelops: React.FC<{ telops: Telop[]; anchorBottom?: number; anchorTop?: number }> = ({
  telops,
  anchorBottom,
  anchorTop,
}) => {
  const { fps } = useVideoConfig();
  const ordered = [...telops].sort((a, b) => (b.at ?? 2) - (a.at ?? 2));
  const pos = anchorTop !== undefined ? { top: anchorTop } : { bottom: H - (anchorBottom ?? 1552) };
  return (
    <div
      style={{
        position: 'absolute', left: 0, right: 0, ...pos,
        display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 14,
      }}
    >
      {ordered.map((t, i) => (
        <TelopBox key={i} telop={t} startFrame={Math.round((t.at ?? 2) * fps)} />
      ))}
    </div>
  );
};

export const ArrowDown: React.FC<{ cx: number; cy: number; color: string }> = ({ cx, cy, color }) => (
  <svg width={140} height={170} viewBox="0 0 140 170" style={{ position: 'absolute', left: cx - 70, top: cy - 120 }}>
    <path d="M45 6 H95 V92 H132 L70 164 L8 92 H45 Z" fill={color} stroke="#fff" strokeWidth={8} strokeLinejoin="round" />
  </svg>
);

export const ArrowRight: React.FC<{ cx: number; cy: number; color: string }> = ({ cx, cy, color }) => (
  <svg width={280} height={170} viewBox="0 0 280 170" style={{ position: 'absolute', left: cx - 160, top: cy - 85 }}>
    <path d="M8 55 H170 V10 L272 85 L170 160 V115 H8 Z" fill={color} stroke="#fff" strokeWidth={8} strokeLinejoin="round" />
  </svg>
);

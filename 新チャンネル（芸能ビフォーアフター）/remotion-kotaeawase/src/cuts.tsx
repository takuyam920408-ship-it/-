import React, { useState } from 'react';
import { FONT, MAGENTA, ARROW_RED, PHOTO, BOTTOM_EDGE, TOP_TELOP_Y } from './theme';
import { ArrowDown, ArrowRight, BottomTelops, PhotoBox, TopTelop, type Rect } from './parts';
import type { BodyCut, CompareCut, TitleCut } from './spec';

const TITLE_FONT = 84;
const TITLE_LINE = 1.2;

// 冒頭画面（サムネも兼ねる）
export const TitleCutView: React.FC<{ cut: TitleCut }> = ({ cut }) => {
  const lines = cut.title.split('\n').length;
  const titleTop = cut.pattern === 'A' && lines <= 2 ? 200 : 170;
  const titleH = Math.round(lines * TITLE_FONT * TITLE_LINE + 16 * 2 + 12 * 2);
  const imgTop = titleTop + titleH + 16;
  const mosaic = cut.mosaic ?? 48;

  let body: React.ReactNode = null;
  if (cut.pattern === 'A') {
    const bottom = 1580;
    const mid = Math.round(imgTop + (bottom - imgTop) * 0.47);
    body = (
      <>
        {cut.before ? <PhotoBox photo={cut.before} box={{ x: 90, y: imgTop, w: 900, h: mid - imgTop }} fit="cover" /> : null}
        <PhotoBox photo={cut.after} box={{ x: 90, y: mid, w: 900, h: bottom - mid }} mosaic={mosaic} fit="cover" />
        <ArrowDown cx={540} cy={mid} color={MAGENTA} />
      </>
    );
  } else if (cut.pattern === 'B') {
    const bottom = 1520;
    body = (
      <>
        {cut.before ? <PhotoBox photo={cut.before} box={{ x: 60, y: imgTop, w: 475, h: bottom - imgTop }} fit="cover" /> : null}
        <PhotoBox photo={cut.after} box={{ x: 545, y: imgTop, w: 475, h: bottom - imgTop }} mosaic={mosaic} fit="cover" />
        <ArrowRight cx={540} cy={Math.round(imgTop + (bottom - imgTop) * 0.72)} color={ARROW_RED} />
      </>
    );
  } else {
    body = <PhotoBox photo={cut.after} box={{ x: 120, y: imgTop, w: 840, h: 1540 - imgTop }} mosaic={mosaic} fit="cover" />;
  }

  return (
    <>
      {body}
      <div style={{ position: 'absolute', top: titleTop, left: 0, right: 0, display: 'flex', justifyContent: 'center' }}>
        <div
          style={{
            width: 960, boxSizing: 'border-box', background: '#fff', border: `12px solid ${MAGENTA}`, borderRadius: 18,
            padding: '16px 24px', fontFamily: FONT, fontWeight: 900, fontSize: TITLE_FONT, lineHeight: TITLE_LINE,
            color: MAGENTA, textAlign: 'center', whiteSpace: 'pre-line',
          }}
        >
          {cut.title}
        </div>
      </div>
    </>
  );
};

// 本編：写真1枚／公開カット／横長キャプチャ
export const BodyCutView: React.FC<{ cut: BodyCut }> = ({ cut }) => {
  const [rect, setRect] = useState<Rect | null>(null);
  if (cut.type === 'wide') {
    const box = { x: 55, y: 640, w: 970, h: 546 };
    return (
      <>
        <PhotoBox photo={cut.image} box={box} onRect={setRect} />
        <TopTelop telop={cut.top} y={TOP_TELOP_Y} />
        <BottomTelops telops={cut.bottom} anchorTop={(rect ? rect.y + rect.h : box.y + box.h) + 54} />
      </>
    );
  }
  return (
    <>
      <PhotoBox photo={cut.image} box={PHOTO} mosaic={cut.type === 'single' ? cut.mosaic : undefined} />
      <TopTelop telop={cut.top} y={TOP_TELOP_Y} />
      <BottomTelops telops={cut.bottom} anchorBottom={BOTTOM_EDGE} />
    </>
  );
};

// 本編：2枚比較（vertical＝上が昔・下が今／side＝左が昔・右が今）
export const CompareCutView: React.FC<{ cut: CompareCut }> = ({ cut }) => (
  <>
    {cut.layout === 'side' ? (
      <>
        <PhotoBox photo={cut.images[0]} box={{ x: 55, y: 386, w: 480, h: 1147 }} fit="cover" />
        <PhotoBox photo={cut.images[1]} box={{ x: 545, y: 386, w: 480, h: 1147 }} fit="cover" />
      </>
    ) : (
      <>
        <PhotoBox photo={cut.images[0]} box={{ x: 120, y: 386, w: 840, h: 566 }} fit="cover" />
        <PhotoBox photo={cut.images[1]} box={{ x: 120, y: 967, w: 840, h: 566 }} fit="cover" />
      </>
    )}
    <TopTelop telop={cut.top} y={TOP_TELOP_Y} />
    <BottomTelops telops={cut.bottom} anchorBottom={BOTTOM_EDGE} />
  </>
);

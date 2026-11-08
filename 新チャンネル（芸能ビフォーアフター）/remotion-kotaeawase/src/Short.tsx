import React, { useEffect, useState } from 'react';
import { AbsoluteFill, Audio, Sequence, continueRender, delayRender, staticFile, useVideoConfig } from 'remotion';
import { Background, ShowCredit, TelopSfx } from './parts';
import { BodyCutView, CompareCutView, TitleCutView } from './cuts';
import type { Cut, Spec } from './spec';

const textsOf = (cut: Cut): string[] => {
  if (cut.type === 'title') return [cut.title];
  const t = [cut.top.text, ...cut.bottom.map((b) => b.text)];
  if (cut.type === 'compare') return [...t, ...cut.images.map((i) => `${i.tag ?? ''}${i.label ?? ''}`)];
  return [...t, cut.image.label ?? ''];
};

// フォント（M PLUS Rounded 1c）を、使う文字の分だけ読み終わるまで待つ
const useFonts = (spec: Spec) => {
  const [handle] = useState(() => delayRender('fonts'));
  useEffect(() => {
    const all = spec.cuts.flatMap(textsOf).join('') + '0123456789出典：';
    Promise.all([
      document.fonts.load(`800 78px "M PLUS Rounded 1c"`, all),
      document.fonts.load(`900 84px "M PLUS Rounded 1c"`, all),
    ])
      .then(() => document.fonts.ready)
      .then(() => continueRender(handle))
      .catch(() => continueRender(handle));
  }, [handle, spec]);
};

export const cutFrames = (cut: Cut, fps: number) => Math.round(cut.dur * fps);

export const Short: React.FC<{ spec: Spec }> = ({ spec }) => {
  const { fps } = useVideoConfig();
  useFonts(spec);
  let from = 0;
  const vol = spec.sfx?.volume ?? 0.5;
  const titleSe = spec.sfx?.title === undefined ? 'se/don.wav' : spec.sfx.title;
  const telopSe = spec.sfx?.telop === undefined ? 'se/pon.wav' : spec.sfx.telop;
  const cutSe = spec.sfx?.cut ?? null;
  return (
    <ShowCredit.Provider value={spec.creditLabels ?? false}>
    <TelopSfx.Provider value={{ src: telopSe, volume: vol }}>
    <AbsoluteFill>
      <Background />
      {spec.cuts.map((cut, i) => {
        const dur = cutFrames(cut, fps);
        const start = from;
        from += dur;
        return (
          <Sequence key={i} from={start} durationInFrames={dur} name={`カット${i + 1}（${cut.type}）`}>
            {cut.type === 'title' ? <TitleCutView cut={cut} /> : null}
            {cut.type === 'single' || cut.type === 'reveal' || cut.type === 'wide' ? <BodyCutView cut={cut} /> : null}
            {cut.type === 'compare' ? <CompareCutView cut={cut} /> : null}
            {cut.voice ? <Audio src={staticFile(cut.voice)} /> : null}
            {'se' in cut && cut.se ? <Audio src={staticFile(cut.se)} volume={Math.min(1, vol * 1.6)} /> : null}
            {cut.type === 'title' && titleSe ? <Audio src={staticFile(titleSe)} volume={vol} /> : null}
            {cut.type !== 'title' && cutSe ? <Audio src={staticFile(cutSe)} volume={vol * 0.7} /> : null}
          </Sequence>
        );
      })}
      {spec.bgm ? <Audio src={staticFile(spec.bgm)} volume={spec.bgmVolume ?? 0.12} loop /> : null}
    </AbsoluteFill>
    </TelopSfx.Provider>
    </ShowCredit.Provider>
  );
};

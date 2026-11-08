import React from 'react';
import { Composition } from 'remotion';
import '@fontsource/m-plus-rounded-1c/800.css';
import '@fontsource/m-plus-rounded-1c/900.css';
import { Short, cutFrames } from './Short';
import { FPS, H, W } from './theme';
import type { Spec } from './spec';
import mihon from '../specs/mihon.json';

export const RemotionRoot: React.FC = () => (
  <Composition
    id="kotaeawase"
    component={Short}
    width={W}
    height={H}
    fps={FPS}
    durationInFrames={300}
    defaultProps={{ spec: mihon as Spec }}
    calculateMetadata={({ props }) => ({
      durationInFrames: props.spec.cuts.reduce((s, c) => s + cutFrames(c, FPS), 0),
    })}
  />
);

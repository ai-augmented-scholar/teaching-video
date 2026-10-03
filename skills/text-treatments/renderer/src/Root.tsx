import React from "react";
import {Composition} from "remotion";
import {TreatmentPackage, totalFrames, type PackageProps} from "./TreatmentPackage";
import {sampleCards} from "./sample-cards";
import {DEFAULT_LOOK} from "./design-systems";
import type {Mode} from "./Frame";

// One design system (neutral, built from the user's look), three modes.
// Cards, look and frame rate arrive as input props from the render script
// (`--props=<file>.json`), so nothing in src/ changes per video and two videos
// can render from the same install without overwriting each other.
//
// Every size is authored at 1920x1080. The frame rate follows the footage
// (the render script reads it), so the fades do not judder on the timeline.

const WIDTH = 1920;
const HEIGHT = 1080;
const DEFAULT_FPS = 30;

const modes: Mode[] = ["alpha", "imovie", "ground"];

export const RemotionRoot: React.FC = () => (
  <>
    {modes.map((mode) => (
      <Composition
        key={mode}
        id={`neutral-${mode}`}
        component={TreatmentPackage as never}
        durationInFrames={totalFrames(sampleCards, DEFAULT_FPS)}
        fps={DEFAULT_FPS}
        width={WIDTH}
        height={HEIGHT}
        defaultProps={{cards: sampleCards, look: DEFAULT_LOOK, mode, fps: DEFAULT_FPS} as never}
        calculateMetadata={({props}) => {
          const p = props as unknown as PackageProps;
          const fps = p.fps || DEFAULT_FPS;
          return {
            fps,
            durationInFrames: totalFrames(p.cards, fps),
            props: {...p, mode, fps} as never,
          };
        }}
      />
    ))}
  </>
);

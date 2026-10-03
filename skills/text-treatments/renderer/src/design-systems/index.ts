// A design system supplies every colour, type and layout decision. The scenes
// own none of their own: a scene asks for a role (`t.quote`, `t.eyebrow`) and
// the design system decides what that looks like. Never hardcode a colour, a
// font, a size or a weight in a scene.
//
// This plugin ships exactly one design system, `neutral`, and it is built at
// render time from the user's saved look (config.json → look). Every size is
// authored at 1920x1080.

export type ColorRole = "ink" | "secondary" | "accent";

export type TypeSpec = {
  family: string;
  weight: number;
  size: number;
  lineHeight: number;
  italic?: boolean;
  tracking?: number; // em
  uppercase?: boolean;
  color: ColorRole;
};

// A backdrop behind the text, for footage whose free area is too light for
// white letters. Edge-feathered so it never shows a hard border over footage —
// except in `imovie` mode, where the edge must be hard so the green key cuts it
// cleanly (see Frame.tsx).
export type Plate = {
  color: string; // hex, e.g. #202020
  opacity: number; // 0..1, e.g. 0.7
  featherX: number;
  featherY: number;
  bleedX: number;
  bleedY: number;
};

// A design system may carry its own motion. When it does not, the three
// helpers in motion.ts and their default timings apply.
export type MotionOverride = {
  inDur?: number;
  outDur?: number;
  rise?: number;
  // Uniform per-element step, used instead of the named stagger delays.
  staggerStep?: number;
  delayText?: number;
  easing?: [number, number, number, number];
};

// Where the type may live in the frame, in px at 1920x1080.
//   column       — a rectangle the user marked as free (an empty wall beside
//                  them). Every card sits inside it, left-aligned.
//   lower-thirds — no free area: every card becomes a lower third in a band
//                  along the bottom of the frame.
export type Layout =
  | {kind: "column"; left: number; top: number; width: number; height: number}
  | {kind: "lower-thirds"; padLeft: number; padBottom: number; width: number};

export type DesignSystem = {
  id: string;
  ground: string; // preview ground only (`ground` mode)
  ink: string;
  secondary: string;
  // Secondary as an OPAQUE colour, for the keyed `imovie` render: a
  // translucent colour blends with the key green into a pale green that the
  // keyer half removes and despill greys out. Optional; without it the
  // keyed render uses `secondary` as is.
  secondaryOpaque?: string;
  accent: string;
  hairline: string;
  plate?: Plate;
  motion?: MotionOverride;
  layout: Layout;
  type: {
    eyebrow: TypeSpec;
    dek: TypeSpec;
    hookHeadline: TypeSpec;
    titleHeadline: TypeSpec;
    quote: TypeSpec;
    ltName: TypeSpec;
    ltRole: TypeSpec;
    signOff: TypeSpec;
    cta: TypeSpec;
    stepIndex?: TypeSpec;
    stepLabel?: TypeSpec;
  };
};

export {buildNeutral, DEFAULT_LOOK} from "./neutral";
export type {Look} from "./neutral";

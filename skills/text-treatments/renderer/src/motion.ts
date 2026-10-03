// Exactly three motion helpers. Nothing eases outside them.
//
// The default timings are the accumulated craft of this skill; keep them.
//
// A design system MAY override them (`ds.motion`): its own easing curve, a
// uniform stagger step, a text delay that waits for its plate. One that says
// nothing gets the defaults below.
//
// Every helper takes localTime in SECONDS, measured from the start of its own
// scene — inside a Remotion <Sequence>, useCurrentFrame() already resets to
// zero, so localTime is simply frame / fps. That is what lets a scene stretch
// instead of clip when its duration changes.

import {interpolate, Easing} from "remotion";
import type {DesignSystem} from "./design-systems";

export const IN_DUR = 0.85;
export const OUT_DUR = 0.5;
export const RISE = 16;

// Per-element stagger, in seconds. Elements enter in reading order.
// A design system with a uniform staggerStep uses index * step instead; ORDER keeps the
// two schemes in agreement about which element is "first".
export const STAGGER = {
  eyebrow: 0.1,
  headline: 0.3,
  dek: 0.9,
  tail: 1.4,
} as const;

export const ORDER = {eyebrow: 0, headline: 1, dek: 2, tail: 3} as const;
export type Slot = keyof typeof STAGGER;

const easeOutCubic = Easing.bezier(0.215, 0.61, 0.355, 1);
const easeInOutSine = Easing.bezier(0.445, 0.05, 0.55, 0.95);

const easeOf = (ds?: DesignSystem) => {
  const e = ds?.motion?.easing;
  return e ? Easing.bezier(e[0], e[1], e[2], e[3]) : easeOutCubic;
};

const inDurOf = (ds?: DesignSystem) => ds?.motion?.inDur ?? IN_DUR;
const outDurOf = (ds?: DesignSystem) => ds?.motion?.outDur ?? OUT_DUR;
const riseOf = (ds?: DesignSystem) => ds?.motion?.rise ?? RISE;

// The delay for a named slot, honouring a uniform stagger if it has one.
export const delayFor = (slot: Slot, ds?: DesignSystem) => {
  const m = ds?.motion;
  if (m?.staggerStep !== undefined) {
    return (m.delayText ?? 0) + ORDER[slot] * m.staggerStep;
  }
  return STAGGER[slot];
};

// Fade and rise. Returns the style fragment for one element.
export const enter = (lt: number, slot: Slot, ds?: DesignSystem, riseOverride?: number) => {
  const delay = delayFor(slot, ds);
  const dur = inDurOf(ds);
  const rise = riseOverride ?? riseOf(ds);
  const p = interpolate(lt, [delay, delay + dur], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: easeOf(ds),
  });
  return {opacity: p, transform: `translateY(${(1 - p) * rise}px)`};
};

// 0 to 1, for a contour dash, a rule, or a scaleY. Lines draw; they never fade.
export const draw = (lt: number, delay: number, dur?: number, ds?: DesignSystem) =>
  interpolate(lt, [delay, delay + (dur ?? inDurOf(ds))], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: easeInOutSine,
  });

// The plate fades in first; the text waits for it.
export const plateIn = (lt: number, ds?: DesignSystem) => {
  const d = ds?.motion?.delayText ?? 0.3;
  // A design system with no plate can set delayText to 0 — there is nothing to wait
  // for. interpolate rejects a zero-length range, so short-circuit it.
  if (d <= 0) return 1;
  return interpolate(lt, [0, d], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: easeOf(ds),
  });
};

// Whole-frame opacity back to 0 across the last OUT_DUR of the scene.
// This is half of the cut contract: it guarantees the scene ends on bare ground.
export const close = (lt: number, sceneDur: number, ds?: DesignSystem) =>
  interpolate(lt, [sceneDur - outDurOf(ds), sceneDur], [1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: easeInOutSine,
  });

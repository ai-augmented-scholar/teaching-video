// The neutral design system: white type, no brand marks, built from the user's
// saved look (config.json → look) at render time.
//
// What the look decides:
//   layout          "column" (inside free_area) or "lower-thirds"
//   free_area       {x, y, w, h} as fractions of the frame (column only)
//   plate           true → a backdrop behind the text, for a light background
//   plate_color     default #202020
//   plate_opacity   default 0.7
//   text_color      default #FFFFFF
//   font            default "Inter" (bundled, so it works on any Mac)
//   font_file       optional, a font file the render script copied into
//                   public/fonts/user/ — for a font that is not installed
//
// Type scales with the column: a narrow free area gets smaller type, never
// below 24px, so every card stays readable on a laptop screen.

import type {DesignSystem, Layout, TypeSpec} from "./index";
import {familyFor} from "../fonts";

export type Look = {
  layout?: "column" | "lower-thirds";
  free_area?: {x: number; y: number; w: number; h: number};
  background_luminance?: number | null;
  plate?: boolean;
  plate_color?: string;
  plate_opacity?: number;
  text_color?: string;
  font?: string;
  font_file?: string;
};

export const DEFAULT_LOOK: Required<Omit<Look, "font_file" | "background_luminance">> = {
  layout: "column",
  free_area: {x: 0.05, y: 0.15, w: 0.4, h: 0.7},
  plate: false,
  plate_color: "#202020",
  plate_opacity: 0.7,
  text_color: "#FFFFFF",
  font: "Inter",
};

const W = 1920;
const H = 1080;
const FLOOR = 24;

const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v));

// Secondary text is the text colour at reduced strength, so a dek reads as
// second in line without a second hue.
const withAlpha = (hex: string, a: number) => {
  const h = hex.replace("#", "");
  const n = h.length === 3 ? h.split("").map((c) => c + c).join("") : h;
  const r = parseInt(n.slice(0, 2), 16);
  const g = parseInt(n.slice(2, 4), 16);
  const b = parseInt(n.slice(4, 6), 16);
  return `rgba(${r}, ${g}, ${b}, ${a})`;
};

// The same strength as an opaque colour: the text colour mixed over `under`
// at `a`. For the keyed `imovie` render, where translucency would mix with
// the key green (see DesignSystem.secondaryOpaque).
const mixOver = (hex: string, under: string, a: number) => {
  const rgb = (x: string) => {
    const h = x.replace("#", "");
    const n = h.length === 3 ? h.split("").map((c) => c + c).join("") : h;
    return [0, 2, 4].map((o) => parseInt(n.slice(o, o + 2), 16));
  };
  const [t, u] = [rgb(hex), rgb(under)];
  const m = t.map((v, i) => Math.round(a * v + (1 - a) * u[i]));
  return "#" + m.map((v) => v.toString(16).padStart(2, "0")).join("");
};

// Relative luminance (0..1) → the sRGB grey with that luminance, as hex.
const greyFor = (lum?: number | null) => {
  if (lum === undefined || lum === null || !(lum >= 0 && lum <= 1)) return "#202020";
  const v = lum <= 0.0031308 ? 12.92 * lum : 1.055 * Math.pow(lum, 1 / 2.4) - 0.055;
  const c = Math.round(clamp(v, 0, 1) * 255).toString(16).padStart(2, "0");
  return "#" + c + c + c;
};

export const buildNeutral = (input?: Look): DesignSystem => {
  const look = {...DEFAULT_LOOK, ...(input ?? {})};
  const family = familyFor(look.font, look.font_file);

  // Plate padding: generous, so the letters never crowd its edge.
  const bleedX = 44;
  const bleedY = 32;

  let layout: Layout;
  let scale: number;
  if (look.layout === "lower-thirds") {
    layout = {kind: "lower-thirds", padLeft: 120, padBottom: 96, width: 860};
    scale = 0.72;
  } else {
    const a = look.free_area ?? DEFAULT_LOOK.free_area;
    const fx = clamp(a.x, 0, 1);
    const fy = clamp(a.y, 0, 1);
    const fw = clamp(a.w, 0.05, 1 - fx);
    const fh = clamp(a.h, 0.05, 1 - fy);
    // Inset the column so a plate's bleed stays inside the free area, and
    // keep every card at least SAFE px from the frame edge (title-safe), even
    // when the free area runs to the edge.
    const SAFE = 80;
    const inset = look.plate ? bleedX : 24;
    const padY = look.plate ? bleedY : 16;
    const left = Math.round(Math.max(SAFE, fx * W + inset));
    const right = Math.round(Math.min(W - SAFE, (fx + fw) * W - inset));
    const top = Math.round(Math.max(SAFE, fy * H + padY));
    const bottom = Math.round(Math.min(H - SAFE, (fy + fh) * H - padY));
    const width = Math.max(320, right - left);
    const height = Math.max(200, bottom - top);
    layout = {kind: "column", left, top, width, height};
    // 1000px of column = full size; a 600px column gets 0.6.
    scale = clamp(width / 1000, 0.55, 1);
  }

  const sz = (base: number) => Math.max(FLOOR, Math.round(base * scale));

  const spec = (base: number, weight: number, extra: Partial<TypeSpec> = {}): TypeSpec => ({
    family,
    weight,
    size: sz(base),
    lineHeight: 1.18,
    color: "ink",
    ...extra,
  });

  const eyebrow: TypeSpec = {
    family,
    weight: 600,
    size: FLOOR,
    lineHeight: 1.2,
    tracking: 0.14,
    uppercase: true,
    color: "secondary",
  };

  return {
    id: "neutral",
    ground: "#2B2B2B",
    ink: look.text_color,
    secondary: withAlpha(look.text_color, 0.82),
    // Over the plate when there is one; otherwise over the background the
    // look questions measured (its relative luminance, as an sRGB grey), so
    // the keyed dek matches the alpha dek over the same wall. No measurement:
    // a dark stand-in, since white text without a plate is only chosen for a
    // dark background.
    secondaryOpaque: mixOver(
      look.text_color,
      look.plate ? look.plate_color : greyFor(look.background_luminance),
      0.82,
    ),
    accent: look.text_color,
    hairline: withAlpha(look.text_color, 0.5),
    plate: look.plate
      ? {
          color: look.plate_color,
          opacity: clamp(look.plate_opacity, 0, 1),
          featherX: 28,
          featherY: 22,
          bleedX,
          bleedY,
        }
      : undefined,
    motion: look.plate ? undefined : {delayText: 0},
    layout,
    type: {
      eyebrow,
      dek: spec(32, 400, {lineHeight: 1.45, color: "secondary"}),
      hookHeadline: spec(78, 650, {lineHeight: 1.1, tracking: -0.015}),
      titleHeadline: spec(66, 650, {lineHeight: 1.12, tracking: -0.012}),
      quote: spec(56, 500, {lineHeight: 1.2, italic: true}),
      ltName: spec(48, 650, {lineHeight: 1.15}),
      ltRole: spec(30, 400, {lineHeight: 1.35, color: "secondary"}),
      signOff: spec(62, 650, {lineHeight: 1.15, tracking: -0.012}),
      cta: eyebrow,
      stepIndex: {...eyebrow, size: sz(28), tracking: 0.08},
      stepLabel: spec(46, 550, {lineHeight: 1.2}),
    },
  };
};

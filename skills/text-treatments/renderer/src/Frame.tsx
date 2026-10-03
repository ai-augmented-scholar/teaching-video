import React from "react";
import {AbsoluteFill, useCurrentFrame, useVideoConfig} from "remotion";
import {close} from "./motion";
import type {DesignSystem, TypeSpec, ColorRole} from "./design-systems";

// Three render modes, one composition tree.
//   alpha   — transparent ground. ProRes 4444 with alpha, for editors that
//             read an alpha channel (Final Cut Pro, Premiere, Resolve, and
//             others).
//   imovie  — pure green ground (#00FF00), for iMovie's Green/Blue Screen
//             overlay. iMovie does not reliably honour an alpha channel in a
//             video overlay, so it gets a keyable ground instead.
//   ground  — a dark grey ground, for previewing the type.
export type Mode = "alpha" | "ground" | "imovie";

export const KEY_GREEN = "#00FF00";

export type SceneProps = {
  ds: DesignSystem;
  mode: Mode;
};

export const colorFor = (ds: DesignSystem, mode: Mode, role: ColorRole): string =>
  role === "ink"
    ? ds.ink
    : role === "secondary"
      ? (mode === "imovie" && ds.secondaryOpaque) || ds.secondary
      : ds.accent;

export const groundFor = (ds: DesignSystem, mode: Mode): string =>
  mode === "imovie" ? KEY_GREEN : mode === "ground" ? ds.ground : "transparent";

// Turns a design system's TypeSpec into a style object. Scenes never choose a
// font, a size, a weight or a colour themselves — they ask for a role.
export const textStyle = (
  ds: DesignSystem,
  mode: Mode,
  spec: TypeSpec
): React.CSSProperties => ({
  fontFamily: spec.family,
  fontWeight: spec.weight,
  fontSize: spec.size,
  lineHeight: spec.lineHeight,
  fontStyle: spec.italic ? "italic" : "normal",
  letterSpacing: spec.tracking ? `${spec.tracking}em` : undefined,
  textTransform: spec.uppercase ? "uppercase" : undefined,
  color: colorFor(ds, mode, spec.color),
});

// The plate, when the look asks for one (a background too light for white
// letters). Painted behind the content with a two-axis mask so the edges never
// show a hard border over footage.
//
// In imovie mode the plate is drawn OPAQUE with HARD edges. A keyer removes
// green by colour distance: a 70% plate over green becomes a dark green that
// iMovie half-keys into a muddy smear, and a feathered edge becomes a ring of
// green-tinted pixels. Opaque and hard keys cleanly. The cost: in iMovie the
// plate does not let the footage show through.
const PlateBackdrop: React.FC<{ds: DesignSystem; mode: Mode; opacity: number}> = ({
  ds,
  mode,
  opacity,
}) => {
  if (!ds.plate) return null;
  const {color, featherX, featherY, bleedX, bleedY} = ds.plate;
  const hard = mode === "imovie";
  const mask = hard
    ? undefined
    : [
        `linear-gradient(90deg, transparent, #000 ${featherX}px, #000 calc(100% - ${featherX}px), transparent)`,
        `linear-gradient(180deg, transparent, #000 ${featherY}px, #000 calc(100% - ${featherY}px), transparent)`,
      ].join(", ");
  return (
    <div
      style={{
        position: "absolute",
        inset: `${-bleedY}px ${-bleedX}px`,
        background: color,
        opacity: hard ? opacity : opacity * ds.plate.opacity,
        WebkitMaskImage: mask,
        maskImage: mask,
        WebkitMaskComposite: mask ? "source-in" : undefined,
        maskComposite: mask ? "intersect" : undefined,
      }}
    />
  );
};

// Where a scene's content block sits, from the design system's layout.
//   column       — inside the free rectangle the user marked, left-aligned,
//                  vertically centred in it (or at its foot for "bottom").
//   lower-thirds — every card sits in a band along the bottom of the frame.
export const columnFill = (
  ds: DesignSystem,
  vertical: "center" | "bottom" = "center",
  _fallbackPadPct = 12
): React.CSSProperties => {
  const l = ds.layout;
  if (l.kind === "lower-thirds") {
    return {
      alignItems: "flex-start",
      justifyContent: "flex-end",
      padding: `0 0 ${l.padBottom}px ${l.padLeft}px`,
    };
  }
  return {
    left: l.left,
    top: l.top,
    width: l.width,
    height: l.height,
    right: "auto",
    bottom: "auto",
    alignItems: "flex-start",
    justifyContent: vertical === "bottom" ? "flex-end" : "center",
  };
};

// The content block itself: left-aligned, capped at the column width, and
// otherwise as wide as its text, so a plate hugs the words instead of filling
// the whole free area.
export const columnWidth = (ds: DesignSystem): number => ds.layout.width;

export const columnBlock = (ds: DesignSystem): React.CSSProperties => ({
  maxWidth: columnWidth(ds),
  textAlign: "left",
});

// Wraps every scene. Owns the ground and the close(), so no scene can forget
// the second half of the cut contract.
export const Frame: React.FC<{
  ds: DesignSystem;
  mode: Mode;
  children: React.ReactNode;
}> = ({ds, mode, children}) => {
  const frame = useCurrentFrame();
  const {fps, durationInFrames} = useVideoConfig();
  const lt = frame / fps;
  // The last RENDERED frame is durationInFrames - 1, so the close() ramp has to
  // finish there, not at durationInFrames. Using the raw duration leaves the
  // final frame at ~7% opacity and puts a faint ghost on every lifted card.
  const sceneDur = (durationInFrames - 1) / fps;

  return (
    <AbsoluteFill style={{backgroundColor: groundFor(ds, mode)}}>
      <AbsoluteFill style={{opacity: close(lt, sceneDur, ds)}}>{children}</AbsoluteFill>
    </AbsoluteFill>
  );
};

// Content wrapper that carries the plate behind whatever a scene lays out.
// The caller's `style` goes on the INNER wrapper, not the outer one. Putting it
// outside left the children inside a plain block div, so a scene asking for
// `display: flex` silently got block flow — which is why the pull quote's,
// lower third's and end card's accent rules collapsed to zero size and never
// appeared.
export const PlatedBlock: React.FC<{
  ds: DesignSystem;
  mode: Mode;
  plateOpacity: number;
  style?: React.CSSProperties;
  children: React.ReactNode;
}> = ({ds, mode, plateOpacity, style, children}) => (
  <div style={{position: "relative"}}>
    <PlateBackdrop ds={ds} mode={mode} opacity={plateOpacity} />
    <div style={{position: "relative", ...style}}>{children}</div>
  </div>
);

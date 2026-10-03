import React from "react";
import {AbsoluteFill, useCurrentFrame, useVideoConfig} from "remotion";
import {
  Frame,
  PlatedBlock,
  textStyle,
  colorFor,
  columnFill,
  columnBlock,
  type SceneProps,
} from "../Frame";
import {enter, draw, delayFor, plateIn} from "../motion";

// Step list — eyebrow + 3 to 5 numbered items, each a tracked mono index and a
// display label, entering in reading order on the brand's own stagger.
// Typical duration 6–7s: the viewer has to read every line, not just the top one.
export const StepList: React.FC<
  SceneProps & {eyebrow?: string; headline?: string; items: string[]; delays?: number[]}
> = ({ds, mode, eyebrow, headline, items, delays}) => {
  const lt = useCurrentFrame() / useVideoConfig().fps;
  const t = ds.type;
  const indexSpec = t.stepIndex ?? t.eyebrow;
  const labelSpec = t.stepLabel ?? t.titleHeadline;
  const step = ds.motion?.staggerStep ?? 0.14;
  const base = delayFor("dek", ds);

  return (
    <Frame ds={ds} mode={mode}>
      <AbsoluteFill style={columnFill(ds, "center", 12)}>
        <PlatedBlock
          ds={ds}
          mode={mode}
          plateOpacity={plateIn(lt, ds)}
          style={{display: "flex", flexDirection: "column", gap: 26, ...columnBlock(ds)}}
        >
          {eyebrow ? (
            <div style={{...textStyle(ds, mode, t.eyebrow), ...enter(lt, "eyebrow", ds)}}>
              {eyebrow}
            </div>
          ) : null}
          {headline ? (
            <div style={{...textStyle(ds, mode, t.titleHeadline), ...enter(lt, "headline", ds)}}>
              {headline}
            </div>
          ) : null}
          <div style={{display: "flex", flexDirection: "column", gap: 20, marginTop: 12}}>
            {items.map((item, i) => {
              // Each item keeps the brand's uniform step, continuing the
              // choreography rather than starting a second one — unless the
              // card gives explicit per-row `delays`, which let a row land on
              // the spoken word.
              const delay = delays?.[i] ?? base + i * step;
              const p = draw(lt, delay, ds.motion?.inDur ?? 0.85, ds);
              const local = {
                opacity: p,
                transform: `translateY(${(1 - p) * (ds.motion?.rise ?? 16)}px)`,
              };
              const ruleFill = draw(lt, delay, 0.5, ds);
              return (
                <div key={i} style={{display: "flex", alignItems: "baseline", gap: 22, ...local}}>
                  <div style={{...textStyle(ds, mode, indexSpec), width: 52, flexShrink: 0}}>
                    {String(i + 1).padStart(2, "0")}
                  </div>
                  <div style={{position: "relative", paddingBottom: 14, flexGrow: 1}}>
                    <div style={textStyle(ds, mode, labelSpec)}>{item}</div>
                    <div
                      style={{
                        position: "absolute",
                        left: 0,
                        right: 0,
                        bottom: 0,
                        height: 1,
                        backgroundColor: colorFor(ds, mode, "accent"),
                        opacity: 0.32,
                        transform: `scaleX(${ruleFill})`,
                        transformOrigin: "left",
                      }}
                    />
                  </div>
                </div>
              );
            })}
          </div>
        </PlatedBlock>
      </AbsoluteFill>
    </Frame>
  );
};

import React from "react";
import {AbsoluteFill, useCurrentFrame, useVideoConfig} from "remotion";
import {Frame, PlatedBlock, textStyle, colorFor, type SceneProps, columnFill, columnBlock, columnWidth} from "../Frame";
import {enter, draw, plateIn} from "../motion";

// Pull quote — accent left rule that draws down + display line.
// Typical duration 4.5s. Attribution is optional and enters last.
export const PullQuote: React.FC<SceneProps & {quote: string; attribution?: string}> = ({
  ds,
  mode,
  quote,
  attribution,
}) => {
  const lt = useCurrentFrame() / useVideoConfig().fps;
  const t = ds.type;
  const rule = draw(lt, 0, 0.5, ds);

  return (
    <Frame ds={ds} mode={mode}>
      <AbsoluteFill style={columnFill(ds, "center", 14)}>
        <PlatedBlock
          ds={ds}
          mode={mode}
          plateOpacity={plateIn(lt, ds)}
          style={{display: "flex", alignItems: "stretch", gap: 40, ...columnBlock(ds)}}
        >
          <div
            style={{
              width: 4,
              backgroundColor: colorFor(ds, mode, "accent"),
              transform: `scaleY(${rule})`,
              transformOrigin: "top",
            }}
          />
          <div style={{display: "flex", flexDirection: "column", gap: 22, maxWidth: columnWidth(ds) - 44}}>
            <div style={{...textStyle(ds, mode, t.quote), ...enter(lt, "headline", ds)}}>
              {quote}
            </div>
            {attribution ? (
              <div style={{...textStyle(ds, mode, t.dek), ...enter(lt, "tail", ds)}}>
                {attribution}
              </div>
            ) : null}
          </div>
        </PlatedBlock>
      </AbsoluteFill>
    </Frame>
  );
};

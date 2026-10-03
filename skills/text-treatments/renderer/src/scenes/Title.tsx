import React from "react";
import {AbsoluteFill, useCurrentFrame, useVideoConfig} from "remotion";
import {Frame, PlatedBlock, textStyle, colorFor, type SceneProps, columnFill, columnBlock} from "../Frame";
import {enter, draw, delayFor, plateIn} from "../motion";

// Title — eyebrow + left display line + contour draw. Typical duration 4.5s.
// The contour is a rule, so it draws rather than fades.
export const Title: React.FC<SceneProps & {eyebrow: string; headline: string}> = ({
  ds,
  mode,
  eyebrow,
  headline,
}) => {
  const lt = useCurrentFrame() / useVideoConfig().fps;
  const t = ds.type;
  const contour = draw(lt, delayFor("dek", ds), 1.0, ds);

  return (
    <Frame ds={ds} mode={mode}>
      <AbsoluteFill style={columnFill(ds, "center", 12)}>
        <PlatedBlock
          ds={ds}
          mode={mode}
          plateOpacity={plateIn(lt, ds)}
          style={{display: "flex", flexDirection: "column", gap: 30, ...columnBlock(ds)}}
        >
          <div style={{...textStyle(ds, mode, t.eyebrow), ...enter(lt, "eyebrow", ds)}}>
            {eyebrow}
          </div>
          <div
            style={{
              ...textStyle(ds, mode, t.titleHeadline),
              ...enter(lt, "headline", ds),
              maxWidth: "100%",
            }}
          >
            {headline}
          </div>
          <div
            style={{
              height: 2,
              width: 220,
              backgroundColor: colorFor(ds, mode, "accent"),
              transform: `scaleX(${contour})`,
              transformOrigin: "left",
            }}
          />
        </PlatedBlock>
      </AbsoluteFill>
    </Frame>
  );
};

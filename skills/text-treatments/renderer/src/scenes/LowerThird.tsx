import React from "react";
import {AbsoluteFill, useCurrentFrame, useVideoConfig} from "remotion";
import {Frame, PlatedBlock, textStyle, colorFor, type SceneProps, columnFill, columnBlock} from "../Frame";
import {enter, draw, plateIn} from "../motion";

// Lower third — plate bottom-left. Typical duration 4s.
// No corner mark on this one: it already sits over a face.
export const LowerThird: React.FC<SceneProps & {name: string; role: string}> = ({
  ds,
  mode,
  name,
  role,
}) => {
  const lt = useCurrentFrame() / useVideoConfig().fps;
  const t = ds.type;
  const rule = draw(lt, 0, 0.6, ds);

  return (
    <Frame ds={ds} mode={mode}>
      <AbsoluteFill style={columnFill(ds, "bottom")}>
        <PlatedBlock
          ds={ds}
          mode={mode}
          plateOpacity={plateIn(lt, ds)}
          style={{display: "flex", alignItems: "stretch", gap: 26, ...columnBlock(ds)}}
        >
          <div
            style={{
              width: 3,
              backgroundColor: colorFor(ds, mode, "accent"),
              transform: `scaleY(${rule})`,
              transformOrigin: "top",
            }}
          />
          <div style={{display: "flex", flexDirection: "column", gap: 12}}>
            <div style={{...textStyle(ds, mode, t.ltName), ...enter(lt, "headline", ds, 12)}}>
              {name}
            </div>
            <div style={{...textStyle(ds, mode, t.ltRole), ...enter(lt, "dek", ds, 12)}}>
              {role}
            </div>
          </div>
        </PlatedBlock>
      </AbsoluteFill>
    </Frame>
  );
};

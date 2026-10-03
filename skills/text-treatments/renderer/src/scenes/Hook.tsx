import React from "react";
import {AbsoluteFill, useCurrentFrame, useVideoConfig} from "remotion";
import {Frame, PlatedBlock, textStyle, type SceneProps, columnFill, columnBlock} from "../Frame";
import {enter, plateIn} from "../motion";

// Hook — eyebrow + display line + dek. Typical duration 4s.
export const Hook: React.FC<SceneProps & {eyebrow: string; headline: string; dek?: string}> = ({
  ds,
  mode,
  eyebrow,
  headline,
  dek,
}) => {
  const lt = useCurrentFrame() / useVideoConfig().fps;
  const t = ds.type;

  return (
    <Frame ds={ds} mode={mode}>
      <AbsoluteFill style={columnFill(ds, "center", 12)}>
        <PlatedBlock
          ds={ds}
          mode={mode}
          plateOpacity={plateIn(lt, ds)}
          style={{display: "flex", flexDirection: "column", gap: 22, textAlign: "left", ...columnBlock(ds)}}
        >
          <div style={{...textStyle(ds, mode, t.eyebrow), ...enter(lt, "eyebrow", ds)}}>
            {eyebrow}
          </div>
          <div style={{...textStyle(ds, mode, t.hookHeadline), ...enter(lt, "headline", ds)}}>
            {headline}
          </div>
          {dek ? (
            <div style={{...textStyle(ds, mode, t.dek), ...enter(lt, "dek", ds)}}>{dek}</div>
          ) : null}
        </PlatedBlock>
      </AbsoluteFill>
    </Frame>
  );
};

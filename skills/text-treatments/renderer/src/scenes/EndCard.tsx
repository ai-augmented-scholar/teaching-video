import React from "react";
import {AbsoluteFill, Img, staticFile, useCurrentFrame, useVideoConfig} from "remotion";
import {Frame, PlatedBlock, textStyle, colorFor, type SceneProps, columnFill, columnBlock} from "../Frame";
import {enter, draw, delayFor, plateIn} from "../motion";

// End card — sign-off + optional dek + call to action. Typical duration 4.5s;
// 6 to 7s when the dek carries a full sentence.
// An optional mark (the user's own logo) goes here: pass it as markSrc — a file
// in renderer/public/, loaded through staticFile(). markOpacity sets how
// strongly it shows (default 1).
export const EndCard: React.FC<
  SceneProps & {signOff: string; dek?: string; cta: string; markSrc?: string; markOpacity?: number}
> = ({ds, mode, signOff, dek, cta, markSrc, markOpacity}) => {
  const lt = useCurrentFrame() / useVideoConfig().fps;
  const t = ds.type;
  const rule = draw(lt, delayFor("dek", ds) + (dek ? 0.4 : 0), 0.8, ds);
  const markIn = enter(lt, "eyebrow", ds);

  return (
    <Frame ds={ds} mode={mode}>
      <AbsoluteFill style={columnFill(ds, "center", 12)}>
        <PlatedBlock
          ds={ds}
          mode={mode}
          plateOpacity={plateIn(lt, ds)}
          style={{
            display: "flex",
            flexDirection: "column",
            alignItems: "flex-start",
            gap: 30,
            textAlign: "left",
            ...columnBlock(ds),
          }}
        >
          {markSrc ? (
            <Img
              src={staticFile(markSrc)}
              style={{
                width: 108,
                height: 108,
                ...markIn,
                opacity: markIn.opacity * (markOpacity ?? 1),
              }}
            />
          ) : null}
          <div style={{...textStyle(ds, mode, t.signOff), ...enter(lt, "headline", ds)}}>
            {signOff}
          </div>
          {dek ? (
            <div style={{...textStyle(ds, mode, t.dek), ...enter(lt, "dek", ds)}}>{dek}</div>
          ) : null}
          <div
            style={{
              height: 2,
              width: 180,
              backgroundColor: colorFor(ds, mode, "accent"),
              transform: `scaleX(${rule})`,
            }}
          />
          <div style={{...textStyle(ds, mode, t.cta), ...enter(lt, "tail", ds)}}>{cta}</div>
        </PlatedBlock>
      </AbsoluteFill>
    </Frame>
  );
};

import React from "react";
import {AbsoluteFill, Sequence} from "remotion";
import {buildNeutral, type DesignSystem, type Look} from "./design-systems";
import type {Mode} from "./Frame";
import {Hook} from "./scenes/Hook";
import {Title} from "./scenes/Title";
import {PullQuote} from "./scenes/PullQuote";
import {LowerThird} from "./scenes/LowerThird";
import {EndCard} from "./scenes/EndCard";
import {StepList} from "./scenes/StepList";

// One clip, many treatments. Each card is a self-contained scene laid end to
// end; the editor scrubs to one and cuts it out. Never deliver one file per
// card.
//
// Every scene starts and ends on the bare ground, so adjacent scenes match
// frame for frame and any card lifts out with clean handles at both ends.

export type Card =
  | {kind: "hook"; dur: number; eyebrow: string; headline: string; dek?: string}
  | {kind: "title"; dur: number; eyebrow: string; headline: string}
  | {kind: "pullQuote"; dur: number; quote: string; attribution?: string}
  | {kind: "lowerThird"; dur: number; name: string; role: string}
  // `delays`: optional per-row entry times in seconds from the card start, so a
  // row can land on the spoken word instead of on the uniform stagger.
  | {kind: "stepList"; dur: number; eyebrow?: string; headline?: string; items: string[]; delays?: number[]}
  // `dek`: an optional second, smaller line under the sign-off.
  // `markSrc`: optional logo file in public/; `markOpacity`: default 1.
  | {kind: "endCard"; dur: number; signOff: string; dek?: string; cta: string; markSrc?: string; markOpacity?: number};

export const totalFrames = (cards: Card[], fps: number) =>
  cards.reduce((sum, c) => sum + Math.round(c.dur * fps), 0);

const renderCard = (card: Card, ds: DesignSystem, mode: Mode) => {
  switch (card.kind) {
    case "hook":
      return <Hook ds={ds} mode={mode} eyebrow={card.eyebrow} headline={card.headline} dek={card.dek} />;
    case "title":
      return <Title ds={ds} mode={mode} eyebrow={card.eyebrow} headline={card.headline} />;
    case "pullQuote":
      return <PullQuote ds={ds} mode={mode} quote={card.quote} attribution={card.attribution} />;
    case "lowerThird":
      return <LowerThird ds={ds} mode={mode} name={card.name} role={card.role} />;
    case "stepList":
      return (
        <StepList
          ds={ds}
          mode={mode}
          eyebrow={card.eyebrow}
          headline={card.headline}
          items={card.items}
          delays={card.delays}
        />
      );
    case "endCard":
      return (
        <EndCard
          ds={ds}
          mode={mode}
          signOff={card.signOff}
          dek={card.dek}
          cta={card.cta}
          markSrc={card.markSrc}
          markOpacity={card.markOpacity}
        />
      );
  }
};

// The props a render receives (`--props=<file>.json`): the cards for this
// video, the user's saved look, and the frame rate of their footage.
export type PackageProps = {
  cards: Card[];
  look?: Look;
  mode: Mode;
  fps: number;
};

export const TreatmentPackage: React.FC<PackageProps> = ({cards, look, mode, fps}) => {
  const ds: DesignSystem = buildNeutral(look);
  let from = 0;
  return (
    <AbsoluteFill>
      {cards.map((card, i) => {
        const durationInFrames = Math.round(card.dur * fps);
        const seq = (
          <Sequence key={i} from={from} durationInFrames={durationInFrames} name={card.kind}>
            {renderCard(card, ds, mode)}
          </Sequence>
        );
        from += durationInFrames;
        return seq;
      })}
    </AbsoluteFill>
  );
};

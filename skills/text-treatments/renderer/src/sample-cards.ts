// Sample cards, used only by Remotion Studio and as the render default when no
// cards file is passed. A real video's cards come from its own cards.json.

import type {Card} from "./TreatmentPackage";

export const sampleCards: Card[] = [
  {kind: "hook", dur: 4, eyebrow: "Week 3", headline: "Why the Enlightenment is not the Renaissance", dek: "Two movements, two directions in time."},
  {kind: "title", dur: 4.5, eyebrow: "Part 1", headline: "The Renaissance looks back"},
  {kind: "pullQuote", dur: 4.5, quote: "Dare to know.", attribution: "Immanuel Kant, 1784"},
  {kind: "lowerThird", dur: 4, name: "Your Name", role: "Department · Course"},
  {kind: "stepList", dur: 6.5, eyebrow: "Three questions", items: ["Where is the golden age?", "Who holds authority?", "What counts as evidence?"]},
  {kind: "endCard", dur: 4.5, signOff: "Next week: the Romantics", cta: "Readings on the course page"},
];

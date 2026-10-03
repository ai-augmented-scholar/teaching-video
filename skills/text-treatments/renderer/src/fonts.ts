// Font loading. Inter ships inside the renderer (public/fonts, SIL Open Font
// License, see public/fonts/OFL.txt), so the default look renders the same on
// any Mac without an install.
//
// Another font comes from one of two places:
//   - installed on the Mac: Chrome finds it by family name, nothing to load;
//   - a font file (look.font_file): the render script copies it into
//     public/fonts/user/, and it is loaded here under the family name.
// Inter stays in every stack as the fallback, so a missing font degrades to
// Inter instead of to a browser default. scripts/look/check_font.py tells the
// user beforehand whether their font will actually render.

import {continueRender, delayRender, staticFile} from "remotion";

const BUNDLED = "TV Inter";
const loaded = new Set<string>();

const load = (family: string, url: string, descriptors: FontFaceDescriptors) => {
  const key = `${family}|${url}|${descriptors.style ?? "normal"}`;
  if (loaded.has(key) || typeof document === "undefined") return;
  loaded.add(key);
  const handle = delayRender(`font ${family}`);
  const face = new FontFace(family, `url("${url}")`, descriptors);
  face
    .load()
    .then((f) => {
      document.fonts.add(f);
      continueRender(handle);
    })
    .catch((err) => {
      // A broken font file must not hang the render: fall back to Inter.
      console.error(`Could not load font ${family}: ${err}`);
      continueRender(handle);
    });
};

load(BUNDLED, staticFile("fonts/InterVariable.woff2"), {weight: "100 900", style: "normal"});
load(BUNDLED, staticFile("fonts/InterVariable-Italic.woff2"), {weight: "100 900", style: "italic"});

export const familyFor = (font?: string, fontFile?: string): string => {
  const name = (font ?? "").trim();
  if (!name || name.toLowerCase() === "inter") return `"${BUNDLED}", sans-serif`;
  if (fontFile) load(name, staticFile(fontFile), {weight: "100 900", style: "normal"});
  return `"${name}", "${BUNDLED}", sans-serif`;
};

#!/usr/bin/env node
// Render a video's text cards. Plain Node, no dependencies of its own.
//
//   TV_DATA="<plugin data folder>" node render.mjs --cards cards.json --out DIR \
//       [--footage VIDEO] [--modes alpha,imovie,ground] [--look look.json] \
//       [--name STEM] [--check]
//
// What it does, in order:
//   1. Syncs the renderer from the plugin into $TV_DATA/renderer (the plugin
//      folder changes on every update, so the 1.6 GB of node_modules live in
//      the data folder), then runs its setup.mjs, which installs only when
//      package.json or package-lock.json changed.
//   2. Builds the render props: the cards, the user's look from
//      $TV_DATA/config.json (or --look), and the footage's frame rate.
//   3. Renders each requested mode:
//        alpha   ProRes 4444 with alpha   <stem>-alpha.mov
//        imovie  ProRes 422 HQ on green   <stem>-imovie-green.mov
//        ground  H.264 preview            <stem>-preview.mp4
//   4. With --check, verifies the cut contract: every card boundary frame must
//      equal the bare ground, checked on lossless PNG frames.
//   5. Writes <stem>-card-times.txt (where each card starts in the clip) and
//      prints a JSON summary.

import {spawnSync} from "node:child_process";
import {createHash} from "node:crypto";
import {
  copyFileSync, cpSync, existsSync, mkdirSync, readFileSync, readdirSync,
  rmSync, writeFileSync,
} from "node:fs";
import {basename, dirname, join, resolve} from "node:path";
import {fileURLToPath} from "node:url";
import {homedir} from "node:os";

const HERE = dirname(fileURLToPath(import.meta.url));
const SOURCE = resolve(HERE, "..", "renderer");

const fail = (msg) => {
  process.stderr.write(`text-treatments: ${msg}\n`);
  process.exit(1);
};

// ---- arguments ------------------------------------------------------------
const args = {modes: "alpha,imovie", name: "text-cards", check: false};
const argv = process.argv.slice(2);
for (let i = 0; i < argv.length; i++) {
  const a = argv[i];
  if (a === "--check") args.check = true;
  else if (a.startsWith("--")) args[a.slice(2)] = argv[++i];
}
if (!args.cards) fail("--cards <cards.json> is required");
if (!args.out) fail("--out <folder> is required");

const expand = (p) => (p && p.startsWith("~/") ? join(homedir(), p.slice(2)) : p);
const DATA = expand(args.data || process.env.TV_DATA || "");
if (!DATA || !existsSync(DATA)) {
  fail("the plugin data folder is missing. Run /video-teach-plugin:setup first.");
}
const OUT = resolve(expand(args.out));
mkdirSync(OUT, {recursive: true});

const ENV = {
  ...process.env,
  PATH: `/opt/homebrew/bin:/usr/local/bin:${process.env.PATH || ""}`,
};

const run = (cmd, argList, cwd) => {
  const r = spawnSync(cmd, argList, {cwd, env: ENV, encoding: "utf8", maxBuffer: 64 * 1024 * 1024});
  return r;
};

// ---- 1. sync the renderer -------------------------------------------------
const DEST = join(DATA, "renderer");
mkdirSync(DEST, {recursive: true});
const sameBytes = (a, b) =>
  existsSync(b) &&
  createHash("sha256").update(readFileSync(a)).digest("hex") ===
    createHash("sha256").update(readFileSync(b)).digest("hex");

for (const f of ["package.json", "package-lock.json"]) {
  const s = join(SOURCE, f);
  if (existsSync(s) && !sameBytes(s, join(DEST, f))) copyFileSync(s, join(DEST, f));
}
for (const f of ["remotion.config.ts", "tsconfig.json", "setup.mjs"]) {
  copyFileSync(join(SOURCE, f), join(DEST, f));
}
rmSync(join(DEST, "src"), {recursive: true, force: true});
cpSync(join(SOURCE, "src"), join(DEST, "src"), {recursive: true});
mkdirSync(join(DEST, "public", "fonts"), {recursive: true});
for (const f of readdirSync(join(SOURCE, "public", "fonts"))) {
  copyFileSync(join(SOURCE, "public", "fonts", f), join(DEST, "public", "fonts", f));
}

const setup = run("node", ["setup.mjs"], DEST);
if (setup.status !== 0) fail(`renderer setup failed:\n${setup.stderr || setup.stdout}`);

// ---- 2. props ---------------------------------------------------------------
let cards;
try {
  const raw = JSON.parse(readFileSync(expand(args.cards), "utf8"));
  cards = Array.isArray(raw) ? raw : raw.cards;
} catch (e) {
  fail(`cannot read the cards file: ${e.message}`);
}
if (!Array.isArray(cards) || cards.length === 0) fail("the cards file holds no cards");

let look = {};
const cfgPath = join(DATA, "config.json");
if (args.look) look = JSON.parse(readFileSync(expand(args.look), "utf8"));
else if (existsSync(cfgPath)) look = JSON.parse(readFileSync(cfgPath, "utf8")).look || {};

if (look.font_file) {
  const src = expand(look.font_file);
  if (existsSync(src)) {
    const userDir = join(DEST, "public", "fonts", "user");
    mkdirSync(userDir, {recursive: true});
    copyFileSync(src, join(userDir, basename(src)));
    look = {...look, font_file: `fonts/user/${basename(src)}`};
  } else {
    process.stderr.write(`text-treatments: font file not found (${src}); using the installed font or Inter.\n`);
    look = {...look, font_file: undefined};
  }
}

let fps = 30;
if (args.footage) {
  const p = run("ffprobe", [
    "-v", "error", "-select_streams", "v:0",
    "-show_entries", "stream=r_frame_rate", "-of", "csv=p=0", expand(args.footage),
  ]);
  const m = (p.stdout || "").trim().match(/^(\d+)\/(\d+)$/);
  if (m) fps = Math.round((Number(m[1]) / Number(m[2])) * 1000) / 1000;
}

const props = {cards, look, fps};
const stem = args.name;
const propsPath = join(OUT, `${stem}-props.json`);
writeFileSync(propsPath, JSON.stringify(props, null, 2));

// ---- 3. render ----------------------------------------------------------------
const remotion = (list) => run("npx", ["--no-install", "remotion", ...list], DEST);
const MODES = {
  alpha: {
    file: `${stem}-alpha.mov`,
    flags: ["--image-format=png", "--pixel-format=yuva444p10le", "--codec=prores", "--prores-profile=4444"],
  },
  imovie: {
    file: `${stem}-imovie-green.mov`,
    flags: ["--image-format=png", "--codec=prores", "--prores-profile=hq"],
  },
  ground: {file: `${stem}-preview.mp4`, flags: ["--codec=h264", "--crf=18"]},
};

const summary = {fps, cards: cards.length, outputs: [], check: null};
for (const mode of args.modes.split(",").map((m) => m.trim()).filter(Boolean)) {
  const m = MODES[mode];
  if (!m) fail(`unknown mode "${mode}" (alpha, imovie, ground)`);
  const target = join(OUT, m.file);
  const t0 = Date.now();
  // --timeout: a long alpha render keeps every browser tab busy writing PNG
  // frames, and the bundled font then takes longer than Remotion's 28 s
  // default to load in a new tab (seen on a 96 s, 60 fps package).
  const r = remotion(["render", "src/index.ts", `neutral-${mode}`, target, `--props=${propsPath}`, "--timeout=120000", ...m.flags]);
  if (r.status !== 0) fail(`render of ${mode} failed:\n${(r.stderr || r.stdout).slice(-3000)}`);
  summary.outputs.push({mode, file: target, seconds: Math.round((Date.now() - t0) / 100) / 10});
}

// ---- 4. the cut contract --------------------------------------------------------
const starts = [];
let acc = 0;
for (const c of cards) {
  starts.push(acc);
  acc += Math.round(c.dur * fps);
}
const total = acc;

if (args.check) {
  // Remotion reads a dot in the folder name as a file extension, so no dot here.
  const tmp = join(OUT, `${stem}-check-frames`);
  rmSync(tmp, {recursive: true, force: true});
  mkdirSync(tmp, {recursive: true});
  const r = remotion([
    "render", "src/index.ts", "neutral-ground", tmp, `--props=${propsPath}`,
    "--sequence", "--image-format=png", "--timeout=120000",
  ]);
  if (r.status !== 0) fail(`check render failed:\n${(r.stderr || r.stdout).slice(-3000)}`);
  const files = readdirSync(tmp).filter((f) => f.endsWith(".png")).sort();
  const md5 = (i) => createHash("md5").update(readFileSync(join(tmp, files[i]))).digest("hex");
  const bare = md5(0);
  const boundary = new Set([total - 1]);
  for (const s of starts) {
    boundary.add(s);
    if (s > 0) boundary.add(s - 1);
  }
  const pops = [...boundary].sort((a, b) => a - b).filter((f) => f < files.length && md5(f) !== bare);
  summary.check = {frames_checked: boundary.size, pops};
  rmSync(tmp, {recursive: true, force: true});
}

// ---- 5. card times ----------------------------------------------------------------
const tc = (frames) => {
  const s = frames / fps;
  const mm = Math.floor(s / 60);
  const ss = (s - mm * 60).toFixed(2).padStart(5, "0");
  return `${mm}:${ss}`;
};
const label = (c) => c.headline || c.quote || c.name || c.signOff || c.eyebrow || (c.items || [])[0] || "";
const lines = cards.map((c, i) => `${String(i + 1).padStart(2, "0")}  ${tc(starts[i])}–${tc(starts[i] + Math.round(c.dur * fps))}  ${c.kind.padEnd(10)} ${label(c)}`);
writeFileSync(join(OUT, `${stem}-card-times.txt`), `Where each card sits in the clip (${fps} fps)\n\n${lines.join("\n")}\n`);
summary.card_times = join(OUT, `${stem}-card-times.txt`);
summary.duration_seconds = Math.round((total / fps) * 100) / 100;

process.stdout.write(JSON.stringify(summary, null, 2) + "\n");

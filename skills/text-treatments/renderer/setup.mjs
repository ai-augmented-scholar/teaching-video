// Text-treatments renderer bootstrap. Plain Node, no dependencies.
//   node setup.mjs
// Idempotent and safe to run before every render. Installs npm dependencies
// only when they are missing or stale, and pre-downloads Remotion's headless
// browser so the first render does not stall. Prints one line on success.
import {spawnSync} from "node:child_process";
import {existsSync, readFileSync, writeFileSync} from "node:fs";
import {createHash} from "node:crypto";
import {dirname, join} from "node:path";
import {fileURLToPath} from "node:url";

const ROOT = dirname(fileURLToPath(import.meta.url));

const fail = (step, detail) => {
  process.stderr.write(`text-treatments setup failed at: ${step}\n`);
  if (detail && detail.trim()) process.stderr.write(detail.trim() + "\n");
  process.exit(1);
};

const run = (cmd) =>
  spawnSync(cmd, {
    cwd: ROOT,
    shell: true,
    encoding: "utf8",
    stdio: ["ignore", "pipe", "pipe"],
    maxBuffer: 32 * 1024 * 1024,
  });

// Node 18+
const major = Number(process.versions.node.split(".")[0]);
if (major < 18) fail("node version", `Found Node ${process.versions.node}; need 18 or newer.`);

// Dependencies: reinstall when node_modules is absent or when package.json /
// package-lock.json changed since the last install. A content hash, not file
// times: the render script copies these files on every plugin update, which
// would make a time comparison reinstall every run.
const modules = join(ROOT, "node_modules");
const stamp = join(modules, ".tv-install-hash");
const hash = createHash("sha256");
for (const f of ["package.json", "package-lock.json"]) {
  if (existsSync(join(ROOT, f))) hash.update(readFileSync(join(ROOT, f)));
}
const want = hash.digest("hex");
const have = existsSync(stamp) ? readFileSync(stamp, "utf8").trim() : "";

if (!existsSync(modules) || have !== want) {
  const r = run("npm install --no-audit --no-fund");
  if (r.status !== 0) fail("npm install", r.stderr || r.stdout);
  writeFileSync(stamp, want + "\n");
}

// Remotion's headless browser, so the first render does not pause to fetch it.
const b = run("npx remotion browser ensure");
if (b.status !== 0) fail("remotion browser ensure", b.stderr || b.stdout);

process.stdout.write("text-treatments renderer ready\n");

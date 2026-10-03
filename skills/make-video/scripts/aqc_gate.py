#!/usr/bin/env python3
"""Run audio-quality-check on a finished file and decide whether the workflow may continue.

Usage:
  aqc_gate.py FILE [--cleaned] [--target-lufs -16] [--ceiling-dbtp -1.5]
  aqc_gate.py --from-json RESULT.json [--cleaned]   (test hook: gate a saved --json result)

--cleaned says the file already went through audio-enhance (step 03) and,
for a cut or an export, perfect-cuts (step 04). make-video passes it at steps
04 and 09. Without the flag the gate still treats a file as cleaned when its
name shows it (`_enhanced-audio`, a `perfect cut (C)` package folder) or when
a make-video-status.json beside it, or one or two folders up, lists the file
as an output of step 03, 04 or 07. On a cleaned file the advice never says
"run audio-enhance": running it again cannot help, and on a tightly cut file
a raised floor or a lower signal-to-noise ratio is expected (the pauses are
gone, so the quietest moments sit next to speech). The advice then speaks
about the next recording, and only when a value is really poor (FAIL).
The stop rules, the check ids and the table do not change.

Prints, in this order: the gate's own verdict in plain words ("Sound check: OK
to continue." or "Sound check: STOP ..."), any advice, audio-quality-check's
table WITHOUT its own VERDICT line, then one GATE line and a JSON summary.
The table's verdict is left out on purpose: it judges a file for publishing
(any FAIL fails), while the gate only stops on loudness or true peak, and two
contradicting verdicts on one screen read as a failure.

Exit 0 = continue (warnings are advice), 2 = stop (loudness or true peak failed),
3 = the JSON lacks a gating check id, so the gate cannot decide.

The gate matches the stable check ids that analyze.py puts in its --json output
(loudness, true_peak, noise_floor, silences, level_consistency, clarity), never
the printed check names. A renamed or removed gating check therefore stops the
workflow with exit 3 instead of passing silently.

Only loudness and true peak can stop the workflow. Run this on the finished
cut (after step 04) or the user's final export (after step 09), never on the
uncut cleaned recording: there the retake pauses fail the silence check and
the very low floor after noise removal inflates the level spread, so the other
checks read as failures that the cut itself does not have.
"""
import argparse
import importlib.util
import re
import json
import sys
from pathlib import Path

GATING_IDS = ("loudness", "true_peak")
CLEAN_STEPS = ("03", "04", "07")


def looks_cleaned(path):
    """Evidence from the file system that FILE already went through cleanup."""
    p = Path(path).resolve()
    if "_enhanced-audio" in p.name:
        return True
    if any("perfect cut (C)" in part for part in p.parent.parts[-2:]):
        return True
    for folder in (p.parent, p.parent.parent, p.parent.parent.parent):
        status = folder / "make-video-status.json"
        if not status.is_file():
            continue
        try:
            steps = json.loads(status.read_text()).get("steps", [])
        except (OSError, ValueError):
            continue
        for st in steps:
            if st.get("step") in CLEAN_STEPS and any(
                    Path(o).resolve() == p for o in st.get("outputs", [])):
                return True
    return False


def cleaned_advice(row):
    """Advice for a check on a file that is already cleaned and cut.

    Returns None to keep the table's own fix text (it never names a step that
    would help less than it says)."""
    cid, bad = row["id"], row["status"] == "FAIL"
    if cid == "noise_floor":
        if not bad:
            return ("Expected on a cleaned, tightly cut file: with the pauses cut "
                    "out, the quietest moments sit next to speech. Nothing to re-run.")
        return ("Background noise is still audible after cleanup. Running "
                "audio-enhance again will not remove it. For the next recording: "
                "a quieter room (fans, air conditioning, computer off) and the mic "
                "closer to your mouth.")
    if cid == "clarity":
        if "below 44.1 kHz" in str(row.get("value")):
            return ("Record at 48 kHz next time (a setting in your camera or "
                    "recording app). Nothing to re-run for this file.")
        if not bad:
            return ("Fine for a lecture video: the voice sits clearly above the "
                    "background. Nothing to re-run.")
        return ("The voice sits close to the background noise. Re-running a step "
                "will not change that. For the next recording: the mic closer and "
                "a quieter room.")
    if cid == "level_consistency":
        # The spread figure (10th to 90th percentile of speech windows) is
        # inflated on a cleaned, cut file: noise removal pushes the floor down,
        # breaths and word tails pass the speech test, and the cut leaves no
        # pauses. The loudness range (LRA) is the honest reading there.
        lra = re.search(r"LRA ([\d.]+) LU", str(row.get("value")))
        if lra and float(lra.group(1)) <= 6.0:
            return ("The loudness range is steady (LRA %s LU). The spread figure "
                    "is raised by the quiet gaps between words in a cleaned, cut "
                    "file. Nothing to do." % lra.group(1))
        if not bad:
            return ("Small level swings are normal in a lecture. Nothing to re-run.")
        return ("The level swings a lot, usually from moving toward and away from "
                "the mic. For the next recording, keep a fixed distance from it.")
    if cid == "silences":
        return ("There is a pause of 2 s or more in the file. If it is not on "
                "purpose, ask for it to be cut at the review (step 05) or cut it "
                "in your editor.")
    if cid == "true_peak":
        return ("Slightly above the -1.5 dBTP target, usually from the editor's "
                "export; safe to publish. To bring it under the target, lower the "
                "volume by 1 dB in the editor before you export.")
    if cid == "loudness":
        return ("A little off the -16 LUFS target, usually from the editor's "
                "export; fine for a course video. Leave the volume at 100% in the "
                "editor to stay on target.")
    return None
ANALYZE = Path(__file__).resolve().parents[2] / "audio-quality-check" / "scripts" / "analyze.py"


def load_analyze():
    if not ANALYZE.is_file():
        sys.exit(f"ERROR: audio-quality-check not found at {ANALYZE}")
    spec = importlib.util.spec_from_file_location("aqc_analyze", ANALYZE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def gate(rec, mod=None, cleaned=False):
    checks = rec.get("checks", [])
    present = {c.get("id") for c in checks}
    missing = [i for i in GATING_IDS if i not in present]
    if missing:
        print("Sound check: ERROR - the gate cannot decide. audio-quality-check "
              "returned no check with id " + ", ".join(missing) + "; the check ids "
              "in audio-quality-check/scripts/analyze.py and this script must match.")
        print("\nGATE: ERROR")
        sys.exit(3)

    blocking, advice = [], []
    for c in checks:
        if c.get("status") == "PASS":
            continue
        row = {"id": c.get("id"), "check": c.get("check"), "status": c.get("status"),
               "value": c.get("value"), "fix": c.get("fix")}
        if cleaned and not (c.get("status") == "FAIL" and c.get("id") in GATING_IDS):
            row["fix"] = cleaned_advice(row) or row["fix"]
        if c.get("status") == "FAIL" and c.get("id") in GATING_IDS:
            blocking.append(row)
        else:
            advice.append(row)

    ok = not blocking
    # 1. The gate's verdict first, in plain words.
    if ok:
        print("Sound check: OK to continue. Loudness and peak level are within target.")
    else:
        print("Sound check: STOP. "
              + "; ".join(f"{b['check']} is {b['value']}" for b in blocking)
              + ". Fix this before going on.")
    if advice:
        print("Advice (does not stop the workflow"
              + ("; this file is already cleaned, so it is about the recording,"
                 " not about re-running a step" if cleaned else "") + "):")
        for a in advice:
            print(f"  - {a['check']}: {a['value']}. {a['fix']}")

    # 2. The detailed table, without its own VERDICT line.
    if mod is not None and rec.get("measurements"):
        mod.print_report(rec, show_verdict=False)

    # 3. Machine-readable lines last.
    print(f"GATE: {'CONTINUE' if ok else 'STOP'}")
    print(json.dumps({"file": rec.get("file"), "table_verdict": rec.get("verdict"),
                      "cleaned": cleaned, "continue": ok,
                      "blocking": blocking, "advice": advice}, indent=2))
    sys.exit(0 if ok else 2)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("file", nargs="?")
    p.add_argument("--target-lufs", type=float, default=-16.0)
    p.add_argument("--ceiling-dbtp", type=float, default=-1.5)
    p.add_argument("--from-json", help="gate a saved analyze.py --json result (for tests)")
    p.add_argument("--cleaned", action="store_true",
                   help="the file already went through audio-enhance (and perfect-cuts)")
    a = p.parse_args()

    mod = load_analyze()
    if a.from_json:
        data = json.loads(Path(a.from_json).read_text())
        gate(data[0] if isinstance(data, list) else data, mod, cleaned=a.cleaned)
    if not a.file:
        p.error("give a FILE, or --from-json")
    if not Path(a.file).is_file():
        sys.exit(f"ERROR: not found: {a.file}")

    mod.need_tool("ffmpeg")
    mod.need_tool("ffprobe")
    # One analysis pass; the same result feeds the verdict and the table.
    rec = mod.analyze(a.file, a.target_lufs, a.ceiling_dbtp)
    gate(rec, mod, cleaned=a.cleaned or looks_cleaned(a.file))


if __name__ == "__main__":
    main()

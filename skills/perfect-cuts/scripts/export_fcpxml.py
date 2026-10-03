#!/usr/bin/env python3
"""Generate a gapless FCPXML timeline from a cut list — for Final Cut Pro.

Final Cut Pro does NOT import the FCP7 XML that export_fcp7.py writes (that
format is for Premiere and Resolve), and it has no EDL import at all. This is
the Final Cut path: File > Import > XML.

Usage:
    python3 export_fcpxml.py cuts.json [/abs/output.fcpxml]

(Output path may also come from cuts.json's "output" key, as in export_fcp7.py.)

cuts.json:
{
  "source": "/abs/path/clip.mov",
  "fps": 60.0, "width": 1280, "height": 720, "samplerate": 48000,
  "source_duration": 60.0,          // or "source_frames": 3600
  "sequence_name": "clip perfect cut",
  "output": "/abs/out.fcpxml",
  "clips": [{"in_frame": 491, "out_frame": 584, "text": "..."}, ...]
}

Optional second camera (two-camera interviews):

  "angles": {
    "guest": {"source": "/abs/guest-camera.mov", "fps": 60.0,
               "width": 1280, "height": 720,
               "offset_frames": 13429,      // angle frame 0 sits at this ANGLE-fps
                                            // frame count into the master
               "source_frames": 139114}     // or "source_duration"
  }

and a clip may carry "angle": "guest". The primary storyline stays the master
(its audio is always the audio). An angle clip gets a connected asset-clip on
lane 1 with srcEnable="video", covering exactly the same span. Delete or trim
that connected clip in Final Cut to fall back to the master's picture. A clip
whose span falls outside the angle's recording stays on the master and is
counted in the report.

Clips are laid back-to-back from offset 0 — zero gap space by construction.

Time in FCPXML is rational (frames x frameDuration), never decimal seconds, so
NTSC rates stay exact: at 29.97 one frame is 1001/30000s, and frame N is
N*1001/30000s. Rounding to decimal seconds here is what makes third-party
FCPXML land a frame off; don't "simplify" it.

Output validates against Apple's FCPXMLv1_9.dtd, which ships inside Final Cut
Pro at Contents/Frameworks/Interchange.framework/Versions/A/Resources/.
"""
import json
import math
import sys
import urllib.parse
from xml.sax.saxutils import quoteattr

FCPXML_VERSION = "1.9"   # FCP 10.4.9 through 11.x all import this

# NTSC rates carry a 1001/1000 pulldown; everything else is exactly 1/fps.
NTSC = {23.976: 24000, 29.97: 30000, 59.94: 60000}

# Sequence audioRate uses FCP's shorthand; asset audioRate uses plain Hz.
AUDIO_RATE = {32000: "32k", 44100: "44.1k", 48000: "48k",
              88200: "88.2k", 96000: "96k", 176400: "176.4k", 192000: "192k"}


def frame_duration(fps):
    """Return (numerator, denominator) of one frame in seconds."""
    for ntsc_fps, den in NTSC.items():
        if abs(fps - ntsc_fps) < 0.01:
            return 1001, den
    return 1, round(fps)


def time_str(frames, fdn, fdd):
    """Frames -> an FCPXML rational time string, reduced where it divides out."""
    num = frames * fdn
    if num == 0:
        return "0s"
    if num % fdd == 0:
        return f"{num // fdd}s"
    g = math.gcd(num, fdd)
    return f"{num // g}/{fdd // g}s"


def clip_name(text, index):
    """Readable name in the FCP timeline: the opening words of the line."""
    words = " ".join(text.split())
    if not words:
        return f"clip {index}"
    return words[:40].rstrip() + ("..." if len(words) > 40 else "")


def main():
    spec = json.load(open(sys.argv[1]))
    out = sys.argv[2] if len(sys.argv) > 2 else spec["output"]

    src = spec["source"]
    fps = spec["fps"]
    fdn, fdd = frame_duration(fps)
    w, h = spec["width"], spec["height"]
    sr = spec.get("samplerate", 48000)
    src_name = src.rsplit("/", 1)[-1]
    stem = src_name.rsplit(".", 1)[0]
    seq_name = spec.get("sequence_name", f"{stem} perfect cut")
    colorspace = spec.get("colorspace", "1-1-1 (Rec. 709)")
    pathurl = "file://" + urllib.parse.quote(src)
    src_frames = (spec.get("source_frames", 0)
                  or int(math.floor(spec.get("source_duration", 0) * fps)))

    def t(frames):
        return time_str(frames, fdn, fdd)

    # --- optional extra camera angles -------------------------------------
    angles = {}
    for key, a in (spec.get("angles") or {}).items():
        afps = a["fps"]
        afdn, afdd = frame_duration(afps)
        aframes = (a.get("source_frames", 0)
                   or int(math.floor(a.get("source_duration", 0) * afps)))
        angles[key] = dict(a, fdn=afdn, fdd=afdd, frames=aframes,
                           rid=f"r{10 + len(angles) * 2}",
                           fid=f"r{11 + len(angles) * 2}",
                           stem=a["source"].rsplit("/", 1)[-1].rsplit(".", 1)[0])

    clips, timeline, clamped, off_angle = [], 0, 0, 0
    for n, c in enumerate(spec["clips"], 1):
        in_f = max(0, int(c["in_frame"]))
        out_f = int(c["out_frame"])
        # FCP rejects a clip that runs past the end of its media. The "+1 frame
        # out" rule can push the final clip one frame past the last, so clamp.
        if src_frames and out_f > src_frames:
            out_f = src_frames
            clamped += 1
        dur = out_f - in_f
        if dur <= 0:
            continue
        name = clip_name(c.get("text", ""), n)
        ang = angles.get(c.get("angle") or "")
        inner = ""
        if ang:
            # master frames -> angle frames, then subtract the angle's offset
            a_in = round(in_f * ang["fps"] / fps) - int(ang["offset_frames"])
            a_dur = round(dur * ang["fps"] / fps)
            if a_in < 0 or (ang["frames"] and a_in + a_dur > ang["frames"]):
                off_angle += 1
            else:
                at = lambda fr: time_str(fr, ang["fdn"], ang["fdd"])
                # Three guards against the angle's audio leaking in: the asset is
                # declared video-only (hasAudio="0"), the clip is srcEnable="video",
                # and its volume is floored. FCP 12.3 ignored srcEnable alone on a
                # real import and played the second camera's damaged track.
                inner = (
                    f'\n                <asset-clip ref="{ang["rid"]}" lane="1" offset="{t(in_f)}" '
                    f'name={quoteattr(ang["stem"] + " | " + name)} start="{at(a_in)}" '
                    f'duration="{at(a_dur)}" format="{ang["fid"]}" tcFormat="NDF" '
                    f'srcEnable="video">\n'
                    f'                    <adjust-volume amount="-96dB"/>\n'
                    f'                </asset-clip>\n            ')
        if inner:
            clips.append(
                f'            <asset-clip ref="r2" offset="{t(timeline)}" '
                f'name={quoteattr(name)} start="{t(in_f)}" duration="{t(dur)}" '
                f'format="r1" tcFormat="NDF" audioRole="dialogue">{inner}</asset-clip>')
        else:
            clips.append(
                f'            <asset-clip ref="r2" offset="{t(timeline)}" '
                f'name={quoteattr(name)} start="{t(in_f)}" duration="{t(dur)}" '
                f'format="r1" tcFormat="NDF" audioRole="dialogue"/>')
        timeline += dur

    audio_rate = AUDIO_RATE.get(sr, "48k")
    angle_res = ""
    for ang in angles.values():
        apath = "file://" + urllib.parse.quote(ang["source"])
        adur = time_str(ang["frames"], ang["fdn"], ang["fdd"])
        angle_res += (
            f'    <format id="{ang["fid"]}" frameDuration="{ang["fdn"]}/{ang["fdd"]}s" '
            f'width="{ang["width"]}" height="{ang["height"]}" colorSpace={quoteattr(colorspace)}/>\n'
            f'    <asset id="{ang["rid"]}" name={quoteattr(ang["stem"])} start="0s" duration="{adur}" '
            f'hasVideo="1" hasAudio="0" format="{ang["fid"]}">\n'
            f'      <media-rep kind="original-media" src={quoteattr(apath)}/>\n'
            f'    </asset>\n')
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE fcpxml>
<fcpxml version="{FCPXML_VERSION}">
  <resources>
    <format id="r1" frameDuration="{fdn}/{fdd}s" width="{w}" height="{h}" colorSpace={quoteattr(colorspace)}/>
    <asset id="r2" name={quoteattr(stem)} start="0s" duration="{t(src_frames)}" hasVideo="1" hasAudio="1" format="r1" audioSources="1" audioChannels="2" audioRate="{sr}">
      <media-rep kind="original-media" src={quoteattr(pathurl)}/>
    </asset>
{angle_res}  </resources>
  <library>
    <event name="Perfect Cuts">
      <project name={quoteattr(seq_name)}>
        <sequence format="r1" duration="{t(timeline)}" tcStart="0s" tcFormat="NDF" audioLayout="stereo" audioRate="{audio_rate}">
          <spine>
{chr(10).join(clips)}
          </spine>
        </sequence>
      </project>
    </event>
  </library>
</fcpxml>
"""
    open(out, "w", encoding="utf-8").write(xml)
    if clamped:
        print(f"clamped {clamped} clip(s) to the last source frame ({src_frames})")
    if off_angle:
        print(f"{off_angle} clip(s) asked for an angle outside its recording; kept on the master")
    n_ang = sum(1 for c in clips if 'lane="1"' in c)
    if angles:
        print(f"{n_ang} clip(s) carry a connected second-camera clip (srcEnable=video)")
    print(f"{len(clips)} clips, {timeline / fps:.2f}s -> {out}")


if __name__ == "__main__":
    main()

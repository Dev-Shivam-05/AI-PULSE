"""
v3-L live preflight — can THIS machine sustain a YouTube live encode, with the
settings YouTube recommends, before anyone goes live?

    py -3 scripts/live_preflight.py                    # 20 s test pattern, 1080p30
    py -3 scripts/live_preflight.py --profile 720p30
    py -3 scripts/live_preflight.py --source desktop   # real screen capture (ddagrab)

What it does, and deliberately does NOT do:
  * encodes N seconds to a LOCAL .flv in temp/live/ (gitignored) — FLV because it
    is the container RTMP carries, so the probe sees what the ingest would see;
  * reports the encoder's speed (must stay >= 1.0x or the stream stalls) and the
    dropped-frame count;
  * probes the file and checks resolution, frame rate, codec, the 2 s keyframe
    interval and the audio format against docs/spec/ai-pulse-v3l.md §5;
  * it NEVER connects to YouTube and never reads a stream key. Going live is done
    in OBS (installed) with the same numbers, by the owner, after approval.

`--source desktop` records whatever is on screen into temp/live/ — close anything
private first. The test pattern (default) records nothing personal.

Stdlib only: tests import this module on the CI test job, which installs no
media packages (see CLAUDE.md, "Importing ai_pipeline pulls in the whole package").
"""
import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "temp" / "live"

# Every number below is copied from YouTube's "Choose live encoder settings,
# bitrates, and resolutions" (support.google.com/youtube/answer/2853702,
# read 2026-10-01) — see spec §5. Change them there first, then here.
PROFILES = {
    "1080p30": {"w": 1920, "h": 1080, "fps": 30, "kbps": 14000},   # recommended 14 Mbps
    "720p30": {"w": 1280, "h": 720, "fps": 30, "kbps": 8000},      # recommended 8 Mbps
}
KEYFRAME_S = 2            # "Recommended 2 seconds … Do not exceed 4 seconds"
KEYFRAME_MAX_S = 4
AUDIO_KBPS = 128          # "128 Kbps for stereo"
AUDIO_HZ = 44100          # "44.1 KHz for stereo audio"
# x264 "veryfast" is OBS's default x264 preset, so the preflight measures the
# same CPU cost the owner will pay when streaming from OBS.
X264_PRESET = "veryfast"
DEFAULT_SECONDS = 20


def source_args(source: str, p: dict) -> list:
    """ffmpeg input arguments for the video + audio source."""
    size = f"{p['w']}x{p['h']}"
    if source == "desktop":
        # ddagrab = the Desktop Duplication API, the capture path OBS's Display
        # Capture uses. gdigrab (GDI) was measured first and is NOT a stand-in:
        # on this laptop it delivered ~20 of 30 fps at 1080p (102 duplicated
        # frames in 10 s) while ddagrab delivered 300/300 on the same screen.
        # Scaled to the profile so a 720p preflight works on a 1080p desktop.
        video = ["-f", "lavfi", "-i",
                 f"ddagrab=framerate={p['fps']},hwdownload,format=bgra,"
                 f"scale={p['w']}:{p['h']}"]
    elif source == "pattern":
        video = ["-f", "lavfi", "-i", f"testsrc2=size={size}:rate={p['fps']}"]
    else:
        raise ValueError(f"unknown source: {source}")
    audio = ["-f", "lavfi", "-i", f"sine=frequency=440:sample_rate={AUDIO_HZ}"]
    return video + audio


def encode_args(profile: str, source: str, seconds: int, out: str,
                ffmpeg: str = "ffmpeg") -> list:
    """The full ffmpeg command. Pure, so the settings are asserted in tests."""
    p = PROFILES[profile]
    gop = p["fps"] * KEYFRAME_S
    kbps = f"{p['kbps']}k"
    return [
        ffmpeg, "-hide_banner", "-nostats", "-y",
        *source_args(source, p),
        "-t", str(seconds),
        "-map", "0:v", "-map", "1:a",
        "-c:v", "libx264", "-preset", X264_PRESET, "-profile:v", "high",
        "-pix_fmt", "yuv420p", "-r", str(p["fps"]),
        # Fixed GOP with scene-cut keyframes off: YouTube's ingest wants a key
        # frame every 2 s exactly, and x264 would otherwise insert extra ones.
        "-g", str(gop), "-keyint_min", str(gop), "-sc_threshold", "0",
        # CBR: equal min/max rate and a one-second buffer — the shape a live
        # ingest expects (a VBR spike is a stall on a fixed uplink).
        "-b:v", kbps, "-minrate", kbps, "-maxrate", kbps, "-bufsize", kbps,
        "-c:a", "aac", "-b:a", f"{AUDIO_KBPS}k", "-ar", str(AUDIO_HZ), "-ac", "2",
        "-progress", "pipe:1",
        "-f", "flv", out,
    ]


def probe_args(path: str, ffprobe: str = "ffprobe") -> list:
    return [ffprobe, "-v", "error", "-print_format", "json",
            "-show_streams", "-show_entries",
            "packet=pts_time,flags,stream_index", path]


def parse_progress(text: str) -> dict:
    """Last values of ffmpeg's `-progress` key=value blocks."""
    out = {}
    for line in text.splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip()
    speed = out.get("speed", "").rstrip("x")
    try:
        sp = float(speed)
    except ValueError:
        sp = None
    counts = {}
    for key in ("drop_frames", "dup_frames"):
        try:
            counts[key] = int(out.get(key, "0"))
        except ValueError:
            counts[key] = None
    return {"speed": sp, **counts}


def keyframe_gaps(packets: list, video_index: int) -> list:
    """Seconds between consecutive video key frames."""
    times = []
    for pk in packets:
        if pk.get("stream_index") != video_index or "K" not in pk.get("flags", ""):
            continue
        try:
            times.append(float(pk["pts_time"]))
        except (KeyError, TypeError, ValueError):
            continue
    times.sort()
    return [round(b - a, 3) for a, b in zip(times, times[1:])]


def evaluate(probe: dict, progress: dict, profile: str, source: str = "pattern") -> list:
    """[(check, ok, observed)] — every check named after a spec §5 row."""
    p = PROFILES[profile]
    streams = probe.get("streams") or []
    v = next((s for s in streams if s.get("codec_type") == "video"), {})
    a = next((s for s in streams if s.get("codec_type") == "audio"), {})
    gaps = keyframe_gaps(probe.get("packets") or [], v.get("index", 0))
    # every full GOP must be 2 s; the last gap can be short when -t cuts it
    full = gaps[:-1] if len(gaps) > 1 else gaps
    speed = progress.get("speed")
    drops, dups = progress.get("drop_frames"), progress.get("dup_frames")
    if source == "pattern":
        # a generated source runs as fast as the encoder allows, so speed IS
        # the headroom: below 1.0x a live encode falls behind and stalls
        pace = ("encoder speed >= 1.0x", speed is not None and speed >= 1.0, f"{speed}x")
    else:
        # a capture source is clamped to real time (ffmpeg reports ~0.97x from
        # start-up alone), so falling behind shows up as frames ffmpeg had to
        # duplicate or drop to hold 30 fps — not as speed. Up to one second of
        # duplicates is start-up (ddagrab repeats until the first screen
        # change: 3 were measured); more than that is a capture that can't keep up.
        pace = (f"duplicated frames <= {p['fps']}", dups is not None and dups <= p["fps"], dups)
    return [
        ("resolution", (v.get("width"), v.get("height")) == (p["w"], p["h"]),
         f"{v.get('width')}x{v.get('height')}"),
        ("frame rate", v.get("r_frame_rate") == f"{p['fps']}/1", v.get("r_frame_rate")),
        ("video codec", v.get("codec_name") == "h264", v.get("codec_name")),
        ("keyframe interval", bool(full) and all(abs(g - KEYFRAME_S) < 0.05 for g in full)
         and max(gaps) <= KEYFRAME_MAX_S, f"{sorted(set(gaps))} s"),
        ("audio codec", a.get("codec_name") == "aac", a.get("codec_name")),
        ("audio sample rate", a.get("sample_rate") == str(AUDIO_HZ), a.get("sample_rate")),
        ("audio channels", a.get("channels") == 2, a.get("channels")),
        pace,
        ("dropped frames", drops == 0, drops),
    ]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--profile", choices=sorted(PROFILES), default="1080p30")
    ap.add_argument("--source", choices=["pattern", "desktop"], default="pattern")
    ap.add_argument("--seconds", type=int, default=DEFAULT_SECONDS)
    a = ap.parse_args(argv)
    if not 5 <= a.seconds <= 120:
        print("--seconds must be 5..120 (a preflight, not a stream)")
        return 2
    ffmpeg, ffprobe = shutil.which("ffmpeg"), shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        print("ffmpeg/ffprobe not on PATH")
        return 2
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"preflight_{a.profile}_{a.source}.flv"
    cmd = encode_args(a.profile, a.source, a.seconds, str(out), ffmpeg)
    run = subprocess.run(cmd, capture_output=True, text=True, timeout=a.seconds * 10)
    if run.returncode != 0:
        print("ffmpeg failed:\n" + run.stderr[-2000:])
        return 1
    progress = parse_progress(run.stdout)
    pr = subprocess.run(probe_args(str(out), ffprobe), capture_output=True,
                        text=True, timeout=120)
    if pr.returncode != 0:
        print("ffprobe failed:\n" + pr.stderr[-2000:])
        return 1
    results = evaluate(json.loads(pr.stdout), progress, a.profile, a.source)
    print(f"live preflight · {a.profile} · source={a.source} · {a.seconds}s → {out}")
    for name, ok, seen in results:
        print(f"  {'PASS' if ok else 'FAIL'}  {name:<22} {seen}")
    failed = [n for n, ok, _ in results if not ok]
    print("RESULT:", "ready" if not failed else "NOT ready — " + ", ".join(failed))
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())

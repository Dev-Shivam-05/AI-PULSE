"""
v3-N.1 node preflight: can THIS machine stream, and with which profile?
(docs/spec/ai-pulse-v3n1.md section 5)

    py -3 node/node_preflight.py --data C:\\ToolDojo\\data     # the supervisor runs this once
    py -3 node/node_preflight.py --data temp/node_pf --seconds 10   # a sanity run elsewhere

It measures, from inside whatever context runs it (the supervisor runs it inside the
scheduled task, session 0, because GPU / Quick Sync can behave differently there):

  1. RAM: total and available, before and while headless Chromium is open;
  2. Chromium: the cost of one 1920x1080 screenshot of the real radar page;
  3. the encoders: `radar_live.segment_args` - the EXACT production command - for
     1080p30 / 720p30 x libx264 / h264_qsv, fed with those real board frames (mostly
     static, like the stream), timed, then probed for 2 s keyframes and H.264.

Then it picks the first profile in AUTO_ORDER whose producer cost fits the budget and
writes it to <data>/node.local.json, which the supervisor hands to stream jobs.

Heavy imports (playwright, radar_live) happen inside functions, so the pure selection
logic imports on the CI test job.
"""
from __future__ import annotations

import argparse
import ctypes
import json
import os
import platform
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

APP = Path(__file__).resolve().parent.parent
# Spec rows 9-10. Lowest load first: Quick Sync runs on the GPU, so it is tried before
# any CPU encode. 1080p30 x264 is measured (for the report) but never auto-picked on the
# node: it is the heaviest option and requirement 2 is the lowest possible load.
AUTO_ORDER = [("1080p30", "h264_qsv"), ("720p30", "h264_qsv"), ("720p30", "libx264")]
MEASURED = AUTO_ORDER + [("1080p30", "libx264")]
# Producer seconds of work per second of video must stay under this. The remaining 20 %
# is for edge-tts, the LLM call, the remux and the sender ffmpeg sharing the same CPU.
BUDGET = 0.80
# radar row 18: a screenshot every whole second plus one per caption phrase start
# (<= 6 words at ~2.5 words/s, i.e. ~0.4/s): 1.4/s, rounded up.
SHOTS_PER_VIDEO_SECOND = 1.5
RAM_MIN_AVAILABLE_MB = 1024    # free while Chromium is open: room for 2 ffmpeg + producer
SHOTS = 20
DEFAULT_SECONDS = 20


def memory_mb() -> dict:
    """{'total': MB, 'available': MB} via GlobalMemoryStatusEx; {} off Windows."""
    if os.name != "nt":
        return {}

    class MS(ctypes.Structure):
        _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
    try:
        m = MS()
        m.dwLength = ctypes.sizeof(MS)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
        return {"total": round(m.ullTotalPhys / 2**20), "available": round(m.ullAvailPhys / 2**20)}
    except Exception:  # noqa: BLE001
        return {}


def cpu_name() -> str:
    if os.name == "nt":
        try:
            import winreg
            k = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                               r"HARDWARE\DESCRIPTION\System\CentralProcessor\0")
            return str(winreg.QueryValueEx(k, "ProcessorNameString")[0]).strip()
        except OSError:
            pass
    return platform.processor() or "unknown"


def producer_cost(render_ms: float | None, speed: float | None,
                  shots_per_s: float = SHOTS_PER_VIDEO_SECOND) -> float | None:
    """Wall seconds the producer spends per second of video: screenshots + encode.
    The radar renders and encodes one segment after the other on one process."""
    if not speed or speed <= 0 or render_ms is None:
        return None
    return round(render_ms / 1000.0 * shots_per_s + 1.0 / speed, 3)


def select_profile(results: list, render_ms: float | None, avail_mb: float | None,
                   order=AUTO_ORDER, budget: float = BUDGET,
                   ram_min: float = RAM_MIN_AVAILABLE_MB) -> dict:
    """The first candidate in `order` that encoded correctly and fits the budget.
    `results` rows: {"profile", "encoder", "ok", "speed", "error"}."""
    if render_ms is None:
        return {"stream_profile": "insufficient", "encoder": "",
                "verdict": "headless Chromium did not render the board"}
    if avail_mb is not None and avail_mb < ram_min:
        return {"stream_profile": "insufficient", "encoder": "",
                "verdict": f"only {avail_mb:.0f} MB RAM available with Chromium open "
                           f"(needs {ram_min} MB)"}
    by = {(r.get("profile"), r.get("encoder")): r for r in results}
    notes = []
    for prof, enc in order:
        r = by.get((prof, enc))
        if not r:
            continue
        if not r.get("ok"):
            notes.append(f"{prof} {enc}: {r.get('error') or 'failed'}")
            continue
        cost = producer_cost(render_ms, r.get("speed"))
        if cost is not None and cost <= budget:
            return {"stream_profile": prof, "encoder": enc, "producer_cost": cost,
                    "verdict": f"{prof} {enc}: producer cost {cost:.2f} s per video second "
                               f"(budget {budget}); encode {r.get('speed')}x, "
                               f"screenshot {render_ms:.0f} ms"}
        notes.append(f"{prof} {enc}: cost {cost} > {budget}")
    return {"stream_profile": "insufficient", "encoder": "",
            "verdict": "no profile fits: " + "; ".join(notes)}


def render_frames(out_dir: Path, n: int = SHOTS) -> tuple:
    """([png paths], mean ms per screenshot, available MB while open) - fail-soft."""
    out_dir.mkdir(parents=True, exist_ok=True)
    page_path = APP / "assets" / "radar" / "radar.html"
    try:
        from playwright.sync_api import sync_playwright   # heavy, optional: import here
        with sync_playwright() as pw:
            browser = pw.chromium.launch()      # headless (Playwright's default)
            page = browser.new_page(viewport={"width": 1920, "height": 1080},
                                    device_scale_factor=1)
            page.goto(page_path.resolve().as_uri())
            page.wait_for_function("window.__ready === true", timeout=30000)
            shots, times = [], []
            for i in range(n):
                p = out_dir / f"{i:05d}.png"
                t0 = time.perf_counter()
                page.screenshot(path=str(p))
                times.append((time.perf_counter() - t0) * 1000)
                shots.append(p)
            avail = memory_mb().get("available")
            browser.close()
        # the first shot pays for the first paint; it is not the steady-state cost
        steady = times[1:] or times
        return shots, round(sum(steady) / len(steady), 1), avail, ""
    except Exception as e:  # noqa: BLE001
        return [], None, memory_mb().get("available"), f"{type(e).__name__}: {str(e)[:200]}"


def measure_encode(shots: list, profile: str, encoder: str, seconds: int, work: Path,
                   ffmpeg: str, ffprobe: str) -> dict:
    """One production segment encode (radar_live.segment_args) of real board frames."""
    sys.path[:0] = [str(APP), str(APP / "scripts")]
    import live_preflight as lp                  # stdlib only
    import radar_live as rl                      # pulls factverse.config + radar (requests)
    from factverse import storyboard
    row = {"profile": profile, "encoder": encoder, "ok": False, "speed": None, "error": ""}
    lst = work / f"list_{profile}_{encoder}.txt"
    frames = [(str(p), float(i)) for i, p in enumerate(shots[:seconds])]
    while len(frames) < seconds:             # hold the last board, as a long phrase would
        frames.append((frames[-1][0], float(len(frames))))
    lst.write_text(storyboard.concat_list(frames, seconds), encoding="utf-8")
    out = work / f"seg_{profile}_{encoder}.ts"
    cmd = rl.segment_args(str(lst), None, seconds, str(out), ffmpeg,
                          encoder=encoder, profile=profile)
    t0 = time.perf_counter()
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=seconds * 20)
    except subprocess.TimeoutExpired:
        row["error"] = "encode timed out"
        return row
    wall = time.perf_counter() - t0
    if r.returncode != 0 or not out.exists():
        row["error"] = (r.stderr or "").strip().splitlines()[-1][:200] if r.stderr else "failed"
        return row
    row["speed"] = round(seconds / wall, 2) if wall > 0 else None
    row["wall_s"] = round(wall, 2)
    pr = subprocess.run(lp.probe_args(str(out), ffprobe), capture_output=True, text=True,
                        timeout=120)
    try:
        probe = json.loads(pr.stdout)
    except ValueError:
        row["error"] = "ffprobe failed"
        return row
    checks = {n: ok for n, ok, _ in lp.evaluate(probe, {"speed": row["speed"], "drop_frames": 0,
                                                         "dup_frames": 0}, profile)}
    bad = [n for n in ("resolution", "frame rate", "video codec", "keyframe interval")
           if not checks.get(n)]
    row["ok"] = not bad
    row["error"] = ("failed checks: " + ", ".join(bad)) if bad else ""
    return row


def run(data: Path, seconds: int = DEFAULT_SECONDS) -> dict:
    work = APP / "temp" / "node_preflight"
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True, exist_ok=True)
    ffmpeg = os.environ.get("FFMPEG_BIN") or shutil.which("ffmpeg") or "ffmpeg"
    ffprobe = os.environ.get("FFPROBE_BIN") or shutil.which("ffprobe") or "ffprobe"
    report = {"measured_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
              "host": {"cpu": cpu_name(), "logical_cpus": os.cpu_count(),
                       "ram_mb": memory_mb(), "session": os.environ.get("SESSIONNAME", "")},
              "results": []}
    shots, render_ms, avail, err = render_frames(work / "frames")
    report.update({"render_ms": render_ms, "available_mb_with_chromium": avail,
                   "chromium_error": err})
    if shots:
        for prof, enc in MEASURED:
            try:
                report["results"].append(measure_encode(shots, prof, enc, seconds, work,
                                                        ffmpeg, ffprobe))
            except Exception as e:  # noqa: BLE001 - one encoder failing is a result
                report["results"].append({"profile": prof, "encoder": enc, "ok": False,
                                          "speed": None, "error": f"{type(e).__name__}: {e}"})
    for r in report["results"]:
        r["producer_cost"] = producer_cost(render_ms, r.get("speed")) if r.get("ok") else None
    report.update(select_profile(report["results"], render_ms, avail))
    data.mkdir(parents=True, exist_ok=True)
    (data / "node.local.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    (data / "preflight_report.txt").write_text(format_report(report), encoding="utf-8")
    shutil.rmtree(work, ignore_errors=True)
    return report


def format_report(r: dict) -> str:
    lines = [f"ToolDojo Node preflight - {r.get('measured_at')}",
             f"CPU: {r['host'].get('cpu')} ({r['host'].get('logical_cpus')} logical)",
             f"RAM: {r['host'].get('ram_mb')} ; available with Chromium open: "
             f"{r.get('available_mb_with_chromium')} MB",
             f"Chromium 1920x1080 screenshot: {r.get('render_ms')} ms"
             + (f"  ERROR {r['chromium_error']}" if r.get("chromium_error") else ""),
             "Encodes (real board frames, the production segment command):"]
    for x in r.get("results", []):
        lines.append(f"  {x['profile']:<8} {x['encoder']:<9} "
                     + (f"{x['speed']}x  producer cost {x.get('producer_cost')} s/s"
                        if x.get("ok") else f"FAILED {x.get('error')}"))
    lines += [f"SELECTED: {r.get('stream_profile')} {r.get('encoder')}",
              f"VERDICT: {r.get('verdict')}"]
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="ToolDojo Node preflight (v3-N.1)")
    ap.add_argument("--data", required=True)
    ap.add_argument("--seconds", type=int, default=DEFAULT_SECONDS)
    a = ap.parse_args(argv)
    if not 6 <= a.seconds <= 60 or a.seconds % 2:
        print("--seconds must be an even number 6..60")
        return 2
    r = run(Path(a.data).resolve(), a.seconds)
    try:
        print(format_report(r).encode("ascii", "replace").decode("ascii"))
    except Exception:  # noqa: BLE001 - pythonw has no stdout
        pass
    return 0 if r.get("stream_profile") != "insufficient" else 1


if __name__ == "__main__":
    sys.exit(main())

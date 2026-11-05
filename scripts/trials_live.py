"""
v3-T.1 ToolDojo Live Trials - the unattended 12-minute vertical live show
(docs/spec/ai-pulse-v3t1.md).

    py -3 scripts/trials_live.py --minutes 12 --start-at 18:45     # the node job (Saturdays)
    py -3 scripts/trials_live.py --out rtmp://127.0.0.1:1935/live/t1  # local verification
    py -3 scripts/trials_live.py --dry-run                         # plan + preflight + all branches, no stream

One named tool, four committed fixtures, its OWN hosted demo (no candidate code runs
here), deterministic checks, prepared narration in four outcome branches, and a
12-minute grid that never changes. A producer PROCESS plans the episode, runs the
preflight, writes and voices every branch, then (once on air) runs each test during
the broadcast and renders the window that shows it. The main process streams it
through scripts/radar_live.py's single connection (imported, not forked): remux onto
one timeline, `ffmpeg -re`, reconnect, key redaction, *.youtube.com-only ingest.

Unattended rules (CLAUDE.md): nothing raises out of main(); the stream key never
reaches a log line; no window, no click; the show ends cleanly.
"""
import argparse
import json
import multiprocessing as mp
import os
import queue
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from factverse import config as fv           # noqa: E402
from factverse import radar as rd            # noqa: E402
from factverse import trials as tr           # noqa: E402
import radar_live as rl                      # noqa: E402

W, H, FPS = 1080, 1920, rl.FPS               # row 6: vertical 1080x1920
PAGE = fv.ASSETS / "trials" / "trials.html"
# R3 §2's fixed 12-minute grid, in seconds. Every length is even (2 s GOPs tile it).
GRID = (("open", 30), ("rules", 30), ("result1", 30),
        ("run2", 90), ("result2", 30), ("run3", 90), ("result3", 30),
        ("run4", 90), ("result4", 30), ("repeat", 90),
        ("verdict", 60), ("files", 60), ("limits", 60))
QUEUE_DEPTH = 2         # producer lead, in segments
PREROLL = 2             # "open" + "rules" are ready before the connection opens
# A late window is covered by a silent hold, never a gap. 10 s like radar's standby:
# a 2 s hold cost ~3.5 s to remux and send, so the first local session sank behind
# real time while it repeated them.
HOLD_SECONDS = 10
MAX_HOLD_SECONDS = 120  # more hold than this and the show ends (the producer stalled)
HOLD_MARGIN = 4.0       # seconds of stream left in the pipe before a hold is sent
PREP_TIMEOUT = 25 * 60  # planning + preflight + every voice + the first renders
OVERRUN = 300           # wall-clock backstop after the grid
PHRASE_WORDS = 5        # captions at 64 px hold 2 lines
CAP_HOLD = 0.6          # trials.html's CAP_HOLD: a caption stays this long past its phrase
# #vbox inside #ev (trials.html); even sides for yuv420p. Recordings are always
# REC_W x REC_H (1280x720), so the scale is exact: no pad (a 405-high pad failed
# on rounding and cost the first local session every capture window).
CAP_W, CAP_H, CAP_X, CAP_Y = 720, 404, 180, 512
RESULT_REPLAY_MAX = 12.0  # a result window replays at most this much of the run
STREAM_ENV = ("YT_TRIALS_STREAM_URL", "YT_TRIALS_STREAM_KEY")
VOICE_WORKERS = 4
HEARTBEAT_SECONDS = 60  # the node supervisor kills a job silent for 300 s
# Windows: no console window for any child (the node runs jobs invisibly)
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def out_profile(env=None) -> dict:
    """The delivered size and bitrate. The page is always rendered at 1080x1920 (its
    64/80/96 px floors are measured there); `TOOLDOJO_STREAM_PROFILE=720p30` (the
    node's choice on a weak CPU) scales the encode to 720x1280 at the 720p bitrate.
    Only x264 is supported; any other `TOOLDOJO_ENCODER` is logged and ignored."""
    env = os.environ if env is None else env
    name = str(env.get("TOOLDOJO_STREAM_PROFILE", "") or "").strip().lower()
    if name.startswith("720"):
        return {"name": "720p30", "w": 720, "h": 1280, "kbps": rl.lp.PROFILES["720p30"]["kbps"]}
    return {"name": "1080p30", "w": 1080, "h": 1920, "kbps": rl.lp.PROFILES["1080p30"]["kbps"]}

WORK = fv.TEMP / "trials"
LOG = fv.LOGS / "trials_live.log"
SESSIONS = fv.LOGS / "trials_sessions.jsonl"


def grid_starts() -> dict:
    out, t = {}, 0
    for wid, n in GRID:
        out[wid] = t
        t += n
    return out


GRID_LEN = dict(GRID)
STARTS = grid_starts()
assert sum(GRID_LEN.values()) == tr.SHOW_MINUTES * 60


def log(msg: str) -> None:
    line = f"{datetime.now(timezone.utc):%Y-%m-%d %H:%M:%S}Z {rl.redact(msg)}"
    try:
        print(line.encode("ascii", "replace").decode("ascii"), flush=True)
    except Exception:  # noqa: BLE001
        pass
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with LOG.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:  # noqa: BLE001
        pass


# ================================================================== pure helpers
def hhmmss(iso: str) -> str:
    d = tr._slot_dt(iso)
    return f"{d:%H:%M:%S} UTC" if d else ""


def window_kind(wid: str) -> str:
    return wid.rstrip("0123456789")


def test_index(wid: str) -> int | None:
    """0-based test index a window shows, or None."""
    k = wid.rstrip("0123456789")
    return int(wid[len(k):]) - 1 if wid[len(k):] else None


def skipped_windows(results: dict) -> set:
    """Windows the "test incomplete" ending removes: after two CONSECUTIVE execution
    failures (R2), every run/result window that has no executed test is dropped and the
    show goes to the verdict. `results` is {index: result} for the tests that ran."""
    ran = [results[i] for i in sorted(results) if i < 4]
    if not tr.incomplete(ran):
        return set()
    last = max(results)
    out = {w for w, _ in GRID if window_kind(w) in ("run", "result") and test_index(w) > last}
    out.add("repeat")
    return out


def run_at(index: int) -> float:
    """Seconds after air when test `index` may start: at most RUN_LEAD_SECONDS before
    the window that first shows it (result1 for the fresh baseline, runK otherwise)."""
    wid = "result1" if index == 0 else f"run{index + 1}" if index < 4 else "repeat"
    return max(0.0, STARTS[wid] - tr.RUN_LEAD_SECONDS)


def top_score(results: list) -> str:
    t = tr.tally(results)
    return f"SCORE {t['passed']}/{2 * len(results)}" if results else ""


def tokens_of(r: dict) -> list:
    """The tool's OWN words (its casing and punctuation), each marked by the
    word-level comparison (trials.raw_marks)."""
    m = next((c.get("marks") for c in (r or {}).get("checks") or [] if c.get("marks")), None)
    return [[w, k] for w, k in tr.raw_marks((r or {}).get("transcript", ""), m)] if m else []


def status_lines(r: dict) -> list:
    """What the output card says when there is no transcript to show."""
    b = (r or {}).get("branch")
    if b == "TIMEOUT":
        return [{"text": f"NO RESULT IN {tr.RUN_SECONDS:.0f} S", "cls": "yel"},
                {"text": "TEST WINDOW EXPIRED", "cls": "sub"}]
    if b == "PARTIAL_FAIL" and not (r or {}).get("transcript"):
        return [{"text": "THE TOOL RETURNED", "cls": "yel"}, {"text": "AN ERROR", "cls": "yel"}]
    if (r or {}).get("transcript") == "" and b == "PARTIAL_FAIL":
        return [{"text": "EMPTY TRANSCRIPT", "cls": "yel"}]
    return [{"text": "COULD NOT VERIFY", "cls": "yel"}, {"text": "THE OUTPUT", "cls": "yel"}]


def check_rows(r: dict, at0: float) -> list:
    rows = []
    for i, c in enumerate((r or {}).get("checks") or []):
        st = "pass" if c.get("ok") is True else "fail" if c.get("ok") is False else "na"
        text = (f"KEY WORDS {c['value']}" if c["id"] == "terms"
                else f"ERRORS {c.get('errors')} · MAX {c.get('max')}" if c.get("errors") is not None
                else "WORD ERRORS ?")
        if c.get("value") == "not run":
            text = "KEY WORDS NOT RUN" if c["id"] == "terms" else "ERRORS NOT RUN"
        rows.append({"text": text, "state": st, "at": round(at0 + 2 * i, 3),
                     "pending": "KEY WORDS" if c["id"] == "terms" else "WORD ERRORS"})
    return rows


def frame_times(spec: dict) -> list:
    """The only moments this page can change: the state changes and the caption edges.
    radar's every-whole-second grid exists for its moving clock; here it spent 21 of the
    38 s a 90 s window takes to render, which is what put a hold card at 1:30."""
    ts = {0.0}
    for a, b, _text in spec.get("phrases") or []:
        ts |= {float(a), float(b) + CAP_HOLD}
    ev, out, score = spec.get("ev") or {}, spec.get("out") or {}, spec.get("score") or {}
    marks = [ev.get("video_from"), ev.get("video_to"), out.get("reveal_at"),
             score.get("total_at"), spec.get("top_score_at"), *(spec.get("extra_times") or []),
             *(r.get("at") for r in score.get("rows") or [])]
    ts |= {float(x) for x in marks if x is not None}
    return sorted(round(t, 3) for t in ts if 0 <= t < spec["length"])


def base_spec(plan: dict, length: int, results: list) -> dict:
    return {"type": "trial", "length": int(length), "phrases": [],
            "disclosure": tr.DISCLOSURE, "tool": plan["tool"], "question": plan["question"],
            "question_short": plan.get("question_short", ""),
            "top_score": top_score(results), "extra_times": []}


def ref_lines(clip: dict) -> list:
    return [{"text": f"“{clip['text']}”"}]


def replay_window(r: dict, at: float, room: float) -> tuple:
    """(cut, at, shown) for the capture replay: the run's own cut (P.1 hosted_cut,
    <= 20 s), sped up further only to fit `room` seconds (never above 4x overall)."""
    cut = (r or {}).get("cut")
    if not cut or not (r or {}).get("recording") or not Path(r["recording"]).exists():
        return None, at, 0.0
    shown = float(cut["seconds"]) if float(cut["length"]) / float(cut["speed"]) >= 8.0 \
        else float(cut["length"]) / float(cut["speed"])
    shown = min(shown, float(cut["length"]) / float(cut["speed"]))
    speed = float(cut["speed"])
    if shown > room:
        speed = min(4.0, float(cut["length"]) / room)
        shown = float(cut["length"]) / speed
    if shown > room:      # still too long at 4x: keep the END (the result)
        start = float(cut["start"]) + float(cut["length"]) - room * speed
        cut = dict(cut, start=round(start, 3), length=round(room * speed, 3))
        shown = room
    return dict(cut, speed=round(speed, 4)), round(at, 3), round(shown, 3)


# ------------------------------------------------------------------ window specs (pure)
def spec_open(plan: dict, pre: dict) -> dict:
    c = plan["set"]["clips"][0]
    s = base_spec(plan, GRID_LEN["open"], [])
    s["ev"] = {"badge": tr.SOURCE_LABEL.upper(), "header": f"CLIP 1 OF 4 · {c['name'].upper()}",
               "lines": ref_lines(c)}
    s["out"] = {"header": f"PREFLIGHT RESULT · {hhmmss(pre.get('ran_at', ''))} · BEFORE THE STREAM",
                "tokens": tokens_of(pre), "lines": [] if tokens_of(pre) else status_lines(pre)}
    rows = check_rows(pre, 0.0)
    for r in rows:
        r["text"] = "PREFLIGHT " + r["text"]
    s["score"] = {"mode": "checks", "rows": rows[:1] + [{"text": "LIVE RERUN STARTING", "state": "wait"}]}
    return s


def spec_rules(plan: dict) -> dict:
    s = base_spec(plan, GRID_LEN["rules"], [])
    s["ev"] = {"badge": tr.SOURCE_LABEL.upper(), "header": "THE TEST",
               "lines": [{"text": "4 CLIPS"}, {"text": "KNOWN TRANSCRIPTS", "cls": "sub"},
                         {"text": "2 CHECKS EACH"}, {"text": f"{tr.RUN_SECONDS:.0f} S PER RUN", "cls": "sub"}]}
    s["out"] = {"header": f"CONFIGURATION · {plan['space']}",
                "lines": [{"text": "ITS OWN HF DEMO"},
                          {"text": f"{plan.get('hardware', '').upper()} · NOT A LAPTOP TEST", "cls": "sub"}]}
    s["score"] = {"mode": "checks", "rows": [{"text": "KEY WORDS HEARD", "state": "info"},
                                             {"text": "ERRORS ≤ ALLOWANCE", "state": "info"}]}
    return s


def spec_result(plan: dict, index: int, r: dict, results_so_far: list, wid: str) -> dict:
    """A 30 s result window: a short replay of the run, the marked transcript, the two
    checks ticking, then the test's branch and the running count."""
    c = plan["set"]["clips"][index]
    s = base_spec(plan, GRID_LEN[wid], results_so_far)
    cut, at, shown = replay_window(r, 0.0, RESULT_REPLAY_MAX)
    reveal = round(at + shown, 3) if cut else 0.0
    s["ev"] = {"badge": tr.SOURCE_LABEL.upper(),
               "header": f"TEST {index + 1} OF 4 · RAN {hhmmss(r.get('ran_at', ''))}",
               "lines": ref_lines(c)}
    if cut:
        s["ev"].update(video_from=at, video_to=reveal)
        s["capture"] = {"path": r["recording"], "cut": cut, "at": at, "shown": shown}
    s["out"] = {"header": f"WHAT {plan['tool'].upper()} HEARD",
                "tokens": tokens_of(r), "lines": [] if tokens_of(r) else status_lines(r),
                "reveal_at": reveal if cut else None, "pending": "REPLAYING THE RUN"}
    rows = check_rows(r, reveal + 1.0)
    t = tr.tally(results_so_far)
    total_at = round(reveal + 1.0 + 2 * len(rows) + 1.0, 3)
    s["score"] = {"mode": "total", "rows": rows, "total_at": total_at,
                  "big": tr.BRANCH_LABEL[r["branch"]],
                  "big_cls": {"PASS": "pass", "PARTIAL_FAIL": "fail"}.get(r["branch"], "na"),
                  "sub": f"TEST {index + 1} · {t['passed']}/{2 * len(results_so_far)} SO FAR"}
    s["extra_times"] = [reveal] + [x["at"] for x in rows] + [total_at]
    s["top_score_before"], s["top_score_at"] = top_score(results_so_far[:-1]), total_at
    return s


def spec_run(plan: dict, index: int, r: dict, results_before: list, speech_end: float) -> dict:
    """A 90 s run window: the clip and why it matters (narrated), then the replay of the
    run recorded earlier in this stream, then the transcript and the checks ticking."""
    c = plan["set"]["clips"][index]
    wid = f"run{index + 1}"
    s = base_spec(plan, GRID_LEN[wid], results_before)
    room = GRID_LEN[wid] - speech_end - 12.0
    cut, at, shown = replay_window(r, speech_end + 1.0, max(4.0, room))
    reveal = round(at + shown, 3) if cut else round(speech_end + 1.0, 3)
    s["ev"] = {"badge": tr.SOURCE_LABEL.upper(),
               "header": f"TEST {index + 1} OF 4 · {c['name'].upper()}", "lines": ref_lines(c)}
    if cut:
        s["ev"].update(video_from=at, video_to=reveal)
        s["capture"] = {"path": r["recording"], "cut": cut, "at": at, "shown": shown}
    s["out"] = {"header": f"RUN RECORDED {hhmmss(r.get('ran_at', ''))} · THIS STREAM",
                "tokens": tokens_of(r), "lines": [] if tokens_of(r) else status_lines(r),
                "reveal_at": reveal, "pending": "REPLAY NEXT"}
    rows = check_rows(r, reveal + 1.0)
    s["score"] = {"mode": "checks", "rows": rows}
    s["extra_times"] = [at, reveal] + [x["at"] for x in rows]
    return s


def spec_repeat(plan: dict, index: int, first: dict, r: dict, results: list,
                speech_end: float, branch_at: float) -> dict:
    c = plan["set"]["clips"][index]
    s = base_spec(plan, GRID_LEN["repeat"], results)
    room = max(4.0, branch_at - speech_end - 10.0)
    cut, at, shown = replay_window(r, speech_end + 1.0, room)
    reveal = round(at + shown, 3) if cut else round(speech_end + 1.0, 3)
    s["ev"] = {"badge": tr.SOURCE_LABEL.upper(),
               "header": f"REPEAT OF TEST {index + 1} · RAN {hhmmss(r.get('ran_at', ''))}",
               "lines": ref_lines(c)}
    if cut:
        s["ev"].update(video_from=at, video_to=reveal)
        s["capture"] = {"path": r["recording"], "cut": cut, "at": at, "shown": shown}
    s["out"] = {"header": f"REPEAT · WHAT {plan['tool'].upper()} HEARD", "tokens": tokens_of(r),
                "lines": [] if tokens_of(r) else status_lines(r), "reveal_at": reveal,
                "pending": "REPLAY NEXT"}
    rows = check_rows(r, reveal + 1.0)
    s["score"] = {"mode": "total", "rows": rows, "total_at": round(branch_at, 3),
                  "big": tr.BRANCH_LABEL[r["branch"]],
                  "big_cls": {"PASS": "pass", "PARTIAL_FAIL": "fail"}.get(r["branch"], "na"),
                  "sub": f"REPEAT · FIRST RUN {tr.BRANCH_LABEL[first['branch']]}"}
    s["extra_times"] = [at, reveal, branch_at] + [x["at"] for x in rows]
    return s


def verdict_cls(verdict: str) -> str:
    """The count keeps one colour across the verdict, files and limits windows."""
    return {"PASS": "pass", "PARTIAL_FAIL": "fail"}.get(verdict, "na")


def spec_verdict(plan: dict, results: list, rep: dict | None, verdict: str) -> dict:
    s = base_spec(plan, GRID_LEN["verdict"], results)
    mark = {"PASS": "✓", "PARTIAL_FAIL": "✗"}
    lines = [{"text": f"{mark.get(r['branch'], '?')} TEST {i + 1} {tr.BRANCH_LABEL[r['branch']]}",
              "cls": "" if r["branch"] == "PASS" else "yel"} for i, r in enumerate(results)]
    if rep:
        lines.append({"text": f"↻ REPEAT {tr.BRANCH_LABEL[rep['branch']]}", "cls": "sub"})
    s["ev"] = {"badge": tr.SOURCE_LABEL.upper(), "header": "SCORECARD", "lines": lines}
    t = tr.tally(results)
    s["out"] = {"header": "VERDICT", "lines": [
        {"text": tr.BRANCH_LABEL[verdict], "cls": "cyan" if verdict == "PASS" else "yel"},
        {"text": tr.tally_text(t).upper(), "cls": "sub"}]}
    s["score"] = {"mode": "total", "rows": [], "big": f"{t['passed']}/{t['declared']} CHECKS",
                  "big_cls": verdict_cls(verdict),
                  "sub": "PASSED"}
    return s


def spec_files(plan: dict, results: list, url: str | None, verdict: str) -> dict:
    s = base_spec(plan, GRID_LEN["files"], results)
    if url:
        u = url.replace("https://", "")
        host, _, rest = u.partition("/")
        head, _, name = rest.rpartition("/")
        s["ev"] = {"badge": "RESULTS SHEET", "header": "OPEN THIS LINK",
                   "lines": [{"text": host, "cls": "url"}, {"text": f"/{head}/", "cls": "url"},
                             {"text": name, "cls": "url"}]}
        s["out"] = {"header": "ON THE SHEET", "lines": [{"text": "4 CLIPS TO DOWNLOAD"},
                                                        {"text": "EVERY OUTPUT + CHECK", "cls": "sub"},
                                                        {"text": "HOW TO REPEAT IT", "cls": "sub"}]}
    else:
        s["ev"] = {"badge": "RESULTS SHEET", "header": "NOT PUBLISHED",
                   "lines": [{"text": "NO LINK YET", "cls": "yel"},
                             {"text": "THE SHEET DID NOT PUBLISH", "cls": "sub"}]}
        s["out"] = {"header": "SAVED", "lines": [{"text": "EVERY INPUT, OUTPUT"},
                                                 {"text": "AND CHECK IS KEPT", "cls": "sub"}]}
    t = tr.tally(results)
    s["score"] = {"mode": "total", "rows": [], "big": f"{t['passed']}/{t['declared']} CHECKS",
                  "big_cls": verdict_cls(verdict), "sub": tr.BRANCH_LABEL[verdict]}
    return s


def spec_limits(plan: dict, results: list, verdict: str) -> dict:
    s = base_spec(plan, GRID_LEN["limits"], results)
    s["ev"] = {"badge": tr.SOURCE_LABEL.upper(), "header": "LIMITATIONS",
               "lines": [{"text": "HOSTED DEMO"}, {"text": "NOT YOUR MACHINE", "cls": "sub"},
                         {"text": "4 SHORT CLIPS"}, {"text": "SYNTHETIC VOICES", "cls": "sub"}]}
    s["out"] = {"header": "TAKEAWAY", "lines": [
        {"text": tr.BRANCH_LABEL[verdict], "cls": "cyan" if verdict == "PASS" else "yel"},
        {"text": plan["set"]["title"].upper(), "cls": "sub"}]}
    t = tr.tally(results)
    s["score"] = {"mode": "total", "rows": [], "big": f"{t['passed']}/{t['declared']} CHECKS",
                  "big_cls": verdict_cls(verdict), "sub": "TOOLDOJO LIVE TRIALS"}
    return s


def spec_hold(plan: dict) -> dict:
    s = base_spec(plan, HOLD_SECONDS, [])
    s["ev"] = {"badge": tr.SOURCE_LABEL.upper(), "header": "ONE MOMENT", "lines": [{"text": "NEXT RESULT"}]}
    s["out"] = {"header": "", "lines": [{"text": "LOADING", "cls": "sub"}]}
    s["score"] = {"mode": "checks", "rows": []}
    return s


# ------------------------------------------------------------------ ffmpeg args (pure)
def segment_args(concat_path: str, audio: str | None, length: int, out_ts: str,
                 music: str | None = None, music_at: float = 0.0, music_gain: float = 1.0,
                 capture: dict | None = None, ffmpeg: str = "ffmpeg",
                 profile: dict | None = None) -> list:
    """radar_live.segment_args' encoder (row 11 GOPs, no B-frames, the exact frame
    count, voice + looped music bed) plus an optional capture overlay composited into
    the evidence card (#vbox) and the output scale of the stream profile, so the
    segments remux onto radar_live's single connection."""
    prof = profile or out_profile({})
    gop = FPS * rl.lp.KEYFRAME_S
    cap = f"{prof['kbps']}k"
    audio_in = (["-i", audio] if audio else
                ["-f", "lavfi", "-i", f"anullsrc=r={rl.lp.AUDIO_HZ}:cl=stereo"])
    scale = (f",scale={prof['w']}:{prof['h']}:flags=lanczos"
             if (prof["w"], prof["h"]) != (W, H) else "")
    ins, n = [], 2
    if capture:
        c = capture["cut"]
        ins += ["-ss", f"{float(c['start']):.3f}", "-t", f"{float(c['length']):.3f}",
                "-i", capture["path"]]
        at, shown = float(capture["at"]), float(capture["shown"])
        vf = (f"[0:v]fps={FPS},format=yuv420p[b];"
              f"[2:v]setpts=(PTS-STARTPTS)/{float(c['speed']):.4f}+{at:.3f}/TB,fps={FPS},"
              f"scale={CAP_W}:{CAP_H}:flags=lanczos,setsar=1,format=yuv420p[c];"
              f"[b][c]overlay=x={CAP_X}:y={CAP_Y}:eof_action=pass:"
              f"enable='between(t,{at:.3f},{at + shown:.3f})'{scale},format=yuv420p[v]")
        n = 3
    else:
        vf = f"[0:v]fps={FPS}{scale},format=yuv420p[v]"
    vgain = f"volume={rl.VOICE_GAIN_DB}dB," if rl.VOICE_GAIN_DB else ""
    if music:
        playlist = str(music).endswith(".ffconcat")
        ins += ["-stream_loop", "-1", "-ss", f"{max(0.0, music_at):.3f}",
                *(["-f", "concat", "-safe", "0"] if playlist else []), "-i", music]
        # both inputs run forever (apad, loop); -t below ends the segment
        af = (f";[1:a]{vgain}apad[vo];[{n}:a]volume={music_gain}[m];"
              "[vo][m]amix=inputs=2:duration=shortest:normalize=0[a]")
    else:
        af = f";[1:a]{vgain}apad[a]"
    return [ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
            "-f", "concat", "-safe", "0", "-i", concat_path, *audio_in, *ins,
            "-filter_complex", vf + af, "-map", "[v]", "-map", "[a]",
            "-c:v", "libx264", "-preset", rl.lp.X264_PRESET, "-profile:v", "high", "-crf", rl.CRF,
            # no B-frames: a negative first DTS lands before the previous segment's last
            "-bf", "0", "-maxrate", cap, "-bufsize", cap,
            "-g", str(gop), "-keyint_min", str(gop), "-sc_threshold", "0",
            "-c:a", "aac", "-b:a", f"{rl.lp.AUDIO_KBPS}k", "-ar", str(rl.lp.AUDIO_HZ), "-ac", "2",
            "-frames:v", str(length * FPS), "-t", str(length),
            "-muxdelay", "0", "-muxpreload", "0", "-f", "mpegts", out_ts]


def voice_mix_args(clips: list, length: int, out_wav: str, ffmpeg: str = "ffmpeg") -> list:
    """Place several voice clips [(path, at_seconds)] on one `length`-second track."""
    ins, labels, fc = [], [], []
    for i, (p, at) in enumerate(clips):
        ins += ["-i", str(p)]
        ms = int(round(float(at) * 1000))
        fc.append(f"[{i}:a]aresample={rl.lp.AUDIO_HZ},adelay={ms}|{ms}[v{i}]")
        labels.append(f"[v{i}]")
    fc.append("".join(labels) + f"amix=inputs={len(clips)}:normalize=0:duration=longest,apad[a]")
    return [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", *ins, "-filter_complex",
            ";".join(fc), "-map", "[a]", "-t", str(length), "-ar", str(rl.lp.AUDIO_HZ), "-ac", "2",
            out_wav]


def shift_phrases(phrases: list, at: float) -> list:
    return [[round(a + at, 3), round(b + at, 3), t] for a, b, t in phrases]


# ================================================================== producer
class Producer:
    """Runs in its own PROCESS (radar_live's reason: the sender's writer must not share
    a GIL with Playwright screenshots)."""

    def __init__(self, q, stop, onair, opts: dict):
        self.q, self.stop, self.onair, self.opts = q, stop, onair, opts
        self.renderer = None
        self.music, self.music_len, self.music_clock, self.music_gain = None, 0.0, 0.0, 1.0
        self.voices = {}          # narration key -> (mp3, words, seconds, text)
        self.results = {}         # test index -> result ; 4 = the repeat
        self.ready = {i: threading.Event() for i in range(5)}
        self.air_t0 = None
        self.plan = None
        self.narration = None
        self.n = 0
        self.profile = out_profile()
        self.sheet_url = None

    # -------------------------------------------------------------- prepare
    def _music(self):
        tracks = rl.playlist_order(rl.MUSIC_DIR.glob("*.mp3"), datetime.now(timezone.utc).date())
        if not tracks:
            return
        # normalised once per track and kept: re-normalising 5 tracks cost 72 s of the
        # node's 300 s lead in the first local session
        mdir = WORK / "music"
        mdir.mkdir(parents=True, exist_ok=True)
        done = []
        for src in tracks:
            st = Path(src).stat()
            dst = mdir / f"{tr.slug(Path(src).stem, 30)}-{st.st_size}.wav"
            if dst.exists() and rl.media_seconds(str(dst)) > 1:
                done.append(str(dst))
                continue
            try:
                r = subprocess.run(rl.normalize_args(src, str(dst), fv.FFMPEG or "ffmpeg"),
                                   capture_output=True, timeout=300, creationflags=NO_WINDOW)
                if r.returncode == 0 and dst.exists() and rl.media_seconds(str(dst)) > 1:
                    done.append(str(dst))
            except Exception:  # noqa: BLE001
                pass
        if done:
            pl = mdir / "playlist.ffconcat"
            pl.write_text(rl.concat_playlist(done), encoding="utf-8")
            self.music_len = sum(rl.media_seconds(p) for p in done)
            self.music = str(pl)
            log(f"  music: {len(done)} tracks normalised to {rl.MUSIC_TARGET_LUFS} LUFS")

    def _voice_all(self) -> str:
        """Voice EVERY prepared line, every branch (the rehearsal gate). '' = all
        voiced and each fits its window; else the reason the show cannot run. Four
        lines at a time: the node starts the job only 5 minutes before the slot."""
        from concurrent.futures import ThreadPoolExecutor
        vdir = WORK / "voice"
        shutil.rmtree(vdir, ignore_errors=True)
        vdir.mkdir(parents=True, exist_ok=True)

        def one(item):
            key, text = item
            mp3 = vdir / (key.replace(".", "_") + ".mp3")
            words, secs = rl.voice(text, mp3)
            if not words:
                words, secs = rl.voice(text, mp3)      # one retry (network)
            return key, text, str(mp3), words, secs

        with ThreadPoolExecutor(max_workers=VOICE_WORKERS) as pool:
            done = list(pool.map(one, tr._flat(self.narration)))
        for key, text, mp3, words, secs in done:
            if not words:
                return f"voice failed for {key}"
            limit = tr.WINDOW_SPEECH[window_kind(key.split(".")[0])] + 4
            if secs > limit:
                return f"{key} runs {secs:.1f}s, over its {limit}s window"
            self.voices[key] = (mp3, words, secs, text)
        return ""

    def _phr(self, key: str, at: float = 0.0) -> list:
        mp3, words, secs, text = self.voices[key]
        return shift_phrases([list(p) for p in rd.phrases(rd.punctuate(words, text), PHRASE_WORDS)], at)

    def prepare(self) -> dict:
        """Everything before the connection opens. Returns the hello message."""
        self._music()
        history = tr.load_history()
        feed = tr.feed_candidates() if self.opts.get("feed") else []
        plans, plog = tr.plan_episodes(history=history, feed=feed, signals=self.opts.get("signals", True))
        for line in plog:
            log("  plan: " + line)
        pre = None
        for plan in plans:
            pre = tr.run_test(plan, plan["set"]["clips"][0], WORK / "preflight" / tr.slug(plan["space"]),
                              label="Preflight")
            if pre["branch"] in ("PASS", "PARTIAL_FAIL"):
                self.plan = plan
                break
            log(f"  preflight {plan['space']}: {pre['branch']} ({pre['why']}) - next candidate")
        if not self.plan:
            return {"ready": True, "skip": "no candidate passed the gates and its preflight"}
        self.pre = pre
        tmpl = tr.template_narration(self.plan)
        self.narration, wrote = tr.llm_narration(self.plan, tmpl) if self.opts.get("llm", True) \
            else (tmpl, 0)
        self.narration_source = "llm" if wrote else "template"
        ok, why = tr.materially_varied(self.plan, self.narration, history)
        if not ok:
            return {"ready": True, "skip": "not materially varied: " + "; ".join(why)}
        err = self._voice_all()
        if err:
            return {"ready": True, "skip": "branches not rehearsed: " + err}
        log(f"  episode {self.plan['id']}: {self.plan['tool']} on {self.plan['space']}, "
            f"set {self.plan['fixture_set']}, narration={self.narration_source} "
            f"({len(self.voices)} lines voiced)")
        return {"ready": True, "skip": "", "plan": {k: self.plan[k] for k in (
            "id", "tool", "space", "fixture_set", "question", "hardware")},
            "preflight": self.pre["branch"], "narration": self.narration_source}

    # -------------------------------------------------------------- render
    def _encode(self, spec: dict, clips: list, name: str, kind: str, wid: str = "",
                advance_music: bool = True) -> dict | None:
        d = WORK / "seg" / f"{self.n:02d}_{name}"
        self.n += 1
        shutil.rmtree(d, ignore_errors=True)
        d.mkdir(parents=True, exist_ok=True)
        spec["times"] = frame_times(spec)
        shots, unfit = self.renderer.frames(spec, d)
        if [u for u in unfit if u != "transcript_cut"]:
            log(f"  {name}: text did not fit at the floor: {unfit}")
        from factverse import storyboard
        lst = d / "list.txt"
        lst.write_text(storyboard.concat_list(shots, spec["length"]), encoding="utf-8")
        audio = None
        if len(clips) == 1 and clips[0][1] == 0:
            audio = clips[0][0]
        elif clips:
            audio = str(d / "voice.wav")
            r = subprocess.run(voice_mix_args(clips, spec["length"], audio, fv.FFMPEG or "ffmpeg"),
                               capture_output=True, text=True, timeout=120, creationflags=NO_WINDOW)
            if r.returncode != 0:
                log(f"  {name}: voice mix failed {(r.stderr or '')[-200:]}")
                audio = None
        at = self.music_clock % self.music_len if self.music else 0.0
        ts = d / "segment.ts"
        ok = False
        # a capture that cannot be composited costs the replay, never the window: the
        # second attempt encodes the same frames, voice and bed without it
        for capture in ([spec["capture"], None] if spec.get("capture") else [None]):
            r = subprocess.run(segment_args(str(lst), audio, spec["length"], str(ts), self.music, at,
                                            self.music_gain, capture, fv.FFMPEG or "ffmpeg",
                                            self.profile),
                               capture_output=True, text=True, timeout=900, creationflags=NO_WINDOW)
            ok = r.returncode == 0 and ts.exists() and ts.stat().st_size >= 10000
            if ok:
                break
            log(f"  {name}: segment encode failed{' with the replay' if capture else ''}: "
                f"{(r.stderr or '')[-300:]}")
        if not ok:
            return None
        if advance_music:
            self.music_clock += spec["length"]
        return {"ts": str(ts), "length": spec["length"], "kind": kind, "wid": wid or name,
                "unfit": unfit}

    def _put(self, item) -> None:
        while not self.stop.is_set():
            try:
                self.q.put(item, timeout=1.0)
                return
            except queue.Full:
                continue

    def render_window(self, wid: str) -> dict | None:
        p, N = self.plan, self.narration
        res = [self.results[i] for i in range(4) if i in self.results]
        if wid == "open":
            spec = spec_open(p, self.pre)
            spec["phrases"] = self._phr("open")
            return self._encode(spec, [(self.voices["open"][0], 0)], wid, "window", wid)
        if wid == "rules":
            spec = spec_rules(p)
            spec["phrases"] = self._phr("rules")
            return self._encode(spec, [(self.voices["rules"][0], 0)], wid, "window", wid)
        k = test_index(wid) if wid not in ("repeat",) else None
        if window_kind(wid) == "result":
            r = self.results[k]
            spec = spec_result(p, k, r, [self.results[i] for i in range(k + 1)], wid)
            key = f"{wid}.{r['branch']}"
            # the branch is spoken once the transcript is on screen: at the result
            # label when it fits, else as late as the window allows
            at = min(spec["score"]["total_at"], spec["length"] - self.voices[key][2] - 1.0)
            at = max(at, spec["out"].get("reveal_at") or 0.0, 0.0)
            spec["phrases"] = self._phr(key, at)
            return self._encode(spec, [(self.voices[key][0], at)], wid, "window", wid)
        if window_kind(wid) == "run":
            r = self.results[k]
            speech = self.voices[wid][2]
            spec = spec_run(p, k, r, [self.results[i] for i in range(k)], speech)
            spec["phrases"] = self._phr(wid)
            return self._encode(spec, [(self.voices[wid][0], 0)], wid, "window", wid)
        if wid == "repeat":
            idx, why = tr.repeat_choice(res)
            r = self.results[4]
            ikey = "repeat_intro." + ("control" if why == "control" else str(idx + 1))
            bkey = f"repeat_result.{r['branch']}"
            speech = self.voices[ikey][2]
            b_at = GRID_LEN["repeat"] - self.voices[bkey][2] - 3.0
            spec = spec_repeat(p, idx, self.results[idx], r, res, speech, b_at)
            spec["phrases"] = self._phr(ikey) + self._phr(bkey, b_at)
            return self._encode(spec, [(self.voices[ikey][0], 0), (self.voices[bkey][0], b_at)],
                                wid, "window", wid)
        if wid == "verdict":
            v = tr.verdict(res)
            spec = spec_verdict(p, res, self.results.get(4), v)
            spec["phrases"] = self._phr(f"verdict.{v}")
            return self._encode(spec, [(self.voices[f"verdict.{v}"][0], 0)], wid, "window", wid)
        if wid == "files":
            v = tr.verdict(res)
            key = "files.published" if self.sheet_url else "files.unpublished"
            spec = spec_files(p, res, self.sheet_url, v)
            spec["phrases"] = self._phr(key)
            return self._encode(spec, [(self.voices[key][0], 0)], wid, "window", wid)
        if wid == "limits":
            v = tr.verdict(res)
            spec = spec_limits(p, res, v)
            spec["phrases"] = self._phr(f"limits.{v}")
            return self._encode(spec, [(self.voices[f"limits.{v}"][0], 0)], wid, "end", wid)
        return None

    # -------------------------------------------------------------- live runs
    def runner(self):
        """Runs the tests DURING the broadcast, each no earlier than RUN_LEAD_SECONDS
        before the window that shows it, then the repeat. Stops after two consecutive
        execution failures (the "test incomplete" ending)."""
        clips = self.plan["set"]["clips"]
        try:
            for i in range(4):
                self._wait_air(run_at(i))
                if self.stop.is_set():
                    return
                label = "Fresh rerun" if i == 0 else f"Test {i + 1}"
                self.results[i] = tr.run_test(self.plan, clips[i], WORK / "runs" / f"t{i + 1}", label=label)
                self.ready[i].set()
                if tr.incomplete([self.results[j] for j in range(i + 1)]):
                    log("  two consecutive execution failures: test incomplete")
                    for j in range(i + 1, 5):
                        self.ready[j].set()
                    return
            self._wait_air(run_at(4))
            idx, why = tr.repeat_choice([self.results[j] for j in range(4)])
            self.results[4] = tr.run_test(self.plan, clips[idx], WORK / "runs" / "repeat",
                                          label=f"Repeat of test {idx + 1}")
        except Exception as e:  # noqa: BLE001
            log(f"  runner failed: {type(e).__name__}: {str(e)[:120]}")
        finally:
            for j in range(5):
                self.ready[j].set()

    def _wait_air(self, at: float):
        while not self.stop.is_set() and time.monotonic() - self.air_t0 < at:
            time.sleep(0.5)

    def _need(self, wid: str) -> int | None:
        if wid in ("open", "rules", "verdict", "files", "limits"):
            return None
        return 4 if wid == "repeat" else test_index(wid)

    # -------------------------------------------------------------- record
    def record(self) -> dict:
        res = [self.results[i] for i in range(4) if i in self.results]
        v = tr.verdict(res)
        t = tr.tally(res)
        started = self.opts.get("air_iso") or datetime.now(timezone.utc).isoformat(timespec="seconds")
        rep = self.results.get(4)
        ep = {"id": self.plan["id"], "date": self.plan["date"], "slot": self.plan["slot"],
              "tool": self.plan["tool"], "maker": self.plan.get("maker", ""),
              "space": self.plan["space"], "space_sha": self.plan.get("sha", ""),
              "repo": self.plan.get("repo", ""), "model": self.plan.get("model", ""),
              "hardware": self.plan.get("hardware", ""), "pins": self.plan.get("pins", []),
              "settings": (res[0].get("settings") if res else {}) or {},
              "fixture_set": self.plan["fixture_set"], "set": self.plan["set"],
              "question": self.plan["question"], "question_short": self.plan["question_short"],
              "signals": self.plan.get("signals", {}), "preflight": _slim(self.pre),
              "tests": [_slim(r) for r in res], "repeat": _slim(rep) if rep else None,
              "verdict": v, "tally": t,
              "branch_why": _branch_why(v, res, t),
              "narration_source": self.narration_source,
              "narration_hash": tr.narration_hash(self.narration),
              "narration_text": tr.investigation_text(self.narration),
              "started_at": started, "recap_not_before": tr.recap_not_before(started),
              "local_test": bool(self.opts.get("local")), "status": "aired"}
        ep["sheet_url"] = ""
        return ep

    def publish(self, ep: dict) -> str | None:
        out = tr.LOCAL_DIR / ep["id"]
        out.mkdir(parents=True, exist_ok=True)
        ep_sheet = dict(ep, sheet_url=tr.sheet_url(ep))
        page = tr.render_sheet(ep_sheet)
        (out / tr.sheet_name(ep)).write_text(page, encoding="utf-8")
        hist = [e for e in tr.load_history() if e.get("id") != ep["id"]] + [ep_sheet]
        url = None
        if not self.opts.get("local"):
            files = {f"{tr.SHEETS_DIR}/{tr.sheet_name(ep)}": page}
            pub = [tr.public_record(e) for e in hist if not e.get("local_test")]
            files["state/trials_episodes.json"] = json.dumps(pub, indent=1, ensure_ascii=False) + "\n"
            done = tr.publish_files(files, f"trials: {ep['id']} results sheet [skip ci]")
            if done and f"{tr.SHEETS_DIR}/{tr.sheet_name(ep)}" in done:
                url = ep_sheet["sheet_url"]
        ep["sheet_url"] = url or ""
        hist = [e for e in hist if e.get("id") != ep["id"]] + [ep]
        if not self.opts.get("local"):
            tr.save_history(hist)
        else:
            tr.save_history(hist, tr.LOCAL_DIR / "local_test_episodes.json")
        log(f"  results sheet: {out / tr.sheet_name(ep)} "
            + (f"published {url}" if url else "(not published)"))
        return url

    # -------------------------------------------------------------- main loop
    def run(self):
        rl.LOG = LOG
        try:
            self.renderer = rl.Renderer(page=PAGE, size=(W, H))
            hello = self.prepare()
            if hello.get("skip"):
                log("  skipped: " + hello["skip"])
                self._put(hello)
                self._put(None)
                return
            self.hold = self._encode(spec_hold(self.plan), [], "hold", "standby", advance_music=False)
            hello["hold"] = self.hold
            self._put(hello)
            for wid in ("open", "rules"):
                seg = self.render_window(wid)
                if not seg:
                    self._put(None)
                    return
                self._put(seg)
            while not self.onair.wait(timeout=1.0):
                if self.stop.is_set():
                    return
            self.air_t0 = time.monotonic()
            self.opts["air_iso"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
            threading.Thread(target=self.runner, daemon=True).start()
            self.sheet_url = None
            for wid, _n in GRID[2:]:
                if self.stop.is_set():
                    return
                need = self._need(wid)
                if need is not None:
                    while not self.ready[need].wait(timeout=1.0):
                        if self.stop.is_set():
                            return
                    if need not in self.results:
                        if wid in skipped_windows(self.results) or need == 4:
                            log(f"  {wid}: skipped (test incomplete)")
                            continue
                        log(f"  {wid}: no result")
                        continue
                if wid == "files":
                    try:
                        self.sheet_url = self.publish(self.record())
                    except Exception as e:  # noqa: BLE001
                        log(f"  sheet failed: {type(e).__name__}: {str(e)[:120]}")
                seg = self.render_window(wid)
                if seg:
                    self._put(seg)
                else:
                    log(f"  {wid}: render failed")
            self._put(None)
        except Exception as e:  # noqa: BLE001 — the sender ends the session cleanly
            log(f"  producer failed: {type(e).__name__}: {str(e)[:200]}")
            self._put({"ready": True, "skip": f"producer failed: {type(e).__name__}"})
            self._put(None)
        finally:
            if self.renderer:
                self.renderer.close()


def _slim(r: dict | None) -> dict | None:
    if not r:
        return None
    return {k: v for k, v in r.items() if k not in ("cut",)}


def _branch_why(v: str, res: list, t: dict) -> str:
    """The sentence that says WHY the verdict branch was chosen (the record and sheet)."""
    names = lambda b: ", ".join(str(i + 1) for i, r in enumerate(res) if r["branch"] == b)  # noqa: E731
    if v == "PASS":
        return f"All {len(res)} tests passed both checks ({t['passed']}/{t['declared']})."
    if v == "PARTIAL_FAIL":
        return f"At least one check failed on test(s) {names('PARTIAL_FAIL')}; {tr.tally_text(t)}."
    if v == "TIMEOUT":
        return f"No check failed, but test(s) {names('TIMEOUT')} did not finish within {tr.RUN_SECONDS:.0f} s."
    return "No check failed, but at least one result could not be verified" + (
        f" (test(s) {names('INCONCLUSIVE')})" if names("INCONCLUSIVE") else "") + "."


def producer_main(q, stop, onair, opts: dict) -> None:
    Producer(q, stop, onair, opts).run()


# ================================================================== sender
def wait_until(start_at: str, now=None) -> float:
    """Seconds to wait until today's HH:MM UTC (0 when it has passed)."""
    now = now or datetime.now(timezone.utc)
    hh, mm = (int(x) for x in start_at.split(":"))
    target = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
    return max(0.0, (target - now).total_seconds())


def late_by(start_at: str, now=None) -> float:
    now = now or datetime.now(timezone.utc)
    hh, mm = (int(x) for x in start_at.split(":"))
    target = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
    return (now - target).total_seconds()


def run_show(dest: str, opts: dict) -> dict:
    WORK.mkdir(parents=True, exist_ok=True)
    summary = {"start": "", "status": "ok", "segments": [], "holds": 0, "restarts": 0,
               "seconds": 0, "episode": None}
    q = mp.Queue(maxsize=QUEUE_DEPTH)
    stop, onair = mp.Event(), mp.Event()
    prod = mp.Process(target=producer_main, args=(q, stop, onair, opts), daemon=True)
    streamer = None
    try:
        prod.start()
        try:
            hello = q.get(timeout=PREP_TIMEOUT)
        except queue.Empty:
            summary["status"] = "failed: producer not ready"
            return summary
        if not isinstance(hello, dict) or hello.get("skip") or not hello.get("ready"):
            summary["status"] = "skipped: " + str((hello or {}).get("skip") or "nothing usable")
            return summary
        summary["episode"] = hello.get("plan")
        hold = hello.get("hold")
        pending, ended, err = rl.preroll(q.get, PREROLL, 600)
        if len(pending) < PREROLL:
            summary["status"] = "failed: the opening windows did not render" + (f" ({err})" if err else "")
            return summary
        if opts.get("start_at"):
            late = late_by(opts["start_at"])
            if late > tr.LATE_START_MAX:
                summary["status"] = f"skipped: ready {late:.0f}s after {opts['start_at']} UTC"
                return summary
            wait = wait_until(opts["start_at"])
            log(f"  ready; connecting at {opts['start_at']} UTC (in {wait:.0f}s)")
            end = time.monotonic() + wait
            while time.monotonic() < end:
                time.sleep(min(1.0, end - time.monotonic()))
        streamer = rl.Streamer(dest)
        streamer.start()
        onair.set()
        t0 = time.monotonic()
        summary["start"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        log(f"  on air: {summary['episode']}")
        offset = 0.0
        deadline = t0 + tr.SHOW_MINUTES * 60 + OVERRUN
        while time.monotonic() < deadline:
            if streamer.broken.is_set():
                if summary["restarts"] >= rl.RESTARTS:
                    summary["status"] = "ended: streamer kept failing"
                    break
                summary["restarts"] += 1
                log(f"  streamer exited; restart {summary['restarts']}/{rl.RESTARTS}")
                streamer.finish(wait=5)
                time.sleep(rl.RESTART_WAIT)
                streamer = rl.Streamer(dest)
                streamer.start()
                offset, t0 = 0.0, time.monotonic()
                continue
            try:
                seg = pending.pop(0) if pending else q.get(timeout=0.5)
            except queue.Empty:
                if offset - (time.monotonic() - t0) > HOLD_MARGIN or not hold:
                    continue
                seg = hold
            if seg is None:
                break
            if seg.get("ready"):
                if seg.get("skip"):
                    log("  producer: " + str(seg["skip"]))
                continue
            data = rl.remux(seg, offset)
            if not data:
                log(f"  remux failed for {seg.get('wid')}; skipping it")
                continue
            if not streamer.put(data):
                continue
            offset += seg["length"]
            summary["seconds"] += seg["length"]
            if seg["kind"] == "standby":
                summary["holds"] += 1
                if summary["holds"] * HOLD_SECONDS > MAX_HOLD_SECONDS:
                    # the producer has stalled: end the show rather than air a hold card
                    summary["status"] = f"ended: producer stalled ({summary['holds']} holds)"
                    log("  " + summary["status"])
                    break
            else:
                summary["segments"].append(seg.get("wid"))
            log(f"  queued {seg.get('wid')} ({seg['length']}s) - timeline {offset:.0f}s")
            if seg["kind"] == "end":
                break
    finally:
        stop.set()
        if streamer:
            summary["ffmpeg_exit"] = streamer.finish()
            summary["ffmpeg_tail"] = streamer.tail[-5:]
            summary["seam_flags"] = streamer.seam_flags
        prod.join(timeout=60)
        if prod.is_alive():
            prod.terminate()
        summary["end"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return summary


# ================================================================== dry run
def rehearse(opts: dict) -> int:
    """Plan + preflight + every branch written and voiced, and a still of each result
    window in all four branches — no stream, no network beyond the planning reads."""
    out = tr.LOCAL_DIR / "rehearsal"
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True, exist_ok=True)
    p = Producer(None, mp.Event(), mp.Event(), opts)
    rl.LOG = LOG
    p.renderer = rl.Renderer(page=PAGE, size=(W, H))
    try:
        hello = p.prepare()
        if hello.get("skip"):
            log("rehearsal: " + hello["skip"])
            return 1
        (out / "narration.json").write_text(json.dumps(p.narration, indent=2, ensure_ascii=False),
                                            encoding="utf-8")
        (out / "plan.json").write_text(json.dumps({k: v for k, v in p.plan.items() if k != "set"},
                                                  indent=2, default=str), encoding="utf-8")
        pre = p.pre
        fake = {"PASS": pre if pre["branch"] == "PASS" else None,
                "PARTIAL_FAIL": pre if pre["branch"] == "PARTIAL_FAIL" else None}
        clip = p.plan["set"]["clips"][0]
        if not fake["PASS"]:
            fake["PASS"] = dict(pre, branch="PASS", transcript=clip["text"],
                                checks=tr.checks_for(clip, clip["text"]))
        if not fake["PARTIAL_FAIL"]:
            bad = clip["text"].replace(clip["terms"][0], "something")
            fake["PARTIAL_FAIL"] = dict(pre, branch="PARTIAL_FAIL", transcript=bad,
                                        checks=tr.checks_for(clip, bad))
        nr = [{"id": "terms", "label": "Key words heard", "value": "not run", "ok": None},
              {"id": "errors", "label": "Word errors", "value": "not run", "ok": None}]
        fake["TIMEOUT"] = dict(pre, branch="TIMEOUT", transcript="", checks=nr, recording="", cut=None)
        fake["INCONCLUSIVE"] = dict(pre, branch="INCONCLUSIVE", transcript="", checks=nr,
                                    recording="", cut=None)
        shots = []
        for name, spec, t in (("open", spec_open(p.plan, pre), 10), ("rules", spec_rules(p.plan), 10)):
            spec["phrases"] = p._phr(name)
            shots.append((name, spec, t))
        for b in tr.BRANCHES:
            spec = spec_result(p.plan, 0, fake[b], [fake[b]], "result1")
            spec["phrases"] = p._phr(f"result1.{b}", 14)
            shots.append((f"result1_{b}", spec, 25))
        for b in tr.BRANCHES:
            res = [fake[b]] * 4
            spec = spec_verdict(p.plan, res, None, b)
            spec["phrases"] = p._phr(f"verdict.{b}")
            shots.append((f"verdict_{b}", spec, 4))
        url = tr.sheet_url({"date": p.plan["date"], "tool": p.plan["tool"], "fixture_set": p.plan["fixture_set"]})
        for name, spec in (("files_published", spec_files(p.plan, [fake["PASS"]] * 4, url, "PASS")),
                           ("files_unpublished", spec_files(p.plan, [fake["PASS"]] * 4, None, "PASS"))):
            spec["phrases"] = p._phr(name.replace("_", "."))
            shots.append((name, spec, 4))
        for name, spec, t in shots:
            p.renderer._page.evaluate("s => window.__load(s)", spec)
            p.renderer._page.evaluate("t => window.__seek(t)", t)
            p.renderer._page.screenshot(path=str(out / f"{name}.png"))
        log(f"rehearsal: {p.plan['id']} preflight={pre['branch']} - stills and narration in {out}")
        for key, text in tr._flat(p.narration):
            print(f"  {key:28s} {p.voices[key][2]:5.1f}s  {text}")
        return 0
    finally:
        p.renderer.close()


# ================================================================== main
def heartbeat(stop) -> None:
    """The node's pulse file (logs/trials_live.log) gets a line at least this often,
    whatever the producer is doing (TTS and the preflight can be quiet for minutes)."""
    while not stop.wait(HEARTBEAT_SECONDS):
        log("  alive")


def trials_day(now=None) -> bool:
    now = now or datetime.now(timezone.utc)
    return now.weekday() == tr.SLOT_WEEKDAY


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--minutes", type=float, default=float(tr.SHOW_MINUTES),
                    help="must be 12: the show is a fixed 12-minute grid")
    ap.add_argument("--start-at", default="", help="HH:MM UTC to connect at (the node job: 18:45)")
    ap.add_argument("--out", "--local-rtmp", dest="out",
                    help="local test target (a file or rtmp://127.0.0.1/...); never needs a key")
    ap.add_argument("--dry-run", action="store_true", help="plan, preflight, voice every branch, "
                                                           "render stills; no stream")
    ap.add_argument("--no-llm", action="store_true", help="template narration only")
    ap.add_argument("--no-signals", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--feed", action="store_true", help="also read the tool lane's feeds")
    a = ap.parse_args(argv)
    if not a.out and not a.dry_run and not a.start_at:
        a.start_at = tr.SLOT_UTC          # the node passes no arguments: connect at the slot
    opts = {"llm": not a.no_llm, "signals": not a.no_signals, "feed": a.feed,
            "start_at": a.start_at, "local": bool(a.out or a.dry_run)}
    summary = {"status": "not started"}
    try:
        if abs(a.minutes - tr.SHOW_MINUTES) > 1e-6:
            log(f"--minutes {a.minutes:g}: the show is a fixed {tr.SHOW_MINUTES}-minute grid")
            return 2
        if a.start_at and not __import__("re").fullmatch(r"\d{2}:\d{2}", a.start_at):
            log("--start-at must be HH:MM (UTC)")
            return 2
        if a.dry_run:
            return rehearse(opts)
        if a.out:
            if "youtube.com" in a.out.lower():
                log("--out is for local tests; YouTube is reached only through .env")
                return 2
            dest = a.out
        else:
            if not fv.flag("trials_live", False):
                log("trials_live is off in config.json: no show (spec row K1)")
                return 0
            if not trials_day():
                log("not a Live Trials day (Saturday UTC): no show")
                return 0
            url, key = (os.environ.get(n, "") for n in STREAM_ENV)
            if not key:
                log(f"no {STREAM_ENV[1]} in .env: Live Trials is off")
                return 0
            rl._SECRETS.append(key)
            if not rl.valid_ingest(url):
                log(f"{STREAM_ENV[0]} must be the rtmps:// Stream URL from YouTube Studio "
                    "(host *.youtube.com) - refusing to send the key anywhere else")
                return 2
            dest = rl.ingest_target(url, key)
        rl.LOG = LOG
        rl.keep_awake(True)
        prof = out_profile()
        enc = os.environ.get("TOOLDOJO_ENCODER", "")
        if enc and enc.lower() not in ("x264", "libx264"):
            log(f"TOOLDOJO_ENCODER={enc} is not supported here; encoding with libx264")
        log(f"profile {prof['name']} ({prof['w']}x{prof['h']}, {prof['kbps']} kbps)")
        beat = threading.Event()
        threading.Thread(target=heartbeat, args=(beat,), daemon=True).start()
        try:
            summary = run_show(dest, opts)
        finally:
            beat.set()
    except Exception as e:  # noqa: BLE001 — unattended: log, never crash the scheduler
        summary = {**summary, "status": f"crashed: {type(e).__name__}: {rl.redact(str(e))[:200]}"}
        log(summary["status"])
    finally:
        rl.keep_awake(False)
        try:
            SESSIONS.parent.mkdir(parents=True, exist_ok=True)
            with SESSIONS.open("a", encoding="utf-8") as f:
                f.write(rl.redact(json.dumps(summary, default=str)) + "\n")
        except Exception:  # noqa: BLE001
            pass
    log(f"session end: {summary.get('status')} · {len(summary.get('segments') or [])} windows · "
        f"{summary.get('holds', 0)} holds · {summary.get('restarts', 0)} restarts · "
        f"{summary.get('seconds', 0)}s")
    return 0 if str(summary.get("status", "")).startswith(("ok", "skipped")) else 1


if __name__ == "__main__":
    sys.exit(main())

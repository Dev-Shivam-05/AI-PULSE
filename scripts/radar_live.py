"""
v3-L.2 ToolDojo Radar Live — the unattended live streamer (docs/spec/ai-pulse-v3l2.md).

    py -3 scripts/radar_live.py                      # a real session: YT_STREAM_URL + YT_STREAM_KEY
    py -3 scripts/radar_live.py --minutes 10         # a shorter session (the private test)
    py -3 scripts/radar_live.py --out temp/live/t.flv --minutes 5    # local test, no YouTube

How it works: a producer thread fetches live GitHub / Hugging Face data, writes and voices
one segment at a time, renders its frames in headless Chromium and encodes it; the main
thread remuxes each finished segment onto one continuous timeline and pipes it into a
single `ffmpeg -re … -c copy -f flv` connection. When nothing is ready a silent standby
board fills the gap, because an ingest that starves ends the broadcast.

Unattended rules (CLAUDE.md): nothing here may raise out of main() — a failure is logged and
the session ends cleanly; the stream key never reaches a log line, and the URL it is sent to
must be rtmps:// on a *.youtube.com host.
"""
import argparse
import ctypes
import json
import multiprocessing as mp
import os
import queue
import random
import shutil
import subprocess
import sys
import threading
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from factverse import config as fv          # noqa: E402
from factverse import radar as rd           # noqa: E402
import live_preflight as lp                 # noqa: E402

# v3-N.1 rows 9-10: on the ToolDojo Node the preflight picks the output profile and the
# encoder and the supervisor passes them as RADAR_PROFILE / RADAR_ENCODER. Unset (the
# laptop) = 1080p30 x264, exactly as before. The page is ALWAYS rendered at its locked
# 1920x1080 layout and scaled down in ffmpeg: a 1280 px viewport would re-flow the board.
PAGE_W, PAGE_H = 1920, 1080
ENCODERS = ("libx264", "h264_qsv")
PROFILE_NAME = str(fv.setting("radar_profile", "1080p30") or "1080p30")
if PROFILE_NAME not in lp.PROFILES:
    PROFILE_NAME = "1080p30"
ENCODER = str(fv.setting("radar_encoder", "libx264") or "libx264")
if ENCODER not in ENCODERS:
    ENCODER = "libx264"
PROFILE = lp.PROFILES[PROFILE_NAME]         # spec row 2
# W, H = the RENDER size (the page), whatever the output profile; segment_args scales
W, H, FPS = PAGE_W, PAGE_H, PROFILE["fps"]
# Session-0 safe Quick Sync: D3D11, never D3D9 (a scheduled task with nobody signed in
# has no interactive desktop, and D3D9 device creation fails there - ffmpeg trac #7511).
QSV_DEVICE = ["-init_hw_device", "qsv=qs:hw_any,child_device_type=d3d11va"]
CRF = "20"                                  # row 3: the storyboard's CRF (v3g1 row 7)
SESSION_MINUTES = 120                       # row 4 (the default when nothing else says)
MAX_SESSION_MINUTES = 360                   # L6 row 7: the ramp's top stage (S4)
MIN_SESSION_MINUTES = 30                    # L6 row 7: a manifest below this is ignored
QUEUE_DEPTH = 3                             # row 19
STANDBY_SECONDS = 10                        # row 20
RESTARTS, RESTART_WAIT = 5, 10              # row 21
REFRESH_SECONDS = 15 * 60                   # row 8
READY_TIMEOUT = 300  # first data fetch + browser + standby render, before giving up
TTS_SECONDS = 120    # wall clock for one narration
MAX_FAILURES = 5     # row 21a: consecutive failed segments end the session
PREROLL = 3          # v3l3 row 1: segments ready before the connection opens
MUSIC_VOLUME = 0.07  # v3l3 row 4: the long-form's bed level (factverse_engine.py)
# L6 row 10: speech -19.8 LUFS (the long-form's measured voice), music 17 LU under it.
# Tracks are loudness-normalised ONCE per session, so the mix gain is 1.0; a track that
# cannot be normalised falls back to the raw file at MUSIC_VOLUME.
MUSIC_TARGET_LUFS = -36.8
VOICE_GAIN_DB = 0.0  # L6 row 10: measured edge-tts level vs -19.8 LUFS (spec section 6)
# L6 row 8: one subscribe line after real value, then rarely. Seconds of session timeline.
CTA_FIRST, CTA_EVERY, CTA_SECONDS, CTA_LEAD = 165, 900, 5, 2
CTA_TEXT = ("If these discoveries help you choose AI tools, subscribe to ToolDojo "
            "for practical updates.")              # review 2026-11-01 point 8, verbatim
WRAP_LEAD = 150      # L6 row 9: ask for the end card this long before the target
OVERRUN = 600        # L6 row 9: hard wall-clock stop this long after the target
MANIFEST_URL = ("https://raw.githubusercontent.com/Dev-Shivam-05/AI-PULSE/main/"
                "state/live_broadcast.json")
IST = timezone(timedelta(hours=5, minutes=30))
# Each remuxed segment restarts its TS continuity counters, so the demuxer flags the
# seam packet; decoding the received stream shows no damage. Counted, not logged.
SEAM_NOISE = ("Packet corrupt", "corrupt input packet")

LIVE_DIR = fv.TEMP / "live"
HISTORY = LIVE_DIR / "radar_history.json"
LOG = fv.LOGS / "radar_live.log"
SESSIONS = fv.LOGS / "radar_sessions.jsonl"
PAGE = fv.ASSETS / "radar" / "radar.html"
MUSIC_DIR = fv.ASSETS / "music" / "radar"

_SECRETS: list = []


# ------------------------------------------------------------------ pure helpers
def redact(text: str, secrets=None) -> str:
    out = str(text)
    for s in (secrets if secrets is not None else _SECRETS):
        if s and len(s) >= 4:
            out = out.replace(s, "<redacted>")
    return out


def valid_ingest(url: str) -> bool:
    """Row 22: only rtmps:// to a *.youtube.com host ever receives the key.
    `rtmps://a.youtube.com.evil.test/` fails: the HOST must end in .youtube.com."""
    try:
        u = urlparse(str(url or "").strip())
    except ValueError:
        return False
    host = (u.hostname or "").lower()
    return u.scheme == "rtmps" and (host == "youtube.com" or host.endswith(".youtube.com"))


def ingest_target(url: str, key: str) -> str:
    return url.strip().rstrip("/") + "/" + key.strip()


def pick_track(tracks, day_of_year: int) -> str | None:
    """v3l3 row 4: one bed per session, by day of the year from the sorted list."""
    tracks = sorted(str(t) for t in tracks)
    return tracks[day_of_year % len(tracks)] if tracks else None


def playlist_order(tracks, day: date) -> list:
    """L6 row 10: every track, in an order shuffled once per calendar day (seeded by the
    date, so a restarted session plays the same order). The whole list plays before any
    track repeats; with today's 5 tracks that is the library's own limit."""
    out = sorted(str(t) for t in tracks)
    random.Random(day.toordinal()).shuffle(out)
    return out


def normalize_args(src: str, dst: str, ffmpeg: str = "ffmpeg",
                   target: float = MUSIC_TARGET_LUFS) -> list:
    """One track to the bed level (L6 row 10), as 44.1 kHz stereo WAV so the concat
    demuxer joins tracks without a codec change between them."""
    return [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", src,
            "-af", f"loudnorm=I={target}:TP=-2:LRA=11",
            "-ar", str(lp.AUDIO_HZ), "-ac", "2", "-c:a", "pcm_s16le", dst]


def concat_playlist(paths: list) -> str:
    """An ffconcat file body. Single quotes in a path are escaped the way ffconcat wants."""
    lines = ["ffconcat version 1.0"]
    for p in paths:
        lines.append("file '" + Path(p).as_posix().replace("'", "'\\''") + "'")
    return "\n".join(lines) + "\n"


def cta_window(seg_start: float, length: int, next_due: float) -> tuple:
    """L6 row 8: ((at, until) within this segment, or None; the next due time). The
    line appears CTA_LEAD s into the first segment that reaches the due time and stays
    CTA_SECONDS; a segment too short to hold it passes the turn to the next one."""
    if seg_start + length <= next_due:
        return None, next_due
    at = max(float(CTA_LEAD), next_due - seg_start)
    if at + CTA_SECONDS > length:
        return None, next_due
    return (round(at, 3), round(at + CTA_SECONDS, 3)), seg_start + at + CTA_EVERY


def session_minutes(cli: float | None, manifest: dict | None, default: float) -> float:
    """L6 row 7: --minutes wins, then today's CI manifest, then config; always clamped."""
    out = None
    for cand in (cli, (manifest or {}).get("target_minutes"), default, SESSION_MINUTES):
        try:
            out = float(cand)
            break
        except (TypeError, ValueError):
            continue                       # a bad value falls to the next source
    return max(1.0, min(out, float(MAX_SESSION_MINUTES)))


def manifest_for_today(data, today_ist: date) -> dict | None:
    """L7: the CI-written broadcast manifest counts only for TODAY (IST) and only when
    CI marked it ready with a sane target. Anything else is ignored, never trusted."""
    if not isinstance(data, dict) or data.get("status") != "ready":
        return None
    if str(data.get("date", "")) != today_ist.isoformat():
        return None
    try:
        t = float(data.get("target_minutes"))
    except (TypeError, ValueError):
        return None
    if not MIN_SESSION_MINUTES <= t <= MAX_SESSION_MINUTES:
        return None
    return {"target_minutes": t, "broadcast_id": str(data.get("broadcast_id", ""))[:40],
            "stage": str(data.get("stage", ""))[:8]}


def wrap_due(offset: float, target_seconds: float) -> bool:
    return offset >= target_seconds - WRAP_LEAD


def segment_args(concat_path: str, audio: str | None, length: int, out_ts: str,
                 ffmpeg: str = "ffmpeg", music: str | None = None,
                 music_at: float = 0.0, music_gain: float = MUSIC_VOLUME,
                 voice_gain_db: float = 0.0, encoder: str | None = None,
                 profile: str | None = None) -> list:
    """One segment, encoded once at timeline 0. Exactly `length` seconds (an even
    number, row 11) so the 2 s GOPs tile the whole stream. With `music`, the bed is
    looped from `music_at` (the session's running music time) under the voice. A
    `.ffconcat` music file is the L6 playlist; anything else is one track.
    `encoder` / `profile` default to the module's (N.1); the node preflight passes
    them explicitly so it measures this exact command."""
    enc = encoder if encoder in ENCODERS else ENCODER
    prof = lp.PROFILES.get(profile or PROFILE_NAME, PROFILE)
    fps = prof["fps"]
    gop = fps * lp.KEYFRAME_S
    cap = f"{prof['kbps']}k"
    scale = ("" if (prof["w"], prof["h"]) == (PAGE_W, PAGE_H)
             else f",scale={prof['w']}:{prof['h']}:flags=bicubic")
    if enc == "h264_qsv":
        pre, pix = list(QSV_DEVICE), "nv12"
        # CBR at YouTube's recommended rate (v3l section 5): QSV has no CRF; equal
        # -b:v / -maxrate is its constant-bitrate mode. No B-frames, same reason as x264.
        vcodec = ["-c:v", "h264_qsv", "-preset", lp.X264_PRESET, "-profile:v", "high",
                  "-b:v", cap, "-bf", "0"]
    else:
        pre, pix = [], "yuv420p"
        vcodec = ["-c:v", "libx264", "-preset", lp.X264_PRESET, "-profile:v", "high",
                  "-crf", CRF,
                  # no B-frames: with them a segment's first DTS is negative, and after the
                  # offset it lands before the previous segment's last one (measured at the
                  # 10 s seam)
                  "-bf", "0"]
    audio_in = (["-i", audio] if audio else
                ["-f", "lavfi", "-i", f"anullsrc=r={lp.AUDIO_HZ}:cl=stereo"])
    vgain = f"volume={voice_gain_db}dB," if voice_gain_db else ""
    if music:
        playlist = str(music).endswith(".ffconcat")
        music_in = ["-stream_loop", "-1", "-ss", f"{max(0.0, music_at):.3f}",
                    *(["-f", "concat", "-safe", "0"] if playlist else []), "-i", music]
        # both inputs run forever (apad, loop); -t below is what ends the segment
        mix = ["-filter_complex",
               f"[1:a]{vgain}apad[v];[2:a]volume={music_gain}[m];"
               "[v][m]amix=inputs=2:duration=shortest:normalize=0[a]",
               "-map", "0:v", "-map", "[a]"]
    else:
        music_in, mix = [], ["-map", "0:v", "-map", "1:a", "-af", f"{vgain}apad"]
    return [
        ffmpeg, "-hide_banner", "-loglevel", "error", "-y", *pre,
        "-f", "concat", "-safe", "0", "-i", concat_path, *audio_in, *music_in, *mix,
        "-vf", f"fps={fps}{scale},format={pix}",
        *vcodec,
        "-maxrate", cap, "-bufsize", cap,
        "-g", str(gop), "-keyint_min", str(gop), "-sc_threshold", "0",
        "-c:a", "aac", "-b:a", f"{lp.AUDIO_KBPS}k",
        "-ar", str(lp.AUDIO_HZ), "-ac", "2",
        # exactly length*FPS frames: the concat list's doubled last frame made one extra,
        # a duplicate timestamp at the next seam (measured in the first local session)
        "-frames:v", str(length * fps),
        "-t", str(length), "-muxdelay", "0", "-muxpreload", "0", "-f", "mpegts", out_ts,
    ]


def remux_args(seg_ts: str, offset: float, ffmpeg: str = "ffmpeg") -> list:
    """Shift a finished segment onto the running timeline without re-encoding."""
    return [ffmpeg, "-hide_banner", "-loglevel", "error", "-i", seg_ts, "-map", "0",
            "-c", "copy", "-output_ts_offset", f"{offset:.3f}",
            "-muxdelay", "0", "-muxpreload", "0", "-f", "mpegts", "pipe:1"]


def stream_args(dest: str, ffmpeg: str = "ffmpeg") -> list:
    """The one long-lived connection. -re paces the pipe at real time; video is copied,
    audio is re-encoded through aresample so a few ms of AAC priming at each segment
    seam cannot put the audio clock out of order."""
    return [ffmpeg, "-hide_banner", "-loglevel", "warning", "-re",
            "-f", "mpegts", "-i", "pipe:0", "-map", "0:v", "-map", "0:a",
            "-c:v", "copy",
            # min_hard_comp 0.01: trim the ~23 ms of AAC priming that overlaps each seam;
            # the default 0.1 s only stretched it and the encoder saw time run backwards
            "-af", "aresample=async=1000:min_hard_comp=0.01:first_pts=0",
            "-c:a", "aac", "-b:a", f"{lp.AUDIO_KBPS}k",
            "-ar", str(lp.AUDIO_HZ), "-ac", "2",
            "-f", "flv", dest]


def kind_of(i: int) -> str:
    """Segment i (0-based) is a board every BOARD_EVERY-th time (row 10)."""
    return "board" if (i + 1) % rd.BOARD_EVERY == 0 else "spotlight"


def board_sig(rows: list) -> tuple:
    return tuple((r["id"], r["number"]) for r in rows)


# ------------------------------------------------------------------ logging
def log(msg: str) -> None:
    line = f"{datetime.now(timezone.utc):%Y-%m-%d %H:%M:%S}Z {redact(msg)}"
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


def keep_awake(on: bool) -> None:
    """Row 23: hold the machine awake only while a session runs."""
    try:
        es_continuous, es_system = 0x80000000, 0x00000001
        flags = es_continuous | es_system if on else es_continuous
        ctypes.windll.kernel32.SetThreadExecutionState(flags)
    except Exception:  # noqa: BLE001 — not Windows, or no kernel32: nothing to hold
        pass


def media_seconds(path: str) -> float:
    try:
        r = subprocess.run([fv.FFPROBE or "ffprobe", "-v", "error", "-show_entries",
                            "format=duration", "-of", "default=nw=1:nk=1", path],
                           capture_output=True, text=True, timeout=60)
        return float(r.stdout.strip())
    except Exception:  # noqa: BLE001
        return 0.0


# ------------------------------------------------------------------ rendering
class Renderer:
    """One headless Chromium page for the whole session."""

    def __init__(self, page: Path = PAGE, size: tuple = (W, H)):
        # v3-T.1 reuses this renderer for its vertical page (trials_live.py)
        from playwright.sync_api import sync_playwright   # heavy, optional: import here
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch()
        self._page = self._browser.new_page(viewport={"width": size[0], "height": size[1]},
                                            device_scale_factor=1)
        self._page.goto(Path(page).resolve().as_uri())
        self._page.wait_for_function("window.__ready === true", timeout=15000)

    def frames(self, spec: dict, out_dir: Path) -> tuple:
        """([(png, t)], unfit fields) for one segment."""
        out_dir.mkdir(parents=True, exist_ok=True)
        unfit = self._page.evaluate("s => window.__load(s)", spec)
        shots = []
        # v3-T.1 passes its own list: its page has no moving clock to redraw every second
        times = spec.get("times") or rd.frame_times(spec["length"], spec["phrases"])
        cta = spec.get("cta")
        if cta:   # L6 row 8: the line must appear and leave on a frame of its own
            times = sorted(set(times) | {float(cta[0]), float(cta[1])})
            times = [t for t in times if t < spec["length"]]
        if spec.get("extra_times"):   # v3-T.1: timed state changes get a frame of their own
            times = sorted(set(times) | {float(x) for x in spec["extra_times"]
                                         if 0 <= float(x) < spec["length"]})
        for i, t in enumerate(times):
            self._page.evaluate("t => window.__seek(t)", t)
            p = out_dir / f"{i:05d}.png"
            self._page.screenshot(path=str(p))
            shots.append((str(p), t))
        return shots, list(unfit or [])

    def close(self):
        for f in (self._browser.close, self._pw.stop):
            try:
                f()
            except Exception:  # noqa: BLE001
                pass


def encode(renderer: Renderer, spec: dict, audio: str | None, out_dir: Path,
           music: str | None = None, music_at: float = 0.0,
           music_gain: float = MUSIC_VOLUME) -> str | None:
    from factverse import storyboard   # pure concat_list; heavy deps are lazy there too
    shots, unfit = renderer.frames(spec, out_dir)
    if unfit:
        log(f"  text did not fit at the floor: {unfit} (shown clipped)")
    lst = out_dir / "list.txt"
    lst.write_text(storyboard.concat_list(shots, spec["length"]), encoding="utf-8")
    ts = out_dir / "segment.ts"
    r = subprocess.run(segment_args(str(lst), audio, spec["length"], str(ts),
                                    fv.FFMPEG or "ffmpeg", music, music_at, music_gain,
                                    VOICE_GAIN_DB),
                       capture_output=True, text=True, timeout=600)
    if r.returncode != 0 or not ts.exists() or ts.stat().st_size < 10000:
        log(f"  segment encode failed: {(r.stderr or '')[-300:]}")
        return None
    return str(ts)


def voice(text: str, out_mp3: Path) -> tuple:
    """(words, seconds) or ([], 0) — edge-tts with the config voice (row 16)."""
    from factverse import captions
    out = {}

    def _synth():
        out["words"] = captions.synth_with_words(
            text, fv.setting("voice", "en-US-GuyNeural"), fv.setting("voice_rate", "+5%"),
            str(out_mp3))

    # edge-tts calls asyncio.run(), which refuses to run inside Playwright's event loop
    # on the producer thread — measured: every spotlight failed. A fresh thread has none.
    t = threading.Thread(target=_synth, daemon=True)
    t.start()
    t.join(timeout=TTS_SECONDS)
    words = out.get("words") or []
    secs = media_seconds(str(out_mp3)) if out_mp3.exists() else 0.0
    return (words, secs) if words and secs > 0 else ([], 0.0)


# ------------------------------------------------------------------ producer
class Producer:
    """Runs in its own PROCESS (producer_main). As a thread it shared the sender's GIL:
    while Playwright decoded screenshots the writer thread could not keep the pipe full
    and ffmpeg logged 0.4-0.8 s input lags in the first 6-minute local session."""

    def __init__(self, q, stop, history: dict, delay: float = 0.0, wrap=None,
                 daily_at: str = ""):
        self.q, self.stop, self.delay = q, stop, delay
        self.wrap, self.daily_at = wrap, daily_at
        self.history_at_start = dict(history)
        self.tools: list = []
        self.baseline: dict = {}
        self.spotlighted: set = set()
        self.last_refresh = 0.0
        self.as_of = None
        self.last_board = None
        self.have_llm = bool(fv.GEMINI_KEY)
        self.n = 0
        self.renderer = None
        self.error = ""
        self.failures = 0
        self.pool_size = 0
        self.standby = None
        self.music, self.music_len, self.music_clock = None, 0.0, 0.0
        self.music_gain = MUSIC_VOLUME
        self.timeline = 0.0           # seconds of produced segments (CTA clock, L6 row 8)
        self.next_cta = float(CTA_FIRST)
        self.next_tool = None         # L6 row 6: the tool the NEXT spotlight will show
        self.shown = 0

    def pick_music(self) -> None:
        """L6 row 10: the day's shuffled playlist, each track normalised to the bed level.
        Falls back to v3-L.3's one raw track at MUSIC_VOLUME if normalising fails."""
        tracks = playlist_order(MUSIC_DIR.glob("*.mp3"), datetime.now(IST).date())
        if not tracks:
            return
        mdir = LIVE_DIR / "music"
        shutil.rmtree(mdir, ignore_errors=True)
        mdir.mkdir(parents=True, exist_ok=True)
        done = []
        for i, src in enumerate(tracks):
            dst = mdir / f"{i:02d}.wav"
            try:
                r = subprocess.run(normalize_args(src, str(dst), fv.FFMPEG or "ffmpeg"),
                                   capture_output=True, timeout=300)
                if r.returncode == 0 and dst.exists() and media_seconds(str(dst)) > 1:
                    done.append(str(dst))
            except Exception:  # noqa: BLE001
                pass
        if done:
            pl = mdir / "playlist.ffconcat"
            pl.write_text(concat_playlist(done), encoding="utf-8")
            self.music_len = sum(media_seconds(p) for p in done)
            self.music, self.music_gain = str(pl), 1.0
            log(f"  music: {len(done)} tracks, {self.music_len / 60:.1f} min, "
                f"normalised to {MUSIC_TARGET_LUFS} LUFS: "
                + ", ".join(Path(t).stem for t in tracks))
            return
        track = pick_track(tracks, datetime.now().timetuple().tm_yday)
        secs = media_seconds(track) if track else 0.0
        if track and secs > 1:
            self.music, self.music_len = track, secs
            log(f"  music bed (not normalised): {Path(track).name}")

    def _encode(self, spec: dict, audio: str | None, d: Path) -> str | None:
        """encode() with the bed continued from where the previous segment left it."""
        at = self.music_clock % self.music_len if self.music else 0.0
        ts = encode(self.renderer, spec, audio, d, self.music, at, self.music_gain)
        if ts:
            self.music_clock += spec["length"]
            self.timeline += spec["length"]
        return ts

    def refresh(self, force: bool = False) -> None:
        if not force and time.monotonic() - self.last_refresh < REFRESH_SECONDS:
            return
        self.last_refresh = time.monotonic()
        gh, hf = rd.fetch_github_wide(), rd.fetch_hf_wide()
        if gh is None and hf is None:
            log("  data refresh failed on both sources; keeping the last data")
            return
        merged = {t["id"]: t for t in self.tools}
        # a source that failed keeps its previous tools; a source that answered replaces them
        for kinds, fresh_list in ((("github",), gh), (("hf", "space"), hf)):
            if fresh_list is not None:
                merged = {k: v for k, v in merged.items() if v["kind"] not in kinds}
                merged.update({t["id"]: t for t in fresh_list})
        kept, dropped = rd.screen(list(merged.values()))
        self.tools = kept
        rd.update_baseline(self.baseline, kept)
        self.as_of = datetime.now(timezone.utc)
        log(f"  data refreshed: {len(kept)} tools ({len(dropped)} screened out; "
            f"github {'ok' if gh is not None else 'FAILED'}, hf {'ok' if hf is not None else 'FAILED'})")

    def candidates(self) -> list:
        now = datetime.now(timezone.utc)
        return [t for t in rd.fresh(self.tools, self.history_at_start, self.spotlighted, now)
                if rd.spotlightable(t, self.have_llm)]

    def _spec(self, kind: str, phrases: list, length: int, tool=None, rank_no=0,
              use_it_for: str = "") -> dict:
        now = datetime.now(timezone.utc)
        sections = rd.board_sections(self.tools, self.baseline,
                                     n=rd.SECTION_SIZE if kind == "spotlight" else rd.BIG_SECTION_SIZE,
                                     include=tool["id"] if tool else None)
        cta = None
        if kind in ("spotlight", "board"):
            cta, self.next_cta = cta_window(self.timeline, length, self.next_cta)
        nxt = self.next_tool
        spec = {"type": kind, "as_of": f"{self.as_of:%H:%M} UTC" if self.as_of else "",
                "stale": rd.is_stale(self.as_of, now), "sections": sections,
                "phrases": [list(p) for p in phrases], "length": length,
                "next": nxt["name"] if (nxt and kind != "end") else "",
                "cta": list(cta) if cta else None, "cta_text": CTA_TEXT}
        if tool:
            spec.update({
                "tool": {"kind": tool["kind"], "name": tool["name"], "desc": tool["desc"],
                         "url_text": tool["url"].replace("https://", ""),
                         "label": rd.kind_label(tool), "use_it_for": use_it_for},
                "facts": rd.chips(tool, self.history_at_start),
                "status": rd.status_label(tool, self.history_at_start),
                "rank_label": f"#{rank_no} {rd.kind_label(tool)}"
                              + (" · ★/DAY" if tool["kind"] == "github" else " · TRENDING"),
                "highlight": tool["id"]})
        return spec

    def _pick_next(self, cands: list) -> dict:
        """L6 row 6: the spotlight shows the tool it reserved last time, when that tool is
        still a candidate, so the "NEXT" line on the previous frame comes true."""
        if self.next_tool and any(c["id"] == self.next_tool["id"] for c in cands):
            return next(c for c in cands if c["id"] == self.next_tool["id"])
        return cands[0]

    def make_spotlight(self, d: Path):
        cands = self.candidates()
        if not cands:
            return "exhausted"
        tool = self._pick_next(cands)
        self.spotlighted.add(tool["id"])
        rest = [c for c in cands if c["id"] != tool["id"]]
        self.next_tool = rest[0] if rest else None
        rank_no = rd.section_rank(self.tools, tool)
        text, source, use_it = None, "template", ""
        if self.have_llm:
            readme = rd.fetch_readme(tool)
            got = rd.llm_spotlight(tool, rd.facts(tool, self.history_at_start), readme)
            if got:
                text, use_it, source = got["narration"], got["use_it_for"], "llm"
        if not text:
            if tool["kind"] == "github" and not rd.spoken_description(tool.get("desc", "")):
                return None                  # no written narration and nothing readable
            text = rd.template_narration(tool, rank_no, self.history_at_start)
        words, secs = voice(text, d / "voice.mp3")
        if not words:
            # usually the network: put the tool back; MAX_FAILURES ends a dead session
            self.spotlighted.discard(tool["id"])
            self.next_tool = tool
            log(f"  voice failed for {tool['id']}")
            return None
        length = rd.segment_seconds(secs)
        spec = self._spec("spotlight", rd.phrases(rd.punctuate(words, text)), length, tool,
                          rank_no, use_it)
        ts = self._encode(spec, str(d / "voice.mp3"), d)
        if ts:
            self.shown += 1
        return {"ts": ts, "length": length, "kind": "spotlight", "tool": tool,
                "narration": source, "cta": bool(spec["cta"])} if ts else None

    def make_board(self, d: Path):
        sections = rd.board_sections(self.tools, self.baseline, n=rd.BIG_SECTION_SIZE)
        sig = board_sig(sections["github"] + sections["hf"])
        phrases, audio = [], None
        if sig and sig != self.last_board:
            text = rd.sections_narration(sections, self.as_of or datetime.now(timezone.utc))
            words, secs = voice(text, d / "voice.mp3")
            if words:
                phrases, audio = rd.phrases(rd.punctuate(words, text)), str(d / "voice.mp3")
                self.last_board = sig
        length = rd.BOARD_SECONDS
        spec = self._spec("board", phrases, length)
        ts = self._encode(spec, audio, d)
        return {"ts": ts, "length": length, "kind": "board", "tool": None,
                "cta": bool(spec["cta"])} if ts else None

    def make_standby(self) -> dict | None:
        d = LIVE_DIR / "standby"
        shutil.rmtree(d, ignore_errors=True)
        ts = encode(self.renderer, self._spec("standby", [], STANDBY_SECONDS), None, d,
                    self.music, 0.0, self.music_gain)
        return {"ts": ts, "length": STANDBY_SECONDS, "kind": "standby", "tool": None} if ts else None

    def make_end(self, reason: str) -> dict | None:
        """L6 row 9: a voiced end card with the true stop reason, then the session ends."""
        d = LIVE_DIR / "end"
        shutil.rmtree(d, ignore_errors=True)
        d.mkdir(parents=True, exist_ok=True)
        text = rd.end_narration(self.shown, reason, self.daily_at)
        words, secs = voice(text, d / "voice.mp3")
        phrases = rd.phrases(rd.punctuate(words, text)) if words else []
        length = max(STANDBY_SECONDS, rd.segment_seconds(secs)) if words else STANDBY_SECONDS
        spec = self._spec("end", phrases, length)
        spec.update({"end_reason": reason, "end_count": self.shown,
                     "end_daily": self.daily_at})
        ts = self._encode(spec, str(d / "voice.mp3") if words else None, d)
        return {"ts": ts, "length": length, "kind": "end", "tool": None,
                "reason": reason} if ts else None

    def run(self):
        try:
            # Playwright's sync objects belong to the thread that made them, so the
            # browser is created, used and closed here, never on the sender's thread
            self.renderer = Renderer()
            self.pick_music()
            self.refresh(force=True)
            self.pool_size = len(self.candidates())
            if self.pool_size >= rd.MIN_FRESH:
                self.standby = self.make_standby()
            self._put({"ready": True, "pool": self.pool_size, "standby": self.standby,
                       "have_llm": self.have_llm, "error": ""})
            if self.pool_size < rd.MIN_FRESH or not self.standby:
                return
            while not self.stop.is_set():
                if self.wrap is not None and self.wrap.is_set():
                    log("  target length reached; rendering the end card")
                    self._finish("time")
                    return
                self.refresh()
                if self.delay:
                    time.sleep(self.delay)        # test hook: forces the standby path
                d = LIVE_DIR / f"seg_{self.n:04d}"
                shutil.rmtree(d, ignore_errors=True)
                d.mkdir(parents=True, exist_ok=True)
                kind = kind_of(self.n)
                self.n += 1
                seg = self.make_board(d) if kind == "board" else self.make_spotlight(d)
                if seg == "exhausted":
                    log("  fresh pool exhausted; ending the session after what is queued")
                    self._finish("exhausted")
                    return
                if seg:
                    if kind == "spotlight":
                        self.failures = 0     # only a spotlight proves voice + render work
                    self._put(seg)
                else:
                    self.failures += 1
                    if self.failures >= MAX_FAILURES:
                        self.error = f"{self.failures} segments in a row failed"
                        log(f"  {self.error}; ending the session")
                        self._put(None)
                        return
        except Exception as e:  # noqa: BLE001 — the sender ends the session cleanly
            self.error = f"{type(e).__name__}: {str(e)[:200]}"
            log(f"  producer failed: {self.error}")
            self._put({"ready": True, "pool": self.pool_size, "standby": None,
                       "have_llm": self.have_llm, "error": self.error})
            self._put(None)
        finally:
            if self.renderer:
                self.renderer.close()

    def _finish(self, reason: str) -> None:
        end = None
        try:
            end = self.make_end(reason)
        except Exception as e:  # noqa: BLE001 — a missing end card must not cost the session
            log(f"  end card failed: {type(e).__name__}")
        if end:
            self._put(end)
        self._put(None)

    def _put(self, item):
        while not self.stop.is_set():
            try:
                self.q.put(item, timeout=1.0)
                return
            except queue.Full:
                continue


def producer_main(q, stop, history: dict, delay: float, wrap=None,
                  daily_at: str = "") -> None:
    """Child-process entry point (must be top level so Windows' spawn can pickle it)."""
    Producer(q, stop, history, delay, wrap, daily_at).run()


# ------------------------------------------------------------------ sender
class Streamer:
    """One ffmpeg connection plus a writer thread.

    An OS pipe holds almost nothing, so ffmpeg (-re) runs dry the moment a write ends:
    the first local session measured a 2.2 s input gap after a standby. The writer
    therefore always has the NEXT remuxed segment waiting in `wq` while it writes the
    current one, and the sender only falls back to standby when that reserve is gone."""

    def __init__(self, dest: str):
        self.dest = dest
        self.proc = None
        self.tail: list = []
        self.seam_flags = 0
        self.wq: queue.Queue = queue.Queue(maxsize=1)
        self.broken = threading.Event()
        self._writer = None

    def start(self) -> None:
        self.proc = subprocess.Popen(stream_args(self.dest, fv.FFMPEG or "ffmpeg"),
                                     stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                                     stderr=subprocess.PIPE)
        threading.Thread(target=self._drain, daemon=True).start()
        self._writer = threading.Thread(target=self._write, daemon=True)
        self._writer.start()

    def _drain(self) -> None:
        # ffmpeg prints the output URL - with the key in it - so every line is redacted,
        # and the pipe must be drained or ffmpeg blocks once it fills
        for raw in iter(self.proc.stderr.readline, b""):
            line = redact(raw.decode("utf-8", "replace").rstrip())
            if any(n in line for n in SEAM_NOISE):
                self.seam_flags += 1
                continue
            if line:
                self.tail = (self.tail + [line])[-20:]
                log(f"  ffmpeg: {line}")

    def _write(self) -> None:
        while True:
            data = self.wq.get()
            if data is None:
                return
            try:
                self.proc.stdin.write(data)
                self.proc.stdin.flush()
            except (OSError, ValueError):
                self.broken.set()
                return

    def put(self, data) -> bool:
        while not self.broken.is_set():
            try:
                self.wq.put(data, timeout=0.5)
                return True
            except queue.Full:
                continue
        return False

    def starving(self) -> bool:
        """True when nothing waits behind the segment now being written."""
        return self.wq.empty()

    def finish(self, wait: float = 30.0):
        if not self.proc:
            return None
        if not self.broken.is_set():
            self.put(None)
            if self._writer:
                # the writer may still be pacing out up to two queued segments
                self._writer.join(timeout=wait + 240)
        try:
            self.proc.stdin.close()
        except Exception:  # noqa: BLE001
            pass
        try:
            return self.proc.wait(timeout=wait)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            return self.proc.wait()


def preroll(get, n: int, timeout: float, clock=time.monotonic) -> tuple:
    """v3l3 row 1: wait for up to `n` real segments before the connection opens, so a
    session never starts with one segment in hand and standby behind it (the first
    private YouTube session showed 3 standbys in its first minute). Returns
    (segments, producer_ended, producer_error); stops early at `timeout`."""
    got, error, end = [], "", clock() + timeout
    while len(got) < n:
        left = end - clock()
        if left <= 0:
            break
        try:
            item = get(timeout=left)
        except queue.Empty:
            break
        if item is None:
            return got, True, error
        if isinstance(item, dict) and item.get("ready"):
            error = item.get("error", "") or error     # a late failure report
            continue
        got.append(item)
    return got, False, error


def remux(seg: dict, offset: float) -> bytes:
    r = subprocess.run(remux_args(seg["ts"], offset, fv.FFMPEG or "ffmpeg"),
                       capture_output=True, timeout=120)
    return r.stdout if r.returncode == 0 else b""


def run_session(dest: str, minutes: float, max_segments: int, producer_delay: float,
                daily_at: str = "") -> dict:
    LIVE_DIR.mkdir(parents=True, exist_ok=True)
    history = rd.load_json(HISTORY, {})
    summary = {"start": datetime.now(timezone.utc).isoformat(timespec="seconds"),
               "target_minutes": minutes, "segments": 0, "standby": 0, "restarts": 0,
               "seconds": 0, "tools": [], "narration": {"llm": 0, "template": 0},
               "cta": 0, "stop_reason": "", "remux_max_s": 0.0, "status": "ok"}
    q = mp.Queue(maxsize=QUEUE_DEPTH)
    stop = mp.Event()
    wrap = mp.Event()
    prod = mp.Process(target=producer_main,
                      args=(q, stop, history, producer_delay, wrap, daily_at), daemon=True)
    streamer = None
    producer_error = ""
    try:
        prod.start()
        try:
            hello = q.get(timeout=READY_TIMEOUT)
        except queue.Empty:
            summary["status"] = "failed: producer not ready"
            return summary
        if not isinstance(hello, dict) or not hello.get("ready"):
            summary["status"] = "failed: producer said nothing usable"
            return summary
        log(f"session start: {hello['pool']} fresh tools, "
            f"narration={'llm' if hello['have_llm'] else 'template'}")
        if hello["error"]:
            summary["status"] = f"failed: {hello['error']}"
            return summary
        if hello["pool"] < rd.MIN_FRESH:
            summary["status"] = f"skipped: {hello['pool']} fresh tools < {rd.MIN_FRESH}"
            log(summary["status"])
            return summary
        standby = hello["standby"]
        if not standby:
            summary["status"] = "failed: standby segment did not render"
            return summary
        # connect only once PREROLL real segments exist, so a session opens on a
        # spotlight with the next ones already written (v3l3 row 1)
        pending, ended, producer_error = preroll(q.get, PREROLL, READY_TIMEOUT)
        if not pending:
            summary["status"] = "failed: no first segment" + (
                f" ({producer_error})" if producer_error else "")
            return summary
        if ended:
            pending.append(None)
        log(f"  pre-roll: {len([p for p in pending if p])} segments ready")
        streamer = Streamer(dest)
        streamer.start()
        # L6 row 9: the producer is asked for its end card WRAP_LEAD s before the target;
        # the wall clock is only a backstop (OVERRUN) for a producer that stopped answering
        target_s = minutes * 60
        offset, deadline = 0.0, time.monotonic() + target_s + OVERRUN
        while time.monotonic() < deadline:
            if max_segments and summary["segments"] >= max_segments:
                break
            if not wrap.is_set() and wrap_due(summary["seconds"], target_s):
                wrap.set()
                log(f"  {summary['seconds']}s streamed of {target_s:.0f}s: asking for the end card")
            if streamer.broken.is_set():
                if summary["restarts"] >= RESTARTS:
                    summary["status"] = "ended: streamer kept failing"
                    log(summary["status"])
                    break
                summary["restarts"] += 1
                log(f"  streamer exited; restart {summary['restarts']}/{RESTARTS} in {RESTART_WAIT}s")
                streamer.finish(wait=5)
                time.sleep(RESTART_WAIT)
                streamer = Streamer(dest)
                streamer.start()
                offset = 0.0              # a new connection is a new timeline
                continue
            try:
                seg = pending.pop(0) if pending else q.get(timeout=0.5)
            except queue.Empty:
                if not streamer.starving():
                    continue              # a whole segment is still in reserve: keep waiting
                seg = standby
            if seg is None:
                break
            if seg.get("ready"):
                producer_error = seg.get("error", "")   # a late failure report
                continue
            t_remux = time.monotonic()
            data = remux(seg, offset)
            summary["remux_max_s"] = round(max(summary["remux_max_s"],
                                               time.monotonic() - t_remux), 2)
            if seg["kind"] != "standby":
                shutil.rmtree(Path(seg["ts"]).parent, ignore_errors=True)
            if not data:
                log(f"  remux failed for a {seg['kind']} segment; skipping it")
                continue
            if not streamer.put(data):
                continue                  # the writer broke; the top of the loop restarts
            offset += seg["length"]
            summary["seconds"] += seg["length"]
            summary["cta"] += 1 if seg.get("cta") else 0
            if seg["kind"] == "standby":
                summary["standby"] += 1
            elif seg["kind"] == "end":
                summary["stop_reason"] = seg.get("reason", "")
                log(f"  queued end card ({seg['length']}s, {summary['stop_reason']})")
                break
            else:
                summary["segments"] += 1
                if seg.get("tool"):
                    rd.remember(history, seg["tool"], datetime.now(timezone.utc))
                    summary["tools"].append(seg["tool"]["id"])
                    summary["narration"][seg.get("narration", "template")] += 1
                    HISTORY.write_text(json.dumps(history, indent=1), encoding="utf-8")
            log(f"  queued {seg['kind']} ({seg['length']}s) - timeline {offset:.0f}s")
        if not summary["stop_reason"]:
            summary["stop_reason"] = "deadline" if time.monotonic() >= deadline else "producer ended"
        if producer_error:
            summary["status"] = f"ended: producer failed ({producer_error})"
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


def fetch_manifest() -> dict | None:
    """Today's CI manifest (L7), or None. Read-only, public, fail-soft: no manifest means
    the session runs at the config length exactly as before."""
    try:
        import requests
        r = requests.get(MANIFEST_URL, timeout=15)
        data = r.json() if r.status_code == 200 else None
    except Exception:  # noqa: BLE001
        return None
    return manifest_for_today(data, datetime.now(IST).date())


def schedule_installed() -> bool:
    """The end card promises tomorrow's session only when the daily task really exists.
    On the ToolDojo Node (v3-N.1) the supervisor's job table IS the schedule, and it says
    so through TOOLDOJO_NODE_SCHEDULED=1 for a job that repeats."""
    if os.environ.get("TOOLDOJO_NODE_SCHEDULED") == "1":
        return True
    try:
        r = subprocess.run(["schtasks", "/Query", "/TN", "ToolDojo Radar Live"],
                           capture_output=True, timeout=20)
        return r.returncode == 0
    except Exception:  # noqa: BLE001
        return False


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--minutes", type=float, default=None)
    ap.add_argument("--out", help="local test target (a file or rtmp://127.0.0.1/...); "
                                  "never needs the stream key")
    ap.add_argument("--segments", type=int, default=0, help="stop after N segments (testing)")
    ap.add_argument("--producer-delay", type=float, default=0.0, help=argparse.SUPPRESS)
    a = ap.parse_args(argv)
    summary = {"status": "not started"}
    try:
        if a.out:
            if "youtube.com" in a.out.lower():
                log("--out is for local tests; YouTube is reached only through .env")
                return 2
            dest = a.out
        else:
            # config.py has already loaded the local .env into os.environ
            url = os.environ.get("YT_STREAM_URL", "")
            key = os.environ.get("YT_STREAM_KEY", "")
            if not key:
                log("no YT_STREAM_KEY in .env: Radar Live is off (spec row 26)")
                return 0
            _SECRETS.append(key)
            if not valid_ingest(url):
                log("YT_STREAM_URL must be the rtmps:// Stream URL from YouTube Studio "
                    "(host *.youtube.com) - refusing to send the key anywhere else")
                return 2
            dest = ingest_target(url, key)
        # only a real session reads the manifest; a local test never touches the network here
        manifest = None if (a.out or a.minutes is not None) else fetch_manifest()
        minutes = session_minutes(a.minutes, manifest,
                                  fv.setting("radar_session_minutes", SESSION_MINUTES))
        log(f"target: {minutes:.0f} min"
            + (f" (CI manifest, stage {manifest['stage']}, broadcast {manifest['broadcast_id']})"
               if manifest else " (no manifest for today)"))
        daily_at = fv.setting("radar_daily_at_spoken", "8 PM") if schedule_installed() else ""
        keep_awake(True)
        summary = run_session(dest, minutes, a.segments, a.producer_delay, daily_at)
    except Exception as e:  # noqa: BLE001 — unattended: log, never crash the scheduler
        summary = {**summary, "status": f"crashed: {type(e).__name__}: {redact(str(e))[:200]}"}
        log(summary["status"])
    finally:
        keep_awake(False)
        try:
            SESSIONS.parent.mkdir(parents=True, exist_ok=True)
            with SESSIONS.open("a", encoding="utf-8") as f:
                f.write(redact(json.dumps(summary)) + "\n")
        except Exception:  # noqa: BLE001
            pass
    log(f"session end: {summary.get('status')} · {summary.get('segments', 0)} segments · "
        f"{summary.get('standby', 0)} standby · {summary.get('restarts', 0)} restarts")
    return 0 if str(summary.get("status", "")).startswith(("ok", "skipped")) else 1


if __name__ == "__main__":
    sys.exit(main())

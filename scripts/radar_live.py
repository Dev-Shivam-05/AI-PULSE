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
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from factverse import config as fv          # noqa: E402
from factverse import radar as rd           # noqa: E402
import live_preflight as lp                 # noqa: E402

PROFILE = lp.PROFILES["1080p30"]            # spec row 2
W, H, FPS = PROFILE["w"], PROFILE["h"], PROFILE["fps"]
CRF = "20"                                  # row 3: the storyboard's CRF (v3g1 row 7)
SESSION_MINUTES = 120                       # row 4
QUEUE_DEPTH = 3                             # row 19
STANDBY_SECONDS = 10                        # row 20
RESTARTS, RESTART_WAIT = 5, 10              # row 21
REFRESH_SECONDS = 15 * 60                   # row 8
READY_TIMEOUT = 300  # first data fetch + browser + standby render, before giving up
TTS_SECONDS = 120    # wall clock for one narration
MAX_FAILURES = 5     # row 21a: consecutive failed segments end the session
# Each remuxed segment restarts its TS continuity counters, so the demuxer flags the
# seam packet; decoding the received stream shows no damage. Counted, not logged.
SEAM_NOISE = ("Packet corrupt", "corrupt input packet")

LIVE_DIR = fv.TEMP / "live"
HISTORY = LIVE_DIR / "radar_history.json"
LOG = fv.LOGS / "radar_live.log"
SESSIONS = fv.LOGS / "radar_sessions.jsonl"
PAGE = fv.ASSETS / "radar" / "radar.html"

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


def segment_args(concat_path: str, audio: str | None, length: int, out_ts: str,
                 ffmpeg: str = "ffmpeg") -> list:
    """One segment, encoded once at timeline 0. Exactly `length` seconds (an even
    number, row 11) so the 2 s GOPs tile the whole stream."""
    gop = FPS * lp.KEYFRAME_S
    cap = f"{PROFILE['kbps']}k"
    audio_in = (["-i", audio] if audio else
                ["-f", "lavfi", "-i", f"anullsrc=r={lp.AUDIO_HZ}:cl=stereo"])
    return [
        ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
        "-f", "concat", "-safe", "0", "-i", concat_path, *audio_in,
        "-map", "0:v", "-map", "1:a",
        "-vf", f"fps={FPS},format=yuv420p",
        "-c:v", "libx264", "-preset", lp.X264_PRESET, "-profile:v", "high", "-crf", CRF,
        # no B-frames: with them a segment's first DTS is negative, and after the offset
        # it lands before the previous segment's last one (measured at the 10 s seam)
        "-bf", "0",
        "-maxrate", cap, "-bufsize", cap,
        "-g", str(gop), "-keyint_min", str(gop), "-sc_threshold", "0",
        "-af", "apad", "-c:a", "aac", "-b:a", f"{lp.AUDIO_KBPS}k",
        "-ar", str(lp.AUDIO_HZ), "-ac", "2",
        # exactly length*FPS frames: the concat list's doubled last frame made one extra,
        # a duplicate timestamp at the next seam (measured in the first local session)
        "-frames:v", str(length * FPS),
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

    def __init__(self):
        from playwright.sync_api import sync_playwright   # heavy, optional: import here
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch()
        self._page = self._browser.new_page(viewport={"width": W, "height": H},
                                            device_scale_factor=1)
        self._page.goto(PAGE.resolve().as_uri())
        self._page.wait_for_function("window.__ready === true", timeout=15000)

    def frames(self, spec: dict, out_dir: Path) -> tuple:
        """([(png, t)], unfit fields) for one segment."""
        out_dir.mkdir(parents=True, exist_ok=True)
        unfit = self._page.evaluate("s => window.__load(s)", spec)
        shots = []
        for i, t in enumerate(rd.frame_times(spec["length"], spec["phrases"])):
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


def encode(renderer: Renderer, spec: dict, audio: str | None, out_dir: Path) -> str | None:
    from factverse import storyboard   # pure concat_list; heavy deps are lazy there too
    shots, unfit = renderer.frames(spec, out_dir)
    if unfit:
        log(f"  text did not fit at the floor: {unfit} (shown clipped)")
    lst = out_dir / "list.txt"
    lst.write_text(storyboard.concat_list(shots, spec["length"]), encoding="utf-8")
    ts = out_dir / "segment.ts"
    r = subprocess.run(segment_args(str(lst), audio, spec["length"], str(ts),
                                    fv.FFMPEG or "ffmpeg"),
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

    def __init__(self, q, stop, history: dict, delay: float = 0.0):
        self.q, self.stop, self.delay = q, stop, delay
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

    def refresh(self, force: bool = False) -> None:
        if not force and time.monotonic() - self.last_refresh < REFRESH_SECONDS:
            return
        self.last_refresh = time.monotonic()
        gh, hf = rd.fetch_github(), rd.fetch_hf()
        if gh is None and hf is None:
            log("  data refresh failed on both sources; keeping the last data")
            return
        merged = {t["id"]: t for t in self.tools}
        # a source that failed keeps its previous tools; a source that answered replaces them
        for kind, fresh_list in (("github", gh), ("hf", hf)):
            if fresh_list is not None:
                merged = {k: v for k, v in merged.items() if v["kind"] != kind}
                merged.update({t["id"]: t for t in fresh_list})
        kept, dropped = rd.screen(list(merged.values()))
        self.tools = kept
        rd.update_baseline(self.baseline, kept)
        self.as_of = datetime.now(timezone.utc)
        log(f"  data refreshed: {len(kept)} tools ({len(dropped)} screened out)")

    def candidates(self) -> list:
        now = datetime.now(timezone.utc)
        return [t for t in rd.fresh(self.tools, self.history_at_start, self.spotlighted, now)
                if rd.spotlightable(t, self.have_llm)]

    def _spec(self, kind: str, phrases: list, length: int, tool=None, rank_no=0) -> dict:
        rows = rd.board_rows(self.tools, self.baseline,
                             include=tool["id"] if tool else None)
        spec = {"type": kind, "as_of": f"{self.as_of:%H:%M} UTC" if self.as_of else "",
                "board": rows, "phrases": [list(p) for p in phrases], "length": length}
        if tool:
            prev = self.history_at_start.get(tool["id"])
            spec.update({
                "tool": {"kind": tool["kind"], "name": tool["name"], "desc": tool["desc"],
                         "url_text": tool["url"].replace("https://", "")},
                "facts": rd.chips(tool, self.history_at_start),
                "rank_label": "BACK ON THE RADAR" if prev else f"#{rank_no} ON THE RADAR",
                "highlight": tool["id"]})
        return spec

    def make_spotlight(self, d: Path):
        cands = self.candidates()
        if not cands:
            return "exhausted"
        tool = cands[0]
        self.spotlighted.add(tool["id"])
        ranked = rd.rank(self.tools)
        rank_no = next((i for i, t in enumerate(ranked, 1) if t["id"] == tool["id"]), 0)
        text, source = None, "template"
        if self.have_llm:
            readme = rd.fetch_readme(tool)
            text = rd.llm_narration(tool, rd.facts(tool, self.history_at_start), readme)
            source = "llm" if text else "template"
        if not text:
            if not rd.readable(tool.get("desc", "")) and tool["kind"] == "github":
                return None                  # no written narration and nothing readable
            text = rd.template_narration(tool, rank_no, self.history_at_start)
        words, secs = voice(text, d / "voice.mp3")
        if not words:
            # usually the network: put the tool back; MAX_FAILURES ends a dead session
            self.spotlighted.discard(tool["id"])
            log(f"  voice failed for {tool['id']}")
            return None
        length = rd.segment_seconds(secs)
        spec = self._spec("spotlight", rd.phrases(rd.punctuate(words, text)), length, tool,
                          rank_no)
        ts = encode(self.renderer, spec, str(d / "voice.mp3"), d)
        return {"ts": ts, "length": length, "kind": "spotlight", "tool": tool,
                "narration": source} if ts else None

    def make_board(self, d: Path):
        rows = rd.board_rows(self.tools, self.baseline)
        phrases, audio = [], None
        if rows and board_sig(rows) != self.last_board:
            text = rd.board_narration(rows, self.as_of or datetime.now(timezone.utc))
            words, secs = voice(text, d / "voice.mp3")
            if words:
                phrases, audio = rd.phrases(rd.punctuate(words, text)), str(d / "voice.mp3")
                self.last_board = board_sig(rows)
        length = rd.BOARD_SECONDS
        spec = self._spec("board", phrases, length)
        ts = encode(self.renderer, spec, audio, d)
        return {"ts": ts, "length": length, "kind": "board", "tool": None} if ts else None

    def make_standby(self) -> dict | None:
        d = LIVE_DIR / "standby"
        shutil.rmtree(d, ignore_errors=True)
        ts = encode(self.renderer, self._spec("board", [], STANDBY_SECONDS), None, d)
        return {"ts": ts, "length": STANDBY_SECONDS, "kind": "standby", "tool": None} if ts else None

    def run(self):
        try:
            # Playwright's sync objects belong to the thread that made them, so the
            # browser is created, used and closed here, never on the sender's thread
            self.renderer = Renderer()
            self.refresh(force=True)
            self.pool_size = len(self.candidates())
            if self.pool_size >= rd.MIN_FRESH:
                self.standby = self.make_standby()
            self._put({"ready": True, "pool": self.pool_size, "standby": self.standby,
                       "have_llm": self.have_llm, "error": ""})
            if self.pool_size < rd.MIN_FRESH or not self.standby:
                return
            while not self.stop.is_set():
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
                    self._put(None)
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

    def _put(self, item):
        while not self.stop.is_set():
            try:
                self.q.put(item, timeout=1.0)
                return
            except queue.Full:
                continue


def producer_main(q, stop, history: dict, delay: float) -> None:
    """Child-process entry point (must be top level so Windows' spawn can pickle it)."""
    Producer(q, stop, history, delay).run()


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


def remux(seg: dict, offset: float) -> bytes:
    r = subprocess.run(remux_args(seg["ts"], offset, fv.FFMPEG or "ffmpeg"),
                       capture_output=True, timeout=120)
    return r.stdout if r.returncode == 0 else b""


def run_session(dest: str, minutes: float, max_segments: int, producer_delay: float) -> dict:
    LIVE_DIR.mkdir(parents=True, exist_ok=True)
    history = rd.load_json(HISTORY, {})
    summary = {"start": datetime.now(timezone.utc).isoformat(timespec="seconds"),
               "segments": 0, "standby": 0, "restarts": 0, "seconds": 0, "tools": [],
               "narration": {"llm": 0, "template": 0}, "status": "ok"}
    q = mp.Queue(maxsize=QUEUE_DEPTH)
    stop = mp.Event()
    prod = mp.Process(target=producer_main, args=(q, stop, history, producer_delay),
                      daemon=True)
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
        streamer = Streamer(dest)
        streamer.start()
        offset, deadline = 0.0, time.monotonic() + minutes * 60
        while time.monotonic() < deadline:
            if max_segments and summary["segments"] >= max_segments:
                break
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
                seg = q.get(timeout=0.5)
            except queue.Empty:
                if not streamer.starving():
                    continue              # a whole segment is still in reserve: keep waiting
                seg = standby
            if seg is None:
                break
            if seg.get("ready"):
                producer_error = seg.get("error", "")   # a late failure report
                continue
            data = remux(seg, offset)
            if seg["kind"] != "standby":
                shutil.rmtree(Path(seg["ts"]).parent, ignore_errors=True)
            if not data:
                log(f"  remux failed for a {seg['kind']} segment; skipping it")
                continue
            if not streamer.put(data):
                continue                  # the writer broke; the top of the loop restarts
            offset += seg["length"]
            summary["seconds"] += seg["length"]
            if seg["kind"] == "standby":
                summary["standby"] += 1
            else:
                summary["segments"] += 1
                if seg.get("tool"):
                    rd.remember(history, seg["tool"], datetime.now(timezone.utc))
                    summary["tools"].append(seg["tool"]["id"])
                    summary["narration"][seg.get("narration", "template")] += 1
                    HISTORY.write_text(json.dumps(history, indent=1), encoding="utf-8")
            log(f"  queued {seg['kind']} ({seg['length']}s) - timeline {offset:.0f}s")
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


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--minutes", type=float, default=SESSION_MINUTES)
    ap.add_argument("--out", help="local test target (a file or rtmp://127.0.0.1/...); "
                                  "never needs the stream key")
    ap.add_argument("--segments", type=int, default=0, help="stop after N segments (testing)")
    ap.add_argument("--producer-delay", type=float, default=0.0, help=argparse.SUPPRESS)
    a = ap.parse_args(argv)
    summary = {"status": "not started"}
    try:
        minutes = max(1.0, min(a.minutes, SESSION_MINUTES))
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
        keep_awake(True)
        summary = run_session(dest, minutes, a.segments, a.producer_delay)
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

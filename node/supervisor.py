"""
v3-N.1 ToolDojo Node supervisor (docs/spec/ai-pulse-v3n1.md).

One long-running, fail-soft process, started by the "ToolDojo Node" scheduled task at
system start-up (session 0, nobody signed in). It waits for the network, optionally
updates the code, runs the encoder preflight once, then runs the job table in
config.json (`node_jobs`): Radar Live daily, Live Trials on Saturday, anything else that
is "a command line + a schedule window + a max duration".

    pythonw node\\supervisor.py --data C:\\ToolDojo\\data       # what the task runs
    py -3 node/supervisor.py --data <tmp> --jobs <tmp>/jobs.json --run-for 120 \\
        --no-update --no-network-wait --no-preflight             # a foreground test

Rules it keeps (CLAUDE.md, spec section 4):
  * it never exits on an exception: every tick, every job and every housekeeping step is
    isolated, and the outer loop restarts the whole supervisor after 30 s if all else fails;
  * no child can ever open a window: CREATE_NO_WINDOW (a hidden console that grandchildren
    such as ffmpeg inherit - DETACHED_PROCESS is deliberately NOT used, because then every
    console grandchild would allocate a NEW, visible console), SW_HIDE, BelowNormal
    priority enforced on the whole process tree by a Job Object;
  * a secret never reaches a log line or an alert (`redact`);
  * stdlib only, so a broken venv or a bad update cannot take the supervisor down with it.
"""
from __future__ import annotations

import argparse
import json
import logging
import logging.handlers
import os
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

APP = Path(__file__).resolve().parent.parent
UTC = timezone.utc
DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")

# Spec section 3 (delegated defaults). config.json's node_* keys override every one.
DEFAULTS = {
    "node_enabled": True,
    "node_self_update": True,
    "node_update_branch": "main",
    "node_update_at_utc": "21:30",
    "node_import_check": ["factverse.config", "factverse.radar", "live_preflight",
                          "radar_live", "supervisor", "node_preflight"],
    "node_network_wait_max_s": 900,
    "node_network_hosts": ["www.youtube.com:443", "github.com:443"],
    "node_clock_url": "https://www.google.com/generate_204",
    "node_clock_max_skew_s": 120,
    "node_backoff_base_s": 30,
    "node_backoff_max_s": 600,
    "node_late_grace_s": 120,
    "node_disk_min_free_gb": 10,
    "node_disk_floor_gb": 3,
    "node_cleanup_globs": ["temp/live/seg_*", "temp/live/standby", "temp/live/end",
                           "temp/live/preflight_*", "temp/node_preflight"],
    "node_log_max_mb": 5,
    "node_log_keep": 3,
    "node_alert_telegram": True,
    "node_alert_after_failures": 2,
    "node_alert_max_per_day": 6,
    "node_stream_profile": "auto",
    "node_priority": "below_normal",
    "node_cpu_cap_percent": 0,
    "node_status_every_s": 15,
    "node_tick_s": 2,
    "node_jobs": [],
}
PRIORITIES = {"idle": 0x40, "below_normal": 0x4000, "normal": 0x20}
CREATE_NO_WINDOW = 0x08000000
CREATE_NEW_PROCESS_GROUP = 0x00000200
SECRET_KEY = re.compile(r"(KEY|TOKEN|SECRET|PASSWORD|PASS)$", re.I)
TELEGRAM_URL_TOKEN = re.compile(r"bot\d{5,}:[A-Za-z0-9_-]{20,}")
NAME_OK = re.compile(r"^[a-z0-9][a-z0-9_-]{0,39}$")
HHMM = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")
FALLBACK_PROFILE = {"stream_profile": "720p30", "encoder": "libx264",
                    "verdict": "no preflight yet: the most conservative profile"}

log = logging.getLogger("tooldojo.node")


# ================================================================== pure helpers
def redact(text, secrets=()) -> str:
    """Every known secret value, longest first (a short one inside a long one would
    otherwise cut it in half and leak the rest - notify._redact's rule), plus any
    Telegram bot token that appears in a URL even if we were never told its value."""
    s = str(text if text is not None else "")
    for v in sorted({str(x) for x in secrets if x and len(str(x)) >= 6}, key=len, reverse=True):
        s = s.replace(v, "***")
    return TELEGRAM_URL_TOKEN.sub("bot***", s)


def parse_dotenv(text: str) -> dict:
    """The same rules as factverse.config._load_dotenv."""
    out = {}
    for raw in str(text or "").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def secret_values(env: dict) -> list:
    return [v for k, v in env.items() if SECRET_KEY.search(k) and v and "PASTE" not in v]


def parse_job(raw) -> tuple:
    """(job, "") or (None, why). Config is human-edited: coerce, never trust the type."""
    if not isinstance(raw, dict):
        return None, "a job must be an object"
    name = str(raw.get("name", "")).strip().lower()
    if not NAME_OK.match(name):
        return None, f"bad job name {name!r}"
    cmd = raw.get("cmd")
    if isinstance(cmd, str):
        cmd = cmd.split()
    if not isinstance(cmd, list) or not cmd or not all(isinstance(c, (str, int, float)) for c in cmd):
        return None, f"{name}: cmd must be a non-empty list of strings"
    m = HHMM.match(str(raw.get("start_utc", "")).strip())
    if not m:
        return None, f"{name}: start_utc must be HH:MM (UTC)"
    days = raw.get("days", "daily")
    if isinstance(days, str):
        days = list(DAYS) if days.strip().lower() == "daily" else [d.strip() for d in days.split(",")]
    days = [str(d).strip().lower()[:3] for d in (days if isinstance(days, list) else [])]
    if not days or any(d not in DAYS for d in days):
        return None, f"{name}: days must be 'daily' or a list of mon..sun"

    def num(key, default, lo, hi):
        try:
            v = float(raw.get(key, default))
        except (TypeError, ValueError):
            v = float(default)
        if v != v or v in (float("inf"), float("-inf")):   # NaN / inf from a hand edit
            v = float(default)
        return max(lo, min(hi, v))

    slot = num("slot_minutes", 60, 1, 1380)
    env = raw.get("env") if isinstance(raw.get("env"), dict) else {}
    job = {
        "name": name,
        "enabled": bool(raw.get("enabled", True)) if not isinstance(raw.get("enabled"), str)
        else raw["enabled"].strip().lower() in ("1", "true", "yes", "on"),
        "stream": bool(raw.get("stream", False)),
        "cmd": [str(c) for c in cmd],
        "start": (int(m.group(1)), int(m.group(2))),
        "start_utc": m.group(0),
        "days": [d for d in DAYS if d in days],
        "slot_minutes": slot,
        "min_minutes": num("min_minutes", min(10, slot), 0, slot),
        "max_minutes": num("max_minutes", slot, 1, 1440),
        "lead_seconds": num("lead_seconds", 0, 0, 3600),
        "hang_seconds": num("hang_seconds", 600, 0, 86400),
        "attempts_per_day": int(num("attempts_per_day", 3, 1, 50)),
        "remaining_arg": str(raw.get("remaining_arg", "") or ""),
        # every day of the week = the job really is daily (the radar's end card says
        # "back every day" only then, L6 row 9)
        "daily": len(set(days)) == 7,
        "pulse_file": safe_relpath(raw.get("pulse_file", "")),
        "env": {str(k): str(v) for k, v in env.items()},
    }
    return job, ""


def parse_jobs(raw_list) -> tuple:
    """([jobs], [errors]). One bad row never stops the others (job isolation)."""
    jobs, errors, seen = [], [], set()
    for raw in raw_list if isinstance(raw_list, list) else []:
        job, err = parse_job(raw)
        if err:
            errors.append(err)
        elif job["name"] in seen:
            errors.append(f"{job['name']}: duplicate name, second row ignored")
        else:
            seen.add(job["name"])
            jobs.append(job)
    return jobs, errors


def slot_at(job: dict, now: datetime) -> dict | None:
    """The slot whose window contains `now`, or None. A slot opens `lead_seconds` before
    its start and closes `slot_minutes` after it; yesterday's slot is checked too, so a
    window that crosses midnight UTC still counts."""
    hh, mm = job["start"]
    for back in (1, 0):
        d = (now - timedelta(days=back)).date()
        if DAYS[d.weekday()] not in job["days"]:
            continue
        start = datetime(d.year, d.month, d.day, hh, mm, tzinfo=UTC)
        opens = start - timedelta(seconds=job["lead_seconds"])
        end = start + timedelta(minutes=job["slot_minutes"])
        if opens <= now < end:
            return {"key": start.strftime("%Y-%m-%dT%H:%MZ"), "start": start,
                    "opens": opens, "end": end}
    return None


def next_slot(job: dict, now: datetime) -> datetime | None:
    hh, mm = job["start"]
    for ahead in range(0, 9):
        d = (now + timedelta(days=ahead)).date()
        if DAYS[d.weekday()] not in job["days"]:
            continue
        opens = (datetime(d.year, d.month, d.day, hh, mm, tzinfo=UTC)
                 - timedelta(seconds=job["lead_seconds"]))
        if opens > now:
            return opens
    return None


def backoff(failures: int, base: float, cap: float) -> float:
    """30, 60, 120, 240, 480, 600, 600 ... seconds with the defaults."""
    if failures <= 0:
        return 0.0
    return float(min(cap, base * (2 ** min(failures - 1, 20))))


def new_job_state(key: str = "") -> dict:
    return {"slot": key, "attempts": 0, "failures": 0, "done": False, "skipped": "",
            "next_try": "", "running": False, "last_exit": None, "last_reason": "",
            "alerted": False, "started": ""}


def decide(job: dict, st: dict, now: datetime, slot: dict | None, stream_busy: str = "",
           disk_ok: bool = True, paused: str = "", hardware_ok: bool = True,
           grace_s: float = 120) -> tuple:
    """("start", extra_args) | ("wait", why) | ("skip", why) | ("idle", why).

    "skip" is final for this slot (logged once); "wait" is re-checked every tick.
    The power-cut resume rule lives here: inside the window with >= min_minutes left
    = start (a late start is told how long it has, when the job takes `remaining_arg`);
    less than that = skip, with the reason."""
    if not job["enabled"]:
        return "idle", "disabled in config"
    if slot is None:
        return "idle", "outside its window"
    if st.get("done"):
        return "idle", "done for this slot"
    if st.get("skipped"):
        return "idle", st["skipped"]
    if st.get("running"):
        return "idle", "running"
    if st.get("attempts", 0) >= job["attempts_per_day"]:
        return "skip", f"retry cap reached ({st['attempts']}/{job['attempts_per_day']} attempts)"
    left_min = (slot["end"] - now).total_seconds() / 60.0
    if left_min < job["min_minutes"]:
        return "skip", (f"only {left_min:.1f} min left of the {slot['key']} slot "
                        f"(needs {job['min_minutes']:.0f})")
    if paused:
        return "wait", paused
    nt = st.get("next_try")
    if nt:
        try:
            when = datetime.fromisoformat(nt)
            if now < when:
                return "wait", f"backing off until {when:%H:%M:%S}Z"
        except ValueError:
            pass
    if job["stream"] and not hardware_ok:
        return "skip", "the preflight verdict is 'insufficient' for streaming"
    if job["stream"] and not disk_ok:
        return "wait", "free disk below the floor"
    if job["stream"] and stream_busy and stream_busy != job["name"]:
        return "wait", f"{stream_busy} holds the stream (never two at once)"
    extra = []
    late_s = (now - slot["start"]).total_seconds()
    if job["remaining_arg"] and late_s > grace_s:
        extra = [job["remaining_arg"], str(int(max(1, left_min)))]
    return "start", extra


def on_started(st: dict, now: datetime) -> None:
    st["attempts"] = int(st.get("attempts", 0)) + 1
    st["running"] = True
    st["started"] = now.isoformat(timespec="seconds")
    st["next_try"] = ""


def on_exit(st: dict, code, now: datetime, reason: str, base: float, cap: float) -> None:
    st["running"] = False
    st["last_exit"] = code
    st["last_reason"] = reason
    if code == 0:
        st["done"] = True
        st["failures"] = 0
        return
    st["failures"] = int(st.get("failures", 0)) + 1
    st["next_try"] = (now + timedelta(seconds=backoff(st["failures"], base, cap))).isoformat(
        timespec="seconds")


def recover_interrupted(states: dict, now: datetime) -> list:
    """After a reboot or power cut, a job the state file still calls 'running' died with
    the machine: count it as a failed attempt and allow an immediate retry (its backoff
    was spent while the PC was off)."""
    names = []
    for name, st in states.items():
        if isinstance(st, dict) and st.get("running"):
            st["running"] = False
            st["failures"] = int(st.get("failures", 0)) + 1
            st["last_exit"] = None
            st["last_reason"] = "interrupted: the supervisor or the PC restarted mid-run"
            st["next_try"] = ""
            names.append(name)
    return names


def is_hung(last_output: float, now_mono: float, hang_s: float) -> bool:
    return bool(hang_s) and (now_mono - last_output) > hang_s


def is_overtime(started: float, now_mono: float, max_minutes: float) -> bool:
    return (now_mono - started) > max_minutes * 60.0


def skew_seconds(date_header: str, local_now: datetime) -> float | None:
    """Server time minus ours, from an HTTP Date header (1 s resolution)."""
    try:
        server = parsedate_to_datetime(date_header)
    except (TypeError, ValueError, IndexError):
        return None
    if server is None:
        return None
    if server.tzinfo is None:
        server = server.replace(tzinfo=UTC)
    s = (server - local_now).total_seconds()
    return s if abs(s) < 86400 * 2 else None      # a wild answer is ignored, not trusted


def safe_cleanup_targets(root: Path, patterns: list, allowed: list) -> list:
    """Paths matched by `patterns` (relative to root) that resolve INSIDE one of the
    `allowed` directories. An absolute pattern or one with '..' is refused outright:
    the disk guard deletes only its own temp/output, never anything else."""
    out = []
    root = Path(root).resolve()
    allowed = [Path(a).resolve() for a in allowed]
    for pat in patterns if isinstance(patterns, list) else []:
        pat = str(pat).replace("\\", "/").strip()
        if not pat or pat.startswith("/") or ":" in pat or ".." in pat.split("/"):
            continue
        for p in root.glob(pat):
            try:
                rp = p.resolve()
            except OSError:
                continue
            if any(rp != a and _inside(rp, a) for a in allowed):
                out.append(rp)
    return sorted(set(out))


def _inside(p: Path, parent: Path) -> bool:
    try:
        p.relative_to(parent)
        return True
    except ValueError:
        return False


def rotate_file(path: Path, max_bytes: int, keep: int) -> bool:
    """path -> path.1 -> ... -> path.<keep> (the oldest is dropped); True when it rotated."""
    try:
        keep = max(1, int(keep))
        if not path.exists() or path.stat().st_size < max_bytes:
            return False
        last = path.with_name(f"{path.name}.{keep}")
        if last.exists():
            last.unlink()
        for i in range(keep - 1, 0, -1):
            src = path.with_name(f"{path.name}.{i}")
            if src.exists():
                src.replace(path.with_name(f"{path.name}.{i + 1}"))
        path.replace(path.with_name(f"{path.name}.1"))
        return True
    except OSError:
        return False


def safe_relpath(rel: str) -> str:
    """A job's pulse_file must stay inside the app folder."""
    rel = str(rel or "").replace("\\", "/").strip()
    if not rel or rel.startswith("/") or ":" in rel or ".." in rel.split("/"):
        return ""
    return rel


def profile_env(profile: dict, forced: str = "auto") -> tuple:
    """(env vars for stream jobs, hardware_ok). `forced` is node_stream_profile:
    "auto" = the preflight's pick, or "<profile>_<x264|qsv>" set by the owner."""
    prof = dict(profile or {})
    m = re.match(r"^(1080p30|720p30)_(x264|qsv)$", str(forced or "").strip())
    if m:
        prof = {"stream_profile": m.group(1),
                "encoder": "h264_qsv" if m.group(2) == "qsv" else "libx264",
                "verdict": f"forced by node_stream_profile={forced}"}
    name = prof.get("stream_profile")
    if name == "insufficient":
        return {}, False
    if name not in ("1080p30", "720p30") or prof.get("encoder") not in ("libx264", "h264_qsv"):
        prof = dict(FALLBACK_PROFILE)
    env = {"RADAR_PROFILE": prof["stream_profile"], "RADAR_ENCODER": prof["encoder"],
           "TOOLDOJO_STREAM_PROFILE": prof["stream_profile"],
           "TOOLDOJO_ENCODER": prof["encoder"]}
    return env, True


def child_python(executable: str) -> str:
    """Children need a console-subsystem python (their stdout is the watchdog's pulse);
    the supervisor itself runs under pythonw."""
    p = Path(executable)
    if p.name.lower() == "pythonw.exe":
        cand = p.with_name("python.exe")
        if cand.exists():
            return str(cand)
    return str(p)


def expand_cmd(cmd: list, python: str, app: Path) -> list:
    return [c.replace("{python}", python).replace("{app}", str(app)) for c in cmd]


def import_check_code(app: Path, modules: list) -> str:
    paths = [str(app), str(app / "scripts"), str(app / "node")]
    mods = [m for m in modules if re.match(r"^[A-Za-z_][A-Za-z0-9_.]*$", str(m))]
    return ("import sys, importlib\n"
            f"sys.path[:0] = {paths!r}\n"
            f"for m in {mods!r}:\n"
            "    importlib.import_module(m)\n"
            "print('import check ok')\n")


def update_plan(old: str, new: str, dirty: str, bad_commit: str) -> tuple:
    """("apply" | "skip", why) for a fetched commit."""
    if not new or not old:
        return "skip", "git did not answer"
    if new == old:
        return "skip", "already current"
    if new == bad_commit:
        return "skip", f"{new[:10]} failed the import check before; waiting for a newer commit"
    if dirty.strip():
        return "skip", "tracked files were edited on this PC; not touching them"
    return "apply", f"{old[:10]} -> {new[:10]}"


def _hhmm_due(hhmm: str, now: datetime, last_day: str) -> bool:
    m = HHMM.match(str(hhmm or ""))
    if not m:
        return False
    at = now.replace(hour=int(m.group(1)), minute=int(m.group(2)), second=0, microsecond=0)
    return now >= at and last_day != now.date().isoformat()


# ================================================================== Windows plumbing
class JobObject:
    """Every child gets its own Job Object: the whole tree (Chromium, ffmpeg, the radar's
    producer process) can be killed in one call, BelowNormal is enforced on every
    process in it, and an optional hard CPU cap. Fail-soft: without it, taskkill /T."""

    def __init__(self, priority_class: int = 0, cpu_cap_percent: int = 0):
        self.handle = None
        if os.name != "nt":
            return
        try:
            import ctypes
            from ctypes import wintypes
            k32 = ctypes.WinDLL("kernel32", use_last_error=True)
            k32.CreateJobObjectW.restype = wintypes.HANDLE
            k32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
            k32.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int,
                                                    ctypes.c_void_p, wintypes.DWORD]
            k32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
            k32.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
            k32.CloseHandle.argtypes = [wintypes.HANDLE]

            class IO(ctypes.Structure):
                _fields_ = [(n, ctypes.c_ulonglong) for n in (
                    "r", "w", "o", "rb", "wb", "ob")]

            class BASIC(ctypes.Structure):
                _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64),
                            ("PerJobUserTimeLimit", ctypes.c_int64),
                            ("LimitFlags", wintypes.DWORD),
                            ("MinimumWorkingSetSize", ctypes.c_size_t),
                            ("MaximumWorkingSetSize", ctypes.c_size_t),
                            ("ActiveProcessLimit", wintypes.DWORD),
                            ("Affinity", ctypes.c_size_t),
                            ("PriorityClass", wintypes.DWORD),
                            ("SchedulingClass", wintypes.DWORD)]

            class EXT(ctypes.Structure):
                _fields_ = [("Basic", BASIC), ("Io", IO),
                            ("ProcessMemoryLimit", ctypes.c_size_t),
                            ("JobMemoryLimit", ctypes.c_size_t),
                            ("PeakProcessMemoryUsed", ctypes.c_size_t),
                            ("PeakJobMemoryUsed", ctypes.c_size_t)]

            h = k32.CreateJobObjectW(None, None)
            if not h:
                return
            info = EXT()
            info.Basic.LimitFlags = 0x2000                      # KILL_ON_JOB_CLOSE
            if priority_class:
                info.Basic.LimitFlags |= 0x20                   # LIMIT_PRIORITY_CLASS
                info.Basic.PriorityClass = priority_class
            k32.SetInformationJobObject(h, 9, ctypes.byref(info), ctypes.sizeof(info))
            if cpu_cap_percent and 1 <= cpu_cap_percent < 100:
                class CPU(ctypes.Structure):
                    _fields_ = [("ControlFlags", wintypes.DWORD), ("CpuRate", wintypes.DWORD)]
                cpu = CPU(0x1 | 0x4, int(cpu_cap_percent * 100))   # ENABLE | HARD_CAP
                k32.SetInformationJobObject(h, 15, ctypes.byref(cpu), ctypes.sizeof(cpu))
            self._k32, self.handle = k32, h
        except Exception:  # noqa: BLE001 - no job object = taskkill fallback
            self.handle = None

    def assign(self, proc) -> bool:
        if not self.handle:
            return False
        try:
            return bool(self._k32.AssignProcessToJobObject(self.handle, int(proc._handle)))
        except Exception:  # noqa: BLE001
            return False

    def kill(self) -> bool:
        if not self.handle:
            return False
        try:
            return bool(self._k32.TerminateJobObject(self.handle, 1))
        except Exception:  # noqa: BLE001
            return False

    def close(self) -> None:
        if self.handle:
            try:
                self._k32.CloseHandle(self.handle)
            except Exception:  # noqa: BLE001
                pass
            self.handle = None


def hidden_popen_kwargs(priority: str = "below_normal") -> dict:
    """The flags every child gets (spec section 6, "never blocks the screen")."""
    if os.name != "nt":
        return {}
    si = subprocess.STARTUPINFO()
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    si.wShowWindow = 0                                            # SW_HIDE
    flags = CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP | PRIORITIES.get(priority, 0x4000)
    return {"creationflags": flags, "startupinfo": si}


class Child:
    """One running job: hidden, below normal, in its own Job Object, its output read
    line by line (the watchdog's pulse), redacted and written to its own log."""

    def __init__(self, name: str, cmd: list, cwd: Path, env: dict, log_path: Path,
                 secrets: list, priority: str = "below_normal", cpu_cap: int = 0):
        self.name, self.secrets = name, secrets
        self.tail: list = []
        self.last_output = time.monotonic()
        self.started = time.monotonic()
        self.log_path = log_path
        self.job = JobObject(PRIORITIES.get(priority, 0), cpu_cap)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        self._log = log_path.open("a", encoding="utf-8")
        self._log.write(f"\n===== {datetime.now(UTC):%Y-%m-%d %H:%M:%S}Z start: "
                        f"{redact(' '.join(cmd), secrets)}\n")
        self._log.flush()
        self.proc = subprocess.Popen(cmd, cwd=str(cwd), env=env, stdin=subprocess.DEVNULL,
                                     stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                     **hidden_popen_kwargs(priority))
        self.pid = self.proc.pid
        self.in_job = self.job.assign(self.proc)
        self._reader = threading.Thread(target=self._read, daemon=True)
        self._reader.start()

    def _read(self) -> None:
        try:
            for raw in iter(self.proc.stdout.readline, b""):
                self.last_output = time.monotonic()
                line = redact(raw.decode("utf-8", "replace").rstrip(), self.secrets)
                self.tail = (self.tail + [line])[-20:]
                try:
                    self._log.write(line + "\n")
                    self._log.flush()
                except (OSError, ValueError):
                    pass
        except Exception:  # noqa: BLE001
            pass

    def poll(self):
        return self.proc.poll()

    def kill(self) -> None:
        if not self.job.kill():
            try:
                subprocess.run(["taskkill", "/T", "/F", "/PID", str(self.pid)],
                               capture_output=True, timeout=30, **hidden_popen_kwargs("normal"))
            except Exception:  # noqa: BLE001
                pass
        try:
            self.proc.kill()
        except Exception:  # noqa: BLE001
            pass
        try:
            self.proc.wait(timeout=15)
        except Exception:  # noqa: BLE001
            pass

    def close(self, code) -> None:
        try:
            self._reader.join(timeout=5)
        except Exception:  # noqa: BLE001
            pass
        try:
            self._log.write(f"===== {datetime.now(UTC):%Y-%m-%d %H:%M:%S}Z exit {code}\n")
            self._log.close()
        except (OSError, ValueError):
            pass
        self.job.close()


def keep_awake() -> None:
    """ES_CONTINUOUS | ES_SYSTEM_REQUIRED for the supervisor's whole life: the power plan
    already says never sleep on AC, this covers a plan someone changes later."""
    if os.name != "nt":
        return
    try:
        import ctypes
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | 0x00000001)
    except Exception:  # noqa: BLE001
        pass


def acquire_lock(path: Path):
    """An exclusive byte lock on a file: cross-session (session 0 vs the owner's own
    session), released by Windows when the process dies. None = someone holds it."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fh = path.open("a+b")
        if os.name == "nt":
            import msvcrt
            fh.seek(0)
            msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
        return fh
    except OSError:
        return None


# ================================================================== the supervisor
class Supervisor:
    def __init__(self, app: Path, data: Path, cfg: dict, jobs_raw=None, foreground=False,
                 python: str | None = None):
        self.app, self.data, self.cfg = Path(app), Path(data), cfg
        self.foreground = foreground
        self.python = python or child_python(sys.executable)
        self.state_path = self.data / "node_state.json"
        self.status_path = self.data / "status.json"
        self.local_path = self.data / "node.local.json"
        self.logs = self.data / "logs"
        self.jobs, self.job_errors = parse_jobs(jobs_raw if jobs_raw is not None
                                                else cfg.get("node_jobs", []))
        self.dotenv = self._read_env()
        self.secrets = secret_values(self.dotenv)
        self.state = self._load_json(self.state_path, {})
        self.state.setdefault("jobs", {})
        self.children: dict = {}
        self.boot_at = datetime.now(UTC)
        self.offset = 0.0               # clock correction (s), from the HTTP Date check
        self.skew = None
        self.network_ok = None
        self.disk_free_gb = None
        self.disk_ok = True
        self.version = ""
        self.update_result = ""
        self.import_ok = None
        self.last_status = 0.0
        self.last_disk = 0.0
        self.last_clock = 0.0
        self.skip_logged: dict = {}
        self.alerts_today = (datetime.now(UTC).date().isoformat(), 0)
        self.exit_for_update = False

    # ---------------------------------------------------------------- small IO
    def _read_env(self) -> dict:
        try:
            return parse_dotenv((self.app / ".env").read_text(encoding="utf-8"))
        except OSError:
            return {}

    @staticmethod
    def _load_json(path: Path, default):
        try:
            v = json.loads(path.read_text(encoding="utf-8"))
            return v if isinstance(v, type(default)) else default
        except Exception:  # noqa: BLE001
            return default

    def _write_json(self, path: Path, data) -> None:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_name(path.name + ".tmp")
            tmp.write_text(json.dumps(data, indent=1, default=str), encoding="utf-8")
            os.replace(tmp, path)
        except Exception as e:  # noqa: BLE001
            self.say(f"could not write {path.name}: {type(e).__name__}")

    def say(self, msg: str, level=logging.INFO) -> None:
        log.log(level, redact(msg, self.secrets))

    def now(self) -> datetime:
        return datetime.now(UTC) + timedelta(seconds=self.offset)

    def c(self, key):
        return self.cfg.get(key, DEFAULTS.get(key))

    def save_state(self) -> None:
        self._write_json(self.state_path, self.state)

    # ---------------------------------------------------------------- alerts
    def alert(self, text: str) -> None:
        """Telegram to the owner's own chat, rate-limited per UTC day, on a thread so a
        slow network can never stall the loop. Fail-soft, token redacted."""
        self.say(f"ALERT: {text}", logging.WARNING)
        if not self.c("node_alert_telegram"):
            return
        tok = self.dotenv.get("TELEGRAM_BOT_TOKEN", "") or os.environ.get("TELEGRAM_BOT_TOKEN", "")
        chat = (self.dotenv.get("NODE_TELEGRAM_CHAT_ID", "")
                or os.environ.get("NODE_TELEGRAM_CHAT_ID", ""))
        if not tok or not chat:
            return
        day, n = self.alerts_today
        today = datetime.now(UTC).date().isoformat()
        if day != today:
            day, n = today, 0
        if n >= int(self.c("node_alert_max_per_day")):
            return
        self.alerts_today = (day, n + 1)
        secrets = self.secrets + [tok]
        body = redact(f"ToolDojo Node: {text}", secrets)[:3500]
        threading.Thread(target=_send_telegram, args=(tok, chat, body, secrets),
                         daemon=True).start()

    # ---------------------------------------------------------------- boot steps
    def wait_network(self, probe=None, sleep=time.sleep) -> bool:
        probe = probe or (lambda: tcp_probe(self.c("node_network_hosts")))
        waited, step, limit = 0.0, 5.0, float(self.c("node_network_wait_max_s"))
        while True:
            if probe():
                self.network_ok = True
                if waited:
                    self.say(f"network up after {waited:.0f} s")
                return True
            if waited >= limit:
                self.network_ok = False
                self.say(f"no network after {waited:.0f} s; starting anyway "
                         "(jobs fail soft and are retried)", logging.WARNING)
                return False
            sleep(step)
            waited += step
            step = min(60.0, step * 2)

    def check_clock(self) -> None:
        self.last_clock = time.monotonic()
        try:
            import urllib.request
            req = urllib.request.Request(self.c("node_clock_url"), method="HEAD")
            with urllib.request.urlopen(req, timeout=10) as r:      # noqa: S310 - fixed https URL
                date_h = r.headers.get("Date", "")
        except Exception as e:  # noqa: BLE001
            self.say(f"clock check failed: {type(e).__name__}")
            return
        s = skew_seconds(date_h, datetime.now(UTC))
        if s is None:
            return
        self.skew = round(s, 1)
        # the schedule runs on corrected time whatever the Windows clock says
        self.offset = s if abs(s) > 2 else 0.0
        if abs(s) > float(self.c("node_clock_max_skew_s")):
            self.alert(f"the Windows clock is off by {s:.0f} s; schedules use corrected time. "
                       "Check Settings > Time > Sync now.")

    def git(self, *args, timeout=120) -> tuple:
        cmd = [git_exe(), "-c", f"safe.directory={self.app.as_posix()}", *args]
        try:
            r = subprocess.run(cmd, cwd=str(self.app), capture_output=True, text=True,
                               timeout=timeout, **hidden_popen_kwargs("below_normal"))
            return r.returncode, (r.stdout or "").strip(), redact((r.stderr or "")[-400:],
                                                                   self.secrets)
        except Exception as e:  # noqa: BLE001
            return 1, "", f"{type(e).__name__}"

    def import_check(self) -> tuple:
        code = import_check_code(self.app, list(self.c("node_import_check")))
        try:
            r = subprocess.run([self.python, "-c", code], cwd=str(self.app), capture_output=True,
                               text=True, timeout=180, env=self.child_env({}),
                               **hidden_popen_kwargs("below_normal"))
            ok = r.returncode == 0
            tail = redact(((r.stdout or "") + (r.stderr or ""))[-600:], self.secrets)
        except Exception as e:  # noqa: BLE001
            ok, tail = False, type(e).__name__
        self.import_ok = ok
        return ok, tail

    def self_update(self) -> str:
        """Fetch the configured branch; check out the new commit DETACHED (never reset,
        never clean); run the import check; roll back to the old commit if it fails.
        Returns "updated:<node files changed?>" / "rolled back" / a skip reason."""
        if not (self.app / ".git").exists():
            return "skip: not a git checkout (installed from the ZIP snapshot)"
        branch = str(self.c("node_update_branch"))
        if not re.match(r"^[A-Za-z0-9._/-]{1,100}$", branch) or ".." in branch:
            return "skip: bad node_update_branch"
        rc, old, err = self.git("rev-parse", "HEAD")
        rc2, _, err2 = self.git("fetch", "--quiet", "--depth", "1", "origin", branch, timeout=300)
        if rc2 != 0:
            return f"skip: fetch failed ({err2[-120:]})"
        _, new, _ = self.git("rev-parse", "FETCH_HEAD")
        _, dirty, _ = self.git("status", "--porcelain", "--untracked-files=no")
        plan, why = update_plan(old, new, dirty, str(self.state.get("bad_commit", "")))
        if plan != "apply":
            return f"skip: {why}"
        rc3, _, err3 = self.git("checkout", "--quiet", "--detach", new)
        if rc3 != 0:
            return f"skip: checkout refused ({err3[-120:]})"
        ok, tail = self.import_check()
        if ok:
            _, changed, _ = self.git("diff", "--name-only", old, new)
            self.state["bad_commit"] = ""
            self.say(f"updated {why}")
            node_changed = any(p.startswith("node/") for p in changed.splitlines())
            return f"updated: node files changed={node_changed}"
        self.git("checkout", "--quiet", "--detach", old)
        self.state["bad_commit"] = new
        self.import_check()
        self.alert(f"update {why} broke the import check; rolled back. {tail[-200:]}")
        return "rolled back"

    def profile(self) -> dict:
        return self._load_json(self.local_path, {})

    def run_preflight(self) -> None:
        """Measured from INSIDE the task's own context (session 0, this account), because
        GPU / Quick Sync can behave differently there than in a signed-in session."""
        script = self.app / "node" / "node_preflight.py"
        if not script.exists():
            self.say("node_preflight.py missing; using the conservative profile")
            return
        self.say("running the encoder/hardware preflight (once; takes a few minutes)")
        try:
            child = Child("preflight", [self.python, str(script), "--data", str(self.data)],
                          self.app, self.child_env({}), self.logs / "jobs" / "preflight.log",
                          self.secrets, str(self.c("node_priority")))
            deadline = time.monotonic() + 1200
            while child.poll() is None and time.monotonic() < deadline:
                self.write_status(force=True)
                time.sleep(2)
            if child.poll() is None:
                child.kill()
            code = child.poll()
            child.close(code)
            p = self.profile()
            self.say(f"preflight exit {code}: {p.get('stream_profile')} {p.get('encoder')} "
                     f"- {p.get('verdict', '')}")
            if p.get("stream_profile") == "insufficient":
                self.alert(f"preflight verdict: insufficient for streaming. {p.get('verdict', '')}")
        except Exception as e:  # noqa: BLE001
            self.say(f"preflight failed to run: {type(e).__name__}: {e}", logging.WARNING)

    def boot(self, network=True, update=True, preflight=True) -> None:
        keep_awake()
        names = recover_interrupted(self.state["jobs"], self.now())
        for n in names:
            self.say(f"{n}: was running when the PC/supervisor stopped; counted as a failed attempt")
        for e in self.job_errors:
            self.say(f"job table: {e}", logging.WARNING)
        self.save_state()
        if network:
            self.wait_network()
            self.check_clock()
        if update and self.c("node_self_update") and self.network_ok is not False:
            self.update_result = self.self_update()
            self.say(f"self-update: {self.update_result}")
            self.state["last_update_day"] = self.now().date().isoformat()
            self.save_state()
            if self.update_result.startswith("updated: node files changed=True"):
                # the running supervisor is the OLD code; exit so the task's 5-minute
                # trigger starts the new one (spec row 14)
                self.exit_for_update = True
                return
        if self.import_ok is None:
            ok, tail = self.import_check()
            if not ok:
                self.alert(f"import check failed; jobs will fail until fixed. {tail[-200:]}")
        _, self.version, _ = self.git("rev-parse", "--short", "HEAD", timeout=30)
        if preflight and not self.profile().get("stream_profile"):
            self.run_preflight()

    # ---------------------------------------------------------------- the loop body
    def child_env(self, job: dict) -> dict:
        env = dict(os.environ)
        bin_dir = self.app.parent / "bin"
        if bin_dir.exists():
            env["PATH"] = str(bin_dir) + os.pathsep + env.get("PATH", "")
            for exe, var in (("ffmpeg.exe", "FFMPEG_BIN"), ("ffprobe.exe", "FFPROBE_BIN")):
                if (bin_dir / exe).exists():
                    env[var] = str(bin_dir / exe)
        pw = self.app.parent / "ms-playwright"
        if pw.exists():
            env["PLAYWRIGHT_BROWSERS_PATH"] = str(pw)
        env.update({"PYTHONIOENCODING": "utf-8", "PYTHONUNBUFFERED": "1",
                    "TOOLDOJO_NODE": "1", "TOOLDOJO_NODE_DATA": str(self.data)})
        if job:
            if job.get("stream"):
                penv, _ = profile_env(self.profile(), str(self.c("node_stream_profile")))
                env.update(penv)
            if job.get("daily"):
                env["TOOLDOJO_NODE_SCHEDULED"] = "1"
            env.update(job.get("env", {}))
        return env

    def paused(self) -> str:
        if not self.c("node_enabled"):
            return "node_enabled is false in config.json"
        if (self.data / "PAUSE").exists():
            return "paused by the PAUSE file in the data folder"
        return ""

    def stream_holder(self) -> str:
        for name in self.children:
            job = self._job(name)
            if job and job["stream"]:
                return name
        return ""

    def _job(self, name):
        return next((j for j in self.jobs if j["name"] == name), None)

    def _jst(self, name: str) -> dict:
        st = self.state["jobs"].get(name)
        if not isinstance(st, dict):
            st = new_job_state()
            self.state["jobs"][name] = st
        return st

    def reap_and_watch(self, now: datetime) -> None:
        mono = time.monotonic()
        for name in list(self.children):
            child = self.children[name]
            job = self._job(name) or {"hang_seconds": 0, "max_minutes": 1440, "pulse_file": ""}
            try:
                code = child.poll()
                reason = f"exit {code}" if code is not None else ""
                last = child.last_output
                if job.get("pulse_file"):
                    # a log file the job (or its own child processes) keeps writing also
                    # counts as a pulse: the radar's producer process never reaches stdout
                    try:
                        mt = (self.app / job["pulse_file"]).stat().st_mtime
                        last = max(last, mono - max(0.0, time.time() - mt))
                    except OSError:
                        pass
                if code is None and is_hung(last, mono, job["hang_seconds"]):
                    reason = f"hung: no output for {job['hang_seconds']:.0f} s; killed"
                elif code is None and is_overtime(child.started, mono, job["max_minutes"]):
                    reason = f"ran past max_minutes={job['max_minutes']:.0f}; killed"
                if not reason:
                    continue
                if code is None:
                    child.kill()
                    code = child.poll()
                    code = -1 if code is None or code == 0 else code
                child.close(code)
                del self.children[name]
                st = self._jst(name)
                on_exit(st, code, now, reason, float(self.c("node_backoff_base_s")),
                        float(self.c("node_backoff_max_s")))
                tail = " | ".join(child.tail[-3:])[-300:]
                self.say(f"{name}: {reason}" + (f" (next try {st['next_try']})" if code else "")
                         + (f" - last output: {tail}" if code and tail else ""))
                if code and st["failures"] >= int(self.c("node_alert_after_failures")) \
                        and not st.get("alerted"):
                    st["alerted"] = True
                    self.alert(f"{name} failed {st['failures']} times in slot {st['slot']}: "
                               f"{reason}. Last output: {tail}")
                self.save_state()
            except Exception as e:  # noqa: BLE001 - one bad child never stops the loop
                self.say(f"{name}: watchdog error {type(e).__name__}: {e}", logging.WARNING)

    def schedule(self, now: datetime) -> None:
        paused = self.paused()
        _, hardware_ok = profile_env(self.profile(), str(self.c("node_stream_profile")))
        for job in self.jobs:
            try:
                name = job["name"]
                slot = slot_at(job, now)
                st = self._jst(name)
                if slot and st.get("slot") != slot["key"] and not st.get("running"):
                    self.state["jobs"][name] = st = new_job_state(slot["key"])
                    self.save_state()
                if name in self.children:
                    continue
                action, info = decide(job, st, now, slot, self.stream_holder(), self.disk_ok,
                                      paused, hardware_ok, float(self.c("node_late_grace_s")))
                if action == "skip":
                    st["skipped"] = info
                    self.say(f"{name}: skipped slot {st.get('slot')}: {info}")
                    if "retry cap" in info:
                        self.alert(f"{name} gave up for slot {st.get('slot')}: {info}. "
                                   f"Last: {st.get('last_reason')}")
                    self.save_state()
                elif action == "wait":
                    if self.skip_logged.get(name) != info:
                        self.skip_logged[name] = info
                        self.say(f"{name}: waiting - {info}")
                elif action == "start":
                    self.skip_logged.pop(name, None)
                    self.start_job(job, st, now, info)
            except Exception as e:  # noqa: BLE001 - job isolation
                self.say(f"{job.get('name')}: scheduler error {type(e).__name__}: {e}",
                         logging.WARNING)

    def start_job(self, job: dict, st: dict, now: datetime, extra: list) -> None:
        cmd = expand_cmd(job["cmd"], self.python, self.app) + list(extra)
        on_started(st, now)
        self.save_state()
        log_path = self.logs / "jobs" / f"{job['name']}.log"
        rotate_file(log_path, int(float(self.c("node_log_max_mb")) * 1e6),
                    int(self.c("node_log_keep")))
        try:
            self.children[job["name"]] = Child(
                job["name"], cmd, self.app, self.child_env(job), log_path, self.secrets,
                str(self.c("node_priority")), int(self.c("node_cpu_cap_percent") or 0))
            self.say(f"{job['name']}: started attempt {st['attempts']}/{job['attempts_per_day']} "
                     f"(pid {self.children[job['name']].pid})"
                     + (f" late, with {' '.join(extra)}" if extra else ""))
        except Exception as e:  # noqa: BLE001 - a missing exe is a failed attempt, not a crash
            on_exit(st, -2, now, f"could not start: {type(e).__name__}: {e}",
                    float(self.c("node_backoff_base_s")), float(self.c("node_backoff_max_s")))
            self.say(f"{job['name']}: could not start: {type(e).__name__}: {e}", logging.WARNING)
            self.save_state()

    def housekeeping(self, now: datetime) -> None:
        mono = time.monotonic()
        if mono - self.last_disk >= 60 or not self.last_disk:
            self.last_disk = mono
            try:
                free = shutil.disk_usage(str(self.app)).free / 1e9
                if free < float(self.c("node_disk_min_free_gb")) and not self.children:
                    freed = self.cleanup()
                    self.say(f"disk guard: {free:.1f} GB free < {self.c('node_disk_min_free_gb')} GB;"
                             f" cleaned {freed / 1e6:.0f} MB of the node's own temp files")
                    free = shutil.disk_usage(str(self.app)).free / 1e9
                was_ok = self.disk_ok
                self.disk_ok = free >= float(self.c("node_disk_floor_gb"))
                self.disk_free_gb = round(free, 1)
                if was_ok and not self.disk_ok:
                    self.alert(f"only {free:.1f} GB free; streams will not start below "
                               f"{self.c('node_disk_floor_gb')} GB")
                if not self.children:
                    rotate_file(self.app / "logs" / "radar_live.log", 20_000_000, 2)
            except Exception as e:  # noqa: BLE001
                self.say(f"disk guard error: {type(e).__name__}")
        if self.last_clock and mono - self.last_clock >= 6 * 3600:
            self.check_clock()
        if (self.c("node_self_update") and not self.children
                and _hhmm_due(self.c("node_update_at_utc"), now,
                              str(self.state.get("last_update_day", "")))
                and not any(slot_at(j, now) for j in self.jobs if j["enabled"])):
            self.state["last_update_day"] = now.date().isoformat()
            self.update_result = self.self_update()
            self.say(f"daily self-update: {self.update_result}")
            self.save_state()
            if self.update_result.startswith("updated: node files changed=True"):
                self.exit_for_update = True

    def cleanup(self) -> int:
        targets = safe_cleanup_targets(self.app, list(self.c("node_cleanup_globs")),
                                       [self.app / "temp"])
        freed = 0
        for p in targets:
            try:
                if p.is_dir():
                    freed += sum(f.stat().st_size for f in p.rglob("*") if f.is_file())
                    shutil.rmtree(p, ignore_errors=True)
                else:
                    freed += p.stat().st_size
                    p.unlink()
            except OSError:
                continue
        return freed

    def write_status(self, force=False) -> None:
        mono = time.monotonic()
        if not force and mono - self.last_status < float(self.c("node_status_every_s")):
            return
        self.last_status = mono
        now = self.now()
        jobs = {}
        for job in self.jobs:
            st = self.state["jobs"].get(job["name"], {})
            nxt = next_slot(job, now)
            child = self.children.get(job["name"])
            jobs[job["name"]] = {
                "enabled": job["enabled"], "stream": job["stream"],
                "window": f"{','.join(job['days'])} {job['start_utc']}Z +{job['slot_minutes']:.0f}m",
                "in_window": bool(slot_at(job, now)), "next_window": nxt.isoformat() if nxt else "",
                "running": bool(child), "pid": child.pid if child else None,
                "silent_s": round(mono - child.last_output) if child else None,
                **{k: st.get(k) for k in ("slot", "attempts", "failures", "done", "skipped",
                                          "next_try", "last_exit", "last_reason")}}
        p = self.profile()
        self._write_json(self.status_path, {
            "updated": now.isoformat(timespec="seconds"), "pid": os.getpid(),
            "boot": self.boot_at.isoformat(timespec="seconds"), "version": self.version,
            "app": str(self.app), "paused": self.paused(), "network_ok": self.network_ok,
            "clock_skew_s": self.skew, "disk_free_gb": self.disk_free_gb, "disk_ok": self.disk_ok,
            "import_ok": self.import_ok, "update": self.update_result,
            "profile": {k: p.get(k) for k in ("stream_profile", "encoder", "verdict", "measured_at")},
            "stream_holder": self.stream_holder(), "job_table_errors": self.job_errors,
            "jobs": jobs})

    def tick(self) -> None:
        now = self.now()
        for step in (self.reap_and_watch, self.housekeeping, self.schedule):
            try:
                step(now)
            except Exception as e:  # noqa: BLE001
                self.say(f"{step.__name__} error {type(e).__name__}: {e}", logging.WARNING)
        self.write_status()

    def stop_all(self, why: str) -> None:
        for name, child in list(self.children.items()):
            child.kill()
            code = child.poll()
            child.close(code)
            st = self._jst(name)
            on_exit(st, code if code else -1, self.now(), why,
                    float(self.c("node_backoff_base_s")), float(self.c("node_backoff_max_s")))
            st["next_try"] = ""
            self.say(f"{name}: stopped ({why})")
        self.children.clear()
        self.save_state()

    def loop(self, run_for: float = 0) -> None:
        end = time.monotonic() + run_for if run_for else None
        while not self.exit_for_update:
            self.tick()
            if end and time.monotonic() >= end:
                self.stop_all("the foreground --run-for ended")
                self.write_status(force=True)
                return
            time.sleep(float(self.c("node_tick_s")))
        self.write_status(force=True)


def _send_telegram(tok: str, chat: str, text: str, secrets: list) -> None:
    try:
        import urllib.parse
        import urllib.request
        data = urllib.parse.urlencode({"chat_id": chat, "text": text}).encode()
        req = urllib.request.Request(f"https://api.telegram.org/bot{tok}/sendMessage", data=data)
        with urllib.request.urlopen(req, timeout=15) as r:          # noqa: S310 - fixed host
            r.read(2000)
    except Exception as e:  # noqa: BLE001
        log.warning(redact(f"telegram alert failed: {type(e).__name__}: {e}", secrets))


def git_exe() -> str:
    """git from PATH, else the machine-wide install (a task's PATH can be minimal)."""
    found = shutil.which("git")
    if found:
        return found
    std = Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "Git" / "cmd" / "git.exe"
    return str(std) if std.exists() else "git"


def tcp_probe(hosts) -> bool:
    for h in hosts if isinstance(hosts, list) else []:
        host, _, port = str(h).rpartition(":")
        try:
            with socket.create_connection((host, int(port)), timeout=5):
                return True
        except (OSError, ValueError):
            continue
    return False


def load_config(path: Path) -> dict:
    cfg = dict(DEFAULTS)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            cfg.update({k: v for k, v in raw.items() if k.startswith("node_")})
    except Exception as e:  # noqa: BLE001 - a broken config.json still gets a supervisor
        cfg["_config_error"] = f"{type(e).__name__}: {e}"
    return cfg


def setup_logging(data: Path, foreground: bool) -> None:
    log.setLevel(logging.INFO)
    log.handlers.clear()
    fmt = logging.Formatter("%(asctime)sZ %(levelname)s %(message)s", "%Y-%m-%d %H:%M:%S")
    fmt.converter = time.gmtime
    try:
        (data / "logs").mkdir(parents=True, exist_ok=True)
        fh = logging.handlers.RotatingFileHandler(data / "logs" / "supervisor.log",
                                                  maxBytes=1_000_000, backupCount=5,
                                                  encoding="utf-8")
        fh.setFormatter(fmt)
        log.addHandler(fh)
    except OSError:
        pass
    if foreground and sys.stdout is not None:
        class Ascii(logging.StreamHandler):
            def emit(self, record):
                try:
                    msg = self.format(record).encode("ascii", "replace").decode("ascii")
                    self.stream.write(msg + "\n")
                    self.flush()
                except Exception:  # noqa: BLE001 - cp1252 consoles must never kill us
                    pass
        sh = Ascii(sys.stdout)
        sh.setFormatter(fmt)
        log.addHandler(sh)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="ToolDojo Node supervisor (v3-N.1)")
    ap.add_argument("--app", default=str(APP))
    ap.add_argument("--data", default=os.environ.get("TOOLDOJO_NODE_DATA", ""))
    ap.add_argument("--config", default="")
    ap.add_argument("--jobs", default="", help="a JSON file with a job list (testing)")
    ap.add_argument("--run-for", type=float, default=0, help="seconds, then stop (testing)")
    ap.add_argument("--no-update", action="store_true")
    ap.add_argument("--no-network-wait", action="store_true")
    ap.add_argument("--no-preflight", action="store_true")
    a = ap.parse_args(argv)
    app = Path(a.app).resolve()
    data = Path(a.data).resolve() if a.data else app / "temp" / "node"
    foreground = bool(a.run_for) or (sys.stdout is not None and sys.stdout.isatty())
    setup_logging(data, foreground)
    lock = acquire_lock(data / "supervisor.lock")
    if lock is None:
        log.info("another supervisor holds the lock; this one exits")
        return 0
    first = True
    while True:
        try:
            cfg = load_config(Path(a.config) if a.config else app / "config.json")
            jobs_raw = None
            if a.jobs:
                jobs_raw = json.loads(Path(a.jobs).read_text(encoding="utf-8"))
            sup = Supervisor(app, data, cfg, jobs_raw, foreground)
            if cfg.get("_config_error"):
                sup.say(f"config.json unreadable ({cfg['_config_error']}); defaults only",
                        logging.WARNING)
            sup.say(f"supervisor start pid {os.getpid()} app={app} data={data} "
                    f"jobs={[j['name'] for j in sup.jobs]}")
            sup.boot(network=not a.no_network_wait, update=first and not a.no_update,
                     preflight=not a.no_preflight)
            first = False
            sup.loop(a.run_for)
            if sup.exit_for_update:
                sup.say("exiting so the scheduled task starts the updated supervisor")
                return 0
            if a.run_for:
                sup.say("foreground run finished")
                return 0
        except KeyboardInterrupt:
            if foreground:
                return 0
        except Exception as e:  # noqa: BLE001 - the supervisor never exits on an exception
            log.exception(redact(f"supervisor crashed: {type(e).__name__}: {e}; restarting in 30 s"))
            try:
                sup.stop_all("supervisor restart")   # noqa: F821 - may not exist yet
            except Exception:  # noqa: BLE001
                pass
            time.sleep(30)


if __name__ == "__main__":
    sys.exit(main())

"""v3-N.1 ToolDojo Node: supervisor scheduling, resume rule, backoff, isolation, disk guard,
redaction, preflight selection, radar profile args, bundle filter (docs/spec/ai-pulse-v3n1.md).

Never touches the network, ffmpeg or an LLM. Helpers are prefixed `_n1_` (CLAUDE.md:
test modules share one namespace per file, and a bare `_row` once broke 16 tests)."""
import importlib.util
import json
import logging
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
UTC = timezone.utc


def _n1_load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


sv = _n1_load("n1_supervisor", "node/supervisor.py")
pf = _n1_load("n1_node_preflight", "node/node_preflight.py")
nb = _n1_load("n1_build_node_bundle", "scripts/build_node_bundle.py")


def _n1_job(**over):
    raw = {"name": "radar_live", "stream": True, "cmd": ["{python}", "scripts/radar_live.py"],
           "days": "daily", "start_utc": "14:30", "slot_minutes": 120, "min_minutes": 30,
           "max_minutes": 180, "hang_seconds": 600, "attempts_per_day": 4,
           "remaining_arg": "--minutes"}
    raw.update(over)
    job, err = sv.parse_job(raw)
    assert not err, err
    return job


def _n1_at(h, m, day=4, s=0):
    """2026-11-04 is a Wednesday."""
    return datetime(2026, 11, day, h, m, s, tzinfo=UTC)


# ------------------------------------------------------------------ job table
def test_n1_parse_job_coerces_and_rejects():
    job = _n1_job(slot_minutes="90", attempts_per_day="2", enabled="false", days="mon,sat")
    assert job["slot_minutes"] == 90 and job["attempts_per_day"] == 2
    assert job["enabled"] is False and job["days"] == ["mon", "sat"] and job["daily"] is False
    assert _n1_job()["daily"] is True
    assert _n1_job(min_minutes=999)["min_minutes"] == 120          # clamped to the slot
    assert _n1_job(max_minutes=float("nan"))["max_minutes"] == 120  # NaN falls to default
    for bad in ({"start_utc": "25:00"}, {"cmd": []}, {"name": "Bad Name!"},
                {"days": ["someday"]}, {"cmd": [{"x": 1}]}):
        job, err = sv.parse_job({**{"name": "x", "cmd": ["a"], "start_utc": "10:00"}, **bad})
        assert job is None and err
    assert _n1_job(pulse_file="../../etc/x")["pulse_file"] == ""
    assert _n1_job(pulse_file="C:/x.log")["pulse_file"] == ""
    assert _n1_job(pulse_file="logs/radar_live.log")["pulse_file"] == "logs/radar_live.log"


def test_n1_parse_jobs_isolates_bad_rows():
    jobs, errors = sv.parse_jobs([{"name": "a", "cmd": ["x"], "start_utc": "10:00"},
                                  "not a dict", {"name": "b"},
                                  {"name": "a", "cmd": ["y"], "start_utc": "11:00"},
                                  {"name": "c", "cmd": "py -3 x.py", "start_utc": "12:00"}])
    assert [j["name"] for j in jobs] == ["a", "c"]
    assert jobs[1]["cmd"] == ["py", "-3", "x.py"]
    assert len(errors) == 3
    assert sv.parse_jobs("garbage") == ([], [])


def test_n1_config_job_table_parses_in_both_files():
    for name in ("config.json", "config.example.json"):
        cfg = json.loads((ROOT / name).read_text(encoding="utf-8"))
        jobs, errors = sv.parse_jobs(cfg["node_jobs"])
        assert not errors, (name, errors)
        radar = next(j for j in jobs if j["name"] == "radar_live")
        # 14:30 UTC = 20:00 IST, the v3l2 row 24 slot; 180 min = the old task's 3 h kill
        assert radar["start_utc"] == "14:30" and radar["max_minutes"] == 180
        assert radar["min_minutes"] == 30 and radar["stream"] and radar["daily"]
        trials = next(j for j in jobs if j["name"] == "live_trials")
        assert trials["days"] == ["sat"] and trials["start_utc"] == "18:45"
        assert trials["enabled"] is False          # until v3-T.1 ships scripts/trials_live.py
        for key in sv.DEFAULTS:
            if key in ("node_import_check", "node_network_hosts", "node_clock_url",
                       "node_late_grace_s", "node_cleanup_globs", "node_log_max_mb",
                       "node_log_keep", "node_status_every_s", "node_tick_s"):
                continue                           # code-only defaults (spec section 3)
            assert key in cfg, (name, key)


# ------------------------------------------------------------------ windows
def test_n1_slot_window_and_midnight():
    job = _n1_job()
    assert sv.slot_at(job, _n1_at(14, 29)) is None
    s = sv.slot_at(job, _n1_at(14, 30))
    assert s["key"] == "2026-11-04T14:30Z" and s["end"] == _n1_at(16, 30)
    assert sv.slot_at(job, _n1_at(16, 30)) is None             # the end is exclusive
    late = _n1_job(start_utc="23:30", slot_minutes=90)
    s = sv.slot_at(late, _n1_at(0, 40, day=5))                   # after midnight UTC
    assert s and s["key"] == "2026-11-04T23:30Z"


def test_n1_slot_respects_days_and_lead():
    sat = _n1_job(name="live_trials", days=["sat"], start_utc="18:45", slot_minutes=12,
                  lead_seconds=300, min_minutes=12)
    assert sv.slot_at(sat, _n1_at(18, 45)) is None               # a Wednesday
    s = sv.slot_at(sat, _n1_at(18, 40, day=7))                   # Saturday, lead opens it
    assert s and s["opens"] == _n1_at(18, 40, day=7) and s["end"] == _n1_at(18, 57, day=7)
    assert sv.next_slot(sat, _n1_at(12, 0)) == _n1_at(18, 40, day=7)


def test_n1_backoff_doubles_and_caps():
    assert [sv.backoff(n, 30, 600) for n in range(0, 8)] == [0, 30, 60, 120, 240, 480, 600, 600]
    assert sv.backoff(500, 30, 600) == 600


# ------------------------------------------------------------------ the decision
def test_n1_resume_rule_after_a_power_cut():
    job = _n1_job()
    st = sv.new_job_state("2026-11-04T14:30Z")
    now = _n1_at(15, 50)                                        # back with 40 min left
    act, extra = sv.decide(job, st, now, sv.slot_at(job, now))
    assert act == "start" and extra == ["--minutes", "40"]      # ends on schedule
    now = _n1_at(16, 5)                                         # 25 min left < 30
    act, why = sv.decide(job, st, now, sv.slot_at(job, now))
    assert act == "skip" and "25.0 min left" in why and "needs 30" in why


def test_n1_on_time_start_passes_no_length():
    job = _n1_job()
    now = _n1_at(14, 31)                                        # inside the 120 s grace
    act, extra = sv.decide(job, sv.new_job_state(), now, sv.slot_at(job, now))
    assert act == "start" and extra == []
    no_arg = _n1_job(remaining_arg="")
    now = _n1_at(15, 0)
    assert sv.decide(no_arg, sv.new_job_state(), now, sv.slot_at(no_arg, now)) == ("start", [])


def test_n1_retry_cap_and_backoff_wait():
    job = _n1_job(attempts_per_day=2)
    st = sv.new_job_state("k")
    now = _n1_at(14, 40)
    slot = sv.slot_at(job, now)
    sv.on_started(st, now)
    sv.on_exit(st, 1, now, "exit 1", 30, 600)
    act, why = sv.decide(job, st, now + timedelta(seconds=10), slot)
    assert act == "wait" and "backing off" in why
    act, _ = sv.decide(job, st, now + timedelta(seconds=31), slot)
    assert act == "start"
    sv.on_started(st, now)
    sv.on_exit(st, 1, now, "exit 1", 30, 600)
    assert st["next_try"] == (now + timedelta(seconds=60)).isoformat(timespec="seconds")
    act, why = sv.decide(job, st, now + timedelta(minutes=5), slot)
    assert act == "skip" and "retry cap" in why


def test_n1_success_is_done_for_the_slot():
    job = _n1_job()
    st = sv.new_job_state("k")
    now = _n1_at(14, 31)
    sv.on_started(st, now)
    sv.on_exit(st, 0, now, "exit 0", 30, 600)
    assert st["done"] and st["failures"] == 0
    assert sv.decide(job, st, now, sv.slot_at(job, now)) == ("idle", "done for this slot")


def test_n1_never_two_streams_at_once():
    radar = _n1_job()
    other = _n1_job(name="live_trials")
    batch = _n1_job(name="report", stream=False)
    now = _n1_at(14, 31)
    slot = sv.slot_at(radar, now)
    act, why = sv.decide(other, sv.new_job_state(), now, slot, stream_busy="radar_live")
    assert act == "wait" and "never two at once" in why
    assert sv.decide(batch, sv.new_job_state(), now, slot, stream_busy="radar_live")[0] == "start"
    assert sv.decide(radar, sv.new_job_state(), now, slot, stream_busy="radar_live")[0] == "start"


def test_n1_pause_disk_and_hardware_gates():
    job = _n1_job()
    now = _n1_at(14, 31)
    slot = sv.slot_at(job, now)
    assert sv.decide(job, sv.new_job_state(), now, slot, paused="paused")[0] == "wait"
    assert sv.decide(job, sv.new_job_state(), now, slot, disk_ok=False) == (
        "wait", "free disk below the floor")
    assert sv.decide(job, sv.new_job_state(), now, slot, hardware_ok=False)[0] == "skip"
    assert sv.decide(_n1_job(enabled=False), sv.new_job_state(), now, slot)[0] == "idle"


def test_n1_interrupted_run_counts_and_retries_now():
    states = {"radar_live": {**sv.new_job_state("k"), "running": True, "attempts": 1,
                             "next_try": "2099-01-01T00:00:00+00:00"},
              "other": sv.new_job_state("k")}
    assert sv.recover_interrupted(states, _n1_at(15, 0)) == ["radar_live"]
    st = states["radar_live"]
    assert not st["running"] and st["failures"] == 1 and st["next_try"] == ""
    assert "interrupted" in st["last_reason"]


def test_n1_hang_and_overtime():
    assert sv.is_hung(100.0, 701.0, 600) and not sv.is_hung(100.0, 699.0, 600)
    assert not sv.is_hung(0.0, 10_000.0, 0)                      # 0 = watchdog off
    assert sv.is_overtime(0.0, 180 * 60 + 1, 180) and not sv.is_overtime(0.0, 100, 180)


# ------------------------------------------------------------------ secrets
def test_n1_redact_values_longest_first_and_bot_urls():
    tok = "123456789:AAH" + "x" * 32
    s = sv.redact(f"POST https://api.telegram.org/bot{tok}/sendMessage key=abcd-efgh-1234",
                  ["abcd-efgh-1234", "abcd-efgh"])
    assert tok not in s and "abcd" not in s and "bot***" in s
    # a token we were never told about is still caught by its URL shape
    s = sv.redact("Max retries exceeded with url: /bot987654321:AAzzzzzzzzzzzzzzzzzzzzzzzzz/getMe")
    assert "AAzzz" not in s
    assert sv.redact("short", ["ab"]) == "short"                 # < 6 chars is never a key


def test_n1_dotenv_secret_values():
    env = sv.parse_dotenv('# c\nYT_STREAM_KEY="abcd-1234-x"\nYT_STREAM_URL=rtmps://a.youtube.com/x\n'
                          "GEMINI_API_KEY=PASTE_YOUR_GEMINI_KEY\nTELEGRAM_BOT_TOKEN=1:AAbbbbbb\n")
    assert env["YT_STREAM_KEY"] == "abcd-1234-x"
    vals = sv.secret_values(env)
    assert "abcd-1234-x" in vals and "1:AAbbbbbb" in vals
    assert "rtmps://a.youtube.com/x" not in vals and not any("PASTE" in v for v in vals)


def test_n1_telegram_failure_is_redacted(monkeypatch, caplog):
    tok = "123456789:AA" + "q" * 33
    import urllib.request

    def boom(req, timeout=0):
        raise OSError(f"Max retries exceeded with url: {req.full_url}")
    monkeypatch.setattr(urllib.request, "urlopen", boom)
    with caplog.at_level(logging.WARNING, logger="tooldojo.node"):
        sv._send_telegram(tok, "42", "hello", [tok])
    assert caplog.text and tok not in caplog.text and "q" * 20 not in caplog.text


# ------------------------------------------------------------------ housekeeping
def test_n1_disk_guard_cleans_only_its_own_temp(tmp_path):
    app = tmp_path / "app"
    (app / "temp" / "live" / "seg_0001").mkdir(parents=True)
    (app / "temp" / "live" / "seg_0001" / "segment.ts").write_bytes(b"x" * 10)
    (app / "temp" / "live" / "radar_history.json").write_text("{}")
    (app / "state").mkdir()
    (app / "state" / "keep.json").write_text("{}")
    (tmp_path / "outside").mkdir()
    pats = ["temp/live/seg_*", "../outside", "/etc", "C:/Windows", "state/*", "temp/live/*.json"]
    got = sv.safe_cleanup_targets(app, pats, [app / "temp"])
    names = {p.name for p in got}
    assert "seg_0001" in names and "radar_history.json" in names
    assert "keep.json" not in names and "outside" not in names
    assert sv.safe_cleanup_targets(app, ["temp"], [app / "temp"]) == []   # never the root itself


def test_n1_disk_guard_wipes_targets_in_the_supervisor(tmp_path):
    sup = _n1_sup(tmp_path)
    seg = sup.app / "temp" / "live" / "seg_0009"
    seg.mkdir(parents=True)
    (seg / "segment.ts").write_bytes(b"x" * 1000)
    keep = sup.app / "temp" / "live" / "radar_history.json"
    keep.write_text("{}")
    assert sup.cleanup() == 1000
    assert not seg.exists() and keep.exists()


def test_n1_rotate_file(tmp_path):
    p = tmp_path / "job.log"
    for i in range(4):
        p.write_text(f"run {i}" + "x" * 100)
        assert sv.rotate_file(p, 50, 2)
    assert not p.exists()
    assert (tmp_path / "job.log.1").read_text().startswith("run 3")
    assert (tmp_path / "job.log.2").read_text().startswith("run 2")
    assert not (tmp_path / "job.log.3").exists()
    p.write_text("tiny")
    assert not sv.rotate_file(p, 50, 2)


def test_n1_clock_skew_from_date_header():
    local = datetime(2026, 11, 4, 12, 0, 0, tzinfo=UTC)
    assert sv.skew_seconds("Wed, 04 Nov 2026 12:03:00 GMT", local) == 180
    assert sv.skew_seconds("Wed, 04 Nov 2026 11:59:30 GMT", local) == -30
    assert sv.skew_seconds("garbage", local) is None
    assert sv.skew_seconds("Wed, 04 Nov 2020 12:00:00 GMT", local) is None   # wild: ignored


def test_n1_update_plan():
    assert sv.update_plan("a" * 40, "a" * 40, "", "")[0] == "skip"
    assert sv.update_plan("a" * 40, "b" * 40, "", "")[0] == "apply"
    assert "import check" in sv.update_plan("a" * 40, "b" * 40, "", "b" * 40)[1]
    assert "edited on this PC" in sv.update_plan("a" * 40, "b" * 40, " M config.json", "")[1]
    assert sv.update_plan("", "b", "", "")[0] == "skip"


def test_n1_import_check_code_runs_and_filters_names(tmp_path):
    code = sv.import_check_code(ROOT, ["json", "os; import shutil", "live_preflight"])
    assert "os; import shutil" not in code
    ns = {}
    exec(compile(code, "<check>", "exec"), ns)                  # stdlib-only modules


# ------------------------------------------------------------------ profile + children
def test_n1_profile_env_auto_forced_insufficient_and_fallback():
    env, ok = sv.profile_env({"stream_profile": "1080p30", "encoder": "h264_qsv"})
    assert ok and env["RADAR_PROFILE"] == "1080p30" and env["RADAR_ENCODER"] == "h264_qsv"
    env, ok = sv.profile_env({"stream_profile": "1080p30", "encoder": "h264_qsv"}, "720p30_x264")
    assert ok and (env["RADAR_PROFILE"], env["RADAR_ENCODER"]) == ("720p30", "libx264")
    assert sv.profile_env({"stream_profile": "insufficient"}) == ({}, False)
    env, ok = sv.profile_env({})                                # no preflight yet
    assert ok and (env["RADAR_PROFILE"], env["RADAR_ENCODER"]) == ("720p30", "libx264")
    env, _ = sv.profile_env({"stream_profile": "4k", "encoder": "nvenc"})
    assert env["RADAR_ENCODER"] == "libx264"


def test_n1_expand_cmd_and_child_python(tmp_path):
    assert sv.expand_cmd(["{python}", "{app}/x.py"], "P", Path("A")) == ["P", "A/x.py"]
    (tmp_path / "pythonw.exe").write_text("")
    (tmp_path / "python.exe").write_text("")
    assert sv.child_python(str(tmp_path / "pythonw.exe")) == str(tmp_path / "python.exe")
    assert sv.child_python(str(tmp_path / "python.exe")) == str(tmp_path / "python.exe")


@pytest.mark.skipif(os.name != "nt", reason="Windows creation flags")
def test_n1_children_are_hidden_and_below_normal():
    kw = sv.hidden_popen_kwargs()
    flags = kw["creationflags"]
    assert flags & 0x08000000                       # CREATE_NO_WINDOW
    assert flags & 0x00004000                       # BELOW_NORMAL_PRIORITY_CLASS
    assert not flags & 0x00000008                   # never DETACHED_PROCESS (see module doc)
    assert not flags & 0x00000010                   # never CREATE_NEW_CONSOLE
    assert kw["startupinfo"].wShowWindow == 0       # SW_HIDE


@pytest.mark.skipif(os.name != "nt", reason="msvcrt byte lock")
def test_n1_single_instance_lock(tmp_path):
    a = sv.acquire_lock(tmp_path / "s.lock")
    assert a is not None
    assert sv.acquire_lock(tmp_path / "s.lock") is None
    a.close()
    b = sv.acquire_lock(tmp_path / "s.lock")
    assert b is not None
    b.close()


# ------------------------------------------------------------------ the loop, with fakes
class _N1FakeChild:
    made: list = []
    fail_for: set = set()

    def __init__(self, name, cmd, cwd, env, log_path, secrets, priority="below_normal",
                 cpu_cap=0):
        if name in self.fail_for:
            raise FileNotFoundError("no such exe")
        self.name, self.cmd, self.env = name, cmd, env
        self.pid, self.tail, self.code, self.killed = 4242, ["line"], None, False
        self.last_output = self.started = time.monotonic()
        _N1FakeChild.made.append(self)

    def poll(self):
        return self.code

    def kill(self):
        self.killed, self.code = True, 1

    def close(self, code):
        pass


def _n1_sup(tmp_path, jobs=None, now=None, **cfg):
    app = tmp_path / "app"
    app.mkdir(exist_ok=True)
    (app / ".env").write_text("YT_STREAM_KEY=abcd-efgh-ijkl-mnop-qrst\n"
                              "TELEGRAM_BOT_TOKEN=123456789:AA" + "t" * 33 + "\n"
                              "NODE_TELEGRAM_CHAT_ID=42\n", encoding="utf-8")
    conf = dict(sv.DEFAULTS)
    conf.update(cfg)
    sup = sv.Supervisor(app, tmp_path / "data", conf, jobs if jobs is not None else [], python="PY")
    fixed = now or _n1_at(14, 31)
    sup.now = lambda: fixed
    return sup


def _n1_raw(name, **over):
    raw = {"name": name, "stream": False, "cmd": ["{python}", f"{name}.py"], "days": "daily",
           "start_utc": "14:30", "slot_minutes": 60, "min_minutes": 5, "max_minutes": 30,
           "hang_seconds": 60, "attempts_per_day": 3}
    raw.update(over)
    return raw


def test_n1_one_job_failing_to_start_never_stops_the_others(tmp_path, monkeypatch):
    monkeypatch.setattr(sv, "Child", _N1FakeChild)
    _N1FakeChild.made, _N1FakeChild.fail_for = [], {"broken"}
    sup = _n1_sup(tmp_path, [_n1_raw("broken"), _n1_raw("fine"), {"name": "bad row"}])
    sup.tick()
    assert [c.name for c in _N1FakeChild.made] == ["fine"]
    st = sup.state["jobs"]["broken"]
    assert st["attempts"] == 1 and st["failures"] == 1 and "could not start" in st["last_reason"]
    assert sup.job_errors and json.loads(sup.status_path.read_text())["jobs"]["fine"]["running"]
    assert _N1FakeChild.made[0].cmd == ["PY", "fine.py"]


def test_n1_watchdog_kills_a_hung_child_and_backs_off(tmp_path, monkeypatch):
    monkeypatch.setattr(sv, "Child", _N1FakeChild)
    _N1FakeChild.made, _N1FakeChild.fail_for = [], set()
    sup = _n1_sup(tmp_path, [_n1_raw("hangs", hang_seconds=60)])
    sup.tick()
    child = _N1FakeChild.made[0]
    child.last_output -= 61
    sup.tick()
    st = sup.state["jobs"]["hangs"]
    assert child.killed and not st["running"] and st["failures"] == 1
    assert "hung" in st["last_reason"] and st["next_try"]
    assert len(_N1FakeChild.made) == 1                       # backing off, not restarted yet


def test_n1_stream_env_and_daily_flag_reach_the_child(tmp_path, monkeypatch):
    monkeypatch.setattr(sv, "Child", _N1FakeChild)
    _N1FakeChild.made, _N1FakeChild.fail_for = [], set()
    sup = _n1_sup(tmp_path, [_n1_raw("radar", stream=True, env={"X": "1"})])
    sup.local_path.parent.mkdir(parents=True, exist_ok=True)
    sup.local_path.write_text(json.dumps({"stream_profile": "1080p30", "encoder": "h264_qsv"}))
    sup.tick()
    env = _N1FakeChild.made[0].env
    assert env["RADAR_PROFILE"] == "1080p30" and env["RADAR_ENCODER"] == "h264_qsv"
    assert env["TOOLDOJO_NODE_SCHEDULED"] == "1" and env["X"] == "1"
    assert env["PYTHONIOENCODING"] == "utf-8"


def test_n1_pause_file_stops_new_starts(tmp_path, monkeypatch):
    monkeypatch.setattr(sv, "Child", _N1FakeChild)
    _N1FakeChild.made, _N1FakeChild.fail_for = [], set()
    sup = _n1_sup(tmp_path, [_n1_raw("radar")])
    (sup.data / "PAUSE").parent.mkdir(parents=True, exist_ok=True)
    (sup.data / "PAUSE").write_text("")
    sup.tick()
    assert _N1FakeChild.made == []
    assert "PAUSE" in json.loads(sup.status_path.read_text())["paused"]


def test_n1_alerts_are_redacted_and_rate_limited(tmp_path, monkeypatch):
    sent = []

    class _N1SyncThread:
        def __init__(self, target, args, daemon=True):
            self.target, self.args = target, args

        def start(self):
            self.target(*self.args)
    monkeypatch.setattr(sv.threading, "Thread", _N1SyncThread)
    monkeypatch.setattr(sv, "_send_telegram", lambda tok, chat, text, secrets: sent.append(text))
    sup = _n1_sup(tmp_path, [], node_alert_max_per_day=2)
    for _ in range(4):
        sup.alert("radar failed: key abcd-efgh-ijkl-mnop-qrst in ffmpeg output")
    assert len(sent) == 2
    assert all("abcd-efgh-ijkl-mnop-qrst" not in t and "***" in t for t in sent)
    sup2 = _n1_sup(tmp_path, [], node_alert_telegram=False)
    sent.clear()
    sup2.alert("x")
    assert sent == []


def test_n1_supervisor_log_lines_are_redacted(tmp_path, caplog):
    sup = _n1_sup(tmp_path, [])
    with caplog.at_level(logging.INFO, logger="tooldojo.node"):
        sup.say("ffmpeg: rtmps://a.rtmps.youtube.com/live2/abcd-efgh-ijkl-mnop-qrst failed")
    assert "abcd-efgh-ijkl-mnop-qrst" not in caplog.text and "***" in caplog.text


# ------------------------------------------------------------------ preflight
def test_n1_producer_cost():
    assert pf.producer_cost(200, 2.0) == pytest.approx(0.2 * 1.5 + 0.5)
    assert pf.producer_cost(None, 2.0) is None and pf.producer_cost(100, 0) is None


def test_n1_select_profile_prefers_quick_sync_then_720p_x264():
    rows = [{"profile": "1080p30", "encoder": "h264_qsv", "ok": False, "error": "MFX -9"},
            {"profile": "720p30", "encoder": "h264_qsv", "ok": False, "error": "MFX -9"},
            {"profile": "720p30", "encoder": "libx264", "ok": True, "speed": 3.0},
            {"profile": "1080p30", "encoder": "libx264", "ok": True, "speed": 9.0}]
    got = pf.select_profile(rows, 150, 3000)
    assert (got["stream_profile"], got["encoder"]) == ("720p30", "libx264")   # 0.225+0.333
    rows[0].update(ok=True, speed=4.0, error="")
    assert pf.select_profile(rows, 150, 3000)["encoder"] == "h264_qsv"
    slow = [{"profile": "720p30", "encoder": "libx264", "ok": True, "speed": 1.1}]
    got = pf.select_profile(slow, 250, 3000)
    assert got["stream_profile"] == "insufficient" and "cost" in got["verdict"]
    assert pf.select_profile(rows, None, 3000)["stream_profile"] == "insufficient"
    assert "RAM" in pf.select_profile(rows, 150, 600)["verdict"]
    # 1080p30 x264 is never auto-picked, however fast (requirement 2: lowest load)
    only = [{"profile": "1080p30", "encoder": "libx264", "ok": True, "speed": 50}]
    assert pf.select_profile(only, 10, 3000)["stream_profile"] == "insufficient"


# ------------------------------------------------------------------ radar_live profile args
def test_n1_radar_qsv_720p_segment_args():
    import radar_live as rl
    a = rl.segment_args("l.txt", None, 10, "s.ts", encoder="h264_qsv", profile="720p30")
    s = " ".join(a)
    assert a[a.index("-init_hw_device") + 1].endswith("child_device_type=d3d11va")
    assert a.index("-init_hw_device") < a.index("-i")
    assert "scale=1280:720" in s and "format=nv12" in s
    assert a[a.index("-c:v") + 1] == "h264_qsv" and a[a.index("-b:v") + 1] == "8000k"
    assert a[a.index("-bf") + 1] == "0" and "-crf" not in a
    assert a[a.index("-frames:v") + 1] == "300" and a[a.index("-g") + 1] == "60"


def test_n1_radar_default_args_unchanged():
    import radar_live as rl
    a = rl.segment_args("l.txt", None, 10, "s.ts")
    s = " ".join(a)
    assert "scale=" not in s and "-init_hw_device" not in a and "format=yuv420p" in s
    assert a[a.index("-c:v") + 1] == "libx264" and a[a.index("-crf") + 1] == "20"
    assert a[a.index("-maxrate") + 1] == "14000k"
    x = rl.segment_args("l.txt", None, 10, "s.ts", encoder="libx264", profile="720p30")
    assert "scale=1280:720" in " ".join(x) and x[x.index("-maxrate") + 1] == "8000k"


def test_n1_radar_end_card_knows_the_node_schedule(monkeypatch):
    import radar_live as rl
    monkeypatch.setenv("TOOLDOJO_NODE_SCHEDULED", "1")
    monkeypatch.setattr(rl.subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(AssertionError))
    assert rl.schedule_installed() is True


# ------------------------------------------------------------------ bundle
def test_n1_bundle_keeps_code_and_drops_secrets_and_output():
    for p in ("factverse/radar.py", "scripts/radar_live.py", "node/install.ps1",
              "assets/radar/radar.html", "config.json", ".env.example", "requirements.txt"):
        assert nb.include(p), p
    for p in (".env", "sub/.env", ".env.local", "client_secret_123.json", "youtube_token.pickle",
              "output/demo/x.png", "state/ledger.json", "tests/test_x.py", ".github/workflows/a.yml",
              "docs/debate/x.md", "logs/a.log", "temp/live/x.ts", "yt_token.json", "ig_session.json",
              "used_urls.json"):
        assert not nb.include(p), p


def test_n1_bundle_scan_finds_credential_shapes():
    assert nb.scan("a.py", b"key = 'AIza" + b"A" * 35 + b"'") == ["Google API key"]
    assert nb.scan("a.txt", b"123456789:AA" + b"b" * 33) == ["Telegram bot token"]
    assert nb.scan("a.md", b"stream abcd-1234-efgh-5678-ijkl") == ["YouTube stream key"]
    assert nb.scan("a.md", b"-----BEGIN RSA PRIVATE KEY-----") == ["private key"]
    assert nb.scan("a.md", b"YT_STREAM_KEY=PASTE_YOUR_KEY") == []


def test_n1_committed_tree_is_clean_of_credentials():
    """The real repo, as the bundle would carry it, has no credential shape in it."""
    import subprocess
    try:
        files = nb.committed_files()
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        pytest.skip("no git checkout here")
    hits = [(p, nb.scan(p, d)) for p, d in files if nb.include(p)]
    assert [h for h in hits if h[1]] == []


# ------------------------------------------------------------------ PowerShell 5.1
def test_n1_powershell_scripts_are_ps51_safe():
    for name in ("install.ps1", "uninstall.ps1", "status.ps1"):
        text = (ROOT / "node" / name).read_text(encoding="utf-8")
        code = "\n".join(l for l in text.splitlines() if not l.lstrip().startswith("#"))
        assert "&&" not in code and "||" not in code, name          # parser error in 5.1
        assert "??" not in code and "?." not in code, name
        assert not re.search(r"\)\s*\?\s*[^\s:]+\s*:", code), name  # no ternary
        assert "-DryRun" in text or name == "status.ps1"

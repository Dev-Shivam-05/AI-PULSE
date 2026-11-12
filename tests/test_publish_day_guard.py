"""The duplicate-publish guard must key on the day a video goes PUBLIC, not only on
the day the run happened.

GitHub's cron fires 4-8 h late (observed every day 2026-10-23..11-11), and
`scheduling.long_slot` rolls a run past 16:30 UTC to TOMORROW's 16:45 slot. So a late
run on day N-1 and an earlier run on day N both target day N's slot, while
`already_published_today` only compared the RUN day. The ledger shows it happened 6
times (07-29, 09-05, 09-12, 09-19, 10-17, 10-24): two long-forms public at the same
16:45. Under the recovery cohort that is two videos on one Mon/Wed/Fri slot.

Tests never touch the network: `git fetch` / `git show` are stubbed.
"""
import datetime as dt
import json
import subprocess

from factverse import ai_pipeline as ap


def _guard_ledger(monkeypatch, tmp_path, rows, slot_day):
    """Serve `rows` as origin/main's ledger, an empty local ledger, and a fixed slot."""
    text = "\n".join(json.dumps(r) for r in rows) + "\n"

    def fake_run(args, **kw):
        out = text if args[:2] == ["git", "show"] else ""
        return subprocess.CompletedProcess(args, 0, stdout=out, stderr="")
    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(ap, "RUNS_LOG", tmp_path / "runs.jsonl")
    monkeypatch.setattr(ap.scheduling, "long_slot", lambda: f"{slot_day}T16:45:00Z")
    monkeypatch.delenv("FORCE_PUBLISH", raising=False)


def _guard_days():
    today = dt.datetime.utcnow().date()
    return today - dt.timedelta(days=1), today, today + dt.timedelta(days=1)


def test_guard_blocks_a_second_video_for_a_slot_yesterday_already_filled(monkeypatch, tmp_path):
    """The 10-23 / 10-24 shape: yesterday's late run scheduled today's slot; today's
    early run would schedule the same slot again."""
    yesterday, today, _ = _guard_days()
    rows = [{"timestamp": f"{yesterday}T18:31:42", "status": "PUBLISHED",
             "publish_at": f"{today}T16:45:00Z", "title": "earshot"}]
    _guard_ledger(monkeypatch, tmp_path, rows, slot_day=today)
    assert ap.already_published_today() is True


def test_guard_lets_the_next_slot_through(monkeypatch, tmp_path):
    """Yesterday's run filled today's slot; today's LATE run targets tomorrow — publish."""
    yesterday, today, tomorrow = _guard_days()
    rows = [{"timestamp": f"{yesterday}T19:00:00", "status": "PUBLISHED",
             "publish_at": f"{today}T16:45:00Z", "title": "a"}]
    _guard_ledger(monkeypatch, tmp_path, rows, slot_day=tomorrow)
    assert ap.already_published_today() is False


def test_guard_still_blocks_a_second_run_on_the_same_day(monkeypatch, tmp_path):
    """The original run-day rule is unchanged (primary cron + retry cron)."""
    _, today, tomorrow = _guard_days()
    rows = [{"timestamp": f"{today}T19:43:25", "status": "PUBLISHED",
             "publish_at": f"{tomorrow}T16:45:00Z", "title": "a"}]
    _guard_ledger(monkeypatch, tmp_path, rows, slot_day=tomorrow)
    assert ap.already_published_today() is True


def test_guard_ignores_failed_rows_and_odd_publish_at(monkeypatch, tmp_path):
    yesterday, today, _ = _guard_days()
    rows = [{"timestamp": f"{yesterday}T19:00:00", "status": "QA_FAILED",
             "publish_at": f"{today}T16:45:00Z"},
            {"timestamp": f"{yesterday}T19:05:00", "status": "PUBLISHED", "publish_at": None},
            {"timestamp": f"{yesterday}T19:06:00", "status": "PUBLISHED", "publish_at": 12345},
            {"timestamp": f"{yesterday}T19:07:00", "status": "PUBLISHED", "publish_at": ["x"]}]
    _guard_ledger(monkeypatch, tmp_path, rows, slot_day=today)
    assert ap.already_published_today() is False


def test_guard_survives_an_unreadable_slot(monkeypatch, tmp_path):
    """long_slot raising must not raise out of the guard: fall back to the run-day rule."""
    yesterday, today, _ = _guard_days()
    rows = [{"timestamp": f"{yesterday}T19:00:00", "status": "PUBLISHED",
             "publish_at": f"{today}T16:45:00Z"}]
    _guard_ledger(monkeypatch, tmp_path, rows, slot_day=today)
    monkeypatch.setattr(ap.scheduling, "long_slot", lambda: 1 / 0)
    assert ap.already_published_today() is False


def test_guard_force_publish_still_overrides(monkeypatch, tmp_path):
    yesterday, today, _ = _guard_days()
    rows = [{"timestamp": f"{yesterday}T19:00:00", "status": "PUBLISHED",
             "publish_at": f"{today}T16:45:00Z"}]
    _guard_ledger(monkeypatch, tmp_path, rows, slot_day=today)
    monkeypatch.setenv("FORCE_PUBLISH", "1")
    assert ap.already_published_today() is False

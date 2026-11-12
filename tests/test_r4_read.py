"""v3-R.4: the cohort read — collection, D13 reads, D14 verdict (docs/spec/ai-pulse-v3r.md).

No network: the Analytics client is a fake that records its queries. Two tests read the
REAL committed state files to check the frozen numbers (W0 and a known video length).
"""
import datetime as dt
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from factverse import analytics            # noqa: E402
from factverse import cohort as co         # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def _r4_snaps():
    out = []
    for line in (ROOT / "state" / "analytics.jsonl").read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out


# ================================================================ frozen numbers
def test_r4_frozen_values_match_the_spec():
    spec = (ROOT / "docs" / "spec" / "ai-pulse-v3r.md").read_text(encoding="utf-8")
    assert len(co.BASELINE_IDS) == 11 and all(v in spec for v in co.BASELINE_IDS)
    assert "W0 = 13 min" in spec and co.W0_MINUTES == 13.0
    assert (co.R0_TARGET_S, co.R0_LIFT, co.SHORTS_STAYED_MIN) == (7.0, 8.0, 22.0)
    assert (co.FLOOR_LONG, co.FLOOR_BASE, co.FLOOR_SHORTS, co.SHORTS_MIN_IMPRESSIONS) == (4, 4, 4, 50)
    assert (co.DELIVERY_DAY, co.OUTCOME_DAY, co.PLANNED_LONG, co.PLANNED_SHORTS) == (14, 21, 6, 6)


def test_r4_w0_recomputes_from_the_real_collector_data():
    snaps = _r4_snaps()
    mins = [co.first7_minutes(v, snaps) for v in co.BASELINE_IDS]
    assert all(m is not None for m in mins)
    assert co._median(mins) == co.W0_MINUTES


def test_r4_duration_comes_from_the_collectors_own_numbers():
    d = co.duration_of("4MTEDi4MdnQ", _r4_snaps())        # gpu-unlock is 347 s long
    assert d is not None and abs(d - 347) / 347 < 0.03
    assert co.duration_of("nope", _r4_snaps()) is None


# ================================================================ windows and collection
def test_r4_window_is_the_age_bands_seven_days():
    assert co.window(dt.date(2026, 11, 16)) == (dt.date(2026, 11, 16), dt.date(2026, 11, 22))


def test_r4_due_waits_for_the_lag_and_skips_stored_curves():
    vids = {"A": dt.date(2026, 11, 16), "B": dt.date(2026, 11, 16), "C": None}
    stored = {"B": {"curve": [[i / 10, 0.5] for i in range(10)]}}
    assert co.due(vids, stored, dt.date(2026, 11, 23)) == []                 # lag not over
    assert co.due(vids, stored, dt.date(2026, 11, 24)) == [("A", dt.date(2026, 11, 16), dt.date(2026, 11, 22))]


class _R4Exec:
    def __init__(self, fn):
        self.fn = fn

    def execute(self):
        return self.fn()


class _R4Yta:
    def __init__(self, boom=()):
        self.calls, self.boom = [], set(boom)

    def reports(self):
        return self

    def query(self, **kw):
        self.calls.append(kw)
        vid = kw.get("filters", "").split("==")[-1]

        def go():
            if vid in self.boom:
                raise RuntimeError("refused")
            return {"rows": [[i / 100, 1.0 - i / 200, 0.5] for i in range(1, 101)]}
        return _R4Exec(go)


def _r4_rows():
    rows = [{"status": "PUBLISHED", "format": "tool", "youtube_url": f"https://youtube.com/watch?v={v}",
             "publish_at": "2026-10-20T16:45:00Z"} for v in co.BASELINE_IDS]
    rows.append({"status": "PUBLISHED", "format": "tool", "title": "gpu-unlock: which GPUs?",
                 "youtube_url": "https://youtube.com/watch?v=COHORT00001", "publish_at": "2026-11-16T16:45:00Z",
                 "shorts": [{"url": "https://youtube.com/watch?v=SHORT000001", "engine": "native"}]})
    return rows


def test_r4_collect_reads_baseline_once_and_cohort_when_due(monkeypatch):
    monkeypatch.setitem(co.fv.CONFIG, "cohort_start", "2026-11-16")
    yta = _R4Yta(boom={"Q-P_P-Y1-to"})
    out = co.collect(yta, _r4_rows(), [], dt.date(2026, 11, 24))
    assert set(out) == set(co.BASELINE_IDS) | {"COHORT00001"}
    assert out["COHORT00001"]["start"] == "2026-11-16" and out["COHORT00001"]["end"] == "2026-11-22"
    assert len(out["COHORT00001"]["curve"]) == 100 and "error" in out["Q-P_P-Y1-to"]
    assert all(c["dimensions"] == "elapsedVideoTimeRatio" for c in yta.calls)
    again = co.collect(_R4Yta(), _r4_rows(), [{"cohort_reads": out}], dt.date(2026, 11, 25))
    assert set(again) == {"Q-P_P-Y1-to"}                                      # only the failed one retries


# ================================================================ reads and the verdict
def test_r4_retention_at_seven_seconds():
    rd = {"curve": [[i / 100, 1.0 - i / 200] for i in range(1, 101)]}
    assert co.retention_at(rd, 100.0) == pytest.approx(96.5, abs=0.01)     # point at 7 s: 1 - 0.07/2
    assert co.retention_at({"curve": [[0.1, 0.5]]}, 100.0) is None          # not usable
    assert co.retention_at(rd, None) is None


@pytest.mark.parametrize("ret, mins, r0, nc, nb, out", [
    (None, 20, 50, 6, 11, "pending"), (60, None, 50, 6, 11, "pending"), (60, 20, None, 6, 11, "pending"),
    (60, 20, 50, 3, 11, "inconclusive"), (60, 20, 50, 6, 3, "inconclusive"),
    (58, 14, 50, 6, 11, "promising"), (57.9, 14, 50, 6, 11, "mixed"), (58, 13, 50, 6, 11, "mixed"),
    (50, 13, 50, 6, 11, "stop"), (40, 10, 50, 4, 4, "stop"), (55, 12, 50, 6, 11, "mixed"),
])
def test_r4_verdict_truth_table(ret, mins, r0, nc, nb, out):
    assert co.verdict(ret, mins, r0, nc, nb) == out


def test_r4_delivery_counts_what_shipped():
    rows = _r4_rows() + [
        {"status": "PUBLISHED", "format": "news", "youtube_url": "https://youtube.com/watch?v=NEWS0000001",
         "publish_at": "2026-11-18T16:45:00Z", "shorts": [{"url": "u", "engine": "crop"}]},
        {"status": "NO_SCRIPT", "format": "tool", "timestamp": "2026-11-20T12:30:00"}]
    replied = {"c1": {"status": "answered", "published": "2026-11-17T10:00:00Z", "at": "2026-11-17T12:30:00"},
               "c2": {"status": "answered", "published": "2026-11-15T10:00:00Z", "at": "2026-11-17T12:30:00"},
               "c3": {"status": "not_question"}}
    d = co.delivery(rows, replied, dt.date(2026, 11, 16))
    assert d["long_forms"] == 1 and d["filler"] == 1 and d["native_shorts"] == 1 and d["crop_shorts"] == 1
    assert d["logged_misses"] == 1 and d["replies"] == 2 and d["replies_on_time"] == 1


def test_r4_shorts_read_needs_the_csv_and_its_floor(tmp_path):
    assert co.shorts_read(None)["verdict"] == "pending"
    rows = [{"video": f"s{i}", "feed_impressions": 120, "stayed_pct": 25.0} for i in range(4)]
    assert co.shorts_read(rows)["verdict"] == "promising"
    rows[0]["feed_impressions"] = 10
    assert co.shorts_read(rows)["verdict"] == "inconclusive"                  # 3 exposed < floor 4
    p = tmp_path / "s.csv"
    p.write_text("video,feed_impressions,stayed_pct\nabc,120,31.5\nbad,x,1\n", encoding="utf-8")
    assert co.read_shorts_csv(p) == [{"video": "abc", "feed_impressions": 120, "stayed_pct": 31.5}]


def test_r4_outcome_and_report_show_every_upload(monkeypatch):
    monkeypatch.setitem(co.fv.CONFIG, "cohort_start", "2026-11-16")
    curve = [[i / 100, 1.0 - i / 200] for i in range(1, 101)]
    snaps = [{"cohort_reads": {v: {"curve": curve} for v in list(co.BASELINE_IDS) + ["COHORT00001"]},
              "ledger_headers": ["video", "views", "estimatedMinutesWatched", "averageViewDuration",
                                 "averageViewPercentage"],
              "ledger_videos": [[v, 10, 5, 30, 10.0] for v in list(co.BASELINE_IDS) + ["COHORT00001"]],
              "age_bands": {v: {"perf": {"7d": {"minutes": 20, "complete": True}}}
                            for v in list(co.BASELINE_IDS) + ["COHORT00001"]}}]
    oc = co.outcome(_r4_rows(), snaps, dt.date(2026, 11, 16))
    assert oc["uploads"] == 1 and oc["baseline_curves"] == 11 and oc["long_verdict"] == "inconclusive"
    rep = co.format_report(dt.date(2026, 12, 7), dt.date(2026, 11, 16),
                           co.delivery(_r4_rows(), {}, dt.date(2026, 11, 16)), oc)
    assert "day 21" in rep and "COHORT00001" in rep and "Long-form verdict: inconclusive" in rep


def test_r4_main_never_raises_and_writes_outside_docs(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(co, "OUT_DIR", tmp_path / "cohort")
    assert co.main([]) == 0
    assert (tmp_path / "cohort" / "report.md").exists()
    monkeypatch.setattr(co.learn, "read_runs", lambda path=None: 1 / 0)
    assert co.main([]) == 0 and "cohort read failed" in capsys.readouterr().out
    assert "output/cohort/" in (ROOT / ".gitignore").read_text(encoding="utf-8")


def test_r4_the_collector_carries_the_reads_behind_its_kill_switch(monkeypatch):
    src = (ROOT / "factverse" / "analytics.py").read_text(encoding="utf-8")
    i = src.index('if fv.flag("cohort_reads", False):')
    assert "cohort.collect(" in src[i:i + 900] and 'snap["cohort_reads"]' in src[i:i + 900]
    cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    assert cfg["cohort_reads"] is True

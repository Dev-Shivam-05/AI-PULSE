"""Suite-wide defaults.

v3-P.1 turned on three config switches (`evidence_engine`, `evidence_required`,
`claim_substantiation`). With them on, every older test that reaches script_tool,
build_script or run() would gather evidence over the NETWORK, skip its fixture
candidate for having none, or rewrite its fixture title. Tests never touch the
network (CLAUDE.md), and the older tests pin the behaviour without those
switches — so they are OFF by default here, through the env override fv.flag
already honours. tests/test_p1_evidence.py turns them on explicitly per test.

v3-P.2 adds three more for the same reason: `pilot_a` would read and assign from
the real state/pilot_a.json, `query_map` would rename every evidence-backed
fixture title and write state/first_seen.json, `pilot_retention` would add
Analytics queries. tests/test_p2_opening.py turns them on per test.
"""
import pytest


@pytest.fixture(autouse=True)
def _p1_evidence_switches_off(monkeypatch):
    for name in ("EVIDENCE_ENGINE", "EVIDENCE_REQUIRED", "CLAIM_SUBSTANTIATION",
                 "PILOT_A", "QUERY_MAP", "PILOT_RETENTION"):
        monkeypatch.setenv(name, "0")


@pytest.fixture(autouse=True)
def _m1_network_switches_off(monkeypatch):
    """Integration (v3-M.1 + v3-P.1): `followup_candidates` and `shadow_queue` read
    the REAL state files and, now that evidence.py exists, call `evidence.probe`
    — GitHub/HF over the network — for any family with enough search views. Every
    older build_script("tool") test reaches memory.followup_items, so once main's
    analytics carry `search_terms` they would go to the network. Off by default;
    tests/test_m1_memory.py turns them on with `_m1_flag`, which overrides this."""
    for name in ("FOLLOWUP_CANDIDATES", "SHADOW_QUEUE"):
        monkeypatch.setenv(name, "0")


@pytest.fixture(autouse=True)
def _r2_cohort_off(monkeypatch):
    """v3-R: `recovery_cohort` is ON in config.json, and it changes the lane, the
    schedule, the Shorts and the evidence route. Every older test pins the
    behaviour without it, so it is OFF here; tests/test_r2_cohort.py turns it on
    per test (the same env override fv.flag honours)."""
    monkeypatch.setenv("RECOVERY_COHORT", "0")

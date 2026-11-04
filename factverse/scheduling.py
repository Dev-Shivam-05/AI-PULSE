"""
Distribution scheduling: spaced Shorts drops via YouTube's publishAt.

Rule: never dump Shorts together. Each Short uploads as PRIVATE with a
publishAt timestamp on the fixed daily grid (07:00 / 12:00 / 17:00 / 21:00 IST,
minimum 4h apart by construction). YouTube itself holds the queue — nothing
needs to persist across ephemeral CI runs, and yesterday's tail slots naturally
interleave with today's, so consecutive slots come from different videos.

validate_distribution() is the hard tripwire: any future edit that violates
the spacing or volume rules raises PipelineViolation instead of publishing.
"""
from __future__ import annotations

import datetime as dt

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
SLOT_HOURS = (7, 12, 17, 21)          # IST; consecutive gaps 5h/5h/4h/10h — all >= 4h
MIN_GAP_HOURS = 4
MAX_DAILY_UPLOADS = 5                  # 1 long + at most 4 scheduled Shorts


class PipelineViolation(RuntimeError):
    """A hard distribution rule was about to be broken. Never catch-and-continue."""


def next_slots(n: int, after: dt.datetime | None = None) -> list[str]:
    """The next `n` publish slots (RFC3339 UTC strings) strictly in the future."""
    now = (after or dt.datetime.now(dt.timezone.utc)).astimezone(IST)
    cursor = now + dt.timedelta(minutes=20)   # publishAt must be safely in the future
    out: list[dt.datetime] = []
    day = cursor.date()
    while len(out) < n:
        for h in SLOT_HOURS:
            t = dt.datetime.combine(day, dt.time(h, 0), IST)
            if t > cursor and len(out) < n:
                out.append(t)
        day += dt.timedelta(days=1)
    validate_distribution(out)
    return [t.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") for t in out]


def validate_distribution(slots: list[dt.datetime]) -> None:
    """Assert the immutable distribution rules. Raises PipelineViolation."""
    if len(slots) + 1 > MAX_DAILY_UPLOADS:
        raise PipelineViolation(f"volume dump: {len(slots)} shorts queued (max {MAX_DAILY_UPLOADS - 1})")
    for a, b in zip(slots, slots[1:]):
        gap = (b - a).total_seconds() / 3600
        if gap < MIN_GAP_HOURS - 0.01:
            raise PipelineViolation(f"spacing violation: {gap:.1f}h between drops (min {MIN_GAP_HOURS}h)")


def validate_shorts_batch(shorts: list, hooks: list) -> None:
    """Every published Short must be a re-hooked cut, never a raw slice."""
    if len(shorts) > len([h for h in hooks if h and str(h).strip()]):
        raise PipelineViolation("un-rehooked short in batch: every Short needs fresh hook text")


def long_slot(now: dt.datetime | None = None) -> str:
    """The fixed daily long-form publish time (RFC3339 UTC) — render whenever the
    cron fires, publish at the same clock time every day. Decouples render from
    publish and makes the slot an audience appointment."""
    from factverse import config as fv
    hh, mm = (str(fv.setting("longform_slot_utc", "16:45")).split(":") + ["0"])[:2]
    now = now or dt.datetime.now(dt.timezone.utc)
    slot = now.replace(hour=int(hh), minute=int(mm), second=0, microsecond=0)
    if slot < now + dt.timedelta(minutes=15):
        slot += dt.timedelta(days=1)   # missed today's slot — tomorrow's (guard prevents dupes)
    return slot.strftime("%Y-%m-%dT%H:%M:%SZ")


PILOT_B_SLOTS = ((0, 18, 45), (1, 1, 30))   # v3-S.1: (day offset from D, hour, minute) UTC


def pilot_b_slots(long_publish_rfc3339: str, now: dt.datetime | None = None) -> list[str] | None:
    """v3-S.1 Pilot B: exactly 18:45 UTC on production day D (the long-form's publish
    date) and 01:30 UTC on D+1, in that order (round 3 §4). With the default
    16:45 long-form slot these ARE the slots shorts_slots_after_long already gives;
    pinning them means a changed `longform_slot_utc` cannot move the pilot.

    None when the first slot is not safely in the future (publishAt needs ~20 min)
    or the input is unreadable: the caller then uses the normal grid and records
    the pair as off-slot. Never raises."""
    try:
        base = dt.datetime.strptime(long_publish_rfc3339, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=dt.timezone.utc)
        slots = [dt.datetime.combine(base.date() + dt.timedelta(days=d), dt.time(h, m),
                                     dt.timezone.utc) for (d, h, m) in PILOT_B_SLOTS]
        now = now or dt.datetime.now(dt.timezone.utc)
        if slots[0] <= now + dt.timedelta(minutes=20):
            return None
        validate_distribution(slots)
        return [t.strftime("%Y-%m-%dT%H:%M:%SZ") for t in slots]
    except Exception:
        return None


def slot_label(rfc3339) -> str | None:
    """"HH:MM" (UTC) of a publishAt string — the ledger's `slot`. None if unreadable."""
    s = str(rfc3339 or "")
    return s[11:16] if len(s) >= 16 and s[13] == ":" else None


def shorts_slots_after_long(n: int, long_publish_rfc3339: str) -> list[str]:
    """Shorts drop schedule: the first Short lands ~2h after the long-form publish
    (routing traffic during its early-signal window), the rest fall on the daily
    grid with the 4h minimum preserved."""
    base = dt.datetime.strptime(long_publish_rfc3339, "%Y-%m-%dT%H:%M:%SZ").replace(
        tzinfo=dt.timezone.utc)
    first = base + dt.timedelta(hours=2)
    if n <= 1:
        return [first.strftime("%Y-%m-%dT%H:%M:%SZ")]
    # next_slots adds a 20-min future buffer internally; this offset guarantees
    # every grid slot lands >= MIN_GAP_HOURS after the first Short
    rest = next_slots(n - 1, after=first + dt.timedelta(hours=MIN_GAP_HOURS, minutes=-20))
    slots = [first] + [dt.datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc)
                       for s in rest]
    validate_distribution(slots)
    return [t.strftime("%Y-%m-%dT%H:%M:%SZ") for t in slots]

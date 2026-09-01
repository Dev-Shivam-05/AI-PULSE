"""
Union-merge pipeline state with origin/main so the CI state-save can never lose
a race again.

The old approach (commit, then pull --rebase on conflict) breaks precisely when
it matters: two runs appending to the same JSON files produce rebase conflicts
git cannot resolve, the push retries exhaust, and the day's topic history is
lost — which later causes duplicate published videos.

This module knows the merge semantics of every state file:
  * used_topics.json / used_urls.json  -> ordered union of two lists
  * state/failed_topics.json           -> per-key max of two count dicts
  * state/l2_usage.json                -> per-kind ordered union of used names
  * state/stock_ledger.json            -> ordered line/entry union
  * output/production_log.json         -> union of entries by (timestamp, title)
  * state/runs.jsonl / analytics.jsonl -> ordered line union
  * state/tools_index.json             -> union by page name, later entry wins

Usage (from the repo root, typically in CI after `git checkout -B main origin/main`):
    python -m factverse.state_merge <incoming_dir>
where <incoming_dir> holds this run's versions of the files (saved aside before
the checkout). Files missing on either side are handled gracefully.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from factverse import config as fv

FILES = (
    "used_topics.json",
    "used_urls.json",
    "state/failed_topics.json",
    "output/production_log.json",
    "state/runs.jsonl",
    "state/analytics.jsonl",
    # Both are TRACKED and written by the run. A tracked state file that is not
    # stashed AND merged is reverted by `git checkout -B main origin/main` on
    # every CI run: l2_usage would let the same human clip be injected into every
    # video, and stock_ledger would forget the 30-day stock repeat guard.
    "state/l2_usage.json",
    "state/stock_ledger.json",
    # v3-F.1: the site catalog. Every docs/*.html file is DERIVED from this, so
    # losing it to `checkout -B main origin/main` would silently empty the site
    # index on the next rebuild. Basenames must stay unique — main() reads the
    # incoming copy by basename, not by path.
    "state/tools_index.json",
    # v3-F.2/F.3: the video URLs already announced, one list per surface. Lists of
    # strings, so the generic ordered union below is already the right semantics.
    # Losing either to `checkout -B main origin/main` would re-post the same video
    # every day; sharing ONE list between the surfaces would mark a video done for
    # X because Telegram took it, and then X would never post it at all.
    "state/notified.json",
    "state/notified_x.json",
)


def _read_text(p: Path) -> str | None:
    try:
        return p.read_text(encoding="utf-8") if p.exists() else None
    except OSError:
        return None


def _merge_list(a, b) -> list:
    # A side that is not a list (a corrupt/hand-edited body: a dict, a scalar) used
    # to raise TypeError here — inside the ONE CI step with no `|| true`, where
    # `bash -e` then kills the state-save and loses ALL state, not just this file.
    # _merge_index got this guard in v3-F.1; the generic fallback never had it.
    a = a if isinstance(a, list) else []
    b = b if isinstance(b, list) else []
    seen, out = set(), []
    for item in a + b:
        key = json.dumps(item, ensure_ascii=False, sort_keys=True)
        if key not in seen:
            seen.add(key)
            out.append(item)
    return out


def _merge_counts(a, b) -> dict:
    out = dict(a or {})
    for k, v in (b or {}).items():
        try:
            out[k] = max(int(out.get(k, 0)), int(v))
        except (TypeError, ValueError):
            out.setdefault(k, v)
    return out


def _merge_log(a, b) -> list:
    seen, out = set(), []
    for e in (a or []) + (b or []):
        key = (e.get("timestamp", ""), e.get("title", "")) if isinstance(e, dict) else str(e)
        if key not in seen:
            seen.add(key)
            out.append(e)
    out.sort(key=lambda e: e.get("timestamp", "") if isinstance(e, dict) else "")
    return out[-400:]


def _merge_used(a, b) -> dict:
    """state/l2_usage.json: kind -> list of clip names. Per-key ordered union.

    A name that appears on either side is consumed: an L2 clip is usable at most
    once, so the union must never lose one.
    """
    out = {k: list(v) for k, v in (a or {}).items() if isinstance(v, list)}
    for k, v in (b or {}).items():
        if not isinstance(v, list):
            continue
        cur = out.setdefault(k, [])
        for name in v:
            if name not in cur:
                cur.append(name)
    return out


def _merge_seen(a, b) -> dict:
    """state/stock_ledger.json: clip id -> ISO timestamp. Union, latest wins.

    The ledger answers "did we use this stock clip in the last 30 days", so a
    later sighting is the one that matters and no id may be dropped.
    """
    out = dict(a or {})
    for k, v in (b or {}).items():
        if k not in out or str(v) > str(out[k]):
            out[k] = v
    return out


def _merge_index(a, b) -> list:
    """state/tools_index.json: union keyed by `page`, later entry wins.

    The generic list union dedups on exact equality, so a retry that re-uploads
    the same tool with a different video_url would print that tool TWICE on the
    index. `page` is the identity (one page per tool video); between two rows
    with that key the later date wins, and on an equal date the side that has a
    video_url does (a page written before the upload carries none).
    """
    out: dict[str, dict] = {}
    order: list[str] = []
    # `list(a or [])` raises TypeError on a scalar, and merge_file's caller in CI has
    # no `|| true` — under `bash -e` that would abort the whole state-save step.
    for e in ((a if isinstance(a, list) else []) + (b if isinstance(b, list) else [])):
        if not isinstance(e, dict) or not e.get("page"):
            continue
        key = str(e["page"])
        cur = out.get(key)
        if key not in out:
            order.append(key)
        if cur is None or (str(e.get("date", "")), bool(e.get("video_url"))) >= (
                str(cur.get("date", "")), bool(cur.get("video_url"))):
            out[key] = e
    return [out[k] for k in order]


def _merge_jsonl(a: str | None, b: str | None) -> str:
    seen, out = set(), []
    for text in (a, b):
        for line in (text or "").splitlines():
            line = line.strip()
            if line and line not in seen:
                seen.add(line)
                out.append(line)
    return "\n".join(out) + ("\n" if out else "")


def merge_file(rel: str, ours_text: str | None, theirs_text: str | None) -> str | None:
    """Return merged file content (text), or None if neither side has it."""
    if ours_text is None and theirs_text is None:
        return None
    if rel.endswith(".jsonl"):
        return _merge_jsonl(theirs_text, ours_text)
    try:
        ours = json.loads(ours_text) if ours_text else None
        theirs = json.loads(theirs_text) if theirs_text else None
    except json.JSONDecodeError:
        # one side corrupt: keep whichever parses; ours wins ties
        for t in (ours_text, theirs_text):
            try:
                json.loads(t or "")
                return t
            except json.JSONDecodeError:
                continue
        return ours_text or theirs_text
    if rel == "state/failed_topics.json":
        merged = _merge_counts(theirs, ours)
    elif rel == "output/production_log.json":
        merged = _merge_log(theirs, ours)
    elif rel == "state/l2_usage.json":
        merged = _merge_used(theirs, ours)
    elif rel == "state/stock_ledger.json":
        merged = _merge_seen(theirs, ours)
    elif rel == "state/tools_index.json":
        merged = _merge_index(theirs, ours)
    else:
        merged = _merge_list(theirs, ours)
    return json.dumps(merged, ensure_ascii=False, indent=(2 if "production_log" in rel else None))


def main(incoming_dir: str) -> int:
    inc = Path(incoming_dir)
    base = fv.BASE
    changed = 0
    for rel in FILES:
        ours = _read_text(inc / Path(rel).name)          # this run's version (saved aside)
        theirs = _read_text(base / rel)                   # origin/main's version (checked out)
        merged = merge_file(rel, ours, theirs)
        if merged is None:
            continue
        dest = base / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        if _read_text(dest) != merged:
            dest.write_text(merged, encoding="utf-8")
            changed += 1
    print(f"state-merge: {changed} file(s) updated")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "state_incoming"))

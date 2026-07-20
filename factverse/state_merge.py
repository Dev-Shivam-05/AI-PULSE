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
  * output/production_log.json         -> union of entries by (timestamp, title)
  * state/runs.jsonl / analytics.jsonl -> ordered line union

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
)


def _read_text(p: Path) -> str | None:
    try:
        return p.read_text(encoding="utf-8") if p.exists() else None
    except OSError:
        return None


def _merge_list(a, b) -> list:
    seen, out = set(), []
    for item in (a or []) + (b or []):
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

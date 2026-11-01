"""
v3-L.2 ToolDojo Radar Live — the data and narration half (docs/spec/ai-pulse-v3l2.md).

Everything here is pure or fail-soft. A fetch that fails returns None and the caller
keeps its last good data, because the stream is unattended: a raise would end a live
broadcast with nobody there to restart it. Rendering and streaming live in
scripts/radar_live.py; this module never touches ffmpeg or a browser.
"""
from __future__ import annotations

import json
import math
import re
import time
from datetime import datetime, timedelta, timezone

import requests

from factverse import config as fv
from factverse import gates
from factverse import llm

UA = {"User-Agent": "python:tooldojo.radar:v1.0 (live board)"}
TIMEOUT = 20

# spec rows, by number
GITHUB_DAYS, GITHUB_MIN_STARS, GITHUB_ITEMS = 14, 120, 50       # row 6
HF_ITEMS = 50                                                    # row 6
# v3-L.6 row 1: the 50+50 fetch was our own cap (measured 2026-11-01: 160 repos matched the
# old query, 1,083 at 30 days / >50 stars). The search API returns at most 1,000 results
# per query, so the window is split by creation date and each part is its own query.
GITHUB_WINDOWS = ((0, 7), (7, 14), (14, 30))                     # L6 row 1 (days ago)
GITHUB_WIDE_STARS, GITHUB_WIDE_ITEMS = 50, 100                   # L6 row 1
HF_MODEL_ITEMS, HF_SPACE_ITEMS = 100, 100                        # L6 row 1
BOARD_SIZE, BOARD_EVERY, BOARD_SECONDS = 8, 4, 20                # row 10
SECTION_SIZE, BIG_SECTION_SIZE = 4, 7                            # L6 row 3: per source
STALE_MINUTES = 30                                               # L6 row 4
TAIL_SECONDS = 3                                                 # row 11
COOLDOWN_DAYS = 3                                                # row 12
NARRATION_WORDS = (100, 160)                                     # v3l3 row 3 (asked of the model)
GATE_WORDS = (70, 200)                                           # v3l3 row 3 (accepted)
NARRATION_CHARS = 1400                                           # v3l3 row 3 (model text cap)
NARRATION_MODEL = "gemini-3.5-flash-lite"                        # v3l3 row 1 (asked first)
PHRASE_WORDS = 6                                                 # row 18
MIN_FRESH = 10                                                   # row 5
README_CHARS = 6000          # grounding handed to the model; READMEs run long
FETCH_BYTES = 200_000        # a README larger than this is cut, never streamed whole
FETCH_SECONDS = 15           # wall clock per README download


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ------------------------------------------------------------------ parsing (pure)
def _int(v) -> int:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return 0
    return int(f) if math.isfinite(f) and f > 0 else 0


def _text(v, limit: int = 400) -> str:
    """Model- and API-supplied text: one line, no control characters, bounded."""
    s = re.sub(r"[\x00-\x1f\x7f]+", " ", str(v or "")).strip()
    s = re.sub(r"\s+", " ", s)
    return s[:limit]


def _days_since(iso: str, now: datetime) -> int | None:
    try:
        t = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    except ValueError:
        return None
    if t.tzinfo is None:
        t = t.replace(tzinfo=timezone.utc)
    return max(0, (now - t).days)


def tool_from_github(it: dict, now: datetime) -> dict | None:
    if not isinstance(it, dict):
        return None
    full = _text(it.get("full_name"), 140)
    if "/" not in full:
        return None
    owner, name = full.split("/", 1)
    lic = it.get("license") if isinstance(it.get("license"), dict) else {}
    age = _days_since(it.get("created_at", ""), now)
    stars = _int(it.get("stargazers_count"))
    return {
        "id": f"gh:{full.lower()}", "kind": "github", "name": name, "owner": owner,
        "url": f"https://github.com/{full}", "desc": _text(it.get("description")),
        "stars": stars, "language": _text(it.get("language"), 40),
        "license": _text((lic or {}).get("spdx_id"), 40).replace("NOASSERTION", ""),
        "age_days": age,
        # stars per day since creation: the key-free stand-in for "trending"
        "velocity": round(stars / max(1, age or 1)) if age is not None else 0,
        "readme": f"https://raw.githubusercontent.com/{full}/HEAD/README.md",
    }


def tool_from_hf(m: dict, now: datetime) -> dict | None:
    if not isinstance(m, dict):
        return None
    mid = _text(m.get("modelId") or m.get("id"), 140)
    if "/" not in mid:
        return None
    owner, name = mid.split("/", 1)
    tag = _text(m.get("pipeline_tag"), 40).replace("-", " ")
    return {
        "id": f"hf:{mid.lower()}", "kind": "hf", "name": name, "owner": owner,
        "url": f"https://huggingface.co/{mid}",
        "desc": f"a trending {tag} model on Hugging Face" if tag else "a trending model on Hugging Face",
        "likes": _int(m.get("likes")), "downloads": _int(m.get("downloads")),
        "trending": _int(m.get("trendingScore")), "task": tag,
        "age_days": _days_since(m.get("createdAt", ""), now),
        "readme": f"https://huggingface.co/{mid}/raw/main/README.md",
    }


def tool_from_hf_space(s: dict, now: datetime) -> dict | None:
    """A Hugging Face Space: a runnable app, the closest HF has to a 'tool'. Its
    short_description is written by the Space's author, so unlike our model label it may
    be quoted as the tool's own words."""
    if not isinstance(s, dict):
        return None
    sid = _text(s.get("id"), 140)
    if "/" not in sid:
        return None
    owner, name = sid.split("/", 1)
    card = s.get("cardData") if isinstance(s.get("cardData"), dict) else {}
    title = _text(card.get("title"), 90)
    return {
        "id": f"hfs:{sid.lower()}", "kind": "space", "name": title or name, "owner": owner,
        "url": f"https://huggingface.co/spaces/{sid}",
        "desc": _text(card.get("short_description")) or (f"{title} on Hugging Face Spaces"
                                                         if title else ""),
        "likes": _int(s.get("likes")), "trending": _int(s.get("trendingScore")),
        "sdk": _text(s.get("sdk"), 20), "age_days": _days_since(s.get("createdAt", ""), now),
        "readme": f"https://huggingface.co/spaces/{sid}/raw/main/README.md",
    }


def is_hf(t: dict) -> bool:
    return t.get("kind") in ("hf", "space")


def kind_label(t: dict) -> str:
    return {"github": "GITHUB", "hf": "HF MODEL", "space": "HF SPACE"}.get(t.get("kind"), "")


def github_windows(now: datetime) -> list[str]:
    """L6 row 1: one `created:` range per window, newest first."""
    out = []
    for lo, hi in GITHUB_WINDOWS:
        a = (now - timedelta(days=hi)).strftime("%Y-%m-%d")
        b = (now - timedelta(days=lo)).strftime("%Y-%m-%d")
        out.append(f"{a}..{b}")
    return out


# ------------------------------------------------------------------ fetching (fail-soft)
def _get(url: str, **kw):
    return requests.get(url, headers={**UA, **kw.pop("headers", {})}, timeout=TIMEOUT, **kw)


def fetch_github(now: datetime | None = None) -> list | None:
    now = now or _now()
    try:
        since = (now - timedelta(days=GITHUB_DAYS)).strftime("%Y-%m-%d")
        r = _get("https://api.github.com/search/repositories",
                 params={"q": f"ai OR llm OR agent OR diffusion created:>{since} "
                              f"stars:>{GITHUB_MIN_STARS}",
                         "sort": "stars", "order": "desc", "per_page": GITHUB_ITEMS},
                 headers={"Accept": "application/vnd.github+json"})
        if r.status_code != 200:
            return None
        items = r.json().get("items")
        return [t for t in (tool_from_github(i, now) for i in (items or [])) if t]
    except Exception:  # noqa: BLE001 — fail soft, the caller keeps its last data
        return None


def fetch_hf(now: datetime | None = None) -> list | None:
    now = now or _now()
    try:
        r = _get("https://huggingface.co/api/models",
                 params={"sort": "trendingScore", "direction": "-1", "limit": HF_ITEMS})
        if r.status_code != 200:
            return None
        data = r.json()
        if not isinstance(data, list):
            return None
        return [t for t in (tool_from_hf(m, now) for m in data) if t]
    except Exception:  # noqa: BLE001
        return None


def _github_page(created: str, now: datetime) -> list | None:
    try:
        r = _get("https://api.github.com/search/repositories",
                 params={"q": f"ai OR llm OR agent OR diffusion created:{created} "
                              f"stars:>{GITHUB_WIDE_STARS}",
                         "sort": "stars", "order": "desc", "per_page": GITHUB_WIDE_ITEMS},
                 headers={"Accept": "application/vnd.github+json"})
        if r.status_code != 200:
            return None
        return [t for t in (tool_from_github(i, now) for i in (r.json().get("items") or [])) if t]
    except Exception:  # noqa: BLE001
        return None


def fetch_github_wide(now: datetime | None = None) -> list | None:
    """L6 row 1: every created-date window, de-duplicated by id. A window that fails is
    skipped; None only when every window failed (the caller then keeps its last data)."""
    now = now or _now()
    seen, any_ok = {}, False
    for created in github_windows(now):
        page = _github_page(created, now)
        if page is None:
            continue
        any_ok = True
        for t in page:
            seen.setdefault(t["id"], t)
    return list(seen.values()) if any_ok else None


def fetch_hf_wide(now: datetime | None = None) -> list | None:
    """L6 row 1: trending models AND trending Spaces. None only when both failed."""
    now = now or _now()
    out, any_ok = [], False
    for path, limit, make, extra in (
            ("models", HF_MODEL_ITEMS, tool_from_hf, {}),
            ("spaces", HF_SPACE_ITEMS, tool_from_hf_space,
             {"expand[]": ["cardData", "likes", "trendingScore", "createdAt", "sdk"]})):
        try:
            r = _get(f"https://huggingface.co/api/{path}",
                     params={"sort": "trendingScore", "direction": "-1", "limit": limit,
                             **extra})
            data = r.json() if r.status_code == 200 else None
        except Exception:  # noqa: BLE001
            data = None
        if not isinstance(data, list):
            continue
        any_ok = True
        out += [t for t in (make(m, now) for m in data) if t]
    return out if any_ok else None


def fetch_readme(tool: dict) -> str:
    """The tool's README, capped in bytes AND chars. '' on any failure."""
    url = str(tool.get("readme") or "")
    if not url.startswith(("https://raw.githubusercontent.com/", "https://huggingface.co/")):
        return ""
    try:
        # requests' timeout bounds the gap between reads, not the download: a
        # slow-drip server would hold a live segment forever (CLAUDE.md trap)
        deadline = time.monotonic() + FETCH_SECONDS
        with requests.get(url, headers=UA, timeout=TIMEOUT, stream=True) as r:
            if r.status_code != 200:
                return ""
            buf = b""
            for chunk in r.iter_content(16384):
                buf += chunk
                if len(buf) >= FETCH_BYTES or time.monotonic() > deadline:
                    break
        return buf.decode("utf-8", "replace")[:README_CHARS]
    except Exception:  # noqa: BLE001
        return ""


# ------------------------------------------------------------------ pool (pure)
def screen(tools: list) -> tuple[list, list]:
    """(kept, [(tool, term)]) through the tool lane's own suitability screen."""
    kept, dropped = [], []
    for t in tools:
        blocked, term = gates.tool_unsuitable(f"{t['owner']}/{t['name']}", t.get("desc", ""))
        (dropped.append((t, term)) if blocked else kept.append(t))
    return kept, dropped


def rank(tools: list) -> list:
    """Board order (row 9): GitHub by stars/day, HF by trending score, interleaved."""
    gh = sorted((t for t in tools if t["kind"] == "github"),
                key=lambda t: (-t.get("velocity", 0), t["id"]))
    hf = sorted((t for t in tools if is_hf(t)),
                key=lambda t: (-t.get("trending", 0), t["id"]))
    out = []
    for i in range(max(len(gh), len(hf))):
        out += [x[i] for x in (gh, hf) if i < len(x)]
    return out


def headline_number(t: dict) -> int:
    return t.get("stars", 0) if t["kind"] == "github" else t.get("likes", 0)


def update_baseline(baseline: dict, tools: list) -> dict:
    """First number seen this session per tool — 'since this stream started'."""
    for t in tools:
        baseline.setdefault(t["id"], headline_number(t))
    return baseline


def board_rows(tools: list, baseline: dict, n: int = BOARD_SIZE,
               include: str | None = None) -> list:
    """Top n by board order. `include` (the spotlighted id) takes the last slot when
    it ranks below n, so the card's "#9 on the radar" is never missing from the board."""
    ranked = list(enumerate(rank(tools), start=1))
    picked = ranked[:n]
    if include and include not in {t["id"] for _, t in picked}:
        extra = [x for x in ranked if x[1]["id"] == include]
        if extra:
            picked = picked[:n - 1] + extra
    rows = []
    for i, t in picked:
        num = headline_number(t)
        rows.append({"rank": i, "id": t["id"], "kind": t["kind"],
                     "name": t["name"], "owner": t["owner"], "number": num,
                     "unit": "stars" if t["kind"] == "github" else "likes",
                     "gain": max(0, num - baseline.get(t["id"], num))})
    return rows


def board_sections(tools: list, baseline: dict, n: int = SECTION_SIZE,
                   include: str | None = None) -> dict:
    """L6 row 3: GitHub and Hugging Face are ranked SEPARATELY, each by its own measure,
    because stars/day and HF's trendingScore are not one scale (the L.2 board interleaved
    them under one "momentum" rank). Rank numbers are within the section. The spotlighted
    tool takes its section's last slot when it ranks below n."""
    gh = sorted((t for t in tools if t["kind"] == "github"),
                key=lambda t: (-t.get("velocity", 0), t["id"]))
    hf = sorted((t for t in tools if is_hf(t)), key=lambda t: (-t.get("trending", 0), t["id"]))
    out = {}
    for key, ordered in (("github", gh), ("hf", hf)):
        ranked = list(enumerate(ordered, start=1))
        picked = ranked[:n] if n else ranked          # n=0: the whole section
        if include and include not in {t["id"] for _, t in picked}:
            extra = [x for x in ranked if x[1]["id"] == include]
            if extra and picked:
                picked = picked[:n - 1] + extra
        rows = []
        for i, t in picked:
            num = headline_number(t)
            rows.append({"rank": i, "id": t["id"], "kind": t["kind"], "name": t["name"],
                         "owner": t["owner"], "number": num,
                         "unit": "stars" if t["kind"] == "github" else "likes",
                         "measure": (f"{_n(t.get('velocity', 0))}/day" if t["kind"] == "github"
                                     else f"trend {_n(t.get('trending', 0))}"),
                         "per_day": t.get("velocity", 0) if t["kind"] == "github" else 0,
                         "gain": max(0, num - baseline.get(t["id"], num))})
        out[key] = rows
    return out


def section_rank(tools: list, tool: dict) -> int:
    """The spotlighted tool's rank within its OWN source (L6 row 3)."""
    rows = board_sections(tools, {}, n=0)["github" if tool["kind"] == "github" else "hf"]
    return next((r["rank"] for r in rows if r["id"] == tool["id"]), 0)


def status_label(t: dict, history: dict | None) -> str:
    """L6 row 4: SPOTTED = never spotlighted on any earlier day; BACK = spotlighted before and
    outside the cooldown (its card then states the change since last time)."""
    return "BACK ON RADAR" if (history or {}).get(t["id"]) else "SPOTTED THIS SESSION"


def is_stale(last_ok: datetime | None, now: datetime, minutes: int = STALE_MINUTES) -> bool:
    return last_ok is None or (now - last_ok) > timedelta(minutes=minutes)


def fresh(tools: list, history: dict, spotlighted: set, now: datetime) -> list:
    """Ranked tools not yet spotlighted this session and outside the cooldown."""
    cut = now - timedelta(days=COOLDOWN_DAYS)
    out = []
    for t in rank(tools):
        if t["id"] in spotlighted:
            continue
        seen = (history.get(t["id"]) or {}).get("at", "")
        try:
            last = datetime.fromisoformat(seen) if seen else None
        except ValueError:
            last = None
        if last and last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        if last and last > cut:
            continue
        out.append(t)
    return out


def remember(history: dict, tool: dict, now: datetime) -> dict:
    history[tool["id"]] = {"at": now.isoformat(timespec="seconds"),
                           "number": headline_number(tool)}
    return history


# ------------------------------------------------------------------ narration
def _n(v: int) -> str:
    return f"{v:,}"


def _days(n: int) -> str:
    return "1 day" if n == 1 else f"{n} days"


def facts(t: dict, history: dict | None = None) -> list[str]:
    """Plain fact lines: shown on the card, spoken by the template, and the ONLY
    numbers the model may use (row 14)."""
    lines = []
    if t["kind"] == "github":
        lines.append(f"{_n(t.get('stars', 0))} stars on GitHub")
        if t.get("age_days") is not None:
            lines.append(f"created {_days(t['age_days'])} ago")
            lines.append(f"about {_n(t.get('velocity', 0))} stars a day since then")
        if t.get("language"):
            lines.append(f"written mostly in {t['language']}")
        if t.get("license"):
            lines.append(f"licensed {t['license']}")
    else:
        lines.append(f"{_n(t.get('likes', 0))} likes on Hugging Face")
        if t.get("downloads"):
            # the list API omits the field for new models; 0 would be a false fact
            lines.append(f"{_n(t['downloads'])} downloads")
        if t.get("age_days") is not None:
            lines.append(f"published {_days(t['age_days'])} ago")
        if t["kind"] == "space":
            lines.append(f"a {t['sdk']} app on Hugging Face Spaces" if t.get("sdk")
                         else "an app on Hugging Face Spaces")
    prev = (history or {}).get(t["id"])
    if prev and isinstance(prev.get("number"), int):
        unit = "stars" if t["kind"] == "github" else "likes"
        lines.append(f"up {_n(max(0, headline_number(t) - prev['number']))} {unit} "
                     f"since the radar last covered it")
    return lines


def chips(t: dict, history: dict | None = None) -> list[str]:
    """The same facts, short enough for the card (row 17). Sentence-length facts
    needed three rows on a two-row card - measured on the first local session."""
    out = []
    if t["kind"] == "github":
        out.append(f"\u2605 {_n(t.get('stars', 0))}")
        if t.get("age_days") is not None:
            out.append(f"{_days(t['age_days'])} old")
            out.append(f"~{_n(t.get('velocity', 0))} \u2605/day")
        if t.get("language"):
            out.append(t["language"])
        if t.get("license"):
            out.append(t["license"])
    else:
        out.append(f"\u2665 {_n(t.get('likes', 0))}")
        if t.get("downloads"):
            out.append(f"{_n(t['downloads'])} downloads")
        if t.get("age_days") is not None:
            out.append(f"{_days(t['age_days'])} old")
        if t.get("task"):
            out.append(t["task"])
        if t.get("sdk"):
            out.append(f"{t['sdk']} app")
    prev = (history or {}).get(t["id"])
    if prev and isinstance(prev.get("number"), int):
        out.append(f"+{_n(max(0, headline_number(t) - prev['number']))} since last time")
    return out


READABLE_SHARE = 0.7          # row 15a


def readable(text: str) -> bool:
    """Row 15a: at least 70% of the letters are Latin script. The voice is English
    and the brand font has no CJK glyphs, so a Chinese or Japanese description is
    never read aloud by the template."""
    letters = [c for c in str(text or "") if c.isalpha()]
    if not letters:
        return False
    return sum(c.isascii() for c in letters) / len(letters) >= READABLE_SHARE


def spoken_description(text: str) -> str:
    """The part of a description the English voice should read. Bilingual repos write
    "<Japanese> / <English>" (seen on stream: yomiyasu), which passes the 70% rule as
    a whole, so each " / " or " | " part is judged on its own and only readable parts
    are spoken. The card still shows the full description."""
    parts = [p.strip() for p in re.split(r"\s[/|]\s", str(text or "")) if p.strip()]
    keep = [p for p in parts if readable(p)]
    return " / ".join(keep)


def spotlightable(t: dict, have_llm: bool) -> bool:
    """A template spotlight needs a readable description; a written one (LLM, gated)
    is grounded in the README instead, so it may take any tool."""
    return have_llm or (t["kind"] == "hf") or bool(spoken_description(t.get("desc", "")))


def template_narration(t: dict, rank_no: int, history: dict | None = None) -> str:
    back = "Back on the radar" if (history or {}).get(t["id"]) else f"Number {rank_no} on the radar"
    fl = facts(t, history)
    head = f"{back}: {t['name']}, from {t['owner']}. {'; '.join(fl)}."
    if t["kind"] == "hf":
        task = t.get("task")
        return f"{head} It is a trending {task} model." if task else head
    desc = spoken_description(t.get("desc", "")) or "no description yet"
    return f"{head} In its own words: {desc.rstrip('.')}."


_NUM = re.compile(r"\d[\d,]*(?:\.\d+)?")


def _numbers(text: str) -> set:
    return {m.group(0).replace(",", "").rstrip(".") for m in _NUM.finditer(text or "")}


def narration_ok(text: str, grounding: str) -> bool:
    """Row 14: numbers subset of grounding, no hype, GATE_WORDS long (v3l3 row 3)."""
    words = len((text or "").split())
    if not GATE_WORDS[0] <= words <= GATE_WORDS[1]:
        return False
    if gates.hype_terms(text):
        return False
    return _numbers(text) <= _numbers(grounding)


USE_IT_WORDS = (2, 9)          # L6 row 5: the card's benefit line


def _prompt(t: dict, fact_lines: list, readme: str) -> str:
    # L6 row 5: benefit first. A viewer who joins mid-stream must learn what the tool is FOR
    # before its numbers (debate 2026-11-01, R03); the limitation comes only from the README.
    return f"""You are the narrator of a live, automated board of trending AI tools.
Explain this tool to a developer in {NARRATION_WORDS[0]}-{NARRATION_WORDS[1]} words, in this order:
1. the problem it solves, in one sentence;
2. what it does;
3. one concrete piece of evidence from FACTS or README (a number, a supported platform, a requirement);
4. one limitation or requirement the README states (hardware, platform, licence, maturity). If the
   README states none, say that its limitations are not documented yet. Never invent one;
5. who should try it.
Use ONLY the facts and README below. Every number you say must appear in FACTS or README. No hype
words, no superlatives, no "game-changer". Say the name as written. Do not greet, do not say
"subscribe". Also write "use_it_for": {USE_IT_WORDS[0]}-{USE_IT_WORDS[1]} plain words that start
with a verb and say what a viewer could use it for (example: "turn scanned PDFs into searchable text").
Return ONLY JSON {{"use_it_for": "...", "narration": "..."}}

NAME: {t['owner']}/{t['name']}
FACTS:
{chr(10).join('- ' + f for f in fact_lines)}
README (may be cut):
{readme}"""


def use_it_ok(text: str, grounding: str) -> bool:
    words = len((text or "").split())
    return (USE_IT_WORDS[0] <= words <= USE_IT_WORDS[1] and readable(text)
            and not gates.hype_terms(text) and _numbers(text) <= _numbers(grounding))


def llm_spotlight(t: dict, fact_lines: list, readme: str) -> dict | None:
    """{"narration", "use_it_for"} or None (no key, model failure, or gate refusal). A
    benefit line that fails its own gate is dropped ("") without losing the narration."""
    if not fv.GEMINI_KEY or len(readme) < 200:
        return None
    try:
        # v3l3 row 1: the shared chain opens on models that stalled the 2026-10-05 sessions
        raw = llm.generate_json(_prompt(t, fact_lines, readme), model=NARRATION_MODEL,
                                temperature=0.4, max_tokens=2048)
        raw = raw if isinstance(raw, dict) else {}
        text = _text(raw.get("narration"), NARRATION_CHARS)
        use = _text(raw.get("use_it_for"), 90).rstrip(".")
    except Exception:  # noqa: BLE001
        return None
    grounding = " ".join(fact_lines) + " " + readme
    if not narration_ok(text, grounding):
        return None
    return {"narration": text, "use_it_for": use if use_it_ok(use, grounding) else ""}


def llm_narration(t: dict, fact_lines: list, readme: str) -> str | None:
    """The written explanation, or None (no key, model failure, or gate refusal)."""
    got = llm_spotlight(t, fact_lines, readme)
    return got["narration"] if got else None


def board_narration(rows: list, as_of: datetime) -> str:
    if not rows:
        return ""
    top = rows[0]
    movers = sorted((r for r in rows if r["gain"] > 0), key=lambda r: -r["gain"])
    s = (f"The board at {as_of:%H:%M} UTC. At the top: {top['name']}, "
         f"with {_n(top['number'])} {top['unit']}.")
    if movers:
        m = movers[0]
        s += f" Biggest climber since this stream started: {m['name']}, up {_n(m['gain'])} {m['unit']}."
    return s


def sections_narration(sections: dict, as_of: datetime) -> str:
    """L6 row 3: each source is read with its own measure; nothing ranks across them."""
    gh, hf = sections.get("github") or [], sections.get("hf") or []
    if not gh and not hf:
        return ""
    s = f"The board at {as_of:%H:%M} UTC."
    if gh:
        s += (f" On GitHub, the fastest riser is {gh[0]['name']}, at about "
              f"{_n(gh[0].get('per_day', 0))} stars a day since it was created.")
    if hf:
        s += f" On Hugging Face, {hf[0]['name']} leads the trending list."
    movers = sorted((r for r in gh + hf if r["gain"] > 0), key=lambda r: -r["gain"])
    if movers:
        m = movers[0]
        s += f" Biggest climber since this stream started: {m['name']}, up {_n(m['gain'])} {m['unit']}."
    return s


def end_narration(spotlights: int, reason: str, daily_at: str) -> str:
    """L6 row 9: the true stop reason. `daily_at` only when the daily schedule is real."""
    why = ("Every fresh tool on the radar has now been covered." if reason == "exhausted"
           else "That is the end of today's session.")
    back = f" ToolDojo Radar is back every day at {daily_at}, India time." if daily_at else ""
    return f"{why} Today the radar covered {spotlights} tools.{back} Thanks for watching."


# ------------------------------------------------------------------ timing (pure)
def _bare(w: str) -> str:
    return re.sub(r"[^0-9a-z]", "", str(w).lower())


def punctuate(words: list, text: str) -> list:
    """edge-tts word timings drop punctuation, so captions ran across sentences
    ("ago In its own words a"). Re-attach each spoken word to its token in the
    narration text, in order; a word that does not match keeps its spoken form."""
    tokens = str(text or "").split()
    out, j = [], 0
    for w in words:
        target = _bare(w[2])
        k = j
        while k < len(tokens) and k < j + 4 and _bare(tokens[k]) != target:
            k += 1
        if target and k < len(tokens) and _bare(tokens[k]) == target:
            out.append((w[0], w[1], tokens[k]))
            j = k + 1
        else:
            out.append(tuple(w))
    return out


def phrases(words: list, max_words: int = PHRASE_WORDS) -> list:
    """[(start, end, text)] caption phrases from (start, end, word) timings; a
    sentence end also closes a phrase so a caption never straddles two sentences."""
    out, cur = [], []
    for w in words:
        cur.append(w)
        if len(cur) >= max_words or str(w[2]).endswith((".", "?", "!")):
            out.append((cur[0][0], cur[-1][1], " ".join(str(x[2]) for x in cur)))
            cur = []
    if cur:
        out.append((cur[0][0], cur[-1][1], " ".join(str(x[2]) for x in cur)))
    return out


def segment_seconds(audio_seconds: float, tail: float = TAIL_SECONDS) -> int:
    """Row 11: narration + tail, rounded UP to an even whole number (2 s GOPs)."""
    s = math.ceil(max(0.0, audio_seconds) + tail)
    return s + (s % 2)


def frame_times(length: int, phrase_list: list) -> list:
    """Row 18: every whole second and every phrase start, within [0, length)."""
    ts = {float(i) for i in range(int(length))}
    ts |= {round(float(p[0]), 3) for p in phrase_list if 0 <= p[0] < length}
    return sorted(ts)


def load_json(path, default):
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, type(default)) else default
    except Exception:  # noqa: BLE001
        return default

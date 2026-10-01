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
BOARD_SIZE, BOARD_EVERY, BOARD_SECONDS = 8, 4, 20                # row 10
TAIL_SECONDS = 3                                                 # row 11
COOLDOWN_DAYS = 3                                                # row 12
NARRATION_WORDS = (50, 90)                                       # row 13 (asked of the model)
GATE_WORDS = (30, 120)                                           # row 14 (accepted)
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
    hf = sorted((t for t in tools if t["kind"] == "hf"),
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


def spotlightable(t: dict, have_llm: bool) -> bool:
    """A template spotlight needs a readable description; a written one (LLM, gated)
    is grounded in the README instead, so it may take any tool."""
    return have_llm or (t["kind"] == "hf") or readable(t.get("desc", ""))


def template_narration(t: dict, rank_no: int, history: dict | None = None) -> str:
    back = "Back on the radar" if (history or {}).get(t["id"]) else f"Number {rank_no} on the radar"
    fl = facts(t, history)
    head = f"{back}: {t['name']}, from {t['owner']}. {'; '.join(fl)}."
    if t["kind"] == "hf":
        task = t.get("task")
        return f"{head} It is a trending {task} model." if task else head
    desc = t.get("desc") or "no description yet"
    return f"{head} In its own words: {desc}."


_NUM = re.compile(r"\d[\d,]*(?:\.\d+)?")


def _numbers(text: str) -> set:
    return {m.group(0).replace(",", "").rstrip(".") for m in _NUM.finditer(text or "")}


def narration_ok(text: str, grounding: str) -> bool:
    """Row 14: numbers subset of grounding, no hype, 30-120 words."""
    words = len((text or "").split())
    if not GATE_WORDS[0] <= words <= GATE_WORDS[1]:
        return False
    if gates.hype_terms(text):
        return False
    return _numbers(text) <= _numbers(grounding)


def _prompt(t: dict, fact_lines: list, readme: str) -> str:
    return f"""You are the narrator of a live, automated board of trending AI tools.
Explain this tool to a developer in {NARRATION_WORDS[0]}-{NARRATION_WORDS[1]} words: what it is,
who would use it, and one honest limitation or open question. Use ONLY the facts and README below.
Every number you say must appear in FACTS or README. No hype words, no superlatives, no
"game-changer". Say the name as written. Do not greet, do not say "subscribe".
Return ONLY JSON {{"narration": "..."}}

NAME: {t['owner']}/{t['name']}
FACTS:
{chr(10).join('- ' + f for f in fact_lines)}
README (may be cut):
{readme}"""


def llm_narration(t: dict, fact_lines: list, readme: str) -> str | None:
    """The written explanation, or None (no key, model failure, or gate refusal)."""
    if not fv.GEMINI_KEY or len(readme) < 200:
        return None
    try:
        raw = llm.generate_json(_prompt(t, fact_lines, readme), temperature=0.4, max_tokens=1024)
        text = _text((raw or {}).get("narration") if isinstance(raw, dict) else "", 900)
    except Exception:  # noqa: BLE001
        return None
    grounding = " ".join(fact_lines) + " " + readme
    return text if narration_ok(text, grounding) else None


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

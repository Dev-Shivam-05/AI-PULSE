"""v3-T.1 ToolDojo Live Trials: plan, run, score and record one live test episode.

spec docs/spec/ai-pulse-v3t1.md (review docs/debate/2026-11-04-tooldojo-live-stream-ideas).
One named tool is tested per episode in a 12-minute vertical live show. This module
is everything except the stream itself (scripts/trials_live.py):

  plan      pick the tool (hard gates first, then demand signals), the fixture set
            the channel has never used, the question;
  narrate   write ALL FOUR outcome branches of every result window BEFORE any run
            (LLM through factverse.llm when a key exists, else a deterministic
            template built from the episode's own fixtures);
  run       upload one committed fixture to the tool's OWN hosted Gradio demo in a
            clean headless browser (P.1's hosted-capture approach: no candidate code
            ever executes on our machine), record it, read the transcript back;
  score     deterministic checks per clip (key words heard, word errors within the
            allowance). A checker that breaks gives INCONCLUSIVE, never PASS;
  record    the episode record, the results sheet (docs/trials/*.html, published by
            the GitHub Contents API) and the pipeline hooks (live-day Short drop,
            no recap of an episode within 72 h).

Every network / browser seam fails soft and SAYS what happened (CLAUDE.md). Playwright
is imported inside the function that drives the browser (CI's test job has none).
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import html
import json
import math
import re
import shutil
import threading
import time
from pathlib import Path

from factverse import config as fv
from factverse import evidence

# ------------------------------------------------------------------ locked (review)
SHOW_MINUTES = 12                       # RESULT row 1: a 12-minute show
SLOT_WEEKDAY = 5                        # row 14: Saturday (date.weekday())
SLOT_UTC = "18:45"                      # row 14: 18:45-18:57 UTC
SLOT_END_UTC = "18:57"
DISCLOSURE = "Prepared narration • Tool execution and scores live"   # row 5, verbatim
SOURCE_LABEL = evidence.LABELS["hosted"]                                # "Hosted test"
BRANCHES = ("PASS", "PARTIAL_FAIL", "TIMEOUT", "INCONCLUSIVE")         # row 5 / R3 §2
BRANCH_LABEL = {"PASS": "PASS", "PARTIAL_FAIL": "PARTIAL / FAIL", "TIMEOUT": "TIMEOUT",
                "INCONCLUSIVE": "INCONCLUSIVE"}
# the shared evidence interface (docs/spec/ai-pulse-v3-growth.md) for each branch
EVIDENCE_STATUS = {"PASS": "PASSED_FIXED_TEST", "PARTIAL_FAIL": "FAILED_FIXED_TEST",
                   "TIMEOUT": "TIMED_OUT", "INCONCLUSIVE": "INCONCLUSIVE"}
RECAP_HOURS = 72                        # row 9: no recap upload in the archive's first 72 h
# row 12: the 14-day test (archive AVD, seconds)
AVD_BASELINE_S, AVD_STRETCH_S, AVD_STOP_S, STOP_MIN_VIEWS = 62, 120, 45, 25
HARDWARE_OK = ("cpu-basic", "cpu-upgrade")   # ₹0 to us and no ZeroGPU quota (K.1 finding)
FAMILY = "speech-to-text"               # the first task family (K.1: >= 3 CPU Spaces)

# ------------------------------------------------------------------ delegated (spec)
WER_MAX = 0.15          # D1: a clip passes "word errors" at <= floor(0.15 x reference words)
RUN_SECONDS = 60.0      # D2: one hosted run, page load to result (the declared test window)
RUN_LEAD_SECONDS = 120  # D3: a run starts at most this long before its window airs
VARIED_MAX_OVERLAP = 0.5  # D9: narration 4-gram overlap with any earlier episode
LATE_START_MAX = 300    # D11: a show that cannot connect within 5 min of 18:45 is skipped
REPO = "Dev-Shivam-05/AI-PULSE"         # the repo the results sheet and fixtures live in
REC_W, REC_H = evidence.REC_W, evidence.REC_H

FIXTURES = fv.ASSETS / "trials" / "fixtures" / FAMILY
MANIFEST = FIXTURES / "sets.json"
LOCAL_DIR = fv.OUTPUT / "trials"                     # gitignored: the node's own copy
HISTORY = LOCAL_DIR / "episodes.json"
STATE = fv.BASE / "state" / "trials_episodes.json"   # published copy CI reads (recap rule)
SHEETS_DIR = "docs/trials"

# The speech-to-text Spaces the K.1 supply check found (CPU, Gradio, audio in -> text
# out), plus how each one is pinned. `pins` are radio choices the test sets before it
# uploads (k2-fsa's default model is "Medical dictation English"). `repo` is where the
# demand signals (release date, star growth) are read. Feed candidates are added at
# plan time when the tool lane's feeds carry a speech-to-text tool with a Space.
SPACES = (
    {"space": "microsoft/vibevoice-asr-bitnet-demo", "tool": "VibeVoice-ASR-BitNet",
     "maker": "Microsoft", "model": "microsoft/VibeVoice-ASR-BitNet",
     "repo": "microsoft/VibeASR.cpp", "pins": [], "settings": []},
    {"space": "k2-fsa/automatic-speech-recognition", "tool": "sherpa-onnx",
     "maker": "k2-fsa (Next-gen Kaldi)", "model": "",
     "repo": "k2-fsa/sherpa-onnx", "pins": ["English"],
     "settings": ["Select a model", "Decoding method"]},
    {"space": "istupakov/onnx-asr", "tool": "onnx-asr", "maker": "istupakov",
     "model": "", "repo": "istupakov/onnx-asr", "pins": [], "settings": ["Model"]},
)


def _now() -> _dt.datetime:
    return _dt.datetime.now(_dt.timezone.utc)


def _log(msg: str) -> None:
    try:
        print(f"  [trials] {msg}".encode("ascii", "replace").decode("ascii"), flush=True)
    except Exception:  # noqa: BLE001
        pass


def slug(text: str, n: int = 40) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", str(text or "").lower()).strip("-")
    return s[:n].strip("-") or "tool"


# ================================================================== text checks (pure)
_ONES = ("zero one two three four five six seven eight nine ten eleven twelve thirteen "
         "fourteen fifteen sixteen seventeen eighteen nineteen").split()
_TENS = ("", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety")
_ORD = {"one": "first", "two": "second", "three": "third", "five": "fifth", "eight": "eighth",
        "nine": "ninth", "twelve": "twelfth"}


def number_words(n: int) -> list[str]:
    """0..999999 as English words, no "and" ("one hundred five"). PURE."""
    n = int(n)
    if n < 0 or n > 999_999:
        return [str(n)]
    if n < 20:
        return [_ONES[n]]
    if n < 100:
        return [_TENS[n // 10]] + ([_ONES[n % 10]] if n % 10 else [])
    if n < 1000:
        return [_ONES[n // 100], "hundred"] + (number_words(n % 100) if n % 100 else [])
    return number_words(n // 1000) + ["thousand"] + (number_words(n % 1000) if n % 1000 else [])


def _ordinal(words: list[str]) -> list[str]:
    last = words[-1]
    if last in _ORD:
        last = _ORD[last]
    elif last.endswith("y"):
        last = last[:-1] + "ieth"
    else:
        last = last + "th"
    return words[:-1] + [last]


def normalize(text: str) -> list[str]:
    """Words to compare: lower case, punctuation and apostrophes removed, digits read
    as words ("9:15" -> nine fifteen, "4" -> four, "4th" -> fourth, "2,450" -> two
    thousand four hundred fifty). PURE, never raises on odd input."""
    t = str(text or "").lower().replace("’", "'").replace("'", "")
    t = t.replace("%", " percent ").replace("&", " and ")

    def _time(m):
        h, mm = int(m.group(1)), int(m.group(2))
        out = number_words(h)
        if mm:
            out += (["oh"] if mm < 10 else []) + number_words(mm)
        return " " + " ".join(out) + " "

    t = re.sub(r"\b(\d{1,2}):(\d{2})\b", _time, t)
    t = re.sub(r"(?<=\d),(?=\d{3}\b)", "", t)
    t = re.sub(r"\b(\d+)(st|nd|rd|th)\b", lambda m: " " + " ".join(_ordinal(number_words(int(m.group(1))))) + " ", t)
    t = re.sub(r"\b\d+\b", lambda m: " " + " ".join(number_words(int(m.group(0)))) + " ", t)
    return re.findall(r"[a-z0-9]+", t)


def align(ref: list[str], hyp: list[str]) -> tuple[int, list[tuple[str, str]]]:
    """(word errors, [(hyp word, "ok"|"sub"|"ins")]) — a word-level Levenshtein
    alignment; deletions count as errors but have no hyp word to mark. PURE."""
    n, m = len(ref), len(hyp)
    d = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n + 1):
        d[i][0] = i
    for j in range(m + 1):
        d[0][j] = j
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            c = 0 if ref[i - 1] == hyp[j - 1] else 1
            d[i][j] = min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + c)
    # backtrace preference: a match, then an insertion, then a deletion, then a
    # substitution — so a right word is never painted wrong when an equal-cost path
    # keeps it ("send the report now" vs "send the final report": only "now" is marked)
    marks, i, j = [], n, m
    while i > 0 or j > 0:
        if i > 0 and j > 0 and ref[i - 1] == hyp[j - 1] and d[i][j] == d[i - 1][j - 1]:
            marks.append((hyp[j - 1], "ok"))
            i, j = i - 1, j - 1
        elif j > 0 and d[i][j] == d[i][j - 1] + 1:
            marks.append((hyp[j - 1], "ins"))
            j -= 1
        elif i > 0 and d[i][j] == d[i - 1][j] + 1:
            i -= 1
        else:
            marks.append((hyp[j - 1], "sub"))
            i, j = i - 1, j - 1
    return d[n][m], list(reversed(marks))


def raw_marks(transcript: str, marks) -> list[tuple[str, str]]:
    """The transcript's own whitespace words with the comparison's marks mapped back
    onto them (a word is marked when any of its normalised parts is). Falls back to
    the normalised words when the two do not line up. PURE."""
    marks = [tuple(m) for m in (marks or [])]
    out, k = [], 0
    for w in str(transcript or "").split():
        parts = normalize(w)
        got = marks[k:k + len(parts)]
        if len(got) != len(parts) or any(g[0] != p for g, p in zip(got, parts)):
            return marks
        k += len(parts)
        bad = [m for _w, m in got if m != "ok"]
        out.append((w, bad[0] if bad else "ok"))
    return out if k == len(marks) else marks


def allowed_errors(n_ref: int) -> int:
    return int(math.floor(WER_MAX * max(0, int(n_ref)) + 1e-9))


def term_heard(term: str, hyp: list[str]) -> bool:
    t = normalize(term)
    if not t:
        return False
    return any(hyp[i:i + len(t)] == t for i in range(len(hyp) - len(t) + 1))


def checks_for(clip: dict, transcript) -> list[dict]:
    """The two declared checks of one clip. Each check's "ok" is True/False, or None
    when the checker itself could not run — the caller turns None into INCONCLUSIVE,
    never into PASS (row 16)."""
    out = []
    terms = list(clip.get("terms") or [])
    try:
        hyp = normalize(transcript)
        heard = [t for t in terms if term_heard(t, hyp)]
        out.append({"id": "terms", "label": "Key words heard",
                    "value": f"{len(heard)}/{len(terms)}", "ok": bool(terms) and len(heard) == len(terms),
                    "missing": [t for t in terms if t not in heard]})
    except Exception:  # noqa: BLE001
        out.append({"id": "terms", "label": "Key words heard", "value": "?", "ok": None,
                    "missing": []})
    try:
        ref = normalize(clip["text"])
        errs, marks = align(ref, normalize(transcript))
        cap = allowed_errors(len(ref))
        out.append({"id": "errors", "label": "Word errors", "value": f"{errs} (max {cap})",
                    "ok": errs <= cap, "errors": errs, "max": cap, "marks": marks})
    except Exception:  # noqa: BLE001
        out.append({"id": "errors", "label": "Word errors", "value": "?", "ok": None})
    return out


def test_status(outcome: dict, checks: list[dict] | None) -> tuple[str, str]:
    """(branch, reason) for ONE run. The order matters: an execution failure is never
    scored, and a broken checker never defaults to PASS."""
    o = outcome if isinstance(outcome, dict) else {}
    err = str(o.get("error") or "")
    if o.get("unavailable") or (err and evidence._UNAVAILABLE_RX.search(err)):
        return "INCONCLUSIVE", "the hosted demo was unavailable (" + (err or "no page")[:80] + ")"
    if o.get("deadline"):
        if o.get("submitted"):
            return "TIMEOUT", f"no result within the {RUN_SECONDS:.0f}-second test window"
        return "INCONCLUSIVE", "the demo page did not become usable in time"
    if err:
        return "PARTIAL_FAIL", "the tool returned an error: " + err[:80]
    if o.get("inconclusive") and not o.get("done"):
        return "INCONCLUSIVE", str(o["inconclusive"])[:120]
    if not o.get("done"):
        return "INCONCLUSIVE", "the output could not be read"
    if not checks or any(c.get("ok") is None for c in checks):
        return "INCONCLUSIVE", "a checker failed, so no pass or fail is given"
    if all(c["ok"] for c in checks):
        return "PASS", "every check passed"
    failed = [c["label"].lower() for c in checks if not c["ok"]]
    return "PARTIAL_FAIL", "failed: " + ", ".join(failed)


def execution_failure(branch: str) -> bool:
    return branch in ("TIMEOUT", "INCONCLUSIVE")


def incomplete(results: list[dict]) -> bool:
    """R2: two CONSECUTIVE execution failures end the testing early ("test incomplete")."""
    run = 0
    for r in results:
        run = run + 1 if execution_failure(r.get("branch", "")) else 0
        if run >= 2:
            return True
    return False


def verdict(results: list[dict]) -> str:
    """The episode branch from the main tests (the repeat is shown, never substituted):
    all PASS -> PASS; any check failed -> PARTIAL_FAIL; else any timeout -> TIMEOUT;
    else INCONCLUSIVE. An episode with no completed test is INCONCLUSIVE."""
    bs = [r.get("branch") for r in results]
    if bs and all(b == "PASS" for b in bs) and len(bs) == 4:
        return "PASS"
    if "PARTIAL_FAIL" in bs:
        return "PARTIAL_FAIL"
    if "TIMEOUT" in bs:
        return "TIMEOUT"
    return "INCONCLUSIVE"


def tally(results: list[dict], declared: int = 8) -> dict:
    """Counts, never a percentage (row 16): passed checks of the declared checks, and
    how many tests timed out / could not be verified."""
    passed = sum(1 for r in results for c in (r.get("checks") or []) if c.get("ok") is True)
    return {"passed": passed, "declared": declared,
            "timed_out": sum(1 for r in results if r.get("branch") == "TIMEOUT"),
            "unverified": sum(1 for r in results if r.get("branch") == "INCONCLUSIVE")}


def tally_text(t: dict) -> str:
    s = f"{t['passed']}/{t['declared']} checks passed"
    extra = []
    if t.get("timed_out"):
        extra.append(f"{t['timed_out']} timed out" if t["timed_out"] > 1 else "one timed out")
    if t.get("unverified"):
        extra.append(f"{t['unverified']} not verified" if t["unverified"] > 1 else "one not verified")
    return s + ("; " + ", ".join(extra) if extra else "")


def repeat_choice(results: list[dict]) -> tuple[int, str]:
    """R3 07:30: repeat the first FAILED test, otherwise the declared control (clip 1).
    Returns (test index 0-3, "failed"|"control")."""
    for i, r in enumerate(results):
        if r.get("branch") == "PARTIAL_FAIL":
            return i, "failed"
    return 0, "control"


# ================================================================== fixtures
def load_sets(path: Path | None = None) -> list[dict]:
    try:
        d = json.loads(Path(path or MANIFEST).read_text(encoding="utf-8"))
        sets = d.get("sets") if isinstance(d, dict) else None
        return [s for s in (sets or []) if isinstance(s, dict) and len(s.get("clips") or []) == 4]
    except Exception:  # noqa: BLE001
        return []


def clip_path(clip: dict) -> Path:
    return FIXTURES / str(clip.get("file") or "")


def fixture_ok(clip: dict) -> bool:
    """The committed WAV exists and matches the manifest's sha256 — a fixture that
    changed silently would make two episodes' results incomparable."""
    p = clip_path(clip)
    try:
        return p.exists() and hashlib.sha256(p.read_bytes()).hexdigest() == clip.get("sha256")
    except Exception:  # noqa: BLE001
        return False


def make_fixtures(path: Path | None = None) -> list[str]:
    """Generate every clip in the manifest (edge-tts + ffmpeg) and write each sha256 and
    duration back. Run ONCE by a developer (`py -3 -m factverse.trials --make-fixtures`);
    the WAVs are committed, the show never regenerates them."""
    import asyncio
    import subprocess

    import edge_tts

    man_path = Path(path or MANIFEST)
    man = json.loads(man_path.read_text(encoding="utf-8"))
    done = []
    ff = fv.FFMPEG or "ffmpeg"
    for s in man["sets"]:
        for c in s["clips"]:
            out = FIXTURES / c["file"]
            out.parent.mkdir(parents=True, exist_ok=True)
            mp3 = out.with_suffix(".src.mp3")

            async def _go(c=c, mp3=mp3):
                await edge_tts.Communicate(c["text"], c["voice"], rate=c.get("rate") or "+0%").save(str(mp3))
            asyncio.run(_go())
            nz = c.get("noise")
            if nz:
                # speech level -> noise level at the declared SNR; gain_db lowers BOTH
                # (a quiet microphone), applied after the mix
                gain = float(nz.get("gain_db", 0.0))
                fc = (f"[0:a]aresample=16000,aformat=channel_layouts=mono,loudnorm=I=-23:TP=-2[s];"
                      f"anoisesrc=color={nz['color']}:seed={int(nz['seed'])}:sample_rate=16000:amplitude=1,"
                      f"loudnorm=I={-23 - float(nz['snr_db'])}:TP=-2[n];"
                      f"[s][n]amix=inputs=2:duration=first:normalize=0,volume={gain}dB[a]")
                args = [ff, "-y", "-loglevel", "error", "-i", str(mp3), "-filter_complex", fc,
                        "-map", "[a]", "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", str(out)]
            else:
                args = [ff, "-y", "-loglevel", "error", "-i", str(mp3), "-af", "loudnorm=I=-23:TP=-2",
                        "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", str(out)]
            subprocess.run(args, check=True, timeout=120)
            mp3.unlink(missing_ok=True)
            c["sha256"] = hashlib.sha256(out.read_bytes()).hexdigest()
            c["seconds"] = round(out.stat().st_size / 32000.0, 2)   # 16 kHz x 16-bit mono
            done.append(c["file"])
    man_path.write_text(json.dumps(man, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return done


def fixture_url(clip: dict) -> str:
    return f"https://github.com/{REPO}/raw/main/assets/trials/fixtures/{FAMILY}/{clip['file']}"


# ================================================================== history
def load_history(paths: tuple | None = None) -> list[dict]:
    """Every recorded episode, the node's own file and the repo's published copy,
    de-duplicated by id. Fail-soft: unreadable = empty."""
    seen, out = set(), []
    for p in (paths or (HISTORY, STATE)):
        try:
            d = json.loads(Path(p).read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        for e in (d if isinstance(d, list) else []):
            if isinstance(e, dict) and e.get("id") and e["id"] not in seen:
                seen.add(e["id"])
                out.append(e)
    return out


def save_history(episodes: list[dict], path: Path | None = None) -> bool:
    try:
        p = Path(path or HISTORY)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(episodes, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        return True
    except Exception:  # noqa: BLE001
        return False


def public_record(ep: dict) -> dict:
    """What the repo copy keeps: no narration text, no local paths."""
    keep = ("id", "date", "slot", "tool", "maker", "repo", "model", "space", "space_sha",
            "hardware", "fixture_set",
            "question", "verdict", "tally", "branch_why", "started_at", "ended_at",
            "recap_not_before", "sheet_url", "narration_source", "narration_hash", "tests",
            "repeat", "status")
    out = {k: ep.get(k) for k in keep if k in ep}
    for key in ("tests",):
        out[key] = [{k: v for k, v in (t or {}).items() if k not in ("recording", "clip", "marks")}
                    for t in (ep.get(key) or [])]
    if isinstance(ep.get("repeat"), dict):
        out["repeat"] = {k: v for k, v in ep["repeat"].items() if k not in ("recording", "clip")}
    return out


# ================================================================== pipeline hooks
def _slot_dt(slot) -> _dt.datetime | None:
    try:
        s = str(slot or "").strip().replace("Z", "+00:00")
        d = _dt.datetime.fromisoformat(s)
        return d.astimezone(_dt.timezone.utc) if d.tzinfo else d.replace(tzinfo=_dt.timezone.utc)
    except Exception:  # noqa: BLE001
        return None


def is_live_slot(slot) -> bool:
    """True when `slot` is the Live Trials slot itself (Saturday 18:45 UTC)."""
    d = _slot_dt(slot)
    return bool(d and d.weekday() == SLOT_WEEKDAY and f"{d:%H:%M}" == SLOT_UTC)


def skip_short_slot(slot) -> bool:
    """Row 8: on a live day the live replaces the 18:45 Short (3 notifications per 24 h
    already go to the long-form + two Shorts). Behind `trials_live`. Called inside
    run()'s post-upload zone, so it NEVER raises."""
    try:
        return fv.flag("trials_live", False) and is_live_slot(slot)
    except Exception:  # noqa: BLE001
        return False


def _norm_name(s) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(s or "").lower())


def recap_blocked(item: dict, now: _dt.datetime | None = None,
                  episodes: list[dict] | None = None) -> bool:
    """Row 9: no recap upload in an episode archive's first 72 h. A tool-lane candidate
    whose URL or name is the tested tool's, within `recap_not_before`, is skipped.
    Never raises; no episodes = never blocks."""
    try:
        now = now or _now()
        eps = episodes if episodes is not None else load_history((STATE, HISTORY))
        url = str((item or {}).get("url") or "").lower()
        title = _norm_name((item or {}).get("title"))
        for e in eps:
            nb = _slot_dt(e.get("recap_not_before"))
            if not nb or now >= nb:
                continue
            names = [_norm_name(e.get("tool"))] + [_norm_name(x) for x in (e.get("aliases") or [])]
            ids = [str(x).lower() for x in (e.get("space"), e.get("repo"), e.get("model")) if x]
            if any(i and i in url for i in ids) or any(n and len(n) >= 4 and n in title for n in names):
                return True
        return False
    except Exception:  # noqa: BLE001
        return False


def recap_not_before(started_at: str) -> str:
    d = _slot_dt(started_at) or _now()
    return (d + _dt.timedelta(hours=RECAP_HOURS)).isoformat(timespec="seconds")


def fourteen_day_readout(episodes: list[dict]) -> str:
    """Row 12 on the two pilot episodes' archive numbers [{"avd_s", "views"}]:
    "insufficient" (fewer than 2 with data), "stop" (both < 0:45 with >= 25 views each),
    "stretch" (both >= 2:00), "better" (both > 1:02), else "inconclusive".
    Concurrency and subscribers are signals only — they never enter this."""
    rows = [e for e in (episodes or []) if isinstance(e, dict)]
    good = []
    for e in rows[:2]:
        try:
            a, v = float(e["avd_s"]), int(e["views"])
        except (KeyError, TypeError, ValueError):
            continue
        if math.isfinite(a):
            good.append((a, v))
    if len(good) < 2:
        return "insufficient"
    if all(a < AVD_STOP_S and v >= STOP_MIN_VIEWS for a, v in good):
        return "stop"
    if all(a >= AVD_STRETCH_S for a, _ in good):
        return "stretch"
    if all(a > AVD_BASELINE_S for a, _ in good):
        return "better"
    return "inconclusive"


# ================================================================== the hosted demo
def space_facts(space: str) -> dict | None:
    """HF API facts for one Space, or None. Bounded fetch (evidence._json)."""
    d = evidence._json(f"https://huggingface.co/api/spaces/{space}")
    if not isinstance(d, dict):
        return None
    rt = d.get("runtime") if isinstance(d.get("runtime"), dict) else {}
    hw = rt.get("hardware") if isinstance(rt.get("hardware"), dict) else {}
    host = str(d.get("host") or "")
    if not host and d.get("subdomain"):
        host = f"https://{d['subdomain']}.hf.space"
    card = d.get("cardData") if isinstance(d.get("cardData"), dict) else {}
    return {"space": space, "host": host, "sdk": str(d.get("sdk") or ""),
            "stage": str(rt.get("stage") or ""), "hardware": str(hw.get("current") or ""),
            "sha": str(d.get("sha") or ""), "last_modified": str(d.get("lastModified") or ""),
            "likes": int(d.get("likes") or 0) if str(d.get("likes") or "0").isdigit() else 0,
            "license": str(card.get("license") or "")}


def upload_plan(cfg, prefer: str = "") -> dict | None:
    """PURE: from a Gradio /config, the plan to run OUR file — a button whose click
    dependency takes an upload-capable audio component and returns a textbox (the
    transcript the checks read). `prefer` = a button label to choose when several
    qualify; otherwise a label that says English / (en) wins, then the first. None =
    not drivable with our fixture."""
    if not isinstance(cfg, dict):
        return None
    comps = {c.get("id"): c for c in (cfg.get("components") or []) if isinstance(c, dict)}
    best = None
    for d in (cfg.get("dependencies") or []):
        if not isinstance(d, dict):
            continue
        for t in d.get("targets") or []:
            if not (isinstance(t, (list, tuple)) and len(t) == 2 and t[1] == "click"):
                continue
            btn = comps.get(t[0]) or {}
            if btn.get("type") != "button":
                continue
            audio = [i for i in (d.get("inputs") or [])
                     if (comps.get(i) or {}).get("type") == "audio"
                     and "upload" in ((comps.get(i) or {}).get("props") or {}).get("sources", ["upload"])]
            outs = [o for o in (d.get("outputs") or []) if (comps.get(o) or {}).get("type") == "textbox"]
            if not audio or not outs:
                continue
            text = str((btn.get("props") or {}).get("value") or "").strip()
            low = text.lower()
            rank = (0 if prefer and text == prefer else 1,
                    0 if ("(en)" in low or "english" in low) else 1, t[0])
            if best is None or rank < best[0]:
                best = (rank, t[0], audio[0], outs[0], d)
    if not best:
        return None
    _r, bid, aid, oid, dep = best

    def sel(cid):
        eid = str(((comps.get(cid) or {}).get("props") or {}).get("elem_id") or "")
        return f"#{eid}" if re.fullmatch(r"[A-Za-z][\w-]*", eid) else f"#component-{cid}"

    def lab(cid):
        return str(((comps.get(cid) or {}).get("props") or {}).get("label") or "").strip()[:80]

    return {"button": sel(bid),
            "button_text": str(((comps.get(bid) or {}).get("props") or {}).get("value") or "").strip()[:60],
            "audio": sel(aid), "audio_label": lab(aid),
            "outputs": [sel(oid)], "output_labels": [lab(oid)], "output_types": ["textbox"],
            "api_name": str(dep.get("api_name") or "")[:60],
            "gradio": str(cfg.get("version") or "")[:20]}


def _audio_input(page, plan: dict):
    """The <input type=file> of the plan's audio component: by DOM id (Gradio 4/5),
    else inside the block carrying its label (Gradio 6 renders no ids), else the
    page's first upload input."""
    loc = page.locator(f"{plan['audio']} input[type=file]")
    if plan.get("audio_label"):
        loc = loc.or_(page.locator(".block").filter(
            has=page.get_by_text(plan["audio_label"], exact=True)).locator("input[data-testid=file-upload]"))
    return loc.or_(page.locator("input[data-testid=file-upload]")).first


def _setting_values(page, labels: list[str]) -> dict:
    out = {}
    for lab in labels or []:
        try:
            box = page.locator(".block").filter(has=page.get_by_text(lab, exact=True)).last
            inp = box.locator("input").first
            v = inp.input_value(timeout=2000) if inp.count() else ""
            if not v:
                v = box.locator("input:checked").first.get_attribute("value", timeout=1000) or ""
            if v:
                out[lab] = str(v)[:100]
        except Exception:  # noqa: BLE001
            continue
    return out


def drive_upload(host: str, plan: dict, wav: str, out_dir: Path, seconds: float = RUN_SECONDS,
                 pins: list[str] | None = None, settings: list[str] | None = None) -> dict:
    """Upload ONE fixture to the Space's own audio input, press its button, read the
    transcript back — in a clean headless browser, recorded. Returns the raw outcome
    (`test_status` reads it). Never raises. Runs in its own thread when the caller
    already holds a Playwright loop (trials_live's renderer)."""
    from playwright.sync_api import sync_playwright

    o = {"recording": "", "t_input": 0.0, "t_done": 0.0, "text": "", "settings": {},
         "ran_at": _now().isoformat(timespec="seconds")}
    out_dir = Path(out_dir)
    rec_dir = out_dir / "rec"
    shutil.rmtree(rec_dir, ignore_errors=True)
    rec_dir.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + float(seconds)

    def left_ms():
        return max(1, int((deadline - time.monotonic()) * 1000))

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=["--enable-unsafe-swiftshader",
                                                             "--use-angle=swiftshader"])
            # a CLEAN context: no storage, no cookies, no log-in (P.1 D5)
            ctx = browser.new_context(viewport={"width": REC_W, "height": REC_H},
                                      record_video_dir=str(rec_dir),
                                      record_video_size={"width": REC_W, "height": REC_H},
                                      color_scheme="light")
            page = ctx.new_page()
            t_page = time.monotonic()
            try:
                resp = page.goto(host, wait_until="domcontentloaded", timeout=left_ms())
                if resp is not None and resp.status >= 400:
                    o["unavailable"] = True
                    raise RuntimeError(f"HTTP {resp.status}")
                btn = evidence._button_locator(page, plan)
                btn.wait_for(state="visible", timeout=left_ms())
                up = _audio_input(page, plan)
                up.wait_for(state="attached", timeout=left_ms())
                for choice in pins or []:
                    page.get_by_label(choice, exact=True).first.check(timeout=min(10000, left_ms()))
                    page.wait_for_timeout(1500)       # the Space swaps its model list
                page.wait_for_timeout(800)
                o["settings"] = _setting_values(page, settings or [])
                out = evidence._output_locator(page, plan, 0)
                handle = out.element_handle(timeout=min(5000, left_ms()))
                if handle is None:
                    raise RuntimeError("transcript box not found on the page")
                before = page.evaluate(evidence._SIG_JS, [handle])
                o["t_input"] = time.monotonic() - t_page
                up.set_input_files(str(wav), timeout=left_ms())
                page.wait_for_timeout(1500)           # upload + waveform render
                btn.click(timeout=left_ms())
                o["submitted"] = True
                evidence._center(out)
                while True:
                    if time.monotonic() >= deadline:
                        o["deadline"] = True
                        break
                    page.wait_for_timeout(250)
                    s = page.evaluate(evidence._SIG_JS, [handle])
                    o["queued"] = s["queued"]
                    if s["error"]:
                        page.wait_for_timeout(1000)   # the toast with the reason lands late
                        o["error"] = page.evaluate(evidence._SIG_JS, [handle])["error"] or s["error"]
                        break
                    if s["nonempty"] and not s["pending"] and s["sig"] != before["sig"]:
                        o["done"] = True
                        o["text"] = _full_text(page, handle) or s["text"]
                        break
                o["t_done"] = time.monotonic() - t_page
                o["seconds"] = round(o["t_done"] - o["t_input"], 1)
                if o.get("done"):
                    page.wait_for_timeout(1500)
                    try:
                        page.screenshot(path=str(out_dir / "result.png"))
                    except Exception:  # noqa: BLE001
                        pass
            except Exception as e:  # noqa: BLE001
                o.setdefault("inconclusive", f"{type(e).__name__}: {str(e)[:120]}")
                if o.get("submitted") and "Timeout" in type(e).__name__ and time.monotonic() >= deadline - 1:
                    o["deadline"] = True
            try:
                o["recording"] = str(page.video.path()) if page.video else ""
            except Exception:  # noqa: BLE001
                pass
            page.close()
            ctx.close()
            browser.close()
    except Exception as e:  # noqa: BLE001
        o.setdefault("inconclusive", f"{type(e).__name__}: {str(e)[:120]}")
    return o


def _full_text(page, handle) -> str:
    """The whole transcript (the evidence signature cuts text at 300 chars)."""
    try:
        return str(page.evaluate(
            "(el) => { const t = el.querySelector('textarea'); return t ? t.value : (el.innerText || ''); }",
            handle) or "")[:2000]
    except Exception:  # noqa: BLE001
        return ""


def in_thread(fn, timeout: float, *a, **kw):
    """Run `fn` in a fresh thread (Playwright's sync API refuses to start inside a
    thread that already runs its loop — the renderer's) with a wall-clock join."""
    box = {}

    def _go():
        try:
            box["v"] = fn(*a, **kw)
        except Exception as e:  # noqa: BLE001
            box["e"] = e

    t = threading.Thread(target=_go, daemon=True)
    t.start()
    t.join(timeout=timeout)
    if t.is_alive():
        return {"inconclusive": "the browser did not return in time", "deadline": False}
    return box.get("v") if "v" in box else {"inconclusive": f"{type(box.get('e')).__name__}"}


def capture_cut(o: dict) -> dict | None:
    """The span of the recording that shows the run (P.1's hosted_cut: 1 s before the
    upload to 2.5 s after the result, at most 4x, kept to 20 s)."""
    if not o.get("recording") or not o.get("t_done"):
        return None
    return evidence.hosted_cut(o["t_input"], o["t_done"])


def run_test(plan: dict, clip: dict, out_dir: Path, label: str = "") -> dict:
    """One fixture through the hosted demo, scored. The result dict is what the show,
    the sheet and the record read."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    o = in_thread(drive_upload, RUN_SECONDS + 45, plan["host"], plan["upload"],
                  str(clip_path(clip)), out_dir, RUN_SECONDS, plan.get("pins"), plan.get("settings"))
    o = o if isinstance(o, dict) else {}
    checks = checks_for(clip, o.get("text", "")) if o.get("done") else []
    branch, why = test_status(o, checks)
    if not o.get("done"):
        checks = [{"id": "terms", "label": "Key words heard", "value": "not run", "ok": None},
                  {"id": "errors", "label": "Word errors", "value": "not run", "ok": None}]
    r = {"clip": clip["id"], "role": clip.get("role", ""), "label": label,
         "branch": branch, "why": why, "status": EVIDENCE_STATUS[branch],
         "transcript": str(o.get("text") or "")[:2000], "checks": checks,
         "seconds": o.get("seconds"), "ran_at": o.get("ran_at", ""),
         "settings": o.get("settings") or {}, "recording": o.get("recording", ""),
         "cut": capture_cut(o), "error": str(o.get("error") or o.get("inconclusive") or "")[:160]}
    _log(f"{label or clip['id']}: {branch} ({why}) transcript={r['transcript'][:80]!r}")
    return r


def evidence_record(plan: dict, clip: dict, r: dict) -> dict:
    """The shared `evidence` dict (docs/spec/ai-pulse-v3-growth.md) for one run, so a
    Live Trials result can feed the catalog the same way a P.1 hosted test does."""
    ev = evidence.empty()
    ev.update({"source": "hosted", "status": r["status"], "label": SOURCE_LABEL,
               "wording": "", "url": plan.get("host", ""),
               "captured_at": str(r.get("ran_at", ""))[:10],
               "input": f"ToolDojo fixture {clip['file']} (known transcript)",
               "observed": (f"In our hosted-demo run, this clip produced: \"{r['transcript'][:160]}\""
                            if r.get("transcript") else ""),
               "supported_claims": [], "version": plan.get("sha", "")})
    return ev


# ================================================================== planning
def search_movement(name: str, snaps: list[dict] | None = None) -> int | None:
    """Exact-name YouTube search views, newest snapshot window minus the previous
    one, or None when there are not two windows (missing data is not zero demand)."""
    try:
        if snaps is None:
            from factverse import memory
            snaps = memory.snapshots()
        key = _norm_name(name)
        windows, seen = [], set()
        for s in reversed(snaps or []):
            st = s.get("search_terms") if isinstance(s, dict) else None
            if not isinstance(st, dict):
                continue
            w = (st.get("start"), st.get("end"))
            if w in seen:
                continue
            seen.add(w)
            views = 0
            for terms in (st.get("videos") or {}).values():
                for row in terms or []:
                    if isinstance(row, (list, tuple)) and len(row) >= 2 and _norm_name(row[0]) == key:
                        try:
                            views += int(row[1])
                        except (TypeError, ValueError):
                            pass
            windows.append(views)
            if len(windows) == 2:
                break
        return windows[0] - windows[1] if len(windows) == 2 else None
    except Exception:  # noqa: BLE001
        return None


def release_days(repo: str, now: _dt.datetime | None = None) -> int | None:
    """Days since the repo's latest GitHub release, or None."""
    if not repo:
        return None
    d = evidence._json(f"https://api.github.com/repos/{repo}/releases/latest",
                       headers=evidence._gh_headers())
    t = _slot_dt((d or {}).get("published_at")) if isinstance(d, dict) else None
    return ((now or _now()) - t).days if t else None


def star_growth(repo: str, now: _dt.datetime | None = None) -> int | None:
    """New stars in the last 7 days minus the 7 days before, from the stargazer
    timestamps (the newest pages only). None when GitHub would not say."""
    if not repo:
        return None
    now = now or _now()
    info = evidence._json(f"https://api.github.com/repos/{repo}", headers=evidence._gh_headers())
    try:
        n = int((info or {}).get("stargazers_count"))
    except (TypeError, ValueError):
        return None
    last = min(400, max(1, math.ceil(n / 100)))
    hdr = dict(evidence._gh_headers(), Accept="application/vnd.github.star+json")
    a = b = 0
    for page in range(last, max(0, last - 5), -1):
        rows = evidence._json(f"https://api.github.com/repos/{repo}/stargazers",
                              headers=hdr, params={"per_page": 100, "page": page})
        if not isinstance(rows, list):
            return None
        oldest = None
        for r in rows:
            t = _slot_dt((r or {}).get("starred_at")) if isinstance(r, dict) else None
            if not t:
                continue
            age = (now - t).days
            oldest = age if oldest is None else max(oldest, age)
            if age < 7:
                a += 1
            elif age < 14:
                b += 1
        if oldest is not None and oldest >= 14:
            break
    return a - b


def rank_key(c: dict) -> tuple:
    """Row 13: exact-name search movement, then a real release in the last 30 days,
    then 7-day star growth. Missing data ranks after any known value (never as 0)."""
    s, r, g = c.get("search_delta"), c.get("release_days"), c.get("stars_delta")
    return (0 if s is not None else 1, -(s or 0),
            0 if (r is not None and r <= 30) else 1,
            0 if g is not None else 1, -(g or 0), c.get("order", 99))


def gate(c: dict, facts: dict | None, plan: dict | None) -> list[str]:
    """Hard gates (row 13 + the integrator's decision), as refusal reasons."""
    why = []
    if c.get("family", FAMILY) != FAMILY:
        why.append("no deterministic checker for this task family")
    if not facts:
        why.append("the Space could not be read")
        return why
    if facts["hardware"] not in HARDWARE_OK:
        why.append(f"hardware {facts['hardware'] or 'unknown'} is not free CPU (GPU-only: an "
                   "edited explainer instead)")
    if facts["stage"] != "RUNNING":
        why.append(f"Space is {facts['stage'] or 'not running'}")
    if facts["sdk"] != "gradio" or not str(facts["host"]).startswith("https://"):
        why.append("not a Gradio Space")
    if not plan:
        why.append("no audio upload -> transcript text path (cannot run our fixture without clicks)")
    return why


def feed_candidates(items: list[dict] | None = None) -> list[dict]:
    """Tool-lane feed items that are speech-to-text and link a hosted Space, as
    registry-shaped candidates. Fail-soft: [] on anything."""
    out = []
    try:
        from factverse import tasks
        if items is None:
            from factverse import radar
            gh, hf = radar.fetch_github_wide(), radar.fetch_hf_wide()
            items = [dict(t, title=t.get("name"), what=t.get("desc")) for t in (gh or []) + (hf or [])]
        for it in items[:200]:
            if tasks.task_family({"title": it.get("title"), "tool": it.get("title"),
                                  "what": it.get("what")}) != FAMILY:
                continue
            pr = evidence.probe(it)
            for h in (pr or {}).get("hosted") or []:
                if h.get("id"):
                    out.append({"space": h["id"], "tool": str(it.get("title") or h["id"])[:60],
                                "maker": "", "model": pr.get("ident", "") if pr.get("kind") == "hf" else "",
                                "repo": pr.get("ident", "") if pr.get("kind") == "github" else "",
                                "pins": [], "settings": [], "feed": True})
            if len(out) >= 5:
                break
    except Exception as e:  # noqa: BLE001
        _log(f"feed candidates skipped: {type(e).__name__}")
    return out


def pick_set(history: list[dict], sets: list[dict] | None = None) -> dict | None:
    """The first fixture set no earlier episode used (row 16: every episode changes its
    inputs and checks). None = every set is used: write a new set before the next show."""
    used = {str(e.get("fixture_set")) for e in history or []}
    for s in sets if sets is not None else load_sets():
        if s.get("id") not in used:
            return s
    return None


def candidates(feed: list[dict] | None = None) -> list[dict]:
    seen, out = set(), []
    for i, c in enumerate(list(SPACES) + list(feed or [])):
        if c["space"] in seen:
            continue
        seen.add(c["space"])
        out.append(dict(c, order=i, family=FAMILY))
    return out


def plan_episodes(today: _dt.date | None = None, history: list[dict] | None = None,
                  feed: list[dict] | None = None, signals: bool = True) -> tuple[list[dict], list[str]]:
    """(ranked episode plans that pass every hard gate, log lines). The caller
    preflights them in order; the first that RUNS is the episode."""
    today = today or _now().date()
    history = load_history() if history is None else history
    log = []
    fset = pick_set(history)
    if not fset:
        return [], ["no unused fixture set (row 16: inputs must change every episode)"]
    if not all(fixture_ok(c) for c in fset["clips"]):
        return [], [f"fixture set {fset['id']}: a WAV is missing or its sha256 changed"]
    plans = []
    for c in candidates(feed):
        facts = space_facts(c["space"])
        cfg = evidence._json(f"{facts['host'].rstrip('/')}/config") if facts and facts.get("host") else None
        up = upload_plan(cfg)
        why = gate(c, facts, up)
        if why:
            log.append(f"{c['space']}: refused - " + "; ".join(why))
            continue
        if signals:
            c["search_delta"] = search_movement(c["tool"])
            c["release_days"] = release_days(c.get("repo", ""))
            c["stars_delta"] = star_growth(c.get("repo", ""))
        demand = ("search movement " + str(c.get("search_delta"))
                  if c.get("search_delta") is not None else
                  "exploratory: no exact-name search data (unvalidated demand)")
        plans.append({
            "id": f"{today.isoformat()}-{slug(c['tool'])}", "date": today.isoformat(),
            "slot": f"{today.isoformat()}T{SLOT_UTC}:00Z", "tool": c["tool"],
            "maker": c.get("maker", ""), "model": c.get("model", ""), "repo": c.get("repo", ""),
            "space": c["space"], "host": facts["host"], "sha": facts["sha"],
            "hardware": facts["hardware"], "likes": facts["likes"], "license": facts["license"],
            "upload": up, "pins": list(c.get("pins") or []), "settings": list(c.get("settings") or []),
            "fixture_set": fset["id"], "set": fset,
            "question": fset["question"].format(tool=c["tool"]),
            "question_short": fset["question_short"],
            "signals": {"search_delta": c.get("search_delta"), "release_days": c.get("release_days"),
                        "stars_delta": c.get("stars_delta"), "demand": demand},
            "order": c["order"], "search_delta": c.get("search_delta"),
            "release_days": c.get("release_days"), "stars_delta": c.get("stars_delta")})
        log.append(f"{c['space']}: eligible ({facts['hardware']}, {demand})")
    plans.sort(key=rank_key)
    for p in plans:
        if any(e.get("tool") == p["tool"] and e.get("fixture_set") == p["fixture_set"] for e in history):
            log.append(f"{p['space']}: same tool + fixture set as an earlier episode")
    plans = [p for p in plans if not any(e.get("tool") == p["tool"] and e.get("fixture_set") == p["fixture_set"]
                                         for e in history)]
    return plans, log


def comparison_honest(a: dict, b: dict) -> tuple[bool, str]:
    """Row 2 (Episode B, "Same task, two tools"): honest only when both plans test the
    SAME fixture set with the same checks, on the same kind of hosted hardware, and
    neither is the same tool twice. Episode B's run-of-show is a later phase; this is
    the admission rule it must call."""
    if not (isinstance(a, dict) and isinstance(b, dict)):
        return False, "two plans are needed"
    if a.get("tool") == b.get("tool"):
        return False, "the same tool twice"
    if a.get("fixture_set") != b.get("fixture_set"):
        return False, "different inputs"
    if (a.get("hardware") in HARDWARE_OK) != (b.get("hardware") in HARDWARE_OK):
        return False, "one runs on free CPU and the other does not"
    return True, "same inputs, same checks, both hosted on free CPU"


# ================================================================== narration
# windows (scripts/trials_live.GRID) and how many seconds of speech each may hold
WINDOW_SPEECH = {"open": 24, "rules": 26, "result": 22, "run": 40, "repeat_intro": 26,
                 "repeat_result": 20, "verdict": 48, "files": 40, "limits": 50}
WORDS_PER_SECOND = 2.5          # edge-tts at +5% measured ~2.6-2.8; the budget stays under it


def _ord_word(i: int) -> str:
    return ("one", "two", "three", "four")[i]


def _spoken_list(xs: list[str]) -> str:
    xs = [str(x) for x in xs if str(x)]
    return xs[0] if len(xs) == 1 else ", ".join(xs[:-1]) + " and " + xs[-1] if xs else ""


def _lc(name: str) -> str:
    """A clip name inside a sentence: only its first letter lowered ("Fast British
    speech" -> "fast British speech"), so proper nouns keep their capitals."""
    name = str(name or "")
    return name[:1].lower() + name[1:]


def _hardware_spoken(hw: str) -> str:
    return {"cpu-basic": "a free basic CPU", "cpu-upgrade": "an upgraded CPU"}.get(hw, "shared")


def template_narration(plan: dict) -> dict:
    """Every narration line of the episode, ALL FOUR branches of every result window,
    built only from this episode's own fixtures, tool and question. Deterministic: the
    show can run with no LLM at all. Keys: window -> text, or window -> {branch: text}."""
    tool, clips, s = plan["tool"], plan["set"]["clips"], plan["set"]
    hw = _hardware_spoken(plan.get("hardware", ""))
    n = {}
    c1 = clips[0]
    n["open"] = (f"Live trial: {tool}. On screen is our preflight result for clip one, {_lc(c1['name'])}, "
                 f"recorded before this stream started. It is not today's result. "
                 f"The live rerun of the same clip starts now.")
    n["rules"] = (f"The question: {plan['question']} Four clips, each with a known transcript, go to "
                  f"{tool}'s own hosted demo on Hugging Face, running on {hw}. Each clip has two checks: "
                  f"the key words must come through, and word errors must stay within the allowance. "
                  f"This is a hosted test, not a laptop-performance test.")
    for i, c in enumerate(clips):
        k = _ord_word(i)
        terms = _spoken_list(c["terms"])
        if i > 0:
            n[f"run{i + 1}"] = (f"Test {k}: {_lc(c['name'])}. {c['what']} {c['why']} "
                                f"The words that must survive are {terms}. Here is the run, "
                                f"recorded moments ago during this stream.")
        n[f"result{i + 1}"] = {
            "PASS": f"Clip {k} passed both checks. Both key words came through, {terms}, and the "
                    f"word errors stayed within the allowance.",
            "PARTIAL_FAIL": f"Clip {k} failed at least one check. The marked words show where the "
                            f"transcript differs from what was said.",
            "TIMEOUT": f"Clip {k} did not finish within our {RUN_SECONDS:.0f}-second test window. That is "
                       f"not a general speed verdict: hosted demos share their hardware.",
            "INCONCLUSIVE": f"We could not verify clip {k}'s result, so it gets no pass and no fail.",
        }
    n["repeat_intro"] = {"control": ("The repeat. Nothing failed, so clip one, the control, runs again "
                                     "to check the result is stable. Both results stay on the record.")}
    for i, c in enumerate(clips):
        n["repeat_intro"][str(i + 1)] = (f"The repeat. Clip {_ord_word(i)}, {_lc(c['name'])}, failed, so "
                                         f"it runs again under the same conditions. Both results stay on "
                                         f"the record.")
    n["repeat_result"] = {
        "PASS": "The repeat passed both checks. Compare it with the first run on the scorecard.",
        "PARTIAL_FAIL": "The repeat failed at least one check. The marked words show where.",
        "TIMEOUT": f"The repeat did not finish within the {RUN_SECONDS:.0f}-second window.",
        "INCONCLUSIVE": "We could not verify the repeat, so it gets no pass and no fail.",
    }
    q = s["question_short"].rstrip("?").lower()
    n["verdict"] = {
        "PASS": (f"The verdict on {q}: on these four clips, yes. {tool} passed every check shown. "
                 f"That is evidence for these clips, not for every recording."),
        "PARTIAL_FAIL": (f"The verdict on {q}: not on every clip. At least one required check failed, "
                         f"and the scorecard shows which. Compare the marked output with the source "
                         f"before you rely on it."),
        "TIMEOUT": (f"The verdict on {q}: incomplete. At least one run did not finish within the "
                    f"declared test window. That is not a general performance verdict."),
        "INCONCLUSIVE": (f"The verdict on {q}: inconclusive. At least one result could not be "
                         f"validated reliably, so no overall pass or fail is given."),
    }
    n["files"] = {
        "published": (f"Everything from this trial is on the results sheet: the four clips to "
                      f"download, the reference transcripts, every output from {tool}, every check, "
                      f"and how to repeat the test yourself on the same demo. The link is on screen."),
        "unpublished": ("The results sheet did not publish during this stream, so there is no link "
                        "to show yet. Every input, output and check from this trial is saved."),
    }
    lim = (f"Limitations. {tool} ran on its own hosted demo, on hardware we do not control, so the "
           f"timing says nothing about your machine. {s['limitation']}")
    n["limits"] = {
        "PASS": f"{lim} The takeaway: {s['takeaway_pass']}.",
        "PARTIAL_FAIL": f"{lim} The takeaway: {s['takeaway_fail']}.",
        "TIMEOUT": f"{lim} The takeaway: this demo did not finish every clip in time, so the question "
                   f"stays open for those clips.",
        "INCONCLUSIVE": f"{lim} The takeaway: this run could not answer the question, and we will not "
                        f"pretend it did.",
    }
    return n


def _budget(key: str) -> int:
    base = re.sub(r"\d+$", "", key)
    return int(WINDOW_SPEECH.get(base, 22) * WORDS_PER_SECOND)


def _flat(n: dict) -> list[tuple[str, str]]:
    out = []
    for k, v in n.items():
        if isinstance(v, dict):
            out += [(f"{k}.{b}", t) for b, t in v.items()]
        else:
            out.append((k, v))
    return out


def text_ok(key: str, text: str, grounding: str) -> bool:
    """The LLM line gate: inside the window's word budget, no hype, no claim a hosted
    test cannot support, and every number already in the grounding."""
    from factverse import gates
    t = str(text or "").strip()
    words = len(t.split())
    if not 6 <= words <= _budget(key.split(".")[0]):
        return False
    if gates.hype_terms(t):
        return False
    if evidence._OVERCLAIM_HOSTED.search(t):
        return False
    nums = set(re.findall(r"\d[\d,.]*", t))
    return nums <= set(re.findall(r"\d[\d,.]*", grounding))


def llm_narration(plan: dict, template: dict) -> tuple[dict, int]:
    """(narration, lines the model wrote). The model REWRITES the template line by line
    for this episode; any line that fails `text_ok` keeps the template's. No key, or
    any failure, returns the template untouched."""
    if not fv.GEMINI_KEY:
        return template, 0
    try:
        from factverse import llm
        flat = _flat(template)
        grounding = json.dumps({k: v for k, v in plan.items() if k in ("tool", "question", "maker")}) \
            + json.dumps(plan["set"]) + " ".join(t for _k, t in flat)
        prompt = ("You narrate a live, automated test of an AI tool. Rewrite each line below for a "
                  "viewer, in plain spoken English, keeping its exact meaning, its branch outcome and "
                  "every fact. Never add a number, a claim of speed, or anything the line does not "
                  "say. Never say we installed it or that it works offline or on the viewer's "
                  "hardware. Keep each line at most as long as given. Return ONLY JSON "
                  "{\"<key>\": \"<line>\"} with the same keys.\n\nFACTS:\n" + grounding[:6000]
                  + "\n\nLINES:\n" + json.dumps(dict(flat), ensure_ascii=False))
        raw = llm.generate_json(prompt, temperature=0.4, max_tokens=4096)
        raw = raw if isinstance(raw, dict) else {}
    except Exception:  # noqa: BLE001
        return template, 0
    out, wrote = json.loads(json.dumps(template)), 0
    for k, t in _flat(template):
        new = raw.get(k)
        if isinstance(new, str) and text_ok(k, new, grounding):
            if "." in k and k.split(".")[0] in out and isinstance(out[k.split(".")[0]], dict):
                w, b = k.split(".", 1)
                out[w][b] = new.strip()
            else:
                out[k] = new.strip()
            wrote += 1
    return out, wrote


def narration_text(n: dict) -> str:
    return " ".join(t for _k, t in sorted(_flat(n)))


# R3 §2: "standardize the viewing experience and evidence standards; vary the actual
# investigation". The branch lines ARE the standard scoring vocabulary, so the
# variation check reads the windows that carry the investigation: the opening, the
# question and configuration, each test's explanation and the limitations.
VARIED_WINDOWS = ("open", "rules", "run2", "run3", "run4", "limits")


def investigation_text(n: dict) -> str:
    out = []
    for w in VARIED_WINDOWS:
        v = n.get(w)
        vals = list(v.values()) if isinstance(v, dict) else [v]
        for t in vals:
            for sent in re.split(r"(?<=[.!?])\s+", str(t or "")):
                if sent and sent not in out:
                    out.append(sent)
    return " ".join(out)


def narration_hash(n: dict) -> str:
    return hashlib.sha256(narration_text(n).encode("utf-8")).hexdigest()[:16]


def _grams(text: str, k: int = 4) -> set:
    w = re.findall(r"[a-z0-9]+", str(text or "").lower())
    return {tuple(w[i:i + k]) for i in range(len(w) - k + 1)}


def overlap(a: str, b: str) -> float:
    ga, gb = _grams(a), _grams(b)
    return len(ga & gb) / len(ga | gb) if ga and gb else 0.0


def materially_varied(plan: dict, narration: dict, history: list[dict]) -> tuple[bool, list[str]]:
    """Row 16: every episode changes its question, inputs, checks, findings and
    limitations. Refused when the question, the fixture set or the narration repeats
    an earlier episode (narration 4-gram overlap above VARIED_MAX_OVERLAP) — swapping
    the tool name over the same narration fails here."""
    why = []
    text = investigation_text(narration)
    for e in history or []:
        if e.get("question") == plan.get("question"):
            why.append(f"same question as {e.get('id')}")
        if e.get("fixture_set") == plan.get("fixture_set"):
            why.append(f"same fixture set as {e.get('id')}")
        prev = str(e.get("narration_text") or "")
        if prev and overlap(text, prev) > VARIED_MAX_OVERLAP:
            why.append(f"narration overlaps {e.get('id')} by {overlap(text, prev):.2f}")
    return (not why), why


# ================================================================== the results sheet
def sheet_name(ep: dict) -> str:
    return f"{slug(ep.get('date', ''), 10)}-{slug(ep.get('tool', ''))}-{slug(ep.get('fixture_set', ''), 20)}.html"


def sheet_url(ep: dict) -> str:
    from factverse import site
    return site.site_url(f"trials/{sheet_name(ep)}")


def _marks_html(marks) -> str:
    out = []
    for w, m in marks or []:
        cls = "" if m == "ok" else f' class="{ "x" if m == "sub" else "i"}"'
        out.append(f"<span{cls}>{html.escape(str(w))}</span>")
    return " ".join(out)


def render_sheet(ep: dict) -> str:
    """The episode's results sheet (docs/ is served verbatim by Pages: HTML only, every
    value escaped, every href through site.safe_link)."""
    from factverse import site
    e = site._esc
    tl = ep.get("tally") or {}
    clips = {c["id"]: c for c in ((ep.get("set") or {}).get("clips") or [])}
    title = f"{ep.get('tool', '')}: {ep.get('question_short', '')} Live trial results"
    url = sheet_url(ep)
    css = (".ok{color:#3FB950;font-weight:700}.no{color:#F85149;font-weight:700}"
           ".na{color:#D29922;font-weight:700}.x{background:#5a1d1d;border-radius:3px;padding:0 2px}"
           ".i{background:#4d3b0a;border-radius:3px;padding:0 2px}table{width:100%;border-collapse:"
           "collapse;font-size:14px}td,th{border-bottom:1px solid #30363D;padding:6px 4px;text-align:"
           "left;vertical-align:top}audio{width:100%;margin:6px 0}")
    parts = ["<!doctype html><html lang=\"en\"><head>",
             site._head(title, f"{ep.get('tool', '')} tested live on four fixed clips: "
                        f"{tally_text(tl) if tl else ''}.", url, ""),
             f"<style>{css}</style></head><body><main class=\"wrap\">", site._brand(),
             f"<h1>{e(ep.get('tool'))}: <span>{e(ep.get('question_short'))}</span></h1>",
             f"<p class=\"meta\">{e(SOURCE_LABEL)} · Live trial {e(ep.get('date'))} "
             f"{e(SLOT_UTC)}-{e(SLOT_END_UTC)} UTC · {e(DISCLOSURE)}</p>",
             f"<div class=\"decision\"><b>Verdict: {e(BRANCH_LABEL.get(ep.get('verdict'), ''))}</b>"
             f"<p>{e(tally_text(tl) if tl else '')}. {e(ep.get('branch_why', ''))}</p></div>",
             "<h2>The question</h2>", f"<p>{e(ep.get('question'))}</p>",
             "<h2>What was tested</h2><ul>",
             f"<li>Tool: {e(ep.get('tool'))}" + (f" ({e(ep.get('maker'))})" if ep.get('maker') else "") + "</li>"]
    space = site.safe_link(f"https://huggingface.co/spaces/{ep.get('space', '')}")
    parts.append(f"<li>Hosted demo: <a href=\"{e(space)}\">{e(ep.get('space'))}</a>"
                 + (f" at commit <code>{e(str(ep.get('space_sha', ''))[:12])}</code>" if ep.get('space_sha') else "")
                 + f", hardware <code>{e(ep.get('hardware'))}</code></li>")
    st = ep.get("settings") or {}
    if st:
        parts.append("<li>Settings: " + ", ".join(f"{e(k)} = <code>{e(v)}</code>" for k, v in st.items()) + "</li>")
    parts.append(f"<li>Checks per clip: every key word heard; word errors at most "
                 f"{e(int(WER_MAX * 100))} in 100 reference words, rounded down. A check that "
                 f"cannot run is never a pass.</li>")
    parts.append(f"<li>Time limit per run: {RUN_SECONDS:.0f} seconds from opening the demo.</li></ul>")
    parts.append("<h2>Results</h2>")
    for r in list(ep.get("tests") or []) + ([ep["repeat"]] if isinstance(ep.get("repeat"), dict) else []):
        c = clips.get(r.get("clip")) or {}
        cls = {"PASS": "ok", "PARTIAL_FAIL": "no"}.get(r.get("branch"), "na")
        wav = site.safe_link(fixture_url(c)) if c.get("file") else ""
        marks = next((k.get("marks") for k in r.get("checks") or [] if k.get("marks")), None)
        heard = (_marks_html(raw_marks(r.get("transcript", ""), marks)) if marks
                 else e(r.get("transcript") or "(no transcript)"))
        parts.append(
            f"<div class=\"res\"><div class=\"n\">{e(r.get('label'))}: {e(c.get('name'))} "
            f"<span class=\"{cls}\">{e(BRANCH_LABEL.get(r.get('branch'), ''))}</span></div>"
            f"<p class=\"s\"><b>Said:</b> {e(c.get('text'))}</p>"
            f"<p class=\"s\"><b>{e(ep.get('tool'))} heard:</b> {heard}</p>"
            "<table>" + "".join(
                f"<tr><td>{e(k.get('label'))}</td><td>{e(k.get('value'))}</td><td class=\""
                f"{'ok' if k.get('ok') is True else 'no' if k.get('ok') is False else 'na'}\">"
                f"{'pass' if k.get('ok') is True else 'fail' if k.get('ok') is False else 'not run'}</td></tr>"
                for k in r.get("checks") or []) + "</table>"
            f"<p class=\"l\">{e(c.get('what'))} Voice {e(c.get('voice'))}, rate {e(c.get('rate'))}. "
            f"Ran {e(r.get('ran_at'))}"
            # a run with no transcript has no "upload to result" time to report
            + (f", {e(r.get('seconds'))} s from upload to result"
               if r.get("seconds") is not None and r.get("transcript") else "")
            + f". {e(str(r.get('why') or '')[:1].upper() + str(r.get('why') or '')[1:])}."
            + (f" <a href=\"{e(wav)}\">Download the clip</a>" if wav else "") + "</p></div>")
    parts += ["<h2>Repeat it yourself</h2><ol>",
              f"<li>Download the four clips (links above). Each one is a 16 kHz mono WAV.</li>",
              f"<li>Open <a href=\"{e(space)}\">{e(ep.get('space'))}</a>"
              + (f" and choose {e(', '.join(ep.get('pins') or []))}" if ep.get("pins") else "")
              + ".</li><li>Upload a clip, press the button, and compare the transcript with the "
                "reference above: lower-case it, drop punctuation, read numbers as words, then count "
                "inserted, missing and wrong words.</li></ol>",
              "<h2>Limitations</h2><ul>",
              f"<li>{e(site.NOT_ESTABLISHED['hosted'])}</li>",
              f"<li>{e(site.NO_SPEED_RANKING)}</li>",
              f"<li>{e((ep.get('set') or {}).get('limitation', ''))}</li>",
              f"<li>Demand for this tool: {e((ep.get('signals') or {}).get('demand', 'not measured'))}.</li></ul>",
              "<h2>How this was made</h2>",
              f"<p class=\"note\">{e(DISCLOSURE)}. The narration for every possible outcome was "
              f"written before the test ran; the branch you heard was chosen by the checks above. "
              f"No code from the tool ran on our machine: the clips were uploaded to the tool's own "
              f"public demo in a clean browser. Fixtures: {e('self-generated (Edge TTS voices, ffmpeg noise)')}.</p>",
              site._footer(), "</main></body></html>"]
    return "".join(parts)


# ================================================================== publishing
def publish_files(files: dict, message: str, token: str | None = None,
                  seconds: float = 60.0) -> list[str] | None:
    """Commit `files` ({repo path: text}) straight to main through the GitHub Contents
    API — the node never edits its own checkout, so a later `git pull` cannot conflict.
    Needs TRIALS_GITHUB_TOKEN (contents: write on this repo only). Returns the paths
    written, or None. The token rides in a header, never in a URL or a log line."""
    import os
    tok = token if token is not None else os.environ.get("TRIALS_GITHUB_TOKEN", "")
    if not tok:
        return None
    box = {}

    def _go():
        import base64
        import requests
        done = []
        h = {"Authorization": f"Bearer {tok}", "Accept": "application/vnd.github+json",
             "User-Agent": "ToolDojo-trials"}
        for path, text in files.items():
            api = f"https://api.github.com/repos/{REPO}/contents/{path}"
            r = requests.get(api, headers=h, params={"ref": "main"}, timeout=20)
            sha = r.json().get("sha") if r.status_code == 200 else None
            body = {"message": message, "branch": "main",
                    "content": base64.b64encode(text.encode("utf-8")).decode("ascii")}
            if sha:
                body["sha"] = sha
            p = requests.put(api, headers=h, json=body, timeout=30)
            if p.status_code in (200, 201):
                done.append(path)
        box["done"] = done

    try:
        t = threading.Thread(target=_go, daemon=True)
        t.start()
        t.join(timeout=seconds)        # requests' timeout is not a deadline (CLAUDE.md)
        return box.get("done") if box.get("done") else None
    except Exception as e:  # noqa: BLE001
        _log("publish failed: " + str(e).replace(tok, "<redacted>")[:120])
        return None


def _cli(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="v3-T.1 Live Trials helpers")
    ap.add_argument("--make-fixtures", action="store_true")
    a = ap.parse_args(argv)
    if a.make_fixtures:
        for f in make_fixtures():
            print("wrote", f)
        return 0
    ap.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())

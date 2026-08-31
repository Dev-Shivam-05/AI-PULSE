"""v3-F.2: one Telegram message per published video.

The channel's only distribution surface is YouTube's own feed. A Telegram
channel is the cheapest owned one there is — free, no review, no algorithm —
and the v3-F.1 tool page already emits the OG card Telegram renders.

**Why this is a separate entry point and not part of run():** `eng.yt_upload`
uploads the long-form PRIVATE with `publishAt` = `longform_slot_utc` (16:45
UTC), while the pipeline runs at 12:23 UTC. A message sent from the post-upload
zone would link a video that reads "Video unavailable" for four and a half
hours. So `.github/workflows/notify.yml` fires at 16:55 UTC and this module
reads the ledger for a row whose `publish_at` is already in the past.

Every function fails soft (returns False/None, never raises) and `main()`
always exits 0: this is an unattended job whose failure must never turn the
repo red or block the state-save.

Spec: docs/spec/ai-pulse-v3f2.md
"""
from __future__ import annotations

import datetime as _dt
import html
import json
import os
import sys
from pathlib import Path

import requests

from factverse import config as fv
from factverse import site

API = "https://api.telegram.org"
RUNS_LOG = fv.STATE / "runs.jsonl"
NOTIFIED = fv.STATE / "notified.json"

MAX_NOTIFIED = 500       # spec #10 — newest N video URLs are remembered
MAX_AGE_HOURS = 36       # spec #3 — never post a video older than this
TIMEOUT = 20             # spec #9
MAX_TEXT = 4096          # Bot API hard limit: one char over is a 400, i.e. no post


# --------------------------------------------------------------- config/secrets
def enabled() -> bool:
    # fv.flag, not fv.setting: setting() returns an env var as a STRING and
    # bool("false") is True — the switch would be un-flippable from Actions.
    return fv.flag("telegram", True)


def _token() -> str:
    """Env only (spec #7). A bot token in config.json would be a committed secret."""
    return str(os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip()


def _chat() -> str:
    return str(os.environ.get("TELEGRAM_CHAT_ID") or "").strip()


def _redact(text, token: str | None = None) -> str:
    """The request URL carries the token, and requests' own exception messages quote
    that URL verbatim ("Max retries exceeded with url: /bot123:AA.../sendMessage").
    Actions masks secret values in its logs; a local run and a fork do not."""
    s = str(text or "")
    tok = token if token is not None else _token()
    if tok:
        s = s.replace("bot" + tok, "bot***").replace(tok, "***")
    return s


# --------------------------------------------------------------- state (fail-soft)
def load_notified(path: Path | None = None) -> list[str]:
    """The video URLs already posted, or [] — a missing or corrupt file must never
    stop the job (it costs at most one duplicate message)."""
    p = Path(path or NOTIFIED)
    try:
        data = json.loads(p.read_text(encoding="utf-8")) if p.exists() else []
    except (OSError, json.JSONDecodeError):
        return []
    return [str(u) for u in data if isinstance(u, str) and u.strip()] if isinstance(data, list) else []


def save_notified(urls: list[str], path: Path | None = None) -> bool:
    p = Path(path or NOTIFIED)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(urls[-MAX_NOTIFIED:], ensure_ascii=False), encoding="utf-8")
        return True
    except OSError as e:
        print(f"   ⚠️ notified-state write failed: {e}")
        return False


def load_rows(path: Path | None = None) -> list[dict]:
    """The run ledger as dicts. One unparsable line must not lose the rest."""
    p = Path(path or RUNS_LOG)
    out: list[dict] = []
    try:
        text = p.read_text(encoding="utf-8") if p.exists() else ""
    except OSError:
        return out
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            out.append(row)
    return out


# --------------------------------------------------------------- selection (pure)
def _when(row: dict) -> _dt.datetime | None:
    """The row's publish moment, naive UTC. `publish_at` is the truth ('…Z' from
    scheduling); `timestamp` is the fallback (record_run writes datetime.now(), and
    CI runs in UTC). A row whose time parses as neither is skipped — eligibility
    cannot be proven for it, and posting on a guess is how a private video leaks."""
    for key in ("publish_at", "timestamp"):
        raw = str(row.get(key) or "").strip()
        if not raw:
            continue
        try:
            dt = _dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            continue
        return dt.astimezone(_dt.timezone.utc).replace(tzinfo=None) if dt.tzinfo else dt
    return None


def pick_row(rows: list[dict], notified: list[str] | None = None,
             now: _dt.datetime | None = None) -> dict | None:
    """The newest ledger row that may be posted (spec #3), or None.

    PUBLISHED + a YouTube URL + already public + younger than 36 h + not already
    sent. The age bound is what stops the first-ever run announcing a video from
    months ago off the existing ledger."""
    now = now or _dt.datetime.utcnow()
    seen = set(notified or [])
    eligible: list[tuple[_dt.datetime, dict]] = []
    for row in rows or []:
        if not isinstance(row, dict) or row.get("status") != "PUBLISHED":
            continue
        url = str(row.get("youtube_url") or "").strip()
        if not url or url in seen:
            continue
        when = _when(row)
        if when is None or when > now:                       # not public yet
            continue
        if (now - when) > _dt.timedelta(hours=MAX_AGE_HOURS):
            continue
        eligible.append((when, row))
    if not eligible:
        return None
    return max(eligible, key=lambda p: p[0])[1]


def catalog_entry(video_url: str, entries: list[dict] | None = None) -> dict | None:
    """The tool page's catalog row for this video, or None. The catalog is the same
    source of truth the site renders from — no second store, no second slug."""
    url = str(video_url or "").strip()
    if not url:
        return None
    rows = entries if entries is not None else site.load_catalog()
    for e in reversed(rows or []):
        if isinstance(e, dict) and str(e.get("video_url") or "").strip() == url:
            return e
    return None


# --------------------------------------------------------------- message (pure)
def _esc(v) -> str:
    """quote=FALSE on purpose. Telegram's HTML style mandates exactly three
    replacements (& < >) and every value here lands in text, never in a tag
    attribute. quote=True additionally emits `&#x27;` for an apostrophe — a
    NUMERIC reference, which the Bot API docs never promise to decode, and
    "OpenAI's" is the single most common shape a story title has."""
    return html.escape(str(v or ""), quote=False)


def format_message(row: dict, entry: dict | None = None) -> str:
    """The message body (spec #5). Pure: same row in, same bytes out.

    A section with no truthful value is omitted rather than left empty — a tool row
    whose PDF/page seam failed still posts its command and its video."""
    row = row if isinstance(row, dict) else {}
    # Bounded before escaping (which can multiply a length by five): sendMessage
    # rejects >4096 chars with a 400, and a 400 costs the whole post.
    title = str(row.get("title") or "").strip()[:300]
    video = site.safe_link(row.get("youtube_url"))      # never link a scheme we did not check
    if not title or not video:
        return ""
    entry = entry if isinstance(entry, dict) else None
    if entry is None:
        return f"📰 <b>{_esc(title)}</b>\n\n▶ {_esc(video)}"

    head, tail = [f"🔧 <b>{_esc(title)}</b>"], [f"▶ {_esc(video)}"]
    blocks: list[tuple[str, list[str]]] = []
    command = str(entry.get("command") or "").strip()[:800]
    if command:
        blocks.append(("command", ["", f"<code>{_esc(command)}</code>"]))
    what = str(entry.get("what") or "").strip()[:600]
    if what:
        blocks.append(("what", ["", _esc(what)]))
    name = site.entry_name(entry)                       # the one answer for the page's name
    if name:
        blocks.append(("page", ["", f"📄 Cheat sheet: {_esc(site.public_url(name))}"]))

    def _join(bs) -> str:
        return "\n".join(head + [ln for _, b in bs for ln in b] + tail)

    # sendMessage rejects >4096 chars with a 400, and a 400 costs the ENTIRE post —
    # a silent no-post day. Shed by VALUE, not by position: the message exists to
    # deliver the command and the video, so the prose goes first and the command
    # last. Never a raw slice — cutting mid-tag or mid-entity is a 400 of its own.
    for drop in ("what", "page", "command"):
        text = _join(blocks)
        if len(text) <= MAX_TEXT:
            return text
        blocks = [(k, b) for k, b in blocks if k != drop]
    return _join(blocks)                                # title + link always fit


# --------------------------------------------------------------- send (I/O)
def send(text: str, link: str = "", token: str | None = None, chat: str | None = None) -> bool:
    """POST one message. True only on HTTP 200 with `ok: true` — requests does NOT
    raise on 400/401/403, and announcing a post the API refused is worse than none."""
    token = _token() if token is None else token
    chat = _chat() if chat is None else chat
    if not (token and chat and text):
        return False
    payload: dict = {"chat_id": chat, "text": text, "parse_mode": "HTML"}
    if link:
        # spec #6: without this Telegram previews the FIRST link (the page); the
        # video is what needs the click.
        payload["link_preview_options"] = {"url": link, "prefer_large_media": True}
    for attempt in (1, 2):
        try:
            r = requests.post(f"{API}/bot{token}/sendMessage", json=payload, timeout=TIMEOUT)
        except Exception as e:
            print(f"   ⚠️ telegram failed — {type(e).__name__}: {_redact(e, token)}")
            return False
        code = getattr(r, "status_code", 0)
        ok = False
        if code == 200:
            try:
                ok = bool((r.json() or {}).get("ok"))
            except Exception:
                ok = False
        if ok:
            return True
        print(f"   ⚠️ telegram failed — HTTP {code} "
              f"{_redact(str(getattr(r, 'text', ''))[:120], token)}")
        # A 400 is the shape of the request, not the network: drop the newest field
        # and try once more, so an API change costs the preview, not the post.
        if attempt == 1 and code == 400 and "link_preview_options" in payload:
            payload.pop("link_preview_options")
            continue
        return False
    return False


def main(argv: list[str] | None = None) -> int:
    """Always returns 0 — a failed announcement must never fail the workflow."""
    if not enabled():
        print("  ↷ Telegram: disabled by config (telegram=false).")
        return 0
    if not (_token() and _chat()):
        print("  ↷ Telegram not configured — skipping.")
        return 0
    try:
        notified = load_notified()
        row = pick_row(load_rows(), notified)
        if not row:
            print("  ↷ Telegram: nothing new to post.")
            return 0
        url = str(row.get("youtube_url") or "").strip()
        entry = catalog_entry(url) if row.get("format") == "tool" else None
        text = format_message(row, entry)
        if not text:
            print("  ↷ Telegram: nothing new to post.")
            return 0
        if send(text, site.safe_link(url)):
            print(f"  📣 Telegram: posted — {row.get('title', '')}")
            # only on success: a failure retries tomorrow, or ages out of the window
            save_notified(notified + [url])
    except Exception as e:
        print(f"   ⚠️ telegram failed — {type(e).__name__}: {_redact(e)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

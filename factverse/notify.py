"""v3-F.2/F.3: one Telegram message and one X post per published video.

The channel's only distribution surface is YouTube's own feed. A Telegram
channel is the cheapest owned one there is — free, no review, no algorithm —
and the v3-F.1 tool page already emits the OG card Telegram renders. X's free
tier adds a second surface for the same ledger row at the same price (~500
posts/month against our ~31).

**Why this is a separate entry point and not part of run():** `eng.yt_upload`
uploads the long-form PRIVATE with `publishAt` = `longform_slot_utc` (16:45
UTC), while the pipeline runs at 12:23 UTC. A message sent from the post-upload
zone would link a video that reads "Video unavailable" for four and a half
hours. So `.github/workflows/notify.yml` fires at 16:55 UTC and this module
reads the ledger for a row whose `publish_at` is already in the past.

Every function fails soft (returns False/None, never raises) and `main()`
always exits 0: this is an unattended job whose failure must never turn the
repo red or block the state-save. The two surfaces are independent — each has
its own switch, its own secrets and its own `notified` list, so one being
broken or unconfigured never costs the other its post.

Specs: docs/spec/ai-pulse-v3f2.md (Telegram), docs/spec/ai-pulse-v3f3.md (X)
"""
from __future__ import annotations

import base64
import datetime as _dt
import hashlib
import hmac
import html
import json
import os
import re
import sys
import time
from pathlib import Path
from urllib.parse import parse_qsl, quote, urlsplit

import requests

from factverse import config as fv
from factverse import site

API = "https://api.telegram.org"
X_API = "https://api.x.com/2/tweets"
RUNS_LOG = fv.STATE / "runs.jsonl"
NOTIFIED = fv.STATE / "notified.json"
NOTIFIED_X = fv.STATE / "notified_x.json"

MAX_NOTIFIED = 500       # F.2 #10 — newest N video URLs are remembered
MAX_AGE_HOURS = 36       # F.2 #3 — never post a video older than this
TIMEOUT = 20             # F.2 #9
MAX_TEXT = 4096          # Bot API hard limit: one char over is a 400, i.e. no post
MAX_POST = 280           # X: WEIGHTED chars, not characters — see weighted_len
URL_WEIGHT = 23          # F.3 #8: every URL costs 23 regardless of length (t.co)


# --------------------------------------------------------------- config/secrets
def enabled() -> bool:
    # fv.flag, not fv.setting: setting() returns an env var as a STRING and
    # bool("false") is True — the switch would be un-flippable from Actions.
    return fv.flag("telegram", True)


def x_enabled() -> bool:
    # "twitter", not "x": fv.setting overrides from the env var of the same
    # UPPER name, and `$X` is far too generic a name to bet an unattended job on.
    return fv.flag("twitter", True)


def _token() -> str:
    """Env only (F.2 #7). A bot token in config.json would be a committed secret."""
    return str(os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip()


def _chat() -> str:
    return str(os.environ.get("TELEGRAM_CHAT_ID") or "").strip()


def _x_secrets() -> tuple[str, str, str, str]:
    """(consumer key, consumer secret, access token, access secret) — env only.

    OAuth 1.0a user context (F.3 #3): nothing here expires, so an unattended job
    never has to write a refreshed credential back into a repository secret."""
    return tuple(str(os.environ.get(n) or "").strip() for n in (   # type: ignore[return-value]
        "X_API_KEY", "X_API_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_SECRET"))


def _redact(text, token: str | None = None, extra=()) -> str:
    """The Telegram request URL carries the token, and requests' own exception
    messages quote that URL verbatim ("Max retries exceeded with url:
    /bot123:AA.../sendMessage"). X's credentials ride in an Authorization header
    rather than the URL, but a proxy error can echo a header back, so the four
    values go through the same door. Actions masks secret values in its logs; a
    local run and a fork do not."""
    s = str(text or "")
    tok = token if token is not None else _token()
    if tok:
        s = s.replace("bot" + tok, "bot***").replace(tok, "***")
    # longest first: a short secret that is a substring of a long one would
    # otherwise cut the long one in half and leak the remainder.
    for value in sorted({str(v) for v in (extra or []) if str(v or "").strip()},
                        key=len, reverse=True):
        s = s.replace(value, "***")
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
    """The newest ledger row that may be posted (F.2 #3), or None.

    PUBLISHED + a YouTube URL + already public + younger than 36 h + not already
    sent. The age bound is what stops the first-ever run announcing a video from
    months ago off the existing ledger.

    `notified` is the caller's own list, so the two surfaces retry independently:
    a video Telegram has taken and X has not is still eligible for X."""
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
    """The Telegram message body (F.2 #5). Pure: same row in, same bytes out.

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


# --------------------------------------------------------------- X text (pure)
# F.3 #8: X's limit is 280 WEIGHTED characters (twitter-text config v3). A code
# point inside one of these ranges costs 1; everything else — every emoji, every
# CJK character — costs 2. `len()` therefore ships posts the API refuses with
# "Text is too long", and the two lane emoji alone are 2 apiece.
_WEIGHT_1_RANGES = ((0, 4351), (8192, 8205), (8208, 8210), (8214, 8238),
                    (8240, 8286), (8304, 8348), (8352, 8383))
# We write every URL in these posts ourselves, so a whitespace-delimited scheme
# match is the whole grammar we need. It is deliberately MORE permissive than X's
# own extractor: the only place that could under-count is a scheme-like token
# inside a `title`, and a title arrives from YouTube, which caps it at 100 chars —
# far below the point where the budget bites at all.
_URL_RE = re.compile(r"https?://\S+")


def weighted_len(text) -> int:
    """X's own character count: a URL is 23 whatever its length (t.co rewrites it),
    a code point in `_WEIGHT_1_RANGES` is 1, anything else is 2."""
    s = str(text or "")
    urls = len(_URL_RE.findall(s))
    body = _URL_RE.sub("", s)
    total = urls * URL_WEIGHT
    for ch in body:
        cp = ord(ch)
        total += 1 if any(lo <= cp <= hi for lo, hi in _WEIGHT_1_RANGES) else 2
    return total


def _fit_title(title: str, budget: int) -> str:
    """The title cut to `budget` weighted chars, on a word boundary, with '…'.

    LAST resort only (F.3 #9) — the blocks are shed first. Slicing is safe here
    and was not safe in the Telegram body: an X post is plain text, so there is no
    tag or entity to cut in half. '…' is U+2026, inside the 8214–8238 weight-1
    range, so it costs exactly 1."""
    title = str(title or "").strip()
    if budget <= 0:
        return ""
    if weighted_len(title) <= budget:
        return title
    out, used = [], 0
    for ch in title:
        w = weighted_len(ch)
        if used + w > budget - 1:            # -1 reserves the ellipsis
            break
        out.append(ch)
        used += w
    cut = "".join(out)
    if " " in cut.strip():
        cut = cut[:cut.rstrip().rfind(" ")]
    cut = cut.rstrip()
    # The per-character accumulation above can UNDER-count: weighted_len charges a
    # URL 23 whatever its length, so a title containing a short URL measures more
    # as a whole than as the sum of its characters. Measuring the real result and
    # shrinking is the only exact answer, and an over-long post is a 403, i.e. a
    # silent no-post day.
    while cut and weighted_len(cut + "…") > budget:
        cut = cut[:-1].rstrip()
    return (cut + "…") if cut else ""


def format_post(row: dict, entry: dict | None = None) -> str:
    """The X post body (F.3 #6/#7). Pure: same row in, same bytes out.

    Plain text — no markup, no hashtags, no escaping. The only thing that differs
    from `format_message` is the budget: 280 weighted chars instead of 4096."""
    row = row if isinstance(row, dict) else {}
    title = str(row.get("title") or "").strip()
    video = site.safe_link(row.get("youtube_url"))      # never post a scheme we did not check
    if not title or not video:
        return ""
    entry = entry if isinstance(entry, dict) else None
    tail = f"▶ {video}"
    lead = "📰" if entry is None else "🔧"

    blocks: list[tuple[str, list[str]]] = []
    if entry is not None:
        command = str(entry.get("command") or "").strip()
        if command:
            blocks.append(("command", ["", command]))
        name = site.entry_name(entry)
        if name:
            page = site.safe_link(site.public_url(name))
            if page:
                blocks.append(("page", ["", f"📄 {page}"]))

    def _join(t: str, bs) -> str:
        head = [f"{lead} {t}"]
        body = [ln for _, b in bs for ln in b]
        # A story post has no blocks, so it needs its own blank line before the
        # video; a tool post's 📄 line sits directly above it (F.3 #6/#7).
        return "\n".join(head + (body if body else [""]) + [tail])

    # Shed whole blocks by VALUE — the page link before the command, because the
    # command is the product. Never a partial block.
    for drop in ("page", "command"):
        text = _join(title, blocks)
        if weighted_len(text) <= MAX_POST:
            return text
        blocks = [(k, b) for k, b in blocks if k != drop]

    text = _join(title, blocks)
    if weighted_len(text) <= MAX_POST:
        return text
    # Everything optional is gone and it still does not fit: the title itself is
    # the overflow. Cut it, keeping the lane emoji and the video link intact.
    return _join(_fit_title(title, MAX_POST - weighted_len(_join("", blocks))), blocks)


# --------------------------------------------------------------- send (I/O)
def send(text: str, link: str = "", token: str | None = None, chat: str | None = None) -> bool:
    """POST one Telegram message. True only on HTTP 200 with `ok: true` — requests
    does NOT raise on 400/401/403, and announcing a post the API refused is worse
    than announcing none."""
    token = _token() if token is None else token
    chat = _chat() if chat is None else chat
    if not (token and chat and text):
        return False
    payload: dict = {"chat_id": chat, "text": text, "parse_mode": "HTML"}
    if link:
        # F.2 #6: without this Telegram previews the FIRST link (the page); the
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


# --------------------------------------------------------------- OAuth 1.0a (pure)
def _pct(s) -> str:
    """RFC 3986 percent-encoding: unreserved is ALPHA / DIGIT / '-' / '.' / '_' /
    '~'. Python's always-safe set is exactly those, so `safe=""` is the whole
    rule — this is the single place OAuth 1.0a implementations go wrong."""
    return quote(str(s), safe="")


def oauth_base_string(method: str, url: str, params) -> str:
    """RFC 5849 §3.4.1: METHOD & pct(base URL) & pct(normalized params).

    `params` is a sequence of (key, value) PAIRS, not a dict — a parameter name
    may legally repeat, and the sort is over the encoded pairs."""
    parts = urlsplit(str(url))
    base_url = f"{parts.scheme.lower()}://{parts.netloc.lower()}{parts.path}"
    pairs = [(_pct(k), _pct(v)) for k, v in list(params)]
    pairs += [(_pct(k), _pct(v)) for k, v in parse_qsl(parts.query, keep_blank_values=True)]
    norm = "&".join(f"{k}={v}" for k, v in sorted(pairs))
    return f"{method.upper()}&{_pct(base_url)}&{_pct(norm)}"


def oauth_signature(base: str, consumer_secret: str, token_secret: str) -> str:
    """HMAC-SHA1 over the base string, keyed by pct(consumer)&pct(token), base64."""
    key = f"{_pct(consumer_secret)}&{_pct(token_secret)}".encode("utf-8")
    mac = hmac.new(key, str(base).encode("utf-8"), hashlib.sha1).digest()
    return base64.b64encode(mac).decode("ascii")


def oauth_header(method: str, url: str, secrets, nonce: str = "", timestamp: str = "") -> str:
    """The `Authorization: OAuth …` header for one request.

    The JSON body is deliberately NOT signed: OAuth 1.0a only folds a body into
    the base string when it is `application/x-www-form-urlencoded`, and X's v2
    endpoints take JSON."""
    ck, cs, at, ats = secrets
    oauth = [
        ("oauth_consumer_key", ck),
        ("oauth_nonce", nonce or base64.urlsafe_b64encode(os.urandom(24)).decode().strip("=")),
        ("oauth_signature_method", "HMAC-SHA1"),
        ("oauth_timestamp", timestamp or str(int(time.time()))),
        ("oauth_token", at),
        ("oauth_version", "1.0"),
    ]
    sig = oauth_signature(oauth_base_string(method, url, oauth), cs, ats)
    fields = sorted(oauth + [("oauth_signature", sig)])
    return "OAuth " + ", ".join(f'{_pct(k)}="{_pct(v)}"' for k, v in fields)


def send_x(text: str, secrets=None) -> bool:
    """POST one tweet. True only on HTTP 200/201 carrying a `data.id`.

    No retry (F.3 #5): X answers a repeated post with 403 `duplicate content`, so
    retrying a call that may have half-succeeded is how one video becomes two."""
    try:
        ck, cs, at, ats = _x_secrets() if secrets is None else tuple(secrets)
    except (TypeError, ValueError):     # not four values: unconfigured, not a crash
        return False
    if not (text and ck and cs and at and ats):
        return False
    hide = (cs, ats, at, ck)
    try:
        r = requests.post(X_API, json={"text": text},
                          headers={"Authorization": oauth_header("POST", X_API, (ck, cs, at, ats)),
                                   "Content-Type": "application/json"},
                          timeout=TIMEOUT)
    except Exception as e:
        print(f"   ⚠️ x failed — {type(e).__name__}: {_redact(e, '', hide)}")
        return False
    code = getattr(r, "status_code", 0)
    if code in (200, 201):
        try:
            data = (r.json() or {}).get("data")
        except Exception:
            data = None
        if isinstance(data, dict) and str(data.get("id") or "").strip():
            return True
    print(f"   ⚠️ x failed — HTTP {code} {_redact(str(getattr(r, 'text', ''))[:120], '', hide)}")
    return False


# --------------------------------------------------------------- entry points
def _post_telegram() -> None:
    """One Telegram message, or a logged no-op. Never raises.

    The config read and the secret read are INSIDE the try: `main()` has no
    handler of its own, so anything that escapes here fails the workflow for a
    message nobody missed."""
    token = ""
    try:
        if not enabled():
            print("  ↷ Telegram: disabled by config (telegram=false).")
            return
        token, chat = _token(), _chat()
        if not (token and chat):
            print("  ↷ Telegram not configured — skipping.")
            return
        notified = load_notified(NOTIFIED)
        row = pick_row(load_rows(), notified)
        if not row:
            print("  ↷ Telegram: nothing new to post.")
            return
        url = str(row.get("youtube_url") or "").strip()
        entry = catalog_entry(url) if row.get("format") == "tool" else None
        text = format_message(row, entry)
        if not text:
            print("  ↷ Telegram: nothing new to post.")
            return
        if send(text, site.safe_link(url)):
            print(f"  📣 Telegram: posted — {row.get('title', '')}")
            # only on success: a failure retries tomorrow, or ages out of the window
            save_notified(notified + [url], NOTIFIED)
    except Exception as e:
        # the local token, not _token(): the read that raised must not be re-run
        # in the handler that is supposed to survive it
        print(f"   ⚠️ telegram failed — {type(e).__name__}: {_redact(e, token)}")


def _post_x() -> None:
    """One X post, or a logged no-op. Never raises.

    Its own `notified_x` list, so a video Telegram already took is still eligible
    here — the two surfaces fail and retry independently. The config and secret
    reads are inside the try for the same reason as `_post_telegram`."""
    secrets: tuple = ()
    try:
        if not x_enabled():
            print("  ↷ X: disabled by config (twitter=false).")
            return
        secrets = _x_secrets()
        if not all(secrets):
            print("  ↷ X not configured — skipping.")
            return
        notified = load_notified(NOTIFIED_X)
        row = pick_row(load_rows(), notified)
        if not row:
            print("  ↷ X: nothing new to post.")
            return
        url = str(row.get("youtube_url") or "").strip()
        entry = catalog_entry(url) if row.get("format") == "tool" else None
        text = format_post(row, entry)
        if not text:
            print("  ↷ X: nothing new to post.")
            return
        if send_x(text, secrets):
            print(f"  🐦 X: posted — {row.get('title', '')}")
            save_notified(notified + [url], NOTIFIED_X)
    except Exception as e:
        print(f"   ⚠️ x failed — {type(e).__name__}: {_redact(e, '', secrets)}")


def main(argv: list[str] | None = None) -> int:
    """Always returns 0 — a failed announcement must never fail the workflow.

    Both surfaces always run: a broken or unconfigured Telegram must not cost X
    its post, and vice versa."""
    _post_telegram()
    _post_x()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

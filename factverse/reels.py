"""v3-F.4: one Instagram Reel and one Facebook Reel per published video.

The day's Shorts are rendered anyway and used once. IG and FB both take the same
9:16 file through the official Graph API, so a third and fourth distribution
surface costs one upload each and no new content. `docs/ENGINEERING_AUDIT.md` #6
named this route: the first-party API, never the `instagrapi` path (disabled,
and ban-bait from a datacenter IP).

**Why this runs from publish.yml and not from the 16:55 notify workflow.** The
Shorts MP4 exists only inside the publish job's workspace — `output/shorts/` is
gitignored and the runner is destroyed when the job ends. Announcing a *link*
can happen anywhere; re-uploading a *file* can only happen where the file is.

**Why the 16:45 publish-slot rule does not apply.** That rule exists because the
long-form is PRIVATE until `publishAt`, so a link posted at 12:23 UTC is dead for
four and a half hours. A Reel is a re-upload of the Short, not a link to the
long-form, and its caption carries NO YouTube URL at all (spec #9). Nothing in
it can be dead.

Every function fails soft (returns False/None, never raises) and `main()` always
exits 0: the publish workflow must never turn red for a Reel nobody missed. IG
and FB are independent — own switch, own state, own `try` — so one being broken
or unconfigured never costs the other its post.

Spec: docs/spec/ai-pulse-v3f4.md
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import requests

from factverse import config as fv
from factverse import notify
from factverse import site

# One version constant (spec #6). The two upload hosts are Meta's, not ours: the
# Graph host takes the JSON calls, rupload takes the bytes.
GRAPH = "v25.0"
GRAPH_API = f"https://graph.facebook.com/{GRAPH}"
RUPLOAD_IG = f"https://rupload.facebook.com/ig-api-upload/{GRAPH}"
RUPLOAD_FB = f"https://rupload.facebook.com/video-upload/{GRAPH}"

PROD_LOG = fv.OUTPUT / "production_log.json"
NOTIFIED_IG = fv.STATE / "notified_ig.json"
NOTIFIED_FB = fv.STATE / "notified_fb.json"

MAX_CAPTION = 2200               # IG's caption limit; FB's is larger, so this binds both
MAX_BYTES = 200 * 1024 * 1024    # spec #15 — a 35 s 1080x1920 clip is ~10 MB
TIMEOUT = 30                     # the small JSON calls
UPLOAD_TIMEOUT = 180             # the one call that carries the file
POLL_EVERY = 5                   # spec #8
POLL_MAX = 24                    # 24 x 5 s = 120 s, enforced as a wall clock too
HASHTAGS = "#ai #aitools #opensource #developer #tech"


# --------------------------------------------------------------- config/secrets
def ig_enabled() -> bool:
    # fv.flag, not fv.setting: setting() hands back an env var as a STRING and
    # bool("false") is True — the switch would be un-flippable from Actions.
    return fv.flag("instagram", True)


def fb_enabled() -> bool:
    return fv.flag("facebook", True)


def _token() -> str:
    """The long-lived Page access token — env only (spec #5). Meta: a Page token
    minted from a long-lived User token "does not have an expiration date", which
    is the whole requirement for a job nobody watches."""
    return str(os.environ.get("META_PAGE_TOKEN") or "").strip()


def _page_id() -> str:
    return str(os.environ.get("META_PAGE_ID") or "").strip()


def _ig_user_id() -> str:
    return str(os.environ.get("META_IG_USER_ID") or "").strip()


# --------------------------------------------------------------- selection
def load_log(path: Path | None = None) -> list[dict]:
    """`output/production_log.json` as a list, or [] — a missing or corrupt file
    must never stop the run.

    This, not `runs.jsonl`, is the source of truth here: only the production log
    records the Short *paths* (the ledger records counts)."""
    p = Path(path or PROD_LOG)
    try:
        data = json.loads(p.read_text(encoding="utf-8")) if p.exists() else []
    except (OSError, json.JSONDecodeError):
        return []
    return [e for e in data if isinstance(e, dict)] if isinstance(data, list) else []


def resolve_short(rel, base: Path | None = None) -> Path | None:
    """A logged Short path as a readable file under MAX_BYTES, or None.

    `_rel` writes posix separators, but its own fallback returns the raw string —
    so a Windows-authored log carries backslashes that mean nothing on the ubuntu
    runner. Splitting on BOTH separators is the standing trap in this repo
    (`receipts._basename`, `deliverable.safe_name`), here on the joining side."""
    raw = str(rel or "").strip().replace("\\", "/")
    if not raw:
        return None
    try:
        p = Path(raw)
        if not p.is_absolute():
            p = Path(base or fv.BASE) / p
        if not p.is_file():
            return None
        if p.stat().st_size > MAX_BYTES or p.stat().st_size == 0:
            print(f"   ↷ Short {p.name} is {p.stat().st_size} bytes — skipping.")
            return None
        return p
    except OSError:
        return None


def pick_entry(entries: list[dict], notified: list[str] | None = None,
               base: Path | None = None):
    """`(row, video_path)` for today's Short, or None.

    Only the LAST production-log entry is ever considered (spec #3): an older row
    is another day's video whose file left with its runner, and posting one on a
    retry firing is how a week-old Short lands as today's Reel. It must be
    PUBLISHED, carry the YouTube URL that is this surface's idempotence key, and
    have a first Short still on disk.

    `notified` is the caller's own list, so IG and FB retry independently."""
    rows = [e for e in (entries or []) if isinstance(e, dict)]
    if not rows:
        return None
    row = rows[-1]
    if row.get("status") != "PUBLISHED":
        return None
    url = str(row.get("youtube_url") or "").strip()
    if not url or url in set(notified or []):
        return None
    shorts = row.get("shorts") if isinstance(row.get("shorts"), list) else []
    if not shorts:
        return None
    video = resolve_short(shorts[0], base)          # spec #3: the first Short, only
    return (row, video) if video else None


# --------------------------------------------------------------- caption (pure)
def _fit_title(title: str, budget: int) -> str:
    """The title cut to `budget` CHARACTERS, on a word boundary, with '…'.

    Last resort only (spec #10) — the blocks are shed first. Characters, not
    weighted chars: IG and FB count what `len` counts, unlike X. Slicing is safe
    because a caption is plain text — there is no tag or entity to cut in half."""
    title = str(title or "").strip()
    if budget <= 0:
        return ""
    if len(title) <= budget:
        return title
    cut = title[:budget - 1]
    if " " in cut.strip():
        cut = cut[:cut.rstrip().rfind(" ")]
    cut = cut.rstrip()
    return (cut + "…") if cut else ""


def caption(row: dict, entry: dict | None = None) -> str:
    """The Reel caption (spec #9). Pure: same row in, same bytes out.

    Deliberately NOT `shorts_meta[i]["instagram_caption"]`: that field comes from
    a v2-era prompt in `factverse_engine.step8_meta` — 20 hashtags and a
    hard-coded `Follow @{HANDLE}` — and it is raw model output nothing coerces.

    No YouTube URL anywhere: the long-form is still private when this runs."""
    row = row if isinstance(row, dict) else {}
    title = str(row.get("title") or "").strip()
    if not title:
        return ""
    entry = entry if isinstance(entry, dict) else None
    lead = "\U0001F4F0" if entry is None else "\U0001F527"      # 📰 / 🔧
    handle = str(fv.setting("channel_handle", "") or "").strip()
    cta = f"Full breakdown on YouTube — @{handle}" if handle else "Full breakdown on YouTube"

    command = page = ""
    if entry is not None:
        command = str(entry.get("command") or "").strip()
        name = site.entry_name(entry)
        # the catalog is merged state read back off origin/main and `page` derives
        # from model output — safe_link is the guard the site and screencap use
        page = site.safe_link(site.public_url(name)) if name else ""

    def _join(t: str, keep) -> str:
        out = [f"{lead} {t}"]
        if command and "command" in keep:
            out += ["", command]
        if page and "page" in keep:
            out += ["", f"\U0001F4C4 {page}"]
        out += ["", cta]
        if "tags" in keep:
            out += ["", HASHTAGS]
        return "\n".join(out)

    # Shed whole blocks by VALUE — never a partial one. The hashtags are the
    # cheapest thing in the caption, the command is the product, so they go in
    # that order; only when nothing optional is left is the title itself cut.
    keep = ["command", "page", "tags"]
    for drop in ("tags", "page", "command"):
        text = _join(title, keep)
        if len(text) <= MAX_CAPTION:
            return text
        keep = [k for k in keep if k != drop]
    text = _join(title, keep)
    if len(text) <= MAX_CAPTION:
        return text
    return _join(_fit_title(title, MAX_CAPTION - len(_join("", keep))), keep)


# --------------------------------------------------------------- HTTP (fail-soft)
def _body(resp) -> dict:
    try:
        d = resp.json()
    except Exception:
        return {}
    return d if isinstance(d, dict) else {}


def _hide(token: str) -> tuple:
    return (token,)


def graph_post(path: str, data: dict, token: str) -> dict | None:
    """POST to the Graph API. The parsed body on 2xx, else None.

    The token rides in the FORM BODY, never the query string: `requests` quotes
    the full request URL inside its own exception messages and Actions logs are
    public (the `notify._redact` lesson, from the other direction)."""
    payload = dict(data or {})
    payload["access_token"] = token
    try:
        r = requests.post(f"{GRAPH_API}/{path}", data=payload, timeout=TIMEOUT)
    except Exception as e:
        print(f"   ⚠️ graph POST {path} — {type(e).__name__}: "
              f"{notify._redact(e, '', _hide(token))}")
        return None
    if getattr(r, "status_code", 0) in (200, 201):
        return _body(r)
    print(f"   ⚠️ graph POST {path} — HTTP {getattr(r, 'status_code', 0)} "
          f"{notify._redact(str(getattr(r, 'text', ''))[:200], '', _hide(token))}")
    return None


def graph_get(path: str, fields: str, token: str) -> dict | None:
    """GET one object's fields. The token goes in an `Authorization: Bearer`
    header, NOT in `params` (spec #14): requests would put a param in the query
    string, and requests' own exception text quotes the whole request URL —
    which is exactly how a token reaches a public Actions log. Verified against
    the live API: a bad token in this header answers OAuthException **190**
    ("could not be decrypted"), while no token at all answers 2500, so the header
    is genuinely read."""
    try:
        r = requests.get(f"{GRAPH_API}/{path}", params={"fields": fields},
                         headers={"Authorization": f"Bearer {token}"}, timeout=TIMEOUT)
    except Exception as e:
        print(f"   ⚠️ graph GET {path} — {type(e).__name__}: "
              f"{notify._redact(e, '', _hide(token))}")
        return None
    if getattr(r, "status_code", 0) == 200:
        return _body(r)
    print(f"   ⚠️ graph GET {path} — HTTP {getattr(r, 'status_code', 0)} "
          f"{notify._redact(str(getattr(r, 'text', ''))[:200], '', _hide(token))}")
    return None


def _upload_url(answer: dict | None, fallback: str) -> str:
    """The upload URL Meta handed back, else our own constant.

    Meta returns it (FB's start call names it `upload_url`) precisely so clients
    do not hard-code a host, and a hard-coded one is a single API move from being
    wrong. But that URL is where the Page token is about to be sent, so it is
    honoured ONLY on Meta's own upload host — `site.safe_link` refuses a scheme it
    did not check for the same reason, one layer down."""
    url = str((answer or {}).get("upload_url") or (answer or {}).get("uri") or "").strip()
    return url if url.startswith("https://rupload.facebook.com/") else fallback


def upload_bytes(url: str, video: Path, token: str) -> bool:
    """PUSH the file to rupload. True only on 2xx with no `error` in the body.

    One shot from `offset: 0` — resuming is what the `offset` header is for, but
    a retry of a call that may have half-succeeded is the risk this repo already
    refuses everywhere else (spec #13), and tomorrow renders another Short."""
    try:
        blob = Path(video).read_bytes()
    except OSError as e:
        print(f"   ⚠️ could not read {Path(video).name}: {e}")
        return False
    headers = {"Authorization": f"OAuth {token}", "offset": "0",
               "file_size": str(len(blob)), "Content-Type": "application/octet-stream"}
    try:
        r = requests.post(url, data=blob, headers=headers, timeout=UPLOAD_TIMEOUT)
    except Exception as e:
        print(f"   ⚠️ upload — {type(e).__name__}: {notify._redact(e, '', _hide(token))}")
        return False
    code = getattr(r, "status_code", 0)
    body = _body(r)
    if code in (200, 201) and not body.get("error") and body.get("success") is not False:
        return True
    print(f"   ⚠️ upload — HTTP {code} "
          f"{notify._redact(str(getattr(r, 'text', ''))[:200], '', _hide(token))}")
    return False


def wait_for_container(container_id: str, token: str) -> bool:
    """Poll the IG container until `FINISHED` (spec #8). False on ERROR, EXPIRED,
    an unreadable answer, or the 120 s deadline.

    Bounded by BOTH a poll count and a `time.monotonic` wall clock: a `timeout=`
    is only the gap between socket reads, never a deadline, so 24 slow polls
    could otherwise outlive the useful life of the job."""
    deadline = time.monotonic() + POLL_MAX * POLL_EVERY
    for _ in range(POLL_MAX):
        d = graph_get(str(container_id), "status_code", token)
        status = str((d or {}).get("status_code") or "").upper()
        if status in ("FINISHED", "PUBLISHED"):
            return True
        if status in ("ERROR", "EXPIRED"):
            print(f"   ⚠️ instagram container {status}")
            return False
        if time.monotonic() >= deadline:
            break
        time.sleep(POLL_EVERY)
    print("   ⚠️ instagram container never finished processing")
    return False


# --------------------------------------------------------------- publish
def publish_ig(video: Path, text: str, ig_user_id: str, token: str) -> bool:
    """Container -> bytes -> poll -> publish (spec #7). True only when
    `media_publish` hands back a media id."""
    if not (text and ig_user_id and token):
        return False
    created = graph_post(f"{ig_user_id}/media",
                         {"media_type": "REELS", "upload_type": "resumable",
                          "caption": text}, token)
    container = str((created or {}).get("id") or "").strip()
    if not container:
        return False
    if not upload_bytes(_upload_url(created, f"{RUPLOAD_IG}/{container}"), video, token):
        return False
    if not wait_for_container(container, token):
        return False
    published = graph_post(f"{ig_user_id}/media_publish", {"creation_id": container}, token)
    return bool(str((published or {}).get("id") or "").strip())


def publish_fb(video: Path, text: str, page_id: str, token: str) -> bool:
    """start -> bytes -> finish (spec #7). True only on the finish call's
    `success`. The processing phase is asynchronous and deliberately NOT polled —
    Meta's own answer to the finish call is the answer we record."""
    if not (text and page_id and token):
        return False
    started = graph_post(f"{page_id}/video_reels", {"upload_phase": "start"}, token)
    video_id = str((started or {}).get("video_id") or "").strip()
    if not video_id:
        return False
    if not upload_bytes(_upload_url(started, f"{RUPLOAD_FB}/{video_id}"), video, token):
        return False
    done = graph_post(f"{page_id}/video_reels",
                      {"upload_phase": "finish", "video_id": video_id,
                       "video_state": "PUBLISHED", "description": text}, token)
    return bool((done or {}).get("success"))


# --------------------------------------------------------------- entry points
def _post_ig() -> None:
    """One Instagram Reel, or a logged no-op. Never raises.

    The config read and the secret read are INSIDE the try: `main()` has no
    handler of its own, so anything escaping here fails the publish workflow for
    a Reel nobody missed. That exact hole was found in shipped F.2/F.3 code."""
    token = ""
    try:
        if not ig_enabled():
            print("  ↷ Instagram: disabled by config (instagram=false).")
            return
        token, ig_id = _token(), _ig_user_id()
        if not (token and ig_id):
            print("  ↷ Instagram not configured — skipping.")
            return
        notified = notify.load_notified(NOTIFIED_IG)
        picked = pick_entry(load_log(), notified)
        if not picked:
            print("  ↷ Instagram: no Short from today's run to post.")
            return
        row, video = picked
        url = str(row.get("youtube_url") or "").strip()
        entry = notify.catalog_entry(url) if row.get("format") == "tool" else None
        text = caption(row, entry)
        if not text:
            print("  ↷ Instagram: no Short from today's run to post.")
            return
        if publish_ig(video, text, ig_id, token):
            print(f"  📸 Instagram: posted — {row.get('title', '')}")
            # only on success: a failure leaves the URL eligible for tomorrow
            notify.save_notified(notified + [url], NOTIFIED_IG)
    except Exception as e:
        # the local token, not _token(): the read that raised must not be re-run
        # inside the handler that is supposed to survive it
        print(f"   ⚠️ instagram failed — {type(e).__name__}: "
              f"{notify._redact(e, '', _hide(token))}")


def _post_fb() -> None:
    """One Facebook Reel, or a logged no-op. Never raises. Its own state list, so
    Instagram taking a video cannot silently retire it here."""
    token = ""
    try:
        if not fb_enabled():
            print("  ↷ Facebook: disabled by config (facebook=false).")
            return
        token, page_id = _token(), _page_id()
        if not (token and page_id):
            print("  ↷ Facebook not configured — skipping.")
            return
        notified = notify.load_notified(NOTIFIED_FB)
        picked = pick_entry(load_log(), notified)
        if not picked:
            print("  ↷ Facebook: no Short from today's run to post.")
            return
        row, video = picked
        url = str(row.get("youtube_url") or "").strip()
        entry = notify.catalog_entry(url) if row.get("format") == "tool" else None
        text = caption(row, entry)
        if not text:
            print("  ↷ Facebook: no Short from today's run to post.")
            return
        if publish_fb(video, text, page_id, token):
            print(f"  📘 Facebook: posted — {row.get('title', '')}")
            notify.save_notified(notified + [url], NOTIFIED_FB)
    except Exception as e:
        print(f"   ⚠️ facebook failed — {type(e).__name__}: "
              f"{notify._redact(e, '', _hide(token))}")


def main(argv: list[str] | None = None) -> int:
    """Always returns 0 — a failed Reel must never fail the publish workflow, and
    it runs before the state-save step that the whole day depends on.

    Both surfaces always run: a broken or unconfigured Instagram must not cost
    Facebook its Reel, and vice versa."""
    _post_ig()
    _post_fb()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

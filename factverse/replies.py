"""v3-R D11: answer every genuine viewer question within 24 h, from the video's own sources.

docs/spec/ai-pulse-v3r.md row D11. Until 2026-11-12 the channel had never answered a
comment; a viewer asked "Does it work on 50 series cards" under the gpu-unlock video and
waited days — the README answers it ("Blackwell (RTX 50): Not supported").

Once per publish.yml run (the 12:23 and 14:53 UTC crons, so within 24 h of any question):
list the channel's recent comment threads, skip the channel's own comments and threads it
already answered, and for each new viewer comment ask the model — grounded ONLY in that
video's source page — whether it is a genuine on-topic question and what the sources say.
A question gets a reply; when the sources do not settle it, the reply says so (D11). A
non-question is recorded and never re-asked.

Fail soft all the way to the top: main() never raises (the CLAUDE.md "fail-soft seam has to
be fail-soft all the way" trap — the client build, the state read and every API call sit
inside the try). googleapiclient is imported inside the function that uses it (CI's test job
does not install it). State: state/replied.json, a dict keyed by comment id — in
state_merge.FILES and the publish.yml stash list (the both-halves rule).
"""
from __future__ import annotations

import datetime as dt
import json
import pickle
import re

from factverse import config as fv
from factverse import evidence
from factverse import learn
from factverse import llm
from factverse import memory

STATE = fv.STATE / "replied.json"
LOOKBACK_DAYS = 90            # the backlog D11 clears at launch reaches back this far
MAX_REPLIES = 10              # per run: 50 quota units each
MAX_THREADS = 100             # two pages of commentThreads.list
SOURCE_CHARS = 8000           # source text handed to the model
REPLY_MAX = 450               # characters in a posted reply
STATUSES = ("answered", "not_question", "no_source", "failed")


def enabled() -> bool:
    return fv.flag("comment_replies", False)


# ------------------------------------------------------------------ state
def load_state(path=None) -> dict:
    try:
        d = json.loads((path or STATE).read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except Exception:  # noqa: BLE001 — a missing or corrupt file is an empty one
        return {}


def save_state(state: dict, path=None) -> None:
    try:
        (path or STATE).write_text(json.dumps(state, ensure_ascii=False, indent=1) + "\n",
                                   encoding="utf-8")
    except Exception as e:  # noqa: BLE001
        print(f"  ⚠️ replies: state not saved ({type(e).__name__})")


def merge(theirs, ours) -> dict:
    """state_merge semantics: union by comment id, origin/main's record wins (the first
    decision about a comment stands). A non-dict side contributes nothing."""
    out = dict(ours) if isinstance(ours, dict) else {}
    if isinstance(theirs, dict):
        out.update(theirs)
    return out


# ------------------------------------------------------------------ pure helpers
def own_channel_reply(thread: dict, channel_id: str) -> bool:
    """True when the channel already replied in this thread (by hand or by us)."""
    for c in ((thread.get("replies") or {}).get("comments") or []):
        if (((c.get("snippet") or {}).get("authorChannelId") or {}).get("value")) == channel_id:
            return True
    return False


def pending(threads: list, channel_id: str, state: dict, today: dt.date,
            lookback: int = LOOKBACK_DAYS) -> list[dict]:
    """The viewer comments to look at, oldest first: not the channel's own, not already
    answered by the channel, not in `state`, within `lookback` days. PURE."""
    out = []
    for t in threads or []:
        if not isinstance(t, dict):
            continue
        sn = t.get("snippet") or {}
        top = ((sn.get("topLevelComment") or {}).get("snippet") or {})
        cid = str((sn.get("topLevelComment") or {}).get("id") or t.get("id") or "")
        author = ((top.get("authorChannelId") or {}).get("value")) or ""
        if not cid or cid in state or author == channel_id or own_channel_reply(t, channel_id):
            continue
        try:
            when = dt.date.fromisoformat(str(top.get("publishedAt") or "")[:10])
        except ValueError:
            continue
        if (today - when).days > lookback:
            continue
        out.append({"thread": str(t.get("id") or cid), "comment": cid,
                    "video": str(sn.get("videoId") or top.get("videoId") or ""),
                    "text": str(top.get("textOriginal") or top.get("textDisplay") or "")[:1000],
                    "published": str(top.get("publishedAt") or "")})
    return sorted(out, key=lambda c: c["published"])


def video_row(video_id: str, rows: list) -> dict | None:
    """The PUBLISHED ledger row a video belongs to — its long-form, or the long-form
    whose Short it is."""
    for r in rows or []:
        if not isinstance(r, dict) or r.get("status") != "PUBLISHED":
            continue
        if learn.video_id(r.get("youtube_url") or "") == video_id:
            return r
        for s in r.get("shorts") or []:
            if isinstance(s, dict) and learn.video_id(s.get("url") or "") == video_id:
                return r
    return None


def source_url_of(video_id: str, row: dict | None) -> str:
    """The video's source page: the ledger's source_url, else the site catalogue's
    (older rows predate the field — the memory.build_record fallback)."""
    url = str((row or {}).get("source_url") or "")
    if not url.startswith("http"):
        long_id = learn.video_id((row or {}).get("youtube_url") or "") or video_id
        url = str((memory.tools_index().get(long_id) or {}).get("source_url") or "")
    return url if url.startswith("http") else ""


def prompt(comment: str, title: str, source_url: str, source: str, status: str) -> str:
    ch = fv.CHANNEL_NAME
    return f"""You answer viewer comments for {ch}, a YouTube channel about AI tools.
VIDEO: {title}
EVIDENCE STATUS: {status}
SOURCE ({source_url}), the ONLY thing you may rely on:
{source}

VIEWER COMMENT: {comment}

Decide:
- "question": true only if the comment is a genuine question a viewer wants answered
  (not praise, not a joke, not spam, not abuse).
- "on_topic": true only if it is about this video's subject.
If both are true, write "reply": at most 3 short sentences, plain text, friendly, no emojis,
no links, answered ONLY from the SOURCE. Attribute what the project claims ("the README says").
If the SOURCE does not settle it, say plainly that the project's docs do not say, and set
"settled": false. Never claim {ch} tested, installed or ran anything unless the EVIDENCE
STATUS says so.
Return ONLY JSON: {{"question": true, "on_topic": true, "settled": true, "reply": "..."}}"""


def clean_reply(text) -> str:
    """Model output is never type-safe: a string of at most REPLY_MAX chars, no links
    (a model-written URL is not ours to publish), no markdown emphasis."""
    t = str(text or "") if not isinstance(text, (list, dict)) else ""
    t = re.sub(r"https?://\S+", "", t)
    t = re.sub(r"[*`#]", "", t)
    t = re.sub(r"\s+", " ", t).strip()
    if len(t) > REPLY_MAX:
        cut = t[:REPLY_MAX]
        t = cut[:cut.rfind(". ") + 1] if ". " in cut else cut.rsplit(" ", 1)[0]
    return t.strip()


def decide(raw) -> tuple[str, str, bool]:
    """(status, reply, settled) from the model's answer."""
    if not isinstance(raw, dict):
        return "failed", "", False
    if not raw.get("question") or not raw.get("on_topic"):
        return "not_question", "", False
    reply = clean_reply(raw.get("reply"))
    if not reply:
        return "failed", "", False
    return "answered", reply, bool(raw.get("settled"))


# ------------------------------------------------------------------ the API seams
def _youtube():
    """The Data API client from the CI token, or raise (caught by main)."""
    from googleapiclient.discovery import build  # noqa: PLC0415 — not in the test job
    tok = fv.BASE / "youtube_token.pickle"
    with open(tok, "rb") as f:
        creds = pickle.load(f)
    if creds and creds.expired and creds.refresh_token:
        from google.auth.transport.requests import Request  # noqa: PLC0415
        creds.refresh(Request())
    return build("youtube", "v3", credentials=creds, cache_discovery=False)


def channel_id(yt) -> str:
    resp = yt.channels().list(part="id", mine=True).execute()
    return str(((resp.get("items") or [{}])[0]).get("id") or "")


def threads(yt, cid: str, limit: int = MAX_THREADS) -> list:
    out, token = [], None
    while len(out) < limit:
        kw = {"part": "snippet,replies", "allThreadsRelatedToChannelId": cid, "maxResults": 50,
              "order": "time", "textFormat": "plainText"}
        if token:
            kw["pageToken"] = token
        resp = yt.commentThreads().list(**kw).execute()
        out += resp.get("items") or []
        token = resp.get("nextPageToken")
        if not token:
            break
    return out[:limit]


def post_reply(yt, parent_id: str, text: str) -> bool:
    yt.comments().insert(part="snippet",
                         body={"snippet": {"parentId": parent_id, "textOriginal": text}}).execute()
    return True


def source_text(url: str) -> str:
    """The source page's text: a GitHub/HF README raw, else the page itself."""
    rid = evidence.repo_of(url)
    if rid:
        txt = evidence._readme_raw(rid[0], rid[1]) or ""
        if txt:
            return txt[:SOURCE_CHARS]
    return re.sub(r"<[^>]+>", " ", evidence._text(url) or "")[:SOURCE_CHARS]


# ------------------------------------------------------------------ main
def run_once(yt, rows: list, state: dict, today: dt.date) -> dict:
    """One pass. Mutates `state`; returns counts. Every comment is its own try: one
    bad comment never costs the others (the "a loop that writes must isolate each
    item" trap)."""
    counts = {s: 0 for s in STATUSES}
    cid = channel_id(yt)
    if not cid:
        print("  ⚠️ replies: no channel id — nothing done")
        return counts
    todo = pending(threads(yt, cid), cid, state, today)
    print(f"  💬 replies: {len(todo)} viewer comment(s) to look at")
    posted = 0
    for c in todo:
        if posted >= MAX_REPLIES:
            break
        try:
            row = video_row(c["video"], rows)
            url = source_url_of(c["video"], row)
            src = source_text(url) if url else ""
            if not src:
                state[c["comment"]] = {"video": c["video"], "status": "no_source",
                                       "at": dt.datetime.utcnow().isoformat(timespec="seconds")}
                counts["no_source"] += 1
                continue
            status_text = evidence.label((row or {}).get("evidence_source") or "") or \
                f"Not tested by {fv.CHANNEL_NAME}."
            raw = llm.generate_json(prompt(c["text"], str((row or {}).get("title") or ""), url,
                                           src, status_text), temperature=0.2, max_tokens=1024)
            status, reply, settled = decide(raw)
            if status == "answered":
                post_reply(yt, c["thread"], reply)
                posted += 1
                print(f"  💬 answered {c['comment'][:12]}… ({'settled' if settled else 'not settled'})")
            if status != "failed":
                state[c["comment"]] = {"video": c["video"], "status": status, "settled": settled,
                                       "at": dt.datetime.utcnow().isoformat(timespec="seconds"),
                                       "published": c["published"], "reply": reply}
            counts[status] += 1
        except Exception as e:  # noqa: BLE001 — not recorded: the next run retries it
            counts["failed"] += 1
            print(f"  ⚠️ replies: comment {c['comment'][:12]}… skipped ({type(e).__name__}: {str(e)[:120]})")
    return counts


def main(argv=None) -> int:
    try:
        if not enabled():
            print("  💬 replies: off (comment_replies)")
            return 0
        state = load_state()
        rows = learn.read_runs()
        counts = run_once(_youtube(), rows, state, dt.datetime.utcnow().date())
        save_state(state)
        print(f"  💬 replies done: {counts}")
    except Exception as e:  # noqa: BLE001 — never fail the workflow this lives in
        print(f"  ⚠️ replies skipped: {type(e).__name__}: {str(e)[:160]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

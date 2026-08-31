# Spec — v3-F.2: the Telegram channel bot

Status: **locked 2026-08-31** (owner approved the table below with `go`, no changes).
Branch: `v3-phase-f` (stacked on `v3-phase-c`). Predecessor spec:
`docs/spec/ai-pulse-v3f1.md` (the site — this phase links the pages it writes).

## Why this phase exists

Every video the channel publishes reaches exactly one surface: YouTube's own feed. A
Telegram channel is the cheapest owned distribution there is — free, no review, no
algorithm, one bot token — and the v3-F.1 page already emits the OG card Telegram renders.
This phase pushes one message per published video: the title, the command (tap-to-copy),
the cheat-sheet page and the video.

**The timing is the whole design problem.** `eng.yt_upload` uploads the long-form
**private with `publishAt`** = `longform_slot_utc` (16:45 UTC), while the pipeline itself
runs at 12:23 UTC. A message sent from inside `run()`'s post-upload zone would link a video
that reads "Video unavailable" for the next four and a half hours. So the post does not
happen in `run()` at all — it happens in a second, tiny workflow that fires after the slot
and reads the ledger.

## Locked decisions

| # | Ambiguity | Locked value | Why this default |
|---|---|---|---|
| 1 | Where the code lives | `factverse/notify.py` — pure helpers (`format_message`, `pick_row`, `_redact`) + one I/O seam `send(text, link)` + `main()` behind `python -m factverse.notify`. Every function fail-soft: returns `False`/`None`, never raises, `main()` always exits 0 | The v3-F.1 handoff already named `notify.py`; F.3 (X) becomes a second function in the same module, not a second design |
| 2 | **When it posts** | A **new** workflow `.github/workflows/notify.yml`: `cron: "55 16 * * *"` (16:55 UTC) + `workflow_dispatch`. **Not** in `run()`'s post-upload zone | `yt_upload` uploads private with `publishAt` = 16:45 UTC. A link posted from the 12:23 run is dead for 4½ hours. 16:55 is 10 min after the slot and 2 h after the 14:53 retry cron |
| 3 | Which row it posts | The **newest** `state/runs.jsonl` row with `status == "PUBLISHED"`, a `youtube_url`, `publish_at` in the past, published **within the last 36 h**, and `youtube_url` not already in `state/notified.json`. Exactly one message per run. Long-form only — Shorts are never posted | The 36 h bound stops the first-ever run posting a months-old video off the existing ledger; one message/day keeps the channel worth subscribing to |
| 4 | Which lanes | All four. `tool` rows join `state/tools_index.json` on `video_url` for the command + page; story rows post title + link only | The ledger carries no description, so a story post has nothing else truthful to say. Skipping story days would leave the channel dead 6 days a week |
| 5 | Message text (`parse_mode=HTML`) | **tool:** `🔧 <b>{title}</b>` / blank / `<code>{command}</code>` / blank / `{what}` / blank / `📄 Cheat sheet: {page_url}` / `▶ {video_url}` — **story:** `📰 <b>{title}</b>` / blank / `▶ {video_url}`. Every interpolated value through `html.escape`; both URLs through `site.safe_link` | Tapping a `<code>` block on Telegram mobile copies it — the same "the command is the product" rule as the page's Copy button. `safe_link` is the existing guard for a model-supplied URL |
| 6 | Which link previews | `link_preview_options={"url": <video_url>, "prefer_large_media": True}`. On any HTTP 400, **retry once** with that field removed | The video is what needs the click; without the field Telegram previews the *first* link, which is the page. The retry keeps an API-shape surprise from costing the whole post |
| 7 | Secrets | `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID`, **env only, never `config.json`**. Both unset → log `↷ Telegram not configured — skipping` and exit 0. `notify.yml` passes them from Actions secrets | The ELEVENLABS pattern (v3-E #11): an unset secret expands to `""` and the seam costs nothing until the owner creates it |
| 8 | Token leaking into a public log | `_redact(s)`: every occurrence of the token (and its `bot<token>` form) → `***`. Applied to **every** printed string, including `str(exception)` | A `requests` `ConnectionError` message embeds the full request URL — `.../bot123456:AA…/sendMessage`. Actions masks secret values, but a local or forked run does not |
| 9 | HTTP discipline | `requests.post("https://api.telegram.org/bot<token>/sendMessage", json=…, timeout=20)`; success = HTTP 200 **and** `r.json().get("ok") is True`; anything else logs `⚠️ telegram failed — HTTP {code} {body[:120]}` and returns `False` | `requests` does not raise on 401/403/400 — the `_notify_review` precedent (v3-C.2 #12): never announce a success the API refused |
| 10 | Idempotence state | `state/notified.json` — a **list of video-URL strings**, newest 500 kept. Added to `state_merge.FILES` (the generic `_merge_list` is already the right semantics for a list of strings) **and** to `publish.yml`'s stash loop; `notify.yml` commits it back with the same checkout/merge/retry dance | The standing both-halves trap: a tracked state file in neither list is reverted by `git checkout -B main origin/main` on every run — and then every day re-posts yesterday's video |
| 11 | Kill switch | `config.json` `"telegram": true`, read with `fv.flag` (never `fv.setting`) | `bool("false")` is `True` — `site_pages` shipped that defect once already (F.1 review #9) |
| 12 | Log lines | `📣 Telegram: posted — <title>` / `↷ Telegram: nothing new to post` / `↷ Telegram not configured — skipping` / `⚠️ telegram failed — …`. Exit code always 0 | Same three-state vocabulary as the receipts and site seams, so one glance at the log says worked / no-op / failed |
| 13 | Cron ↔ config coupling | `notify.yml`'s cron is a literal `16:55` with a comment naming `longform_slot_utc`; `main()` does **not** read the clock against config — the `publish_at`-in-the-past check (#3) is what actually guards it | GitHub cron cannot read `config.json`. The runtime check makes an out-of-sync cron a delay, never a broken link |

### Implementation notes (decided during the build, inside the locked table)

- **`html.escape(..., quote=False)`, decided at inspection.** Telegram's HTML style
  mandates exactly three replacements (`&`, `<`, `>`) and every value here lands in text,
  never in a tag attribute. `quote=True` additionally emits `&#x27;` for an apostrophe — a
  *numeric* character reference, which the Bot API documents no promise to decode, and
  `OpenAI's …` is the single most common shape a story title has. The rendered message was
  what caught this; the locked criterion "`"` escaped" is therefore met by leaving `"` and
  `'` literal, which is what Telegram actually wants.
- **`state_merge._merge_list` got the `isinstance` guard `_merge_index` already had.**
  `state/notified.json` is the first file to use the *generic* fallback since v3-F.1, and a
  corrupt/scalar body raised `TypeError` there — inside the one CI step with no `|| true`,
  where `bash -e` loses ALL state, not just this file. Found by the acceptance test, fixed
  in `state_merge`, and it now protects `used_topics.json` / `used_urls.json` too.
- **The 4096-char Bot API limit is enforced by shedding, not slicing.** `sendMessage`
  rejects a longer message with a 400 — which, after the #6 retry, costs the *entire* post.
  A README-derived command and an LLM-written "what" are both unbounded, so the values are
  bounded up front (title 300 / command 800 / what 600) and, if the escaped result is still
  over, the optional blocks are dropped **by value**: prose first, then the page line, then
  the command. Title + video link always survive. A raw slice is never taken — cutting
  mid-tag or mid-entity is a 400 of its own.
- **A row is only marked notified after a successful send.** A failed post therefore
  retries on the next firing — by which time the 36 h window usually still holds, and once
  it does not the row simply ages out rather than posting a stale video days later.
- **`publish_at` is the clock, `timestamp` is the fallback.** Both are naive ISO strings
  (`record_run` writes `datetime.now()`, CI runs in UTC); a row whose time cannot be parsed
  at all is skipped, because eligibility cannot be proven for it.
- The message omits any section it has no truthful value for (no command → no code block,
  no `what` → no paragraph, no page → no 📄 line). The 8-line template is what a complete
  tool row produces.
- `notify.py` imports only `requests`, `config`, `site` (→ `deliverable` → `llm`), so
  `notify.yml` installs nothing beyond `requests`.

## Out of scope (deliberately not built)

- X / IG-FB Reels (board rows F.3 / F.4), a newsletter, or any second platform.
- Posting Shorts, posting a backlog of past videos, or editing/deleting an already-sent
  message.
- Telegram **groups**, replies, buttons/inline keyboards, or reading any inbound message —
  this bot only writes.
- A ledger column or a run-report entry for the post (`state/notified.json` + the log line
  is the record).
- Creating the bot, the channel, or the Actions secrets — owner clicks, below.

## Owner setup (one time, ~3 minutes)

1. Telegram → **@BotFather** → `/newbot` → name it (e.g. `ToolDojo`) and pick a username
   ending in `bot`. BotFather replies with the token — that is `TELEGRAM_BOT_TOKEN`.
2. Create a **public channel** (Telegram → New Channel → Public → `@tooldojo`).
3. Channel → Administrators → **Add the bot as an admin** with "Post messages" on. A bot
   cannot post to a channel it does not administer.
4. GitHub → Settings → Secrets and variables → Actions → **New repository secret**, twice:
   `TELEGRAM_BOT_TOKEN` = the BotFather token, `TELEGRAM_CHAT_ID` = `@tooldojo`
   (a numeric `-100…` id works too, and is what you need if the channel is private).
5. Actions tab → **"ToolDojo — Telegram"** → Run workflow. Expect `📣 Telegram: posted`
   in the log and the message in the channel; `↷ nothing new to post` means the ledger has
   no video published in the last 36 h, which is correct on a day with no run.

## Acceptance criteria

- [x] `py -3 -m pytest tests/ -q` passes with ≥8 new tests (161 → **180**, +19)
- [x] `format_message` on a `tool` row + its catalog entry returns the exact 8-line template
      in #5, with `<b>`/`<code>` intact and `&`, `<`, `>` in title/command escaped (`"` and
      `'` deliberately left literal — see the implementation note above)
- [x] A `javascript:` value in the catalog's `page`/`video_url` produces a message with that
      link absent, not linked
- [x] `pick_row` returns `None` for: an empty ledger, only `SKIPPED_*`/`UPLOAD_FAILED` rows,
      a row whose `publish_at` is in the future, a row 40 h old, and a row whose URL is in
      `notified.json`
- [x] With `notify.requests.post` stubbed: one call, URL contains the token, payload carries
      `chat_id`, `parse_mode="HTML"`, `link_preview_options.url == video_url`; a stubbed
      HTTP 400 triggers exactly one retry **without** `link_preview_options`; a stubbed
      `{"ok": false}` on HTTP 200 is reported as a failure
- [x] A stubbed `post` raising `ConnectionError("… /bot<TOKEN>/sendMessage …")` prints no
      substring of the token, and `main()` still returns 0
- [x] `state_merge.merge_file("state/notified.json", ours, theirs)` unions both lists with no
      duplicates; `state/notified.json` appears in `state_merge.FILES` **and** in
      `publish.yml`'s stash loop
- [x] With no `TELEGRAM_BOT_TOKEN`, and with `telegram: false`, `main()` makes zero HTTP
      calls and returns 0
- [x] Both message bodies rendered and read (`output/demo/telegram/message_*.txt`), and a
      **live `api.telegram.org` call** with a deliberately invalid token returns HTTP 401,
      which `send()` reports as a failure with the token redacted — the endpoint, the
      payload shape and the refusal path verified against the real API without a secret
- [ ] A real message is delivered to a real Telegram channel and screenshotted — command
      tap-to-copy, video preview card. **OUTSTANDING**: no bot token exists on this machine
      or in Actions secrets (see the owner setup above). Everything else was verified against
      a stubbed Bot API and a rendered message body.

## Risks

- **No bot token exists yet**, so the live render is the one thing not verified here.
  Cheapest check: the 5 owner steps above, then a `workflow_dispatch`.
- A second workflow pushing to `main` could race `publish.yml`'s state-save. 16:55 vs
  ~12:30/~15:00 makes overlap effectively impossible, and the merge dance is the same one
  that already survives a forced-fail replay.
- `notify.yml` exiting 0 on a soft failure means a dead token is silent. Cheapest check: the
  `⚠️` line in the run log; if it ever repeats, add a failure alert step (a small F.2b row).
- GitHub disables cron workflows after ~60 days of repo inactivity. `notify.yml` re-enables
  itself the way `publish.yml` does (`gh api -X PUT .../workflows/notify.yml/enable`).

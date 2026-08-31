# HANDOFF — ToolDojo — Phase v3-F.2 (the Telegram bot) — 2026-08-31

*Spec locked (13 decisions, approved with `go`), built, self-reviewed over the diff, and
then wired to a real bot: `notify.main()` delivered a real message to the ToolDojo chat
through the production code path. 180/180 tests. Branch `v3-phase-f` pushed, stacked on
`v3-phase-c` — merge PR #23 (`v3-phase-b`) first, then `v3-phase-c`, then this.*

## Done

- **`factverse/notify.py`**: one Telegram message per published video. It takes the newest
  `PUBLISHED` row in `state/runs.jsonl` whose `publish_at` has already fired, is younger
  than 36 h, and is not in `state/notified.json`; joins `state/tools_index.json` on
  `video_url` for tool rows; and posts title + tap-to-copy `<code>` command + the v3-F.1
  page link + the video. Story lanes post title + video. Every seam fail-soft, `main()`
  always exits 0.
- **`.github/workflows/notify.yml`** (16:55 UTC + `workflow_dispatch`). A *separate*
  workflow on purpose: `yt_upload` uploads private with `publishAt` = 16:45 UTC while the
  pipeline runs at 12:23, so a post from `run()`'s post-upload zone would link a dead video
  for four and a half hours. The runtime `publish_at`-in-the-past check means an
  out-of-sync cron is a delay, never a broken link.
- **Idempotence**: `state/notified.json` (a list of announced URLs, newest 500) got the
  both-halves treatment — `state_merge.FILES` **and** `publish.yml`'s stash list — plus its
  own state-save step in `notify.yml`. A URL is recorded only after a successful send.
- **Live-verified**: the bot `@ToolDojoBot` exists, its token is in the git-ignored `.env`,
  `getMe`/`getChat` returned 200, and `notify.main()` ran the whole real path
  (pick_row → format_message → send → save_notified) with `sendMessage` returning
  `ok: true` — which also proves Telegram accepted the HTML, since it 400s on malformed
  entities. The delivered message was the story-lane template; the tool-lane body is in
  `output/demo/telegram/message_tool.txt` and ships with the first `format=tool` video.
- Earlier, before any token existed, the endpoint and refusal path were proven against the
  real API with a deliberately invalid token (HTTP 401, handled, token redacted).

## Files changed

- `factverse/notify.py` — NEW: config/secrets, `_redact`, ledger + catalog reads,
  `pick_row`, `format_message`, `send`, `main`
- `.github/workflows/notify.yml` — NEW: the 16:55 UTC cron, the post step, its own
  state-save/merge/retry dance, cron keepalive
- `.github/workflows/publish.yml` — `state/notified.json` added to the stash loop
- `factverse/state_merge.py` — `state/notified.json` in `FILES`; `_merge_list` got the
  `isinstance` guard `_merge_index` already had
- `config.json` / `config.example.json` — `"telegram": true` (the kill-switch)
- `tests/test_pipeline_logic.py` — +19 tests (161 → 180)
- `docs/spec/ai-pulse-v3f2.md` — NEW: the contract, the owner setup, what was verified
- `docs/PHASES.md` (F.2 done, owner step 1.5, Next 3 = F.3), `docs/DECISIONS.md`,
  `docs/spec/GLOSSARY.md`, `CLAUDE.md` (3 new traps)
- `state/notified.json` — the announced URL from the live run
- `.env` — **untracked and git-ignored**; holds the two Telegram values locally

## Decisions made (full table in the spec)

- **The announcement lives after the publish slot, not after the upload.** Any future
  surface (X, Reels) belongs in the same place for the same reason.
- All four lanes post, not just tool — the ledger has no description, so a story post is
  title + video, and skipping stories would leave the channel dead six days a week.
- `link_preview_options.url` = the video, with a single retry without that field on a 400:
  the video is what needs the click, and an API-shape surprise should cost the preview,
  not the post.
- Secrets are env-only (`.env` locally, Actions secrets in CI), never `config.json`.
- A row is recorded as notified only on success, so a failed post may retry tomorrow.

## Three defects the self-review found (all fixed and test-pinned)

- `state_merge._merge_list` raised `TypeError` on a scalar body. `state/notified.json` is
  the first file since v3-F.1 to use the *generic* fallback, and that raise sits in the one
  CI step with no `|| true` — under `bash -e` it loses ALL state, not just this file.
- `html.escape(quote=True)` emitted `&#x27;` for an apostrophe — a *numeric* character
  reference the Bot API never promises to decode, and `OpenAI's …` is the commonest story
  title shape. Now escapes exactly what Telegram documents (`& < >`).
- The 4096-char limit: the first version shed message blocks by *position* and threw away
  the command while keeping the prose. It now sheds by **value** — prose, then the page
  link, then the command — and never takes a raw slice, because a cut mid-tag is its own
  400.

## Known broken / deliberately skipped

- **The two Actions secrets are not set** (`TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`).
  `gh` is not installed here and no PAT exists, so this is an owner click. Until then the
  16:55 workflow logs `↷ Telegram not configured — skipping` and posts nothing.
- **The configured chat is a private supergroup, not a broadcast channel** (`getChat` →
  `"type":"supergroup"`). `sendMessage` is identical for both, but a private group cannot
  be found, followed, or linked from a YouTube description. A public `@tooldojo` channel is
  a one-secret change, no code.
- The token was shared in plain text in a chat. Rotating it in @BotFather (`/revoke`) once
  CI is wired is cheap hygiene — it means updating `.env` and the Actions secret, nothing
  else.
- The **tool-lane** message has not been seen in Telegram yet (no tool video has published).
  Its body is rendered in `output/demo/telegram/message_tool.txt`.
- Nothing is live on the web until Pages is enabled — the page link in a tool post 404s
  until then. Same state as the PDF since v3-C.
- `output/demo/hostile/`, `plugins.rb`, `ri.md`, `rl.md` are untracked scratch in the
  working tree; deleting files is your call, so I left them.
- Everything in the previous handoff's owner list is still outstanding.

## Next session starts here

- **Phase v3-F.3 (X free tier)**: the same shape as F.2 — a second function in `notify.py`
  off the same ledger row and catalog join, ~500 posts/month on the free tier. The new work
  is OAuth 1.0a credentials in Actions secrets and a 280-character budget, where F.2's
  "shed by value, never slice" rule is exactly the right pattern.
- First command: `/boot`
- Watch out for: **anything that announces a video must run after `publishAt`, off the
  ledger** — never from `run()`'s post-upload zone, where the video is still private. And
  the standing pair: a tracked state file needs BOTH `state_merge.FILES` and the workflow
  stash list, and a secret in a URL leaks through the HTTP library's own exception text
  (`notify._redact` is the pattern).

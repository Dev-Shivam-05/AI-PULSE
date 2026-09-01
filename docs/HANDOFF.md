# HANDOFF — ToolDojo — Phase v3-F.4 (IG / FB Reels) — 2026-09-01

*Spec locked (16 decisions, approved with `go`), built, self-reviewed over the diff, and
verified against the live Graph API. **217/217 tests.** Branch `v3-phase-f` pushed.*

## Done

- **`factverse/reels.py`** — the day's FIRST rendered Short is re-uploaded as one Instagram
  Reel and one Facebook Page Reel through the official Graph API. Tool rows carry the command
  + the F.1 page link in the caption; story rows carry the title. IG and FB run independently
  — separate switch, separate state, separate `try` — so one being broken or unconfigured
  never costs the other its post.
- **It runs from `publish.yml`, NOT from the 16:55 notify workflow.** The phase's one
  architectural decision, forced by a fact rather than a preference: `output/shorts/` is
  gitignored and dies with the runner, so the MP4 exists only inside the publish job's
  workspace. Announcing a *link* can happen anywhere; re-uploading a *file* can only happen
  where the file is.
- **The 16:45 publish-slot rule does not apply**, and that was reasoned about rather than
  assumed. It exists because a link to the long-form is dead until `publishAt`. A Reel is a
  re-upload, not an announcement — so the caption carries **no YouTube URL at all** and can
  ship at 12:30 UTC with nothing dead in it.
- **Local-binary resumable upload, so nothing has to be hosted.** IG: `POST /{ig}/media`
  (`media_type=REELS`, `upload_type=resumable`) → bytes to `rupload.facebook.com` → poll the
  container to `FINISHED` → `media_publish`. FB: `video_reels` `upload_phase=start` → bytes →
  `upload_phase=finish&video_state=PUBLISHED`. One long-lived **Page** token serves both, and
  a Page token minted from a long-lived User token does not expire — the same
  nothing-may-expire requirement that chose OAuth 1.0a in F.3.
- **`state/notified_ig.json` + `state/notified_fb.json`** — two lists, each with the full
  both-halves treatment (`state_merge.FILES` + `publish.yml`'s stash loop).
- **Verified, not just compiled**: both caption bodies rendered to `output/demo/reels/` and
  read; a live call to `graph.facebook.com/v25.0/me/video_reels` with an invalid token
  returned **HTTP 400 OAuthException 190**, and a live call to
  `rupload.facebook.com/video-upload/v25.0/0` returned **HTTP 400 NotAuthorizedError** — both
  handled, both returning `False`, neither leaking the token. Both hosts of the flow are
  proven reachable and proven to refuse safely.

## Files changed

- `factverse/reels.py` — NEW: the whole surface (caption builder, `pick_entry`, IG's 4-call
  flow, FB's 3-phase flow, bounded container poll, every seam fail-soft, `main()` always 0)
- `.github/workflows/publish.yml` — the reels step (after the pipeline, above the state-save,
  `continue-on-error`), the 3 `META_*` secrets, the two new state files in the stash loop
- `factverse/state_merge.py` — `state/notified_ig.json` + `state/notified_fb.json` in `FILES`
- `config.json` / `config.example.json` — `"instagram": true`, `"facebook": true` kill switches
- `state/notified_ig.json`, `state/notified_fb.json` — NEW, seeded `[]`
- `tests/test_pipeline_logic.py` — +21 tests (196 → 217)
- `docs/spec/ai-pulse-v3f4.md` — NEW: the contract, the owner's 8-step Meta setup, the risks
- `docs/PHASES.md`, `docs/DECISIONS.md`, `docs/spec/GLOSSARY.md`, `docs/CONTENT_PLAYBOOK.md`
  (the "Instagram stays manual" line, corrected), `CLAUDE.md` (4 new traps)
- `output/demo/reels/caption_{tool,story}.txt` — the rendered bodies

## Decisions made

- **In `publish.yml`, not `notify.yml`.** The rule that generalises: *a surface that
  re-uploads a file lives where the file is.* Rejected: an artifact handoff between two
  workflows, and hosting every Short on a public GitHub Release.
- **IG and FB together, not two phases** — one Meta app, one Page, one linked IG account and
  one token serve both; splitting would make the owner do the setup twice.
- **No YouTube link in the caption** — an IG caption cannot hold a clickable link anyway, and
  including one would re-impose the 16:45 constraint for no gain.
- **The caption is built here, not taken from the LLM's `instagram_caption`** — that field
  comes from a v2-era prompt (20 hashtags, a hard-coded `Follow @{HANDLE}` that still says
  `@aipulse`) and nothing coerces it.
- **No retry, anywhere** — a retried call that may have half-succeeded is how one Short
  becomes two Reels. Tomorrow renders another one.
- **Only the LAST production-log row is ever considered** — an older row is another day's
  video whose file left with its runner.

## Two defects the self-review found (both reproduced, fixed, test-pinned)

- **The Page token was in a query string.** `graph_get` passed `access_token` in `params`,
  which requests turns into the request URL — the exact string `requests` quotes back inside
  its own `ConnectionError` text, into a public Actions log. Decision 14 said "never the query
  string" and the first implementation broke it anyway. Fixed with `Authorization: Bearer`,
  proven against the live API *before* the change: 190 ("could not be decrypted") with the
  header, 2500 ("an active access token must be used") with no token at all.
- **A server-supplied `upload_url` was ignored, and honouring it naively would have been
  worse.** Meta returns it so clients need not hard-code a host, but it is where the token
  goes. `_upload_url` now accepts it only on `https://rupload.facebook.com/`; the test
  includes `https://rupload.facebook.com.evil.test/`, which a substring check would accept.

## Known broken / deliberately skipped

- **The Meta app does not exist and the 3 Actions secrets are not set** (`META_PAGE_TOKEN`,
  `META_PAGE_ID`, `META_IG_USER_ID`) — 8 owner steps in the spec. Until then the publish step
  logs `↷ Instagram not configured — skipping` and costs nothing.
- **No live Reel has been posted** — only the refusal path is live-verified.
- **The real risk is App Review, not code.** `instagram_content_publish` is review-gated for
  publishing on behalf of accounts you do not own; publishing to your *own* account from an
  app in Development mode is the expected path, but Meta's own getting-started page 404s and
  only third-party guides say it plainly. Owner step 4 — *post one Reel by hand from Graph
  API Explorer first* — costs nothing and is the only way to find out.
- **The IG account must be Business, not Creator.** Sources disagree on Creator publishing.
- **The 14:53 retry cron can never post a Reel for a video the 12:23 run published** — the
  file is gone from that runner. That day gets no Reel. Accepted.
- **No age bound on the picked row.** F.2/F.3 refuse a row older than 36 h; F.4's gate is
  "the file is still on disk", which in CI is exact. Deliberately not adding a number the
  spec did not lock.
- The caption says `@tooldojo` (`config.json`'s `channel_handle`) — the channel rename is
  still outstanding, so that handle is not claimed yet.
- `output/demo/hostile/`, `plugins.rb`, `ri.md`, `rl.md` are still untracked scratch in the
  working tree; deleting files is your call, so I left them.

## What is left — the merge, and everything else

**Phases left to write: effectively zero to get this live.** Every v3 phase through F.4 is
built and pushed. Only `v3-D` (learning loop) is queued, and it is *blocked on data*, not on
code — it needs ~2 weeks of post-2026-08-24 analytics. `v3-B.1` is conditional on what the
first live tool runs show. Nothing else is planned.

**Branches left to merge: 1, not 3** — verified today, not assumed:

- The stack is strictly contained: `v3-phase-b` ⊂ `v3-phase-c` ⊂ `v3-phase-f`
  (`git rev-list --count` between each pair = 0). **Merging `v3-phase-f` into `main` brings
  all three.** The 3-PR sequence in `## Now` is a review convenience, not a requirement.
- `v3-phase-f` is **69 commits / 98 files** ahead of main (10,374 insertions).
- `main` has 19 commits the branch does not: all daily `state update [skip ci]` CI writes.
- **The merge is clean.** `git merge-tree --write-tree origin/main origin/v3-phase-f` exits 0
  with zero conflicts — the two sides changed *no file in common*. Re-check that command
  before merging, because every day the cron runs adds another state commit to main.

**Owner backlog, in order** (full text in `docs/PHASES.md` → `## Now`):

| # | Thing | Blocks |
|---|-------|--------|
| 0 | Stop the self-views | the whole channel (fake-engagement policy) + every v3 metric |
| 0.5 | Rename the channel to ToolDojo, claim `@tooldojo` | do it BEFORE the first tool video |
| 1 | Merge `v3-phase-f` → main (one PR, clean) | everything below |
| 1.4 | X app + 4 secrets | F.3 posting |
| 1.5 | Telegram 2 secrets | F.2 posting |
| 1.6 | Meta app + Page + Business IG + 3 secrets | F.4 posting |
| 2 | Enable GitHub Pages | F.1 pages AND every cheat-sheet link (404 until then) |
| 3 | One editorial call on `voice clon` in `UNSUITABLE_TOOL` | a legit open-TTS candidate |
| 4 | Supervised first `format=tool` dispatch | the actual pivot |
| 5 | Watch the first unattended day's log lines | confidence in C.2/C.3 |
| 6 | Record the next L2 batch | every video ships with no human take today |

Four distribution surfaces are built and **none of them can post**. That is the bottleneck —
not missing code.

## Next session starts here

- **Phase: none. The next session is the owner backlog above**, then the first supervised
  `format=tool` run. Every further phase adds code to a channel that is not yet distributing.
- First command: `/boot`
- Watch out for: **a surface that re-uploads a FILE lives where the file is** — the notify
  workflow has no workspace. And the standing set, now with a fourth: a tracked state file
  needs BOTH `state_merge.FILES` and its workflow's stash list; a secret leaks through the
  HTTP library's own exception text *and* through any URL you put it in; a fail-soft seam
  must be fail-soft all the way to the top; and a URL the **server** hands you is still a URL
  you have to check before you send a token to it.

# HANDOFF — ToolDojo — Phase v3-F.4 (IG / FB Reels) — 2026-09-01

*Spec locked (16 decisions, approved with `go`), built, self-reviewed over the diff, and
verified against the live Graph API. 217/217 tests. Branch `v3-phase-f` pushed, stacked on
`v3-phase-c` — merge PR #23 (`v3-phase-b`) first, then `v3-phase-c`, then this.*

## Done

- **`factverse/reels.py`** — the day's FIRST rendered Short is re-uploaded as one Instagram
  Reel and one Facebook Page Reel through the official Graph API. Tool rows carry the
  command + the F.1 page link in the caption; story rows carry the title. IG and FB run
  independently — separate switch, separate state, separate `try` — so one being broken or
  unconfigured never costs the other its post.
- **It runs from `publish.yml`, NOT from the 16:55 notify workflow.** This is the phase's one
  architectural decision and it was forced by a fact, not a preference: `output/shorts/` is
  gitignored and dies with the runner, so the MP4 exists only inside the publish job's
  workspace. Announcing a *link* can happen anywhere; re-uploading a *file* can only happen
  where the file is. The alternatives (an artifact handoff between two workflows, or hosting
  every Short on a public GitHub Release) both add a permanent seam to move one file that was
  already sitting in the working directory.
- **The 16:45 publish-slot rule does not apply, and that had to be reasoned about rather than
  assumed.** It exists because a link to the long-form is dead until `publishAt`. A Reel is a
  re-upload, not an announcement — so the caption carries **no YouTube URL at all** and can
  ship at 12:30 UTC with nothing dead in it.
- **Local-binary resumable upload, so nothing has to be hosted.** IG: `POST /{ig}/media`
  (`media_type=REELS`, `upload_type=resumable`) → bytes to `rupload.facebook.com` → poll the
  container to `FINISHED` → `media_publish`. FB: `video_reels` `upload_phase=start` → bytes →
  `upload_phase=finish&video_state=PUBLISHED`. One long-lived **Page** token serves both, and
  a Page token minted from a long-lived User token does not expire — the same
  nothing-may-expire requirement that chose OAuth 1.0a in F.3.
- **`state/notified_ig.json` + `state/notified_fb.json`** — two lists, each with the full
  both-halves treatment (`state_merge.FILES` + `publish.yml`'s stash loop). Four surfaces now
  repeat that pattern; sharing one list would retire a video for whichever surface had not
  posted it.
- **Verified, not just compiled**: both caption bodies rendered to `output/demo/reels/` and
  read; a real call to `graph.facebook.com/v25.0/me/video_reels` with an invalid token
  returned **HTTP 400 OAuthException 190**, and a real call to
  `rupload.facebook.com/video-upload/v25.0/0` returned **HTTP 400 NotAuthorizedError** — both
  handled, both returning False, neither leaking the token. That is both hosts of the flow
  proven reachable and proven to refuse safely.

## Files changed

- `factverse/reels.py` — NEW, the whole surface
- `.github/workflows/publish.yml` — the reels step (after the pipeline, above the state-save,
  `continue-on-error`), the 3 `META_*` secrets, the two new state files in the stash loop
- `factverse/state_merge.py` — `state/notified_ig.json` + `state/notified_fb.json` in `FILES`
- `config.json` / `config.example.json` — `"instagram": true`, `"facebook": true`
- `state/notified_ig.json`, `state/notified_fb.json` — NEW, seeded `[]`
- `tests/test_pipeline_logic.py` — +21 tests (196 → 217)
- `docs/spec/ai-pulse-v3f4.md` — NEW: the contract, the owner's 8-step Meta setup, the risks
- `docs/PHASES.md` (F.4 done, owner step 1.6, a rewritten "Next 3"), `docs/DECISIONS.md`,
  `docs/spec/GLOSSARY.md`, `docs/CONTENT_PLAYBOOK.md` (the "Instagram stays manual" line,
  corrected), `CLAUDE.md` (4 new traps)
- `output/demo/reels/caption_{tool,story}.txt` — the rendered bodies

## Decisions made (full table in the spec)

- **In publish.yml, not notify.yml** — see above. This is the first surface that is not an
  announcement, and the rule that generalises is: *a surface that re-uploads a file lives
  where the file is.*
- **IG and FB together, not split into two phases** — one Meta app, one Page, one linked IG
  account and one token serve both. Splitting would have made the owner do the setup twice.
- **No YouTube link in the caption** — an IG caption cannot hold a clickable link anyway, and
  including one would have re-imposed the 16:45 constraint for no gain.
- **The caption is built here, not taken from the LLM's `instagram_caption`** — that field
  comes from a v2-era prompt (20 hashtags, a hard-coded `Follow @{HANDLE}` that still says
  `@aipulse`) and nothing coerces it.
- **No retry, anywhere** — a retried call that may have half-succeeded is how one Short
  becomes two Reels. Tomorrow renders another one.
- **Only the LAST production-log row is ever considered** — an older row is another day's
  video whose file left with its runner.

## Two defects the self-review found (both reproduced, fixed and test-pinned)

- **The Page token was in a query string.** `graph_get` passed `access_token` in `params`,
  which requests turns into the request URL — the exact string `requests` quotes back inside
  its own `ConnectionError` text, into a public Actions log. Decision 14 said "never the query
  string" and the first implementation broke it anyway. Fixed with `Authorization: Bearer`,
  and the header was proven to work against the live API *before* the change: 190 ("could not
  be decrypted") with it, 2500 ("an active access token must be used") without any token.
- **A server-supplied `upload_url` was ignored, and honouring it naively would have been
  worse.** Meta returns it so clients need not hard-code a host, but it is where the token
  goes. `_upload_url` now accepts it only on `https://rupload.facebook.com/`; the test
  includes `https://rupload.facebook.com.evil.test/`, which a substring check would accept.

## Known broken / deliberately skipped

- **The Meta app does not exist and the 3 Actions secrets are not set**
  (`META_PAGE_TOKEN`, `META_PAGE_ID`, `META_IG_USER_ID`). 8 owner steps in the spec.
  Until then the publish step logs `↷ Instagram not configured — skipping` and costs nothing.
- **No live Reel has been posted** — only the refusal path is live-verified.
- **The real risk is App Review, not code.** `instagram_content_publish` is review-gated for
  publishing on behalf of accounts you do not own; publishing to your *own* account from an
  app in Development mode is the expected path, but Meta's own getting-started page 404s and
  only third-party guides say it plainly. **Owner step 4 is "post one Reel by hand from Graph
  API Explorer before trusting any of this"** — it costs nothing and it is the only way to
  find out.
- **The IG account must be Business, not Creator.** Sources disagree on Creator publishing.
- **The 14:53 retry cron can never post a Reel for a video the 12:23 run published** — the
  file is gone from that runner. That day gets no Reel. Accepted and documented.
- **No age bound on the picked row.** F.2/F.3 refuse a row older than 36 h; F.4's gate is
  "the file is still on disk", which in CI is exact (a fresh runner has no old Shorts). It is
  weaker only for a *local* run against an old checkout — where no `META_*` secret exists
  anyway. Deliberately not adding a number the spec did not lock.
- The caption says `@tooldojo`, which is `config.json`'s `channel_handle` — the channel
  rename (owner step 0.5) is still outstanding, so that handle is not claimed yet.
- Everything in the previous handoff's owner list is still outstanding: 2 Telegram secrets,
  4 X secrets, GitHub Pages, the branch-stack merge, the first supervised `format=tool` run,
  the channel rename, the L2 batch. See `docs/PHASES.md` → `## Now`.
- `output/demo/hostile/`, `plugins.rb`, `ri.md`, `rl.md` are still untracked scratch in the
  working tree; deleting files is your call, so I left them.

## Next session starts here

- **Not another surface.** Four are built and none can post. The highest-value next session
  is the owner list in `docs/PHASES.md` → `## Now`: merge the branch stack, enable Pages, add
  the Telegram/X/Meta secrets, rename the channel, then the first supervised `format=tool`
  dispatch. Every further phase adds code to a channel that is not yet distributing.
- After that: **v3-D (learning loop)** once ~2 weeks of post-2026-08-24 analytics exist.
- First command: `/boot`
- Watch out for: **a surface that re-uploads a FILE lives where the file is** — the notify
  workflow has no workspace. And the standing set, now with a fourth: a tracked state file
  needs BOTH `state_merge.FILES` and its workflow's stash list; a secret leaks through the
  HTTP library's own exception text *and* through any URL you put it in; a fail-soft seam
  must be fail-soft all the way to the top; and a URL the **server** hands you is still a URL
  you have to check before you send a token to it.

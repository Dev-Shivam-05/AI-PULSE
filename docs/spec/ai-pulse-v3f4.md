# Spec — v3-F.4: IG / FB Reels

Status: **locked** (16 decisions, approved with `go` on 2026-09-01) and built.
Module: `factverse/reels.py`. Runs from `.github/workflows/publish.yml`, not `notify.yml`.
Previous surfaces: `docs/spec/ai-pulse-v3f2.md` (Telegram), `docs/spec/ai-pulse-v3f3.md` (X).

## Why this phase exists

The channel's Shorts are rendered every day and used once. IG Reels and FB Reels take the
same 9:16 file, so a third and fourth distribution surface costs one upload each and no new
content. `docs/ENGINEERING_AUDIT.md` #6 already named the route: the **official Graph API**,
not the `instagrapi` path (which is disabled and is ban-bait from a datacenter IP).

**Why this one is NOT on the 16:55 notify workflow, unlike F.2/F.3.** The Shorts MP4 exists
only inside the publish job's workspace: `output/shorts/` is gitignored and the runner is
destroyed when the job ends. Announcing a *link* can happen anywhere; re-uploading a *file*
can only happen where the file is. The alternatives were an artifact handoff between two
workflows (a cross-run `run-id` lookup for the same result) or hosting every Short on a
GitHub Release (a permanent public mirror of the file). Both were rejected — see decision 1.

**Why the 16:45 publish-slot rule does not apply here.** The rule in `CLAUDE.md` exists
because the long-form is PRIVATE until `publishAt`, so a link posted at 12:23 UTC is dead for
four and a half hours. A Reel is a re-upload of the Short, not a link to the long-form, and
its caption therefore carries **no YouTube URL at all** (decision 9). Nothing in it can be
dead.

## Locked decisions

| # | Decision | Value |
|---|----------|-------|
| 1 | Where it runs | A step in `publish.yml`, `continue-on-error: true`, after the publish step and **before** "Save state back to repo". Own process: `python -m factverse.reels`. `main()` always returns 0 |
| 2 | Publish-slot rule | Does not apply — no YouTube URL in the caption, so nothing is dead at 12:30 UTC |
| 3 | Which video | The **first** rendered Short (`shorts[0]`) of the last `output/production_log.json` entry, and only when that entry's `status == "PUBLISHED"`. One Reel per platform per day |
| 4 | Scope | IG Reels **and** FB Page Reels, one module, one Meta app, one Page token |
| 5 | Auth | 3 secrets: `META_PAGE_TOKEN` (long-lived Page access token — Meta: a Page token from a long-lived User token "does not have an expiration date"), `META_PAGE_ID`, `META_IG_USER_ID`. Unset → log and exit 0 |
| 6 | Graph API version | `GRAPH = "v25.0"`, one module constant |
| 7 | Upload method | Local binary, no public hosting. IG: `POST /{ig}/media` `media_type=REELS&upload_type=resumable` → `POST rupload.facebook.com/ig-api-upload/v25.0/{container}` → poll → `POST /{ig}/media_publish`. FB: `POST /{page}/video_reels` `upload_phase=start` → `POST rupload.facebook.com/video-upload/v25.0/{video_id}` → `upload_phase=finish&video_state=PUBLISHED`. Both binary uploads carry `Authorization: OAuth <token>`, `offset: 0`, `file_size: <bytes>` |
| 8 | IG container polling | `GET /{container}?fields=status_code` every 5 s, max 24 polls (120 s). Publish only on `FINISHED`. FB is not polled — `{"success": true}` from the finish call is the answer |
| 9 | Caption | Built here, not the LLM's `instagram_caption`. `{🔧\|📰} {title}` · `{command}` (tool) · `📄 {page url}` (tool) · `Full breakdown on YouTube — @{channel_handle}` · `#ai #aitools #opensource #developer #tech` |
| 10 | Caption cap | 2200 chars (IG's limit). Shed by value: `hashtags → page → command`, then a last-resort title cut on a word boundary with `…` |
| 11 | Idempotence | Two lists — `state/notified_ig.json`, `state/notified_fb.json` — keyed on the day's `youtube_url`, written only on success, each in `state_merge.FILES` **and** `publish.yml`'s stash loop |
| 12 | Kill switches | `"instagram": true` / `"facebook": true` in both config files, read with `fv.flag` |
| 13 | Retry policy | None, on any call. A failure records nothing; tomorrow's video is the next attempt |
| 14 | Secret handling | Token in the POST body or the `Authorization` header, never the query string. Every printed exception and response body goes through `notify._redact(..., extra=(token,))`. Config and secret reads **inside** the `try` |
| 15 | Pre-flight guards | File exists, size ≤ 200 MB. `shorts.MAX_SHORT = 35 s` is inside FB's documented 3–90 s window, so duration is not re-checked |
| 16 | Evidence | +18 offline tests including the "every seam raises" test; both captions rendered to `output/demo/reels/`; one live `graph.facebook.com` call with an invalid token, handled, no token in the output |

### Implementation notes (decided during the build, inside the locked table)

- **`_post_ig` and `_post_fb` are separate entry points with separate switches, separate
  state and separate `try` blocks**, exactly like `_post_telegram` / `_post_x`. The config
  read and the secret read are INSIDE the try: `main()` has no handler of its own, and the
  F.3 self-review found that exact hole in shipped code.
- **`_redact` is imported from `notify`, not re-implemented.** One token, one door. The
  handler redacts with the token value it captured before the raise, never by calling
  `_token()` again inside the handler meant to survive that read failing.
- **The token never goes in a query string.** `graph.facebook.com` calls send
  `access_token` as a form field; `rupload.facebook.com` uses `Authorization: OAuth <token>`.
  A token in a URL leaks through `requests`' own exception text — the F.2 lesson.
- **`pick_entry` reads `production_log.json`, not `runs.jsonl`.** Only the production log
  records the Short *paths*; the ledger records counts. It is already a tracked, merged state
  file (`_merge_log`), so nothing new has to be persisted for this to work.
- **The caption ignores `shorts_meta[i]["instagram_caption"]`.** That field is written by a
  v2-era prompt in `factverse_engine.step8_meta`: 20 hashtags and a hard-coded
  `Follow @{HANDLE}`. It is raw model output with no coercion, and it is not the voice this
  channel ships now.
- **`_fit_caption` measures in characters**, not weighted chars — IG and FB count real
  characters, unlike X. The shed order and the word-boundary cut are the F.3 shape.
- **A missing Short is a normal outcome, not an error.** The 14:53 retry cron runs on a
  fresh workspace with no rendered file, so on a day the 12:23 run published, the retry
  firing logs `no Short from today's run` and exits 0.

## Out of scope (deliberately not built)

- Posting from `notify.yml`, artifact handoff between workflows, hosting the MP4 publicly.
- More than one Reel per day, Stories, carousels, image posts, `video_state=SCHEDULED`.
- Reading IG/FB insights back into the ledger — that is v3-D.
- Removing the dead `instagrapi` seam (`IG_USER` / `IG_PASS` in `config.py`,
  `auto_upload_instagram` in `config.json`). A separate cleanup row.
- Any second Short, and any lane-specific caption beyond the tool/story split.

## Owner setup (one time, ~15 minutes)

Nothing in this phase can post until these exist. Until then the step logs
`↷ Reels not configured — skipping` and costs nothing.

1. **Make the Instagram account a Business account** (Instagram app → Settings → Account
   type → Switch to professional → **Business**, not Creator). Sources disagree on whether
   Creator accounts may publish through the API; Business is the documented one.
2. **Create a Facebook Page** for the channel (or use an existing one) and **link the
   Instagram account to it** (Page → Settings → Linked accounts → Instagram).
3. **Create a Meta app**: developers.facebook.com → My Apps → Create App → type
   **Business**. Leave it in **Development** mode.
4. **Before building anything else, prove publishing works by hand.** In Graph API Explorer,
   select the app, grant `pages_show_list`, `pages_read_engagement`, `pages_manage_posts`,
   `instagram_basic`, `instagram_content_publish`, and post one Reel manually. If Meta
   demands App Review for `instagram_content_publish` on your own account, stop here and say
   so — the code is ready either way, but the account setup is not. **This is the phase's
   one real risk and it costs nothing to test first.**
5. **Get the long-lived Page token.** In Graph API Explorer take the User token, then
   `GET /oauth/access_token?grant_type=fb_exchange_token&client_id=<app id>&client_secret=<app secret>&fb_exchange_token=<short user token>`
   → a ~60-day User token. Then `GET /me/accounts` with THAT token → the Page's
   `access_token` field is the long-lived Page token, which does not expire.
6. **Get the two ids.** `GET /me/accounts?fields=id,name,instagram_business_account` →
   the Page's `id` is `META_PAGE_ID`, and `instagram_business_account.id` is
   `META_IG_USER_ID`. If `instagram_business_account` is absent, step 1 or 2 is incomplete.
7. **Add the three repository secrets**: Settings → Secrets and variables → Actions → New
   repository secret, three times — `META_PAGE_TOKEN`, `META_PAGE_ID`, `META_IG_USER_ID`.
8. Verify on the next publish run: the log shows `📸 Instagram: posted` and
   `📘 Facebook: posted`.

## Acceptance criteria

- [x] `py -3 -m pytest tests/ -q` → 214/214.
- [x] With all three env vars unset, `python -m factverse.reels` prints
      `↷ Instagram not configured — skipping` / `↷ Facebook not configured — skipping`
      and exits 0.
- [x] With `"instagram": false`, the IG path is a no-op and the FB path still runs.
- [x] A test that stubs every seam name in the module to raise leaves `main()` returning 0.
- [x] `output/demo/reels/caption_tool.txt` and `caption_story.txt` exist, are ≤ 2200 chars
      and contain no `youtube.com` URL.
- [x] One live POST to `https://graph.facebook.com/v25.0/…` with an invalid token returns a
      non-2xx, is handled, returns `False`, and the printed line contains `***` and not the
      token.
- [x] `state/notified_ig.json` and `state/notified_fb.json` are in `state_merge.FILES` AND
      in `publish.yml`'s stash loop (asserted by a test that reads both files).

## Risks

- **App Review.** `instagram_content_publish` is review-gated for publishing on behalf of
  accounts you do not own. Publishing to your *own* account from an app in Development mode
  with the owner holding a role is the expected path, but Meta's own getting-started page
  404s and only third-party guides state it plainly. Owner step 4 tests it before anything
  depends on it.
- **Business, not Creator.** Sources disagree on Creator-account publishing. Business is the
  safe pick.
- **The 14:53 retry cron can never post a Reel for a video the 12:23 run published** — the
  file is gone from that runner. That day gets no Reel. Accepted.
- `docs/CONTENT_PLAYBOOK.md` used to say "Instagram stays manual (auto-posting from
  datacenter IPs = ban risk)". That line was about the `instagrapi` path and has been
  updated: the official Graph API is a first-party, authenticated, rate-limited surface, and
  it is what `ENGINEERING_AUDIT.md` #6 asked for.

## Still outstanding (owner)

The Meta app, the Facebook Page, the Business Instagram account and the three Actions
secrets. Eight steps above.

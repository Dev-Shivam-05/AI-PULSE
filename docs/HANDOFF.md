# HANDOFF — ToolDojo — Phase v3-F.3 (the X post) — 2026-09-01

*Spec locked (14 decisions, approved with `go`), built, self-reviewed over the diff, and
verified against the live API. 196/196 tests. Branch `v3-phase-f` pushed, stacked on
`v3-phase-c` — merge PR #23 (`v3-phase-b`) first, then `v3-phase-c`, then this.*

## Done

- **A second announcement surface inside `factverse/notify.py`**, driven from the same
  `main()` and the same 16:55 UTC workflow as v3-F.2: the newest eligible `PUBLISHED`
  ledger row becomes one X post. Tool rows carry title + command + the F.1 page link +
  the video; story rows carry title + video. Telegram and X run independently — separate
  switch, separate secrets, separate state — so one being broken or unconfigured never
  costs the other its post.
- **OAuth 1.0a user context, hand-rolled on the stdlib** (`_pct`, `oauth_base_string`,
  `oauth_signature`, `oauth_header`). Nothing to `pip install` in the notify job and
  nothing that expires in an unattended one — the OAuth 2.0 alternative would need a
  rotated refresh token written back into a repository secret every two hours.
- **`weighted_len()`** — X's limit is 280 **weighted** chars, not 280 characters: a URL
  costs 23 whatever its length, every emoji and CJK char costs 2. `len()` would have
  shipped posts the API refuses with "Text is too long".
- **Shed by value, never slice** — the page link goes first, then the command; the title
  is cut only when nothing optional is left, and that cut is safe here because an X post
  is plain text (it was not safe in the Telegram HTML body).
- **`state/notified_x.json`** is its OWN list with the full both-halves treatment
  (`state_merge.FILES` + `publish.yml`'s stash loop + `notify.yml`'s stash/save). One
  shared list would have marked a video done for X the moment Telegram took it.
- **Verified, not just compiled**: the tool / story / overflow post bodies were rendered
  to `output/demo/x/` and read; a real call to `https://api.x.com/2/tweets` with
  deliberately invalid credentials returned **HTTP 401**, was handled, returned `False`
  and leaked no secret. Signature *correctness* is proven separately by two published
  known-answer vectors (RFC 5849 §3.4.1.1's base string; Twitter's own worked example
  including its HMAC `hCtSmYh+iHYCEqBWrE7C7hYmtUk=`) — a malformed header would 401
  identically, so the live call proves reachability and refusal handling, nothing more.

## Files changed

- `factverse/notify.py` — the whole F.3 surface: `x_enabled`, `_x_secrets`, the four
  OAuth functions, `weighted_len`, `_fit_title`, `format_post`, `send_x`, `_post_x`;
  `_redact` grew an `extra` argument; `main()` split into `_post_telegram` + `_post_x`
- `.github/workflows/notify.yml` — renamed "ToolDojo — announce", the four `X_*` secrets
  wired, `state/notified_x.json` added to the stash/add loop
- `.github/workflows/publish.yml` — `state/notified_x.json` in the stash list
- `factverse/state_merge.py` — `state/notified_x.json` in `FILES`
- `config.json` / `config.example.json` — `"twitter": true` (the kill switch)
- `state/notified_x.json` — NEW, seeded `[]`
- `tests/test_pipeline_logic.py` — +16 tests (180 → 196); the three existing `main()`
  tests gained a `_no_x()` guard, because `config.py` loads `.env` into `os.environ` and
  a machine with real credentials would otherwise post for real from the test suite
- `docs/spec/ai-pulse-v3f3.md` — NEW: the contract, the owner's 6-step X app setup,
  the acceptance evidence
- `docs/PHASES.md` (F.3 done, owner step 1.4, Next 3 = F.4), `docs/DECISIONS.md`,
  `docs/spec/GLOSSARY.md`, `CLAUDE.md` (3 new traps)
- `output/demo/x/post_{tool,story,overflow}.txt` — the rendered bodies

## Decisions made (full table in the spec)

- **OAuth 1.0a, not 2.0** — it is the only X auth with nothing that expires, which is the
  whole requirement for an unattended job.
- **Hand-rolled, not `requests-oauthlib`** — `notify.yml` installs only `requests`, and a
  pinned known-answer vector proves the maths offline; a library proves nothing until it
  hits the network. This is only defensible *because* the vectors are pinned.
- **No retry on failure** — X answers a repeated post with 403 duplicate-content, so
  retrying a call that may have half-succeeded is how one video becomes two posts.
- **All four lanes post**, as in F.2: the ledger has no description, so a story post is
  title + video, and skipping stories would leave the account dead six days a week.
- **Two idempotence lists, not one** — see above; this generalises to every future surface.
- No hashtags, no media, no threads (the account is new; nothing to be clever with yet).

## Three defects the self-review found (all reproduced, fixed and test-pinned)

- **`enabled()` / `_x_secrets()` sat OUTSIDE the `try`**, and `main()` has no handler of
  its own — a raise there would have failed the workflow the module exists to keep green.
  `_post_telegram` had the same shape, so this was a live F.2 bug too. Found by the test
  that stubs *every* seam name to raise; a happy-path test never would.
- **`_fit_title` accumulated per character while `weighted_len` charges a URL 23** — so a
  title carrying a *short* URL measured more as a whole than as the sum of its characters.
  A `"https://a.io " * 40` title produced a **486**-weighted post: over the cap, a 403, a
  silent no-post day. It now shrinks against the real measurement.
- **`send_x` unpacked its credential tuple before any guard**, so a malformed set raised
  out of a seam documented as fail-soft. A wrong shape is now "unconfigured".

## Known broken / deliberately skipped

- **The X app does not exist and the 4 Actions secrets are not set**
  (`X_API_KEY`, `X_API_SECRET`, `X_ACCESS_TOKEN`, `X_ACCESS_SECRET`). `gh` is not
  installed here and no PAT exists, so this is an owner click — 6 steps in the spec.
  Until then the 16:55 workflow logs `↷ X not configured — skipping` and costs nothing.
- **No live X post has been made** — it needs the app. Only the 401 refusal path is
  live-verified. The story-lane body is what will ship first.
- **Set App permissions = Read and write BEFORE generating the access token.** A token
  minted while the app was Read-only stays read-only and posting returns 403
  `oauth1-permissions`, which is a confusing failure to debug from a CI log.
- `_URL_RE` is deliberately more permissive than X's own URL extractor. It can only
  under-count a scheme-like token inside a `title`, and a title comes from YouTube capped
  at 100 chars — far below where the 280 budget bites. Accepted residual, in the spec.
- Everything in the previous handoff's owner list is still outstanding: the 2 Telegram
  secrets, GitHub Pages, the branch-stack merge, the first supervised `format=tool` run,
  the channel rename, the L2 batch. See `docs/PHASES.md` → `## Now`.
- `output/demo/hostile/`, `plugins.rb`, `ri.md`, `rl.md` are still untracked scratch in
  the working tree; deleting files is your call, so I left them.

## Next session starts here

- **Phase v3-F.4 (IG / FB Reels)**: the existing Shorts re-used as-is via the Graph API.
  Same place in the pipeline as F.2/F.3 — off the ledger, after the publish slot — but
  the first surface that uploads a FILE rather than posting text, so the new work is the
  Graph API's two-step container/publish flow and a Business/Creator account link.
- First command: `/boot`
- Watch out for: **anything that announces a video must run after `publishAt`, off the
  ledger** — never from `run()`'s post-upload zone, where the video is still private. And
  the standing pair, now with a third: a tracked state file needs BOTH `state_merge.FILES`
  and every workflow's stash list; a secret leaks through the HTTP library's own exception
  text (`notify._redact`); and a fail-soft seam must be fail-soft **all the way to the
  top**, config and secret reads included, because `main()` has no handler.

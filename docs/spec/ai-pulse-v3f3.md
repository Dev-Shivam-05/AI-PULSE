# Spec — v3-F.3: the X (Twitter) post

Status: **locked 2026-09-01** (owner approved the table below with `go`, no changes).
Branch: `v3-phase-f` (stacked on `v3-phase-c`). Predecessor spec:
`docs/spec/ai-pulse-v3f2.md` (Telegram — this phase reuses its row selection, its
catalog join and its redaction).

## Why this phase exists

v3-F.2 gave the channel one owned distribution surface. X's free tier gives a second
one at the same price: ~500 posts a month against our ~31 (one video a day), no review,
no approval queue beyond creating the app. The work is not the posting — it is OAuth
1.0a and a 280-character budget that is not measured in characters.

**The timing constraint is inherited, not re-derived.** `eng.yt_upload` uploads the
long-form **private with `publishAt`** = `longform_slot_utc` (16:45 UTC) while the
pipeline runs at 12:23 UTC. Anything that ANNOUNCES a video therefore runs off the
ledger after that slot — never from `run()`'s post-upload zone. F.3 rides the workflow
F.2 already built for exactly this reason.

## Locked decisions

| # | Ambiguity | Locked value | Why this default |
|---|---|---|---|
| 1 | Where the code lives | A second surface **inside `factverse/notify.py`** (`x_enabled`, `_x_secrets`, `weighted_len`, `format_post`, `send_x`, `_post_x`), driven from the same `main()`. No new module, no new workflow | v3-F.2 #1 locked this in writing: "F.3 becomes a second function in the same module, not a second design". `pick_row`, `_when`, `catalog_entry` and `_redact` are all reused verbatim |
| 2 | When it posts | The **same** `.github/workflows/notify.yml` run — 16:55 UTC + `workflow_dispatch`. Telegram first, then X, each independent: one failing never blocks the other | Same reason as F.2 #2: the long-form is PRIVATE until 16:45 UTC. A second cron would be a second literal to keep in sync with `longform_slot_utc` |
| 3 | Auth | **OAuth 1.0a user context**, 4 Actions secrets: `X_API_KEY`, `X_API_SECRET`, `X_ACCESS_TOKEN`, `X_ACCESS_SECRET`. Any one missing → `↷ X not configured — skipping`, exit 0 | OAuth 1.0a is the only X auth with no refresh-token dance — nothing expires, so an unattended job never has to write a rotated credential back into a repository secret. OAuth 2.0 PKCE would need exactly that, every two hours |
| 4 | Signing implementation | **Hand-rolled, stdlib only** (`hmac`/`hashlib`/`base64`/`urllib.parse`), with **published known-answer vectors pinned in tests**. No `requests-oauthlib` | `notify.yml` installs only `requests`; a transitive `oauthlib` in an unattended job is a new failure surface. A pinned vector proves correctness offline — a library proves nothing until it hits the network |
| 5 | Endpoint + success | `POST https://api.x.com/2/tweets`, JSON `{"text": …}`, `timeout=20`. Success = HTTP **200 or 201** *and* a non-empty `data.id`. Anything else logs and returns `False`. **No retry** | Creation returns 201. F.2 #9's rule: never announce a success the API refused. No retry because X answers a repeated post with 403 duplicate-content — retrying a call that may have half-succeeded is how one video becomes two posts |
| 6 | Post text — tool row | `🔧 {title}` / blank / `{command}` / blank / `📄 {page_url}` / `▶ {video_url}` — plain text, no markup, no hashtags | Same "the command is the product" order as the Telegram body and the page. X has no markup, so nothing to escape and no entity to cut in half |
| 7 | Post text — story row | `📰 {title}` / blank / `▶ {video_url}` | Same as F.2 #4: the ledger carries no description, so a story post has nothing else truthful to say — and skipping story days would leave the account dead six days a week |
| 8 | The 280 limit | `weighted_len()` per X's documented counting: every URL counts **23** regardless of length; a code point in `0–4351`, `8192–8205`, `8208–8210`, `8214–8238`, `8240–8286`, `8304–8348`, `8352–8383` counts 1, **everything else 2** (emoji, CJK) | X's limit is 280 *weighted* chars, not 280 characters. Counting with `len()` ships posts the API refuses with "Text is too long" — and the two lane emoji are 2 apiece before a single word is written |
| 9 | What gets shed at 280 | Shed whole blocks **by value**, never by slicing: the page link first, then the command. Title + video link always survive. **Last resort only**, if title + link alone still exceed 280: truncate the title at a word boundary + `…` | F.2's shed-by-value rule. The one difference: an X post is plain text, so a title slice is safe here — it was not safe in the Telegram HTML body, where a cut mid-tag is its own 400 |
| 10 | Idempotence state | **`state/notified_x.json`** — a separate list of video URLs, newest 500, identical semantics to `notified.json`. Both-halves treatment: `state_merge.FILES` **and** `publish.yml`'s stash loop **and** `notify.yml`'s stash/save. Recorded only after a successful post | A shared list would mark a video done because *Telegram* took it, and X would then never post it at all. Two lists, two independent retries |
| 11 | Kill switch | `config.json` `"twitter": true`, read with `fv.flag` (never `fv.setting`) | `fv.setting` overrides from the env var of the same UPPER name — a key called `"x"` would read `$X`, far too generic a name to bet an unattended job on. And `bool("false")` is `True`, which is why `fv.flag` and not `fv.setting` |
| 12 | Secret leaking into a public log | `_redact` grows an `extra` argument; the X path passes **all four** values, longest first. Applied to every printed string incl. `str(exception)` | The OAuth signature rides in an `Authorization` header, not the URL — but a proxy error can echo a header back, and a fork's log is public. Same discipline as F.2 #8. Longest-first matters: a short secret that is a substring of a longer one would otherwise cut the long one in half and leak the remainder |
| 13 | Log lines | `🐦 X: posted — <title>` / `↷ X: nothing new to post` / `↷ X not configured — skipping` / `↷ X: disabled by config (twitter=false)` / `⚠️ x failed — HTTP {code} {body[:120]}`. `main()` always exits 0 | The same worked / no-op / failed vocabulary as every other seam in the repo |
| 14 | Free-tier budget | No throttle code. 1 post/day ≈ 31/month against a 500/month write cap; the cap is a comment in `notify.yml` | A quota counter for 6% utilisation is a state file that can only be wrong |

### Implementation notes (decided during the build, inside the locked table)

- **The known-answer vectors, decided at #4's first test.** Two are pinned, because
  neither alone is enough:
  - **RFC 5849 §3.4.1.1** — the base string only. It is the vector with a repeated
    parameter name, a blank value, an `@` in a key and an already-percent-encoded
    value, which is where hand-rolled OAuth actually goes wrong. The test uses errata
    2550's corrected `a2=r b` (the printed RFC shows `a%20b` in the result while its
    own request says `r b`).
  - **Twitter's own "Creating a signature" example** — base string *and* the resulting
    HMAC (`hCtSmYh+iHYCEqBWrE7C7hYmtUk=`). This is the half RFC 5849 cannot give:
    the `oauth_signature` printed in RFC 5849 §3.1 is a fabricated placeholder, not a
    real HMAC of anything.
- **The JSON body is not signed.** OAuth 1.0a folds a request body into the base
  string only when it is `application/x-www-form-urlencoded`; X's v2 endpoints take
  JSON, so the signature covers method + URL + the `oauth_*` parameters. This is why
  `oauth_header` takes no body argument.
- **`…` is U+2026, inside the 8214–8238 weight-1 range**, so the last-resort title cut
  reserves exactly 1 weighted char for it.
- **A fail-soft seam has to be fail-soft all the way to the top.** The "every seam
  raises" test caught `x_enabled()` / `_x_secrets()` sitting *outside* the `try` — and
  `main()` has no handler of its own, so a raise there would have failed the workflow.
  `_post_telegram` had the same shape (`enabled()` / `_token()`) and was fixed with it;
  its handler now redacts with the token it captured, not by calling `_token()` again,
  because the read that raised must not be re-run inside the handler meant to survive it.
- **A row is marked notified only after a successful post**, per surface. A failed post
  retries on the next firing and otherwise ages out of the 36 h window.

## Out of scope (deliberately not built)

- IG/FB Reels (board row F.4), a newsletter, or any third surface.
- Threads, replies, quote-posts, polls, hashtags, @-mentions.
- Media upload — X media needs the v1.1 upload endpoints and a different auth path.
- Reading anything from X (mentions, impressions, follower counts). Analytics is v3-D.
- Posting Shorts, backfilling past videos, editing or deleting a sent post.
- A ledger column for the post (`state/notified_x.json` + the log line is the record).
- Creating the X app or the 4 Actions secrets — owner clicks, below.

## Owner setup (one time, ~10 minutes)

1. https://developer.x.com → sign up for the **Free** tier with the ToolDojo X account
   (create `@tooldojo` on X first if it does not exist — it was verified free on
   2026-08-24). Free tier allows ~500 posts/month, which is 16× what we need.
2. Create a **Project** and inside it an **App**.
3. App → **User authentication settings** → set **App permissions = Read and write**.
   *Do this BEFORE step 4* — an access token minted while the app was Read-only stays
   read-only, and posting returns 403 `oauth1-permissions`. Type of App: "Web App,
   Automated App or Bot"; the callback/website URLs are required fields but unused by
   us — the tool page host (`https://dev-shivam-05.github.io/AI-PULSE/`) is fine.
4. App → **Keys and tokens** → copy the **API Key** and **API Key Secret**, then
   **Generate** the **Access Token and Secret** (regenerate them if step 3 came after).
5. GitHub → Settings → Secrets and variables → Actions → **New repository secret**,
   four times:
   `X_API_KEY`, `X_API_SECRET`, `X_ACCESS_TOKEN`, `X_ACCESS_SECRET`.
6. Actions tab → **"ToolDojo — announce"** → Run workflow. Expect `🐦 X: posted` in the
   log and the post on the account; `↷ X: nothing new to post` means the ledger has no
   video published in the last 36 h, which is correct on a day with no run.

Until step 5 the workflow logs `↷ X not configured — skipping` and costs nothing.

## Acceptance criteria

- [x] `py -3 -m pytest tests/ -q` passes with ≥12 new tests (180 → **196**, +16)
- [x] `oauth_base_string` reproduces RFC 5849 §3.4.1.1's base string byte for byte, and
      `oauth_base_string` + `oauth_signature` reproduce Twitter's published example
      including the HMAC `hCtSmYh+iHYCEqBWrE7C7hYmtUk=`
- [x] `format_post` on a tool row + its catalog entry returns the exact 6-line template
      in #6; on a story row the 3-line template in #7; a section with no truthful value
      is omitted, not left blank
- [x] A `javascript:` `youtube_url` yields `""`; a `javascript:` `page` yields a post
      with the 📄 line absent, not linked
- [x] `weighted_len("https://x.test/"+"a"*200) == 23`; `weighted_len("🔧") == 2`;
      `weighted_len("日本") == 4`; `weighted_len("…") == 1`
- [x] Shed order proven in four steps: under the limit nothing is shed; then the page
      link goes; then the command; then the title is cut on a word boundary with one
      `…`. Every case ≤ 280 weighted and still ends with the video URL — including a
      600-char no-spaces title, a 400-char CJK title and a 300-emoji title
- [x] With `notify.requests.post` stubbed: one call to `https://api.x.com/2/tweets`,
      `Authorization` starting `OAuth `, `Content-Type: application/json`, body
      `{"text": …}`, `timeout=20`; a 403, a 401, a 200 with no `data.id`, a 201 with
      `errors`, a 201 with a non-dict `data`, and unparsable JSON are each `False` with
      **exactly one** HTTP call; a missing credential makes **zero** calls
- [x] A stubbed `post` raising with all four secret values inside the message prints
      none of them; `_redact` handles a short secret that is a prefix of a long one
- [x] Telegram raising at `enabled`, `_token`, `format_message` or `send` does not stop
      X posting; `send_x` raising does not stop Telegram; both `main()` calls return 0
- [x] The two lists are independent: after Telegram takes a URL, the same URL is still
      eligible for X, and X posts it while Telegram no-ops
- [x] `state_merge.merge_file("state/notified_x.json", …)` unions without duplicates and
      survives a scalar/dict/null body; the path is in `state_merge.FILES`,
      `publish.yml`'s stash loop and `notify.yml`; all four secrets are wired in
      `notify.yml`; `"twitter"` is in both config files
- [x] With any of the 4 secrets unset, and with `twitter: false`, zero HTTP calls and
      exit 0
- [x] The tool, story and overflow post bodies rendered to `output/demo/x/` and read
- [x] **Live**: a real call to `https://api.x.com/2/tweets` with deliberately invalid
      OAuth 1.0a credentials returned **HTTP 401 Unauthorized**, was handled, returned
      `False`, and printed no secret. (Reachability + refusal handling. Signature
      *correctness* is proven by the known-answer vectors above, not by this call — a
      malformed header would 401 identically.)

## Still outstanding (owner)

- The 4 Actions secrets and the X app (steps 1–5 above). `gh` is not installed on this
  machine and no PAT exists, so this is a click.
- The first **live post** — it needs the app. The story-lane body is the one that will
  ship first; the tool-lane body is rendered in `output/demo/x/post_tool.txt`.

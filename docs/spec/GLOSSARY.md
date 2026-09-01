# Project glossary — fixed meanings (do not redefine in later sessions)

- **tool format** — the v3 hands-on video lane: a free AI tool/repo/model the viewer can use
  today. Config flag `tool_format` (true since Phase B; env `TOOL_FORMAT` overrides).
- **screencap** — `factverse/screencap.py`, the tool-video visual provider: a headless-Chromium
  recording of the tool's real page, trimmed and cut into per-scene chunks (same
  `list[list[path]]` shape as `step3_download`). Returns None on any failure → stock fallback.
- **code card** — the deliverable rendered as a terminal-style still (Pygments bash, JetBrains
  Mono 22px) and injected as the lead clip of the final scene + first post-hook install scene.
- **tool thumbnail** — `thumbnail.make_tool_thumb`: page screenshot + 2–4 word overlay, Inter
  Black, white on #DC2626, red baseline. Used whenever a screenshot exists; else the old chain.
- **cheat sheet** — the v3-C 1-page A4 PDF written per tool video to `docs/tools/<date>-<slug>.pdf`
  and served by GitHub Pages at `<deliverable_base_url>/tools/<file>`. Built by
  `factverse/deliverable.py`; the LLM-extracted sections fall back to title + deliverable. Never absent.
- **promo block** — config `promo_block`: the affiliate-ready description slot. Empty = omitted;
  non-empty = inserted verbatim after the cheat-sheet line (tool) / after paragraph 1 (others).
- **deliverable block** — the description lines `🔧 Try it yourself:` + command + source +
  `📄 Free 1-page cheat sheet: <url>`, placed after paragraph 1 (spec v3-C decision 7).
  Since v3-F.1 that `<url>` is the **tool page**, not the PDF.
- **tool page** — the v3-F.1 HTML page written per tool video to `docs/tools/<date>-<slug>.html`
  (same stem as its PDF) by `factverse/site.py`: command + Copy button, what/uses/skip_if, the
  video embed, the PDF as a download. What the description and pinned comment link.
- **catalog** — `state/tools_index.json`, the list of tool-page entries. The single source of
  truth for the site: `docs/index.html`, `docs/sitemap.xml` and every tool page are regenerated
  from it (`python -m factverse.site`) after `state_merge` on every CI run.
- **safe_name** — `deliverable.safe_name()`: basenames on BOTH separators and filters the
  charset. Every artifact file name derived from model output must pass through it.
- **_CARRY** — the top-level script keys every LLM rewrite pass must copy across
  (`format, grounding, roundup_items, signal_title, synthesis_claim, filter_segment,
  hook_pattern, deliverable, cheat_sheet`). A pass that forgets one silently changes the video.
- **deliverable** — required field of a tool script: `{"kind": "command|repo|steps", "text", "url"}`.
  Spoken in the final scene, printed in the description as "🔧 Try it yourself". No deliverable = no video.
- **MAX_WORDS** — 900. The anti-padding cap enforced by `enforce_max_length` (cut, never pad).
- **word floor** — 600–620 sanity floor (`MIN_WORDS`), NOT a target. The old 850–1000 floors are
  banned; they were the root cause of the 0:38 average view duration.
- **utility lane** — decide_format's default when no story scores ≥ 8/10: tool if a tool signal
  exists (and flag on), else evergreen.
- **blocked-day fallback** — a FACTCHECK/ADVICE/POLICY block on an automatic run re-runs the day
  as forced evergreen. Forced runs (`force_format` set) still fail honestly with no fallback.
- **notified state** - `state/notified.json`, the list of YouTube URLs already announced on
  Telegram. Written only after a successful send; in `state_merge.FILES` and both workflows'
  stash lists, so `checkout -B main origin/main` cannot make the bot repeat itself.
- **announce window** - the 36 hours after `publish_at` in which `notify.pick_row` will still
  post a video. Older rows age out, so enabling the bot never announces the back catalogue.
- **weighted length** - `notify.weighted_len()`: X's own character count, which is what its
  280 limit is measured in. A URL is 23 regardless of length; a code point outside X's
  weight-1 ranges (every emoji, every CJK character) is 2; everything else is 1.
- **shed by value** - the rule both announcement surfaces use for a hard size limit: drop
  whole optional blocks in order of what the message exists to deliver (prose, then the page
  link, then the command), never take a raw slice. The X post's last-resort title cut is the
  single exception, and only because a plain-text post has no tag or entity to cut in half.
- **notified state** - `state/notified.json` (Telegram) and `state/notified_x.json` (X): the
  YouTube URLs each surface has already announced. Separate files on purpose - one shared
  list would retire a video for the surface that had not posted it yet.
- **Reel** - `factverse/reels.py`: the day's FIRST rendered Short, re-uploaded as one
  Instagram Reel and one Facebook Page Reel. Not an announcement — it carries no YouTube link
  — which is why it may run at 12:30 UTC while the long-form is still private.
- **resumable upload** - Meta's two-host pattern, and the reason Reels need no public file
  host: the JSON call to `graph.facebook.com` creates a container (IG) or a video id (FB), and
  the bytes then go to `rupload.facebook.com` with `Authorization: OAuth`, `offset` and
  `file_size` headers. `reels._upload_url` accepts the server's own upload URL only on that
  host.
- **container status** - the IG-only wait: `GET /{container}?fields=status_code` until
  `FINISHED`, bounded by 24 polls AND a 120-second monotonic deadline. Publishing a container
  that is not FINISHED is an API error. Facebook has no equivalent — its `upload_phase=finish`
  answer is the answer.
- **surface** - one place a video is distributed to, each with its own kill switch, its own
  secrets, its own `notified` list and its own `try` block: Telegram (F.2), X (F.3),
  Instagram and Facebook (F.4). Four now, and every new one repeats the same three files:
  a config flag, an entry in `state_merge.FILES`, and an entry in its workflow's stash list.

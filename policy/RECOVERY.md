# AI Pulse — Recovery Runbook

*For future-you at 2am. Each procedure is self-contained.*

## 1. YouTube token died (runs red with "token invalid/expired")
1. On the laptop, from the project root:
   `.\.venv\Scripts\python scripts\factverse_engine.py auth`
2. Sign in with the channel account → Advanced → continue → allow all permissions.
3. Update the secret:
   `gh secret set YT_TOKEN_B64 --repo Dev-Shivam-05/AI-PULSE --body ([Convert]::ToBase64String([IO.File]::ReadAllBytes("youtube_token.pickle")))`
4. Re-run the workflow from the Actions tab. Done.

## 2. A key rotated / dead (Gemini, Pexels)
1. Get a new key (aistudio.google.com/apikey · pexels.com/api).
2. Update local `.env` AND the matching GitHub secret (`gh secret set NAME`).

## 3. Manual publish (pipeline down, video rendered)
1. `output/videos/` has the master; `output/production_log.json` has title/description/tags.
2. Upload via studio.youtube.com → schedule to the fixed slot → add the thumbnail from
   `output/thumbnails/` → paste description (includes chapters + sources).

## 4. Cron stopped firing
- Actions tab → "AI Pulse — Auto Publish" → if disabled, click Enable.
- The workflow also re-enables itself on every run; check the last run's logs.

## 5. State files corrupted / diverged
- Every state file is in git: `git log -- state/ used_topics.json` and revert the
  bad commit. The union-merge step reconciles the rest on the next run.

## 6. Laptop lost — full rebuild from the repo
1. Clone the repo; run `setup.ps1`; copy `.env` values from the password manager.
2. Re-auth YouTube (procedure 1). Kokoro/whisper models re-download automatically.
3. Voice samples and L2 audio: restore `l2_store/` from the repo (committed) and
   personal samples from backup.

## 7. Account security (do once, verify quarterly)
- Channel on a Brand Account with a second manager account.
- All secrets in the password manager with emergency access configured.
- 2FA backup codes stored offline.
- Quarterly: actually perform procedure 1 end-to-end as a drill.

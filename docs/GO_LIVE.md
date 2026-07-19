# AI Pulse — Go-Live Guide (complete, step by step)

This walks through every account, click, and command needed to take the pipeline
from this repository to a channel that publishes by itself every day. Total
hands-on time: about 45 minutes, one time.

---

## Part 1 — The YouTube channel

### 1.1 Sign in
1. Open **youtube.com** in a browser and sign in with the Google account that will
   own the channel (the dedicated AI Pulse account — keep the channel separate
   from personal accounts).

### 1.2 Create the channel
1. Click your avatar (top-right) → **"Create a channel"** (if you already created
   one earlier, skip to 1.3).
2. When asked for a name, use the channel's brand name (e.g. **AI Pulse**), not
   your personal name. This creates the channel identity viewers see.
3. Pick the handle (e.g. **@aipulse** or the closest available). The handle goes
   into `config.json` → `channel_handle`.

### 1.3 Phone-verify the channel (required)
1. Go to **youtube.com/verify** while signed in.
2. Choose your country, pick **"Text me the verification code"**, enter your
   mobile number, enter the 6-digit code.
3. Why this matters: an unverified channel **cannot upload custom thumbnails**
   (our biggest click-through lever), cannot upload videos longer than 15
   minutes, and cannot live stream. Verification exists to raise the cost of
   spam accounts. One phone number can verify at most 2 channels per year.

### 1.4 Channel appearance (YouTube Studio)
1. Go to **studio.youtube.com** → left sidebar → **Customization**.
2. **Branding tab**:
   - *Picture*: upload `assets/logo_icon_512.png`.
   - *Banner image*: upload `assets/banner_youtube.png` (already sized 2560×1440
     with all content in the safe area — check the TV/desktop/mobile preview).
   - *Video watermark*: upload `assets/logo_icon.png`, display time **"Entire
     video"** (adds a subscribe hotspot on every video).
3. **Basic info tab**: paste a channel description (first 2 lines matter most —
   they show in search), add links.
4. Left sidebar → **Settings → Channel → Advanced settings**: confirm
   **"No, set this channel as not made for kids"**.
5. Left sidebar → **Settings → Upload defaults**: leave everything default — the
   pipeline sets metadata per-video via the API.

---

## Part 2 — Google Cloud project + YouTube Data API

Why: uploading by script requires an API "project" that owns credentials, and
your one-time permission grant (OAuth) that lets the pipeline act on the channel.

### 2.1 Create the project
1. Open **console.cloud.google.com** signed in with the SAME account as the channel.
2. First visit: accept the terms screen.
3. Top bar → project dropdown (says "Select a project") → **"NEW PROJECT"**.
4. Project name: `ai-pulse` (anything works). Organization: leave "No organization".
5. Click **CREATE**, wait a few seconds, then make sure the top-bar dropdown now
   shows `ai-pulse` (click it and select the project if not).

### 2.2 Enable the APIs
1. Left menu (☰) → **"APIs & Services"** → **"Library"**.
2. Search **"YouTube Data API v3"** → open it → click **ENABLE**.
3. Back to Library, search **"YouTube Analytics API"** → open → **ENABLE**
   (powers the nightly performance snapshots the learning loop uses).

### 2.3 OAuth consent screen — and why "publish" matters
1. Left menu → **APIs & Services** → **"OAuth consent screen"**.
2. If asked for user type, choose **External** (Internal is only for Workspace
   organizations). Click **CREATE**.
3. Fill only the required fields:
   - App name: `AI Pulse Publisher`
   - User support email: your address (pick from dropdown)
   - Developer contact email: your address
   - Leave logo and domains EMPTY (adding a logo can trigger a review process).
4. Click **SAVE AND CONTINUE** through the Scopes and (if shown) Test users
   pages — nothing needs to be added on them.
5. Back on the consent screen summary: find the **"Publishing status"** section
   and click **"PUBLISH APP"**, then **CONFIRM**.
   - ⚠️ **This is the single most important click in this guide.** In "Testing"
     status, Google expires refresh tokens after **7 days** — the channel would
     silently stop publishing a week after launch. "In production" tokens
     persist indefinitely.
   - You may see a note about "verification". **Ignore it — do not submit for
     verification.** Unverified production apps are capped at 100 users; this
     app has exactly one user (you). The only effect is a warning screen during
     your own one-time consent, which you can click through.

### 2.4 Create the OAuth client (credentials)
1. Left menu → **APIs & Services** → **"Credentials"**.
2. **"+ CREATE CREDENTIALS"** (top) → **"OAuth client ID"**.
3. Application type: **Desktop app** (NOT "Web application" — the local auth
   flow needs the desktop type). Name: `ai-pulse-desktop`.
4. Click **CREATE** → in the popup click **DOWNLOAD JSON**.
5. Rename the downloaded file to exactly **`client_secret.json`** and move it
   into the project root folder (next to `config.json`). It is gitignored —
   it must never be committed.

---

## Part 3 — Mint the token locally

1. In PowerShell, from the project root:
   ```powershell
   .\.venv\Scripts\python scripts\factverse_engine.py auth
   ```
2. A browser window opens. Pick the channel's Google account.
3. You'll see **"Google hasn't verified this app"** — click **"Advanced"** →
   **"Go to AI Pulse Publisher (unsafe)"**. (This is your own app; the warning
   only means you skipped Google's app-store review, which is intentional.)
4. On the permission screen, **check all requested permissions** (upload +
   manage videos + view analytics) and click **Continue/Allow**.
5. The terminal prints `✅ Success!` and creates **`youtube_token.pickle`** in
   the project root (also gitignored).

---

## Part 4 — GitHub: push, secrets, first run

### 4.1 Push (from the project root)
```powershell
git push -u origin main
```
(The `origin` remote is already configured to the AI-PULSE repository.)

### 4.2 Add the four secrets
Repo page → **Settings → Secrets and variables → Actions → New repository secret**:

| Name | Value |
|---|---|
| `GEMINI_API_KEY`      | the Gemini key (from `.env`) |
| `PEXELS_API_KEY`      | the Pexels key (from `.env`) |
| `YT_CLIENT_SECRET_B64`| base64 of `client_secret.json` |
| `YT_TOKEN_B64`        | base64 of `youtube_token.pickle` |

To copy the base64 values (PowerShell, from the project root — run one, paste,
repeat):
```powershell
[Convert]::ToBase64String([IO.File]::ReadAllBytes("client_secret.json")) | Set-Clipboard
[Convert]::ToBase64String([IO.File]::ReadAllBytes("youtube_token.pickle")) | Set-Clipboard
```
Alternative without clicking around, using GitHub CLI (`winget install GitHub.cli`,
then `gh auth login` once):
```powershell
gh secret set GEMINI_API_KEY --repo Dev-Shivam-05/AI-PULSE
gh secret set PEXELS_API_KEY --repo Dev-Shivam-05/AI-PULSE
gh secret set YT_CLIENT_SECRET_B64 --repo Dev-Shivam-05/AI-PULSE --body ([Convert]::ToBase64String([IO.File]::ReadAllBytes("client_secret.json")))
gh secret set YT_TOKEN_B64 --repo Dev-Shivam-05/AI-PULSE --body ([Convert]::ToBase64String([IO.File]::ReadAllBytes("youtube_token.pickle")))
```

### 4.3 Enable Issues (the alert channel)
Repo → **Settings → General → Features** → make sure **Issues** is checked.
A failed run automatically opens an issue, and GitHub emails you about it —
that is the "something needs a human" signal.

### 4.4 First supervised run
1. Repo → **Actions** tab → if prompted, click **"I understand my workflows,
   go ahead and enable them"**.
2. Click **"AI Pulse — Auto Publish"** (left list) → **"Run workflow"** →
   green **Run workflow** button.
3. Watch the run (~40–60 min). Green = a video, thumbnail, and 3 Shorts are
   live on the channel. Red = read the log; a blocked policy/QA gate is the
   system protecting the channel, not a malfunction.
4. After the first green run, do nothing. The daily schedule (18:30 IST) owns
   publishing from here.

---

## What runs automatically after this
- **Daily video + 3 Shorts** on the cron; format chosen by the viral judge.
- **State commits** back to the repo after every run (topic history, run ledger,
  production log, analytics snapshots).
- **Failure → GitHub issue → email.** Fix-and-forget: most fixes are re-running
  the workflow or refreshing a secret.
- **Cron keepalive** re-enables the schedule (GitHub disables schedules on repos
  with no activity for ~60 days).
- **Nightly analytics snapshots** accumulate the data the learning loop tunes from.

## Routine maintenance (~10 min/month)
- Glance at the Actions tab (or just your email) for red runs.
- Check Settings → Billing → Actions minutes if the repo is private.
- Re-auth locally + update `YT_TOKEN_B64` if Google ever invalidates the token
  (the run log will say so explicitly).

## Troubleshooting quick table
| Symptom | Cause | Fix |
|---|---|---|
| Run red at "publish", log says token invalid | Token revoked/expired | Part 3 again, update `YT_TOKEN_B64` |
| Thumbnail missing on a video | Channel not phone-verified | Part 1.3 |
| Every run red at upload with 403 quotaExceeded | More than one publish/day | Keep a single daily run |
| "Video blocked by policy gate" in log | Script too close to source article | Nothing — the gate re-tries next day with a new story |
| Cron stopped firing | Schedule auto-disabled | Actions tab → workflow → "Enable"; keepalive prevents recurrence |

# ToolDojo Node — set-up for the always-on streaming PC

This PC runs the channel's live streams by itself: Radar Live every day at 20:00 IST,
and Live Trials on Saturday nights once that show ships. After a power cut or a
restart it starts again with nobody signed in. It never opens a window on your screen.
No Claude, Codex or other AI assistant is needed on it.

Full design, recovery rules and verification: `docs/spec/ai-pulse-v3n1.md`.

## Before you start (5 minutes)

1. **On the laptop**, if you ever installed the old laptop schedule, remove it. Otherwise
   two PCs stream to the same key:
   `powershell -ExecutionPolicy Bypass -File scripts\radar_schedule.ps1 -Uninstall`
2. **On the laptop**, build the ZIP:
   `py -3 scripts/build_node_bundle.py --music-dir E:/YOUTUBE/AI-PULSE/assets/music/radar`
   It prints the path, e.g. `temp\node_bundle\ToolDojoNode-<commit>.zip`.
   It holds the code and your music only. **No `.env`, no keys, no `output/`.**
3. Have these ready to paste:
   - YouTube Studio → Go live → Stream → **Stream URL** (the `rtmps://` one) and **Stream key**;
   - optional: the Gemini key (better narration), a Telegram bot token, and your own
     Telegram chat id (failure alerts).

## Install (once, on the node PC)

1. Plug the PC in. Connect it to the internet (a network cable is best).
2. Copy the ZIP to the PC and unzip it, e.g. to `Downloads\ToolDojoNode`.
3. Open **PowerShell as administrator**: Start → type `PowerShell` → right-click →
   *Run as administrator*.
4. Go to the folder and run the installer:
   ```
   cd $HOME\Downloads\ToolDojoNode
   powershell -ExecutionPolicy Bypass -File node\install.ps1
   ```
   (Want to see what it will do first? Add `-DryRun`. That only prints, it changes nothing.)
5. When it asks, paste the Stream URL and the Stream key. Press Enter to skip the optional
   ones. You type them **once**. They are stored only in `C:\ToolDojo\app\.env`, which only
   admins and the node's own account can read.
6. Wait. It installs Python, git and ffmpeg if they are missing. Then it measures this PC's
   encoders (up to 20 minutes) and prints a **VERDICT** and a status page.
   - `SELECTED: 720p30 libx264` (or better): the PC can stream. You are done.
   - `SELECTED: insufficient`: it will not stream. It tells you why. See "Hardware" below.

## BIOS: come back on after a power cut (do this once)

Windows cannot turn the PC back on after a power cut. Only the firmware can.

1. Restart the PC and keep tapping the BIOS key: **F2** or **Del** on most PCs; **F1** on
   Lenovo; **F10** on HP.
2. Find the power setting, usually under *Power*, *Advanced* or *Power Management*. Its
   name depends on the maker:
   - **AC Recovery** / **AC Power Recovery**: set **Power On** (Dell);
   - **After Power Loss**: set **Power On** (Lenovo ThinkCentre, HP);
   - **Restore on AC Power Loss**: set **Power On**;
   - **Power On with AC Attach**: set **On** (some laptops, e.g. ThinkPad).
3. Optional: enable **Wake on LAN** there too, if it exists.
4. Save and exit (usually F10).

**A laptop usually has no such option.** Its battery carries it through a short cut,
because the installer stops it sleeping on battery. If the battery runs flat, someone must
press the power button once. A mini PC with *After Power Loss = Power On* does not need that.

## How to check it worked

- Any time (no admin needed):
  `powershell -ExecutionPolicy Bypass -File C:\ToolDojo\app\node\status.ps1`
  It ends with `RESULT: healthy` or with the reason it is not.
- **The real test:** pull the plug for 10 seconds, plug it back in, and do not sign in.
  - With the BIOS option set, the PC powers on by itself.
  - Wait 3 minutes, then sign in and run `status.ps1`.
  - It should show `Supervisor: ALIVE`, with `since` a few minutes ago.
- On a stream day, open YouTube Studio at 20:05 IST. The stream should be live.

## Everyday use

- **You can use this PC normally**, for example from 9:00 to 12:00. The node runs nothing
  then. During a stream (20:00 to about 22:15 IST) the PC can feel slower, because the
  stream's programs use the CPU. They run at low priority, so your programs come first.
  The only cost is that, under heavy use, the stream may show a few more "standby" boards.
- **Pause** (no new streams start): create an empty file `C:\ToolDojo\data\PAUSE`. Delete
  it to resume.
- **Stop for good:** `powershell -ExecutionPolicy Bypass -File C:\ToolDojo\app\node\uninstall.ps1`
  (admin). Add `-RemoveFiles` to delete everything, keys included.
- **Change a key:** open Notepad as administrator and edit `C:\ToolDojo\app\.env`.
- **Logs:**
  - `C:\ToolDojo\data\logs\supervisor.log`: what the node decided, and why;
  - `C:\ToolDojo\data\logs\jobs\<job>.log`: each job's own output.
  Keys are never written to either one.
- **Updates:** the node pulls new code from GitHub by itself, at boot and daily at
  03:00 IST. A bad update is rolled back automatically.

## Hardware

The node's own measurement (the VERDICT) is the real answer for your PC.
- For an **Intel i3-5005U/5010U** with 8 GB, expect **720p30** at best. Its Quick Sync
  often does not start on new ffmpeg builds.
- If the verdict is *insufficient*, or you want 1080p: a refurbished **Lenovo ThinkCentre
  M720q / M920q Tiny** with an **i5-8500T**, 8–16 GB RAM and a 256 GB SSD costs about
  **₹20,000–31,000**. That is about 3.9× the CPU, and it has *After Power Loss* in the BIOS.
- Adding RAM or an SSD to the i3 does **not** fix a CPU limit.

## Manual prerequisites (only if winget is missing)

- **Python 3.11** from python.org: tick **"Install for all users"**.
- **Git for Windows** from git-scm.com: use the defaults.
- **ffmpeg**: download a "release essentials" build from gyan.dev, then copy `ffmpeg.exe`
  and `ffprobe.exe` into `C:\ToolDojo\bin`.

Then run `node\install.ps1` again. Re-running it is always safe.

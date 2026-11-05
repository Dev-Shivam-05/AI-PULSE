# Spec: v3-N.1, the ToolDojo Node (an always-on streaming PC)

Status: **built 2026-11-04** under the owner's go ("go for it… stop only when everything is
done"). Section 1 records the owner's six requirements, which are locked. Every value in
section 3 was delegated: "default chosen: X, because Y". Each one is **revisable**: change a
row, not the code. The node runs the existing live code unchanged in behaviour. Radar Live's
rows (v3l2/v3l3/v3l6) still apply. Live Trials (v3-T.1) plugs in as one row of the job table
(section 7).

## 1. Locked requirements (the owner's six, translated from Hinglish)

The owner cannot use their laptop for streaming. They have a second Windows PC: an Intel
i3 5th gen (i3-5005U/5010U class: 2 cores / 4 threads, HD 5500), 8 GB RAM and ~256 GB of
storage, assumed to run Windows 10/11 **Home**. They copy a ZIP to it, run a few commands
and enter their credentials once. From then on, live streaming and everything else runs
from that PC.

1. **Auto-recovery, zero manual work.** Power cuts and other failures will happen. After
   any reboot or power return, every service starts by itself, with no sign-in and no
   clicks. Nothing blocks: one failing job never stops the others, and a crash restarts
   with backoff.
2. **Lowest possible load** on that PC.
3. **No AI assistant on that PC.** Streaming, testing and recording all run as plain
   deterministic scripts. The channel's normal `.env` keys (Gemini free tier, the Telegram
   bot) are fine.
4. **Never block the screen.** The owner uses that PC at times, for example 9:00–12:00.
   Jobs run invisibly: no console or browser windows, no focus stealing, no popups. The
   PC stays responsive.
5. **Setup = ZIP + a few commands + credentials once**, with short, numbered English
   steps for a non-expert.
6. **An honest hardware verdict.** If the PC cannot do it, or can only do it at reduced
   quality, say what to buy or upgrade, with numbers.

## 2. Hardware verdict (requirement 6)

**Verdict: an i3-5005U/5010U with 8 GB can probably run Radar Live at 720p30 (x264). It
cannot be trusted at 1080p30. Its Quick Sync will most likely fail to start.** The node
measures itself at install time (section 5), and that measurement replaces this
estimate.

| CPU | PassMark multi / single | × i3-5005U |
|---|---|---|
| i3-5005U | 2,009 / 1,127 | 1.00 |
| i3-5010U | 2,140 / 1,197 | 1.07 |
| i3-10110U | 3,802 / 2,105 | 1.89 |
| N100 | 5,305 / 1,879 | 2.64 |
| i5-8250U | 5,779 / 1,868 | 2.88 |
| **i5-8500T** | **7,729 / 1,997** | **3.85** |
| i9-13900H (the laptop) | ~27,100 / — | ~13.5 |

Sources, read 2026-11-04 by the research pass:
- PassMark: `cpubenchmark.net/cpu.php?cpu=<name>`.
- i3-5005U Cinebench R15: 208 multi / 82 single (technical.city).
- Phoronix x264: i3-5010U 55.45 fps (openbenchmarking.org result 1512109-GA-LAPTOPS6243).

Quick Sync on HD 5500 (Broadwell, gen 8):
- The hardware can encode H.264, and libvpl's dispatcher hands gen 8–11 to the legacy
  Media SDK runtime (github.com/intel/libvpl README).
- In practice, libvpl-based ffmpeg builds fail on Broadwell with `MFX session: -9`.
  Sunshine issue #3351 shows it on an HD 5500 with Windows 10; its maintainer says Windows
  QSV needs Skylake or newer. ffmpeg trac #11605 is the same error with a gyan.dev 7.1.1
  build, still open.
- In a non-interactive session, QSV fails with D3D9 and needs D3D11 (ffmpeg trac #7511).
  The node therefore always asks for `child_device_type=d3d11va`.
- **Expect QSV to fail its preflight on this PC.** The preflight falls back by itself.

YouTube bitrates (support.google.com/youtube/answer/2853702, unchanged): 720p30 recommended
8 Mbps, 1080p30 recommended 14 Mbps, AAC 128 kbps, keyframe every 2 s. These are
`live_preflight.PROFILES`.

**Laptop numbers, for scale only. This laptop is NOT the node.** `node_preflight.py` was
run once on the i9-13900H, with real radar frames and the production segment command:

| Measure | Laptop result |
|---|---|
| screenshot | 62 ms |
| 1080p30 x264 | 5.62× |
| 720p30 x264 | 6.84× |
| 1080p30 QSV | 3.64× |
| 720p30 QSV | 5.48× |
| available RAM with Chromium open | 1,875 MB |
| selected | 1080p30 QSV (producer cost 0.37 s per video second) |

Projected onto the i3 by PassMark (an estimate, not a measurement):
- x264 needs roughly 4–13× the time;
- a screenshot costs roughly 150–250 ms;
- 720p30 x264 lands near the 0.8 budget;
- 1080p30 x264 is over it.

The research pass made the same estimate:
- 1080p30 x264: 0.8–1.5×, marginal;
- 720p30 x264: 1.5–3×, likely fine.

The L.2 "2.31×" figure came from testsrc2 and was generator-bound on the i9. Do not scale it.

**Upgrade, if the verdict says insufficient or you want 1080p:**
- a refurbished **Lenovo ThinkCentre M720q / M920q Tiny**:
  - i5-8500T (6 cores, 35 W, 3.85×);
  - 8–16 GB DDR4, 256 GB SSD, UHD 630;
- about **₹20,000–31,000**:
  - visionit.in ₹19,890–48,390;
  - TradeIndia ₹29,290, or ₹31,490 with 16 GB;
- a Dell OptiPlex 7060 Micro is equivalent, ₹23,190–46,890;
- it runs Windows 11, which the i3-5005U cannot;
- Dell and HP minis document a power-loss BIOS option (Lenovo's "After Power Loss" is
  likely there, but was not confirmed for the M720q).

**What does not help:**
- An 8 GB DDR3L stick (₹1,300–1,550) or a 256 GB SATA SSD (₹1,740–2,590) does **not**
  fix a CPU limit.
- An N100 mini PC (~₹17–34k new) is 2.6× the CPU and much cheaper to run (6 W). It is the
  budget alternative.

## 3. Delegated decisions

| # | Decision | Default chosen | Because |
|---|---|---|---|
| 1 | Layout | `C:\ToolDojo\{app,data,venv,bin,ms-playwright}` | One folder to back up, inspect or delete. `data` (state, logs, profile) lives outside the git checkout, so an update never touches it |
| 2 | Bundle | `git archive HEAD` minus `output/ state/ l2_store/ tests/ .github/ docs/debate/ prompts/`, plus the owner's radar music (gitignored, licence-clean) and `BUNDLE.json`. Every text file is scanned for key shapes, and a hit aborts the build | Committed bytes only: an untracked `.env` or an edit cannot ride along. Music is not in git but the stream needs it |
| 3 | Code on the node | `git clone --depth 1` of `node_update_branch`; the ZIP snapshot is the fallback (self-update then stays off) | Self-update needs a git checkout. The repo is public (23 MB), so no credential is needed |
| 4 | Account / session | A dedicated local **standard** user `tooldojo`. Its random 28+ character password is generated by the installer and never shown or stored. It is hidden from the sign-in screen. The task uses **Password** logon ("run whether or not the user is logged on"), RunLevel **Limited** | Section 6. Not SYSTEM: Chromium renders third-party README text, and that must not run as SYSTEM. Not S4U: S4U has no DPAPI keys, which Chromium's cookie store uses, and no stored password. Not the owner's account: it would need the owner's password and would run in the owner's session |
| 5 | Triggers | AtStartup (+30 s), plus a repetition every 5 min with `MultipleInstances IgnoreNew` | The 5-minute tick is a no-op while the supervisor runs. It restarts the supervisor if it ever exits, including deliberately after a self-update |
| 6 | Task settings | No time limit; restart on failure 999× at 1 min; starts and keeps running on battery; StartWhenAvailable | Requirement 1. The clock logic is inside the supervisor (row 11), so a late task start cannot run a stale job |
| 7 | Power | Sleep and hibernate never, on AC **and** battery. Lid does nothing on AC. Fast Startup off. The supervisor also holds `ES_SYSTEM_REQUIRED` | A laptop battery then rides through a short cut. With Fast Startup on, a "shut down" is a hibernate, and the start-up trigger may not fire |
| 8 | Windows Update | Active hours 08:00–02:00 local (the 18 h maximum); automatic active hours off; `NoAutoRebootWithLoggedOnUsers=1` (Home may ignore it); w32time automatic | It covers the owner's 9–12, Radar 20:00–23:00 IST and Trials 00:10–00:45 IST. An update restart lands at 02:00–08:00, when nothing runs |
| 9 | Encoder order | 1080p30 QSV → 720p30 QSV → 720p30 x264 veryfast → insufficient. 1080p30 x264 is measured but never auto-picked | Lowest load first (requirement 2): QSV runs on the GPU. 1080p x264 is the heaviest option. The owner can force a profile (row 22) |
| 10 | Profile budget | Producer cost = `screenshot_ms × 1.5/s + 1/encode_speed` **≤ 0.80 s per video second**; ≥ 1,024 MB RAM available with Chromium open | The radar renders and then encodes each segment on one process (v3l2 row 19). 1.5 screenshots/s comes from v3l2 row 18 (every second plus each ≤6-word phrase). The remaining 20 % covers edge-tts, the LLM call, the remux and the sender |
| 11 | Window / resume rule | A slot opens `lead_seconds` before `start_utc` and closes `slot_minutes` after it. Inside it, a job starts if ≥ `min_minutes` remain, else it is skipped with the reason logged. A start later than 120 s passes `remaining_arg <minutes left>` | Requirement 1 (a power cut mid-slot) without running past the slot. Radar: `--minutes` |
| 12 | Retries | Exponential backoff 30 s doubling to a 600 s cap; `attempts_per_day` per slot (radar 4). An exit 0 ends the slot | "A crash restarts with backoff". The cap stops a broken job from burning the whole evening |
| 13 | Hang | No stdout **and** no `pulse_file` write for `hang_seconds` = kill the whole tree (radar 600 s, ≥ its 300 s `READY_TIMEOUT` plus margin); `max_minutes` is a hard stop (radar 180 = the old task's 3 h kill) | The radar's producer is a child process whose prints never reach the pipe, so its log file counts as a pulse |
| 14 | Self-update | At boot and daily at 21:30 UTC (03:00 IST) when nothing runs: `git fetch --depth 1`, then `git checkout --detach <new>`, then the import check; a failure = check out the old commit, remember the bad one, alert. It never resets, cleans or overwrites local edits (a dirty tree = skip). If `node/` changed, the supervisor exits and the 5-minute trigger starts the new one | A detached checkout cannot lose work. The import check is the "breaks import" guard |
| 15 | Import check | `node_import_check` = factverse.config, factverse.radar, live_preflight, radar_live, supervisor, node_preflight | It is what the jobs import. Verified in a clean venv with `requirements-node.txt` only |
| 16 | Network wait | TCP connect to youtube.com:443 / github.com:443; backoff 5 s doubling to 60 s; give up after 900 s and start anyway | Bounded. The jobs are fail-soft and retried |
| 17 | Clock | HTTPS `Date` header (google.com/generate_204) at boot and every 6 h. The schedule runs on corrected time when skew > 2 s; alert when > 120 s | Clock drift cannot move a stream. w32time is also turned on |
| 18 | Disk | Every 60 s: below 10 GB free, delete only `node_cleanup_globs` under `app/temp` (crash leftovers), and only while no job runs. Below 3 GB, streams wait and an alert is sent. `radar_live.log` rotates at 20 MB, job logs at 5 MB × 3, the supervisor log at 1 MB × 5 | It cleans only its own temp. A pattern with `..`, an absolute pattern or the root itself is refused |
| 19 | Alerts | Telegram to `NODE_TELEGRAM_CHAT_ID` (the owner's own chat, never the public group) when a job fails ≥ 2× in a slot, gives up, an update rolls back, the disk hits the floor, or the clock is > 120 s off. At most 6 a day. Sent on a thread. Every body and error is redacted | It must never block the loop or leak the token (CLAUDE.md, `notify._redact`) |
| 20 | Priority | Every child is BelowNormal, **enforced on the whole tree** by a Job Object (`LIMIT_PRIORITY_CLASS`). An optional hard CPU cap `node_cpu_cap_percent` defaults to 0 = off | The owner's programs always win the CPU (requirement 4). A permanent cap would throttle the stream when the PC is idle |
| 21 | Kill switches | `node_enabled` (config); a `data\PAUSE` file (no edit needed); a per-job `enabled`; Radar's own (no `YT_STREAM_KEY` = exit 0) | Several layers, the simplest last |
| 22 | Forced profile | `node_stream_profile`: `auto`, or `720p30_x264` / `1080p30_qsv` / … | An escape hatch if the measurement is wrong |
| 23 | Supervisor deps | stdlib only | A broken venv or a bad update cannot take the supervisor (or its alerts) down |
| 24 | Node venv | `node/requirements-node.txt`: requests, edge-tts ≥ 7.3.1, playwright 1.60.0 | The daily pipeline's heavy deps (Kokoro, whisper, OpenCV, rembg) never run here. Smaller = less load, less to break |
| 25 | Who gets the profile | Every stream job gets `TOOLDOJO_STREAM_PROFILE` / `TOOLDOJO_ENCODER`. `RADAR_PROFILE` / `RADAR_ENCODER` go only to a row with `"radar_profile": true` (the radar row) | v3-T.1 calls `rl.segment_args` for its 1080×1920 frames. A `RADAR_PROFILE=720p30` there would scale them to 1280×720 |

## 4. Recovery matrix

| Failure | Expected behaviour | Verified by |
|---|---|---|
| **Power cut mid-stream** | The PC comes back (BIOS AC-recovery, or a laptop's battery never lost it). The task starts the supervisor 30 s after boot. The interrupted run counts as a failed attempt with an immediate retry. ≥ 30 min left in the slot = restart with `--minutes <left>`; less = skip, with the minutes logged | `test_n1_resume_rule_after_a_power_cut`, `test_n1_interrupted_run_counts_and_retries_now`; the real pull-the-plug test is the owner's (README) |
| **Network down at start** | The network wait (≤ 900 s), then the jobs start anyway. Radar fails fast (no data) and exits 1, so it is retried with backoff while the slot has ≥ 30 min | `wait_network` bound; `test_n1_retry_cap_and_backoff_wait` |
| **Network down mid-stream** | Radar's own streamer restarts 5× at 10 s (v3l2 row 21), then exits 1. The supervisor retries with backoff, within the slot | v3l2 §7 reconnect test; the supervisor retry tests |
| **YouTube ingest rejects** (bad key, stream not ready) | Same path: radar ends 1 after 5 reconnects; ≤ 4 attempts; alert after 2 failures and on give-up. The key is redacted everywhere | `test_n1_alerts_are_redacted_and_rate_limited`, `test_n1_supervisor_log_lines_are_redacted` |
| **Windows Update reboot** | Kept to 02:00–08:00 by active hours. If it happens anyway: the same as a power cut, on corrected time | install `-DryRun` steps 14–15; the power-cut tests |
| **Disk full** | Clean its own temp below 10 GB; below 3 GB streams wait and an alert is sent; logs rotate | `test_n1_disk_guard_*`, `test_n1_rotate_file` |
| **Gemini quota exhausted** | Radar's own fallback: the template narration (v3l2 row 14). The stream runs on. Not a supervisor event | v3l2 row 13–15 tests |
| **A child hangs** (no output for N s) | The whole Job Object tree is killed (Chromium, ffmpeg, the producer process), the attempt counts, and backoff starts | `test_n1_watchdog_kills_a_hung_child_and_backs_off`; the foreground run (section 8): the hang and its grandchild were killed |
| **A child crashes** | Exit ≠ 0, then backoff 30/60/120 … s and a retry until the cap. Other jobs are unaffected | the foreground run: crashy failed twice, then completed |
| **Clock drift** | The schedule uses HTTPS-corrected time; an alert when > 120 s | `test_n1_clock_skew_from_date_header` |
| **A code update breaks import** | Check out the old commit (detached), remember the bad commit, alert. The supervisor runs on the old code and retries only when a newer commit appears | `test_n1_update_plan`; the local bare-repo run (section 8): rollback, then skip, then a good update applied |
| **A bad job row / missing program** | The row is reported in `status.json` and the log; the other jobs run. A missing exe = a failed attempt, not a crash | `test_n1_parse_jobs_isolates_bad_rows`, `test_n1_one_job_failing_to_start_never_stops_the_others`; the foreground run's `missing_exe` |
| **The supervisor itself crashes** | The outer loop catches it, kills its children, and restarts in 30 s. If the process dies outright: task restart-on-failure plus the 5-minute trigger. A byte lock stops a second copy | `test_n1_single_instance_lock`; `main()` |
| **Two streams due together** | The second waits ("X holds the stream"); it starts later if `min_minutes` remain, else it is skipped | `test_n1_never_two_streams_at_once`; the foreground run's stream_a / stream_b |

## 5. The node preflight (`node/node_preflight.py`)

The supervisor runs it **inside the scheduled task** (session 0, the `tooldojo` account) at
first boot, whenever `data\node.local.json` is missing. `install.ps1 -Remeasure` forces a
new run.

What it measures:
1. **RAM**: total, and available while Chromium is open (GlobalMemoryStatusEx).
2. **Chromium**: the mean cost of a 1920×1080 screenshot of the real `radar.html`, over 19
   steady shots.
3. **Encodes**: the four profiles, through **`radar_live.segment_args` itself**, the exact
   production command. The input is those real board frames held for 20 s, so the content
   is mostly static, like the stream. Each encode is timed and then probed with
   `live_preflight.evaluate`: resolution, 30/1, H.264 and 2 s keyframes. A QSV
   session-creation failure is a failed row, not a crash.

It writes the pick plus the full measurements to `data\node.local.json`, and a human report
to `data\preflight_report.txt`; `install.ps1` prints that report. What happens with the pick:
- the supervisor passes it to stream jobs as `RADAR_PROFILE` / `RADAR_ENCODER`, plus the
  generic `TOOLDOJO_STREAM_PROFILE` / `TOOLDOJO_ENCODER`;
- the radar renders at 1920×1080 always and scales in ffmpeg;
- **insufficient** = stream jobs are skipped, with the reason logged and an alert sent;
- no file yet = 720p30 x264, the conservative profile.

## 6. Background guarantees ("never blocks the screen")

There are two independent layers.

**Session 0.** A task set to "run whether the user is logged on or not" (Password logon)
runs in session 0. That is a separate, non-interactive window station. Nothing it creates
can appear on the owner's desktop, take focus or show a dialog, even if a flag below were
wrong. The `tooldojo` account never signs in interactively.

**Every process is hidden anyway.**
- The supervisor runs under `pythonw.exe`, which has no console.
- Every child gets `CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP | BELOW_NORMAL`, plus
  `STARTUPINFO` with `SW_HIDE`. It gets no stdin.
- **`DETACHED_PROCESS` is deliberately not used.** With it, every console grandchild
  (ffmpeg, the radar's spawn child) would allocate its own new console window.
  `CREATE_NO_WINDOW` gives one hidden console that they all inherit.
- `test_n1_children_are_hidden_and_below_normal` asserts the flags.
- Chromium is Playwright's default `chromium.launch()`, which is headless (the headless
  shell, no window). The radar and the preflight never pass `headless=False`.
- git and the import check use the same hidden flags.

**When the owner uses the PC during a stream:**
- Nothing appears. The PC is slower, because the radar's x264 encode and Chromium share
  the CPU.
- Everything in the tree is BelowNormal, enforced by the Job Object, so the owner's
  foreground programs win every contest for the CPU.
- Worst case: under sustained heavy use the producer falls behind. The stream then shows
  more 10 s standby boards (v3l2 row 20) instead of stalling.
- Outside the stream slots (all of 9:00–12:00), the node runs nothing: a 2 s tick and a
  15 s status write.

## 7. Job table (the format T.1 uses)

`config.json` → `node_jobs`, a list. One row:

```json
{"name": "live_trials", "enabled": true, "stream": true,
 "cmd": ["{python}", "scripts/trials_live.py", "--episode", "next"],
 "days": ["sat"], "start_utc": "18:45", "lead_seconds": 300,
 "slot_minutes": 12, "min_minutes": 12, "max_minutes": 30,
 "hang_seconds": 300, "pulse_file": "logs/trials_live.log",
 "attempts_per_day": 2, "remaining_arg": "", "radar_profile": false, "env": {}}
```

Each field:
- `name`: `[a-z0-9_-]`, up to 40 characters.
- `cmd`: a list. `{python}` = the node venv's `python.exe`, `{app}` = the checkout. The
  working directory is the checkout.
- `days`: `"daily"` or a list of `mon..sun`, in **UTC**.
- `start_utc`: `HH:MM`.
- `stream: true`: never runs alongside another stream, and gets the profile env.
- Exit codes: **0 = done for the slot**; anything else = retry with backoff.
- Its stdout is the watchdog's pulse. It must print at least every `hang_seconds`, or
  write `pulse_file`.
- `TOOLDOJO_NODE=1` is always set. `TOOLDOJO_NODE_SCHEDULED=1` is set only for a job that
  runs every day.
- A stream job always gets `TOOLDOJO_STREAM_PROFILE` (`1080p30` / `720p30`) and
  `TOOLDOJO_ENCODER` (`libx264` / `h264_qsv`). Only `"radar_profile": true` adds
  `RADAR_PROFILE` / `RADAR_ENCODER`.
- **For T.1:** a 1080×1920 x264 encode costs the same as 1080p30. When the node picked
  `720p30`, read `TOOLDOJO_STREAM_PROFILE` and render or scale to 720×1280. `rl.segment_args`
  now takes `encoder=` / `profile=`.
- T.1 adds its imports to `node/requirements-node.txt` and its module to
  `node_import_check`.

The `live_trials` row ships `enabled: false` until `scripts/trials_live.py` exists. T.1 owns
its values.

## 8. Verification (2026-11-04, on the laptop; nothing installed)

Afterwards there was no `C:\ToolDojo`, no "ToolDojo Node" task and no `tooldojo` user,
checked with `Test-Path` / `Get-ScheduledTask` / `Get-LocalUser`.

**Tests**
- `tests/test_n1_node.py`: **42 tests**, covering the job table, windows, resume rule,
  backoff, retry cap, stream exclusivity, gates, interrupted runs, hang/overtime, redaction
  (values, the bot URL shape, Telegram errors, alert bodies), disk guard, rotation, clock
  skew, update plan, import check, profile env, hidden flags, the lock, the loop with fakes,
  preflight selection, radar args, the bundle filter/scan and PowerShell 5.1 syntax.
- The full suite: **690 passed** in 140 s (`py -3 -m pytest tests/ -q`, background).

**Foreground supervisor run**, 130 s, scratch data folder. The six jobs and what happened:
- `crashy` exited 1 twice: backoff 5 s, then 10 s, an alert at 2 failures, then attempt 3
  ran and `exit 0` = done.
- `hangy` spawned a grandchild and went silent:
  - `hung: no output for 15 s; killed` at exactly 15 s, twice;
  - then `retry cap reached (2/2)` and an alert;
  - both grandchild PIDs (22496, 40628) were gone afterwards: the Job Object killed the
    tree.
- `stream_a` / `stream_b`: B logged `waiting - stream_a holds the stream (never two at
  once)` and started the second A exited.
- `stream_a`'s child saw `RADAR_PROFILE=720p30 libx264` and `TOOLDOJO_NODE_SCHEDULED=1`.
  This run predates row 25: a stream row now needs `radar_profile: true` for `RADAR_*`
  (unit-tested).
  Its printed `/bot123…:AAqq…/sendMessage` reached the job log as `/bot***/sendMessage`.
- `too_late`: `skipped … only 1.2 min left of the 16:11Z slot (needs 5)`.
- `missing_exe`: `could not start: FileNotFoundError`, twice, then the cap. The other five
  jobs were unaffected.
- `status.json` matched all of the above. `status.ps1 -Root <scratch>` rendered it.
- Fixed after reading the log: the disk-guard line repeated every minute (now once a
  day), and a passing import check was not logged.

**Power-cut simulation**
- The supervisor was hard-killed (`taskkill /F`) 12 s into a late-started stream job:
  - its child died with it (KILL_ON_JOB_CLOSE);
  - the state file still said `running`.
- On restart:
  - `was running when the PC/supervisor stopped; counted as a failed attempt`;
  - `import check ok`;
  - `started attempt 2/4 … late, with --minutes 23`.

**Self-update against a local bare repo** (a real git fetch/checkout, no network):
1. nothing new: `skip: already current`;
2. a pushed commit with a syntax error in `factverse/radar.py`: `rolled back`, HEAD back on
   the old commit, the bad commit remembered, and an alert carrying the SyntaxError tail;
3. the same bad commit again: `skip: … failed the import check before`;
4. a fixing commit that also touched `node/`: `updated: node files changed=True`, HEAD =
   the new commit (the supervisor then exits for the 5-minute trigger);
5. a local edit to a tracked file plus a new remote commit: `skip: tracked files were
   edited on this PC`, with the edit kept.

**`install.ps1 -DryRun`** (not elevated), PowerShell 5.1.26100:
- 0 parse errors in all three scripts (`Parser::ParseFile`).
- 18 actions listed, nothing changed.
- **Bug found and fixed:** the only Python on this laptop is per-user
  (`%LOCALAPPDATA%\Programs\Python311`), which the task's account cannot read. The
  installer now accepts only machine-wide Python/git; the re-run plans
  `winget install Python.Python.3.11 --scope machine`.
- `uninstall.ps1 -DryRun`: 2 actions, nothing changed.

**Bundle**:
- `ToolDojoNode-e9f53758c4.zip` (rebuilt at the last code commit): 38.9 MB, 159 files
  (factverse 38, scripts 10, node 7, docs 67, assets 23 including 5 radar music tracks,
  configs, BUNDLE.json).
- No `.env` (only the placeholder `.env.example`), no `output/ state/ temp/ logs/ tests/`,
  no token/pickle/client_secret files.
- The credential-shape scan of every committed file found nothing.

**Import check in a clean venv** with only `node/requirements-node.txt`: all of
factverse.config, factverse.radar, live_preflight, radar_live, supervisor, node_preflight,
captions and storyboard imported.

**Preflight on the laptop** (laptop numbers, section 2): it ran end to end:
- Chromium rendered `radar.html`;
- all four encodes passed the 2 s keyframe / H.264 / 30 fps probe;
- QSV with `child_device_type=d3d11va` worked in a signed-in session.

**Not verified** (needs the node):
- session 0, the Password-logon task and the BIOS power-on;
- QSV on HD 5500;
- a real Radar session from the node;
- a self-update over the network from GitHub (the same code path was run against a
  local bare repo).

## 9. Known limits

- **Not run on the real node.** Session-0 QSV/Chromium behaviour, the Password-logon task,
  the BIOS power-on and Windows Home's handling of `NoAutoRebootWithLoggedOnUsers` are
  documented and coded, but they can only be verified on that PC. The README's
  pull-the-plug test is the acceptance step.
- "Log on as a batch job" is normally granted by Task Scheduler when a task is
  registered with a password. Windows Home has no `secpol.msc` to check it. If a Home build
  does not grant it, `status.ps1` shows the task's last result ≠ 0 and no heartbeat. That
  case is not automated here; the fallback is to set the task's user again in the Task
  Scheduler UI.
- The Job Object is assigned right after `Popen`. A grandchild spawned in the first
  milliseconds could escape it, which is negligible for Python start-up. `taskkill /T` is
  the fallback.
- The radar's cooldown history (`temp/live/radar_history.json`) starts empty on the node,
  so a tool spotlighted on the laptop in the last 3 days can be shown again once.
- The radar's music must be in the bundle (`--music-dir`), or copied later; otherwise the
  stream runs silent under the voice.
- Preemption is not built: a higher-priority stream does not stop a running one; it waits
  (row 11). The current slots never overlap.
- The CI manifest (L.7) can ask for up to 360 min, but the radar row's `max_minutes` of 180
  kills at 3 h, exactly like the old task. Raise both when L.8 approves a longer stage.
- After a power cut late in the slot, the radar restarts with `--minutes <left>`, which
  ignores the manifest (radar_live's own rule for `--minutes`). That is correct for a
  shortened rerun.
- A laptop-class node (i3-5005U) has no BIOS power-on; a flat battery needs one button
  press.
- Windows 10 support: the free consumer updates were due to end 2026-10-13; a reported
  extension to 2027-10-12 is unverified. The i3-5005U cannot run Windows 11.

## 10. Traps (proposed for CLAUDE.md, not added there by this phase)

- **A scheduled task's account cannot see another user's folders.** A per-user Python
  (`%LOCALAPPDATA%\Programs\Python`) or winget ffmpeg is invisible to the `tooldojo`
  account. The installer accepts only machine-wide Python/git and copies ffmpeg into
  `C:\ToolDojo\bin`. The dry run on this laptop found exactly this.
- **`DETACHED_PROCESS` is the flashing-window bug, not the fix.** It gives a child no
  console, so every console grandchild opens a new one. Use `CREATE_NO_WINDOW`, which
  grandchildren inherit.
- **A BOM breaks `.env`.** PowerShell 5.1's `Out-File`/`Set-Content` write one, and
  `config._load_dotenv` would then read the key `\ufeffYT_STREAM_URL`. Write with
  `UTF8Encoding($false)`.
- **The node's measured profile must not live in a tracked file.** Writing it into
  `config.json` would make the tree dirty, and the self-update would then refuse every
  update forever. It lives in `data\node.local.json`.
- **A node-wide env var reaches every job, including the ones that import yours.**
  `RADAR_PROFILE` was first given to every stream job, but T.1 imports `radar_live` and
  calls `rl.segment_args` for vertical frames, so 720p30 would have scaled them to
  1280×720. Scope an env var to the row that asked for it.
- **A multiprocessing child's prints never reach the parent's pipe** (spawn, no
  inherited handles). A stdout-silence watchdog therefore kills a healthy radar during
  pre-roll unless the job's log file also counts as a pulse.

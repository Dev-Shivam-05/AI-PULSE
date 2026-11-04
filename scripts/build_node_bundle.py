"""
v3-N.1 ToolDojo Node bundle: the ZIP the owner copies to the node PC
(docs/spec/ai-pulse-v3n1.md row 2).

    py -3 scripts/build_node_bundle.py
    py -3 scripts/build_node_bundle.py --music-dir E:/YOUTUBE/AI-PULSE/assets/music/radar
    py -3 scripts/build_node_bundle.py --list            # print every file in the ZIP

What goes in: the COMMITTED tree of HEAD (`git archive`, so an uncommitted edit or an
untracked file - a .env above all - can never ride along), minus everything the node
does not run (output/, state/, tests/, CI, debates), plus the owner's optional radar
music (gitignored, licence-clean Audio Library tracks) and BUNDLE.json. Every text file
is scanned for credential shapes; one hit aborts the build and names the file, never
the value. The node itself then clones the repo so it can update; this snapshot is the
fallback when that clone fails.

Output: temp/node_bundle/ToolDojoNode-<commit>.zip (temp/ is gitignored).
"""
from __future__ import annotations

import argparse
import io
import json
import re
import subprocess
import sys
import tarfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOP = "ToolDojoNode"
EXCLUDE_PREFIXES = ("output/", "state/", "l2_store/", "tests/", ".github/", "docs/debate/",
                    "hyperautomation Labs", "hyperautomation-lab.script.md", "prompts/",
                    "temp/", "logs/", "assets/models/")
EXCLUDE_FILES = ("used_topics.json", "used_urls.json", "last_run.json")
SECRET_NAMES = re.compile(
    r"(^|/)(\.env(\..*)?|client_secret[^/]*\.json|[^/]*\.pickle|ig_session\.json|"
    r"[^/]*token[^/]*\.(json|txt|pickle)|[^/]*\.pem|[^/]*\.key)$", re.I)
ALLOWED_SECRET_LOOKALIKES = (".env.example",)
SECRET_PATTERNS = {
    "Google API key": re.compile(rb"AIza[0-9A-Za-z_\-]{35}"),
    "Telegram bot token": re.compile(rb"\b\d{8,10}:AA[0-9A-Za-z_\-]{33}\b"),
    "YouTube stream key": re.compile(rb"\b[a-z0-9]{4}-[a-z0-9]{4}-[a-z0-9]{4}-[a-z0-9]{4}-[a-z0-9]{4}\b"),
    "GitHub token": re.compile(rb"\bgh[pousr]_[A-Za-z0-9]{36,}\b"),
    "private key": re.compile(rb"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
}
TEXT_SUFFIXES = (".py", ".json", ".md", ".txt", ".ps1", ".html", ".yml", ".yaml", ".toml",
                 ".cfg", ".ini", ".example", ".js", ".css", ".csv", ".xml", ".env")


def include(path: str) -> bool:
    """Is this committed path part of the node bundle?"""
    p = str(path).replace("\\", "/")
    if not p or p.endswith("/"):
        return False
    if any(p.startswith(x) for x in EXCLUDE_PREFIXES) or p in EXCLUDE_FILES:
        return False
    name = p.rsplit("/", 1)[-1]
    if name in ALLOWED_SECRET_LOOKALIKES:
        return True
    return not SECRET_NAMES.search(p)


def scan(path: str, data: bytes) -> list:
    """Names of the credential shapes found in a text file ([] = clean)."""
    if not str(path).lower().endswith(TEXT_SUFFIXES) and b"\x00" in data[:4096]:
        return []
    return [name for name, rx in SECRET_PATTERNS.items() if rx.search(data)]


def git(*args) -> bytes:
    return subprocess.run(["git", *args], cwd=str(ROOT), capture_output=True, check=True,
                          timeout=300).stdout


def committed_files() -> list:
    """[(path, bytes)] of HEAD's committed tree."""
    tar = git("archive", "--format=tar", "HEAD")
    out = []
    with tarfile.open(fileobj=io.BytesIO(tar)) as tf:
        for m in tf.getmembers():
            if m.isfile():
                out.append((m.name, tf.extractfile(m).read()))
    return out


def build(out_dir: Path, branch: str, music_dir: Path | None) -> tuple:
    commit = git("rev-parse", "--short=10", "HEAD").decode().strip()
    source = git("rev-parse", "--abbrev-ref", "HEAD").decode().strip()
    files = [(p, d) for p, d in committed_files() if include(p)]
    hits = [(p, scan(p, d)) for p, d in files]
    hits = [(p, h) for p, h in hits if h]
    if hits:
        for p, h in hits:
            print(f"REFUSED: {p} looks like it holds a {', '.join(h)}")
        raise SystemExit(1)
    music = sorted(music_dir.glob("*.mp3")) if music_dir and music_dir.is_dir() else []
    info = {"commit": commit, "source_branch": source, "update_branch": branch,
            "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "files": len(files), "music_tracks": len(music)}
    out_dir.mkdir(parents=True, exist_ok=True)
    zpath = out_dir / f"ToolDojoNode-{commit}.zip"
    with zipfile.ZipFile(zpath, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for p, d in files:
            z.writestr(f"{TOP}/{p}", d)
        for m in music:
            z.write(m, f"{TOP}/assets/music/radar/{m.name}")
        z.writestr(f"{TOP}/BUNDLE.json", json.dumps(info, indent=1))
    return zpath, info


def verify(zpath: Path) -> list:
    """Problems found by re-reading the finished ZIP ([] = clean)."""
    bad = []
    with zipfile.ZipFile(zpath) as z:
        for n in z.namelist():
            rel = n[len(TOP) + 1:] if n.startswith(TOP + "/") else n
            if rel.startswith(("output/", "state/", "temp/", "logs/")) or (
                    SECRET_NAMES.search(rel) and rel.rsplit("/", 1)[-1] not in ALLOWED_SECRET_LOOKALIKES):
                bad.append(n)
    return bad


def main(argv=None) -> int:
    cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    ap = argparse.ArgumentParser(description="Build the ToolDojo Node ZIP (v3-N.1)")
    ap.add_argument("--branch", default=cfg.get("node_update_branch", "main"),
                    help="the branch the node clones and updates from")
    ap.add_argument("--music-dir", default=str(ROOT / "assets" / "music" / "radar"))
    ap.add_argument("--out", default=str(ROOT / "temp" / "node_bundle"))
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args(argv)
    if not re.match(r"^[A-Za-z0-9._/-]{1,100}$", a.branch):
        print("bad --branch")
        return 2
    zpath, info = build(Path(a.out), a.branch, Path(a.music_dir) if a.music_dir else None)
    bad = verify(zpath)
    if bad:
        print("REFUSED after build: " + ", ".join(bad))
        zpath.unlink()
        return 1
    with zipfile.ZipFile(zpath) as z:
        names = z.namelist()
    print(f"{zpath}  ({zpath.stat().st_size / 1e6:.1f} MB, {len(names)} files, "
          f"commit {info['commit']} from {info['source_branch']}, node updates from "
          f"'{info['update_branch']}', {info['music_tracks']} music tracks)")
    if info["music_tracks"] == 0:
        print("note: no radar music in the bundle (pass --music-dir); the stream runs silent "
              "under the voice until tracks are copied to C:\\ToolDojo\\app\\assets\\music\\radar")
    if a.list:
        for n in names:
            print("  " + n)
    return 0


if __name__ == "__main__":
    sys.exit(main())

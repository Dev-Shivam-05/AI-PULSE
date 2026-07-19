"""
FactVerse — portable configuration & environment bootstrap.

Single source of truth for paths, secrets, provider selection, and tool
discovery (ffmpeg / ffprobe). Importing this module once:

  * resolves the project base dir   (portable — no more hard-coded C:/FactVerse)
  * loads secrets from a .env file  (falls back to real environment variables)
  * creates the standard directory layout
  * puts ffmpeg/ffprobe and the Python "Scripts" dir on PATH so the existing
    subprocess calls (`ffmpeg ...`, `edge-tts ...`) keep working unchanged.

Zero third-party dependencies on purpose: this must import on a bare Python
before `pip install -r requirements.txt` has run.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

# The pipeline logs with emoji; on a cp1252 Windows console a bare print() can
# raise UnicodeEncodeError and kill an unattended run. Make stdout unkillable.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(errors="replace")
    except (AttributeError, OSError):
        pass


# --------------------------------------------------------------- base dir ---
def _resolve_base() -> Path:
    override = os.environ.get("FACTVERSE_HOME")
    if override:
        return Path(override).expanduser().resolve()
    # this file lives at <BASE>/factverse/config.py  ->  BASE is two levels up
    return Path(__file__).resolve().parent.parent


BASE = _resolve_base()


# --------------------------------------------------------------- .env -------
def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        # a real environment variable always wins over the .env file
        os.environ.setdefault(key, val)


_load_dotenv(BASE / ".env")


# --------------------------------------------------------------- config.json
def _load_config() -> dict:
    cfg_path = BASE / "config.json"
    if cfg_path.exists():
        try:
            return json.loads(cfg_path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001 - surface, never crash import
            print(f"WARNING: could not parse config.json: {exc}")
    return {}


CONFIG = _load_config()


def setting(name: str, default=None):
    """Return a config.json value, overridable by an UPPER_CASE env var."""
    env = os.environ.get(name.upper())
    if env is not None:
        return env
    return CONFIG.get(name, default)


def _secret(*env_names: str, config_key: str | None = None, default: str = "") -> str:
    for n in env_names:
        v = os.environ.get(n)
        if v:
            return v
    if config_key and CONFIG.get(config_key):
        return str(CONFIG[config_key])
    return default


# --------------------------------------------------------------- secrets ----
GEMINI_KEY = _secret("GEMINI_API_KEY", config_key="gemini_api_key")
PEXELS_KEY = _secret("PEXELS_API_KEY", config_key="pexels_api_key")
IG_USER = _secret("INSTAGRAM_USERNAME", config_key="instagram_username")
IG_PASS = _secret("INSTAGRAM_PASSWORD", config_key="instagram_password")

# --------------------------------------------------------------- providers --
LLM_PROVIDER = setting("llm_provider", "gemini")
TTS_PROVIDER = setting("tts_provider", "edge")
STOCK_PROVIDER = setting("stock_provider", "pexels")
VIDEO_PROVIDER = setting("video_provider", "none")

VOICE = setting("voice", "en-US-GuyNeural")
RATE = setting("voice_rate", "+5%")
KOKORO_VOICE = setting("kokoro_voice", "af_heart")
VOICE_SPEED = setting("voice_speed", 1.0)


def flag(name: str, default: bool = False) -> bool:
    """Boolean config value, overridable by env var (so CI can toggle without a commit)."""
    v = setting(name, default)
    if isinstance(v, str):
        return v.strip().lower() in ("1", "true", "yes", "on")
    return bool(v)

# --------------------------------------------------------------- brand ------
# One place to rebrand the channel. Change channel_name in config.json anytime.
CHANNEL_NAME = setting("channel_name", "AI Pulse")
CHANNEL_HANDLE = setting("channel_handle", "aipulse")
CHANNEL_TAGLINE = setting("channel_tagline", "AI news, decoded")

# --------------------------------------------------------------- paths ------
OUTPUT = BASE / "output"
VIDEOS = OUTPUT / "videos"
SHORTS = OUTPUT / "shorts"
THUMBS = OUTPUT / "thumbnails"
TEMP = BASE / "temp"
ASSETS = BASE / "assets"
MUSIC = ASSETS / "music"
FONTS = ASSETS / "fonts"
LOGS = BASE / "logs"
STATE = BASE / "state"

for _d in (VIDEOS, SHORTS, THUMBS, TEMP, MUSIC, FONTS, LOGS, STATE):
    _d.mkdir(parents=True, exist_ok=True)


# --------------------------------------------------------------- tools ------
def _candidate_scripts_dirs():
    exe = Path(sys.executable).resolve()
    yield exe.parent            # venv:    <env>/Scripts/python.exe
    yield exe.parent / "Scripts"  # global: <root>/Scripts
    yield Path.home() / "AppData/Roaming/Python/Python311/Scripts"


def _find_binary(name: str, env_override: str) -> str | None:
    ev = os.environ.get(env_override)
    if ev and Path(ev).exists():
        return ev
    found = shutil.which(name)
    if found:
        return found
    common = [
        BASE / "bin" / f"{name}.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Links" / f"{name}.exe",
        Path("C:/ffmpeg/bin") / f"{name}.exe",
    ]
    for c in common:
        try:
            if c and Path(c).exists():
                return str(c)
        except OSError:
            continue
    # winget installs land under .../WinGet/Packages/<pkg>/.../bin/<name>.exe
    pkgs = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Packages"
    if pkgs.exists():
        try:
            for p in pkgs.glob(f"**/{name}.exe"):
                return str(p)
        except OSError:
            pass
    return None


FFMPEG = _find_binary("ffmpeg", "FFMPEG_BIN")
FFPROBE = _find_binary("ffprobe", "FFPROBE_BIN")


def _ensure_path() -> None:
    extra: list[str] = []
    if FFMPEG:
        extra.append(str(Path(FFMPEG).parent))
    for d in _candidate_scripts_dirs():
        if d.exists():
            extra.append(str(d))
    cur = os.environ.get("PATH", "")
    for p in extra:
        if p and p not in cur:
            cur = p + os.pathsep + cur
    os.environ["PATH"] = cur


_ensure_path()


# --------------------------------------------------------------- validation -
def validate() -> list[str]:
    """Return a list of human-readable missing prerequisites (empty == ready)."""
    missing: list[str] = []
    if not GEMINI_KEY or "PASTE" in GEMINI_KEY:
        missing.append("GEMINI_API_KEY")
    if not PEXELS_KEY or "PASTE" in PEXELS_KEY:
        missing.append("PEXELS_API_KEY")
    if not FFMPEG:
        missing.append("ffmpeg (install: winget install Gyan.FFmpeg)")
    if not FFPROBE:
        missing.append("ffprobe (ships with ffmpeg)")
    return missing


if __name__ == "__main__":
    print("FactVerse configuration")
    print("  BASE       :", BASE)
    print("  ffmpeg     :", FFMPEG or "NOT FOUND")
    print("  ffprobe    :", FFPROBE or "NOT FOUND")
    print("  providers  :", f"llm={LLM_PROVIDER} tts={TTS_PROVIDER} stock={STOCK_PROVIDER} video={VIDEO_PROVIDER}")
    print("  voice      :", VOICE, RATE)
    print("  Gemini key :", (GEMINI_KEY[:8] + "...") if GEMINI_KEY else "MISSING")
    print("  Pexels key :", (PEXELS_KEY[:8] + "...") if PEXELS_KEY else "MISSING")
    print("  IG user    :", IG_USER or "MISSING")
    miss = validate()
    print("  missing    :", ", ".join(miss) if miss else "none -- ready")

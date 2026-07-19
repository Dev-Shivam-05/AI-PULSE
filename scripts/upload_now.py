"""
FINAL UPLOADER — Uses YouTube API with SAFE hardcoded tags
Zero manual work. Zero errors. Just uploads.
"""
import os, sys, json, pickle, re, time, glob
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from factverse import config as fv

BASE = fv.BASE

# ====== SAFE TAGS — hardcoded, guaranteed to work ======
SAFE_TAGS = [
    "ai", "artificial intelligence", "ai news", "machine learning",
    "tech news", "ai explained", "technology", "deep learning",
    "llm", "generative ai", "ai tools", "future of ai",
    fv.CHANNEL_NAME.lower(),
]

SAFE_SHORT_TAGS = SAFE_TAGS + ["Shorts"]


def yt_auth():
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    
    SCOPES = ["https://www.googleapis.com/auth/youtube.upload",
              "https://www.googleapis.com/auth/youtube",
              "https://www.googleapis.com/auth/yt-analytics.readonly"]
    
    creds = None
    tok = BASE / "youtube_token.pickle"
    
    if tok.exists():
        with open(tok, "rb") as f:
            creds = pickle.load(f)
    
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except:
                creds = None
        if not creds:
            secret = BASE / "client_secret.json"
            if not secret.exists():
                print("❌ client_secret.json not found!")
                sys.exit(1)
            flow = InstalledAppFlow.from_client_secrets_file(str(secret), SCOPES)
            creds = flow.run_local_server(port=8090)
        
        with open(tok, "wb") as f:
            pickle.dump(creds, f)
    
    return creds


def upload_one(yt, filepath, title, description, tags, is_short=False):
    """Upload one video with guaranteed safe tags"""
    from googleapiclient.http import MediaFileUpload
    
    label = "SHORT" if is_short else "VIDEO"
    filename = Path(filepath).name
    filesize = os.path.getsize(filepath) / (1024 * 1024)
    
    print(f"\n  {'📱' if is_short else '📹'} [{label}] {filename} ({filesize:.0f}MB)")
    print(f"     Title: {title[:60]}...")
    
    if is_short and "#Shorts" not in title:
        title = title[:90] + " #Shorts"
    
    body = {
        "snippet": {
            "title": title[:100],
            "description": description[:5000],
            "tags": tags,
            "categoryId": "27"
        },
        "status": {
            "privacyStatus": "public",
            "selfDeclaredMadeForKids": False
        }
    }
    
    media = MediaFileUpload(
        filepath,
        mimetype="video/mp4",
        resumable=True,
        chunksize=5 * 1024 * 1024
    )
    
    request = yt.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media
    )
    
    response = None
    last_progress = 0
    max_retries = 5
    
    while response is None:
        try:
            status, response = request.next_chunk()
            if status:
                progress = int(status.progress() * 100)
                if progress >= last_progress + 10:
                    print(f"     {progress}%", end=" ")
                    last_progress = progress
        except Exception as e:
            err = str(e)
            if "10054" in err or "Connection" in err or "reset" in err.lower():
                max_retries -= 1
                if max_retries <= 0:
                    print(f"\n     ❌ Connection failed after retries")
                    return None
                print(f"↻", end=" ")
                time.sleep(10)
                continue
            else:
                print(f"\n     ❌ Error: {e}")
                return None
    
    video_id = response["id"]
    url = f"https://youtube.com/watch?v={video_id}"
    print(f"\n     ✅ LIVE: {url}")
    return url


def get_video_title(filepath):
    """Extract a nice title from filename"""
    name = Path(filepath).stem
    # Remove timestamp at end
    name = re.sub(r'_\d{8}_\d{6}$', '', name)
    # Replace underscores with spaces
    name = name.replace('_', ' ')
    return name


def load_log_safe():
    """Load production log safely"""
    log_file = BASE / "output" / "production_log.json"
    if not log_file.exists():
        return []
    try:
        with open(log_file, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        try:
            with open(log_file, "r", encoding="utf-8", errors="ignore") as f:
                return json.load(f)
        except:
            try:
                with open(log_file, "rb") as f:
                    content = f.read().decode("utf-8", errors="ignore")
                    return json.loads(content)
            except:
                print("  ⚠️ Could not read log file, using filenames for titles")
                return []


def main():
    print("=" * 55)
    print("  📤 FACTVERSE UPLOADER — FULLY AUTOMATIC")
    print("  Using YouTube API with safe tags")
    print("  ZERO manual work required")
    print("=" * 55)
    
    # Authenticate
    print("\n  🔐 Authenticating YouTube...")
    from googleapiclient.discovery import build
    
    creds = yt_auth()
    yt = build("youtube", "v3", credentials=creds)
    print("  ✅ Authenticated!")
    
    # Find all videos
    video_dir = BASE / "output" / "videos"
    short_dir = BASE / "output" / "shorts"
    
    videos = sorted(video_dir.glob("*.mp4"), key=lambda x: x.stat().st_mtime)
    shorts = sorted(short_dir.glob("*.mp4"), key=lambda x: x.stat().st_mtime)
    
    print(f"\n  📁 Found: {len(videos)} long videos + {len(shorts)} shorts")
    
    if not videos and not shorts:
        print("  ❌ No videos found! Run factverse_engine.py first.")
        return
    
    # Load log for metadata
    logs = load_log_safe()
    
    # Build title lookup from logs
    title_map = {}
    desc_map = {}
    thumb_map = {}
    shorts_meta_map = {}
    already_up = set()      # video/short filenames that already have a YouTube URL

    for log in logs:
        video_path = log.get("video", "")
        if video_path:
            vname = Path(video_path).name
            title_map[vname] = log.get("title", "")
            desc_map[vname] = log.get("description", "")
            if log.get("youtube_url"):
                already_up.add(vname)
            if log.get("thumbnail"):
                thumb_map[vname] = log.get("thumbnail", "")

            # Map shorts to their metadata
            shorts_list = log.get("shorts", [])
            meta_list = log.get("shorts_meta", [])
            short_urls = log.get("youtube_shorts", []) or []
            if isinstance(shorts_list, list):
                for i, sp in enumerate(shorts_list):
                    sname = Path(sp).name
                    if i < len(meta_list):
                        shorts_meta_map[sname] = meta_list[i]
                    if i < len(short_urls) and short_urls[i]:
                        already_up.add(sname)

    # Never re-publish what already has a URL — a rerun must not duplicate the library
    videos = [v for v in videos if v.name not in already_up]
    shorts = [s for s in shorts if s.name not in already_up]
    print(f"  ⏭️ Skipping already-uploaded files → {len(videos)} videos + {len(shorts)} shorts to go")
    
    # ==========================================
    # UPLOAD LONG VIDEOS FIRST
    # ==========================================
    print("\n" + "─" * 55)
    print("  📹 UPLOADING LONG VIDEOS")
    print("─" * 55)
    
    long_urls = {}  # filename -> youtube url
    
    for vid in videos:
        title = title_map.get(vid.name, "") or get_video_title(str(vid))
        desc = desc_map.get(vid.name, "")
        if not desc:
            desc = (
                f"{title}\n\n"
                f"Subscribe to {fv.CHANNEL_NAME} for clear, accurate AI news and explainers!\n\n"
                f"#AI #ArtificialIntelligence #TechNews"
            )
        
        url = upload_one(yt, str(vid), title, desc, SAFE_TAGS)
        
        if url:
            long_urls[vid.name] = url
            
            # Try uploading thumbnail
            thumb = thumb_map.get(vid.name, "")
            if thumb and os.path.exists(thumb):
                try:
                    from googleapiclient.http import MediaFileUpload
                    video_id = url.split("v=")[-1]
                    yt.thumbnails().set(
                        videoId=video_id,
                        media_body=MediaFileUpload(thumb, mimetype="image/jpeg")
                    ).execute()
                    print(f"     🖼️ Thumbnail uploaded!")
                except:
                    print(f"     🖼️ Thumbnail: verify channel at youtube.com/verify")
        
        time.sleep(5)
    
    # Get first long video URL for shorts
    first_long_url = list(long_urls.values())[0] if long_urls else ""
    
    # ==========================================
    # UPLOAD ALL SHORTS
    # ==========================================
    print("\n" + "─" * 55)
    print("  📱 UPLOADING SHORTS")
    print("─" * 55)
    
    short_urls = []
    
    for i, short in enumerate(shorts):
        # Get metadata from log
        meta = shorts_meta_map.get(short.name, {})
        
        title = meta.get("title", "")
        if not title:
            title = f"AI News You Missed — Part {i+1} #Shorts"

        desc = meta.get("description", "")
        if not desc:
            desc = f"🤖 The AI story everyone's talking about. Follow {fv.CHANNEL_NAME}!\n\n#Shorts #AI #TechNews"
        
        # Add long video link to description
        if first_long_url:
            desc = f"🎬 FULL VIDEO: {first_long_url}\n\n{desc}"
        
        url = upload_one(yt, str(short), title, desc, SAFE_SHORT_TAGS, is_short=True)
        
        if url:
            short_urls.append(url)
        
        time.sleep(5)
    
    # ==========================================
    # SUMMARY
    # ==========================================
    print("\n" + "=" * 55)
    print("  🎉 UPLOAD COMPLETE!")
    print("=" * 55)
    
    print(f"\n  📹 Long Videos Uploaded: {len(long_urls)}")
    for name, url in long_urls.items():
        print(f"     ▶️ {url}")
    
    print(f"\n  📱 Shorts Uploaded: {len(short_urls)}")
    for url in short_urls:
        print(f"     ▶️ {url}")
    
    total = len(long_urls) + len(short_urls)
    print(f"\n  ✅ TOTAL: {total} videos now LIVE on YouTube!")
    print("=" * 55)
    
    # Update production log
    try:
        for log in logs:
            vpath = log.get("video", "")
            if vpath:
                vname = Path(vpath).name
                if vname in long_urls:
                    log["youtube_url"] = long_urls[vname]
        
        log_file = BASE / "output" / "production_log.json"
        with open(log_file, "w", encoding="utf-8") as f:
            json.dump(logs, f, indent=2, ensure_ascii=False)
    except:
        pass


if __name__ == "__main__":
    main()
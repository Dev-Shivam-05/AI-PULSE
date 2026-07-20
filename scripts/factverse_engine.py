"""
==========================================================
  FACTVERSE ULTIMATE ENGINE v6.0 — SPEED OPTIMIZED
  Optimized for: 12GB RAM, No GPU, Windows 11
  
  ✅ 720p processing (YouTube re-encodes, looks same)
  ✅ 2 clips per scene (variety without slowness)
  ✅ Ultrafast encoding (15-20 min per video)
  ✅ Crash-proof (handles all timeouts gracefully)
  ✅ 3 Smart Shorts per video (best moments)
  ✅ Long video uploads FIRST → URL in Shorts
  ✅ Professional thumbnails (Pillow)
  ✅ YouTube + Instagram auto-upload
  ✅ Research-based optimal posting schedule
  ✅ 20+ SEO tags per video
  
  COST: ₹0 FOREVER
==========================================================
"""

import os, sys, json, time, random, subprocess, requests, re
import pickle, textwrap, math, shutil
from datetime import datetime
from pathlib import Path

# ============================================================
# CONFIG
# ============================================================
# Portable bootstrap — resolves project base, secrets (.env), ffmpeg + dirs.
# See factverse/config.py. No more hard-coded C:/FactVerse.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from factverse import config as fv

CONFIG     = fv.CONFIG
GEMINI_KEY = fv.GEMINI_KEY
PEXELS_KEY = fv.PEXELS_KEY

BASE   = fv.BASE
VIDEOS = fv.VIDEOS
SHORTS = fv.SHORTS
THUMBS = fv.THUMBS
TEMP   = fv.TEMP
MUSIC  = fv.MUSIC
FONTS  = fv.FONTS

VOICE  = fv.VOICE
RATE   = fv.RATE

_missing = fv.validate()
if _missing:
    print("⚠️  Missing prerequisites:", ", ".join(_missing))

# Brand (config-driven — rebrand in one place via config.json)
BRAND  = fv.CHANNEL_NAME
HANDLE = fv.CHANNEL_HANDLE

# SPEED OPTIMIZATION: 720p (YouTube re-encodes everything anyway)
WIDTH = 1280
HEIGHT = 720
FPS = 30
PRESET = "ultrafast"  # 10x faster than "fast" on CPU

# ============================================================
# SAFE SUBPROCESS — Never crashes on timeout
# ============================================================
def safe_run(cmd, timeout=600, label=""):
    """Run subprocess safely — returns True/False, never crashes"""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        if r.returncode != 0:
            # keep the last failure's stderr so unattended failures are diagnosable
            try:
                (fv.LOGS / "ffmpeg_error.log").write_text(
                    f"cmd: {' '.join(str(c) for c in cmd)[:500]}\n\n{(r.stderr or '')[-3000:]}",
                    encoding="utf-8")
            except Exception:
                pass
        return r.returncode == 0
    except subprocess.TimeoutExpired:
        # subprocess.run already killed the child on timeout
        print(f" ⏰timeout" if not label else f" ⏰{label} timeout")
        return False
    except Exception as e:
        print(f" ❌{e}" if not label else f" ❌{label}: {e}")
        return False


# ============================================================
# GEMINI AI
# ============================================================
def gemini(prompt, model="gemini-2.5-flash-lite", retries=3):
    # Delegate to the resilient, provider-agnostic facade (retry + model fallback).
    from factverse import llm
    return llm.generate(prompt, model=model, retries=retries)

def parse_json(text):
    if not text: return None
    text = text.strip()
    text = re.sub(r'^```(?:json)?\s*','',text)
    text = re.sub(r'\s*```$','',text)
    m = re.search(r'\{[\s\S]*\}', text)
    if m:
        try: return json.loads(m.group(0))
        except: return None
    return None

def dur(f):
    try:
        r = subprocess.run(["ffprobe","-v","quiet","-print_format","json","-show_format",str(f)],
                          capture_output=True, text=True, timeout=30)
        return float(json.loads(r.stdout)["format"]["duration"])
    except: return 0


# ============================================================
# TOPIC TRACKER
# ============================================================
USED_FILE = BASE / "used_topics.json"

def get_used():
    if USED_FILE.exists():
        try:
            with open(USED_FILE, encoding="utf-8") as f: return json.load(f)
        except Exception: return []
    return []

def save_used(t):
    u = get_used(); u.append(t); u = u[-300:]
    with open(USED_FILE,"w",encoding="utf-8") as f: json.dump(u,f,ensure_ascii=False)


# ============================================================
# STEP 1: TOPIC
# ============================================================
def step1_topic():
    print("\n[1/10] 🔍 Finding viral topic...")
    used = ", ".join(get_used()[-30:]) or "None"
    
    prompt = f"""YouTube strategist for "Fact Verse Official" (English facts/mystery channel).

Generate ONE unique viral topic. Categories: mysterious disappearances, dark history, unexplained science, forbidden places, unsolved mysteries, mind-blowing psychology, lost civilizations, creepy real events.

ALREADY USED (don't repeat): {used}

Must be: fascinating, click-worthy, 8-10 min content, English audience, NOT mainstream.
Return ONLY JSON: {{"topic":"title","angle":"unique angle","search_terms":["t1","t2","t3","t4","t5"]}}"""
    
    resp = gemini(prompt)
    if resp:
        try:
            data = parse_json(resp)
            if data and "topic" in data:
                print(f"  ✅ {data['topic']}")
                save_used(data['topic']); return data
        except: pass
    
    fb = {"topic":"The Village That Vanished Overnight — 600 People Gone",
          "angle":"Documented mass disappearances with no explanation",
          "search_terms":["abandoned village","ghost town","mystery","empty houses","foggy landscape"]}
    save_used(fb['topic']); print(f"  ✅ {fb['topic']}"); return fb


# ============================================================
# STEP 2: SCRIPT
# ============================================================
def step2_script(topic):
    print("\n[2/10] ✍️ Writing viral script...")
    
    prompt = f"""ELITE YouTube scriptwriter for "Fact Verse Official".

Topic: {topic['topic']}
Angle: {topic['angle']}

TITLE: Under 60 chars. Power words (Secret, Hidden, Terrifying, Impossible). Extreme curiosity gap.

DESCRIPTION: 200+ words. First 2 lines = hook + keyword. Timestamps every 2 min. "Subscribe to Fact Verse Official!" End with #FactVerse #Facts #Mystery

TAGS: Exactly 20 tags. Tag 1 = title. Tags 2-8 = topic keywords. Tags 9-14 = broader (mystery, science). Tags 15-20 = branding (fact verse, facts, mind blown).

VISUAL QUERIES: CRITICAL — each must be 2-3 SIMPLE words searchable on Pexels. ALL DIFFERENT. 
Good: "ocean waves", "dark forest", "ancient temple". Bad: "VFX glitching" (no results).

SCENES: 15-18 scenes. Each 50-80 words. Start with SHOCKING hook. Pattern interrupts every 60s. Build tension. Final scene = mind-blown + subscribe CTA.

Return ONLY JSON:
{{"title":"...","description":"...","tags":["tag1"..."tag20"],"scenes":[{{"scene_num":1,"narration":"50-80 words","visual_query":"2-3 words"}}]}}"""
    
    resp = gemini(prompt)
    if not resp:
        time.sleep(5); resp = gemini(prompt)
    if not resp: return None
    
    try:
        s = parse_json(resp)
        if not s or "scenes" not in s or len(s["scenes"]) < 5: return None
        
        if "title" not in s: s["title"] = topic["topic"][:60]
        if "description" not in s: s["description"] = f"Discover {topic['topic']}. Subscribe to Fact Verse Official!\n\n#FactVerse #Facts #Mystery"
        if "tags" not in s: s["tags"] = topic.get("search_terms",["facts"])
        
        brand = ["fact verse","fact verse official","facts","mystery","dark history",
                 "mind blown","education","did you know","unexplained","terrifying facts",
                 "scary facts","unknown facts","science facts","amazing facts","shocking facts"]
        existing = [t.lower() for t in s["tags"]]
        for b in brand:
            if b not in existing and len(s["tags"]) < 35: s["tags"].append(b)
        
        words = sum(len(sc.get("narration","").split()) for sc in s["scenes"])
        print(f"  ✅ Title: {s['title']}")
        print(f"  ✅ {len(s['scenes'])} scenes | {words} words | ~{words/150:.1f} min | {len(s['tags'])} tags")
        return s
    except: return None


# ============================================================
# STEP 3: DOWNLOAD STOCK VIDEOS (2 clips per scene — optimized)
# ============================================================
def _slug_score(v, qwords):
    """Relevance of a Pexels result: its page URL slug describes the clip's content."""
    slug = (v.get("url") or "").lower()
    return sum(1 for w in qwords if w in slug)

def dl_clips(query, out_dir, count=2):
    downloaded = []
    try:
        r = requests.get(
            f"https://api.pexels.com/videos/search?query={query}&per_page=15&size=medium&orientation=landscape",
            headers={"Authorization":PEXELS_KEY}, timeout=30)
        r.raise_for_status()
        vids = r.json().get("videos",[])
        # relevance first (slug ↔ query overlap), variety within the top matches
        qwords = [w for w in query.lower().split() if len(w) > 2]
        vids.sort(key=lambda v: _slug_score(v, qwords), reverse=True)
        top = vids[:max(count * 3, 6)]
        random.shuffle(top)
        vids = top + vids[len(top):]
        
        idx = 0
        for v in vids:
            if idx >= count: break
            # smallest rendition that still covers 720p — not the UHD original
            files = sorted(v.get("video_files",[]), key=lambda x:x.get("width",0))
            for f in files:
                if f.get("width",0) >= 960:
                    try:
                        dr = requests.get(f["link"], timeout=60)
                        if dr.status_code == 200 and len(dr.content) > 50000:
                            p = out_dir / f"clip_{idx}.mp4"
                            with open(p,"wb") as o: o.write(dr.content)
                            downloaded.append(str(p)); idx += 1; break
                    except: continue
    except: pass
    return downloaded

def step3_download(script):
    # 3 clips/scene ≈ a visual cut every 5-7s — modern retention pacing
    print("\n[3/10] 📥 Downloading stock videos (3 clips per scene)...")
    scene_clips = []

    for i, sc in enumerate(script["scenes"]):
        q = sc.get("visual_query","nature")
        sd = TEMP / f"sc_{i:03d}"
        sd.mkdir(exist_ok=True)
        print(f"  📥 {i+1}/{len(script['scenes'])}: '{q}'", end=" ")

        clips = dl_clips(q, sd, count=3)
        if not clips:
            for w in q.split():
                if len(w) > 3:
                    clips = dl_clips(w, sd, count=2)
                    if clips: break
        if not clips:
            for t in script.get("tags",["nature"])[:3]:
                clips = dl_clips(t, sd, count=1)
                if clips: break
        
        if clips: scene_clips.append(clips); print(f"✅ ({len(clips)})")
        else: scene_clips.append([]); print("⚠️")
        time.sleep(0.3)
    
    all_c = [c for cl in scene_clips for c in cl]
    for i in range(len(scene_clips)):
        if not scene_clips[i] and all_c:
            scene_clips[i] = [random.choice(all_c)]
    
    total = sum(len(c) for c in scene_clips)
    print(f"  ✅ {total} clips for {len(script['scenes'])} scenes")
    return scene_clips


# ============================================================
# STEP 4: VOICEOVER
# ============================================================
def step4_voice(script):
    print("\n[4/10] 🎙️ Generating voiceover + subtitles...")
    narration = " . . . ".join(sc.get("narration","") for sc in script["scenes"])
    
    nf = TEMP / "narration.txt"
    with open(nf,"w",encoding="utf-8") as f: f.write(narration)
    
    audio = TEMP / "voice.mp3"
    srt = TEMP / "voice.srt"
    
    ok = safe_run(["edge-tts","--voice",VOICE,"--rate",RATE,
                   "--file",str(nf),"--write-media",str(audio),
                   "--write-subtitles",str(srt)], timeout=300)
    
    if ok and audio.exists():
        mb = audio.stat().st_size/(1024*1024)
        d = dur(str(audio))
        print(f"  ✅ Voice: {mb:.1f}MB | {d:.0f}s | Subtitles: ✅")
        return str(audio), str(srt)
    print("  ❌ Voice failed"); return None, None


# ============================================================
# STEP 5: BUILD VIDEO (SPEED OPTIMIZED)
# ============================================================
def step5_build(script, scene_clips, audio_path, srt_path, scene_durs=None):
    print("\n[5/10] 🎬 Building video (720p, ultrafast)...")

    adur = dur(audio_path)
    if adur <= 0: print("  ❌ Can't read audio"); return None
    print(f"  ⏱️ Audio: {adur:.0f}s ({adur/60:.1f} min)")

    num = len(scene_clips)
    # Per-scene durations from real narration timing (visuals track the story);
    # uniform split remains the fallback.
    if scene_durs and len(scene_durs) == num:
        print(f"  📐 {num} scenes, narration-synced durations")
    else:
        scene_durs = [adur / num] * num
        print(f"  📐 {num} scenes × {adur/num:.1f}s each (uniform)")

    # Clear stale segments from any earlier run sharing this temp dir
    for stale in list(TEMP.glob("seg_*.ts")) + list(TEMP.glob("sub_*.ts")):
        try: stale.unlink()
        except OSError: pass

    # Build scene segments
    segments = []
    for i, clips in enumerate(scene_clips):
        seg = TEMP / f"seg_{i:03d}.ts"
        sdur = scene_durs[i]

        if not clips:
            continue

        if len(clips) == 1:
            cd = dur(clips[0])
            if cd <= 0: cd = 5
            loops = max(0, int(math.ceil(sdur/cd)) - 1)
            
            ok = safe_run([
                "ffmpeg","-y","-stream_loop",str(loops),
                "-i",clips[0],"-t",str(sdur),
                "-vf",f"scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=decrease,pad={WIDTH}:{HEIGHT}:(ow-iw)/2:(oh-ih)/2:black,setsar=1,fps={FPS}",
                "-c:v","libx264","-preset",PRESET,"-crf","23",
                "-an","-f","mpegts",str(seg)
            ], timeout=600, label=f"seg{i}")
            
        else:
            # Multiple clips — join for variety
            clip_dur = sdur / len(clips)
            subs = []
            
            for j, clip in enumerate(clips):
                sub = TEMP / f"sub_{i:03d}_{j}.ts"
                cd = dur(clip)
                if cd <= 0: cd = 5
                loops = max(0, int(math.ceil(clip_dur/cd)) - 1)
                
                ok = safe_run([
                    "ffmpeg","-y","-stream_loop",str(loops),
                    "-i",clip,"-t",str(clip_dur),
                    "-vf",f"scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=decrease,pad={WIDTH}:{HEIGHT}:(ow-iw)/2:(oh-ih)/2:black,setsar=1,fps={FPS}",
                    "-c:v","libx264","-preset",PRESET,"-crf","23",
                    "-an","-f","mpegts",str(sub)
                ], timeout=600, label=f"sub{i}_{j}")
                
                if sub.exists() and sub.stat().st_size > 1000:
                    subs.append(str(sub))
            
            if subs:
                ci = "concat:" + "|".join(subs)
                safe_run(["ffmpeg","-y","-i",ci,"-c","copy","-f","mpegts",str(seg)],
                        timeout=300)
        
        if seg.exists() and seg.stat().st_size > 1000:
            segments.append(str(seg))
            print(f"  ✅ Scene {i+1}/{num}", end="\r")
    
    print(f"  ✅ {len(segments)}/{num} segments ready        ")
    
    if not segments:
        print("  ❌ No segments!"); return None
    
    # Join scenes — stream-copy first (zero quality loss, near-instant);
    # re-encode only if the copy concat fails.
    print("  🔗 Joining scenes...")
    joined = TEMP / "joined.mp4"
    cf = TEMP / "concat.txt"
    with open(cf,"w") as f:
        for s in segments: f.write(f"file '{s}'\n")

    # NOTE: do NOT be tempted by `-c copy` here. Copy-concat of these TS segments
    # produces a file that REPORTS the right duration but has non-monotonic PTS,
    # so the final mux silently drops most frames (verified: 536s -> 130s).
    # Decoding + re-encoding normalizes timestamps and is the only reliable join.
    expected = sum(dur(s) for s in segments) or adur
    def _join_ok():
        return (joined.exists() and joined.stat().st_size > 100000
                and abs(dur(str(joined)) - expected) <= max(8, expected * 0.05))

    safe_run(["ffmpeg","-y","-f","concat","-safe","0","-i",str(cf),
              "-c:v","libx264","-preset",PRESET,"-crf","23","-an",
              str(joined)], timeout=900)
    if not _join_ok():
        print("  ❌ Join produced wrong duration!"); return None
    
    if not joined.exists():
        ci = "concat:" + "|".join(segments)
        safe_run(["ffmpeg","-y","-i",ci,"-c:v","libx264","-preset",PRESET,
                  "-crf","25","-r",str(FPS),"-an",str(joined)], timeout=600)
    
    if not joined.exists():
        print("  ❌ Join failed!"); return None
    
    # Final: video + audio + music
    print("  🎵 Adding voiceover + music...")
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    st = re.sub(r'[^\w\s-]','',script.get('title','video'))[:50].strip().replace(' ','_')
    final = VIDEOS / f"{st}_{ts}.mp4"
    
    bgm = MUSIC / "bg_music.mp3"
    if not bgm.exists():
        tracks = sorted(MUSIC.glob("*.mp3"))
        if tracks:
            bgm = random.choice(tracks)

    if bgm.exists():
        ok = safe_run([
            "ffmpeg","-y","-i",str(joined),"-i",str(audio_path),"-i",str(bgm),
            "-filter_complex",
            f"[0:v]trim=0:{adur},setpts=PTS-STARTPTS[v];"
            f"[1:a]aformat=fltp:44100:stereo,volume=1.0[voice];"
            f"[2:a]aloop=loop=-1:size=2e+09,atrim=0:{adur},aformat=fltp:44100:stereo,volume=0.07[music];"
            f"[voice][music]amix=inputs=2:duration=first:dropout_transition=3[a]",
            "-map","[v]","-map","[a]",
            "-c:v","libx264","-preset","fast","-crf","22",
            "-c:a","aac","-b:a","192k","-movflags","+faststart","-shortest",
            str(final)
        ], timeout=1200)
    else:
        ok = safe_run([
            "ffmpeg","-y","-i",str(joined),"-i",str(audio_path),
            "-filter_complex",
            f"[0:v]trim=0:{adur},setpts=PTS-STARTPTS[v];"
            f"[1:a]aformat=fltp:44100:stereo[a]",
            "-map","[v]","-map","[a]",
            "-c:v","libx264","-preset","fast","-crf","22",
            "-c:a","aac","-b:a","192k","-movflags","+faststart","-shortest",
            str(final)
        ], timeout=1200)
    
    if ok and final.exists() and final.stat().st_size > 100000:
        mb = final.stat().st_size/(1024*1024)
        d = dur(str(final))
        if abs(d - adur) > max(10, adur * 0.10):
            print(f"  ❌ Mux truncated the video ({d:.0f}s vs narration {adur:.0f}s)!")
            return None
        print(f"  ✅ Video: {final}")
        print(f"  ✅ {mb:.1f}MB | {d:.0f}s ({d/60:.1f} min)")
        return str(final)
    
    # Fallback
    safe_run(["ffmpeg","-y","-i",str(joined),"-i",str(audio_path),
              "-c:v","libx264","-preset",PRESET,"-crf","23",
              "-c:a","aac","-b:a","128k","-shortest","-t",str(adur),
              str(final)], timeout=1200)
    
    if final.exists():
        print(f"  ✅ Video (simple): {final}"); return str(final)
    print("  ❌ Failed"); return None


# ============================================================
# STEP 5B: SUBTITLES
# ============================================================
def step5b_subs(video, srt):
    print("  📝 Burning subtitles...")
    out = str(video).replace(".mp4","_sub.mp4")
    # Run ffmpeg FROM the .srt's folder and reference it by bare filename. This
    # avoids the Windows drive-colon escaping that breaks the subtitles filter.
    srt_path = Path(srt)
    work = str(srt_path.parent)
    rel = srt_path.name

    style = "FontName=Arial,FontSize=18,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BackColour=&H96000000,BorderStyle=4,Outline=1,Shadow=0,MarginV=40,Alignment=2,Bold=1"

    ok = False
    try:
        r = subprocess.run(
            ["ffmpeg","-y","-i",str(video),
             "-vf",f"subtitles={rel}:force_style='{style}'",
             "-c:v","libx264","-preset","fast","-crf","22",
             "-c:a","copy","-movflags","+faststart", out],
            cwd=work, capture_output=True, text=True, timeout=1200)
        ok = r.returncode == 0
        if not ok:
            try: (fv.LOGS / "subs_error.log").write_text((r.stderr or "")[-2000:], encoding="utf-8")
            except Exception: pass
    except Exception as e:
        print(f"   ⚠️ subs exception: {e}")

    if ok and os.path.exists(out) and os.path.getsize(out)>100000:
        os.replace(out, video)  # atomic: never leaves us with zero copies
        print("  ✅ Subtitles burned!")
        return video

    if os.path.exists(out):
        try: os.remove(out)
        except: pass

    srt_copy = str(video).replace(".mp4",".srt")
    try: shutil.copy2(srt, srt_copy)
    except: pass
    print("  ⚠️ Burn failed — SRT saved (see logs/subs_error.log)")
    return video


# ============================================================
# STEP 6: SMART SHORTS (Best moments + CTA)
# ============================================================
def find_best_moments(script):
    print("  🧠 AI finding best moments for Shorts...")
    all_n = "\n".join(f"[Scene {i+1}]: {sc.get('narration','')}" for i,sc in enumerate(script["scenes"]))
    
    prompt = f"""Viral Shorts expert. Find 3 MOST EXCITING moments from this script.

{all_n}

Rules:
- DO NOT pick Scene 1 (intro is boring for Shorts)
- Pick SHOCKING reveals, SURPRISING facts, DRAMATIC cliffhangers
- Each must create CURIOSITY to watch full video
- Pick from different parts: early (3-5), middle (7-10), near end (12-15)
- Write HOOK TEXT (5-8 words) for text overlay in first 2 seconds

Return ONLY JSON:
{{"moments":[
  {{"scene_num":4,"hook_text":"Scientists couldn't explain THIS"}},
  {{"scene_num":8,"hook_text":"Nobody survived to tell"}},
  {{"scene_num":13,"hook_text":"The truth is TERRIFYING"}}
]}}"""
    
    resp = gemini(prompt, model="gemini-2.5-flash-lite")
    if resp:
        try:
            d = parse_json(resp)
            if d and "moments" in d:
                print(f"  ✅ {len(d['moments'])} exciting moments found")
                return d["moments"]
        except: pass
    
    total = len(script["scenes"])
    return [
        {"scene_num":max(3,total//4),"hook_text":"You won't believe this"},
        {"scene_num":max(5,total//2),"hook_text":"This changes everything"},
        {"scene_num":max(7,total-3),"hook_text":"The shocking truth"}
    ]


def step6_shorts(video_path, script):
    print("\n[6/10] 📱 Creating 3 SMART Shorts (best moments + CTA)...")
    
    vdur = dur(video_path)
    if vdur <= 0: return []
    
    num_sc = len(script.get("scenes",[]))
    if num_sc <= 0: return []
    
    scene_dur = vdur / num_sc
    moments = find_best_moments(script)
    shorts = []
    
    for idx, m in enumerate(moments[:3]):
        sn = max(1, min(m.get("scene_num",3), num_sc))
        hook = m.get("hook_text","Watch this!")
        
        start = max(0, (sn-1) * scene_dur)
        length = min(55, vdur - start)
        if length < 15:
            start = max(0, start - 30)
            length = min(55, vdur - start)
        if length < 15: continue
        
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        sp = SHORTS / f"short_{idx+1}_{ts}.mp4"
        
        print(f"  📱 Short {idx+1}/3: Scene {sn} — '{hook}'")
        
        # Escape for FFmpeg
        he = hook.replace("'","").replace('"','').replace(":","\\:").replace("%","%%")
        
        # Video filter with hook text + channel name + CTA
        vf = (
            f"crop=ih*9/16:ih:(iw-ih*9/16)/2:0,"
            f"scale=1080:1920,setsar=1,"
            f"drawtext=text='{he}':"
            f"fontsize=48:fontcolor=white:borderw=3:bordercolor=black:"
            f"x=(w-text_w)/2:y=h/6:enable='between(t,0,3.5)',"
            f"drawtext=text='{BRAND}':"
            f"fontsize=26:fontcolor=white:borderw=2:bordercolor=black:x=20:y=30,"
            f"drawtext=text='Full Video - Link in Description!':"
            f"fontsize=32:fontcolor=yellow:borderw=2:bordercolor=black:"
            f"x=(w-text_w)/2:y=h*5/6:enable='gt(t,{length-6})',"
            f"drawtext=text='Subscribe for More!':"
            f"fontsize=28:fontcolor=red:borderw=2:bordercolor=white:"
            f"x=(w-text_w)/2:y=h*5/6+40:enable='gt(t,{length-5})'"
        )
        
        # -ss BEFORE -i (input seeking): timestamps reset to 0 so the drawtext
        # enable= windows actually match the cut, and seeking is fast.
        ok = safe_run([
            "ffmpeg","-y",
            "-ss",str(start),"-i",str(video_path),"-t",str(length),
            "-vf",vf,
            "-c:v","libx264","-preset","fast","-crf","22",
            "-c:a","aac","-b:a","128k","-movflags","+faststart",
            str(sp)
        ], timeout=600)

        if not ok or not sp.exists():
            # Fallback without text
            safe_run([
                "ffmpeg","-y",
                "-ss",str(start),"-i",str(video_path),"-t",str(length),
                "-vf","crop=ih*9/16:ih:(iw-ih*9/16)/2:0,scale=1080:1920",
                "-c:v","libx264","-preset","fast","-crf","22",
                "-c:a","aac","-b:a","128k",str(sp)
            ], timeout=600)
        
        if sp.exists() and sp.stat().st_size > 10000:
            mb = sp.stat().st_size/(1024*1024)
            print(f"    ✅ {sp.name} ({mb:.1f}MB)")
            shorts.append(str(sp))
        else:
            print(f"    ❌ Failed")
    
    print(f"  ✅ {len(shorts)} Smart Shorts created")
    return shorts


# ============================================================
# STEP 7: PROFESSIONAL THUMBNAIL
# ============================================================
def step7_thumb(video_path, title, thumb_text=None):
    """Thumbnail. `thumb_text` (2-4 punchy words) beats a full wrapped title for CTR;
    the title is only the fallback when no thumb_text was generated."""
    print("\n[7/10] 🖼️ Creating professional thumbnail...")
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    thumb = THUMBS / f"thumb_{ts}.jpg"
    frame = TEMP / "frame.jpg"
    
    d = dur(video_path)
    seek = max(3, d*0.2)
    
    safe_run(["ffmpeg","-y","-i",str(video_path),"-ss",str(seek),
              "-vframes","1","-vf","scale=1280:720","-q:v","2",str(frame)], timeout=60)
    
    if not frame.exists():
        safe_run(["ffmpeg","-y","-i",str(video_path),"-ss","10",
                  "-vframes","1","-vf","scale=1280:720","-q:v","2",str(frame)], timeout=60)
    
    try:
        from PIL import Image, ImageDraw, ImageFont, ImageEnhance
        
        img = Image.open(str(frame)).convert("RGB") if frame.exists() else Image.new("RGB",(1280,720),(15,15,40))
        img = img.resize((1280,720), Image.LANCZOS)
        
        img = ImageEnhance.Contrast(img).enhance(1.35)
        img = ImageEnhance.Color(img).enhance(1.5)
        img = ImageEnhance.Brightness(img).enhance(1.05)
        img = ImageEnhance.Sharpness(img).enhance(1.2)
        
        draw = ImageDraw.Draw(img, "RGBA")
        
        # Gradient overlay bottom 60%
        for y in range(280,720):
            a = int(220*((y-280)/(720-280)))
            draw.rectangle([(0,y),(1280,y+1)], fill=(0,0,0,a))
        
        # Top dark strip
        draw.rectangle([(0,0),(1280,85)], fill=(0,0,0,180))
        # Bottom red bar
        draw.rectangle([(0,712),(1280,720)], fill=(220,20,20,255))
        # Left red accent
        draw.rectangle([(0,85),(6,710)], fill=(220,20,20,255))
        
        # Font
        fl = fs = fb = None
        for fp in [str(FONTS/"Montserrat-Bold.ttf"),"C:/Windows/Fonts/arialbd.ttf",
                    "C:/Windows/Fonts/impact.ttf","C:/Windows/Fonts/arial.ttf",
                    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"]:
            try:
                fl = ImageFont.truetype(fp,64)
                fs = ImageFont.truetype(fp,34)
                fb = ImageFont.truetype(fp,30)
                break
            except: continue
        if not fl: fl=fs=fb=ImageFont.load_default()
        
        # Headline text: short punchy thumb_text (huge) beats the full title (small)
        if thumb_text:
            big = None
            for fp in [str(FONTS/"Montserrat-Bold.ttf"),"C:/Windows/Fonts/arialbd.ttf",
                        "C:/Windows/Fonts/impact.ttf",
                        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"]:
                try: big = ImageFont.truetype(fp, 108); break
                except: continue
            big = big or fl
            lines = textwrap.wrap(thumb_text.upper(), width=13)[:2]
            fl_use, line_h, y = big, 122, (430 if len(lines) == 1 else 350)
        else:
            lines = textwrap.wrap(title, width=20)[:3]
            fl_use, line_h, y = fl, 76, 380
        for line in lines:
            bb = draw.textbbox((0,0),line,font=fl_use)
            tw = bb[2]-bb[0]
            x = (1280-tw)//2
            # Shadow
            draw.text((x+4,y+4),line,font=fl_use,fill=(0,0,0,255))
            # Outline
            for ox in range(-3,4):
                for oy in range(-3,4):
                    if abs(ox)+abs(oy)>0:
                        draw.text((x+ox,y+oy),line,font=fl_use,fill=(0,0,0,220))
            # High-visibility yellow-on-dark (highest thumbnail contrast combo)
            draw.text((x,y),line,font=fl_use,fill=(255,214,10,255) if thumb_text else (255,255,255,255))
            y += line_h
        
        # Branding: red circle + play button + name
        draw.ellipse([(15,25),(45,55)], fill=(220,20,20,255))
        draw.polygon([(25,30),(25,50),(40,40)], fill=(255,255,255,255))
        draw.text((55,27),BRAND.upper(),font=fb,fill=(255,255,255,240))
        
        # MUST WATCH badge
        badge = "MUST WATCH"
        bb = draw.textbbox((0,0),badge,font=fs)
        bw = bb[2]-bb[0]
        draw.rectangle([(1280-bw-50,15),(1280-15,65)], fill=(220,20,20,240))
        draw.text((1280-bw-35,18),badge,font=fs,fill=(255,255,255,255))
        
        
        img.save(str(thumb),"JPEG",quality=95)
        print(f"  ✅ Thumbnail: {thumb}")
        if frame.exists(): frame.unlink()
        return str(thumb)
    
    except Exception as e:
        print(f"  ⚠️ Pillow: {e}")
    
    # FFmpeg fallback
    safe_run(["ffmpeg","-y","-i",str(video_path),"-ss",str(seek),"-vframes","1",
              "-vf","scale=1280:720,eq=contrast=1.3:saturation=1.4","-q:v","2",
              str(thumb)], timeout=60)
    
    if thumb.exists(): print(f"  ✅ Thumbnail: {thumb}"); return str(thumb)
    return None


# ============================================================
# STEP 8: METADATA FOR SHORTS
# ============================================================
def step8_meta(script, n=3):
    print("\n[8/10] 📝 Generating metadata...")
    prompt = f"""Video: "{script['title']}"
Create metadata for {n} YouTube Shorts. Each DIFFERENT title under 90 chars with #Shorts + power words.
Each Instagram caption: hook emoji + 2 sentences + "Follow @{HANDLE}!" + 20 hashtags.
Return ONLY JSON:
{{"shorts_meta":[{{"title":"...#Shorts","description":"...","instagram_caption":"..."}}]}}"""
    
    resp = gemini(prompt, model="gemini-2.5-flash-lite")
    if resp:
        try:
            d = parse_json(resp)
            if d and "shorts_meta" in d:
                print(f"  ✅ {len(d['shorts_meta'])} metadata sets")
                return d["shorts_meta"]
        except: pass
    
    return [{"title":f"{script['title'][:70]} Part {i+1} #Shorts",
             "description":f"🤖 {script['title']} — full breakdown on {BRAND}. #Shorts #AI #ArtificialIntelligence #TechNews",
             "instagram_caption":f"🤖 {script['title']}\nFollow @{HANDLE}!\n#ai #artificialintelligence #technews #machinelearning #tech"} for i in range(n)]


# ============================================================
# YOUTUBE UPLOAD (With retry)
# ============================================================
def yt_auth():
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    # analytics scope: nightly performance collector; force-ssl: posting the
    # shorts->full-video comment. One consent covers everything.
    SCOPES = ["https://www.googleapis.com/auth/youtube.upload",
              "https://www.googleapis.com/auth/youtube",
              "https://www.googleapis.com/auth/youtube.force-ssl",
              "https://www.googleapis.com/auth/yt-analytics.readonly"]
    creds = None
    tok = BASE/"youtube_token.pickle"
    secret = BASE/"client_secret.json"
    
    if tok.exists():
        with open(tok,"rb") as f: creds = pickle.load(f)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try: creds.refresh(Request())
            except: creds = None
        if not creds:
            if os.environ.get("GITHUB_ACTIONS") or os.environ.get("CI"):
                # Headless runner: an interactive OAuth flow would hang until the job
                # timeout. Fail fast and loudly so the alert fires instead.
                print("  ❌ YouTube token invalid/expired and cannot re-auth headlessly.")
                print("     Fix: run `python scripts/factverse_engine.py auth` locally,")
                print("     then update the YT_TOKEN_B64 GitHub secret.")
                return None
            if not secret.exists():
                print("  ❌ client_secret.json missing!"); return None
            flow = InstalledAppFlow.from_client_secrets_file(str(secret), SCOPES)
            creds = flow.run_local_server(port=8090, prompt="consent")
        with open(tok,"wb") as f: pickle.dump(creds,f)
    return creds

def yt_upload(path, title, desc, tags, thumb=None, is_short=False, retries=3):
    label = "Short" if is_short else "Video"
    print(f"\n  📤 {label} → YouTube...", end=" ")
    try:
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload
        
        creds = yt_auth()
        if not creds: print("❌ Auth failed"); return None
        
        yt = build("youtube","v3",credentials=creds)
        title = re.sub(r'[<>]', '', str(title))
        if is_short and "#Shorts" not in title: title = title[:90]+" #Shorts"

        # Fix tags: remove special chars, limit total to 500 chars (YouTube limit)
        clean_tags = []
        total_chars = 0
        for t in tags:
            t = str(t).strip()
            t = re.sub(r'[^a-zA-Z0-9 ]', '', t).strip()
            if len(t) < 2: continue
            if len(t) > 50: t = t[:50]
            if total_chars + len(t) > 400: break
            clean_tags.append(t)
            total_chars += len(t)

        # YouTube's description limit is 5000 BYTES — truncate on bytes, keep valid UTF-8
        desc_b = re.sub(r'[<>]', '', str(desc)).encode("utf-8")[:4900]
        desc = desc_b.decode("utf-8", errors="ignore")

        body = {"snippet":{"title":title[:100],"description":desc,
                           "tags":clean_tags,"categoryId":"28",
                           "defaultLanguage":"en","defaultAudioLanguage":"en"},
                "status":{"privacyStatus":"public","selfDeclaredMadeForKids":False}}
        # YouTube's synthetic-media disclosure is REQUIRED only for realistic
        # altered content (fabricated people/events). Narrated explainers over
        # licensed stock footage don't meet that bar, and the "AI" badge costs
        # viewer trust — so disclosure is opt-in via config.
        if fv.flag("declare_synthetic_media", False):
            body["status"]["containsSyntheticMedia"] = True

        for attempt in range(retries):
            try:
                media = MediaFileUpload(path,mimetype="video/mp4",resumable=True,chunksize=5*1024*1024)
                req = yt.videos().insert(part="snippet,status",body=body,media_body=media)
                resp = None
                last = 0
                conn_retries = 0
                while resp is None:
                    try:
                        st, resp = req.next_chunk()
                        if st:
                            p = int(st.progress()*100)
                            if p >= last+10: print(f"{p}%",end=" "); last=p
                    except Exception as ce:
                        if ("10054" in str(ce) or "Connection" in str(ce)) and conn_retries < 12:
                            conn_retries += 1
                            print("↻",end=" "); time.sleep(5); continue
                        else: raise
                
                vid = resp["id"]
                url = f"https://youtube.com/watch?v={vid}"
                print(f"✅ {url}")
                
                if thumb and not is_short and os.path.exists(thumb):
                    try:
                        yt.thumbnails().set(videoId=vid,
                            media_body=MediaFileUpload(thumb,mimetype="image/jpeg")).execute()
                        print(f"  🖼️ Thumbnail uploaded ✅")
                    except: print(f"  🖼️ Verify channel: youtube.com/verify")
                return url
            except Exception as e:
                if attempt < retries-1:
                    w = (attempt+1)*20
                    print(f"\n  ⚠️ Retry {attempt+1} in {w}s...")
                    time.sleep(w)
                else: print(f"\n  ❌ {e}"); break
        return None
    except Exception as e:
        print(f"❌ {e}"); return None


def yt_comment(video_url, text):
    """Post a channel comment on a video (e.g. the full-video link on a Short).
    Best-effort: needs the youtube.force-ssl scope — if the current token predates
    that scope, this logs and moves on. Never fails the pipeline."""
    try:
        vid = video_url.split("v=")[-1].split("&")[0]
        from googleapiclient.discovery import build
        creds = yt_auth()
        if not creds: return None
        yt = build("youtube","v3",credentials=creds)
        yt.commentThreads().insert(part="snippet", body={
            "snippet": {"videoId": vid,
                        "topLevelComment": {"snippet": {"textOriginal": text[:9000]}}}
        }).execute()
        print(f"  💬 Comment posted on {vid}")
        return True
    except Exception as e:
        print(f"  💬 Comment skipped ({str(e)[:120]})")
        return None


# ============================================================
# INSTAGRAM UPLOAD
# ============================================================
def ig_upload(path, caption):
    # Credentials come from .env / environment ONLY — never from committed config.json
    user = fv.IG_USER
    pw = fv.IG_PASS
    if not user or not pw or "PASTE" in user: return None
    print(f"  📤 Reel → Instagram...",end=" ")
    try:
        from instagrapi import Client
        cl = Client()
        sess = BASE/"ig_session.json"
        if sess.exists(): cl.load_settings(str(sess)); cl.login(user,pw)
        else: cl.login(user,pw); cl.dump_settings(str(sess))
        cl.clip_upload(path, caption[:2200])
        print("✅"); return True
    except Exception as e: print(f"❌ {e}"); return None


# ============================================================
# REPORT
# ============================================================
def _rel(p):
    """Store paths relative to the project base — portable and machine-agnostic."""
    if not p: return p
    try: return Path(p).resolve().relative_to(BASE.resolve()).as_posix()
    except Exception: return str(p)

def save_report(script,video,shorts,thumb,meta,yt_url=None,yt_shorts=None,status=None):
    print("\n[9/10] 📊 Saving report...")
    if status is None:
        # honest default: publishing succeeded only if a URL came back
        status = "PUBLISHED" if yt_url else "RENDER_ONLY"
    report = {"timestamp":datetime.now().isoformat(),"title":script.get("title",""),
              "description":script.get("description",""),
              "tags":script.get("tags",[]),"video":_rel(video),
              "shorts":[_rel(s) for s in (shorts or [])],
              "thumbnail":_rel(thumb),"youtube_url":yt_url,"youtube_shorts":yt_shorts or [],
              "shorts_meta":meta,"format":script.get("format",""),"status":status}
    log = BASE/"output"/"production_log.json"
    logs = []
    if log.exists():
        try:
            with open(log,encoding="utf-8") as f: logs = json.load(f)
        except: logs = []
    logs.append(report)
    logs = logs[-400:]  # bounded: this file is committed by CI every day
    with open(log,"w",encoding="utf-8") as f: json.dump(logs,f,indent=2,ensure_ascii=False)
    print(f"  ✅ Saved [{status}] ({len(logs)} total)")
    return report


# ============================================================
# CLEANUP
# ============================================================
def cleanup():
    print("  🧹 Cleaning...",end=" ")
    c = 0
    for i in TEMP.rglob("*"):
        if i.is_file():
            try: i.unlink(); c+=1
            except: pass
    for i in sorted(TEMP.rglob("*"),reverse=True):
        if i.is_dir():
            try: i.rmdir()
            except: pass
    print(f"{c} files ✅")


# ============================================================
# ████ MAIN PIPELINE ████
# ============================================================
def run():
    start = time.time()
    print("\n"+"🚀"*30)
    print("  FACTVERSE v6.0 — GENERATING VIDEO")
    print("🚀"*30)
    
    topic = step1_topic()
    
    script = step2_script(topic)
    if not script:
        time.sleep(5); script = step2_script(topic)
    if not script: print("  ❌ Script failed"); return None
    
    with open(TEMP/"script.json","w",encoding="utf-8") as f:
        json.dump(script,f,indent=2,ensure_ascii=False)
    
    scene_clips = step3_download(script)
    
    audio, srt = step4_voice(script)
    if not audio: return None
    
    video = step5_build(script, scene_clips, audio, srt)
    if not video: return None
    
    if srt and os.path.exists(srt):
        video = step5b_subs(video, srt)
    
    shorts = step6_shorts(video, script)
    thumb = step7_thumb(video, script.get("title","Facts"))
    shorts_meta = step8_meta(script, len(shorts))
    
    print("\n[10/10] 📤 Publishing...")
    yt_url = None
    yt_short_urls = []
    
    if CONFIG.get("auto_upload_youtube", False):
        # LONG VIDEO FIRST → get URL for Shorts
        print("\n  📹 Long video first (for Shorts link)...")
        yt_url = yt_upload(video, script["title"], script["description"],
                          script.get("tags",[]), thumb)
        time.sleep(5)
        
        # ALL SHORTS with link to long video
        if shorts:
            for i, sp in enumerate(shorts):
                mi = shorts_meta[i] if i < len(shorts_meta) else shorts_meta[0]
                sd = mi.get("description","")
                if yt_url: sd = f"🎬 FULL VIDEO: {yt_url}\n\n{sd}"
                
                url = yt_upload(sp, mi.get("title",script["title"]+" #Shorts"),
                               sd, script.get("tags",[])+["Shorts"], is_short=True)
                if url: yt_short_urls.append(url)
                time.sleep(5)
    else:
        print("  📤 YouTube: OFF (set auto_upload_youtube=true)")
    
    # Instagram
    if shorts and CONFIG.get("auto_upload_instagram", False):
        for i, sp in enumerate(shorts):
            mi = shorts_meta[i] if i < len(shorts_meta) else shorts_meta[0]
            cap = mi.get("instagram_caption","")
            if yt_url: cap += f"\n\n🎬 Full video on YouTube: {yt_url}"
            ig_upload(sp, cap)
            time.sleep(10)
    
    report = save_report(script,video,shorts,thumb,shorts_meta,yt_url,yt_short_urls)
    cleanup()
    
    elapsed = time.time()-start
    m,s = int(elapsed//60), int(elapsed%60)
    
    print("\n"+"="*60)
    print("  ✅ COMPLETE!")
    print("="*60)
    print(f"  ⏱️ {m}m {s}s")
    print(f"  📹 {video}")
    print(f"  📱 {len(shorts)} shorts")
    print(f"  🖼️ {thumb}")
    print(f"  📋 {script['title']}")
    print(f"  🏷️ {len(script.get('tags',[]))} tags")
    if yt_url: print(f"  ▶️ {yt_url}")
    for i,u in enumerate(yt_short_urls): print(f"  ▶️ Short {i+1}: {u}")
    print("="*60)
    return report


# ============================================================
# BATCH
# ============================================================
def batch(n=3):
    print(f"\n  BATCH: {n} videos ({n*3} shorts)")
    ok = 0
    for i in range(n):
        print(f"\n{'🎬'*25}\n  VIDEO {i+1}/{n}\n{'🎬'*25}")
        if run(): ok += 1
        if i < n-1:
            w = random.randint(30,60)
            print(f"\n  ⏳ Next in {w}s...")
            time.sleep(w)
    print(f"\n  🏁 DONE: {ok}/{n} videos + {ok*3} shorts")


# ============================================================
# SCHEDULER (Research-based optimal times)
# ============================================================
# Best YouTube posting times (research):
# - Global English audience peaks: 12-3 PM EST
# - Indian audience: 6-9 PM IST = 12:30-3:30 PM EST
# - Weekend mornings also strong
# - Post 15-30 min BEFORE peak for processing time
#
# Our schedule (IST):
# 7:30 AM  → catches morning scrollers
# 11:30 AM → catches lunch break viewers
# 5:30 PM  → catches evening peak (biggest audience)
# 9:30 PM  → catches night owls

def schedule():
    vpr = CONFIG.get("videos_per_run", 2)
    
    # Research-optimized hours (IST)
    hours = CONFIG.get("schedule_hours", [7, 11, 17, 21])
    
    print(f"\n{'='*60}")
    print(f"  🤖 AUTO-SCHEDULER (Research-Optimized Times)")
    print(f"  Videos per run: {vpr}")
    print(f"  Schedule: {[f'{h}:30' for h in hours]}")
    print(f"  Daily output: {vpr*len(hours)} long + {vpr*len(hours)*3} shorts")
    print(f"  Ctrl+C to stop")
    print(f"{'='*60}")
    
    last = -1
    while True:
        now = datetime.now()
        h = now.hour
        if h in hours and h != last and now.minute >= 30:
            print(f"\n⏰ Scheduled run: {now.strftime('%Y-%m-%d %H:%M')}")
            batch(vpr)
            last = h
        time.sleep(60)


# ============================================================
# ENTRY
# ============================================================
_DEPRECATION = """
⛔ The legacy engine no longer runs content generation directly.

Its topic/script steps still produce the OLD mystery/facts content, which would
publish off-brand videos to the {brand} channel (and matches the exact profile
YouTube's inauthentic-content policy demonetizes).

Use the current pipeline instead:
    python -m factverse.ai_pipeline            # render only
    python -m factverse.ai_pipeline publish    # render + upload

(Engine render/upload functions remain in use as a library. If you truly need
the old behavior: `python scripts/factverse_engine.py legacy-run`.)
"""

if __name__ == "__main__":
    m = sys.argv[1].lower() if len(sys.argv) > 1 else ""
    if m == "auth":
        print("🔐 YouTube Auth...")
        c = yt_auth()
        if c: print("✅ Success!")
    elif m == "legacy-run": run()
    elif m == "legacy-batch": batch(int(sys.argv[2]) if len(sys.argv)>2 else 3)
    else:
        print(_DEPRECATION.format(brand=BRAND))
        sys.exit(2)

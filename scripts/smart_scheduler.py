"""
FACTVERSE SMART SCHEDULER
- Starts automatically when laptop turns ON
- Runs at scheduled times while laptop is ON
- If laptop was OFF during a scheduled time, runs IMMEDIATELY when turned ON
- You never touch this. Ever.
"""
import subprocess
import sys
import time
import json
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from factverse import config as fv

CONFIG_PATH = fv.BASE / "config.json"
LAST_RUN_FILE = fv.BASE / "last_run.json"
ENGINE = str(Path(__file__).resolve().parent / "factverse_engine.py")

def load_config():
    with open(CONFIG_PATH) as f:
        return json.load(f)

def get_last_runs():
    """Get timestamps of last runs"""
    if LAST_RUN_FILE.exists():
        try:
            with open(LAST_RUN_FILE, encoding="utf-8") as f:
                return json.load(f)
        except:
            pass
    return {}

def save_last_run(hour):
    """Save that we ran at this hour today"""
    runs = get_last_runs()
    today = datetime.now().strftime("%Y-%m-%d")
    if today not in runs:
        runs[today] = []
    if hour not in runs[today]:
        runs[today].append(hour)
    
    # Keep only last 7 days
    cutoff = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
    runs = {k: v for k, v in runs.items() if k >= cutoff}
    
    with open(LAST_RUN_FILE, "w") as f:
        json.dump(runs, f)

def already_ran_today(hour):
    """Check if we already ran at this hour today"""
    runs = get_last_runs()
    today = datetime.now().strftime("%Y-%m-%d")
    return hour in runs.get(today, [])

def run_engine():
    """Run the current AI pipeline for 1 video + 3 shorts."""
    print(f"\n{'🚀'*20}")
    print(f"  RUNNING AUTOMATION — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'🚀'*20}\n")

    try:
        # ai_pipeline exits non-zero on real failure, so this return value is honest.
        result = subprocess.run(
            [sys.executable, "-m", "factverse.ai_pipeline", "publish"],
            cwd=str(fv.BASE),
            timeout=5400,  # 90 min, matches CI
        )
        return result.returncode == 0
    except subprocess.TimeoutExpired:
        print("  ⏰ Timed out after 90 minutes")
        return False
    except Exception as e:
        print(f"  ❌ Error: {e}")
        return False

def main():
    config = load_config()
    hours = config.get("schedule_hours", [7, 11, 17, 21])
    
    print("=" * 55)
    print("  🤖 FACTVERSE SMART SCHEDULER")
    print("  Runs automatically. Zero manual work.")
    print(f"  Schedule: {[f'{h}:30' for h in hours]}")
    print("  Press Ctrl+C to stop")
    print("=" * 55)
    
    # SMART FEATURE: Check if we MISSED any scheduled runs
    # (laptop was OFF during scheduled time)
    now = datetime.now()
    current_hour = now.hour
    
    missed_runs = []
    for h in hours:
        if h < current_hour and not already_ran_today(h):
            missed_runs.append(h)
    
    if missed_runs:
        print(f"\n  ⚠️ Missed runs detected: {[f'{h}:30' for h in missed_runs]}")
        print(f"  🔄 Running missed automations now...")
        
        for h in missed_runs:
            print(f"\n  📌 Catching up: {h}:30 run...")
            success = run_engine()
            if success:
                save_last_run(h)
                print(f"  ✅ Catch-up for {h}:30 complete!")
            time.sleep(30)
    
    # MAIN LOOP: Check every minute
    print(f"\n  👁️ Monitoring schedule: {[f'{h}:30' for h in hours]}")
    print(f"  Current time: {now.strftime('%H:%M')}")
    
    while True:
        now = datetime.now()
        current_hour = now.hour
        current_minute = now.minute
        
        # Check if it's time to run (at :30 of scheduled hours)
        if current_hour in hours and current_minute >= 30 and current_minute < 35:
            if not already_ran_today(current_hour):
                print(f"\n  ⏰ Scheduled time! Running {current_hour}:30 automation...")
                success = run_engine()
                if success:
                    save_last_run(current_hour)
                    print(f"  ✅ {current_hour}:30 run complete!")
                else:
                    print(f"  ⚠️ {current_hour}:30 run had issues")
                    save_last_run(current_hour)  # Mark as done to avoid retry loop
        
        # Show status every 30 minutes
        if current_minute == 0 or current_minute == 30:
            today = datetime.now().strftime("%Y-%m-%d")
            done = get_last_runs().get(today, [])
            pending = [h for h in hours if h not in done]
            
            if current_minute == 0:  # Only print on the hour to avoid spam
                print(f"  [{now.strftime('%H:%M')}] Done today: {done} | Pending: {pending}")
        
        time.sleep(60)  # Check every minute


if __name__ == "__main__":
    main()
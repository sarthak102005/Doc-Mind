import os
import sys
import time
import json
from pathlib import Path
import psutil

summary_file = Path(r"D:\DocMind\benchmark\debug\dump_summary_remaining_both.json")
debug_dir = Path(r"D:\DocMind\benchmark\debug")

print("Waiting for background raw dump (remaining pages) to finish...")
sys.stdout.flush()

start_wait = time.time()
last_count = 0

while True:
    # Check if summary file exists and is valid JSON
    if summary_file.exists():
        try:
            with open(summary_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                if data.get("sample_1") and data.get("sample_1_scanned"):
                    print(f"\n[DONE] Summary file created after {time.time() - start_wait:.1f}s wait.")
                    break
        except Exception:
            pass

    # Count how many files currently in debug dir to show progress
    files = list(debug_dir.glob("sample_1*_p*.json"))
    if len(files) != last_count:
        last_count = len(files)
        # Find latest modified file
        latest = max(files, key=lambda f: f.stat().st_mtime)
        print(f"[{time.strftime('%H:%M:%S')}] {len(files)} page artifacts dumped. Latest: {latest.name}")
        sys.stdout.flush()

    time.sleep(10)

print("\nAll remaining pages processed!")

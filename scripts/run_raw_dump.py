import os
import sys
import time
import json
import subprocess
import argparse
from pathlib import Path
import psutil

def get_disk_free_gb():
    c_free = psutil.disk_usage("C:\\").free / (1024**3)
    d_free = psutil.disk_usage("D:\\").free / (1024**3)
    return round(c_free, 2), round(d_free, 2)

def run_page_subprocess(pdf_path: str, page_num: int, is_scanned: bool, timeout: int = 360):
    cmd = [
        r"D:\DocMind\backend\.venv\Scripts\python.exe",
        r"D:\DocMind\scripts\dump_single_page.py",
        "--pdf", pdf_path,
        "--page", str(page_num),
        "--out-dir", r"D:\DocMind\benchmark\debug"
    ]
    if is_scanned:
        cmd.append("--is-scanned")

    env = os.environ.copy()
    env["TEMP"] = r"D:\DocMind\.cache\tmp"
    env["TMP"] = r"D:\DocMind\.cache\tmp"
    env["HF_HOME"] = r"D:\DocMind\.cache\huggingface"
    env["TORCH_HOME"] = r"D:\DocMind\.cache\torch"
    env["DOCLING_ARTIFACTS_PATH"] = r"D:\DocMind\.cache\docling"
    env["OMP_NUM_THREADS"] = "2"

    t0 = time.time()
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env
    )

    peak_ws_bytes = 0
    p = psutil.Process(proc.pid)

    # Poll process memory while running
    while proc.poll() is None:
        try:
            ws = p.memory_info().rss
            if ws > peak_ws_bytes:
                peak_ws_bytes = ws
            # Also sum child processes if any
            for child in p.children(recursive=True):
                c_ws = child.memory_info().rss
                if c_ws + ws > peak_ws_bytes:
                    peak_ws_bytes = c_ws + ws
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

        if time.time() - t0 > timeout:
            proc.kill()
            return {
                "page": page_num,
                "success": False,
                "error": f"Timeout after {timeout}s",
                "elapsed_sec": round(time.time() - t0, 2),
                "peak_ram_mb": round(peak_ws_bytes / (1024 * 1024), 2),
            }
        time.sleep(0.5)

    stdout, stderr = proc.communicate()
    elapsed = time.time() - t0

    if proc.returncode != 0:
        return {
            "page": page_num,
            "success": False,
            "error": stderr or stdout,
            "elapsed_sec": round(elapsed, 2),
            "peak_ram_mb": round(peak_ws_bytes / (1024 * 1024), 2),
        }

    # Extract JSON summary line if present
    summary_data = {}
    for line in stdout.splitlines():
        if line.startswith("PAGE_DONE:"):
            try:
                summary_data = json.loads(line[len("PAGE_DONE:"):])
            except Exception:
                pass

    return {
        "page": page_num,
        "success": True,
        "elapsed_sec": round(elapsed, 2),
        "peak_ram_mb": round(peak_ws_bytes / (1024 * 1024), 2),
        "summary": summary_data,
        "stderr_warnings": [l for l in stderr.splitlines() if "warning" in l.lower()][:3]
    }

def process_document(pdf_name: str, is_scanned: bool, pages: list[int]):
    pdf_path = f"D:\\DocMind\\benchmark\\{pdf_name}"
    doc_label = "Scanned" if is_scanned else "Digital (Born-digital)"
    print(f"\n=======================================================")
    print(f"PROCESSING: {pdf_name} ({doc_label})")
    print(f"Target Pages: {pages}")
    print(f"=======================================================")

    c_before, d_before = get_disk_free_gb()
    print(f"Disk Free BEFORE: C: {c_before} GB | D: {d_before} GB")

    results = []
    for page in pages:
        print(f"\n>>> Starting Page {page} of {pdf_name}...")
        res = run_page_subprocess(pdf_path, page, is_scanned)
        results.append(res)
        status = "OK" if res["success"] else f"FAILED: {res.get('error')}"
        print(f">>> Finished Page {page}: {status} | Time: {res['elapsed_sec']}s | Peak RAM: {res['peak_ram_mb']} MB")

        # Check safety threshold after every page
        c_now, d_now = get_disk_free_gb()
        if c_now < 3.0:
            print(f"CRITICAL STOP: Drive C dropped to {c_now} GB (< 3.0 GB threshold)!")
            sys.exit(99)

    c_after, d_after = get_disk_free_gb()
    print(f"\nDisk Free AFTER {pdf_name}: C: {c_after} GB | D: {d_after} GB")
    return results

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["focus", "remaining", "all"], default="focus")
    parser.add_argument("--pdf-only", choices=["sample_1", "sample_1_scanned", "both"], default="both")
    args = parser.parse_args()

    if args.mode == "focus":
        pages = [2, 3, 4, 11]
    elif args.mode == "remaining":
        pages = [1, 5, 6, 7, 8, 9, 10, 12]
    else:
        pages = list(range(1, 13))

    print(f"Running Raw Dump Mode: {args.mode} on Pages: {pages} | Filter: {args.pdf_only}")
    
    res_digital = []
    res_scanned = []

    # 1. Process sample_1.pdf if requested
    if args.pdf_only in ["sample_1", "both"]:
        res_digital = process_document("sample_1.pdf", is_scanned=False, pages=pages)
        c_mid, _ = get_disk_free_gb()
        if c_mid < 3.0:
            print(f"CRITICAL STOP: Drive C dropped to {c_mid} GB before scanned PDF!")
            sys.exit(99)

    # 2. Process sample_1_scanned.pdf if requested
    if args.pdf_only in ["sample_1_scanned", "both"]:
        res_scanned = process_document("sample_1_scanned.pdf", is_scanned=True, pages=pages)

    # Output JSON summary for analysis
    summary = {
        "mode": args.mode,
        "pdf_only": args.pdf_only,
        "sample_1": res_digital,
        "sample_1_scanned": res_scanned
    }
    with open(f"D:\\DocMind\\benchmark\\debug\\dump_summary_{args.mode}_{args.pdf_only}.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print("\n=======================================================")
    print("ALL TARGET PAGES COMPLETED SUCCESSFULLY!")
    print("=======================================================")

if __name__ == "__main__":
    main()

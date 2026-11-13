"""Staged End-to-End Ingestion Runner (Step 6).

Runs the DocMind API (uvicorn) and Worker as separate operating system processes.
Ingests in order:
1. sample_1.pdf
2. sample_1_scanned_250dpi.pdf
3. sample_1_scanned.pdf

Monitors and reports:
- Per-stage times (profile, parse, tables, chunk, figures)
- Peak host RAM (MB) and peak GPU VRAM (MB)
- Final status (ready)
- Row counts in page_profiles and table_records in PostgreSQL
- Figure crops uploaded to MinIO
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import httpx
import psutil
import torch
from sqlalchemy import create_engine, text

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.config import get_settings
from app.services.storage import get_storage_service

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("e2e_staged")

DOCUMENTS_TO_INGEST = [
    ("sample_1.pdf", REPO_ROOT / "benchmark" / "sample_1.pdf"),
    ("sample_1_scanned_250dpi.pdf", REPO_ROOT / "benchmark" / "sample_1_scanned_250dpi.pdf"),
    ("sample_1_scanned.pdf", REPO_ROOT / "benchmark" / "sample_1_scanned.pdf"),
]

API_PORT = 8000
API_URL = f"http://127.0.0.1:{API_PORT}"


def get_gpu_vram_mb() -> float:
    """Get current GPU VRAM allocation in MB."""
    if torch.cuda.is_available():
        return torch.cuda.memory_allocated() / (1024 * 1024)
    return 0.0


def get_peak_gpu_vram_mb() -> float:
    """Get peak GPU VRAM allocation in MB."""
    if torch.cuda.is_available():
        return torch.cuda.max_memory_allocated() / (1024 * 1024)
    return 0.0


def get_system_ram_mb() -> float:
    """Get process tree RAM in MB."""
    mem = psutil.virtual_memory()
    return mem.used / (1024 * 1024)


def wait_for_api(timeout: float = 30.0) -> bool:
    """Wait until API responds on /health or /docs."""
    start = time.time()
    while time.time() - start < timeout:
        try:
            r = httpx.get(f"{API_URL}/health", timeout=6.0)
            if r.status_code in (200, 503):
                return True
        except Exception:
            pass
        time.sleep(0.5)
    return False


def get_db_counts(doc_id: str, db_url: str) -> tuple[int, int]:
    """Query row counts for page_profiles and table_records."""
    engine = create_engine(db_url)
    with engine.connect() as conn:
        prof_res = conn.execute(
            text("SELECT count(*) FROM page_profiles WHERE document_id = :d"),
            {"d": doc_id},
        )
        prof_count = prof_res.scalar() or 0

        tbl_res = conn.execute(
            text("SELECT count(*) FROM table_records WHERE document_id = :d"),
            {"d": doc_id},
        )
        tbl_count = tbl_res.scalar() or 0

    return int(prof_count), int(tbl_count)


def main() -> None:
    settings = get_settings()
    python_exe = sys.executable

    logger.info("Hardware Profile: %s (Local models on GPU: %s)", settings.hardware_profile, settings.local_models_on_gpu)
    logger.info("Postgres: %s, Redis: %s, Storage: %s", settings.postgres_host, settings.redis_backend, settings.storage_backend)

    if torch.cuda.is_available():
        torch.cuda.reset_peak_memory_stats()
        logger.info("CUDA Device: %s, Initial VRAM: %.2f MB", torch.cuda.get_device_name(0), get_gpu_vram_mb())

    debug_dir = REPO_ROOT / "benchmark" / "debug"
    debug_dir.mkdir(parents=True, exist_ok=True)
    api_log_file = open(debug_dir / "api_e2e.log", "w", encoding="utf-8")
    worker_log_file = open(debug_dir / "worker_e2e.log", "w", encoding="utf-8")

    # 1. Start API process
    logger.info("Starting API server process on port %d...", API_PORT)
    api_proc = subprocess.Popen(
        [python_exe, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(API_PORT)],
        cwd=str(BACKEND_DIR),
        stdout=api_log_file,
        stderr=subprocess.STDOUT,
        text=True,
    )

    # 2. Start Worker process
    logger.info("Starting Worker process...")
    worker_proc = subprocess.Popen(
        [python_exe, "-m", "app.worker"],
        cwd=str(BACKEND_DIR),
        stdout=worker_log_file,
        stderr=subprocess.STDOUT,
        text=True,
    )

    results: list[dict[str, Any]] = []

    try:
        # Wait for API to be ready
        if not wait_for_api(timeout=25.0):
            logger.error("API failed to become ready in 25s")
            return

        logger.info("API is live. Authenticating...")
        client = httpx.Client(base_url=API_URL, timeout=120.0)

        # Signup test admin user
        user_email = f"e2e_tester_{int(time.time())}@docmind.local"
        user_pw = "DocMindE2ETest123!"
        signup_resp = client.post(
            "/api/v1/auth/signup",
            json={"email": user_email, "password": user_pw, "full_name": "E2E Tester"},
        )
        if signup_resp.status_code == 201:
            token = signup_resp.json()["access_token"]
        else:
            login_resp = client.post(
                "/api/v1/auth/login",
                data={"username": user_email, "password": user_pw},
            )
            token = login_resp.json()["access_token"]

        headers = {"Authorization": f"Bearer {token}"}
        storage = get_storage_service()

        # Ingest documents in order
        for doc_name, pdf_path in DOCUMENTS_TO_INGEST:
            logger.info("=" * 60)
            logger.info("Ingesting staged test: %s (%s)", doc_name, pdf_path)
            assert pdf_path.exists(), f"File {pdf_path} not found"

            # Reset peak VRAM tracking
            if torch.cuda.is_available():
                torch.cuda.reset_peak_memory_stats()

            initial_ram = get_system_ram_mb()
            t0 = time.perf_counter()

            # Upload PDF
            with open(pdf_path, "rb") as f:
                up_resp = client.post(
                    "/api/v1/documents",
                    headers=headers,
                    files={"file": (doc_name, f, "application/pdf")},
                )

            assert up_resp.status_code == 201, f"Upload failed: {up_resp.text}"
            doc_data = up_resp.json()
            doc_id = doc_data["id"]
            logger.info("Uploaded %s -> document_id: %s (status: %s)", doc_name, doc_id, doc_data["status"])

            # Poll status until ready or failed
            final_status = "queued"
            stages_info: dict[str, Any] = {}
            stage_times: dict[str, Any] = {}

            peak_ram = initial_ram
            poll_start = time.time()

            while time.time() - poll_start < 240:
                current_ram = get_system_ram_mb()
                if current_ram > peak_ram:
                    peak_ram = current_ram

                st_resp = client.get(f"/api/v1/documents/{doc_id}/status", headers=headers)
                if st_resp.status_code == 200:
                    status_data = st_resp.json()
                    final_status = status_data["status"]
                    stages_info = status_data.get("stages", {})

                    if final_status in ("ready", "failed"):
                        break

                time.sleep(1.0)

            total_elapsed = time.perf_counter() - t0
            peak_vram = get_peak_gpu_vram_mb()

            # Get document details from DB/API
            detail_resp = client.get(f"/api/v1/documents/{doc_id}", headers=headers)
            detail_data = detail_resp.json() if detail_resp.status_code == 200 else {}
            meta_info = detail_data.get("meta_info", {})
            stage_durations = meta_info.get("stage_durations_ms", {})

            # Row counts in DB
            db_url = settings.sqlalchemy_database_url
            prof_count, tbl_count = get_db_counts(doc_id, db_url)

            # MinIO crops count
            crop_keys = storage.list_objects(prefix=f"figures/{doc_id}/")
            minio_crops = len(crop_keys)

            logger.info(
                "Completed %s: Status=%s, TotalTime=%.2fs, PeakRAM=%.1fMB, PeakVRAM=%.1fMB, PageProfiles=%d, TableRecords=%d, MinIOCrops=%d",
                doc_name,
                final_status,
                total_elapsed,
                peak_ram,
                peak_vram,
                prof_count,
                tbl_count,
                minio_crops,
            )

            results.append({
                "document": doc_name,
                "document_id": doc_id,
                "status": final_status,
                "total_time_s": round(total_elapsed, 2),
                "peak_ram_mb": round(peak_ram, 1),
                "peak_vram_mb": round(peak_vram, 1),
                "page_profiles_count": prof_count,
                "table_records_count": tbl_count,
                "minio_crops_count": minio_crops,
                "stage_durations_ms": stage_durations,
                "stages_status": stages_info,
            })

    finally:
        logger.info("Stopping Worker process...")
        worker_proc.terminate()
        try:
            worker_proc.wait(timeout=5)
        except Exception:
            worker_proc.kill()

        logger.info("Stopping API server process...")
        api_proc.terminate()
        try:
            api_proc.wait(timeout=5)
        except Exception:
            api_proc.kill()

        api_log_file.close()
        worker_log_file.close()

    # Output formatted report
    print("\n" + "=" * 90)
    print("STAGE 6: END-TO-END STAGED INGESTION REPORT (API + WORKER SEPARATE PROCESSES)")
    print("=" * 90)
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()

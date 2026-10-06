#!/usr/bin/env python3
"""Phase 1 End-to-End Verification Script (DocMind).

This script performs complete HTTP-based black-box verification of Phase 1:
1. Rejection of invalid files:
   - Text file renamed to .pdf
   - Oversized file (> 50 MB)
   - Password-protected PDF
2. Rate limiting check (expects 429 Too Many Requests after rapid requests)
3. User signup (User A and User B)
4. User A uploads benchmark/sample_1.pdf
5. Status polling until ready (recording all observed states: queued, processing, ready)
6. Security / multi-tenant isolation:
   - User B cannot list User A's document
   - User B cannot get User A's document (404)
   - User B cannot download User A's document (404)
   - User B cannot delete User A's document (403 or 404)
7. User A downloads via presigned URL and verifies byte size matches original
8. User A deletes the document
9. Verifies object is gone from MinIO and rows are gone from PostgreSQL
"""

from __future__ import annotations

import io
import os
import sys
import time
import uuid
from pathlib import Path

import httpx
import pypdf
from minio import Minio
from sqlalchemy import create_engine, text

REPO_ROOT = Path(__file__).resolve().parents[1]
SAMPLE_PDF = REPO_ROOT / "benchmark" / "sample_1.pdf"
API_BASE = os.environ.get("DOCMIND_API_URL", "http://127.0.0.1:8000")


def log(msg: str) -> None:
    print(f"[VERIFY] {msg}")


def fail(msg: str) -> None:
    print(f"\n[ERROR] VERIFICATION FAILED: {msg}", file=sys.stderr)
    sys.exit(1)


def create_encrypted_pdf() -> bytes:
    """Create a password-protected PDF in memory."""
    writer = pypdf.PdfWriter()
    writer.add_blank_page(width=72, height=72)
    writer.encrypt("topsecret123")
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def test_file_validation_rejections(client: httpx.Client, token_a: str) -> None:
    """Test rejection of non-PDF, oversized, and encrypted PDFs."""
    headers = {"Authorization": f"Bearer {token_a}"}
    log("Testing validation: text file renamed to .pdf...")
    fake_txt = b"Hello, this is not a valid PDF file. Just plain text."
    r = client.post(
        f"{API_BASE}/api/v1/documents",
        headers=headers,
        files={"file": ("fake.pdf", fake_txt, "application/pdf")},
    )
    if r.status_code != 400:
        fail(f"Expected 400 for fake PDF, got {r.status_code}: {r.text}")
    log("  -> Correctly rejected fake PDF with 400 Bad Request.")

    log("Testing validation: oversized file (>50MB)...")
    # 51 MB dummy payload with PDF header
    oversized_data = b"%PDF-1.4\n" + b"0" * (51 * 1024 * 1024)
    r = client.post(
        f"{API_BASE}/api/v1/documents",
        headers=headers,
        files={"file": ("oversized.pdf", oversized_data, "application/pdf")},
    )
    if r.status_code not in (400, 413):
        fail(f"Expected 400 or 413 for oversized file, got {r.status_code}: {r.text}")
    log(f"  -> Correctly rejected oversized file with {r.status_code}.")

    log("Testing validation: password-protected PDF...")
    enc_pdf = create_encrypted_pdf()
    r = client.post(
        f"{API_BASE}/api/v1/documents",
        headers=headers,
        files={"file": ("encrypted.pdf", enc_pdf, "application/pdf")},
    )
    if r.status_code != 400:
        fail(f"Expected 400 for encrypted PDF, got {r.status_code}: {r.text}")
    log("  -> Correctly rejected password-protected PDF with 400 Bad Request.")


def test_rate_limiter(client: httpx.Client) -> None:
    """Verify rate limiter returns 429 after rapid requests."""
    log("Testing rate limiter with rapid login attempts...")
    hit_429 = False
    for i in range(1, 20):
        r = client.post(
            f"{API_BASE}/api/v1/auth/login",
            json={
                "email": f"rate_limit_test_{i}@docmind.internal",
                "password": "wrongpassword",
            },
        )
        if r.status_code == 429:
            hit_429 = True
            log(f"  -> Hit 429 Too Many Requests on request #{i}.")
            break
        time.sleep(0.02)

    if not hit_429:
        fail("Rate limiter did not return 429 after rapid requests!")


def verify_phase1() -> None:
    if not SAMPLE_PDF.is_file():
        fail(f"Sample PDF not found at {SAMPLE_PDF}")

    original_pdf_bytes = SAMPLE_PDF.read_bytes()
    original_size = len(original_pdf_bytes)
    log(f"Starting Phase 1 verification against {API_BASE}")
    log(f"Sample PDF: {SAMPLE_PDF.name} ({original_size} bytes)")

    with httpx.Client(timeout=30.0) as client:
        # 1. Health check
        log("Checking API health...")
        try:
            r = client.get(f"{API_BASE}/health")
            if r.status_code != 200:
                fail(f"API health returned {r.status_code}: {r.text}")
        except Exception as exc:  # noqa: BLE001
            fail(f"Cannot reach API at {API_BASE}: {exc}")
        log("  -> API is healthy.")

        # 2. Rate limiter check
        test_rate_limiter(client)

        # 3. User A and User B signup
        nonce = uuid.uuid4().hex[:6]
        email_a = f"user_a_{nonce}@docmind.internal"
        email_b = f"user_b_{nonce}@docmind.internal"
        pw = "SuperSecurePassword123!"

        log(f"Signing up User A ({email_a})...")
        r_a = client.post(
            f"{API_BASE}/api/v1/auth/signup",
            json={"email": email_a, "password": pw, "full_name": "User Alpha"},
        )
        if r_a.status_code != 201:
            fail(f"Failed to sign up User A: {r_a.status_code} {r_a.text}")
        token_a = r_a.json()["access_token"]
        headers_a = {"Authorization": f"Bearer {token_a}"}

        log(f"Signing up User B ({email_b})...")
        r_b = client.post(
            f"{API_BASE}/api/v1/auth/signup",
            json={"email": email_b, "password": pw, "full_name": "User Beta"},
        )
        if r_b.status_code != 201:
            fail(f"Failed to sign up User B: {r_b.status_code} {r_b.text}")
        token_b = r_b.json()["access_token"]
        headers_b = {"Authorization": f"Bearer {token_b}"}

        # 4. Input validation checks
        test_file_validation_rejections(client, token_a)

        # 5. User A uploads sample_1.pdf
        log("User A uploading benchmark/sample_1.pdf...")
        upload_resp = client.post(
            f"{API_BASE}/api/v1/documents",
            headers=headers_a,
            files={"file": ("sample_1.pdf", original_pdf_bytes, "application/pdf")},
        )
        if upload_resp.status_code != 201:
            fail(f"Upload failed: {upload_resp.status_code} {upload_resp.text}")

        upload_data = upload_resp.json()
        doc_id = upload_data["id"]
        initial_status = upload_data["status"]
        log(f"  -> Uploaded successfully. Document ID: {doc_id}, initial status: {initial_status}")

        # 6. Polling until ready, recording every status
        statuses_seen: list[str] = [initial_status]
        start_time = time.time()
        timeout_seconds = 30.0
        log("Polling status until 'ready'...")

        while time.time() - start_time < timeout_seconds:
            status_resp = client.get(f"{API_BASE}/api/v1/documents/{doc_id}/status", headers=headers_a)
            if status_resp.status_code != 200:
                fail(f"Failed to query status: {status_resp.status_code} {status_resp.text}")
            cur_status = status_resp.json()["status"]
            if not statuses_seen or statuses_seen[-1] != cur_status:
                statuses_seen.append(cur_status)
                log(f"  -> Observed status: '{cur_status}'")

            if cur_status == "ready":
                break
            time.sleep(0.15)

        log(f"Recorded status sequence: {' -> '.join(statuses_seen)}")
        for required in ("queued", "processing", "ready"):
            if required not in statuses_seen:
                fail(f"Status '{required}' was not observed in sequence: {statuses_seen}")
        log("  -> All required statuses (queued, processing, ready) were observed!")

        # 7. User B tries to access User A's document
        log("Testing cross-user isolation: User B trying to access User A's document...")
        # List
        list_b = client.get(f"{API_BASE}/api/v1/documents", headers=headers_b)
        if list_b.status_code != 200:
            fail(f"User B list failed: {list_b.status_code}")
        b_doc_ids = [d["id"] for d in list_b.json()]
        if doc_id in b_doc_ids:
            fail("User B can see User A's document in document list!")
        log("  -> User B listing does NOT contain User A's document (PASS).")

        # Get
        get_b = client.get(f"{API_BASE}/api/v1/documents/{doc_id}", headers=headers_b)
        if get_b.status_code != 404:
            fail(f"Expected 404 for User B GET document, got {get_b.status_code}: {get_b.text}")
        log("  -> User B GET returns 404 Not Found (PASS).")

        # Status
        st_b = client.get(f"{API_BASE}/api/v1/documents/{doc_id}/status", headers=headers_b)
        if st_b.status_code != 404:
            fail(f"Expected 404 for User B GET status, got {st_b.status_code}: {st_b.text}")
        log("  -> User B GET status returns 404 Not Found (PASS).")

        # Delete
        del_b = client.delete(f"{API_BASE}/api/v1/documents/{doc_id}", headers=headers_b)
        if del_b.status_code not in (403, 404):
            fail(f"Expected 403/404 for User B DELETE document, got {del_b.status_code}: {del_b.text}")
        log(f"  -> User B DELETE returns {del_b.status_code} Forbidden/Not Found (PASS).")

        # 8. User A downloads via presigned URL and checks size
        log("User A retrieving presigned download URL...")
        detail_a = client.get(f"{API_BASE}/api/v1/documents/{doc_id}", headers=headers_a)
        if detail_a.status_code != 200:
            fail(f"User A GET detail failed: {detail_a.status_code}")
        download_url = detail_a.json().get("download_url")
        if not download_url:
            fail("No download_url returned for ready document!")

        log(f"Downloading file via presigned URL: {download_url[:60]}...")
        dl_resp = client.get(download_url)
        if dl_resp.status_code != 200:
            fail(f"Presigned download failed with status {dl_resp.status_code}")
        downloaded_size = len(dl_resp.content)
        if downloaded_size != original_size:
            fail(f"Downloaded size ({downloaded_size}) does not match original size ({original_size})")
        log(f"  -> Downloaded size ({downloaded_size} bytes) matches original exactly (PASS).")

        # 9. User A deletes the document
        log(f"User A deleting document {doc_id}...")
        del_a = client.delete(f"{API_BASE}/api/v1/documents/{doc_id}", headers=headers_a)
        if del_a.status_code != 200:
            fail(f"Delete document failed: {del_a.status_code} {del_a.text}")
        log("  -> Document deleted via API.")

        # Document must be gone from API
        check_gone = client.get(f"{API_BASE}/api/v1/documents/{doc_id}", headers=headers_a)
        if check_gone.status_code != 404:
            fail(f"Deleted document still accessible via API: {check_gone.status_code}")
        log("  -> API confirms document is 404 Not Found.")

    # 10. Direct storage and database inspection
    log("Verifying object is deleted from real MinIO bucket...")
    minio_client = Minio(
        endpoint=os.environ.get("MINIO_ENDPOINT", "localhost:9000"),
        access_key=os.environ.get("MINIO_ACCESS_KEY", "docmind"),
        secret_key=os.environ.get("MINIO_SECRET_KEY", "XP0T0DqoQ09hYznmXSa9AXewgEE34AlU"),
        secure=os.environ.get("MINIO_SECURE", "false").lower() == "true",
    )
    bucket = os.environ.get("MINIO_BUCKET", "docmind")
    expected_key = f"documents/{doc_id}/v1.pdf"
    try:
        minio_client.stat_object(bucket, expected_key)
        fail(f"Object {expected_key} STILL EXISTS in MinIO bucket {bucket}!")
    except Exception:  # noqa: BLE001
        log("  -> Confirmed: Object is completely removed from MinIO bucket.")

    log("Verifying rows are deleted from real PostgreSQL tables...")
    pg_url = os.environ.get(
        "DATABASE_URL",
        "postgresql+psycopg://docmind:RH08SthkSV91fb7tSGcVfMJY@localhost:5432/docmind",
    )
    pg_engine = create_engine(pg_url)
    with pg_engine.connect() as conn:
        for tbl in (
            "documents",
            "document_versions",
            "processing_statuses",
            "permissions",
        ):
            count = conn.execute(
                text(
                    f"SELECT COUNT(*) FROM {tbl} WHERE document_id = :id"
                    if tbl != "documents"
                    else f"SELECT COUNT(*) FROM {tbl} WHERE id = :id"
                ),
                {"id": doc_id},
            ).scalar()
            if count != 0:
                fail(f"Table {tbl} still has {count} rows for document_id {doc_id}!")
        log(
            "  -> Confirmed: All rows in documents, document_versions, "
            "processing_statuses, and permissions are gone from PostgreSQL."
        )

    print("\n" + "=" * 70)
    print("ALL PHASE 1 VERIFICATION CHECKS PASSED SUCCESSFULLY!")
    print("=" * 70)


if __name__ == "__main__":
    verify_phase1()

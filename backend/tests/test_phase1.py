"""Phase 1 acceptance test suite: Auth, Document Upload & Validation, Permissions, and Lifecycle."""

from __future__ import annotations

import io
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.worker.tasks import process_document_stub


def test_auth_flow(client: TestClient) -> None:
    """Verify signup, login, and profile fetching (/me)."""
    # 1. Signup
    signup_payload = {
        "email": "lead@nexus.internal",
        "password": "supersecretpassword",
        "full_name": "Team Nexus Lead",
    }
    signup_resp = client.post("/api/v1/auth/signup", json=signup_payload)
    assert signup_resp.status_code == 201, signup_resp.text
    signup_data = signup_resp.json()
    assert "access_token" in signup_data
    assert signup_data["user"]["email"] == "lead@nexus.internal"
    assert signup_data["user"]["role"] == "admin"  # First user gets admin

    # 2. Duplicate signup fails with 409
    dup_resp = client.post("/api/v1/auth/signup", json=signup_payload)
    assert dup_resp.status_code == 409

    # 3. Login with wrong password fails
    bad_login = client.post(
        "/api/v1/auth/login",
        json={"email": "lead@nexus.internal", "password": "wrongpassword"},
    )
    assert bad_login.status_code == 401

    # 4. Login with correct password
    login_resp = client.post(
        "/api/v1/auth/login",
        json={"email": "lead@nexus.internal", "password": "supersecretpassword"},
    )
    assert login_resp.status_code == 200
    token = login_resp.json()["access_token"]

    # 5. /me endpoint
    me_resp = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me_resp.status_code == 200
    me_data = me_resp.json()
    assert me_data["email"] == "lead@nexus.internal"
    assert me_data["full_name"] == "Team Nexus Lead"


def test_document_validation(client: TestClient) -> None:
    """Verify document upload validation (type, size, format)."""
    # Create user and get token
    signup_resp = client.post(
        "/api/v1/auth/signup",
        json={"email": "validator@test.internal", "password": "secretpassword123"},
    )
    token = signup_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Reject non-PDF file
    txt_file = io.BytesIO(b"Hello world, I am a plain text file")
    resp_txt = client.post(
        "/api/v1/documents",
        headers=headers,
        files={"file": ("readme.txt", txt_file, "text/plain")},
    )
    assert resp_txt.status_code == 400
    assert "PDF" in resp_txt.json()["detail"]

    # 2. Reject empty PDF
    empty_file = io.BytesIO(b"")
    resp_empty = client.post(
        "/api/v1/documents",
        headers=headers,
        files={"file": ("empty.pdf", empty_file, "application/pdf")},
    )
    assert resp_empty.status_code == 400
    assert "empty" in resp_empty.json()["detail"]

    # 3. Reject invalid PDF magic bytes
    fake_pdf = io.BytesIO(b"NOT_A_REAL_PDF_HEADER_CONTENT")
    resp_fake = client.post(
        "/api/v1/documents",
        headers=headers,
        files={"file": ("fake.pdf", fake_pdf, "application/pdf")},
    )
    assert resp_fake.status_code == 400
    assert "%PDF" in resp_fake.json()["detail"]


def test_user_document_isolation(client: TestClient, sample_pdf_path: Path, db_session: Session) -> None:
    """Verify that User A cannot see or delete User B's documents."""
    # 1. Signup User A and User B
    resp_a = client.post(
        "/api/v1/auth/signup",
        json={"email": "userA@test.internal", "password": "passwordA123", "role": "user"},
    )
    token_a = resp_a.json()["access_token"]

    resp_b = client.post(
        "/api/v1/auth/signup",
        json={"email": "userB@test.internal", "password": "passwordB123", "role": "user"},
    )
    token_b = resp_b.json()["access_token"]

    # 2. User A uploads sample_1.pdf
    pdf_bytes = sample_pdf_path.read_bytes()
    upload_resp = client.post(
        "/api/v1/documents",
        headers={"Authorization": f"Bearer {token_a}"},
        files={"file": ("sample_1.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
    )
    assert upload_resp.status_code == 201
    doc_a_id = upload_resp.json()["id"]

    # 3. User A can see their document
    list_a = client.get("/api/v1/documents", headers={"Authorization": f"Bearer {token_a}"})
    assert list_a.status_code == 200
    doc_ids_a = [d["id"] for d in list_a.json()]
    assert doc_a_id in doc_ids_a

    # 4. User B CANNOT see User A's document in document listing
    list_b = client.get("/api/v1/documents", headers={"Authorization": f"Bearer {token_b}"})
    assert list_b.status_code == 200
    doc_ids_b = [d["id"] for d in list_b.json()]
    assert doc_a_id not in doc_ids_b

    # 5. User B CANNOT get User A's document by ID (returns 404)
    get_b = client.get(
        f"/api/v1/documents/{doc_a_id}",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert get_b.status_code == 404

    # 6. User B CANNOT delete User A's document (returns 403 or 404)
    del_b = client.delete(
        f"/api/v1/documents/{doc_a_id}",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert del_b.status_code in (403, 404)


def test_document_full_lifecycle(client: TestClient, sample_pdf_path: Path, db_session: Session) -> None:
    """Verify document upload -> queued -> processing -> ready stub -> delete."""
    # 1. Signup user
    signup_resp = client.post(
        "/api/v1/auth/signup",
        json={"email": "lifecycle@test.internal", "password": "lifecyclepass123"},
    )
    token = signup_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 2. Upload sample_1.pdf
    pdf_bytes = sample_pdf_path.read_bytes()
    upload_resp = client.post(
        "/api/v1/documents",
        headers=headers,
        files={"file": ("sample_1.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
    )
    assert upload_resp.status_code == 201
    doc_info = upload_resp.json()
    doc_id = doc_info["id"]
    assert doc_info["original_name"] == "sample_1.pdf"
    assert doc_info["status"] in ("queued", "processing", "ready")

    # 3. Run stub ingestion on the test db session
    process_document_stub(doc_id, db=db_session)

    # 4. Query status endpoint
    status_resp = client.get(f"/api/v1/documents/{doc_id}/status", headers=headers)
    assert status_resp.status_code == 200
    status_data = status_resp.json()
    assert status_data["status"] == "ready"
    assert len(status_data["stages"]) >= 5
    for stage in status_data["stages"]:
        assert stage["status"] == "completed"
        assert stage["progress_percent"] == 100

    # 5. Query detail endpoint
    detail_resp = client.get(f"/api/v1/documents/{doc_id}", headers=headers)
    assert detail_resp.status_code == 200
    detail_data = detail_resp.json()
    assert detail_data["id"] == doc_id
    assert detail_data["download_url"] is not None

    # 6. Delete document
    del_resp = client.delete(f"/api/v1/documents/{doc_id}", headers=headers)
    assert del_resp.status_code == 200
    assert del_resp.json()["status"] == "deleted"

    # 7. Document is gone from list and detail
    list_after = client.get("/api/v1/documents", headers=headers)
    assert doc_id not in [d["id"] for d in list_after.json()]

    get_after = client.get(f"/api/v1/documents/{doc_id}", headers=headers)
    assert get_after.status_code == 404

"""Tests for Chat API endpoints and LangGraph Agent workflow."""

from __future__ import annotations

from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.retrieval.schema import EvidenceChunk
from app.ai.llm.client import LLMResponse
from app.agents.graph import get_agent_graph, run_agent_workflow
from app.db.models.user import User

pytestmark = pytest.mark.unit


def _get_auth_headers(client: TestClient, email: str = "chat_user@docmind.internal") -> dict[str, str]:
    signup_payload = {
        "email": email,
        "password": "password12345",
        "full_name": "Chat Test User",
    }
    client.post("/api/v1/auth/signup", json=signup_payload)
    login_resp = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "password12345"},
    )
    token = login_resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_chat_query_insufficient_evidence(client: TestClient) -> None:
    """When no documents or evidence are found, Chat returns insufficient evidence response."""
    headers = _get_auth_headers(client, "empty_retrieval@docmind.internal")

    resp = client.post(
        "/api/v1/chat/query",
        json={"query": "What is the revenue in 2024?"},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "conversation_id" in data
    assert "message_id" in data
    assert "not contain sufficient evidence" in data["answer"].lower()
    assert data["has_sufficient_evidence"] is False
    assert len(data["citations"]) == 0


def test_chat_query_with_mocked_retrieval_and_llm(client: TestClient) -> None:
    """Test full query endpoint with mocked evidence and LLM response."""
    headers = _get_auth_headers(client, "qa_user@docmind.internal")

    fake_chunk = EvidenceChunk(
        chunk_id="chunk-1",
        document_id="doc-123",
        filename="financial_report.pdf",
        page_number=3,
        section="Revenue Analysis",
        text="The consolidated revenue for FY2024 was $4.2 billion, up 15% year-over-year.",
        dense_score=0.92,
    )

    with patch("app.retrieval.service.RetrievalService.retrieve", return_value=[fake_chunk]):
        with patch("app.ai.llm.client.LLMClient.generate") as mock_generate:
            mock_generate.return_value = LLMResponse(
                content="The consolidated revenue for FY2024 was $4.2 billion [Doc: financial_report.pdf, Page: 3].",
                model_used="baai/bge-m3-mock",
                fallback_occurred=False,
            )

            resp = client.post(
                "/api/v1/chat/query",
                json={"query": "What was the FY2024 revenue?"},
                headers=headers,
            )
            assert resp.status_code == 200, resp.text
            data = resp.json()
            assert "4.2 billion" in data["answer"]
            assert data["has_sufficient_evidence"] is True
            assert len(data["citations"]) == 1
            assert data["citations"][0]["filename"] == "financial_report.pdf"
            assert data["citations"][0]["page_number"] == 3
            assert data["verification"]["is_verified"] is True
            assert data["verification"]["citation_coverage"] == 1.0


def test_conversations_crud(client: TestClient) -> None:
    """Test listing, reading, and deleting conversations."""
    headers = _get_auth_headers(client, "conv_user@docmind.internal")

    # Ask query 1 to create conversation
    resp1 = client.post(
        "/api/v1/chat/query",
        json={"query": "Initial question about document metrics"},
        headers=headers,
    )
    assert resp1.status_code == 200
    conv_id = resp1.json()["conversation_id"]

    # Ask query 2 to append to same conversation
    resp2 = client.post(
        "/api/v1/chat/query",
        json={"query": "Follow-up question", "conversation_id": conv_id},
        headers=headers,
    )
    assert resp2.status_code == 200
    assert resp2.json()["conversation_id"] == conv_id

    # List conversations
    list_resp = client.get("/api/v1/chat/conversations", headers=headers)
    assert list_resp.status_code == 200
    convs = list_resp.json()
    assert len(convs) >= 1
    target = next((c for c in convs if c["id"] == conv_id), None)
    assert target is not None
    assert target["message_count"] == 4  # 2 user msgs + 2 assistant msgs

    # Get conversation details
    detail_resp = client.get(f"/api/v1/chat/conversations/{conv_id}", headers=headers)
    assert detail_resp.status_code == 200
    detail = detail_resp.json()
    assert len(detail["messages"]) == 4

    # Delete conversation
    del_resp = client.delete(f"/api/v1/chat/conversations/{conv_id}", headers=headers)
    assert del_resp.status_code == 204

    # Verify 404 after delete
    get_again = client.get(f"/api/v1/chat/conversations/{conv_id}", headers=headers)
    assert get_again.status_code == 404


def test_agent_graph_compiles_and_runs(db_session: Session) -> None:
    """Test LangGraph agent compilation and execution with mocked components."""
    fake_user = User(id="test-agent-user-id", email="agent@docmind.test", is_active=True, role="user")

    fake_chunk = EvidenceChunk(
        chunk_id="chunk-42",
        document_id="doc-999",
        filename="contract.pdf",
        page_number=7,
        section="Terms",
        text="All deliverables shall be completed by October 31, 2026.",
        dense_score=0.88,
    )

    with patch("app.agents.retriever.retrieve_dense_candidates", return_value=[fake_chunk]):
        with patch("app.ai.llm.client.LLMClient.generate") as mock_gen:
            mock_gen.return_value = LLMResponse(
                content="Deliverables must be finished by October 31, 2026 [Doc: contract.pdf, Page: 7].",
                model_used="openrouter-test",
            )

            result = run_agent_workflow(
                query="When are deliverables due?",
                user=fake_user,
                db=db_session,
            )

            assert "October 31, 2026" in result["answer"]
            assert len(result["citations"]) == 1
            assert result["verification"]["is_verified"] is True

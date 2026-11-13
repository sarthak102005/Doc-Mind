"""Pydantic schemas for Chat and Conversation APIs."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from pydantic import BaseModel, Field


class ChatQueryRequest(BaseModel):
    query: str = Field(..., min_length=1, description="User's question or search query")
    document_ids: list[str] | None = Field(default=None, description="Optional document ID filters")
    conversation_id: str | None = Field(default=None, description="Existing conversation ID to continue")
    use_agent: bool = Field(default=False, description="Whether to run multi-agent LangGraph workflow")


class CitationItem(BaseModel):
    document_id: str
    filename: str = ""
    page_number: int
    section: str = ""
    bbox: list[float] = Field(default_factory=list)
    preview_text: str = ""


class ChatQueryResponse(BaseModel):
    conversation_id: str
    message_id: str
    answer: str
    citations: list[dict[str, Any]] = Field(default_factory=list)
    retrieved_chunks: list[dict[str, Any]] = Field(default_factory=list)
    model_used: str = ""
    fallback_occurred: bool = False
    has_sufficient_evidence: bool = True
    verification: dict[str, Any] = Field(default_factory=dict)


class MessageItem(BaseModel):
    id: str
    conversation_id: str
    role: str
    content: str
    citations: list[dict[str, Any]] = Field(default_factory=list)
    meta_info: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class ConversationSummary(BaseModel):
    id: str
    title: str
    document_id: str | None = None
    created_at: datetime
    updated_at: datetime
    message_count: int = 0


class ConversationDetail(BaseModel):
    id: str
    title: str
    document_id: str | None = None
    created_at: datetime
    updated_at: datetime
    messages: list[MessageItem] = Field(default_factory=list)

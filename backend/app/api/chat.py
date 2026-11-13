"""Chat and conversational document Q&A endpoints."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.ai.llm.generator import generate_grounded_answer
from app.api.deps import get_current_active_user
from app.db.models.conversation import Conversation, Message
from app.db.models.user import User
from app.db.session import get_db
from app.retrieval.service import get_retrieval_service
from app.retrieval.verifier import verify_answer_citations
from app.schemas.chat import (
    ChatQueryRequest,
    ChatQueryResponse,
    ConversationDetail,
    ConversationSummary,
    MessageItem,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("/query", response_model=ChatQueryResponse)
def query_documents(
    req: ChatQueryRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> ChatQueryResponse:
    """Submit a question grounded in authorized documents."""
    # 1. Resolve or create conversation
    if req.conversation_id:
        conv = (
            db.query(Conversation)
            .filter(Conversation.id == req.conversation_id, Conversation.user_id == current_user.id)
            .first()
        )
        if not conv:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conversation not found",
            )
    else:
        title = req.query[:50].strip() or "New Conversation"
        doc_id = req.document_ids[0] if (req.document_ids and len(req.document_ids) == 1) else None
        conv = Conversation(
            id=str(uuid.uuid4()),
            user_id=current_user.id,
            title=title,
            document_id=doc_id,
        )
        db.add(conv)
        db.flush()

    # 2. Fetch recent conversation history
    recent_messages = (
        db.query(Message)
        .filter(Message.conversation_id == conv.id)
        .order_by(Message.created_at.asc())
        .limit(6)
        .all()
    )
    history = [{"role": m.role, "content": m.content} for m in recent_messages]

    # 3. Save user message
    user_msg = Message(
        id=str(uuid.uuid4()),
        conversation_id=conv.id,
        role="user",
        content=req.query,
        citations=[],
        meta_info={},
    )
    db.add(user_msg)

    # 4. Check whether to run multi-agent LangGraph orchestration or standard RAG
    if req.use_agent:
        try:
            from app.agents.graph import run_agent_workflow

            agent_result = run_agent_workflow(
                query=req.query,
                user=current_user,
                db=db,
                document_ids=req.document_ids,
                conversation_history=history,
            )
            grounded_answer = agent_result["answer"]
            citations = agent_result.get("citations", [])
            retrieved_chunks = agent_result.get("retrieved_chunks", [])
            model_used = agent_result.get("model_used", "agent")
            fallback_occurred = agent_result.get("fallback_occurred", False)
            has_sufficient_evidence = agent_result.get("has_sufficient_evidence", True)
            verification_dict = agent_result.get("verification", {})
        except Exception as exc:
            logger.warning("Agent execution fallback to standard retrieval: %s", exc)
            grounded_answer = None
    else:
        grounded_answer = None

    if grounded_answer is None:
        # 5. Standard high-performance RAG pipeline
        retrieval_service = get_retrieval_service()
        evidence = retrieval_service.retrieve(
            query=req.query,
            user=current_user,
            db=db,
            document_ids=req.document_ids,
        )

        ans = generate_grounded_answer(
            query=req.query,
            evidence_chunks=evidence,
            conversation_history=history,
        )

        verification = verify_answer_citations(
            answer=ans.answer,
            evidence_chunks=evidence,
        )

        grounded_answer = ans.answer
        citations = ans.citations
        retrieved_chunks = ans.retrieved_chunks
        model_used = ans.model_used
        fallback_occurred = ans.fallback_occurred
        has_sufficient_evidence = ans.has_sufficient_evidence
        verification_dict = verification.model_dump()

    # 6. Save assistant message
    asst_msg = Message(
        id=str(uuid.uuid4()),
        conversation_id=conv.id,
        role="assistant",
        content=grounded_answer,
        citations=citations,
        meta_info={
            "model_used": model_used,
            "fallback_occurred": fallback_occurred,
            "has_sufficient_evidence": has_sufficient_evidence,
            "verification": verification_dict,
        },
    )
    db.add(asst_msg)

    # 7. Update conversation updated_at
    conv.updated_at = datetime.now(timezone.utc)
    db.commit()

    return ChatQueryResponse(
        conversation_id=conv.id,
        message_id=asst_msg.id,
        answer=grounded_answer,
        citations=citations,
        retrieved_chunks=retrieved_chunks,
        model_used=model_used,
        fallback_occurred=fallback_occurred,
        has_sufficient_evidence=has_sufficient_evidence,
        verification=verification_dict,
    )


@router.get("/conversations", response_model=list[ConversationSummary])
def list_conversations(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> list[ConversationSummary]:
    """List all conversations for the authenticated user."""
    convs = (
        db.query(Conversation)
        .filter(Conversation.user_id == current_user.id)
        .order_by(Conversation.updated_at.desc())
        .all()
    )
    results = []
    for c in convs:
        count = db.query(Message).filter(Message.conversation_id == c.id).count()
        results.append(
            ConversationSummary(
                id=c.id,
                title=c.title,
                document_id=c.document_id,
                created_at=c.created_at,
                updated_at=c.updated_at,
                message_count=count,
            )
        )
    return results


@router.get("/conversations/{conversation_id}", response_model=ConversationDetail)
def get_conversation(
    conversation_id: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> ConversationDetail:
    """Retrieve full conversation details and chronological messages."""
    conv = (
        db.query(Conversation)
        .filter(Conversation.id == conversation_id, Conversation.user_id == current_user.id)
        .first()
    )
    if not conv:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )

    messages = (
        db.query(Message)
        .filter(Message.conversation_id == conv.id)
        .order_by(Message.created_at.asc())
        .all()
    )

    msg_items = [
        MessageItem(
            id=m.id,
            conversation_id=m.conversation_id,
            role=m.role,
            content=m.content,
            citations=m.citations or [],
            meta_info=m.meta_info or {},
            created_at=m.created_at,
        )
        for m in messages
    ]

    return ConversationDetail(
        id=conv.id,
        title=conv.title,
        document_id=conv.document_id,
        created_at=conv.created_at,
        updated_at=conv.updated_at,
        messages=msg_items,
    )


@router.delete("/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_conversation(
    conversation_id: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> None:
    """Delete a conversation and its messages."""
    conv = (
        db.query(Conversation)
        .filter(Conversation.id == conversation_id, Conversation.user_id == current_user.id)
        .first()
    )
    if not conv:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )

    db.delete(conv)
    db.commit()

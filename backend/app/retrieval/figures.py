"""Figure retrieval and visual intent detection for multimodal RAG."""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, Any

from sqlalchemy.orm import Session

from app.db.models.document import Document
from app.retrieval.filters import resolve_authorized_document_ids
from app.retrieval.schema import EvidenceChunk
from app.schemas.chat import ImageAttachment

if TYPE_CHECKING:
    from app.db.models.user import User

logger = logging.getLogger(__name__)

VISUAL_KEYWORDS = {
    "photo", "photos", "photograph", "photographs", "pic", "pics", "picture", "pictures",
    "image", "images", "figure", "figures", "fig", "diagram", "diagrams", "schematic",
    "schematics", "illustration", "illustrations", "drawing", "drawings", "cutaway",
    "exploded", "view", "visual", "look like", "appearance", "show me", "display",
    "see the", "graph", "chart"
}


def is_visual_query(query: str) -> bool:
    """Determine whether the query expresses an intent to view visual assets."""
    q_lower = query.lower()
    for kw in VISUAL_KEYWORDS:
        if re.search(rf"\b{re.escape(kw)}\b", q_lower):
            return True
    return False


def extract_page_reference(query: str) -> int | None:
    """Extract an explicit page number reference from query text (e.g. 'page 11', 'p. 2')."""
    match = re.search(r"\b(?:page|pg|p\.?)\s*(\d+)\b", query.lower())
    if match:
        try:
            return int(match.group(1))
        except ValueError:
            return None
    return None


def retrieve_figures(
    query: str,
    user: User,
    db: Session,
    document_ids: list[str] | None = None,
    evidence_chunks: list[EvidenceChunk] | None = None,
    top_k: int = 3,
) -> list[ImageAttachment]:
    """Retrieve relevant figure attachments for a user query."""
    authorized_ids = resolve_authorized_document_ids(
        user=user,
        db=db,
        requested_ids=document_ids,
    )
    if not authorized_ids:
        return []

    is_visual = is_visual_query(query)
    target_page = extract_page_reference(query)
    q_lower = query.lower()
    query_tokens = set(re.findall(r"\w+", q_lower)) - {"a", "an", "the", "in", "on", "of", "to", "for", "is", "are", "what", "how", "i", "want", "show", "me"}

    # If NOT a visual query and no target page, only return if a figure chunk was explicitly top evidence
    if not is_visual and target_page is None:
        if not evidence_chunks:
            return []
        fig_evidence = [c for c in evidence_chunks if c.chunk_type == "figure_caption" and c.score > 0.85]
        if not fig_evidence:
            return []

    docs = db.query(Document).filter(Document.id.in_(authorized_ids)).all()
    doc_map = {d.id: d for d in docs}

    # Map existing figures across authorized documents
    candidate_scores: dict[str, tuple[float, dict[str, Any], str]] = {}  # fig_id -> (score, fig_dict, doc_id)

    # 1. Inspect evidence_chunks from Qdrant vector retrieval
    if evidence_chunks:
        for idx, chunk in enumerate(evidence_chunks):
            if chunk.chunk_type == "figure_caption" or "minio_key" in chunk.metadata:
                fig_id = chunk.metadata.get("figure_id") or chunk.chunk_id.replace("fig_", "")
                doc_id = chunk.document_id
                doc = doc_map.get(doc_id)
                if not doc:
                    continue
                
                # Base score from vector relevance rank
                score = 50.0 - (idx * 3.0) + (chunk.score * 20.0)
                
                # Check target page
                if target_page is not None and chunk.page_number == target_page:
                    score += 100.0

                fig_dict = {
                    "figure_id": fig_id,
                    "document_id": doc_id,
                    "filename": doc.filename,
                    "page_number": chunk.page_number,
                    "bbox": chunk.metadata.get("bbox", []),
                    "minio_key": chunk.metadata.get("minio_key", f"figures/{doc_id}/{fig_id}.png"),
                    "caption": chunk.text.replace(f"[Figure on Page {chunk.page_number}]: ", "").strip(),
                }
                candidate_scores[fig_id] = (score, fig_dict, doc_id)

    # 2. Inspect Document.meta_info['figures'] manifest
    for doc in docs:
        manifest = (doc.meta_info or {}).get("figures", [])
        for fig in manifest:
            fig_id = fig.get("figure_id", "")
            if not fig_id:
                continue

            score = 0.0
            p_num = fig.get("page_number", 1)
            caption = (fig.get("caption") or "").lower()
            labels = " ".join(fig.get("nearby_labels") or []).lower()
            full_text = f"{caption} {labels} {doc.filename.lower()}"

            # If user explicitly asked for a specific page
            if target_page is not None:
                if p_num == target_page:
                    score += 120.0
                else:
                    score -= 50.0

            # Match query tokens in figure caption / context
            for token in query_tokens:
                if token in full_text:
                    score += 15.0

            if fig_id in candidate_scores:
                existing_score, existing_fig, d_id = candidate_scores[fig_id]
                candidate_scores[fig_id] = (existing_score + score, existing_fig, d_id)
            elif score > 0:
                candidate_scores[fig_id] = (score, fig, doc.id)

    if not candidate_scores:
        return []

    # Sort candidates by score descending
    sorted_candidates = sorted(candidate_scores.values(), key=lambda x: x[0], reverse=True)

    results: list[ImageAttachment] = []
    seen_keys: set[str] = set()

    for score, fig, doc_id in sorted_candidates:
        if score <= 0 and is_visual and len(results) > 0:
            continue

        fig_id = fig.get("figure_id", "")
        clean_id = fig_id.split(f"{doc_id}_")[-1]
        dedup_key = f"{doc_id}_{clean_id}"
        if dedup_key in seen_keys:
            continue
        seen_keys.add(dedup_key)

        doc = doc_map.get(doc_id)
        filename = doc.filename if doc else fig.get("filename", "")
        p_num = fig.get("page_number", 1)
        caption = fig.get("caption") or f"Figure on Page {p_num}"

        attachment = ImageAttachment(
            figure_id=fig_id,
            document_id=doc_id,
            filename=filename,
            page_number=p_num,
            caption=caption,
            description=fig.get("caption"),
            image_url=f"/api/v1/documents/{doc_id}/figures/{fig_id}/image",
            bbox=fig.get("bbox") or [],
            width_px=fig.get("width_px"),
            height_px=fig.get("height_px"),
        )
        results.append(attachment)
        if len(results) >= top_k:
            break

    logger.info("retrieve_figures returned %d images for query %r", len(results), query)
    return results

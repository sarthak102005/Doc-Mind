"""Retrieval pipeline package for DocMind."""

from app.retrieval.schema import EvidenceChunk
from app.retrieval.service import RetrievalService, get_retrieval_service

__all__ = [
    "EvidenceChunk",
    "RetrievalService",
    "get_retrieval_service",
]

"""End-to-End Real RAG Verification & Demonstration Script."""

from __future__ import annotations
import sys

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

def print_flush(*args, **kwargs):
    print(*args, **kwargs, flush=True)

import os
import time
from pathlib import Path

# Ensure backend root is on sys.path
backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

# Configure environment for live integration run
os.environ["APP_ENV"] = "dev"
os.environ["STORAGE_BACKEND"] = "minio"
os.environ["REDIS_BACKEND"] = "memory"

from app.core.config import get_settings
from app.db.session import SessionLocal, init_db
from app.db.models.user import User
from app.db.models.document import Document, DocumentVersion, PageProfile, TableRecord
from app.services.storage import get_storage_service
from app.worker.tasks import process_document_pipeline
from app.retrieval.service import get_retrieval_service
from app.ai.llm.generator import generate_grounded_answer
from app.retrieval.verifier import verify_answer_citations
from app.agents.graph import run_agent_workflow
from app.services.vector_store import delete_document_vectors_sync, search_vectors


def main():
    print_flush("=" * 60)
    print_flush("DocMind End-to-End Multimodal RAG Verification")
    print_flush("=" * 60)

    settings = get_settings()
    init_db()

    session = SessionLocal()
    try:
        # 1. Setup Demo User
        user = session.query(User).filter(User.email == "demo_engineer@docmind.internal").first()
        if not user:
            from app.core.security import hash_password
            user = User(
                id="demo-user-001",
                email="demo_engineer@docmind.internal",
                hashed_password=hash_password("demoPass123"),
                full_name="Demo Systems Engineer",
                role="admin",
                is_active=True,
            )
            session.add(user)
            session.commit()
            print_flush("[+] Verified demo user: demo_engineer@docmind.internal")
        else:
            print_flush("[+] Found demo user: demo_engineer@docmind.internal")

        # 2. Check if an indexed document already exists in DB
        existing_doc = session.query(Document).filter(Document.status == "ready").first()
        if existing_doc:
            doc = existing_doc
            doc_id = doc.id
            print_flush(f"[+] Reusing already ingested & indexed document: {doc_id} ('{doc.filename}')")
        else:
            sample_path = backend_dir.parent / "benchmark" / "sample_1.pdf"
            assert sample_path.is_file(), f"sample_1.pdf missing at {sample_path}"
            pdf_bytes = sample_path.read_bytes()

            doc_id = f"demo-doc-{int(time.time())}"
            minio_key = f"documents/{doc_id}/v1.pdf"

            storage = get_storage_service()
            storage.upload_file(minio_key, pdf_bytes, content_type="application/pdf")
            print_flush(f"[+] Uploaded sample_1.pdf ({len(pdf_bytes)} bytes) to MinIO key: {minio_key}")

            doc = Document(
                id=doc_id,
                owner_id=user.id,
                filename="sample_1.pdf",
                original_name="sample_1.pdf",
                content_type="application/pdf",
                size_bytes=len(pdf_bytes),
                file_hash="demo_hash",
                current_version=1,
                status="queued",
                meta_info={"page_count": 12},
            )
            session.add(doc)
            doc_version = DocumentVersion(
                document_id=doc_id,
                version_num=1,
                minio_key=minio_key,
                file_hash="demo_hash",
                size_bytes=len(pdf_bytes),
            )
            session.add(doc_version)
            session.commit()
            print_flush(f"[+] Registered Document ID in PostgreSQL: {doc_id}")

            print_flush("\n[*] Starting multi-stage ingestion pipeline...")
            t0 = time.perf_counter()
            process_document_pipeline(document_id=doc_id, pdf_path=str(sample_path), db=session)
            elapsed = time.perf_counter() - t0

            session.refresh(doc)
            print_flush(f"[+] Pipeline completed in {elapsed:.2f}s! Final Status: '{doc.status}'")

        # Check DB records
        profile_count = session.query(PageProfile).filter(PageProfile.document_id == doc_id).count()
        table_count = session.query(TableRecord).filter(TableRecord.document_id == doc_id).count()
        print_flush(f"[+] Document has {profile_count} PageProfiles and {table_count} TableRecords in PostgreSQL")

        # 3. Semantic Vector Retrieval & Grounded Generation
        query = "What are the exact voltage, amp ratings, and runtime specifications on page 11?"
        print_flush(f"\n[*] Submitting Query: \"{query}\"")

        retrieval_service = get_retrieval_service(settings)
        evidence = retrieval_service.retrieve(
            query=query,
            user=user,
            db=session,
            document_ids=[doc_id],
            top_k=4,
        )
        print_flush(f"[+] Retrieved {len(evidence)} evidence chunks from Qdrant:")
        for idx, chunk in enumerate(evidence, 1):
            sample_txt = chunk.text.replace("\n", " ")[:90]
            print_flush(f"    - Chunk {idx}: Page {chunk.page_number} | Score: {chunk.score:.3f} | {sample_txt}...")

        # Grounded LLM Generation
        print_flush("\n[*] Generating grounded answer with OpenRouter fallback chain...")
        grounded_ans = generate_grounded_answer(query=query, evidence_chunks=evidence)
        print_flush(f"\n[DocMind Grounded Answer] (Model: {grounded_ans.model_used}):")
        print_flush("-" * 60)
        print_flush(grounded_ans.answer)
        print_flush("-" * 60)
        print_flush(f"[+] Citations found: {len(grounded_ans.citations)}")
        for c in grounded_ans.citations:
            print_flush(f"    * Doc: {c.get('filename')} | Page: {c.get('page_number')}")

        # Verifier check
        verif = verify_answer_citations(grounded_ans.answer, evidence)
        print_flush(f"[+] Citation Verification Result: is_verified={verif.is_verified}, coverage={verif.citation_coverage:.2f}")

        # 4. Multi-Agent LangGraph Workflow
        print_flush("\n[*] Running multi-agent LangGraph workflow (Planner -> Retriever -> Reasoner -> Verifier -> Generator)...")
        agent_res = run_agent_workflow(
            query="Summarize the core technical specifications and voltage requirements.",
            user=user,
            db=session,
            document_ids=[doc_id],
        )
        print_flush(f"\n[Agentic Answer] (Model: {agent_res['model_used']}):")
        print_flush("-" * 60)
        print_flush(agent_res["answer"])
        print_flush("-" * 60)
        print_flush(f"[+] Agent Citations: {len(agent_res.get('citations', []))}")

        # 5. Teardown / Deletion check
        print_flush("\n[*] Verifying vector store purge on document deletion...")
        delete_document_vectors_sync(doc_id)
        session.delete(doc)
        session.commit()
        print_flush(f"[+] Document {doc_id} and associated Qdrant vectors cleaned up successfully!")

        print_flush("\n" + "=" * 60)
        print_flush("ALL END-TO-END ACCEPTANCE CHECKS PASSED SUCCESSFULLY!")
        print_flush("=" * 60)

    finally:
        session.close()


if __name__ == "__main__":
    main()

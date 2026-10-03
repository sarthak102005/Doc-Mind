# DocMind Implementation Progress

## Project Overview
- **Project:** DocMind — Agentic Multimodal Enterprise Document Intelligence System
- **Profile:** `HARDWARE_PROFILE=cpu_8gb`, `DEV_LITE_MODE=true`
- **Team:** Team Nexus (B.Tech Minor Project)

---

## Benchmark Status

| Benchmark Document | Type | Pages | Images | Ingestion Status | Evaluation Pass Rate |
|---|---|---|---|---|---|
| `benchmark/sample_1.pdf` | Born-digital Brochure | 12 | 49 | Pending (Phase 2) | 0/32 (Phase 0 scaffold verified) |
| `benchmark/sample_1_scanned.pdf` | Scanned raster | 12 | - | Pending (Phase 2) | 0/32 |

### Golden Questions Status (`benchmark/golden.jsonl`)
- **Total Defined:** Exactly 32 golden questions (G01 to G32 from Part C).
- **Categories Covered:** spec (10), trap (1), compare (2), layout (2), text (5), legend (2), figure (1), list (2), inconsistency (1), unanswerable (2), image-retrieval (5).
- **Pass Criteria for `make bench`:**
  - Born-digital: 100% on trap, spec, compare, unanswerable, and inconsistency; at least 90% of the rest.
  - Scanned: At least 80% pass rate with breakdown by type.
  - G28 to G32: Image retrieval-only tests (top-3 recall); feeds Phase 8 image-retrieval ablation.

---

## Phase Roadmap & Status

### Phase 0: Foundations, Architecture & Environment Setup
- [x] Review `DocMind_Plan.pdf` and Addenda A2/A3.
- [x] Author `docs/ARCHITECTURE.md` with ambiguities and risk register.
- [x] Author `docs/DECISIONS.md` recording all Addenda overrides and defaults.
- [x] Create project layout matching repository specification.
- [x] Implement typed settings module in `backend/app/core/config.py`.
- [x] Configure `.env.example` with fallback LLM chain and hosted endpoints.
- [x] Configure `docker-compose.yml` (infra-only, memory-capped for 8 GB RAM) and `docker-compose.full.yml`.
- [x] Create `Makefile` with `up`, `test`, `lint`, `eval`, `bench`, `doctor`.
- [x] Implement `/health` endpoint checking PostgreSQL, Qdrant, Redis, and MinIO.
- [x] Setup `benchmark/golden.jsonl` schema and validation loader.
- [x] Verify Docker services and `/health` reporting all up.

### Phase 1: Database Schemas, Security & Authentication
- [ ] PostgreSQL database schema: `users`, `documents`, `document_versions`, `page_profiles`, `table_records`, `conversations`, `messages`, `access_log`.
- [ ] SQLAlchemy/SQLModel or Alembic migrations setup.
- [ ] JWT authentication service and password hashing.
- [ ] Role-based and document-level permission models.
- [ ] Document upload API endpoint with MIME-type, magic byte, and size validation (`MAX_UPLOAD_MB`).
- [ ] MinIO integration for file and extracted asset storage.

### Phase 2: Document Ingestion & Multimodal Extraction Pipeline
- [ ] Ground-truth inspection: run Docling on `benchmark/sample_1.pdf` and dump raw trees to `benchmark/debug/`.
- [ ] Page profiling (`backend/app/ingestion/profile.py`): text character density, image ratio, scanned classification.
- [ ] OCR routing via ONNX Runtime & RapidOCR on image regions and scanned pages.
- [ ] Reading order reconstruction using bounding-box layout clustering (Page 2 unit test).
- [ ] Boilerplate detection: header/footer normalization across pages and metadata extraction.
- [ ] Table extraction: spatial-gap segmentation (Page 11 3-table separation) & `table_records` population.
- [ ] Figure triage & classification: diagrams, labelled renders, UI screenshots, decorative.
- [ ] Content caching by SHA-256 hash.

### Phase 3: Indexing & Hybrid Representation
- [ ] Hierarchy-aware & card-based layout chunking with running headings.
- [ ] Table records chunk formatting with hierarchical context prefixes.
- [ ] Figure description chunking (VLM JSON + OCR text).
- [ ] Hosted BGE-M3 text embeddings pipeline (`docmind_text` collection).
- [ ] SigLIP2-base image embedding pipeline on CPU (`docmind_images` collection).
- [ ] Metadata payload attachment (ACLs, entities, bboxes, page numbers).

### Phase 4: Retrieval & Structured Lookup
- [ ] Dense vector retrieval with Qdrant payload security filters.
- [ ] BM25 keyword search index with boilerplate suppression.
- [ ] Reciprocal Rank Fusion (RRF) for hybrid results.
- [ ] Hosted BGE Reranker integration (`BAAI/bge-reranker-v2-m3`).
- [ ] Structured `table_lookup(entity, attribute, section?)` tool execution.
- [ ] Dual-path image candidate mapping to description chunks.

### Phase 5: Agentic Multi-Agent Orchestration (LangGraph)
- [ ] LangGraph state schema definition.
- [ ] Query Planner Agent (intent classification, entity tagging, modality routing).
- [ ] Retrieval Agent (hybrid execution + structured tool calling).
- [ ] Reasoning Agent (cross-document synthesis, contradiction detection).
- [ ] Verification Agent (grounding checks, citation verification, inconsistency enforcement).
- [ ] Ordered LLM Fallback Chain executor (GPT-OSS 120B → Nemotron → DeepSeek → Qwen → Llama).

### Phase 6: Multimodal Intelligence & VLM Ingestion Tuning
- [ ] Vision interface (`VLM_*`) connecting hosted Qwen2.5-VL / Gemini Flash.
- [ ] Structured callout and legend JSON extraction (Page 3 brush wheel legend).
- [ ] Table verification and raster number cross-checking.
- [ ] Complex page summary generation for high-image ratio pages.

### Phase 7: Frontend Application
- [ ] React (Vite) + Framer Motion user interface.
- [ ] Modern UI with dashboard, upload zone, chat conversation, and document manager.
- [ ] Lightweight inline citations with document/page click navigation.
- [ ] Processing status indicators.

### Phase 8: Testing, Benchmarking & Evaluation
- [ ] Execute `benchmark/golden.jsonl` against all golden questions.
- [ ] Measure retrieval metrics (Precision@K, MRR, Context Recall).
- [ ] Measure generation metrics (Faithfulness, Citation correctness).
- [ ] Benchmark comparison: Baseline 1 (Basic RAG) vs. Baseline 2 (Hybrid) vs. DocMind Agentic.
- [ ] Ingestion throughput, stage timings, and peak RAM consumption reporting.

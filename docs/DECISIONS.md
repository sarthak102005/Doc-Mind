# Architectural Decisions and Precedence Overrides

This document tracks all overrides where Addendum A2 / A3 supersedes `docs/DocMind_Plan.pdf`, as well as design decisions taken where both were silent.

## Precedence Hierarchy
1. **Addendum A3 (Hardware Profile & Image Handling)**
2. **Addendum A2 (Document Inspection Findings & Engineering Rules)**
3. **DocMind_Plan.pdf (Master Specification)**
4. **Simplest viable design adhering to constraints (DECISIONS.md)**

---

## Decision Log

### D-001: Hosted vs. Local Model Execution (Override of Plan §7, §12, §13, §17)
- **Status:** Approved (Addendum A3.1)
- **Context:** The target development machine is an Intel Core i5 (6th gen), 8 GB RAM, with no GPU (`HARDWARE_PROFILE=cpu_8gb`). The PDF plan originally specified running local LLMs, local Qwen2.5-VL, local BGE-M3, and local BGE Reranker.
- **Decision:**
  - All LLM calls (GPT-OSS 120B fallback chain) run via hosted OpenAI-compatible APIs (OpenRouter/Groq/DeepSeek).
  - Vision model (VLM) runs via hosted API (`qwen/qwen2.5-vl-72b-instruct` or compatible via OpenRouter), isolated from LLM fallback chain.
  - Text embeddings run via hosted BGE-M3 API (SiliconFlow `/embeddings`, 1024-d dense).
  - Reranker runs via hosted BGE Reranker API (SiliconFlow `/rerank`).
  - Only RapidOCR (PaddleOCR on ONNX Runtime CPU) and SigLIP2-base (`google/siglip2-base-patch16-224`, ~0.4B params) run locally on CPU, loaded lazily one at a time and unloaded when idle.

### D-002: LLM Fallback Chain Slugs & "Llama 3.3 70B Instant" (Override of Plan §23)
- **Status:** Approved (Addendum A1.2, A3.1)
- **Context:** The PDF specifies "Llama 3.3 70B Instant" as fallback 4. No such model exists; Groq's `llama-3.3-70b-versatile` was retired on 2026-08-16 for developer tiers.
- **Decision:**
  - Fallback 4 is configured as `meta-llama/llama-3.3-70b-instruct` via OpenRouter.
  - Primary: `openai/gpt-oss-120b`
  - Fallback 1: `nvidia/nemotron-3-nano-30b-a3b`
  - Fallback 2: `deepseek/deepseek-v4-flash-0731`
  - Fallback 3: `qwen/qwen3.8-27b`
  - Fallback 4: `meta-llama/llama-3.3-70b-instruct`
  - Fallback triggers on timeout, 429, 5xx, or invalid structured output after 1 repair attempt, applying a cooldown period to failing models.

### D-003: Page Profiling & Targeted OCR (Override of Plan §8, §10)
- **Status:** Approved (Addendum A2.1, A2.2)
- **Context:** Plan diagram shows OCR running globally on all content. Benchmark inspection of `sample_1.pdf` reveals it is born-digital (12 pages, 100% text layer present). Sending digital pages to full-page OCR degrades speed and introduces OCR errors.
- **Decision:**
  - Ingestion runs `profile_page` before parsing: character count, image area ratio, column estimate, reading-order sanity.
  - Pages with healthy text layers are routed to `text_native`.
  - Only scanned pages receive full-page OCR.
  - Inside text-native pages, OCR runs strictly on cropped image regions that may contain text (badges, labelled diagrams, UI screenshots).

### D-004: Table Extraction & Spatial Reconciliation (Override of Plan §8, §11)
- **Status:** Approved (Addendum A2.5, A2.10)
- **Context:** `sample_1.pdf` page 11 features 3 side-by-side spec tables (Micro, Mini, Mag). Naive table parsers merge columns across tables and misattribute specs.
- **Decision:**
  - Segment tables using spatial bounding-box gaps; never merge across horizontal gaps.
  - Link table titles by bounding-box proximity, not PDF stream order.
  - Cross-check table numbers against page raster using VLM on table-heavy pages. Reconcile numbers: any figure reported by VLM must appear in text layer/OCR or be flagged.
  - Store structured data in PostgreSQL (`table_records`) with fields: `(document_id, page, table_id, entity, section, attribute, value, unit_variants, footnotes)`.
  - Provide a dedicated `table_lookup(entity, attribute, section?)` tool to the Retriever agent for deterministic numeric lookups.

### D-005: Reading Order Reconstruction (Override of Plan §9)
- **Status:** Approved (Addendum A2.3)
- **Context:** Multi-column pages (e.g. Page 2 3-column chassis descriptions) have interleaved text streams in the raw PDF.
- **Decision:** Reconstruct reading order using Docling layout bounding boxes and horizontal/vertical column clustering. Validate with a unit test asserting that Page 2 model bullet points remain grouped under their respective model headers.

### D-006: Dual-Path Image Retrieval & SigLIP2 Memory Discipline (Override of Plan §13)
- **Status:** Approved (Addendum A3.2)
- **Context:** Running full multimodal embeddings for all 49 embedded images on 8 GB RAM causes memory exhaustion and excessive latency.
- **Decision:**
  - Path 1 (Primary): Description path. VLM-generated descriptions + OCR + nearby caption are chunked, embedded with BGE-M3, and stored in `docmind_text`.
  - Path 2 (Secondary): SigLIP2 image vectors in `docmind_images` for triaged informative crops only (never decorative images or whole pages).
  - SigLIP2 loads on CPU only when queries have visual intent, and unloads after `IMAGE_EMBED_IDLE_UNLOAD_SECONDS` (120s).
  - Visual search returns candidates, which map to description text chunks for joint reranking. Raw SigLIP scores are never blended directly with text scores.

### D-007: Development Environment Topology (Override of Plan §7)
- **Status:** Approved (Addendum A3.1)
- **Context:** Running all services inside Docker containers alongside WSL2 consumes excessive RAM on an 8 GB system.
- **Decision:**
  - Day-to-day development (`docker-compose.yml`) runs only stateful infra in Docker: PostgreSQL, Qdrant, Redis, MinIO (memory capped to ~1.4 GB total).
  - FastAPI backend, Celery/worker, and Vite frontend run natively on host.
  - `docker-compose.full.yml` is provided for containerized demo deployments.

### D-008: Handling Document Inconsistencies (Override of Default LLM Behavior)
- **Status:** Approved (Addendum A2.11)
- **Context:** LLMs tend to hallucinate corrections when documents contradict themselves (e.g., Page 11 Micro-HD battery rated at 130 ah in spec table vs 210 ah in weight notes).
- **Decision:** The Verifier agent is explicitly forbidden from harmonizing or resolving conflicting numbers. It must report both figures with explicit page/section citations.

### D-009: Unified WordBox Abstraction & Horizontal Band Reading Order
- **Status:** Approved (Phase 2 Design Pass)
- **Context:** Docling's default reading order on Page 2 interlaces vertical columns and places scrub deck options and controller callouts in between chassis models.
- **Decision:**
  - Build a single `WordBox(text, l, t, r, b, page, font_size)` abstraction fed from the native PDF text layer (PyMuPDF) on digital pages and from RapidOCR on scanned pages.
  - Reading order detects horizontal bands first (full-width headings and significant vertical gaps), clusters columns within each band, outputs band-by-band, and attaches the band heading to each chunk's section hierarchy.
  - Proves that "Orbital" / "Cylindrical" / "Disk" scrub deck benefits never contaminate chassis models (Micro-HD, Mini-HD, Mag-HD).
  - Use Docling specifically for table cell structure and figure boundary detection.

### D-010: X-Projection Spatial Table Segmentation & Title Proximity Linking
- **Status:** Verified (Validated by Stage 4 unit & perturbation tests in `tests/test_tables.py`)
- **Context:** On Page 11, Docling TableFormer completely missed the middle table (Mini-HD) on scanned pages, while PyMuPDF merged tables 1 and 2 on digital pages.
- **Decision:**
  - Table zones are derived dynamically from valleys/gaps in the word boxes' horizontal X-distribution (no hard-coded coordinates).
  - Validated by perturbation tests ensuring stability under bounding-box scaling and coordinate translation.
  - Table titles are linked by geometric proximity directly above each detected column zone.

### D-011: Complete Tree Node Ingestion Over Markdown Export
- **Status:** Approved (Phase 2 Design Pass)
- **Context:** On Page 4 (cutaway diagram), Docling's `export_to_markdown()` discarded all 21 component labels as floating elements, reducing the page to 65 bytes.
- **Decision:** Pipeline ingests all AST text nodes (`doc.export_to_dict()["texts"]`) with bounding boxes and spatial coordinates, never relying solely on flattened markdown exports.

### D-012: Explicit Hybrid Ingestion Semantics & Geometric Image Union
- **Status:** Approved (Stage 1 / Stage 2 Refinement Pass)
- **Context:** Simple summation of image bounding boxes inflated raster coverage to 1.000 on multi-image digital pages, obscuring clean native text layers.
- **Decision:**
  - Page image coverage is computed via exact geometric union of image rectangles clipped to the page boundary (1D sweep-line algorithm).
  - The `hybrid` ingestion route is explicitly defined:
    1. High-quality native text layer is extracted directly as primary text stream via `WordBox`.
    2. Hybrid does NOT mean "OCR every image region". Decorative full-page backgrounds (e.g. image area ratio > 0.95 with zero text) are skipped.
    3. Region OCR runs selectively only for informative figure regions that pass figure triage (diagram labels, callouts, spec badges) and is capped within a per-document budget (`settings.max_region_ocr_per_doc = 50`).



"""Benchmark Docling with GPU (CUDA) acceleration on sample_1.pdf pages 2, 3, 4, 11.

Measures:
- Latency (seconds per page)
- Peak GPU VRAM allocated (MB)
- Extracted elements (tables, text items, figures)
Compares against the CPU baseline (D-013) and evaluates runtime fallback feasibility.
"""

from __future__ import annotations

import gc
import json
import logging
import os
import sys
import time
from pathlib import Path

# Add backend directory to sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.config import get_settings

settings = get_settings()
cache_dir = REPO_ROOT / ".cache"
docling_artifacts = cache_dir / "docling"

# Ensure environment variables for Docling and PyTorch cache
os.environ["TEMP"] = str(cache_dir / "tmp")
os.environ["TMP"] = str(cache_dir / "tmp")
os.environ["HF_HOME"] = str(cache_dir / "huggingface")
os.environ["TORCH_HOME"] = str(cache_dir / "torch")
os.environ["DOCLING_ARTIFACTS_PATH"] = str(docling_artifacts)

import pymupdf
import torch
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import (
    AcceleratorDevice,
    AcceleratorOptions,
    PdfPipelineOptions,
)
from docling.document_converter import DocumentConverter, PdfFormatOption

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("docling_gpu_benchmark")


def extract_single_page(pdf_path: Path, page_num: int, out_path: Path) -> None:
    doc = pymupdf.open(pdf_path)
    single_doc = pymupdf.open()
    single_doc.insert_pdf(doc, from_page=page_num - 1, to_page=page_num - 1)
    single_doc.save(str(out_path))
    single_doc.close()
    doc.close()


def run_docling_gpu_benchmark() -> list[dict]:
    pdf_path = REPO_ROOT / "benchmark" / "sample_1.pdf"
    pages_to_test = [2, 3, 4, 11]
    tmp_dir = cache_dir / "tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)

    cuda_available = torch.cuda.is_available()
    device_name = torch.cuda.get_device_name(0) if cuda_available else "CPU (Fallback)"
    logger.info("Running Docling Benchmark on: %s (CUDA Available: %s)", device_name, cuda_available)

    accel_device = AcceleratorDevice.CUDA if cuda_available else AcceleratorDevice.CPU
    accel = AcceleratorOptions(num_threads=4, device=accel_device)
    pipeline_opts = PdfPipelineOptions(
        artifacts_path=str(docling_artifacts),
        accelerator_options=accel,
        do_table_structure=True,
        do_ocr=False,  # Digital sample_1.pdf has native text layer
        do_code_enrichment=False,
        do_formula_enrichment=False,
        do_picture_classification=False,
    )
    doc_converter = DocumentConverter(
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_opts)}
    )

    results = []

    for page_num in pages_to_test:
        temp_pdf = tmp_dir / f"bench_docling_gpu_p{page_num}.pdf"
        extract_single_page(pdf_path, page_num, temp_pdf)

        if cuda_available:
            gc.collect()
            torch.cuda.empty_cache()
            torch.cuda.reset_peak_memory_stats()

        logger.info("Converting Page %d with Docling (CUDA)...", page_num)
        t0 = time.perf_counter()
        conv_result = doc_converter.convert(str(temp_pdf))
        elapsed = time.perf_counter() - t0

        doc_data = conv_result.document
        tables_count = len(doc_data.tables) if hasattr(doc_data, "tables") else 0
        texts_count = len(doc_data.texts) if hasattr(doc_data, "texts") else 0
        pictures_count = len(doc_data.pictures) if hasattr(doc_data, "pictures") else 0

        peak_vram_mb = (
            torch.cuda.max_memory_allocated() / (1024 * 1024) if cuda_available else 0.0
        )

        logger.info(
            "Page %d: Elapsed=%.2fs, PeakVRAM=%.1fMB, Tables=%d, Texts=%d, Pictures=%d",
            page_num,
            elapsed,
            peak_vram_mb,
            tables_count,
            texts_count,
            pictures_count,
        )

        results.append({
            "page": page_num,
            "elapsed_s": round(elapsed, 2),
            "peak_vram_mb": round(peak_vram_mb, 1),
            "tables_found": tables_count,
            "texts_found": texts_count,
            "pictures_found": pictures_count,
            "device": device_name,
        })

        if temp_pdf.exists():
            try:
                temp_pdf.unlink()
            except OSError:
                pass

    return results


def main() -> None:
    results = run_docling_gpu_benchmark()
    out_file = REPO_ROOT / "benchmark" / "debug" / "docling_gpu_benchmark.json"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(results, indent=2))

    print("\n" + "=" * 80)
    print("DOCLING GPU ACCELERATION BENCHMARK RESULTS")
    print("=" * 80)
    print(f"{'Page':<6} | {'Time (s)':<10} | {'Peak VRAM (MB)':<16} | {'Tables':<8} | {'Texts':<8} | {'Pictures':<8}")
    print("-" * 80)
    for r in results:
        print(
            f"{r['page']:<6} | {r['elapsed_s']:<10.2f} | {r['peak_vram_mb']:<16.1f} | "
            f"{r['tables_found']:<8} | {r['texts_found']:<8} | {r['pictures_found']:<8}"
        )
    print("=" * 80)


if __name__ == "__main__":
    main()

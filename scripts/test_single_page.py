import os
import sys
import time
import json
from pathlib import Path
import fitz  # PyMuPDF
import psutil

# Ensure env vars are set before importing docling
os.environ["TEMP"] = r"D:\DocMind\.cache\tmp"
os.environ["TMP"] = r"D:\DocMind\.cache\tmp"
os.environ["HF_HOME"] = r"D:\DocMind\.cache\huggingface"
os.environ["TORCH_HOME"] = r"D:\DocMind\.cache\torch"
os.environ["DOCLING_ARTIFACTS_PATH"] = r"D:\DocMind\.cache\docling"
os.environ["OMP_NUM_THREADS"] = "2"

from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import (
    PdfPipelineOptions,
    AcceleratorOptions,
    RapidOcrOptions,
)

def extract_single_page(pdf_path: str, page_num: int, out_path: str):
    doc = fitz.open(pdf_path)
    single_doc = fitz.open()
    single_doc.insert_pdf(doc, from_page=page_num - 1, to_page=page_num - 1)
    single_doc.save(out_path)
    single_doc.close()
    doc.close()

def run_page(pdf_path: str, page_num: int, is_scanned: bool = False):
    tmp_dir = Path(r"D:\DocMind\.cache\tmp")
    tmp_dir.mkdir(parents=True, exist_ok=True)
    temp_pdf = tmp_dir / f"temp_p{page_num}_{'scanned' if is_scanned else 'digital'}.pdf"
    
    extract_single_page(pdf_path, page_num, str(temp_pdf))
    
    accel = AcceleratorOptions(num_threads=2)
    pipeline_opts = PdfPipelineOptions(
        artifacts_path=r"D:\DocMind\.cache\docling",
        accelerator_options=accel,
        do_table_structure=True,
        do_ocr=is_scanned,
        do_code_enrichment=False,
        do_formula_enrichment=False,
        do_picture_classification=False,
        do_picture_description=False,
        generate_parsed_pages=True,
    )
    if is_scanned:
        pipeline_opts.ocr_options = RapidOcrOptions(backend="onnxruntime", lang=["en"])

    converter = DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_opts)
        }
    )
    
    start_time = time.time()
    res = converter.convert(str(temp_pdf))
    elapsed = time.time() - start_time
    
    doc = res.document
    md = doc.export_to_markdown()
    data = doc.export_to_dict()
    
    print(f"--- SUCCESS: Page {page_num} ({'Scanned' if is_scanned else 'Digital'}) in {elapsed:.2f}s ---")
    print(f"Num tables: {len(doc.tables)}")
    print("Markdown preview (first 500 chars):")
    print(md[:500])
    
    # Clean up temp pdf
    if temp_pdf.exists():
        temp_pdf.unlink()

if __name__ == "__main__":
    page = int(sys.argv[1]) if len(sys.argv) > 1 else 2
    scanned = sys.argv[2].lower() == "true" if len(sys.argv) > 2 else False
    pdf_file = "benchmark/sample_1_scanned.pdf" if scanned else "benchmark/sample_1.pdf"
    run_page(pdf_file, page, scanned)

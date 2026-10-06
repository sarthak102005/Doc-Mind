import os
import sys
import time
import json
import argparse
from pathlib import Path
import pymupdf

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
    doc = pymupdf.open(pdf_path)
    single_doc = pymupdf.open()
    single_doc.insert_pdf(doc, from_page=page_num - 1, to_page=page_num - 1)
    single_doc.save(out_path)
    single_doc.close()
    doc.close()

def main():
    parser = argparse.ArgumentParser(description="Process a single page with Docling")
    parser.add_argument("--pdf", required=True, help="Source PDF file")
    parser.add_argument("--page", type=int, required=True, help="1-indexed page number")
    parser.add_argument("--is-scanned", action="store_true", help="Whether PDF is scanned (enables RapidOCR)")
    parser.add_argument("--out-dir", default="benchmark/debug", help="Output directory")
    args = parser.parse_args()

    doc_slug = "sample_1_scanned" if args.is_scanned else "sample_1"
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    tmp_dir = Path(r"D:\DocMind\.cache\tmp")
    tmp_dir.mkdir(parents=True, exist_ok=True)
    temp_pdf = tmp_dir / f"page_proc_{doc_slug}_p{args.page}.pdf"

    extract_single_page(args.pdf, args.page, str(temp_pdf))

    accel = AcceleratorOptions(num_threads=2)
    pipeline_opts = PdfPipelineOptions(
        artifacts_path=r"D:\DocMind\.cache\docling",
        accelerator_options=accel,
        do_table_structure=True,
        do_ocr=args.is_scanned,
        do_code_enrichment=False,
        do_formula_enrichment=False,
        do_picture_classification=False,
        do_picture_description=False,
        generate_parsed_pages=True,
    )
    if args.is_scanned:
        pipeline_opts.ocr_options = RapidOcrOptions(backend="onnxruntime", lang=["en"])

    converter = DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_opts)
        }
    )

    t0 = time.time()
    conv_res = converter.convert(str(temp_pdf))
    elapsed = time.time() - t0

    doc = conv_res.document
    md = doc.export_to_markdown()
    doc_dict = doc.export_to_dict()

    # Extract tables with data and bounding boxes
    tables_data = []
    for idx, table in enumerate(doc.tables):
        tbl_info = {
            "table_index": idx,
            "num_rows": table.data.num_rows,
            "num_cols": table.data.num_cols,
            "markdown": table.export_to_markdown(),
            "csv": table.export_to_dataframe().to_csv(index=False),
        }
        if hasattr(table, "prov") and table.prov:
            tbl_info["prov"] = [
                {
                    "page_no": p.page_no,
                    "bbox": {
                        "l": p.bbox.l,
                        "t": p.bbox.t,
                        "r": p.bbox.r,
                        "b": p.bbox.b,
                        "coord_origin": str(p.bbox.coord_origin),
                    } if hasattr(p, "bbox") and p.bbox else None
                }
                for p in table.prov
            ]
        tables_data.append(tbl_info)

    # Save output artifacts
    prefix = f"{doc_slug}_p{args.page}"
    with open(out_dir / f"{prefix}_tree.json", "w", encoding="utf-8") as f:
        json.dump(doc_dict, f, indent=2, ensure_ascii=False)

    with open(out_dir / f"{prefix}_md.md", "w", encoding="utf-8") as f:
        f.write(md)

    with open(out_dir / f"{prefix}_tables.json", "w", encoding="utf-8") as f:
        json.dump(tables_data, f, indent=2, ensure_ascii=False)

    # For scanned documents, also extract pure text elements for OCR evaluation
    if args.is_scanned:
        ocr_texts = []
        if "texts" in doc_dict:
            for item in doc_dict["texts"]:
                ocr_texts.append({
                    "text": item.get("text", ""),
                    "label": item.get("label", ""),
                    "prov": item.get("prov", [])
                })
        with open(out_dir / f"{prefix}_ocr.json", "w", encoding="utf-8") as f:
            json.dump(ocr_texts, f, indent=2, ensure_ascii=False)

    # Clean up temp PDF
    if temp_pdf.exists():
        temp_pdf.unlink()

    result_summary = {
        "page": args.page,
        "is_scanned": args.is_scanned,
        "elapsed_sec": round(elapsed, 2),
        "num_tables": len(doc.tables),
        "num_items": len(doc_dict.get("body", {}).get("children", [])),
    }
    print(f"PAGE_DONE:{json.dumps(result_summary)}")

if __name__ == "__main__":
    main()

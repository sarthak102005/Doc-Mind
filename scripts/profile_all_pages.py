"""Profile all 24 pages across sample_1.pdf and sample_1_scanned.pdf.
Prints the complete routing table with per-page timings and metrics.
"""

from pathlib import Path
import pymupdf
from app.ingestion.profile import profile_page

def main():
    root = Path(__file__).resolve().parent.parent
    pdf_paths = [
        ("sample_1.pdf (Digital)", root / "benchmark" / "sample_1.pdf"),
        ("sample_1_scanned.pdf (Scanned)", root / "benchmark" / "sample_1_scanned.pdf"),
    ]

    print(f"{'PDF':<32} | {'Page':<4} | {'Route':<12} | {'Chars':<6} | {'Img Ratio':<9} | {'Quality':<7} | {'Cols':<4} | {'Time (ms)':<9}")
    print("-" * 98)

    total_time = 0.0
    page_count = 0

    for label, path in pdf_paths:
        if not path.exists():
            print(f"Error: {path} not found")
            continue
        doc = pymupdf.open(str(path))
        num_pages = len(doc)
        for page_idx in range(num_pages):
            page_obj = doc[page_idx]
            prof = profile_page(page_obj, page_number=page_idx + 1)
            total_time += prof.duration_ms
            page_count += 1
            print(
                f"{label:<32} | {prof.page_number:<4} | {prof.route:<12} | "
                f"{prof.char_count:<6} | {prof.image_area_ratio:<9.3f} | {prof.text_quality:<7.3f} | "
                f"{prof.column_count_est:<4} | {prof.duration_ms:<9.2f}"
            )

    avg_time = total_time / max(1, page_count)
    print("-" * 98)
    print(f"Total pages profiled: {page_count} | Total time: {total_time:.2f} ms | Avg per-page time: {avg_time:.2f} ms")

if __name__ == "__main__":
    main()

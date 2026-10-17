"""Synthetic test PDF generation for DocMind generalization benchmark.

Generates:
1. synthetic_article_2col.pdf: Two-column research article with full-width header,
   columnar text, inline footnote markers, and bottom footnote.
2. synthetic_ruled_table.pdf: Fully ruled tabular specification document with
   table headers, multi-row numerical values, units, and footnotes.
"""

from pathlib import Path
import pymupdf

OUT_DIR = Path("D:/DocMind/benchmark/generalization")
OUT_DIR.mkdir(parents=True, exist_ok=True)


def generate_synthetic_article() -> Path:
    """Generate 2-column article with footnote and repeated boilerplate."""
    doc = pymupdf.open()
    # A4: 595 x 842 pt
    page = doc.new_page(width=595, height=842)

    # 1. Repeated header boilerplate
    page.insert_text(pymupdf.Point(50, 40), "JOURNAL OF ENTERPRISE AI - VOL 4, ISSUE 2", fontsize=9, color=(0.4, 0.4, 0.4))
    page.draw_line(pymupdf.Point(50, 48), pymupdf.Point(545, 48), color=(0.7, 0.7, 0.7), width=0.5)

    # 2. Full-width title & abstract band
    page.insert_text(pymupdf.Point(50, 80), "Deep Document Intelligence in Enterprise Workflows", fontsize=18, fontname="helv", color=(0.1, 0.1, 0.1))
    page.insert_text(pymupdf.Point(50, 102), "A Comparative Analysis of Multimodal Layout Models and Heuristic Routing", fontsize=11, fontname="tiro", color=(0.3, 0.3, 0.3))

    abstract_text = (
        "Abstract—Enterprise document intelligence systems must process diverse layout typologies without "
        "manual intervention. We evaluate deterministic reading order routing across complex multi-column documents."
    )
    rect_abs = pymupdf.Rect(50, 120, 545, 155)
    page.insert_textbox(rect_abs, abstract_text, fontsize=9.5, fontname="helv")
    page.draw_line(pymupdf.Point(50, 165), pymupdf.Point(545, 165), color=(0.8, 0.8, 0.8), width=0.5)

    # 3. Two-Column Body Text
    col1_rect = pymupdf.Rect(50, 180, 285, 720)
    col2_rect = pymupdf.Rect(310, 180, 545, 720)

    col1_text = (
        "1. INTRODUCTION\n\n"
        "Modern enterprise pipelines routinely encounter complex multi-column service brochures, technical manuals, "
        "and legal contracts. A naive top-to-bottom reading order merges text across column gutters, corrupting semantic "
        "context for downstream retrieval-augmented generation.\n\n"
        "Deterministic horizontal band segmentation clusters words by vertical separation before applying column sorting. "
        "This prevents full-width section titles from being partitioned into column fragments.\n\n"
        "2. FOOTNOTE HANDLING\n\n"
        "Footnotes located at the bottom of the page [1] must not interleave with the terminal paragraphs of either column."
    )

    col2_text = (
        "3. EXPERIMENTAL VALIDATION\n\n"
        "We evaluate precision and recall across synthetic and real-world benchmarks. Multi-column documents demonstrate "
        "robust column boundary detection when gap thresholds adapt dynamically to local line heights.\n\n"
        "4. CONCLUSION\n\n"
        "Heuristic routing provides deterministic guarantees and sub-second processing latencies, making it an ideal "
        "primary ingestion engine prior to selective neural invocation."
    )

    page.insert_textbox(col1_rect, col1_text, fontsize=9.5, fontname="helv")
    page.insert_textbox(col2_rect, col2_text, fontsize=9.5, fontname="helv")

    # 4. Footnote at bottom
    page.draw_line(pymupdf.Point(50, 750), pymupdf.Point(180, 750), color=(0.5, 0.5, 0.5), width=0.5)
    page.insert_text(pymupdf.Point(50, 765), "[1] Document processing pipelines require deterministic reading order.", fontsize=8, color=(0.3, 0.3, 0.3))

    # 5. Footer boilerplate
    page.draw_line(pymupdf.Point(50, 800), pymupdf.Point(545, 800), color=(0.7, 0.7, 0.7), width=0.5)
    page.insert_text(pymupdf.Point(50, 815), "CONFIDENTIAL & PROPRIETARY | PAGE 1", fontsize=8, color=(0.4, 0.4, 0.4))

    out_file = OUT_DIR / "synthetic_article_2col.pdf"
    doc.save(str(out_file))
    doc.close()
    return out_file


def generate_synthetic_ruled_table() -> Path:
    """Generate ruled table with headers, numeric data, and footnotes."""
    doc = pymupdf.open()
    page = doc.new_page(width=792, height=612)  # Landscape US Letter

    # Boilerplate Header
    page.insert_text(pymupdf.Point(50, 40), "FACTORY INDUSTRIAL EQUIPMENT - TECHNICAL SPECIFICATION SHEET", fontsize=9, color=(0.4, 0.4, 0.4))
    page.draw_line(pymupdf.Point(50, 48), pymupdf.Point(742, 48), color=(0.7, 0.7, 0.7), width=0.5)

    # Table Title
    page.insert_text(pymupdf.Point(50, 80), "Table 1: Operational Specifications and Power Ratings", fontsize=14, fontname="helv")

    # Ruled Table Boundaries
    x_cols = [50, 180, 320, 480, 620, 742]
    y_rows = [110, 140, 180, 220, 260, 300]

    # Draw grid lines
    for y in y_rows:
        page.draw_line(pymupdf.Point(x_cols[0], y), pymupdf.Point(x_cols[-1], y), color=(0.2, 0.2, 0.2), width=1.0)
    for x in x_cols:
        page.draw_line(pymupdf.Point(x, y_rows[0]), pymupdf.Point(x, y_rows[-1]), color=(0.2, 0.2, 0.2), width=1.0)

    # Fill Table Header
    headers = ["Model Name", "Deck Type", "Battery System", "Run Time (hrs)**", "Operating Weight"]
    for i in range(len(headers)):
        rect = pymupdf.Rect(x_cols[i] + 5, y_rows[0] + 5, x_cols[i+1] - 5, y_rows[1] - 5)
        page.insert_textbox(rect, headers[i], fontsize=10, fontname="helv")

    # Rows Data
    table_data = [
        ["Micro-HD 20D", "Disk (20\")", "24V / 130 ah", "2.5 - 3.0 hrs**", "441 - 481 lbs"],
        ["Micro-HD 24D", "Disk (24\")", "24V / 210 ah", "3.5 - 4.0 hrs**", "515 - 555 lbs"],
        ["Mini-HD 26C", "Cylindrical (26\")", "24V / 245 ah", "3.0 - 3.5 hrs**", "620 - 680 lbs"],
        ["Mag-HD 30D", "Disk (30\")", "36V / 315 ah", "4.5 - 5.0 hrs**", "815 - 885 lbs"],
    ]

    for r_idx, row in enumerate(table_data):
        y0 = y_rows[r_idx + 1]
        y1 = y_rows[r_idx + 2]
        for c_idx, val in enumerate(row):
            rect = pymupdf.Rect(x_cols[c_idx] + 5, y0 + 5, x_cols[c_idx+1] - 5, y1 - 5)
            page.insert_textbox(rect, val, fontsize=9.5, fontname="helv")

    # Footnote below table
    page.insert_text(pymupdf.Point(50, 330), "** Run times are estimated based on continuous scrubbing in standard power mode.", fontsize=8.5, color=(0.3, 0.3, 0.3))
    page.insert_text(pymupdf.Point(50, 345), "* Machine weights include standard battery pack and empty solution/recovery tanks.", fontsize=8.5, color=(0.3, 0.3, 0.3))

    # Boilerplate Footer
    page.draw_line(pymupdf.Point(50, 560), pymupdf.Point(742, 560), color=(0.7, 0.7, 0.7), width=0.5)
    page.insert_text(pymupdf.Point(50, 575), "CONFIDENTIAL | WWW.FACTORYCAT.COM | SUBJECT TO CHANGE WITHOUT NOTICE", fontsize=8, color=(0.4, 0.4, 0.4))

    out_file = OUT_DIR / "synthetic_ruled_table.pdf"
    doc.save(str(out_file))
    doc.close()
    return out_file


def generate_synthetic_side_by_side_tables() -> Path:
    """Generate page with two independent side-by-side tables separated by a horizontal gutter."""
    doc = pymupdf.open()
    page = doc.new_page(width=792, height=612)

    # Boilerplate Header
    page.insert_text(pymupdf.Point(50, 40), "TECHNICAL COMPONENT COMPARISON - FACTORY CAT SYSTEMS", fontsize=9, color=(0.4, 0.4, 0.4))
    page.draw_line(pymupdf.Point(50, 48), pymupdf.Point(742, 48), color=(0.7, 0.7, 0.7), width=0.5)

    # --- Table 1 (Left): Motor Specifications ---
    page.insert_text(pymupdf.Point(50, 80), "Table 1: Brush Motor Power Ratings", fontsize=12, fontname="helv")
    x1_cols = [50, 160, 260, 360]
    y1_rows = [100, 125, 155, 185, 215]
    for y in y1_rows:
        page.draw_line(pymupdf.Point(x1_cols[0], y), pymupdf.Point(x1_cols[-1], y), color=(0.2, 0.2, 0.2), width=0.8)
    for x in x1_cols:
        page.draw_line(pymupdf.Point(x, y1_rows[0]), pymupdf.Point(x, y1_rows[-1]), color=(0.2, 0.2, 0.2), width=0.8)

    t1_headers = ["Deck System", "Motor HP", "Speed (RPM)"]
    for i in range(len(t1_headers)):
        rect = pymupdf.Rect(x1_cols[i] + 4, y1_rows[0] + 3, x1_cols[i+1] - 4, y1_rows[1] - 3)
        page.insert_textbox(rect, t1_headers[i], fontsize=9, fontname="helv")

    t1_data = [
        ["Disk 20\"", "0.75 HP", "200 RPM"],
        ["Disk 24\"", "1.00 HP", "200 RPM"],
        ["Cylindrical 26\"", "0.75 HP (x2)", "750 RPM"],
    ]
    for r_idx, row in enumerate(t1_data):
        y0, y1 = y1_rows[r_idx + 1], y1_rows[r_idx + 2]
        for c_idx, val in enumerate(row):
            rect = pymupdf.Rect(x1_cols[c_idx] + 4, y0 + 3, x1_cols[c_idx+1] - 4, y1 - 3)
            page.insert_textbox(rect, val, fontsize=8.5, fontname="helv")

    # --- Table 2 (Right): Tank Capacities ---
    page.insert_text(pymupdf.Point(420, 80), "Table 2: Fluid Recovery & Solution Tanks", fontsize=12, fontname="helv")
    x2_cols = [420, 520, 620, 740]
    y2_rows = [100, 125, 155, 185, 215]
    for y in y2_rows:
        page.draw_line(pymupdf.Point(x2_cols[0], y), pymupdf.Point(x2_cols[-1], y), color=(0.2, 0.2, 0.2), width=0.8)
    for x in x2_cols:
        page.draw_line(pymupdf.Point(x, y2_rows[0]), pymupdf.Point(x, y2_rows[-1]), color=(0.2, 0.2, 0.2), width=0.8)

    t2_headers = ["Chassis", "Solution Tank", "Recovery Tank"]
    for i in range(len(t2_headers)):
        rect = pymupdf.Rect(x2_cols[i] + 4, y2_rows[0] + 3, x2_cols[i+1] - 4, y2_rows[1] - 3)
        page.insert_textbox(rect, t2_headers[i], fontsize=9, fontname="helv")

    t2_data = [
        ["Micro-HD", "10 Gallons", "10 Gallons"],
        ["Mini-HD", "16 Gallons", "16 Gallons"],
        ["Mag-HD", "26 Gallons", "27 Gallons"],
    ]
    for r_idx, row in enumerate(t2_data):
        y0, y1 = y2_rows[r_idx + 1], y2_rows[r_idx + 2]
        for c_idx, val in enumerate(row):
            rect = pymupdf.Rect(x2_cols[c_idx] + 4, y0 + 3, x2_cols[c_idx+1] - 4, y1 - 3)
            page.insert_textbox(rect, val, fontsize=8.5, fontname="helv")

    # Boilerplate Footer
    page.draw_line(pymupdf.Point(50, 560), pymupdf.Point(742, 560), color=(0.7, 0.7, 0.7), width=0.5)
    page.insert_text(pymupdf.Point(50, 575), "CONFIDENTIAL & PROPRIETARY | WWW.FACTORYCAT.COM", fontsize=8, color=(0.4, 0.4, 0.4))

    out_file = OUT_DIR / "synthetic_side_by_side_tables.pdf"
    doc.save(str(out_file))
    doc.close()
    return out_file


def generate_synthetic_borderless_table() -> Path:
    """Generate page with a single borderless multi-column table (no vector grid lines)."""
    doc = pymupdf.open()
    page = doc.new_page(width=792, height=612)

    # Boilerplate Header
    page.insert_text(pymupdf.Point(50, 40), "DIMENSIONAL METRICS AND ACOUSTIC RATINGS - FIELD TEST DATA", fontsize=9, color=(0.4, 0.4, 0.4))
    page.draw_line(pymupdf.Point(50, 48), pymupdf.Point(742, 48), color=(0.7, 0.7, 0.7), width=0.5)

    # Table Title
    page.insert_text(pymupdf.Point(50, 80), "Table 1: Acoustic Profiles and Sound Pressure Levels", fontsize=14, fontname="helv")

    # Borderless columns defined purely by spatial layout (no lines)
    col_x = [50, 220, 400, 580]
    headers = ["Machine Configuration", "Operating Mode", "Sound Level (dBA)", "Vibration (m/s2)"]
    for i, h in enumerate(headers):
        page.insert_text(pymupdf.Point(col_x[i], 115), h, fontsize=10, fontname="helv", color=(0.1, 0.1, 0.1))

    # Data rows
    rows = [
        ["Micro-HD 20D Standard", "Eco Scrubbing Mode", "62 dBA", "0.45 m/s2"],
        ["Micro-HD 24D Heavy Duty", "Standard Scrubbing Mode", "65 dBA", "0.52 m/s2"],
        ["Mini-HD 26C Cylindrical", "High Pressure Scrubbing", "68 dBA", "0.68 m/s2"],
        ["Mag-HD 30D Dual Disk", "Deep Strip Protocol", "70 dBA", "0.74 m/s2"],
    ]

    y = 150
    for r in rows:
        for i, val in enumerate(r):
            page.insert_text(pymupdf.Point(col_x[i], y), val, fontsize=9.5, fontname="helv")
        y += 30

    # Footnote
    page.insert_text(pymupdf.Point(50, 310), "* Sound pressure measured at operator ear level per ISO 11201 standards.", fontsize=8.5, color=(0.3, 0.3, 0.3))

    # Boilerplate Footer
    page.draw_line(pymupdf.Point(50, 560), pymupdf.Point(742, 560), color=(0.7, 0.7, 0.7), width=0.5)
    page.insert_text(pymupdf.Point(50, 575), "CONFIDENTIAL | FIELD METRICS SPECIFICATION", fontsize=8, color=(0.4, 0.4, 0.4))

    out_file = OUT_DIR / "synthetic_borderless_table.pdf"
    doc.save(str(out_file))
    doc.close()
    return out_file


if __name__ == "__main__":
    f1 = generate_synthetic_article()
    f2 = generate_synthetic_ruled_table()
    f3 = generate_synthetic_side_by_side_tables()
    f4 = generate_synthetic_borderless_table()
    print("Generated:", f1)
    print("Generated:", f2)
    print("Generated:", f3)
    print("Generated:", f4)

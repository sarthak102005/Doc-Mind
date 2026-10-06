import json
from pathlib import Path

debug_dir = Path(r"D:\DocMind\benchmark\debug")

def inspect_page2():
    print("=== INSPECTING PAGE 2 ===")
    md_p2 = (debug_dir / "sample_1_p2_md.md").read_text(encoding="utf-8")
    print("--- sample_1_p2_md.md ---")
    print(md_p2)
    
    md_scanned_p2 = (debug_dir / "sample_1_scanned_p2_md.md").read_text(encoding="utf-8")
    print("\n--- sample_1_scanned_p2_md.md ---")
    print(md_scanned_p2)

def inspect_page3():
    print("\n=== INSPECTING PAGE 3 ===")
    md_p3 = (debug_dir / "sample_1_p3_md.md").read_text(encoding="utf-8")
    print("--- sample_1_p3_md.md ---")
    print(md_p3)
    
    md_scanned_p3 = (debug_dir / "sample_1_scanned_p3_md.md").read_text(encoding="utf-8")
    print("\n--- sample_1_scanned_p3_md.md ---")
    print(md_scanned_p3)

def inspect_page4():
    print("\n=== INSPECTING PAGE 4 ===")
    md_p4 = (debug_dir / "sample_1_p4_md.md").read_text(encoding="utf-8")
    print("--- sample_1_p4_md.md ---")
    print(md_p4)

    tree_p4 = json.loads((debug_dir / "sample_1_p4_tree.json").read_text(encoding="utf-8"))
    texts_p4 = [t.get("text") for t in tree_p4.get("texts", [])]
    print("Page 4 extracted text items:", len(texts_p4), texts_p4[:10])

def inspect_page11():
    print("\n=== INSPECTING PAGE 11 ===")
    tables_digital = json.loads((debug_dir / "sample_1_p11_tables.json").read_text(encoding="utf-8"))
    print(f"sample_1_p11_tables.json count: {len(tables_digital)}")
    for idx, tbl in enumerate(tables_digital):
        print(f"\n--- Digital Table {idx+1} ({tbl['num_rows']}x{tbl['num_cols']}) ---")
        print("BBox:", tbl.get("prov"))
        print(tbl["markdown"][:600])

    tables_scanned = json.loads((debug_dir / "sample_1_scanned_p11_tables.json").read_text(encoding="utf-8"))
    print(f"\nsample_1_scanned_p11_tables.json count: {len(tables_scanned)}")
    for idx, tbl in enumerate(tables_scanned):
        print(f"\n--- Scanned Table {idx+1} ({tbl['num_rows']}x{tbl['num_cols']}) ---")
        print("BBox:", tbl.get("prov"))
        print(tbl["markdown"][:600])

if __name__ == "__main__":
    inspect_page2()
    inspect_page3()
    inspect_page4()
    inspect_page11()

"""Unit tests for Stage 3: Boilerplate & Margin Stripper (Addendum A2.4).

Verifies:
1. Multi-page boilerplate detection learns repeating templates across pages.
2. Printed page numbers are extracted per page.
3. Legal and contact information is preserved at the document level.
4. Single-occurrence margin lines (such as cover taglines) are preserved and never stripped.
5. Digit normalization collapses numbered running headers into repeating templates.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.ingestion.boilerplate import (
    BoilerplateDetector,
    extract_page_number_from_text,
    is_contact_or_legal_text,
    normalize_boilerplate_text,
)
from app.ingestion.reading_order import WordBox

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.mark.unit
def test_normalize_boilerplate_text() -> None:
    """Verify digit normalization replaces variable page/chapter numbers with '#'."""
    assert normalize_boilerplate_text("FC-WALK-BEHIND 2") == "fc-walk-behind #"
    assert normalize_boilerplate_text("Page 11 of 12") == "page # of #"
    assert normalize_boilerplate_text("Chapter 3: Maintenance") == "chapter #: maintenance"
    assert normalize_boilerplate_text("www.factorycat.com  262-681-3583") == "www.factorycat.com #-#-#"


@pytest.mark.unit
def test_extract_page_number_from_text() -> None:
    """Verify page number extraction from bare digits and formatted strings."""
    assert extract_page_number_from_text("2") == 2
    assert extract_page_number_from_text("11") == 11
    assert extract_page_number_from_text("Page 4") == 4
    assert extract_page_number_from_text("p. 12") == 12
    assert extract_page_number_from_text("Not A Page") is None


@pytest.mark.unit
def test_contact_and_legal_text_detection() -> None:
    """Verify identification of legal disclaimers, URLs, and phone numbers."""
    legal_text = (
        "www.factorycat.com 262-681-3583 RPS Corporation, 1711 South St, "
        "Racine, WI, 53404, USA *Images could include non-standard options. "
        "Subject to change without notice."
    )
    assert is_contact_or_legal_text(legal_text) is True
    assert is_contact_or_legal_text("Ordinary section content") is False


@pytest.mark.unit
def test_boilerplate_multi_page_learning_on_fixtures() -> None:
    """Verify multi-page boilerplate detection on committed fixtures (pages 2, 3, 4, 11)."""
    pages_words: list[tuple[int, list[WordBox], float, float]] = []

    for p in [2, 3, 4, 11]:
        fpath = FIXTURES_DIR / f"wordboxes_sample_1_p{p}.json"
        assert fpath.exists()
        with open(fpath, encoding="utf-8") as f:
            data = json.load(f)
        words = [WordBox(**b) for b in data["words"]]
        pages_words.append((p, words, float(data["page_width"]), float(data["page_height"])))

    detector = BoilerplateDetector(top_margin_ratio=0.10, bottom_margin_ratio=0.10, min_page_repetitions=2)
    doc_summary = detector.analyze_document(pages_words)

    # 1. Repeating footer templates must be discovered
    assert len(doc_summary.repeated_templates) > 0

    # 2. Legal / contact lines must be captured at document level
    assert len(doc_summary.legal_and_contact_lines) > 0
    all_legal = " ".join(doc_summary.legal_and_contact_lines)
    assert "factorycat.com" in all_legal or "rps" in all_legal.lower()

    # 3. Strip boilerplate from each page and verify printed page numbers
    page_numbers: dict[int, int] = {}
    for p_num, words, pw, ph in pages_words:
        res = detector.strip_page_boilerplate(p_num, words, pw, ph, doc_summary)
        assert len(res.stripped_lines) > 0
        if res.printed_page_number is not None:
            page_numbers[p_num] = res.printed_page_number

        # Ensure body content was preserved
        assert len(res.cleaned_words) > 0
        assert len(res.cleaned_words) < len(words)

    # Page numbers 2, 3, 4 should be discovered from the footers
    assert page_numbers.get(2) == 2
    assert page_numbers.get(3) == 3
    assert page_numbers.get(4) == 4


@pytest.mark.unit
def test_single_occurrence_preservation_in_margin() -> None:
    """Verify that a unique margin line appearing on only 1 page (e.g. cover tagline) is NOT stripped."""
    # Page 1 has a unique header tagline in top margin
    p1_words = [
        WordBox(text="FactoryCat", l=50.0, t=20.0, r=150.0, b=40.0, font_size=16.0),
        WordBox(text="Hard-Working", l=160.0, t=20.0, r=260.0, b=40.0, font_size=16.0),
        WordBox(text="Industrial", l=270.0, t=20.0, r=350.0, b=40.0, font_size=16.0),
        WordBox(text="Cleaners", l=360.0, t=20.0, r=440.0, b=40.0, font_size=16.0),
        # Body text
        WordBox(text="Body", l=50.0, t=200.0, r=100.0, b=220.0, font_size=12.0),
    ]

    # Pages 2 and 3 do not have this tagline
    p2_words = [
        WordBox(text="Other", l=50.0, t=200.0, r=100.0, b=220.0, font_size=12.0),
    ]
    p3_words = [
        WordBox(text="Content", l=50.0, t=200.0, r=100.0, b=220.0, font_size=12.0),
    ]

    pages_data = [
        (1, p1_words, 600.0, 800.0),
        (2, p2_words, 600.0, 800.0),
        (3, p3_words, 600.0, 800.0),
    ]

    detector = BoilerplateDetector(top_margin_ratio=0.10, bottom_margin_ratio=0.10, min_page_repetitions=2)
    doc_summary = detector.analyze_document(pages_data)

    # Unique tagline must NOT be in repeated templates
    assert not any("cleaners" in tpl for tpl in doc_summary.repeated_templates)

    # Strip Page 1
    res = detector.strip_page_boilerplate(1, p1_words, 600.0, 800.0, doc_summary)
    cleaned_texts = [w.text for w in res.cleaned_words]

    # All tagline words must remain!
    assert "FactoryCat" in cleaned_texts
    assert "Hard-Working" in cleaned_texts
    assert "Industrial" in cleaned_texts
    assert "Cleaners" in cleaned_texts


@pytest.mark.unit
def test_digit_normalization_collapses_running_headers() -> None:
    """Verify that headers varying only by page or section number are stripped across pages."""
    def make_page_with_header(page_num: int) -> list[WordBox]:
        return [
            # Top margin running header: "Section X - Overview"
            WordBox(text="Section", l=50.0, t=20.0, r=100.0, b=35.0, font_size=10.0),
            WordBox(text=str(page_num), l=105.0, t=20.0, r=120.0, b=35.0, font_size=10.0),
            WordBox(text="-", l=125.0, t=20.0, r=135.0, b=35.0, font_size=10.0),
            WordBox(text="Overview", l=140.0, t=20.0, r=200.0, b=35.0, font_size=10.0),
            # Body
            WordBox(
                text=f"Body paragraph for page {page_num}",
                l=50.0,
                t=200.0,
                r=250.0,
                b=220.0,
                font_size=11.0,
            ),
        ]

    pages_data = [
        (1, make_page_with_header(1), 600.0, 800.0),
        (2, make_page_with_header(2), 600.0, 800.0),
        (3, make_page_with_header(3), 600.0, 800.0),
    ]

    detector = BoilerplateDetector(top_margin_ratio=0.10, bottom_margin_ratio=0.10, min_page_repetitions=2)
    doc_summary = detector.analyze_document(pages_data)

    # Normalized template "section # - overview" must be in repeated_templates
    assert "section # - overview" in doc_summary.repeated_templates

    # On Page 2, the running header must be stripped, while body remains
    res2 = detector.strip_page_boilerplate(2, pages_data[1][1], 600.0, 800.0, doc_summary)
    cleaned_texts = [w.text for w in res2.cleaned_words]

    assert "Section" not in cleaned_texts
    assert "Overview" not in cleaned_texts
    assert "Body paragraph for page 2" in cleaned_texts


@pytest.mark.unit
def test_scanned_route_preserves_margin_words_page9() -> None:
    """Verify that scanned-route extraction does NOT drop margin words before boilerplate detection.

    Ensures that printed page numbers and legal text from sample_1_scanned_250dpi.pdf Page 9
    are preserved as metadata.
    """
    from app.ingestion.reading_order import extract_page_words

    pdf_path = Path(__file__).resolve().parents[2] / "benchmark" / "sample_1_scanned_250dpi.pdf"
    if not pdf_path.exists():
        pytest.skip("sample_1_scanned_250dpi.pdf not found")

    words, pw, ph = extract_page_words(pdf_path, 9, route="scanned")

    # 1. Assert margin words are not dropped prior to boilerplate analysis
    margin_words = [w for w in words if w.b > ph * 0.90]
    assert len(margin_words) >= 4, f"Expected margin words in scanned route, got {len(margin_words)}"
    margin_texts = [w.text for w in margin_words]
    assert any("9" in t for t in margin_texts), "Printed page number '9' must be extracted"
    assert any("rps" in t.lower() or "notice" in t.lower() for t in margin_texts), "Legal text must be extracted"

    # 2. Run boilerplate detector and verify metadata recording
    detector = BoilerplateDetector(top_margin_ratio=0.10, bottom_margin_ratio=0.10, min_page_repetitions=1)
    summary = detector.analyze_document([(9, words, pw, ph)])

    assert len(summary.legal_and_contact_lines) > 0, "Legal text must be recorded in summary metadata"

    # 3. Strip page boilerplate and verify page number recorded
    result = detector.strip_page_boilerplate(9, words, pw, ph, summary)
    assert result.printed_page_number == 9, f"Expected printed page number 9, got {result.printed_page_number}"
    assert len(result.stripped_lines) > 0

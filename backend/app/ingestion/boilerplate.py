"""Boilerplate and margin text detection module (Addendum A2.4).

Detects and strips repeated headers, footers, and legal/contact lines in relative
page margins (top and bottom 8-12%) across pages using digit normalization and
frequency matching.
Preserves single-occurrence text (such as cover taglines), records printed page
numbers per page, and extracts legal/contact text once at document level.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, Field

from app.ingestion.reading_order import WordBox, group_words_into_lines, normalize_coords_to_topleft


class PageBoilerplateResult(BaseModel):
    """Result of boilerplate analysis on a single document page."""

    page_number: int
    cleaned_words: list[WordBox]
    stripped_lines: list[str] = Field(default_factory=list)
    printed_page_number: int | None = None


class DocumentBoilerplateSummary(BaseModel):
    """Document-level boilerplate registry and metadata."""

    repeated_templates: set[str] = Field(default_factory=set)
    legal_and_contact_lines: list[str] = Field(default_factory=list)
    page_numbers: dict[int, int] = Field(default_factory=dict)


def normalize_boilerplate_text(text: str) -> str:
    """Normalize text for cross-page boilerplate matching by replacing digits with '#'.

    Example: 'FC-WALK-BEHIND 2' -> 'fc-walk-behind #'
             'Page 11 of 12' -> 'page # of #'
    """
    clean = text.strip().lower()
    # Replace sequences of digits with a single '#' placeholder
    clean = re.sub(r"\d+", "#", clean)
    # Normalize excessive spaces and punctuation
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean


def is_contact_or_legal_text(text: str) -> bool:
    """Check if a line contains legal, copyright, address, or contact metadata."""
    contact_patterns = [
        r"\b(?:https?://|www\.)\S+",
        r"\b\d{3}[-.\s]\d{3}[-.\s]\d{4}\b",  # phone number
        r"\b(?:corporation|inc\.|llc|ltd|gmbh)\b",
        r"\b(?:all rights reserved|subject to change|copyright|\(c\)|©)\b",
        r"\b\d{5}(?:-\d{4})?\b",  # zip code
    ]
    return any(bool(re.search(pat, text, re.I)) for pat in contact_patterns)


def extract_page_number_from_text(text: str) -> int | None:
    """Extract printed page number from a standalone digit token or 'page X' pattern."""
    # Pattern 1: standalone single or double digit (e.g. '2', '11')
    m_bare = re.fullmatch(r"(\d{1,3})", text.strip())
    if m_bare:
        return int(m_bare.group(1))

    # Pattern 2: 'page 2', 'p. 2', '- 2 -'
    m_pattern = re.search(r"\b(?:page|p\.?)\s*(\d{1,3})\b", text, re.I)
    if m_pattern:
        return int(m_pattern.group(1))

    return None


class BoilerplateDetector:
    """Multi-page boilerplate analyzer and margin stripper."""

    def __init__(
        self,
        top_margin_ratio: float = 0.10,
        bottom_margin_ratio: float = 0.10,
        min_page_repetitions: int = 2,
    ) -> None:
        self.top_margin_ratio = top_margin_ratio
        self.bottom_margin_ratio = bottom_margin_ratio
        self.min_page_repetitions = min_page_repetitions

    def analyze_document(
        self,
        pages_words: list[tuple[int, list[WordBox], float, float]],
    ) -> DocumentBoilerplateSummary:
        """Scan all document pages to build the frequency map of repeating margin templates.

        Args:
            pages_words: List of tuples (page_number, words, page_width, page_height).
        """
        template_page_counts: dict[str, set[int]] = {}
        legal_contact_candidates: set[str] = set()

        for page_num, words, _page_w, page_h in pages_words:
            norm_words = normalize_coords_to_topleft(words, page_h)
            lines = group_words_into_lines(norm_words, max_x_gap=35.0, y_tolerance=6.0)

            top_threshold = page_h * self.top_margin_ratio
            bottom_threshold = page_h * (1.0 - self.bottom_margin_ratio)

            for line in lines:
                is_in_margin = line["t"] < top_threshold or line["b"] > bottom_threshold
                if not is_in_margin:
                    continue

                line_text = line["text"]
                norm_tpl = normalize_boilerplate_text(line_text)

                if norm_tpl not in template_page_counts:
                    template_page_counts[norm_tpl] = set()
                template_page_counts[norm_tpl].add(page_num)

                if is_contact_or_legal_text(line_text):
                    legal_contact_candidates.add(line_text)

        # Retain only templates occurring across >= min_page_repetitions pages
        repeated_templates = {
            tpl for tpl, page_set in template_page_counts.items()
            if len(page_set) >= self.min_page_repetitions
        }

        # Deduplicate and sort legal/contact lines
        legal_lines = sorted(legal_contact_candidates)

        return DocumentBoilerplateSummary(
            repeated_templates=repeated_templates,
            legal_and_contact_lines=legal_lines,
        )

    def strip_page_boilerplate(
        self,
        page_number: int,
        words: list[WordBox],
        page_width: float,
        page_height: float,
        doc_summary: DocumentBoilerplateSummary,
    ) -> PageBoilerplateResult:
        """Strip boilerplate from a single page using the learned document summary."""
        norm_words = normalize_coords_to_topleft(words, page_height)
        lines = group_words_into_lines(norm_words, max_x_gap=35.0, y_tolerance=6.0)

        top_threshold = page_height * self.top_margin_ratio
        bottom_threshold = page_height * (1.0 - self.bottom_margin_ratio)

        words_to_remove: set[int] = set()
        stripped_lines: list[str] = []
        printed_page_num: int | None = None

        for line in lines:
            is_in_margin = line["t"] < top_threshold or line["b"] > bottom_threshold
            if not is_in_margin:
                continue

            line_text = line["text"]
            norm_tpl = normalize_boilerplate_text(line_text)

            # Check if this line matches a repeating template
            if norm_tpl in doc_summary.repeated_templates:
                for w in line["words"]:
                    words_to_remove.add(id(w))
                stripped_lines.append(line_text)

                # Attempt page number extraction from this stripped margin line
                pg_candidate = extract_page_number_from_text(line_text)
                if pg_candidate is not None:
                    printed_page_num = pg_candidate
            else:
                # Check individual word boxes for standalone page number in bottom margin
                if line["b"] > bottom_threshold:
                    pg_cand = extract_page_number_from_text(line_text)
                    if pg_cand is not None and (pg_cand == page_number or abs(pg_cand - page_number) <= 2):
                        for w in line["words"]:
                            words_to_remove.add(id(w))
                        stripped_lines.append(line_text)
                        printed_page_num = pg_cand

        cleaned_words = [w for w in norm_words if id(w) not in words_to_remove]

        return PageBoilerplateResult(
            page_number=page_number,
            cleaned_words=cleaned_words,
            stripped_lines=stripped_lines,
            printed_page_number=printed_page_num,
        )

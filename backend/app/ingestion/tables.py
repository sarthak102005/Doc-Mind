"""Table segmentation and extraction module (Addendum A2.5, A2.10, DECISIONS D-010).

Derives table zones dynamically from valleys/gaps in word box horizontal X-distributions,
avoiding hardcoded coordinates.
Links table titles by spatial proximity directly above each detected column zone.
Extracts structured table records (entity, section, attribute, value) for downstream storage
and deterministic lookup.
"""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, Field

from app.ingestion.reading_order import (
    WordBox,
    group_words_into_lines,
    normalize_coords_to_topleft,
)


class TableRecord(BaseModel):
    """A single structured attribute-value record extracted from a table row."""

    entity: str
    section: str = "GENERAL"
    attribute: str
    value: str
    unit_variants: dict[str, str] = Field(default_factory=dict)
    footnotes: list[str] = Field(default_factory=list)


class TableZone(BaseModel):
    """A spatially bounded table zone on a document page."""

    zone_id: int
    title: str
    bbox: tuple[float, float, float, float]  # (left, top, right, bottom)
    words: list[WordBox] = Field(default_factory=list)
    sections: list[str] = Field(default_factory=list)
    records: list[TableRecord] = Field(default_factory=list)

    @property
    def left(self) -> float:
        return self.bbox[0]

    @property
    def top(self) -> float:
        return self.bbox[1]

    @property
    def right(self) -> float:
        return self.bbox[2]

    @property
    def bottom(self) -> float:
        return self.bbox[3]


def find_x_distribution_gaps(
    words: list[WordBox],
    page_width: float,
    min_gutter_ratio: float = 0.003,
    min_gutter_pt: float = 2.5,
) -> list[tuple[float, float]]:
    """Detect horizontal gutters (valleys/gaps) between column blocks via 1D X-projection.

    Returns a list of (gap_left, gap_right) coordinates.
    """
    if not words:
        return []

    # 1. Project bounding boxes into 1D intervals along the X axis
    intervals = sorted([[w.l, w.r] for w in words], key=lambda iv: iv[0])
    merged: list[list[float]] = []
    for iv in intervals:
        if not merged or iv[0] > merged[-1][1]:
            merged.append([iv[0], iv[1]])
        else:
            merged[-1][1] = max(merged[-1][1], iv[1])

    gutter_threshold = max(min_gutter_pt, min_gutter_ratio * page_width)

    # 2. Identify gaps between adjacent merged intervals that exceed the threshold
    gaps: list[tuple[float, float]] = []
    for i in range(len(merged) - 1):
        gap_width = merged[i + 1][0] - merged[i][1]
        if gap_width >= gutter_threshold:
            gaps.append((merged[i][1], merged[i + 1][0]))

    return gaps


def link_table_titles_by_proximity(
    zones: list[TableZone],
    candidate_lines: list[dict[str, Any]],
    max_vertical_dist: float = 50.0,
) -> list[TableZone]:
    """Associate table titles with detected zones based on horizontal alignment and vertical proximity."""
    updated_zones: list[TableZone] = []

    for zone in zones:
        zl, zt, zr, _ = zone.bbox

        # Find candidate lines above the table zone that overlap horizontally
        matching_lines = [
            line
            for line in candidate_lines
            if line["b"] <= zt + 15.0  # Allow minor baseline overlap with top row
            and (zt - line["b"]) <= max_vertical_dist
            and (zl - 25.0) <= ((line["l"] + line["r"]) / 2.0) <= (zr + 25.0)
        ]

        if matching_lines:
            # Pick candidate closest to zone top
            matching_lines.sort(key=lambda l: abs(zt - l["b"]))
            best_title = matching_lines[0]["text"]
            zone.title = best_title

        updated_zones.append(zone)

    return updated_zones


def parse_zone_records(
    words: list[WordBox],
    entity: str,
    y_tolerance: float = 4.0,
    max_x_gap: float = 40.0,
) -> tuple[list[str], list[TableRecord]]:
    """Parse words inside a table zone into section headers and attribute-value rows."""
    lines = group_words_into_lines(words, max_x_gap=max_x_gap, y_tolerance=y_tolerance)
    if not lines:
        return [], []

    sections: list[str] = []
    records: list[TableRecord] = []
    curr_section = "GENERAL"

    for line in lines:
        text = line["text"].strip()
        if not text:
            continue

        # Check if line is a section header (all uppercase, no colons/units)
        is_section_header = (
            text.isupper()
            and len(text) > 3
            and not any(delim in text for delim in [":", "LBS", "KG", "RPM", "HP"])
        )

        if is_section_header:
            curr_section = text
            if curr_section not in sections:
                sections.append(curr_section)
            continue

        # Parse key-value attribute pairs
        if ":" in text:
            parts = text.split(":", 1)
            attr = parts[0].strip()
            val = parts[1].strip()
            if attr:
                records.append(
                    TableRecord(
                        entity=entity,
                        section=curr_section,
                        attribute=attr,
                        value=val,
                    )
                )

    return sections, records


def detect_table_zones_from_x_gaps(
    words: list[WordBox],
    page_width: float,
    page_height: float,
    top_margin_ratio: float = 0.08,
    bottom_margin_ratio: float = 0.08,
    min_gutter_ratio: float = 0.003,
    min_gutter_pt: float = 2.5,
) -> list[TableZone]:
    """Segment a page's tabular region into distinct side-by-side table zones using X-gaps.

    Dynamically derives column boundaries from valleys in the word boxes' horizontal
    projection without hardcoded coordinates.
    Links each table title by proximity above the zone and extracts structured records.
    """
    if not words:
        return []

    norm_words = normalize_coords_to_topleft(words, page_height)

    # Exclude page margins (running headers and footers)
    top_limit = page_height * top_margin_ratio
    bot_limit = page_height * (1.0 - bottom_margin_ratio)

    content_words = [w for w in norm_words if top_limit <= w.t and w.b <= bot_limit]
    if not content_words:
        return []

    # 1. Filter out any individual word box that spans wider than 45% of page width
    words_for_gaps = [
        w for w in content_words
        if (w.r - w.l) < (page_width * 0.45)
    ]
    if not words_for_gaps:
        words_for_gaps = content_words

    # 2. Detect gutters along the X axis
    gaps = find_x_distribution_gaps(
        words_for_gaps,
        page_width=page_width,
        min_gutter_ratio=min_gutter_ratio,
        min_gutter_pt=min_gutter_pt,
    )

    # 3. Split horizontal space into column zones
    all_l = min(w.l for w in words_for_gaps)
    all_r = max(w.r for w in words_for_gaps)

    col_ranges: list[tuple[float, float]] = []
    curr_l = all_l
    for gap_l, gap_r in gaps:
        col_ranges.append((curr_l, gap_l))
        curr_l = gap_r
    col_ranges.append((curr_l, all_r))

    # 4. Create TableZones and populate words
    zones: list[TableZone] = []
    for z_idx, (zl, zr) in enumerate(col_ranges):
        # Words belonging to this column zone
        z_words = [
            w for w in content_words
            if (zl - 2.0) <= ((w.l + w.r) / 2.0) <= (zr + 2.0)
        ]
        if len(z_words) < 2:
            continue

        z_lines = group_words_into_lines(z_words, max_x_gap=15.0, y_tolerance=3.5)
        if not z_lines:
            continue

        # Initial title from prominent top line
        title = z_lines[0]["text"]

        bbox = (
            min(w.l for w in z_words),
            min(w.t for w in z_words),
            max(w.r for w in z_words),
            max(w.b for w in z_words),
        )

        sections, records = parse_zone_records(z_words, entity=title)

        zones.append(
            TableZone(
                zone_id=z_idx,
                title=title,
                bbox=bbox,
                words=z_words,
                sections=sections,
                records=records,
            )
        )

    # 4. Proximity linking for titles
    # Find candidate title lines in the upper portion above the main grid
    all_lines = group_words_into_lines(content_words, max_x_gap=20.0, y_tolerance=4.0)
    candidate_titles = [
        l for l in all_lines
        if not any(delim in l["text"] for delim in [":", "lbs", "rpm", "hp"])
    ]

    return link_table_titles_by_proximity(zones, candidate_titles)


def perturb_wordboxes(
    words: list[WordBox],
    scale_x: float = 1.0,
    scale_y: float = 1.0,
    shift_x: float = 0.0,
    shift_y: float = 0.0,
) -> list[WordBox]:
    """Perturb a set of word boxes by scaling and shifting their coordinates.

    Used to verify that table segmentation and reading order algorithms are invariant
    to coordinate transformations.
    """
    return [
        WordBox(
            text=w.text,
            l=round(w.l * scale_x + shift_x, 3),
            r=round(w.r * scale_x + shift_x, 3),
            t=round(w.t * scale_y + shift_y, 3),
            b=round(w.b * scale_y + shift_y, 3),
            page=w.page,
            font_size=round(w.font_size * scale_y, 3),
            coord_origin=w.coord_origin,
        )
        for w in words
    ]


def format_table_as_markdown(zone: TableZone) -> str:
    """Format an extracted table zone into a clean markdown table."""
    lines: list[str] = [
        f"### {zone.title}",
        "",
        "| Section | Attribute | Value |",
        "| --- | --- | --- |",
    ]

    for rec in zone.records:
        clean_attr = re.sub(r"\|", "\\|", rec.attribute)
        clean_val = re.sub(r"\|", "\\|", rec.value)
        lines.append(f"| {rec.section} | {clean_attr} | {clean_val} |")

    return "\n".join(lines)

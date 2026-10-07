"""OCR Accuracy Evaluation Metrics (Addendum A2.2, Done Criteria).

Implements:
1. Levenshtein edit distance and Character Error Rate (CER) on body text lines.
2. Numeric token extraction and recall on dense specification pages (Page 11).
"""

from __future__ import annotations

import re


def levenshtein_distance(s1: str, s2: str) -> int:
    """Compute the Levenshtein edit distance between two strings."""
    if len(s1) < len(s2):
        return levenshtein_distance(s2, s1)
    if len(s2) == 0:
        return len(s1)

    previous_row = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row
    return previous_row[-1]


def clean_line_text(s: str) -> str:
    """Normalize whitespace and strip leading/trailing bullet artifacts for fair CER comparison."""
    # Remove leading bullets, dashes, asterisks
    s = re.sub(r"^[\s\u2022\u25cf\u2043\xb7\x95\-\*]+", "", s)
    s = re.sub(r"[\s\u2022\u25cf\u2043\xb7\x95\-\*]+$", "", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def compute_aligned_cer(gt_lines: list[str], ocr_lines: list[str]) -> tuple[float, int, int]:
    """Compute Character Error Rate (CER) on body text by best-match line alignment.

    Returns:
        (cer, total_edit_distance, total_ground_truth_characters)
    """
    clean_gt = [clean_line_text(l) for l in gt_lines if len(clean_line_text(l)) > 3]
    clean_ocr = [clean_line_text(l) for l in ocr_lines if len(clean_line_text(l)) > 3]

    if not clean_gt:
        return (0.0, 0, 0)

    total_gt_len = 0
    total_edits = 0

    for gt_l in clean_gt:
        best_dist = len(gt_l)
        gt_lower = gt_l.lower()
        for ocr_l in clean_ocr:
            dist = levenshtein_distance(gt_lower, ocr_l.lower())
            if dist < best_dist:
                best_dist = dist
                if best_dist == 0:
                    break
        total_gt_len += len(gt_l)
        total_edits += best_dist

    cer = total_edits / total_gt_len if total_gt_len > 0 else 0.0
    return (cer, total_edits, total_gt_len)


def extract_numeric_tokens(text: str) -> list[str]:
    """Extract all numeric tokens (integers and decimals) from text."""
    return re.findall(r"\b\d+(?:\.\d+)?\b", text)


def compute_numeric_token_recall(
    gt_text: str, ocr_text: str
) -> tuple[float, list[str], list[str]]:
    """Compute recall of numeric tokens from ground truth in OCR hypothesis.

    Returns:
        (recall, matched_tokens, missed_tokens)
    """
    gt_tokens = extract_numeric_tokens(gt_text)
    ocr_token_set = set(extract_numeric_tokens(ocr_text))

    if not gt_tokens:
        return (1.0, [], [])

    matched: list[str] = []
    missed: list[str] = []

    for tok in gt_tokens:
        if tok in ocr_token_set:
            matched.append(tok)
        else:
            missed.append(tok)

    recall = len(matched) / len(gt_tokens)
    return (recall, matched, missed)

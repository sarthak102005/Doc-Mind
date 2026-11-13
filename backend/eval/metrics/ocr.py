"""OCR Accuracy Evaluation Metrics (Addendum A2.2, Done Criteria).

Implements:
1. Levenshtein edit distance and Character Error Rate (CER) on text lines and full text.
2. Order-invariant token normalization (splitting numbers from units, hyphen ranges, thousands commas).
3. Multiset (Counter) matching for token Precision, Recall, and F1 to strictly handle duplicate tokens.
"""

from __future__ import annotations

import collections
import difflib
import re


def levenshtein_distance(s1: str, s2: str) -> int:
    """Compute the Levenshtein edit distance between two strings."""
    if s1 == s2:
        return 0
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
    s = re.sub(r"^[\s\u2022\u25cf\u2043\xb7\x95\-\*]+", "", s)
    s = re.sub(r"[\s\u2022\u25cf\u2043\xb7\x95\-\*]+$", "", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def compute_cer(gt: str, pred: str) -> float:
    """Compute standard Character Error Rate (CER) = Levenshtein distance / len(gt)."""
    if not gt:
        return 0.0 if not pred else 1.0
    dist = levenshtein_distance(gt, pred)
    return dist / len(gt)


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


BOILERPLATE_PATTERNS = [
    r"fc[- ]walk[- ]behind",
    r"www\.factorycat\.com",
    r"262[- ]681[- ]3583",
    r"rps corporation.*",
    r"\*images could include non-standard options.*",
    r"subject to change without notice.*",
]


def strip_boilerplate(text: str) -> str:
    """Remove standard multi-page repeated boilerplate lines."""
    lines = text.splitlines()
    kept = []
    for line in lines:
        l_low = line.strip().lower()
        if not l_low:
            continue
        is_bp = any(bool(re.search(pat, l_low)) for pat in BOILERPLATE_PATTERNS)
        if not is_bp:
            kept.append(line)
    return "\n".join(kept)


def normalize_tokens(text: str) -> list[str]:
    """Normalize text into canonical order-invariant tokens.

    Handles:
    - Normalising smart quotes: ’ and ‘ to '
    - Stripping thousands commas between digits: 1,200 -> 1200
    - Separating digits from adjacent units/letters: 441lbs -> 441 lbs, 24VDC -> 24 VDC
    - Splitting hyphenated ranges: 441-481 -> 441 - 481
    - Isolating quotes, asterisks, units
    - Lowercasing and trimming non-essential punctuation
    """
    # 0. Normalise unicode single and double quotes
    text = text.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    # 1. Strip thousands commas between digits: 1,200 -> 1200
    t = re.sub(r"(\d),(\d)", r"\1\2", text)
    # 2. Split digits from adjacent letters/units: 441lbs -> 441 lbs, 24VDC -> 24 VDC
    t = re.sub(r"(\d+)([a-zA-Z]+)", r"\1 \2", t)
    t = re.sub(r"([a-zA-Z]+)(\d+)", r"\1 \2", t)
    # 3. Split hyphenated ranges: 441-481 -> 441 - 481
    t = re.sub(r"(\d+)-(\d+)", r"\1 - \2", t)
    # 4. Separate quotes, asterisks, units
    t = re.sub(r"(\d+)([\"'\*\+])", r"\1 \2", t)
    t = re.sub(r"([\*]+)", r" \1 ", t)
    # 5. Lowercase and strip punctuation noise
    tokens = []
    for tok in t.split():
        clean = tok.strip(" ,;:()[]{}").lower()
        if clean:
            tokens.append(clean)
    return tokens


def compute_token_f1(
    gt_tokens: list[str], ocr_tokens: list[str]
) -> tuple[float, float, float]:
    """Compute order-invariant token precision, recall, and F1 using multiset (Counter) matching.

    Duplicate tokens are tracked strictly: if token X appears 3 times in GT
    and 1 time in OCR, matched = 1, giving Recall = 1/3.
    """
    if not gt_tokens and not ocr_tokens:
        return 1.0, 1.0, 1.0
    if not gt_tokens or not ocr_tokens:
        return 0.0, 0.0, 0.0

    gt_counts = collections.Counter(gt_tokens)
    ocr_counts = collections.Counter(ocr_tokens)

    # Intersection of multisets takes min(count_gt, count_ocr) for every token
    common = gt_counts & ocr_counts
    matched = sum(common.values())

    precision = matched / len(ocr_tokens)
    recall = matched / len(gt_tokens)
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0
    return precision, recall, f1


def extract_numeric_tokens(text: str) -> list[str]:
    """Extract all normalized numeric tokens from text."""
    tokens = normalize_tokens(text)
    return [tok for tok in tokens if re.search(r"\d", tok)]


def compute_numeric_token_recall(
    gt_text: str, ocr_text: str
) -> tuple[float, list[str], list[str]]:
    """Compute recall of numeric tokens using strict multiset Counter matching.

    Returns:
        (recall, matched_tokens, missed_tokens)
    """
    gt_tokens = extract_numeric_tokens(gt_text)
    ocr_tokens = extract_numeric_tokens(ocr_text)

    if not gt_tokens:
        return (1.0, [], [])

    gt_counts = collections.Counter(gt_tokens)
    ocr_counts = collections.Counter(ocr_tokens)

    common = gt_counts & ocr_counts
    matched_count = sum(common.values())

    # Build matched and missed token lists preserving counts
    matched: list[str] = []
    missed: list[str] = []

    remaining_ocr = collections.Counter(ocr_counts)
    for tok in gt_tokens:
        if remaining_ocr[tok] > 0:
            matched.append(tok)
            remaining_ocr[tok] -= 1
        else:
            missed.append(tok)

    recall = matched_count / len(gt_tokens)
    return (recall, matched, missed)

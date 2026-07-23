from __future__ import annotations

import csv
import math
import re
import sys
from collections import Counter
from functools import lru_cache
from heapq import nlargest
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[1]
GITBUGS_DIR = ROOT_DIR / "gitbugs"
TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_]+")
MAX_ROWS_PER_CSV = 800
MAX_DESCRIPTION_CHARS = 3000
csv.field_size_limit(min(sys.maxsize, 2_147_483_647))
STOP_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "but",
    "by",
    "for",
    "from",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "that",
    "the",
    "this",
    "to",
    "with",
}


def find_similar_bugs(query: str, limit: int = 3) -> list[dict[str, Any]]:
    """Return the most similar bugs from the local gitbugs CSV dataset."""
    query_vector = vectorize(query)
    if not query_vector:
        return []

    query_norm = vector_norm(query_vector)
    scored_matches: list[tuple[float, dict[str, Any]]] = []
    for bug in load_bug_records():
        similarity = cosine_similarity(query_vector, query_norm, bug["vector"], bug["norm"])
        if similarity > 0:
            scored_matches.append((similarity, bug))

    top_matches = nlargest(limit, scored_matches, key=lambda item: item[0])
    return [
        {
            "issue_id": bug["issue_id"],
            "summary": bug["summary"],
            "description": bug["description"],
            "severity": bug["severity"],
            "source": bug["source"],
            "similarity": round(score, 2),
        }
        for score, bug in top_matches
    ]


def build_bug_answer(text: str) -> dict[str, str]:
    """Create a short local advisor response from the submitted bug text."""
    lower_text = text.lower()
    error_line = extract_error_line(text)

    if "nonetype" in lower_text or "none" in lower_text:
        likely_cause = "A value is missing or None where the code expects a valid object or number."
        suggested_fix = "Validate inputs before using them, and skip or handle records with missing values."
    elif "nameerror" in lower_text or "not defined" in lower_text:
        likely_cause = "The code is using a variable, function, or import before it is defined."
        suggested_fix = "Check spelling, imports, and variable scope for the undefined name."
    elif "typeerror" in lower_text:
        likely_cause = "The code is applying an operation to an incompatible data type."
        suggested_fix = "Check the value types before the failing operation and convert or guard them."
    elif "indexerror" in lower_text:
        likely_cause = "The code is accessing a list or sequence position that does not exist."
        suggested_fix = "Check the sequence length before indexing."
    else:
        likely_cause = "The submitted bug needs review against similar historical reports."
        suggested_fix = "Compare the closest past bugs below and inspect the failing input path."

    return {
        "detected_error": error_line or "No explicit error line detected.",
        "likely_cause": likely_cause,
        "suggested_fix": suggested_fix,
    }


@lru_cache(maxsize=1)
def load_bug_records() -> tuple[dict[str, Any], ...]:
    records: list[dict[str, Any]] = []
    if not GITBUGS_DIR.exists():
        return tuple(records)

    for csv_path in sorted(GITBUGS_DIR.glob("*/*_bugs.csv")):
        source = csv_path.parent.name
        records.extend(load_bug_csv(csv_path, source))

    return tuple(records)


def load_bug_csv(csv_path: Path, source: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with csv_path.open("r", encoding="utf-8", errors="replace", newline="") as file:
        reader = csv.DictReader(file)
        for index, row in enumerate(reader):
            if index >= MAX_ROWS_PER_CSV:
                break
            summary = clean_text(row.get("Summary", ""))
            description = clean_text(row.get("Description", ""))[:MAX_DESCRIPTION_CHARS]
            searchable_text = f"{summary} {summary} {description}"
            vector = vectorize(searchable_text)
            if not vector:
                continue

            records.append(
                {
                    "issue_id": clean_text(row.get("Issue id", "")),
                    "summary": summary,
                    "description": description,
                    "severity": clean_text(
                        row.get("Priority") or row.get("Status") or row.get("Resolution") or "unknown"
                    ),
                    "source": source,
                    "vector": vector,
                    "norm": vector_norm(vector),
                }
            )
    return records


def vectorize(text: str) -> Counter[str]:
    tokens = [
        token.lower()
        for token in TOKEN_PATTERN.findall(text)
        if len(token) > 1 and token.lower() not in STOP_WORDS
    ]
    return Counter(tokens)


def vector_norm(vector: Counter[str]) -> float:
    return math.sqrt(sum(weight * weight for weight in vector.values()))


def cosine_similarity(
    left: Counter[str],
    left_norm: float,
    right: Counter[str],
    right_norm: float,
) -> float:
    if not left_norm or not right_norm:
        return 0.0

    if len(left) > len(right):
        left, right = right, left

    dot_product = sum(weight * right.get(token, 0) for token, weight in left.items())
    return dot_product / (left_norm * right_norm)


def extract_error_line(text: str) -> str:
    for line in text.splitlines():
        stripped = line.strip("# ").strip()
        if any(marker in stripped for marker in ["Error", "Exception", "Traceback", "TypeError", "NameError"]):
            return stripped
    return ""


def clean_text(value: Any) -> str:
    return str(value or "").strip()

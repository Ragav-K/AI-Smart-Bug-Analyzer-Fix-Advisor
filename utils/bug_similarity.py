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
            # Carried through so a historical fix -- in particular a confirmed
            # fix written back into the knowledge base -- can still ground a
            # recommendation when retrieval runs on the fallback path.
            "resolution": bug["resolution"],
            "root_cause": bug["root_cause"],
            "status": bug["status"],
            "labels": bug["labels"],
            "similarity": round(score, 2),
        }
        for score, bug in top_matches
    ]


@lru_cache(maxsize=1)
def load_bug_records() -> tuple[dict[str, Any], ...]:
    records: list[dict[str, Any]] = []
    if not GITBUGS_DIR.exists():
        return tuple(records)

    # Read every dataset file rather than one filename pattern. The full
    # per-project exports are too large to commit, so a fresh clone has only
    # gitbugs/samples/; both must resolve through the same loader.
    # The samples are a subset of the full exports, so both can be present on
    # a development machine. Key on project and issue id to avoid returning
    # the same historical defect twice.
    seen: set[tuple[str, str]] = set()
    for csv_path in sorted(GITBUGS_DIR.glob("*/*.csv")):
        source = project_name(csv_path)
        for record in load_bug_csv(csv_path, source):
            key = (source, record["issue_id"] or record["summary"])
            if key in seen:
                continue
            seen.add(key)
            records.append(record)

    return tuple(records)


def project_name(csv_path: Path) -> str:
    """Name the project by folder, or by filename inside the samples folder."""
    if csv_path.parent.name == "samples":
        return csv_path.stem.replace("_bugs_sample", "")
    return csv_path.parent.name


def has_searchable_columns(fieldnames: list[str] | None) -> bool:
    """Reject datasets that carry no retrievable text, such as the
    *-combined.csv duplicate-id files, which would otherwise be loaded as
    thousands of empty records."""
    columns = {str(name or "").strip().lower() for name in fieldnames or []}
    return bool(columns & {"summary", "description"})


def load_bug_csv(csv_path: Path, source: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with csv_path.open("r", encoding="utf-8", errors="replace", newline="") as file:
        reader = csv.DictReader(file)
        if not has_searchable_columns(reader.fieldnames):
            return records
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
                    "resolution": clean_text(row.get("Resolution", ""))[:MAX_DESCRIPTION_CHARS],
                    "root_cause": clean_text(row.get("Root cause", ""))[:MAX_DESCRIPTION_CHARS],
                    "status": clean_text(row.get("Status", "")),
                    "labels": clean_text(row.get("Component") or row.get("Labels") or ""),
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


def clean_text(value: Any) -> str:
    return str(value or "").strip()

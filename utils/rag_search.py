from __future__ import annotations

import json
import queue
import re
import threading
import zipfile
from collections import Counter
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st


ROOT_DIR = Path(__file__).resolve().parents[1]
GITBUGS_DIR = ROOT_DIR / "gitbugs"
VECTOR_DIR = ROOT_DIR / "data" / "chroma_gitbugs"
INDEX_READY_MARKER = VECTOR_DIR / ".index_ready"
COLLECTION_NAME = "historical_gitbugs"
MODEL_NAME = "all-MiniLM-L6-v2"
FALLBACK_MODEL_NAME = "Local token similarity"
SEARCH_TIMEOUT_SECONDS = 15.0
SUPPORTED_DATASETS = {".csv", ".json", ".jsonl", ".xlsx", ".xls"}
TEXT_FILE_TYPES = {".txt", ".log", ".java", ".py", ".js", ".ts", ".cpp", ".json", ".xml"}
MAX_FIELD_CHARS = 4000
BATCH_SIZE = 128

FIELD_ALIASES = {
    "bug_id": ["bug id", "bug_id", "issue id", "issue_id", "id", "key", "bugid"],
    "title": ["title", "summary", "bug title", "name"],
    "description": ["description", "desc", "details", "bug description"],
    "stack_trace": ["stack trace", "stack_trace", "trace", "traceback"],
    "error_log": ["error log", "error_log", "logs", "log", "error"],
    "resolution": ["resolution", "fix", "solution", "resolved"],
    "root_cause": ["root cause", "root_cause", "cause"],
    "priority": ["priority", "prio", "importance"],
    "status": ["status", "state", "bug status", "resolution status"],
    "labels": ["labels", "label", "tags", "components", "component", "keywords"],
    "project_name": ["project", "project name", "project_name", "repository", "repo", "product"],
}


@st.cache_resource(show_spinner=False)
def load_embedding_model() -> Any:
    """Load the cached sentence-transformer model once per Streamlit process."""
    from sentence_transformers import SentenceTransformer

    # Interactive bug submission must never wait on an unbounded model
    # download. If the model is not cached, search_similar_bugs falls back to
    # the bounded local matcher below.
    return SentenceTransformer(MODEL_NAME, local_files_only=True)


@st.cache_resource(show_spinner=False)
def get_chroma_collection() -> Any:
    """Create or load the persistent ChromaDB collection without indexing."""
    import chromadb

    VECTOR_DIR.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(VECTOR_DIR))
    return client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )


def get_vector_collection(build_if_missing: bool = True) -> Any:
    """Return the ChromaDB collection and optionally build it when empty."""
    collection = get_chroma_collection()
    if build_if_missing and (collection.count() == 0 or not is_vector_index_ready()):
        build_vector_database(collection)
    return collection


def build_vector_database(collection: Any) -> None:
    """Embed historical bugs and store them persistently in ChromaDB."""
    INDEX_READY_MARKER.unlink(missing_ok=True)
    records = load_historical_bugs()
    if not records:
        return

    model = load_embedding_model()
    for start in range(0, len(records), BATCH_SIZE):
        batch = records[start : start + BATCH_SIZE]
        documents = [record["search_text"] for record in batch]
        embeddings = model.encode(documents, normalize_embeddings=True).tolist()
        # Upsert allows an interrupted build to resume without duplicate-ID
        # failures on records that were already persisted.
        collection.upsert(
            ids=[record["id"] for record in batch],
            documents=documents,
            metadatas=[record["metadata"] for record in batch],
            embeddings=embeddings,
        )
    INDEX_READY_MARKER.write_text(str(collection.count()), encoding="utf-8")


def is_vector_index_ready() -> bool:
    """Return whether a full vector build completed successfully."""
    return INDEX_READY_MARKER.is_file()


def search_similar_bugs(
    query: str,
    limit: int = 5,
    timeout_seconds: float = SEARCH_TIMEOUT_SECONDS,
) -> list[dict[str, Any]]:
    """Search the ready vector index, with a bounded local fallback.

    Building the index is intentionally excluded from this interactive path:
    indexing the full GitBugs dataset can take several minutes.
    """
    cleaned_query = clean_text(query)
    if not cleaned_query:
        return []
    if not is_vector_index_ready():
        return _search_local_fallback(cleaned_query, limit)

    result_queue: queue.Queue[tuple[str, Any]] = queue.Queue(maxsize=1)

    def run_vector_search() -> None:
        try:
            result_queue.put(("ok", _search_vector_bugs(cleaned_query, limit)))
        except Exception as exc:
            result_queue.put(("error", exc))

    worker = threading.Thread(
        target=run_vector_search,
        name="historical-vector-search",
        daemon=True,
    )
    worker.start()

    try:
        status, payload = result_queue.get(timeout=max(0.001, timeout_seconds))
    except queue.Empty:
        return _search_local_fallback(cleaned_query, limit, timed_out=True)

    if status == "error":
        return _search_local_fallback(cleaned_query, limit)

    matches, indexed_count = payload
    if not indexed_count:
        return _search_local_fallback(cleaned_query, limit)
    return matches


def _search_vector_bugs(query: str, limit: int) -> tuple[list[dict[str, Any]], int]:
    """Query an existing ChromaDB index without building it."""
    collection = get_vector_collection(build_if_missing=False)
    indexed_count = collection.count()
    if indexed_count == 0:
        return [], 0

    model = load_embedding_model()
    query_embedding = model.encode([query], normalize_embeddings=True).tolist()[0]
    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=limit,
        include=["documents", "metadatas", "distances"],
    )

    matches: list[dict[str, Any]] = []
    metadatas = results.get("metadatas", [[]])[0]
    documents = results.get("documents", [[]])[0]
    distances = results.get("distances", [[]])[0]
    for metadata, document, distance in zip(metadatas, documents, distances):
        similarity = max(0.0, min(1.0, 1.0 - float(distance)))
        matches.append(
            {
                **metadata,
                "full_text": document,
                "similarity": similarity,
                "similarity_percentage": round(similarity * 100),
                "badge_label": match_badge(similarity),
                "badge_class": match_badge_class(similarity),
                "match_reasons": explain_match(query, document, metadata),
                "search_backend": MODEL_NAME,
                "historical_bugs_indexed": indexed_count,
            }
        )
    return matches, indexed_count


def _search_local_fallback(
    query: str,
    limit: int,
    timed_out: bool = False,
) -> list[dict[str, Any]]:
    """Normalize results from the bounded, dependency-free local matcher."""
    from utils.bug_similarity import find_similar_bugs

    matches: list[dict[str, Any]] = []
    for bug in find_similar_bugs(query, limit=limit):
        similarity = float(bug.get("similarity") or 0.0)
        title = str(bug.get("summary") or "Untitled historical bug")
        description = str(bug.get("description") or "")
        source = str(bug.get("source") or "")
        metadata = {"project_name": source}
        reasons = explain_match(query, f"{title}\n{description}", metadata)
        if timed_out:
            reasons.insert(0, "Semantic search timed out; local match used")
        matches.append(
            {
                "bug_id": bug.get("issue_id") or "Unknown Bug ID",
                "title": title,
                "description": description,
                "full_text": description,
                "project_name": source,
                "priority": bug.get("severity") or "",
                "source_file": f"gitbugs/{source}",
                "similarity": similarity,
                "similarity_percentage": round(similarity * 100),
                "badge_label": match_badge(similarity),
                "badge_class": match_badge_class(similarity),
                "match_reasons": reasons[:4],
                "search_backend": FALLBACK_MODEL_NAME,
                "historical_bugs_indexed": 0,
            }
        )
    return matches


def load_historical_bugs() -> list[dict[str, Any]]:
    """Load all supported GitBugs dataset files and normalize available fields."""
    if not GITBUGS_DIR.exists():
        return []

    records: list[dict[str, Any]] = []
    seen: set[str] = set()
    for path in sorted(GITBUGS_DIR.rglob("*")):
        if path.suffix.lower() not in SUPPORTED_DATASETS:
            continue
        for row_index, row in enumerate(read_dataset_rows(path)):
            normalized = normalize_bug_record(row, path, row_index)
            if not normalized:
                continue
            duplicate_key = "|".join(
                [
                    normalized["metadata"].get("project_name", ""),
                    normalized["metadata"].get("bug_id", ""),
                    normalized["metadata"].get("title", ""),
                ]
            )
            if duplicate_key in seen:
                continue
            seen.add(duplicate_key)
            records.append(normalized)
    return records


def read_dataset_rows(path: Path) -> list[dict[str, Any]]:
    """Read CSV, JSON, JSONL, or Excel datasets into row dictionaries."""
    try:
        suffix = path.suffix.lower()
        if suffix == ".csv":
            frame = pd.read_csv(path, dtype=str, encoding="utf-8", encoding_errors="replace")
        elif suffix == ".jsonl":
            frame = pd.read_json(path, lines=True, dtype=str)
        elif suffix == ".json":
            frame = pd.read_json(path, dtype=str)
        elif suffix in {".xlsx", ".xls"}:
            frame = pd.read_excel(path, dtype=str)
        else:
            return []
    except Exception:
        return []

    frame = frame.fillna("")
    return frame.to_dict(orient="records")


def normalize_bug_record(row: dict[str, Any], source_path: Path, row_index: int) -> dict[str, Any] | None:
    """Map inconsistent dataset columns into the fields the UI needs."""
    keyed_row = {normalize_key(key): value for key, value in row.items()}
    fields = {
        field_name: find_field(keyed_row, aliases)
        for field_name, aliases in FIELD_ALIASES.items()
    }
    if not fields["project_name"]:
        fields["project_name"] = source_path.parent.name

    content_parts = [
        fields["title"],
        fields["description"],
        fields["stack_trace"],
        fields["error_log"],
        fields["root_cause"],
        fields["resolution"],
        fields["labels"],
    ]
    if not any(clean_text(part) for part in content_parts):
        return None

    search_parts = [*content_parts, fields["project_name"]]
    search_text = clean_text("\n".join(part for part in search_parts if part))
    if not search_text:
        return None

    metadata = {
        key: truncate_metadata(clean_text(value))
        for key, value in fields.items()
        if clean_text(value)
    }
    metadata["source_file"] = str(source_path.relative_to(ROOT_DIR))
    if "bug_id" not in metadata:
        metadata["bug_id"] = f"{source_path.stem}-{row_index + 1}"

    return {
        "id": safe_record_id(source_path, row_index),
        "search_text": search_text,
        "metadata": metadata,
    }


def extract_uploaded_text(uploaded_file: Any) -> str:
    """Extract searchable text from supported uploaded files."""
    suffix = Path(uploaded_file.name).suffix.lower()
    try:
        uploaded_file.seek(0)
        if suffix in TEXT_FILE_TYPES:
            content = uploaded_file.read()
            return content.decode("utf-8", errors="replace")
        if suffix == ".pdf":
            from PyPDF2 import PdfReader

            reader = PdfReader(uploaded_file)
            return "\n".join(page.extract_text() or "" for page in reader.pages)
        if suffix == ".docx":
            from docx import Document

            document = Document(uploaded_file)
            return "\n".join(paragraph.text for paragraph in document.paragraphs)
        if suffix == ".zip":
            return extract_zip_text(uploaded_file)
        if suffix in {".png", ".jpg", ".jpeg"}:
            return f"Uploaded image: {uploaded_file.name}"
    except Exception:
        return ""
    finally:
        uploaded_file.seek(0)
    return ""


def extract_zip_text(uploaded_file: Any) -> str:
    parts: list[str] = []
    with zipfile.ZipFile(uploaded_file) as archive:
        for info in archive.infolist():
            suffix = Path(info.filename).suffix.lower()
            if suffix not in TEXT_FILE_TYPES or info.file_size > 1_000_000:
                continue
            with archive.open(info) as file:
                text = file.read().decode("utf-8", errors="replace")
            parts.append(f"--- {info.filename} ---\n{text}")
    return "\n\n".join(parts)


def find_field(row: dict[str, Any], aliases: list[str]) -> str:
    for alias in aliases:
        value = row.get(normalize_key(alias), "")
        if clean_text(value):
            return clean_text(value)
    return ""


def normalize_key(key: Any) -> str:
    return str(key or "").strip().lower().replace("_", " ")


def clean_text(value: Any) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value or "").strip()


def truncate_metadata(value: str) -> str:
    return value[:MAX_FIELD_CHARS]


def safe_record_id(path: Path, row_index: int) -> str:
    safe_path = "_".join(path.relative_to(ROOT_DIR).parts)
    return f"{safe_path}_{row_index + 1}".replace(" ", "_")


def match_badge(similarity: float) -> str:
    percentage = round(similarity * 100)
    return f"{percentage}% Match"


def match_badge_class(similarity: float) -> str:
    percentage = round(similarity * 100)
    if percentage >= 90:
        return "match-high"
    if percentage >= 75:
        return "match-medium"
    return "match-low"


STOP_WORDS = {
    "able", "about", "after", "again", "also", "and", "application", "are", "because",
    "before", "bug", "but", "can", "click", "does", "during", "error", "expected",
    "from", "has", "have", "into", "issue", "not", "result", "same", "should", "the",
    "then", "this", "that", "to", "user", "when", "with",
}


def explain_match(query: str, document: str, metadata: dict[str, Any]) -> list[str]:
    """Return short keyword-overlap reasons without using an LLM."""
    query_terms = important_terms(query)
    document_terms = {term for term, _ in important_terms(document)}
    overlaps = [term for term, _ in query_terms if term in document_terms]

    reasons: list[str] = []
    for term in overlaps[:4]:
        reasons.append(f"Similar {term.replace('_', ' ')}")

    for key, label in [("project_name", "Same project area"), ("labels", "Shared labels")]:
        value_terms = {term for term, _ in important_terms(str(metadata.get(key, "")))}
        shared = [term for term in overlaps if term in value_terms]
        if shared:
            reasons.append(f"{label}: {', '.join(shared[:2])}")

    if not reasons:
        reasons.append("Semantic similarity in title and description")
    return reasons[:4]


def important_terms(text: str) -> list[tuple[str, int]]:
    tokens = [
        token.lower()
        for token in re.findall(r"[A-Za-z][A-Za-z0-9_./-]{2,}", text or "")
        if token.lower() not in STOP_WORDS
    ]
    return Counter(tokens).most_common(24)

from __future__ import annotations

import json
import queue
import re
import threading
import zipfile
from collections import Counter
from pathlib import Path
from typing import Any

import streamlit as st

ROOT_DIR = Path(__file__).resolve().parents[1]
GITBUGS_DIR = ROOT_DIR / "gitbugs"
SAMPLES_DIR = GITBUGS_DIR / "samples"
LEARNED_DIR = GITBUGS_DIR / "learned"
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

# Upload extraction limits.
#
# Streamlit accepts an upload far larger than any stack trace worth analyzing,
# and every extracted character is carried through the whole pipeline: into the
# retrieval query, into the agents, and into the ``log_text`` field that
# ``save_report`` writes back to bug_reports.json. Without a ceiling a single
# large upload turns the saved report store into a file of the same size, and
# every later page load pays to re-read it. The parsers already work from the
# most recent 1,000,000 characters (utils.parser.MAX_LOG_CHARS), so extracting
# beyond this bound cannot improve an answer -- it only costs memory and disk.
MAX_EXTRACTED_CHARS = 2_000_000
TRUNCATION_NOTICE = "\n[Truncated: only the first {kept:,} characters of {name} were analyzed.]"

# Archive limits. A ZIP is a compressed container, so its size on disk says
# nothing about what it expands to: a 288 KB archive of repeated text expands
# to roughly 270 MB. Bounding the per-member size alone does not help when the
# archive holds hundreds of members, so the total and the member count are
# bounded too.
MAX_ZIP_MEMBER_BYTES = 1_000_000
MAX_ZIP_MEMBERS = 50
MAX_ZIP_TOTAL_BYTES = 10_000_000

# Issue trackers record a one-word workflow outcome in their "Resolution"
# column. It states that a defect was closed, not how it was repaired, so it
# must never reach the remediation agent as a recommended fix.
RESOLUTION_STATUS_VALUES = {
    "fixed", "done", "resolved", "complete", "completed", "duplicate",
    "invalid", "incomplete", "wontfix", "won't fix", "wont fix", "worksforme",
    "works for me", "cannot reproduce", "cannotreproduce", "not a bug",
    "no response", "inactive", "expired", "moved", "later", "remind",
    "implemented", "delivered", "auto closed", "unresolved", "none",
}
MIN_RESOLUTION_TEXT_WORDS = 4

FIELD_ALIASES = {
    "bug_id": ["bug id", "bug_id", "issue id", "issue_id", "id", "key", "bugid"],
    "title": ["title", "summary", "bug title", "name"],
    "description": ["description", "desc", "details", "bug description"],
    "stack_trace": ["stack trace", "stack_trace", "trace", "traceback"],
    "error_log": ["error log", "error_log", "logs", "log", "error"],
    # "resolved" is deliberately absent: in the GitBugs exports it is a
    # timestamp column, not a description of the corrective action.
    "resolution": ["resolution", "fix", "solution", "fix description", "resolution notes"],
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


def build_vector_database(collection: Any, include_full_datasets: bool = False) -> None:
    """Embed historical bugs and store them persistently in ChromaDB."""
    INDEX_READY_MARKER.unlink(missing_ok=True)
    records = load_historical_bugs(include_full_datasets)
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


_WARMUP_STARTED = threading.Event()


def warm_retrieval_backend() -> bool:
    """Load the embedding model and collection in the background, once.

    Loading the sentence-transformer costs roughly 25 seconds on a cold
    process, and opening the collection a further 2. A *warm* vector search
    then takes about 50 milliseconds. Left to load lazily, that entire cost
    lands on the first search -- which exceeds the search timeout, so the
    first submission of every session silently falls back to the lexical
    matcher despite a perfectly good index being present.

    Warming starts when the page is first rendered, while the user is still
    filling in the form, so the cost is paid against time they were spending
    anyway. Returns whether this call started the warm-up.
    """
    if not is_vector_index_ready() or _WARMUP_STARTED.is_set():
        return False
    _WARMUP_STARTED.set()

    def warm() -> None:
        try:
            load_embedding_model()
            get_vector_collection(build_if_missing=False)
        except Exception:
            # A failed warm-up is not an error: retrieval still works through
            # the fallback, and the next search retries the vector path.
            _WARMUP_STARTED.clear()

    threading.Thread(target=warm, name="retrieval-warmup", daemon=True).start()
    return True


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
        return _bounded_local_fallback(cleaned_query, limit, timeout_seconds)

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


def _bounded_local_fallback(
    query: str,
    limit: int,
    timeout_seconds: float,
) -> list[dict[str, Any]]:
    """Run disk-backed fallback retrieval within the same latency budget."""
    result_queue: queue.Queue[list[dict[str, Any]]] = queue.Queue(maxsize=1)

    def run_fallback() -> None:
        try:
            result_queue.put(_search_local_fallback(query, limit))
        except Exception:
            result_queue.put([])

    worker = threading.Thread(
        target=run_fallback,
        name="historical-local-search",
        daemon=True,
    )
    worker.start()
    try:
        return result_queue.get(timeout=max(0.001, timeout_seconds))
    except queue.Empty:
        return []


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
    # ChromaDB returns these three as parallel arrays for the same result set,
    # so strict=False states that they are equal by construction rather than
    # letting a future mismatch raise inside the search worker thread.
    for metadata, document, distance in zip(metadatas, documents, distances, strict=False):
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
        # Apply the same filter the indexed path applies, so a bare workflow
        # status such as "Fixed" never reaches remediation as a recommendation.
        resolution, resolution_status = split_resolution(str(bug.get("resolution") or ""))
        matches.append(
            {
                "bug_id": bug.get("issue_id") or "Unknown Bug ID",
                "title": title,
                "description": description,
                "full_text": description,
                "project_name": source,
                "resolution": resolution,
                "resolution_status": resolution_status,
                "root_cause": str(bug.get("root_cause") or ""),
                "status": str(bug.get("status") or ""),
                "labels": str(bug.get("labels") or ""),
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


def corpus_files(include_full_datasets: bool = False) -> list[Path]:
    """Return the dataset files that make up the knowledge base.

    By default this is the **committed corpus**: the curated per-project
    samples plus any fixes learned from confirmed resolutions. That is the
    3,600-record knowledge base the project documents and ships.

    The raw per-project exports are deliberately excluded unless asked for.
    They are gitignored but usually still present on a development machine,
    and they are enormous -- Mozilla Core alone is over 3 million rows, and
    the full set exceeds 5 million. Embedding that is an hours-to-days job
    producing tens of gigabytes, so silently including it turns
    ``build_index.py`` into a command that never appears to finish. The
    bounded lexical matcher already caps itself at 800 rows per file; this
    gives the semantic path an equivalent, explicit bound.
    """
    if not GITBUGS_DIR.exists():
        return []
    if include_full_datasets:
        candidates = sorted(GITBUGS_DIR.rglob("*"))
    else:
        candidates = sorted(
            path
            for directory in (SAMPLES_DIR, LEARNED_DIR)
            if directory.is_dir()
            for path in directory.rglob("*")
        )
    return [path for path in candidates if path.suffix.lower() in SUPPORTED_DATASETS]


def load_historical_bugs(include_full_datasets: bool = False) -> list[dict[str, Any]]:
    """Load supported GitBugs dataset files and normalize available fields."""
    records: list[dict[str, Any]] = []
    seen: set[str] = set()
    for path in corpus_files(include_full_datasets):
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
        # Pandas takes several seconds to import on some Windows systems. Keep
        # it off the web application's startup path and load it only when a
        # dataset is actually read for indexing.
        import pandas as pd

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
        fields["project_name"] = dataset_project_name(source_path)
    fields["resolution"], fields["resolution_status"] = split_resolution(fields["resolution"])

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
        "id": safe_record_id(source_path, row_index, row),
        "search_text": search_text,
        "metadata": metadata,
    }


def extract_uploaded_text(uploaded_file: Any) -> str:
    """Extract searchable text from supported uploaded files.

    The result is always bounded by ``MAX_EXTRACTED_CHARS``. An oversized file
    is analyzed from its leading section and the caller is told so in the text
    itself, which keeps the truncation visible to the reviewer instead of
    silently dropping evidence.
    """
    suffix = Path(uploaded_file.name).suffix.lower()
    try:
        uploaded_file.seek(0)
        if suffix == ".json":
            text = flatten_json_text(uploaded_file.read().decode("utf-8", errors="replace"))
        elif suffix in TEXT_FILE_TYPES:
            text = uploaded_file.read().decode("utf-8", errors="replace")
        elif suffix == ".pdf":
            reader = _pdf_reader()(uploaded_file)
            text = _join_bounded(page.extract_text() or "" for page in reader.pages)
        elif suffix == ".docx":
            from docx import Document

            document = Document(uploaded_file)
            text = _join_bounded(paragraph.text for paragraph in document.paragraphs)
        elif suffix == ".zip":
            text = extract_zip_text(uploaded_file)
        elif suffix in {".png", ".jpg", ".jpeg"}:
            text = f"Uploaded image: {uploaded_file.name}"
        else:
            text = ""
    except Exception:
        return ""
    finally:
        uploaded_file.seek(0)
    return _bound_extracted_text(text, uploaded_file.name)


def _pdf_reader() -> Any:
    """Return a PDF reader class, preferring the maintained ``pypdf``.

    ``PyPDF2`` is end-of-life and emits a DeprecationWarning on import. ``pypdf``
    is its renamed continuation and exposes the same ``PdfReader`` interface, so
    the call site is unchanged. The fallback stays so an environment that has
    only the older package installed keeps working rather than losing PDF
    support entirely.
    """
    try:
        from pypdf import PdfReader
    except ImportError:  # pragma: no cover - legacy environments only
        from PyPDF2 import PdfReader
    return PdfReader


def _join_bounded(parts: Any) -> str:
    """Join page or paragraph text, stopping once the extraction bound is hit.

    A 5,000-page PDF should not be fully decoded only to have the tail thrown
    away, so the generator is abandoned as soon as enough text is collected.
    """
    collected: list[str] = []
    total = 0
    for part in parts:
        collected.append(part)
        total += len(part) + 1
        if total > MAX_EXTRACTED_CHARS:
            break
    return "\n".join(collected)


def _bound_extracted_text(text: str, name: str) -> str:
    """Cap extracted text and state the truncation in the returned text."""
    if len(text) <= MAX_EXTRACTED_CHARS:
        return text
    kept = text[:MAX_EXTRACTED_CHARS]
    return kept + TRUNCATION_NOTICE.format(kept=MAX_EXTRACTED_CHARS, name=name)


def flatten_json_text(raw: str) -> str:
    """Render an uploaded JSON log as plain text.

    A stack trace stored in a JSON string carries escaped newlines, so the
    line-anchored trace parsers cannot see a single frame in the raw file.
    Decoding the structure restores real line breaks and lets an uploaded
    JSON log be analyzed as well as a plain .log file.
    """
    try:
        document = json.loads(raw)
    except (ValueError, TypeError):
        return raw

    lines: list[str] = []

    def walk(node: Any, label: str = "") -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                walk(value, str(key))
        elif isinstance(node, list):
            for item in node:
                walk(item, label)
        else:
            text = str(node if node is not None else "").strip()
            if not text:
                return
            # Multi-line values (stack traces) are emitted on their own lines
            # so the parsers see them exactly as they appear in a raw log.
            lines.append(text if "\n" in text else (f"{label}: {text}" if label else text))

    walk(document)
    return "\n".join(lines)


def extract_zip_text(uploaded_file: Any) -> str:
    """Extract text members from an archive under strict expansion limits.

    Three independent bounds are applied -- per member, on the member count,
    and on the running total -- because a decompression bomb defeats any one of
    them alone. ``info.file_size`` is the header's declared size, so the read
    itself is also capped rather than trusted.
    """
    parts: list[str] = []
    total = 0
    read_members = 0
    truncated = False
    with zipfile.ZipFile(uploaded_file) as archive:
        for info in archive.infolist():
            if read_members >= MAX_ZIP_MEMBERS or total >= MAX_ZIP_TOTAL_BYTES:
                truncated = True
                break
            suffix = Path(info.filename).suffix.lower()
            if info.is_dir() or suffix not in TEXT_FILE_TYPES:
                continue
            if info.file_size > MAX_ZIP_MEMBER_BYTES:
                truncated = True
                continue
            remaining = MAX_ZIP_TOTAL_BYTES - total
            with archive.open(info) as file:
                raw = file.read(min(MAX_ZIP_MEMBER_BYTES, remaining) + 1)
            if len(raw) > remaining:
                raw = raw[:remaining]
                truncated = True
            total += len(raw)
            read_members += 1
            # The member name is data from an untrusted archive and is only
            # ever shown as a label, never used to open a path, so a traversal
            # entry such as "../../evil.log" cannot escape anywhere. It is
            # displayed as-is so the reviewer sees what the archive claimed.
            parts.append(f"--- {info.filename} ---\n{raw.decode('utf-8', errors='replace')}")
    if truncated:
        parts.append(
            f"[Truncated: archive exceeded the {MAX_ZIP_MEMBERS}-file / "
            f"{MAX_ZIP_TOTAL_BYTES // 1_000_000} MB extraction limit.]"
        )
    return "\n\n".join(parts)


def split_resolution(value: str) -> tuple[str, str]:
    """Separate a descriptive fix from a bare workflow outcome.

    Returns (resolution_text, resolution_status). Only genuinely descriptive
    text is kept as a resolution, so remediation can never present the word
    "Fixed" as an evidence-backed recommendation.
    """
    cleaned = clean_text(value)
    if not cleaned:
        return "", ""
    if cleaned.strip().lower() in RESOLUTION_STATUS_VALUES:
        return "", cleaned
    if len(cleaned.split()) < MIN_RESOLUTION_TEXT_WORDS:
        return "", cleaned
    return cleaned, ""


def dataset_project_name(source_path: Path) -> str:
    """Name the project by folder, or by filename inside the samples folder."""
    if source_path.parent.name == "samples":
        return source_path.stem.replace("_bugs_sample", "")
    return source_path.parent.name


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


def learned_record_id(submission_id: str) -> str:
    """The canonical index ID for a fix learned from a confirmed resolution."""
    return f"learned_{submission_id}"


def safe_record_id(path: Path, row_index: int, row: dict[str, Any] | None = None) -> str:
    """Return a stable index ID for one dataset row.

    Rows in the learned corpus are keyed by their source submission rather
    than by file position, so the two paths that can index a confirmed fix --
    the incremental write in ``utils.knowledge_base`` and a full corpus
    rebuild -- produce the *same* ID and therefore upsert the same record.

    Keying the learned corpus by row position instead would make a rebuild
    insert a second copy of every confirmed fix under a different ID: the same
    fix would then be retrieved twice as two separate duplicates, and removing
    it would only ever delete one of them.
    """
    if row is not None and _is_learned_corpus(path):
        submission_id = clean_text(row.get("Source submission"))
        if submission_id:
            return learned_record_id(submission_id)
    safe_path = "_".join(path.relative_to(ROOT_DIR).parts)
    return f"{safe_path}_{row_index + 1}".replace(" ", "_")


def _is_learned_corpus(path: Path) -> bool:
    return LEARNED_DIR in path.parents


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

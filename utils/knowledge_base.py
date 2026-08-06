"""Knowledge base growth: feed confirmed fixes back into retrieval.

A resolved submission whose fix has been confirmed by a human is the highest
quality record this system can hold -- unlike a public issue-tracker export, it
carries a real description of the corrective action. Writing it back means the
next similar failure is answered from a proven fix instead of a diagnostic
inference.

The learned corpus is stored as a CSV under ``gitbugs/learned/`` on purpose.
Both retrieval backends already discover dataset files there:

- the semantic path indexes it through ``utils.rag_search.load_historical_bugs``
- the bounded fallback reads it through ``utils.bug_similarity.load_bug_records``

so one write makes the fix retrievable on either path, and a full index rebuild
picks it up with no special-casing.
"""

from __future__ import annotations

import csv
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from utils.logging_config import get_agent_logger

LOGGER = get_agent_logger(__name__)

ROOT_DIR = Path(__file__).resolve().parents[1]
LEARNED_DIR = ROOT_DIR / "gitbugs" / "learned"
LEARNED_CSV = LEARNED_DIR / "learned_bugs.csv"

# Column names match the aliases both loaders already understand, so no
# dataset-specific mapping code is needed anywhere else.
FIELDNAMES = [
    "Issue id",
    "Summary",
    "Description",
    "Root cause",
    "Resolution",
    "Priority",
    "Status",
    "Component",
    "Confirmed by",
    "Confirmed at",
    "Source submission",
]

# A confirmed fix must describe the corrective action. Anything shorter is a
# workflow status ("fixed", "done"), which utils.rag_search.split_resolution
# would strip out at index time anyway -- rejecting it here gives the user an
# immediate, understandable error instead of a silently useless record.
MIN_FIX_WORDS = 4


class ConfirmedFixError(ValueError):
    """Raised when a submission cannot be promoted into the knowledge base."""


def learned_entries() -> list[dict[str, str]]:
    """Return every confirmed fix currently in the learned corpus."""
    if not LEARNED_CSV.is_file():
        return []
    try:
        with LEARNED_CSV.open("r", encoding="utf-8", newline="") as file:
            return [dict(row) for row in csv.DictReader(file)]
    except OSError:
        LOGGER.exception("Learned knowledge base could not be read")
        return []


def learned_entry_count() -> int:
    """Return how many confirmed fixes have been learned."""
    return len(learned_entries())


def is_learned(submission_id: str) -> bool:
    """Return whether this submission was already promoted."""
    return any(
        str(entry.get("Source submission") or "") == str(submission_id)
        for entry in learned_entries()
    )


def build_learned_record(
    report: dict[str, Any],
    confirmed_fix: str,
    confirmed_by: str = "",
    root_cause: str = "",
) -> dict[str, str]:
    """Assemble a knowledge base row from a submission and its confirmed fix."""
    fix = " ".join(str(confirmed_fix or "").split())
    if len(fix.split()) < MIN_FIX_WORDS:
        raise ConfirmedFixError(
            "Describe the corrective action in at least "
            f"{MIN_FIX_WORDS} words. A status such as 'Fixed' is not a resolution."
        )

    submission_id = str(report.get("submission_id") or "").strip()
    if not submission_id:
        raise ConfirmedFixError("The submission has no identifier and cannot be promoted.")

    analysis = report.get("analysis") or {}
    triage = analysis.get("triage") or {}
    log_analysis = analysis.get("log_analysis") or {}
    agent_root_cause = (analysis.get("root_cause") or {}).get("root_cause") or ""

    summary = " ".join(str(report.get("bug_title") or "").split())
    if not summary:
        exception = log_analysis.get("root_exception") or log_analysis.get("exception_type")
        failure_point = log_analysis.get("failure_point") or ""
        summary = " ".join(
            part
            for part in [
                str(exception or "Reported defect"),
                f"at {failure_point}" if failure_point else "",
            ]
            if part
        )

    description_parts = [
        str(report.get("bug_description") or "").strip(),
        str(report.get("steps_to_reproduce") or "").strip(),
        str(report.get("actual_result") or "").strip(),
        str(log_analysis.get("failure_point") or "").strip(),
        str(report.get("log_text") or "").strip(),
    ]
    description = "\n".join(part for part in description_parts if part)[:4000]

    return {
        "Issue id": f"KB-{submission_id}",
        "Summary": summary or f"Confirmed fix for {submission_id}",
        "Description": description or summary,
        "Root cause": " ".join(str(root_cause or agent_root_cause or "").split())[:2000],
        "Resolution": fix[:4000],
        "Priority": str(triage.get("priority") or ""),
        "Status": "Resolved",
        "Component": str(triage.get("component") or ""),
        "Confirmed by": " ".join(str(confirmed_by or "Unattributed").split()),
        "Confirmed at": datetime.now(UTC).isoformat(timespec="seconds"),
        "Source submission": submission_id,
    }


def record_confirmed_fix(
    report: dict[str, Any],
    confirmed_fix: str,
    confirmed_by: str = "",
    root_cause: str = "",
) -> dict[str, Any]:
    """Add a confirmed fix to the knowledge base and make it retrievable now.

    Re-confirming a submission replaces its existing row rather than appending
    a second one, so a corrected fix description supersedes the earlier text
    instead of competing with it during retrieval.
    """
    record = build_learned_record(report, confirmed_fix, confirmed_by, root_cause)
    existing = learned_entries()
    entries = [
        entry
        for entry in existing
        if str(entry.get("Source submission") or "") != record["Source submission"]
    ]
    replaced = len(entries) != len(existing)
    entries.append(record)
    _write_entries(entries)
    _invalidate_retrieval_caches()
    indexed = _index_learned_record(record)

    LOGGER.info(
        "Confirmed fix added to the knowledge base",
        extra={
            "submission_id": record["Source submission"],
            "indexed": indexed,
            "entries": len(entries),
        },
    )
    return {
        "record": record,
        "entries": len(entries),
        "replaced_previous": replaced,
        "indexed_immediately": indexed,
    }


def remove_confirmed_fix(submission_id: str) -> dict[str, Any]:
    """Remove a confirmed fix from the CSV *and* from the vector index.

    Deleting only the CSV row leaves the embedding behind, so the fix keeps
    being retrieved semantically long after it was supposedly withdrawn --
    which silently invalidates any later before/after comparison. Removal has
    to be symmetric with ``record_confirmed_fix`` to mean anything.
    """
    submission_id = str(submission_id)
    existing = learned_entries()
    remaining = [
        entry
        for entry in existing
        if str(entry.get("Source submission") or "") != submission_id
    ]
    removed = len(existing) - len(remaining)

    if remaining:
        _write_entries(remaining)
    else:
        LEARNED_CSV.unlink(missing_ok=True)
    _invalidate_retrieval_caches()
    unindexed = _unindex_learned_record(submission_id)

    LOGGER.info(
        "Confirmed fix removed from the knowledge base",
        extra={"submission_id": submission_id, "unindexed": unindexed, "entries": len(remaining)},
    )
    return {"removed": removed, "entries": len(remaining), "unindexed": unindexed}


def _unindex_learned_record(submission_id: str) -> bool:
    """Delete one learned fix's embedding from the vector index."""
    try:
        from utils.rag_search import (
            get_vector_collection,
            is_vector_index_ready,
            learned_record_id,
        )

        if not is_vector_index_ready():
            return False
        get_vector_collection(build_if_missing=False).delete(
            ids=[learned_record_id(submission_id)]
        )
        return True
    except Exception:
        LOGGER.exception("Confirmed fix could not be removed from the vector index")
        return False


def _write_entries(entries: list[dict[str, str]]) -> None:
    """Rewrite the learned corpus atomically enough for a single-user app."""
    LEARNED_CSV.parent.mkdir(parents=True, exist_ok=True)
    temporary = LEARNED_CSV.with_suffix(".csv.tmp")
    with temporary.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDNAMES, extrasaction="ignore")
        writer.writeheader()
        for entry in entries:
            writer.writerow({name: entry.get(name, "") for name in FIELDNAMES})
    temporary.replace(LEARNED_CSV)


def _invalidate_retrieval_caches() -> None:
    """Rebuild the cached fallback corpus so the new fix is searchable at once.

    The cache is rebuilt here rather than left cold on purpose. Interactive
    retrieval runs under a short timeout, and reloading the whole corpus from
    disk can exceed it -- which would make the very next search silently return
    nothing, exactly when the reviewer expects to see their confirmed fix. The
    reload is paid here, where the user has just asked for work to happen.
    """
    try:
        from utils.bug_similarity import load_bug_records

        load_bug_records.cache_clear()
        load_bug_records()
    except Exception:
        LOGGER.exception("Fallback retrieval cache could not be rebuilt")


def _index_learned_record(record: dict[str, str]) -> bool:
    """Embed one confirmed fix into the existing vector index.

    Returns False when the semantic index has not been built. That is not an
    error: the fix is already in the CSV, so it is retrievable through the
    fallback matcher immediately and through the vector index after the next
    ``python scripts/build_index.py`` run.
    """
    try:
        from utils.rag_search import (
            clean_text,
            get_vector_collection,
            is_vector_index_ready,
            learned_record_id,
            load_embedding_model,
            split_resolution,
        )

        if not is_vector_index_ready():
            return False

        resolution, _status = split_resolution(record["Resolution"])
        search_parts = [
            record["Summary"],
            record["Description"],
            record["Root cause"],
            resolution,
            record["Component"],
            "learned",
        ]
        search_text = clean_text("\n".join(part for part in search_parts if part))
        if not search_text:
            return False

        metadata = {
            "bug_id": record["Issue id"],
            "title": record["Summary"],
            "description": record["Description"],
            "resolution": resolution,
            "root_cause": record["Root cause"],
            "priority": record["Priority"],
            "status": record["Status"],
            "labels": record["Component"],
            "project_name": "learned",
            "source_file": str(LEARNED_CSV.relative_to(ROOT_DIR)),
        }
        metadata = {key: value for key, value in metadata.items() if value}

        model = load_embedding_model()
        embedding = model.encode([search_text], normalize_embeddings=True).tolist()
        get_vector_collection(build_if_missing=False).upsert(
            ids=[learned_record_id(record["Source submission"])],
            documents=[search_text],
            metadatas=[metadata],
            embeddings=embedding,
        )
        return True
    except Exception:
        # The durable CSV write already succeeded; a failed embedding must not
        # lose the confirmed fix, it only delays semantic retrieval of it.
        LOGGER.exception("Confirmed fix could not be added to the vector index")
        return False

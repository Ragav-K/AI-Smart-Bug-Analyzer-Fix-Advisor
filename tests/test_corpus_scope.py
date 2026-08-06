"""Scope of the indexed corpus, and retrieval warm-up.

Both behaviours here exist because of the same measured problem: the semantic
index was never usable in practice. Indexing pulled in the raw per-project
exports (over 5 million rows), so a build never appeared to finish; and once
built, the 25-second cold model load exceeded the search timeout, so the first
search of every session fell back to the lexical matcher anyway.
"""

from __future__ import annotations

import utils.rag_search as rag


def test_default_corpus_is_the_committed_sample_set():
    """Only gitbugs/samples/ and gitbugs/learned/ are indexed by default."""
    files = rag.corpus_files()

    assert files, "the committed sample corpus should always be present"
    for path in files:
        assert path.parent.name in {"samples", "learned"}, path


def test_default_corpus_excludes_the_raw_project_exports():
    """The multi-million-row per-project exports are never pulled in implicitly.

    Those live directly under a project folder (``gitbugs/firefox/``), unlike
    the curated samples and the learned corpus. ``learned_bugs.csv`` is
    deliberately included -- it is confirmed fixes, and it is small.
    """
    default = rag.corpus_files()

    assert not any("combined" in path.name.lower() for path in default)
    for path in default:
        assert path.parent.name != path.parent.parent.name, path
        assert not (path.parent.name not in {"samples", "learned"}), path


def test_full_scope_includes_more_than_the_default():
    """--full is a real escape hatch, not a no-op."""
    default = rag.corpus_files()
    full = rag.corpus_files(include_full_datasets=True)

    assert len(full) >= len(default)
    assert {path.name for path in default}.issubset({path.name for path in full})


def test_default_corpus_stays_within_a_buildable_size():
    """A default build must be minutes, not hours.

    The committed corpus is 3,600 defects plus any learned fixes. This guards
    the property that matters -- that `python scripts/build_index.py` finishes
    -- rather than pinning an exact count that grows with confirmed fixes.
    """
    records = rag.load_historical_bugs()

    assert 3_000 <= len(records) <= 20_000, (
        f"default corpus is {len(records)} records; a build this size would not "
        "complete in a reasonable time"
    )


def test_warmup_is_skipped_when_no_index_exists(monkeypatch):
    """With no index there is nothing to warm, so no thread is spawned."""
    monkeypatch.setattr(rag, "is_vector_index_ready", lambda: False)
    monkeypatch.setattr(rag, "_WARMUP_STARTED", rag.threading.Event())

    assert rag.warm_retrieval_backend() is False


def test_warmup_runs_once_per_process(monkeypatch):
    """Streamlit reruns the script constantly; the model must load only once."""
    calls: list[str] = []
    monkeypatch.setattr(rag, "is_vector_index_ready", lambda: True)
    monkeypatch.setattr(rag, "_WARMUP_STARTED", rag.threading.Event())
    monkeypatch.setattr(rag, "load_embedding_model", lambda: calls.append("model"))
    monkeypatch.setattr(rag, "get_vector_collection", lambda build_if_missing=True: calls.append("collection"))

    assert rag.warm_retrieval_backend() is True
    assert rag.warm_retrieval_backend() is False
    assert rag.warm_retrieval_backend() is False


def test_failed_warmup_allows_a_later_retry(monkeypatch):
    """A warm-up failure must not permanently disable the vector path."""
    def explode() -> None:
        raise RuntimeError("model unavailable")

    monkeypatch.setattr(rag, "is_vector_index_ready", lambda: True)
    monkeypatch.setattr(rag, "_WARMUP_STARTED", rag.threading.Event())
    monkeypatch.setattr(rag, "load_embedding_model", explode)

    assert rag.warm_retrieval_backend() is True
    for _ in range(200):
        if not rag._WARMUP_STARTED.is_set():
            break
        rag.time.sleep(0.01) if hasattr(rag, "time") else None
    # The flag is cleared by the worker so a later render can try again.
    assert rag._WARMUP_STARTED.is_set() is False

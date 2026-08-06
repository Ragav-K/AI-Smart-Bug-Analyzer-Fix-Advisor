"""A confirmed fix must have one identity, whichever path indexed it.

A learned fix can reach the vector index two ways: the incremental write in
``utils.knowledge_base`` when a reviewer confirms it, and a full corpus rebuild
that reads ``gitbugs/learned/``. When those produced different IDs, a rebuild
inserted a second copy of every confirmed fix -- so the same fix was retrieved
as two separate duplicates, and removing it deleted only one of them.
"""

from __future__ import annotations

from pathlib import Path

import utils.rag_search as rag

LEARNED_CSV = rag.LEARNED_DIR / "learned_bugs.csv"


def test_learned_rows_are_keyed_by_source_submission():
    row = {"Issue id": "KB-DEMO-001", "Source submission": "DEMO-001", "Summary": "Login crash"}

    record_id = rag.safe_record_id(LEARNED_CSV, 0, row)

    assert record_id == rag.learned_record_id("DEMO-001") == "learned_DEMO-001"


def test_learned_row_id_ignores_position_in_the_file():
    """The same fix keeps its identity when other rows are added or removed."""
    row = {"Source submission": "DEMO-001"}

    assert rag.safe_record_id(LEARNED_CSV, 0, row) == rag.safe_record_id(LEARNED_CSV, 47, row)


def test_rebuild_and_incremental_write_agree_on_the_id():
    """This equality is what makes a rebuild upsert rather than duplicate."""
    submission_id = "BUG-20260806-001"
    row = {"Source submission": submission_id}

    from_rebuild = rag.safe_record_id(LEARNED_CSV, 3, row)
    from_incremental = rag.learned_record_id(submission_id)

    assert from_rebuild == from_incremental


def test_ordinary_corpus_rows_still_use_path_and_position():
    """Only the learned corpus is special-cased."""
    sample = rag.SAMPLES_DIR / "hadoop_bugs_sample.csv"
    row = {"Issue id": "HADOOP-1", "Source submission": "ignored-here"}

    record_id = rag.safe_record_id(sample, 0, row)

    assert record_id.endswith("_1")
    assert not record_id.startswith("learned_")


def test_learned_row_without_a_source_submission_falls_back_to_position():
    """A malformed row must still get a usable, unique ID rather than collide."""
    record_id = rag.safe_record_id(LEARNED_CSV, 2, {"Summary": "no source column"})

    assert record_id.endswith("_3")
    assert not record_id.startswith("learned_")


def test_row_is_optional_for_backwards_compatibility():
    assert rag.safe_record_id(LEARNED_CSV, 0) == rag.safe_record_id(LEARNED_CSV, 0, None)


def test_learned_corpus_is_detected_by_location_not_filename():
    assert rag._is_learned_corpus(rag.LEARNED_DIR / "anything.csv") is True
    assert rag._is_learned_corpus(rag.SAMPLES_DIR / "learned_bugs.csv") is False
    assert rag._is_learned_corpus(Path("gitbugs/firefox/Firefox_bugs.csv")) is False

"""Knowledge base growth: confirmed fixes become retrievable evidence."""

import csv

import pytest

from utils import knowledge_base

REPORT = {
    "submission_id": "BUG-20260805-001",
    "bug_title": "Login crashes for every user",
    "bug_description": "Production login returns a 500 for all users.",
    "steps_to_reproduce": "1. Open login\n2. Submit valid credentials",
    "actual_result": "NullPointerException is raised.",
    "log_text": "java.lang.NullPointerException: user is null",
    "analysis": {
        "triage": {"severity": "Critical", "priority": "P0", "component": "Authentication"},
        "log_analysis": {
            "root_exception": "IllegalStateException",
            "failure_point": "validate in LoginService.java",
        },
        "root_cause": {"root_cause": "Session store returned no user for a valid token."},
    },
}

FIX = "Guard the session lookup in LoginService.validate and return a 401 when no user is found."


@pytest.fixture(autouse=True)
def isolated_corpus(tmp_path, monkeypatch):
    """Redirect the learned corpus so tests never touch the real dataset."""
    monkeypatch.setattr(knowledge_base, "LEARNED_CSV", tmp_path / "learned" / "learned_bugs.csv")
    # The semantic index is not built in a test environment; assert the
    # documented CSV-only behaviour rather than reaching for ChromaDB.
    monkeypatch.setattr(knowledge_base, "_index_learned_record", lambda record: False)
    return tmp_path


def test_empty_knowledge_base_reports_no_entries():
    assert knowledge_base.learned_entries() == []
    assert knowledge_base.learned_entry_count() == 0
    assert knowledge_base.is_learned("BUG-20260805-001") is False


def test_confirmed_fix_is_written_with_the_expected_columns():
    outcome = knowledge_base.record_confirmed_fix(REPORT, FIX, confirmed_by="QA Lead")
    assert outcome["entries"] == 1
    assert outcome["replaced_previous"] is False
    assert outcome["indexed_immediately"] is False

    with knowledge_base.LEARNED_CSV.open(encoding="utf-8", newline="") as file:
        rows = list(csv.DictReader(file))
    assert len(rows) == 1
    row = rows[0]
    assert row["Issue id"] == "KB-BUG-20260805-001"
    assert row["Summary"] == "Login crashes for every user"
    assert row["Resolution"] == FIX
    assert row["Root cause"] == "Session store returned no user for a valid token."
    assert row["Component"] == "Authentication"
    assert row["Priority"] == "P0"
    assert row["Status"] == "Resolved"
    assert row["Confirmed by"] == "QA Lead"
    assert row["Source submission"] == "BUG-20260805-001"


def test_learned_entry_is_discoverable_after_writing():
    knowledge_base.record_confirmed_fix(REPORT, FIX)
    assert knowledge_base.learned_entry_count() == 1
    assert knowledge_base.is_learned("BUG-20260805-001") is True


def test_reconfirming_replaces_the_previous_fix_instead_of_duplicating_it():
    knowledge_base.record_confirmed_fix(REPORT, FIX)
    outcome = knowledge_base.record_confirmed_fix(
        REPORT, "Validate the session token at the controller boundary before use."
    )
    assert outcome["replaced_previous"] is True
    assert outcome["entries"] == 1
    entries = knowledge_base.learned_entries()
    assert entries[0]["Resolution"].startswith("Validate the session token")


def test_two_submissions_accumulate_as_separate_entries():
    knowledge_base.record_confirmed_fix(REPORT, FIX)
    knowledge_base.record_confirmed_fix(
        {**REPORT, "submission_id": "BUG-20260805-002"},
        "Return a typed authentication error when the session store yields nothing.",
    )
    assert knowledge_base.learned_entry_count() == 2


@pytest.mark.parametrize("value", ["", "   ", "Fixed", "done", "wontfix"])
def test_a_workflow_status_is_rejected_as_a_resolution(value):
    with pytest.raises(knowledge_base.ConfirmedFixError):
        knowledge_base.record_confirmed_fix(REPORT, value)
    assert knowledge_base.learned_entry_count() == 0


def test_a_submission_without_an_identifier_is_rejected():
    with pytest.raises(knowledge_base.ConfirmedFixError):
        knowledge_base.record_confirmed_fix({"bug_title": "No id"}, FIX)


def test_a_report_without_a_title_is_summarized_from_its_diagnostics():
    record = knowledge_base.build_learned_record(
        {**REPORT, "bug_title": ""}, FIX
    )
    assert "IllegalStateException" in record["Summary"]
    assert "validate in LoginService.java" in record["Summary"]


def test_the_learned_corpus_is_readable_by_the_fallback_retriever(tmp_path, monkeypatch):
    """The written CSV must satisfy the loader that powers fallback search."""
    from utils import bug_similarity

    knowledge_base.record_confirmed_fix(REPORT, FIX)
    monkeypatch.setattr(bug_similarity, "GITBUGS_DIR", knowledge_base.LEARNED_CSV.parents[1])
    bug_similarity.load_bug_records.cache_clear()
    try:
        matches = bug_similarity.find_similar_bugs(
            "login NullPointerException session store returns no user", limit=3
        )
    finally:
        bug_similarity.load_bug_records.cache_clear()

    assert matches, "the confirmed fix should be retrievable through the fallback matcher"
    assert matches[0]["issue_id"] == "KB-BUG-20260805-001"


def test_the_learned_corpus_normalizes_for_the_semantic_indexer(monkeypatch):
    """The written CSV must also normalize cleanly for vector indexing."""
    from utils import rag_search
    from utils.rag_search import normalize_bug_record, read_dataset_rows

    knowledge_base.record_confirmed_fix(REPORT, FIX)
    # The indexer names records relative to the project root; point it at the
    # temporary corpus so the real dataset directory stays untouched.
    monkeypatch.setattr(rag_search, "ROOT_DIR", knowledge_base.LEARNED_CSV.parents[1])
    rows = read_dataset_rows(knowledge_base.LEARNED_CSV)
    assert rows, "the learned CSV should be readable by the dataset loader"

    normalized = normalize_bug_record(rows[0], knowledge_base.LEARNED_CSV, 0)
    assert normalized is not None
    metadata = normalized["metadata"]
    assert metadata["bug_id"] == "KB-BUG-20260805-001"
    # The fix is descriptive, so it survives the status filter and reaches
    # the remediation agent as a real historical resolution.
    assert metadata["resolution"] == FIX


def test_the_retrieval_cache_is_warm_after_a_confirmed_fix(monkeypatch):
    """A cold cache would make the next search reload the whole corpus.

    Interactive retrieval runs under a short timeout, so a cold cache can make
    the search that should show the new fix return nothing instead.
    """
    from utils import bug_similarity

    monkeypatch.setattr(bug_similarity, "GITBUGS_DIR", knowledge_base.LEARNED_CSV.parents[1])
    bug_similarity.load_bug_records.cache_clear()
    try:
        knowledge_base.record_confirmed_fix(REPORT, FIX)
        assert bug_similarity.load_bug_records.cache_info().currsize == 1
    finally:
        bug_similarity.load_bug_records.cache_clear()


def test_a_confirmed_fix_grounds_the_next_recommendation(monkeypatch):
    """The point of the mechanism: a learned fix must change what is advised.

    Before the fix is confirmed, the pipeline can only infer a recommendation
    from diagnostics. After it is confirmed, the same failure must be answered
    from the recorded fix -- and this must hold on the fallback retrieval path,
    which is what runs until the semantic index is rebuilt.
    """
    from agents.orchestrator import BugAnalysisOrchestrator
    from utils import bug_similarity, rag_search

    monkeypatch.setattr(bug_similarity, "GITBUGS_DIR", knowledge_base.LEARNED_CSV.parents[1])
    monkeypatch.setattr(rag_search, "is_vector_index_ready", lambda: False)
    resubmission = {
        "bug_title": "Users cannot sign in after the evening deployment",
        "bug_description": "Sign-in fails for all users with a server error.",
        "log_text": REPORT["log_text"],
    }

    def analyze():
        bug_similarity.load_bug_records.cache_clear()
        return BugAnalysisOrchestrator().analyze(resubmission, "BUG-RESUBMIT")

    try:
        before = analyze()
        assert before["remediation"]["basis"] == "diagnostic"

        knowledge_base.record_confirmed_fix(REPORT, FIX)
        after = analyze()
    finally:
        bug_similarity.load_bug_records.cache_clear()

    assert after["remediation"]["basis"] == "historical"
    assert after["remediation"]["recommended_fix"] == FIX
    assert "KB-BUG-20260805-001" in after["remediation"]["evidence_bug_ids"]


def test_a_bare_workflow_status_from_history_never_becomes_a_recommendation(monkeypatch):
    """A "Fixed" status in a dataset must not be presented as a fix."""
    from utils import bug_similarity

    knowledge_base.LEARNED_CSV.parent.mkdir(parents=True, exist_ok=True)
    knowledge_base.LEARNED_CSV.write_text(
        "Issue id,Summary,Description,Resolution,Status\n"
        "OLD-1,Login fails with NullPointerException,"
        "Session lookup returns no user during login,Fixed,Closed\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(bug_similarity, "GITBUGS_DIR", knowledge_base.LEARNED_CSV.parents[1])
    bug_similarity.load_bug_records.cache_clear()
    try:
        from utils.rag_search import _search_local_fallback

        matches = _search_local_fallback("login NullPointerException session lookup", 3)
    finally:
        bug_similarity.load_bug_records.cache_clear()

    assert matches
    assert matches[0]["resolution"] == ""
    assert matches[0]["resolution_status"] == "Fixed"


def test_an_indexing_failure_does_not_lose_the_confirmed_fix(monkeypatch):
    def broken_index(_record):
        raise RuntimeError("vector index unavailable")

    monkeypatch.setattr(knowledge_base, "_index_learned_record", broken_index)
    with pytest.raises(RuntimeError):
        knowledge_base.record_confirmed_fix(REPORT, FIX)
    # The durable CSV write happens before indexing, so the fix is retained.
    assert knowledge_base.learned_entry_count() == 1

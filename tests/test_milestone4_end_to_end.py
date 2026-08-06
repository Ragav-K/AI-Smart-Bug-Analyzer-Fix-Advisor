"""End-to-end pipeline validation and the fixes it uncovered.

The full harness lives in ``evaluation/end_to_end_validation.py``. These tests
pin the behaviour it measures, including the three defects that end-to-end
validation exposed, so none of them can regress silently.
"""

import pytest

from agents.orchestrator import BugAnalysisOrchestrator
from evaluation.end_to_end_validation import (
    build_cases,
    build_corpus,
    make_retriever,
    run_case,
    summarize,
)
from utils.component_classifier import classify_component
from utils.parser import parse_log
from utils.severity_rules import score_severity

# --- Fixes uncovered by end-to-end validation ------------------------------


@pytest.mark.parametrize(
    ("log_text", "expected"),
    [
        ("FATAL: SecurityError: signed URL validation bypassed for tenant 41", "SecurityError"),
        (
            "level: ERROR\nstack: java.io.IOException: No space left on device\n"
            "\tat com.app.search.IndexWriter.flush(IndexWriter.java:210)",
            "IOException",
        ),
        ("2026-08-05 09:00:00 ERROR app - ValueError: invalid literal for int()", "ValueError"),
    ],
)
def test_exception_prefixed_by_a_log_level_or_field_is_still_detected(log_text, expected):
    parsed = parse_log(log_text)
    assert parsed.exception_type == expected
    assert parsed.root_exception == expected


def test_a_language_specific_parse_is_never_overridden_by_the_generic_scanner():
    java = (
        "java.lang.NullPointerException: user is null\n"
        "\tat com.app.auth.LoginService.validate(LoginService.java:52)\n"
        "Caused by: java.lang.IllegalStateException: no session\n"
        "\tat com.app.auth.SessionStore.lookup(SessionStore.java:77)"
    )
    parsed = parse_log(java)
    assert parsed.exception_type == "NullPointerException"
    assert parsed.root_exception == "IllegalStateException"


def test_plural_component_keywords_are_classified():
    assert classify_component("Something is wrong with notifications.")[0] == "Notifications"
    assert classify_component("Users report missing permissions on the account")[0] == "Authorization"


def test_payment_outage_phrased_as_a_verb_scores_as_critical():
    scores, _ = score_severity("Checkout payment fails for all customers during checkout.")
    assert scores["Critical"] >= 7


def test_retrieval_query_includes_the_stack_trace_when_no_submitted_text_exists():
    calls = []
    BugAnalysisOrchestrator(retriever=lambda query, limit: calls.append(query) or []).analyze(
        {
            "bug_title": "Login crashes",
            "bug_description": "All users hit a 500 during login.",
            "log_text": "java.lang.NullPointerException: user is null",
        }
    )
    assert "NullPointerException" in calls[0]
    assert "Login crashes" in calls[0]


def test_submitted_text_still_wins_when_the_form_supplied_it():
    calls = []
    BugAnalysisOrchestrator(retriever=lambda query, limit: calls.append(query) or []).analyze(
        {"submitted_text": "ValueError expired token", "log_text": "ignored"}
    )
    assert calls == ["ValueError expired token"]


# --- End-to-end pipeline quality -------------------------------------------


@pytest.fixture(scope="module")
def largest_corpus_outcomes():
    corpus = build_corpus(120)
    return [run_case(case, 120, corpus)[0] for case in build_cases()]


def test_every_case_completes_all_five_agents(largest_corpus_outcomes):
    for outcome in largest_corpus_outcomes:
        assert outcome.agents_executed == 5, outcome.case_id
        assert outcome.agent_errors == {}, outcome.case_id


def test_exception_component_and_severity_labels_are_met(largest_corpus_outcomes):
    summary = summarize(largest_corpus_outcomes)
    assert summary["exception_detection_accuracy"] == 1.0
    assert summary["component_accuracy"] == 1.0
    assert summary["severity_accuracy"] == 1.0
    assert summary["stack_parse_accuracy"] == 1.0


def test_duplicate_detection_never_reports_a_wrong_historical_defect(largest_corpus_outcomes):
    summary = summarize(largest_corpus_outcomes)
    assert summary["duplicate_precision"] == 1.0
    assert summary["duplicate_recall"] >= 0.7


def test_recommendations_are_grounded_in_the_defect_that_holds_the_fix(largest_corpus_outcomes):
    assert summarize(largest_corpus_outcomes)["recommendation_relevance"] == 1.0


def test_the_pipeline_degrades_rather_than_fails_without_any_history():
    outcomes = [run_case(case, 0, [])[0] for case in build_cases()]
    for outcome in outcomes:
        assert outcome.agents_executed == 5, outcome.case_id
        assert outcome.predicted_duplicates == [], outcome.case_id
        # Nothing may be presented as historically proven when no history exists.
        assert outcome.remediation_basis in {"diagnostic", "none"}, outcome.case_id


def test_duplicate_quality_is_stable_as_the_corpus_grows():
    """Adding unrelated history must not create false duplicate matches."""
    results = {
        size: summarize([run_case(case, size, build_corpus(size))[0] for case in build_cases()])
        for size in (6, 120)
    }
    for size, summary in results.items():
        assert summary["duplicate_precision"] == 1.0, size
    assert results[6]["duplicate_recall"] == results[120]["duplicate_recall"]


def test_the_harness_covers_varied_bug_types_and_trace_formats():
    cases = build_cases()
    assert len({case.bug_type for case in cases}) >= 10
    formats = {case.trace_format for case in cases}
    assert {"Java stack trace with Caused by", "Python traceback", "Node.js stack trace"} <= formats
    assert any(case.submission == {} for case in cases), "an empty submission must be exercised"
    assert any(isinstance(case.submission, str) for case in cases), "plain text must be exercised"


def test_retriever_returns_nothing_for_an_empty_corpus_or_query():
    assert make_retriever([])("anything", 5) == []
    assert make_retriever(build_corpus(6))("", 5) == []

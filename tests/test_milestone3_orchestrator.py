"""Pipeline, retrieval reuse, fault isolation, and edge-case tests."""

from agents.orchestrator import BugAnalysisOrchestrator

MATCH = {
    "bug_id": "BUG-32",
    "title": "ValueError in authentication parser",
    "description": "Authentication token parser rejected an invalid value.",
    "root_cause": "Expired token reached the parser without validation.",
    "resolution": "Validate token expiry before parsing.",
    "status": "Resolved",
    "priority": "High",
    "similarity": 0.91,
    "similarity_percentage": 91,
}


def test_complete_pipeline_reuses_submission_retrieval():
    calls = []
    orchestrator = BugAnalysisOrchestrator(
        retriever=lambda query, limit: calls.append((query, limit)) or []
    )
    result = orchestrator.analyze(
        {
            "submission_id": "BUG-M3-001",
            "bug_description": "Authentication failed",
            "log_text": "ValueError: expired token",
            "similar_bugs": [MATCH],
        }
    )
    assert calls == []
    assert result["metadata"]["retrieval_reused"] is True
    assert result["metadata"]["retrieval_count"] == 1
    assert result["metadata"]["agents_executed"] == [
        "LogAnalysis",
        "Triage",
        "RootCause",
        "DuplicateDetection",
        "Remediation",
    ]
    assert result["root_cause"]["matched_bug_ids"] == ["BUG-32"]
    assert result["remediation"]["evidence_bug_ids"] == ["BUG-32"]
    assert result["metadata"]["schema_version"] == "3.0"


def test_orchestrator_retrieves_exactly_once():
    calls = []

    def retrieve(query, limit):
        calls.append((query, limit))
        return [MATCH]

    result = BugAnalysisOrchestrator(retriever=retrieve).analyze(
        {"submitted_text": "ValueError expired token"}
    )
    assert calls == [("ValueError expired token", 10)]
    assert result["metadata"]["retrieval_reused"] is False


class FailingRootCause:
    """Synthetic dependency failure."""

    def predict(self, _context):
        raise RuntimeError("root model unavailable")


def test_downstream_agents_degrade_when_root_cause_fails():
    result = BugAnalysisOrchestrator(
        root_cause_agent=FailingRootCause(),
        retriever=lambda _query, _limit: [MATCH],
    ).analyze({"submitted_text": "ValueError expired token"})
    assert "RootCause" in result["metadata"]["agent_errors"]
    assert result["duplicate_detection"] is not None
    assert result["remediation"] is not None


def test_empty_report_completes_all_stages():
    result = BugAnalysisOrchestrator().analyze({"similar_bugs": []})
    assert len(result["metadata"]["agents_executed"]) == 5
    assert result["duplicate_detection"]["duplicates"] == []
    assert result["remediation"]["confidence"] <= 35


def test_retrieval_and_storage_failures_are_reported():
    def broken_retriever(_query, _limit):
        raise OSError("index unavailable")

    def broken_store(_result):
        raise OSError("disk unavailable")

    result = BugAnalysisOrchestrator(
        retriever=broken_retriever,
        result_store=broken_store,
    ).predict({"submitted_text": "ValueError"})
    assert "Retrieval" in result["metadata"]["agent_errors"]
    assert "storage_warning" in result["metadata"]


def test_overall_confidence_without_results_is_zero():
    assert BugAnalysisOrchestrator._overall_confidence({}) == 0

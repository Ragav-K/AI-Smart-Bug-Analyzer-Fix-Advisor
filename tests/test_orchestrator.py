"""Integration and failure-isolation tests for orchestration."""

from agents.orchestrator import BugAnalysisOrchestrator


def test_integration_workflow():
    result = BugAnalysisOrchestrator().analyze({
        "submission_id": "BUG-TEST-001",
        "bug_title": "Production login outage",
        "bug_description": "All users cannot login",
        "log_text": 'Traceback (most recent call last):\n  File "auth.py", line 3, in login\n    user.id\nAttributeError: user missing',
    })
    assert result["submission_id"] == "BUG-TEST-001"
    assert result["triage"]["component"] == "Authentication"
    assert result["log_analysis"]["exception_type"] == "AttributeError"
    assert result["metadata"]["agents_executed"] == ["Triage", "LogAnalysis"]
    assert result["metadata"]["processing_time_seconds"] < 3
    assert result["metadata"]["future_agent_context"]


class FailingAgent:
    def predict(self, _submission):
        raise RuntimeError("synthetic failure")


def test_one_agent_failure_does_not_stop_other():
    result = BugAnalysisOrchestrator(triage_agent=FailingAgent()).analyze("ValueError: bad value")
    assert result["triage"] is None
    assert result["log_analysis"]["exception_type"] == "ValueError"
    assert result["metadata"]["agents_executed"] == ["LogAnalysis"]
    assert "Triage" in result["metadata"]["agent_errors"]


def test_dependency_injected_result_store():
    stored = []
    result = BugAnalysisOrchestrator(result_store=stored.append).analyze("Typo in UI button")
    assert stored and stored[0]["submission_id"] == "UNSAVED"
    assert result["metadata"]["schema_version"] == "2.0"


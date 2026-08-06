"""Tests for dashboard report generation and Streamlit rendering."""

from streamlit.testing.v1 import AppTest

from ui.findings import build_markdown_report

LINE_JOIN = "\n"


ANALYSIS = {
    "submission_id": "BUG-UI-1",
    "overall_confidence": 84,
    "triage": {
        "severity": "High",
        "priority": "P1",
        "component": "Authentication",
        "confidence": 88,
        "business_impact": "Login is blocked.",
        "reasoning": "Authentication signals.",
        "evidence": ["oauth"],
    },
    "log_analysis": {
        "exception_type": "ValueError",
        "failure_point": "login in auth.py",
        "confidence": 90,
        "call_stack_summary": ["login at auth.py:10"],
        "call_stack": [],
    },
    "root_cause": {
        "root_cause": "Expired token was not validated.",
        "confidence": 86,
        "reasoning": "Matched resolved bug.",
        "supporting_evidence": [],
    },
    "duplicate_detection": {
        "duplicates": [],
        "candidates_evaluated": 3,
        "threshold": 65,
    },
    "remediation": {
        "recommended_fix": "Validate token expiry.",
        "steps": ["Add validation.", "Run tests."],
        "files_likely_affected": ["auth.py"],
        "historical_resolution": "BUG-1 used validation.",
        "best_practice": "Test expiry paths.",
        "confidence": 82,
    },
    "metadata": {"processing_time_seconds": 0.2, "agent_errors": {}},
}


def test_markdown_report_contains_all_findings():
    report = build_markdown_report(ANALYSIS, {"bug_title": "Login fails"})
    assert "Login fails" in report
    assert "Expired token was not validated" in report
    assert "Validate token expiry" in report
    assert "Overall confidence: 84%" in report


def test_dashboard_renders_without_exception():
    app = AppTest.from_string(
        """
from ui.findings import render_findings_dashboard
from tests.test_findings import ANALYSIS
render_findings_dashboard(ANALYSIS, {"bug_title": "Login fails"})
"""
    )
    app.run(timeout=15)
    assert not app.exception
    assert any("Structured Findings" in item.value for item in app.markdown)
    rendered_text = LINE_JOIN.join(item.value for item in app.markdown)
    for agent_name in (
        "Log Analysis Agent",
        "Triage Agent",
        "Root Cause Agent",
        "Duplicate Detection Agent",
        "Remediation Agent",
    ):
        assert agent_name in rendered_text


def test_dashboard_renders_evidence_duplicates_and_errors():
    app = AppTest.from_string(
        """
from copy import deepcopy
from ui.findings import render_findings_dashboard
from tests.test_findings import ANALYSIS
value = deepcopy(ANALYSIS)
value["metadata"]["agent_errors"] = {"OptionalStage": "unavailable"}
value["log_analysis"]["error_message"] = "expired token"
value["log_analysis"]["call_stack"] = [{"file": "auth.py", "line": 10, "function": "login"}]
value["root_cause"]["supporting_evidence"] = [{"source": "KB", "bug_id": "BUG-1", "detail": "match", "similarity": 91}]
value["duplicate_detection"]["duplicates"] = [{
    "bug_id": "BUG-1", "similarity": 91, "status": "Resolved",
    "summary": "Expired token", "resolution": "Validate expiry",
    "match_reasons": ["Exception type matches"]
}]
render_findings_dashboard(value, {"bug_title": "Login fails", "bug_description": "Cannot sign in"})
"""
    )
    app.run(timeout=15)
    assert not app.exception
    assert app.dataframe
    assert app.error


def test_dashboard_empty_and_partial_sections_render_safely():
    app = AppTest.from_string(
        """
from ui.findings import (
    render_findings_dashboard, _render_log_analysis,
    _render_root_cause, _render_remediation,
)
render_findings_dashboard({})
_render_log_analysis({})
_render_root_cause({})
_render_remediation({})
"""
    )
    app.run(timeout=15)
    assert not app.exception
    # Each empty section must say so rather than rendering a blank panel.
    assert len(app.info) == 3

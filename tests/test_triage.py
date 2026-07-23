"""Unit tests for deterministic bug triage."""

import pytest

from agents.triage_agent import TriageAgent


@pytest.fixture
def agent() -> TriageAgent:
    return TriageAgent()


@pytest.mark.parametrize(
    ("text", "severity", "priority"),
    [
        ("Production outage affects all users", "Critical", "P0"),
        ("Application crash when worker starts", "Critical", "P1"),
        ("Database unavailable; users cannot complete workflow", "High", "P1"),
        ("Validation issue makes feature partially working", "Medium", "P2"),
        ("Typo and spacing issue", "Low", "P3"),
    ],
)
def test_severity_and_priority(agent, text, severity, priority):
    result = agent.predict(text)
    assert result.severity == severity
    assert result.priority == priority


@pytest.mark.parametrize(
    ("text", "component"),
    [
        ("oauth token expired during login", "Authentication"),
        ("SQL query database connection failed", "Database"),
        ("REST endpoint returned HTTP 500", "REST API"),
        ("card payment gateway rejected checkout", "Payment"),
        ("CSS button layout has wrong spacing", "UI"),
    ],
)
def test_component_detection(agent, text, component):
    assert agent.predict(text).component == component


def test_explainability_fields(agent):
    result = agent.predict("Production payment failure blocks checkout for all users")
    assert result.business_impact
    assert result.reasoning
    assert result.evidence
    assert 0 <= result.confidence <= 100


def test_missing_fields_are_graceful(agent):
    result = agent.predict({})
    assert result.severity == "Medium"
    assert result.component == "Other"
    assert result.confidence <= 50


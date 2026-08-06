"""Defect pattern analytics: themes, hotspots, and systemic issue detection."""

from agents.pattern_analytics_agent import DefectPatternAnalyticsAgent
from utils.defect_analytics import (
    extract_facts,
    percentage,
    recurrence_rate,
    repeated_failure_points,
    theme_label,
)


def report(
    submission_id,
    exception="NullPointerException",
    component="Authentication",
    severity="Critical",
    priority="P0",
    failure_point="validate in LoginService.java",
    duplicates=None,
    basis="historical",
    title="Login fails",
):
    return {
        "submission_id": submission_id,
        "bug_title": title,
        "timestamp": f"2026-08-0{submission_id[-1]}T09:00:00",
        "analysis": {
            "triage": {"severity": severity, "priority": priority, "component": component},
            "log_analysis": {"root_exception": exception, "failure_point": failure_point},
            "duplicate_detection": {"duplicates": duplicates or []},
            "remediation": {"basis": basis},
            "overall_confidence": 70,
        },
    }


def test_no_reports_produces_an_empty_but_valid_result():
    result = DefectPatternAnalyticsAgent().predict([])
    assert result.submissions_analyzed == 0
    assert result.themes == []
    assert result.systemic_patterns == []
    assert result.notes


def test_submissions_without_agent_output_are_excluded_not_counted():
    result = DefectPatternAnalyticsAgent().predict(
        [report("BUG-1"), {"submission_id": "BUG-2"}, {"submission_id": "BUG-3", "analysis": {}}]
    )
    assert result.submissions_analyzed == 3
    assert result.submissions_with_pipeline_output == 1
    assert any("no agent output" in note for note in result.notes)


def test_theme_groups_identical_failures_across_differently_worded_reports():
    reports = [
        report("BUG-1", title="Login crashes"),
        report("BUG-2", title="Cannot sign in at all"),
        report("BUG-3", exception="KeyError", component="REST API", title="Order fails"),
    ]
    result = DefectPatternAnalyticsAgent().predict(reports)
    top = result.themes[0]
    assert top.theme == "NullPointerException in Authentication"
    assert top.occurrences == 2
    assert top.share_percentage == 67
    assert top.example_submission_ids == ["BUG-1", "BUG-2"]
    assert result.recurrence_rate == 67


def test_component_hotspot_counts_high_impact_defects():
    reports = [
        report("BUG-1", severity="Critical"),
        report("BUG-2", severity="High"),
        report("BUG-3", severity="Low"),
        report("BUG-4", component="UI", exception="Unclassified", severity="Low"),
    ]
    hotspot = DefectPatternAnalyticsAgent().predict(reports).component_hotspots[0]
    assert hotspot.component == "Authentication"
    assert hotspot.defect_count == 3
    assert hotspot.high_impact_count == 2
    assert hotspot.top_exceptions == ["NullPointerException"]


def test_recurring_exception_and_component_patterns_are_detected():
    reports = [report(f"BUG-{index}") for index in range(1, 5)]
    patterns = {
        pattern.pattern_id: pattern
        for pattern in DefectPatternAnalyticsAgent().predict(reports).systemic_patterns
    }
    assert "recurring-exception:NullPointerException" in patterns
    assert "component-hotspot:Authentication" in patterns
    assert "repeated-failure-point:validate in LoginService.java" in patterns
    recurring = patterns["recurring-exception:NullPointerException"]
    assert recurring.affected_submissions == 4
    assert recurring.evidence and recurring.recommendation


def test_systemic_detection_stays_silent_below_the_minimum_sample():
    result = DefectPatternAnalyticsAgent().predict([report("BUG-1"), report("BUG-2")])
    assert result.systemic_patterns == []
    assert any("at least 3" in note for note in result.notes)


def test_isolated_incidents_do_not_produce_systemic_patterns():
    reports = [
        report("BUG-1", exception="KeyError", component="REST API", failure_point="a in a.py"),
        report("BUG-2", exception="TypeError", component="Payment", failure_point="b in b.js"),
        report("BUG-3", exception="IOException", component="Storage", failure_point="c in c.java"),
        report("BUG-4", exception="SQLException", component="Database", failure_point="d in d.java"),
    ]
    result = DefectPatternAnalyticsAgent().predict(reports)
    assert [pattern.pattern_id for pattern in result.systemic_patterns] == []
    assert result.recurrence_rate == 0


def test_duplicate_influx_and_knowledge_gap_patterns():
    duplicate = [{"bug_id": "HIST-9", "similarity": 88}]
    reports = [
        report("BUG-1", duplicates=duplicate, basis="diagnostic"),
        report("BUG-2", duplicates=duplicate, basis="diagnostic"),
        report("BUG-3", exception="KeyError", component="REST API", basis="none"),
    ]
    result = DefectPatternAnalyticsAgent().predict(reports)
    identifiers = {pattern.pattern_id for pattern in result.systemic_patterns}
    assert "duplicate-influx" in identifiers
    assert "knowledge-base-gap" in identifiers
    assert result.duplicate_rate == 67


def test_grounded_recommendations_clear_the_knowledge_gap_pattern():
    reports = [report(f"BUG-{index}", basis="historical") for index in range(1, 5)]
    result = DefectPatternAnalyticsAgent().predict(reports)
    assert "knowledge-base-gap" not in {p.pattern_id for p in result.systemic_patterns}


def test_extracted_facts_expose_the_fields_analytics_relies_on():
    fact = extract_facts([report("BUG-1", duplicates=[{"bug_id": "H-1", "similarity": 90}])])[0]
    assert fact["exception"] == "NullPointerException"
    assert fact["component"] == "Authentication"
    assert fact["has_duplicate"] is True
    assert fact["duplicate_similarity"] == 90
    assert fact["theme"] == "NullPointerException in Authentication"


def test_unclassified_failures_are_named_without_inventing_an_exception():
    assert theme_label("Unclassified", "UI") == "Unclassified failure in UI"


def test_percentage_and_rate_helpers_handle_empty_input():
    assert percentage(3, 0) == 0
    assert recurrence_rate([]) == 0
    assert repeated_failure_points([]) == []


def test_failure_points_the_agent_could_not_determine_are_ignored():
    facts = extract_facts(
        [
            report("BUG-1", failure_point="Unable to determine from the supplied log"),
            report("BUG-2", failure_point="Unable to determine from the supplied log"),
        ]
    )
    assert repeated_failure_points(facts) == []


def test_result_serializes_for_the_dashboard_and_reports():
    data = DefectPatternAnalyticsAgent().predict([report("BUG-1")]).model_dump(mode="json")
    assert data["themes"][0]["theme"] == "NullPointerException in Authentication"
    assert "severity_distribution" in data

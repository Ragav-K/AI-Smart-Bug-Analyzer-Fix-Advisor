"""Aggregation primitives for defect pattern analytics.

Every function here is pure and Streamlit-free so the same aggregation can be
rendered in the web application, exercised by tests, and written into the
evaluation reports without duplicating the arithmetic.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

# A rule fired on one or two submissions describes an incident, not a system.
# These floors keep the systemic-pattern section silent until the portfolio is
# large enough for a proportion to mean anything.
MIN_SUBMISSIONS_FOR_PATTERNS = 3
MIN_OCCURRENCES_FOR_THEME = 2
COMPONENT_HOTSPOT_SHARE = 30
COMPONENT_HOTSPOT_MINIMUM = 3
EXCEPTION_PATTERN_SHARE = 25
HIGH_IMPACT_SEVERITIES = {"Critical", "High"}
UNCLASSIFIED_EXCEPTION = "Unclassified"


def percentage(part: int, whole: int) -> int:
    """Return part/whole as a whole percentage, treating an empty whole as 0."""
    if whole <= 0:
        return 0
    return max(0, min(100, round(part * 100 / whole)))


def extract_facts(reports: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Reduce saved submissions to the comparable fields analytics needs.

    Reports saved before the analysis pipeline existed, or whose pipeline
    failed outright, carry no agent output. They are skipped rather than
    counted as an "Unknown/Other" defect, which would invent a fake theme.
    """
    facts: list[dict[str, Any]] = []
    for report in reports:
        analysis = report.get("analysis") or {}
        if not analysis:
            continue
        triage = analysis.get("triage") or {}
        log_analysis = analysis.get("log_analysis") or {}
        duplicates = (analysis.get("duplicate_detection") or {}).get("duplicates") or []
        remediation = analysis.get("remediation") or {}
        exception = str(
            log_analysis.get("root_exception")
            or log_analysis.get("exception_type")
            or ""
        ).strip() or UNCLASSIFIED_EXCEPTION
        component = str(triage.get("component") or "Other").strip() or "Other"
        top_duplicate = duplicates[0] if duplicates else {}
        facts.append(
            {
                "submission_id": str(
                    report.get("submission_id") or analysis.get("submission_id") or "Unknown"
                ),
                "title": str(report.get("bug_title") or "Untitled"),
                "timestamp": str(report.get("timestamp") or analysis.get("timestamp") or ""),
                "severity": str(triage.get("severity") or "Unknown"),
                "priority": str(triage.get("priority") or "Unknown"),
                "component": component,
                "exception": exception,
                "failure_point": str(log_analysis.get("failure_point") or "").strip(),
                "file": str(log_analysis.get("file") or "").strip(),
                "duplicate_bug_id": str(top_duplicate.get("bug_id") or ""),
                "duplicate_similarity": int(top_duplicate.get("similarity") or 0),
                "has_duplicate": bool(duplicates),
                "remediation_basis": str(remediation.get("basis") or "none"),
                "overall_confidence": int(analysis.get("overall_confidence") or 0),
                "theme": theme_label(exception, component),
            }
        )
    return facts


def theme_label(exception: str, component: str) -> str:
    """Name a recurring failure by what failed and where."""
    if exception == UNCLASSIFIED_EXCEPTION:
        return f"Unclassified failure in {component}"
    return f"{exception} in {component}"


def distribution(facts: list[dict[str, Any]], key: str) -> dict[str, int]:
    """Count one extracted field, ordered from most to least frequent."""
    counts = Counter(str(fact.get(key) or "Unknown") for fact in facts)
    return dict(counts.most_common())


def theme_groups(facts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Group facts by failure signature, most frequent first."""
    grouped: dict[str, list[dict[str, Any]]] = {}
    for fact in facts:
        grouped.setdefault(fact["theme"], []).append(fact)

    groups = [
        {
            "theme": theme,
            "exception": members[0]["exception"],
            "component": members[0]["component"],
            "occurrences": len(members),
            "share_percentage": percentage(len(members), len(facts)),
            "timestamps": sorted(
                stamp for stamp in (member["timestamp"] for member in members) if stamp
            ),
            "submission_ids": [member["submission_id"] for member in members],
        }
        for theme, members in grouped.items()
    ]
    groups.sort(key=lambda group: (-group["occurrences"], group["theme"]))
    return groups


def component_groups(facts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Group facts by affected component, most affected first."""
    grouped: dict[str, list[dict[str, Any]]] = {}
    for fact in facts:
        grouped.setdefault(fact["component"], []).append(fact)

    groups = [
        {
            "component": component,
            "defect_count": len(members),
            "share_percentage": percentage(len(members), len(facts)),
            "high_impact_count": sum(
                1 for member in members if member["severity"] in HIGH_IMPACT_SEVERITIES
            ),
            "top_exceptions": [
                name
                for name, _ in Counter(
                    member["exception"]
                    for member in members
                    if member["exception"] != UNCLASSIFIED_EXCEPTION
                ).most_common(3)
            ],
            "submission_ids": [member["submission_id"] for member in members],
        }
        for component, members in grouped.items()
    ]
    groups.sort(key=lambda group: (-group["defect_count"], group["component"]))
    return groups


def recurrence_rate(facts: list[dict[str, Any]]) -> int:
    """Return the share of defects that belong to an already-seen theme."""
    if not facts:
        return 0
    recurring = sum(
        group["occurrences"]
        for group in theme_groups(facts)
        if group["occurrences"] >= MIN_OCCURRENCES_FOR_THEME
    )
    return percentage(recurring, len(facts))


def duplicate_rate(facts: list[dict[str, Any]]) -> int:
    """Return the share of defects matched to a high-confidence duplicate."""
    return percentage(sum(1 for fact in facts if fact["has_duplicate"]), len(facts))


def repeated_failure_points(facts: list[dict[str, Any]]) -> list[tuple[str, int]]:
    """Return failure locations that were reached by more than one defect."""
    counts = Counter(
        fact["failure_point"]
        for fact in facts
        if fact["failure_point"] and "Unable to determine" not in fact["failure_point"]
    )
    return [(point, count) for point, count in counts.most_common() if count >= 2]

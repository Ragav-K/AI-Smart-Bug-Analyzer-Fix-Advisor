"""Reusable confidence and similarity scoring for Milestone 3 agents."""

from __future__ import annotations

import re
from typing import Any


def clamp_percentage(value: float) -> int:
    """Round and constrain a numeric score to the inclusive 0-100 range."""
    return max(0, min(100, round(value)))


def normalized_similarity(candidate: dict[str, Any]) -> float:
    """Return a historical match similarity normalized to 0.0-1.0."""
    raw = candidate.get("similarity")
    if raw is None:
        raw = float(candidate.get("similarity_percentage") or 0) / 100
    value = float(raw or 0)
    return max(0.0, min(1.0, value / 100 if value > 1 else value))


def text_contains(value: Any, needle: Any) -> bool:
    """Compare non-empty diagnostic tokens case-insensitively."""
    left = str(value or "").lower()
    right = str(needle or "").lower()
    return bool(left and right and (right in left or left in right))


def diagnostic_text(candidate: dict[str, Any]) -> str:
    """Build a bounded searchable representation of a historical candidate."""
    keys = (
        "title",
        "description",
        "full_text",
        "root_cause",
        "resolution",
        "labels",
        "project_name",
    )
    return " ".join(str(candidate.get(key) or "") for key in keys)[:20_000]


def rerank_duplicate(
    candidate: dict[str, Any],
    exception_type: str | None,
    component: str | None,
    severity: str | None,
) -> tuple[int, list[str]]:
    """Combine semantic similarity with exact diagnostic agreement."""
    semantic = normalized_similarity(candidate)
    text = diagnostic_text(candidate)
    exception_match = text_contains(text, exception_type)
    component_match = text_contains(text, component)
    severity_match = text_contains(candidate.get("priority"), severity)
    score = (
        semantic * 75
        + (12 if exception_match else 0)
        + (9 if component_match else 0)
        + (4 if severity_match else 0)
    )
    reasons = [f"{clamp_percentage(semantic * 100)}% semantic similarity"]
    if exception_match:
        reasons.append("Exception type matches")
    if component_match:
        reasons.append("Affected component matches")
    if severity_match:
        reasons.append("Severity or priority metadata agrees")
    return clamp_percentage(score), reasons


def stack_similarity(candidate: dict[str, Any], stack_summary: list[str]) -> float:
    """Estimate stack agreement from identifiers shared with retrieved text."""
    if not stack_summary:
        return 0.0
    candidate_tokens = set(re.findall(r"[A-Za-z_][A-Za-z0-9_]{2,}", diagnostic_text(candidate).lower()))
    stack_tokens = set(re.findall(r"[A-Za-z_][A-Za-z0-9_]{2,}", " ".join(stack_summary).lower()))
    if not stack_tokens:
        return 0.0
    return len(candidate_tokens & stack_tokens) / len(stack_tokens)


def root_cause_confidence(
    candidates: list[dict[str, Any]],
    exception_type: str | None,
    component: str | None,
    stack_summary: list[str],
    log_confidence: int,
) -> int:
    """Compute conservative confidence from the requested evidence signals."""
    if not candidates:
        return clamp_percentage(log_confidence * 0.35)
    similarities = [normalized_similarity(item) for item in candidates[:5]]
    best = similarities[0]
    historical_agreement = sum(score >= 0.55 for score in similarities) / len(similarities)
    exception_agreement = sum(
        text_contains(diagnostic_text(item), exception_type) for item in candidates[:5]
    ) / min(5, len(candidates))
    component_agreement = sum(
        text_contains(diagnostic_text(item), component) for item in candidates[:5]
    ) / min(5, len(candidates))
    stack_agreement = max(stack_similarity(item, stack_summary) for item in candidates[:5])
    completeness = max(0.0, min(1.0, log_confidence / 100))
    return clamp_percentage(
        best * 35
        + historical_agreement * 20
        + exception_agreement * 15
        + component_agreement * 10
        + stack_agreement * 10
        + completeness * 10
    )


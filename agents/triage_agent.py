"""Deterministic, explainable bug triage agent."""

from __future__ import annotations

import re
from typing import Any

from models.triage_models import TriageResult
from utils.component_classifier import classify_component
from utils.confidence import bounded_confidence
from utils.logging_config import get_agent_logger
from utils.severity_rules import score_severity


class TriageAgent:
    """Classify issue-tracker fields using weighted, explainable rules."""

    def __init__(self) -> None:
        self.logger = get_agent_logger(__name__)
        self.initialized = False
        self._last_matches: list[str] = []
        self._component_evidence: list[str] = []
        self.initialize()

    def initialize(self) -> None:
        """Initialize local rule resources (kept as a public extension hook)."""
        self.initialized = True

    def preprocess(self, report: str | dict[str, Any] | None) -> str:
        """Normalize either free text or a Module 1 submission record."""
        if isinstance(report, dict):
            preferred = (
                "bug_title", "bug_description", "steps_to_reproduce", "expected_result",
                "actual_result", "environment", "submitted_text", "log_text",
            )
            parts = [str(report.get(key) or "").strip() for key in preferred]
            text = "\n".join(part for part in parts if part)
        else:
            text = str(report or "")
        return re.sub(r"[ \t]+", " ", text).strip()[:1_000_000]

    def classify_severity(self, text: str) -> str:
        scores, matches = score_severity(text)
        ranked = sorted(scores, key=lambda level: scores[level], reverse=True)
        top = ranked[0]
        self._last_matches = matches[top]
        if scores["Critical"] >= 7:
            self._last_matches = matches["Critical"]
            return "Critical"
        if scores["High"] >= 6 or scores["Critical"] >= 4:
            self._last_matches = matches["High"] + matches["Critical"]
            return "High"
        if scores["Medium"] >= 3:
            self._last_matches = matches["Medium"]
            return "Medium"
        if scores["Low"] > 0:
            self._last_matches = matches["Low"]
            return "Low"
        self._last_matches = []
        return "Medium"

    def classify_priority(self, severity: str, text: str) -> str:
        normalized = text.lower()
        urgent = any(term in normalized for term in ("production", "security", "payment", "data loss", "breach"))
        broad_impact = any(term in normalized for term in ("all users", "every user", "customers cannot", "outage"))
        if severity == "Critical" and (urgent or broad_impact):
            return "P0"
        return {"Critical": "P1", "High": "P1", "Medium": "P2", "Low": "P3"}[severity]

    def classify_component(self, text: str) -> str:
        component, evidence, _ = classify_component(text)
        self._component_evidence = evidence
        return component

    def calculate_confidence(self, severity: str, component: str, text: str) -> int:
        signals = len(set(self._last_matches + self._component_evidence))
        ambiguity = int(component == "Other") + int(not self._last_matches)
        if not text.strip():
            return 10
        return bounded_confidence(61, signals, ambiguity)

    def generate_reasoning(self, severity: str, priority: str, component: str) -> str:
        severity_basis = ", ".join(self._last_matches[:3]) or "limited explicit impact signals"
        component_basis = ", ".join(self._component_evidence[:3]) or "no dominant component keywords"
        return (
            f"Classified as {severity}/{priority} from {severity_basis}. "
            f"The affected area is {component}, supported by {component_basis}."
        )

    def predict(self, report: str | dict[str, Any] | None) -> TriageResult:
        text = self.preprocess(report)
        severity = self.classify_severity(text)
        priority = self.classify_priority(severity, text)
        component = self.classify_component(text)
        confidence = self.calculate_confidence(severity, component, text)
        evidence = list(dict.fromkeys(self._last_matches + self._component_evidence))[:8]
        result = TriageResult(
            severity=severity,
            priority=priority,
            component=component,
            business_impact=self._business_impact(severity, component, text),
            confidence=confidence,
            reasoning=self.generate_reasoning(severity, priority, component),
            evidence=evidence,
        )
        self.logger.info("Triage completed", extra={"agent": "Triage", "confidence": confidence})
        return result

    @staticmethod
    def _business_impact(severity: str, component: str, text: str) -> str:
        lowered = text.lower()
        if component == "Authentication":
            impact = "Users may be unable to sign in or maintain authenticated sessions."
        elif component == "Payment":
            impact = "Customers may be unable to complete payments, affecting revenue."
        elif component == "Database":
            impact = "Data-backed workflows may fail or return unavailable or inconsistent results."
        elif component in {"Frontend", "UI", "UX"}:
            impact = "Users may encounter a degraded or blocked interface workflow."
        elif "all users" in lowered or "outage" in lowered:
            impact = "A broad customer population is unable to use the affected service."
        else:
            impact = f"The {component.lower()} workflow may be degraded for affected users."
        if severity == "Critical":
            impact += " Immediate mitigation is required."
        return impact


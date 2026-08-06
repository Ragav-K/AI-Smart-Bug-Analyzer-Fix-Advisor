"""Evidence-grounded root cause analysis using shared RAG results."""

from __future__ import annotations

from collections import Counter
from typing import Any

from models.analysis_models import EvidenceItem, RootCauseResult
from utils.logging_config import get_agent_logger
from utils.scoring import diagnostic_text, normalized_similarity, root_cause_confidence


class RootCauseAgent:
    """Infer why a failure occurred while retaining evidence provenance."""

    def __init__(self) -> None:
        self.logger = get_agent_logger(__name__)

    def predict(self, context: dict[str, Any]) -> RootCauseResult:
        """Analyze current diagnostics and the retrieved historical defects."""
        candidates = list(context.get("retrieved_bugs") or [])[:5]
        log_analysis = context.get("log_analysis") or {}
        triage = context.get("triage") or {}
        exception = log_analysis.get("root_exception") or log_analysis.get("exception_type")
        explicit_causes = [
            str(candidate.get("root_cause")).strip()
            for candidate in candidates
            if str(candidate.get("root_cause") or "").strip()
        ]
        resolutions = [
            str(candidate.get("resolution")).strip()
            for candidate in candidates
            if str(candidate.get("resolution") or "").strip()
        ]
        if explicit_causes:
            root_cause = Counter(explicit_causes).most_common(1)[0][0]
            basis = "the root-cause field recorded in the closest historical defect"
        elif resolutions:
            root_cause = self._cause_from_resolution(resolutions[0], exception, triage.get("component"))
            basis = "the corrective action recorded in the closest historical defect"
        elif candidates and log_analysis.get("probable_cause"):
            root_cause = str(log_analysis["probable_cause"])
            basis = "current log diagnostics, checked against retrieved defects"
        else:
            root_cause = "Insufficient grounded evidence to determine a root cause."
            basis = "the absence of a sufficiently descriptive historical match"

        evidence = self._evidence(candidates, exception, triage.get("component"))
        confidence = root_cause_confidence(
            candidates,
            exception,
            triage.get("component"),
            list(log_analysis.get("call_stack_summary") or []),
            int(log_analysis.get("confidence") or 0),
        )
        matched_ids = [
            str(candidate.get("bug_id") or candidate.get("issue_id"))
            for candidate in candidates
            if candidate.get("bug_id") or candidate.get("issue_id")
        ]
        reasoning = (
            f"The conclusion uses {basis}. "
            f"It compares the {exception or 'unknown exception'} failure in "
            f"{triage.get('component') or 'an unknown component'} with "
            f"{len(candidates)} retrieved historical defect(s)."
        )
        self.logger.info(
            "Root cause analysis completed",
            extra={"agent": "RootCause", "confidence": confidence},
        )
        return RootCauseResult(
            root_cause=root_cause,
            confidence=confidence,
            reasoning=reasoning,
            supporting_evidence=evidence,
            matched_bug_ids=matched_ids,
        )

    @staticmethod
    def _cause_from_resolution(resolution: str, exception: str | None, component: str | None) -> str:
        """Turn a recorded fix into a conservative causal statement."""
        prefix = f"The {component} failure" if component else "The failure"
        exception_text = f" producing {exception}" if exception else ""
        return (
            f"{prefix}{exception_text} is consistent with the condition "
            f"addressed by this historical fix: {resolution}"
        )

    @staticmethod
    def _evidence(
        candidates: list[dict[str, Any]],
        exception: str | None,
        component: str | None,
    ) -> list[EvidenceItem]:
        evidence: list[EvidenceItem] = []
        for candidate in candidates:
            bug_id = str(candidate.get("bug_id") or candidate.get("issue_id") or "Unknown")
            similarity = round(normalized_similarity(candidate) * 100)
            details = list(candidate.get("match_reasons") or [])
            recorded = candidate.get("root_cause") or candidate.get("resolution")
            if recorded:
                details.append(f"Recorded evidence: {str(recorded)[:300]}")
            text = diagnostic_text(candidate).lower()
            if exception and exception.lower() in text:
                details.append(f"Exception match: {exception}")
            if component and component.lower() in text:
                details.append(f"Component match: {component}")
            evidence.append(
                EvidenceItem(
                    source="Historical defect knowledge base",
                    bug_id=bug_id,
                    detail="; ".join(dict.fromkeys(details)) or "Retrieved by semantic similarity.",
                    similarity=similarity,
                )
            )
        return evidence


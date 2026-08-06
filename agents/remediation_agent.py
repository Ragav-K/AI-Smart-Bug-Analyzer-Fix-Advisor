"""Grounded repair recommendations derived from historical resolutions."""

from __future__ import annotations

import re
from typing import Any

from models.analysis_models import RemediationResult
from utils.logging_config import get_agent_logger
from utils.scoring import normalized_similarity


class RemediationAgent:
    """Convert root-cause evidence and resolved duplicates into repair steps."""

    def __init__(self) -> None:
        self.logger = get_agent_logger(__name__)

    def predict(self, context: dict[str, Any]) -> RemediationResult:
        """Generate a recommendation only when retrieved evidence supports it."""
        root_cause = context.get("root_cause") or {}
        duplicate_result = context.get("duplicate_detection") or {}
        candidates = list(context.get("retrieved_bugs") or [])
        resolved = self._resolved_candidates(candidates, duplicate_result)
        log_analysis = context.get("log_analysis") or {}
        files = self._files(log_analysis)
        evidence_ids = [
            str(item.get("bug_id") or item.get("issue_id"))
            for item in resolved
            if item.get("bug_id") or item.get("issue_id")
        ][:5]

        if not resolved:
            # Issue-tracker exports record a workflow status, not a description
            # of the repair, so a historical fix is frequently unavailable.
            # Fall back to the diagnostics that were established for this
            # failure, clearly marked as inference rather than proven evidence.
            result = self._diagnostic_remediation(log_analysis, root_cause, files)
        else:
            resolution = str(resolved[0].get("resolution")).strip()
            result = RemediationResult(
                basis="historical",
                recommended_fix=resolution,
                steps=self._steps(resolution, root_cause.get("root_cause"), files),
                files_likely_affected=files,
                historical_resolution=(
                    f"{evidence_ids[0] if evidence_ids else 'Historical match'}: {resolution}"
                ),
                best_practice=self._best_practice(resolution),
                confidence=min(
                    95,
                    round(
                        int(root_cause.get("confidence") or 0) * 0.55
                        + normalized_similarity(resolved[0]) * 100 * 0.45
                    ),
                ),
                evidence_bug_ids=evidence_ids,
            )
        self.logger.info(
            "Remediation completed",
            extra={"agent": "Remediation", "confidence": result.confidence},
        )
        return result

    # Conservative repair patterns keyed by exception family. These describe
    # the standard engineering response to a failure mode; they are not drawn
    # from any specific historical defect, which is why the result is labelled
    # "diagnostic" and capped well below a historically grounded confidence.
    DIAGNOSTIC_PATTERNS: dict[str, tuple[str, str]] = {
        "NullPointerException": (
            "Guard the dereferenced reference before use and return or raise a domain error when it is absent.",
            "Validate nullable values at the component boundary rather than at the point of use.",
        ),
        "AttributeError": (
            "Confirm the object is the expected type and is initialized before the attribute is accessed.",
            "Validate nullable values at the component boundary rather than at the point of use.",
        ),
        "KeyError": (
            "Replace the direct mapping lookup with a guarded lookup and handle the missing key explicitly.",
            "Treat every external payload field as optional until it has been validated.",
        ),
        "IndexError": (
            "Check the sequence length before indexing and handle the empty or short case explicitly.",
            "Prefer iteration or bounded access over positional indexing on caller-supplied data.",
        ),
        "TypeError": (
            "Normalize or validate the operand types before the failing operation.",
            "Validate types at the component boundary and cover the mixed-type path with a test.",
        ),
        "ValueError": (
            "Validate the input format and range before conversion, and reject invalid input with a clear message.",
            "Parse and validate external input once, at the edge of the system.",
        ),
        "TimeoutError": (
            "Apply an explicit timeout with bounded retries and a defined failure path for the dependency.",
            "Give every outbound call an explicit timeout, bounded retries, and observable failure handling.",
        ),
        "IOException": (
            "Verify the path, permissions, and connectivity, and handle the failure without leaking the resource.",
            "Release resources deterministically and surface I/O failures with actionable context.",
        ),
        "SQLException": (
            "Inspect the failing query, connection lifetime, and transaction boundary, and release connections on error.",
            "Size the connection pool for peak load and fail fast when the database is unavailable.",
        ),
        "ReferenceError": (
            "Define or import the referenced identifier before use and verify the module load order.",
            "Enable static analysis so undefined identifiers are caught before release.",
        ),
        "RecursionError": (
            "Add a base case or convert the recursion to iteration to bound the call depth.",
            "Bound recursion depth explicitly and test the terminating condition.",
        ),
    }

    def _diagnostic_remediation(
        self,
        log_analysis: dict[str, Any],
        root_cause: dict[str, Any],
        files: list[str],
    ) -> RemediationResult:
        """Recommend a repair from current diagnostics when history is silent."""
        root = str(log_analysis.get("root_exception") or "").strip()
        thrown = str(log_analysis.get("exception_type") or "").strip()
        exception = root or thrown
        failure_point = str(log_analysis.get("failure_point") or "").strip()
        cause = self._usable_cause(root_cause, log_analysis)
        # A Java "Caused by:" root is often a generic wrapper such as
        # IllegalStateException, so fall back to the exception that surfaced.
        pattern, best_practice = next(
            (
                self.DIAGNOSTIC_PATTERNS[name]
                for name in (root, thrown)
                if name in self.DIAGNOSTIC_PATTERNS
            ),
            ("", ""),
        )

        if not pattern and not cause:
            # Nothing was established about the failure at all.
            return RemediationResult(
                basis="none",
                recommended_fix="No evidence-backed code change can be recommended from the retrieved defects.",
                steps=[
                    "Reproduce the failure with diagnostic logging enabled.",
                    "Capture the failing inputs and a complete stack trace.",
                    "Add the verified resolution to the historical defect knowledge base before automating a fix.",
                ],
                files_likely_affected=files,
                historical_resolution="No retrieved historical defect contains a recorded resolution.",
                best_practice="Require a traceable defect or engineering reference before applying an automated recommendation.",
                confidence=min(35, int(root_cause.get("confidence") or 0)),
                evidence_bug_ids=[],
            )

        location = f" at {failure_point}" if failure_point and "Unable to determine" not in failure_point else ""
        recommendation = pattern or f"Address the established root cause{location}: {cause[:240]}"

        steps = [
            f"Reproduce the {exception or 'reported'} failure{location} with diagnostic logging enabled.",
            recommendation,
        ]
        if files:
            steps.append(f"Apply and review the change in {files[0]}.")
        steps.append("Add a regression test that fails on the current behaviour and passes after the change.")
        steps.append("Run the affected component's unit and integration tests, then verify the original reproduction steps.")

        return RemediationResult(
            basis="diagnostic",
            recommended_fix=recommendation,
            steps=steps,
            files_likely_affected=files,
            historical_resolution=(
                "No retrieved historical defect recorded a resolution. This recommendation "
                "is inferred from the current exception and root cause, not from a past fix."
            ),
            best_practice=best_practice
            or "Turn the confirmed root cause into a regression test and a code-review checklist item.",
            confidence=self._diagnostic_confidence(log_analysis, root_cause, bool(pattern)),
            evidence_bug_ids=[],
        )

    @staticmethod
    def _usable_cause(root_cause: dict[str, Any], log_analysis: dict[str, Any]) -> str:
        """Return a cause only when one was actually established.

        The upstream agents emit a sentence when they could not determine
        anything. Echoing that back as "address this root cause" would be
        incoherent, so those sentinels are treated as absent.
        """
        sentinels = ("insufficient grounded evidence", "insufficient log context")
        for value in (root_cause.get("root_cause"), log_analysis.get("probable_cause")):
            text = str(value or "").strip()
            if text and not text.lower().startswith(sentinels):
                return text
        return ""

    @staticmethod
    def _diagnostic_confidence(
        log_analysis: dict[str, Any],
        root_cause: dict[str, Any],
        recognized_exception: bool,
    ) -> int:
        """Keep diagnostic confidence clearly below a historically grounded one."""
        log_confidence = int(log_analysis.get("confidence") or 0)
        cause_confidence = int(root_cause.get("confidence") or 0)
        score = log_confidence * 0.35 + cause_confidence * 0.2 + (12 if recognized_exception else 0)
        return max(0, min(55, round(score)))

    @staticmethod
    def _resolved_candidates(
        candidates: list[dict[str, Any]], duplicate_result: dict[str, Any]
    ) -> list[dict[str, Any]]:
        duplicate_ids = {
            str(item.get("bug_id"))
            for item in duplicate_result.get("duplicates") or []
            if item.get("bug_id")
        }
        resolved = [
            item
            for item in candidates
            if str(item.get("resolution") or "").strip()
            and (
                not duplicate_ids
                or str(item.get("bug_id") or item.get("issue_id")) in duplicate_ids
            )
        ]
        return sorted(
            resolved,
            key=lambda item: float(item.get("similarity") or 0),
            reverse=True,
        )

    @staticmethod
    def _files(log_analysis: dict[str, Any]) -> list[str]:
        values = [log_analysis.get("file")]
        values.extend(
            frame.get("file")
            for frame in log_analysis.get("call_stack") or []
            if isinstance(frame, dict)
        )
        return list(dict.fromkeys(str(value) for value in values if value))[:8]

    @staticmethod
    def _steps(resolution: str, root_cause: Any, files: list[str]) -> list[str]:
        target = f" in {files[0]}" if files else ""
        return [
            f"Reproduce and confirm the grounded root cause{target}: {str(root_cause)[:240]}",
            f"Apply the historical corrective pattern: {resolution[:300]}",
            "Run the affected component's unit and integration tests.",
            "Verify the original reproduction steps and monitor for recurrence.",
        ]

    @staticmethod
    def _best_practice(resolution: str) -> str:
        lowered = resolution.lower()
        if re.search(r"\b(null|none|nil|validation|validate)\b", lowered):
            return "Validate nullable inputs at component boundaries and cover the failure path with regression tests."
        if re.search(r"\b(timeout|retry|connection)\b", lowered):
            return "Use bounded retries, explicit timeouts, and observable failure handling for external dependencies."
        if re.search(r"\b(version|upgrade|dependency)\b", lowered):
            return "Pin compatible dependency versions and test upgrades in continuous integration."
        return "Turn the verified historical resolution into a focused regression test and code-review checklist item."

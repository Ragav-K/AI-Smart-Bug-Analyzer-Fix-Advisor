"""Fault-isolated orchestration of the complete bug-analysis pipeline."""

from __future__ import annotations

import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from agents.duplicate_agent import DuplicateDetectionAgent
from agents.log_analysis_agent import LogAnalysisAgent
from agents.remediation_agent import RemediationAgent
from agents.root_cause_agent import RootCauseAgent
from agents.triage_agent import TriageAgent
from utils.logging_config import get_agent_logger
from utils.rag_search import search_similar_bugs


def _dump(model: Any) -> dict[str, Any]:
    method = getattr(model, "model_dump", None)
    return method(mode="json") if method else model.dict()


class BugAnalysisOrchestrator:
    """Execute single-responsibility agents and share one retrieval context."""

    def __init__(
        self,
        triage_agent: TriageAgent | None = None,
        log_analysis_agent: LogAnalysisAgent | None = None,
        root_cause_agent: RootCauseAgent | None = None,
        duplicate_agent: DuplicateDetectionAgent | None = None,
        remediation_agent: RemediationAgent | None = None,
        retriever: Callable[[str, int], list[dict[str, Any]]] | None = None,
        result_store: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        self.triage_agent = triage_agent or TriageAgent()
        self.log_analysis_agent = log_analysis_agent or LogAnalysisAgent()
        self.root_cause_agent = root_cause_agent or RootCauseAgent()
        self.duplicate_agent = duplicate_agent or DuplicateDetectionAgent()
        self.remediation_agent = remediation_agent or RemediationAgent()
        self.retriever = retriever or (
            lambda query, limit: search_similar_bugs(
                query,
                limit=limit,
                timeout_seconds=2.5,
            )
        )
        self.result_store = result_store
        self.logger = get_agent_logger(__name__)

    def analyze(self, submission: dict[str, Any] | str, submission_id: str | None = None) -> dict[str, Any]:
        """Run the ordered pipeline with fault isolation at each agent boundary."""
        started = time.perf_counter()
        submitted_id = submission.get("submission_id") if isinstance(submission, dict) else None
        identifier = submission_id or submitted_id or "UNSAVED"
        output: dict[str, Any] = {
            "submission_id": identifier,
            "timestamp": datetime.now(UTC).isoformat(),
            "triage": None,
            "log_analysis": None,
            "root_cause": None,
            "duplicate_detection": None,
            "remediation": None,
            "overall_confidence": 0,
            "metadata": {
                "agents_executed": [],
                "agent_errors": {},
                "schema_version": "3.0",
                "retrieval_count": 0,
                "retrieval_reused": False,
            },
        }

        self._execute("LogAnalysis", "log_analysis", self.log_analysis_agent, submission, output)
        self._execute("Triage", "triage", self.triage_agent, submission, output)

        retrieved = self._retrieve_once(submission, output)
        context: dict[str, Any] = {
            "submission": submission,
            "triage": output["triage"],
            "log_analysis": output["log_analysis"],
            "retrieved_bugs": retrieved,
        }
        self._execute("RootCause", "root_cause", self.root_cause_agent, context, output)
        context["root_cause"] = output["root_cause"]
        self._execute(
            "DuplicateDetection",
            "duplicate_detection",
            self.duplicate_agent,
            context,
            output,
        )
        context["duplicate_detection"] = output["duplicate_detection"]
        self._execute("Remediation", "remediation", self.remediation_agent, context, output)

        output["overall_confidence"] = self._overall_confidence(output)
        elapsed = time.perf_counter() - started
        output["metadata"]["processing_time_seconds"] = round(elapsed, 4)
        output["metadata"]["future_agent_context"] = {
            "submission_id": identifier,
            "triage": output["triage"],
            "log_analysis": output["log_analysis"],
            "root_cause": output["root_cause"],
            "duplicate_detection": output["duplicate_detection"],
            "remediation": output["remediation"],
        }
        if self.result_store:
            try:
                self.result_store(output)
            except Exception:
                self.logger.exception("Analysis result persistence failed", extra={"submission_id": identifier})
                output["metadata"]["storage_warning"] = "Analysis completed but result persistence failed."
        self.logger.info(
            "Orchestration completed",
            extra={"processing_time_ms": round(elapsed * 1000, 2), "submission_id": identifier},
        )
        return output

    def predict(self, submission: dict[str, Any] | str, submission_id: str | None = None) -> dict[str, Any]:
        """Alias supporting a common interface for agent pipelines."""
        return self.analyze(submission, submission_id)

    def _execute(
        self,
        name: str,
        key: str,
        agent: Any,
        payload: Any,
        output: dict[str, Any],
    ) -> None:
        """Execute one agent and record a structured, isolated failure."""
        try:
            output[key] = _dump(agent.predict(payload))
            output["metadata"]["agents_executed"].append(name)
        except Exception as exc:  # fault isolation is intentional at this boundary
            output["metadata"]["agent_errors"][name] = f"{type(exc).__name__}: {exc}"
            self.logger.exception(
                "Agent execution failed",
                extra={"agent": name, "submission_id": output["submission_id"]},
            )

    def _retrieve_once(
        self,
        submission: dict[str, Any] | str,
        output: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Reuse submission search results or perform exactly one top-10 search."""
        if isinstance(submission, dict) and "similar_bugs" in submission:
            matches = list(submission.get("similar_bugs") or [])[:10]
            output["metadata"]["retrieval_reused"] = True
        else:
            query = self._retrieval_query(submission)
            try:
                matches = self.retriever(query, 10) if query.strip() else []
            except Exception as exc:
                matches = []
                output["metadata"]["agent_errors"]["Retrieval"] = f"{type(exc).__name__}: {exc}"
                self.logger.exception(
                    "Historical retrieval failed",
                    extra={"submission_id": output["submission_id"]},
                )
        output["metadata"]["retrieval_count"] = len(matches)
        return matches

    # A stack trace carries the identifiers that make a historical defect
    # findable, so a query built without it retrieves far less. The web form
    # always supplies ``submitted_text``, which already merges every field, but
    # a record assembled programmatically may not -- end-to-end validation
    # measured the same defect matching its duplicate when submitted as plain
    # text and missing it when submitted as a record whose trace lived only in
    # ``log_text``.
    QUERY_FIELDS = ("bug_title", "bug_description", "steps_to_reproduce", "actual_result", "log_text")
    MAX_QUERY_CHARS = 20_000

    @classmethod
    def _retrieval_query(cls, submission: dict[str, Any] | str) -> str:
        """Build the retrieval query from every available description of the failure."""
        if not isinstance(submission, dict):
            return str(submission or "")
        submitted_text = str(submission.get("submitted_text") or "").strip()
        if submitted_text:
            return submitted_text[: cls.MAX_QUERY_CHARS]
        parts: list[str] = []
        for key in cls.QUERY_FIELDS:
            value = str(submission.get(key) or "").strip()
            if value and not any(value in seen for seen in parts):
                parts.append(value)
        return "\n".join(parts)[: cls.MAX_QUERY_CHARS]

    @staticmethod
    def _overall_confidence(output: dict[str, Any]) -> int:
        """Aggregate available agent confidence without treating absence as certainty.

        Only agent confidence percentages are averaged. A duplicate's
        similarity score answers a different question -- how alike two defects
        are -- so averaging it in would conflate two different units.
        """
        values: list[int] = []
        for key in ("triage", "log_analysis", "root_cause", "remediation"):
            result = output.get(key) or {}
            if "confidence" in result:
                values.append(int(result["confidence"]))
        return round(sum(values) / len(values)) if values else 0

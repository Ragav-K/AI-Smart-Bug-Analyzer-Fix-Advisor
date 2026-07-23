"""Fault-isolated orchestration of current and future bug-analysis agents."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Callable

from agents.log_analysis_agent import LogAnalysisAgent
from agents.triage_agent import TriageAgent
from utils.logging_config import get_agent_logger


def _dump(model: Any) -> dict[str, Any]:
    method = getattr(model, "model_dump", None)
    return method(mode="json") if method else model.dict()


class BugAnalysisOrchestrator:
    """Execute agents independently and emit a stable future-agent context."""

    def __init__(
        self,
        triage_agent: TriageAgent | None = None,
        log_analysis_agent: LogAnalysisAgent | None = None,
        result_store: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        self.triage_agent = triage_agent or TriageAgent()
        self.log_analysis_agent = log_analysis_agent or LogAnalysisAgent()
        self.result_store = result_store
        self.logger = get_agent_logger(__name__)

    def analyze(self, submission: dict[str, Any] | str, submission_id: str | None = None) -> dict[str, Any]:
        started = time.perf_counter()
        identifier = submission_id or (submission.get("submission_id") if isinstance(submission, dict) else None) or "UNSAVED"
        output: dict[str, Any] = {
            "submission_id": identifier,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "triage": None,
            "log_analysis": None,
            "metadata": {"agents_executed": [], "agent_errors": {}, "schema_version": "2.0"},
        }
        for name, key, agent in (
            ("Triage", "triage", self.triage_agent),
            ("LogAnalysis", "log_analysis", self.log_analysis_agent),
        ):
            try:
                output[key] = _dump(agent.predict(submission))
                output["metadata"]["agents_executed"].append(name)
            except Exception as exc:  # fault isolation is intentional at this boundary
                output["metadata"]["agent_errors"][name] = f"{type(exc).__name__}: {exc}"
                self.logger.exception("Agent execution failed", extra={"agent": name, "submission_id": identifier})
        elapsed = time.perf_counter() - started
        output["metadata"]["processing_time_seconds"] = round(elapsed, 4)
        output["metadata"]["future_agent_context"] = {
            "submission_id": identifier,
            "triage": output["triage"],
            "log_analysis": output["log_analysis"],
        }
        if self.result_store:
            try:
                self.result_store(output)
            except Exception:
                self.logger.exception("Analysis result persistence failed", extra={"submission_id": identifier})
                output["metadata"]["storage_warning"] = "Analysis completed but result persistence failed."
        self.logger.info("Orchestration completed", extra={"processing_time_ms": round(elapsed * 1000, 2), "submission_id": identifier})
        return output

    def predict(self, submission: dict[str, Any] | str, submission_id: str | None = None) -> dict[str, Any]:
        """Alias supporting a common interface for agent pipelines."""
        return self.analyze(submission, submission_id)


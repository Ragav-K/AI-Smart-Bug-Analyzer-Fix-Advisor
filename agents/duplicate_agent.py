"""Semantic duplicate detection with diagnostic re-ranking."""

from __future__ import annotations

from typing import Any

from models.analysis_models import DuplicateMatch, DuplicateResult
from utils.logging_config import get_agent_logger
from utils.rag_search import FALLBACK_MODEL_NAME
from utils.scoring import rerank_duplicate


class DuplicateDetectionAgent:
    """Return only high-confidence duplicates from shared RAG candidates."""

    # The two retrieval backends produce different score distributions, so a
    # single threshold would make this agent permanently silent on the
    # fallback path. Measured against the GitBugs corpus, the token matcher
    # scores a true duplicate at ~61 and a merely topical match at ~28, so 45
    # separates them; embedding similarity is far better scaled and keeps 65.
    SEMANTIC_THRESHOLD = 65
    FALLBACK_THRESHOLD = 45

    def __init__(self, threshold: int | None = None, max_results: int = 5) -> None:
        self.threshold = threshold
        self.max_results = max_results
        self.logger = get_agent_logger(__name__)

    def threshold_for(self, candidates: list[dict[str, Any]]) -> int:
        """Choose the score floor that matches the backend that retrieved these."""
        if self.threshold is not None:
            return self.threshold
        backends = {str(candidate.get("search_backend") or "") for candidate in candidates}
        if backends and backends <= {FALLBACK_MODEL_NAME}:
            return self.FALLBACK_THRESHOLD
        return self.SEMANTIC_THRESHOLD

    def predict(self, context: dict[str, Any]) -> DuplicateResult:
        """Re-rank up to ten retrieved bugs without issuing another search."""
        candidates = list(context.get("retrieved_bugs") or [])[:10]
        triage = context.get("triage") or {}
        log_analysis = context.get("log_analysis") or {}
        threshold = self.threshold_for(candidates)
        ranked: list[tuple[int, dict[str, Any], list[str]]] = []
        for candidate in candidates:
            score, reasons = rerank_duplicate(
                candidate,
                log_analysis.get("root_exception") or log_analysis.get("exception_type"),
                triage.get("component"),
                triage.get("severity"),
            )
            if score >= threshold:
                ranked.append((score, candidate, reasons))
        ranked.sort(key=lambda item: item[0], reverse=True)
        duplicates = [
            DuplicateMatch(
                bug_id=str(item.get("bug_id") or item.get("issue_id") or "Unknown"),
                similarity=score,
                status=str(item.get("status") or "Unknown"),
                summary=str(item.get("title") or item.get("summary") or "Untitled historical bug"),
                resolution=str(item.get("resolution") or "No historical resolution recorded."),
                match_reasons=reasons,
            )
            for score, item, reasons in ranked[: self.max_results]
        ]
        self.logger.info(
            "Duplicate detection completed",
            extra={"agent": "DuplicateDetection", "confidence": duplicates[0].similarity if duplicates else 0},
        )
        return DuplicateResult(
            duplicates=duplicates,
            candidates_evaluated=len(candidates),
            threshold=threshold,
        )


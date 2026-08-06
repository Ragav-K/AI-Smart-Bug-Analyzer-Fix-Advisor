"""Structured contracts for the Milestone 3 analysis agents."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class EvidenceItem(BaseModel):
    """A traceable statement supporting an analysis conclusion."""

    source: str
    bug_id: str | None = None
    detail: str
    similarity: int | None = Field(default=None, ge=0, le=100)


class RootCauseResult(BaseModel):
    """Grounded explanation of why the submitted failure occurred."""

    root_cause: str
    confidence: int = Field(ge=0, le=100)
    reasoning: str
    supporting_evidence: list[EvidenceItem] = Field(default_factory=list)
    matched_bug_ids: list[str] = Field(default_factory=list)


class DuplicateMatch(BaseModel):
    """A high-confidence historical duplicate."""

    bug_id: str
    similarity: int = Field(ge=0, le=100)
    status: str = "Unknown"
    summary: str
    resolution: str = "No historical resolution recorded."
    match_reasons: list[str] = Field(default_factory=list)


class DuplicateResult(BaseModel):
    """Ranked duplicate-detection response."""

    duplicates: list[DuplicateMatch] = Field(default_factory=list)
    candidates_evaluated: int = Field(default=0, ge=0)
    threshold: int = Field(default=65, ge=0, le=100)


class RemediationResult(BaseModel):
    """Actionable remediation grounded in retrieved historical evidence.

    ``basis`` states where the recommendation came from, so a reader can never
    mistake a diagnostic inference for a historically proven fix:

    - ``historical``: taken from the recorded resolution of a retrieved defect
    - ``diagnostic``: inferred from the current exception and root cause only
    - ``none``: neither source carried enough signal to recommend anything
    """

    basis: Literal["historical", "diagnostic", "none"] = "historical"
    recommended_fix: str
    steps: list[str] = Field(default_factory=list)
    files_likely_affected: list[str] = Field(default_factory=list)
    historical_resolution: str
    best_practice: str
    confidence: int = Field(ge=0, le=100)
    evidence_bug_ids: list[str] = Field(default_factory=list)


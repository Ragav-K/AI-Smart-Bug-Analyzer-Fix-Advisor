"""Pydantic contracts produced by the triage agent."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class TriageResult(BaseModel):
    """Professional issue-tracker fields inferred from a bug report.

    Priority uses the P0-P3 scale rather than the P1-P4 scale named in the
    milestone brief. P0 is reserved for a Critical defect that is also
    customer-facing or production-breaking, which is the distinction the
    triage rules actually make; a fourth "someday" band would never be
    assigned by those rules. Severity remains Critical/High/Medium/Low.
    """

    severity: Literal["Critical", "High", "Medium", "Low"]
    priority: Literal["P0", "P1", "P2", "P3"]
    component: str = "Other"
    business_impact: str
    confidence: int = Field(ge=0, le=100)
    reasoning: str
    evidence: list[str] = Field(default_factory=list)


"""Pydantic contracts produced by the triage agent."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class TriageResult(BaseModel):
    """Professional issue-tracker fields inferred from a bug report."""

    severity: Literal["Critical", "High", "Medium", "Low"]
    priority: Literal["P0", "P1", "P2", "P3"]
    component: str = "Other"
    business_impact: str
    confidence: int = Field(ge=0, le=100)
    reasoning: str
    evidence: list[str] = Field(default_factory=list)


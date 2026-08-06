"""Structured contracts for the Milestone 4 defect pattern analytics module."""

from __future__ import annotations

from pydantic import BaseModel, Field


class DefectTheme(BaseModel):
    """A recurring failure signature observed across submitted defects.

    A theme is deliberately keyed on the pair (root exception, affected
    component) rather than on free text. Two reports written by different
    people describe the same failure very differently, but the pair the
    pipeline extracted for them is directly comparable.
    """

    theme: str
    exception: str = "Unclassified"
    component: str = "Other"
    occurrences: int = Field(ge=1)
    share_percentage: int = Field(ge=0, le=100)
    first_seen: str | None = None
    last_seen: str | None = None
    example_submission_ids: list[str] = Field(default_factory=list)


class ComponentHotspot(BaseModel):
    """A product component carrying a disproportionate share of defects."""

    component: str
    defect_count: int = Field(ge=1)
    share_percentage: int = Field(ge=0, le=100)
    high_impact_count: int = Field(default=0, ge=0)
    top_exceptions: list[str] = Field(default_factory=list)
    example_submission_ids: list[str] = Field(default_factory=list)


class SystemicPattern(BaseModel):
    """A cross-cutting issue inferred from many defects rather than one.

    ``evidence`` lists the observations that triggered the rule, so a reader
    can always check the conclusion against the underlying submissions.
    """

    pattern_id: str
    title: str
    detail: str
    affected_submissions: int = Field(ge=0)
    evidence: list[str] = Field(default_factory=list)
    recommendation: str


class DefectAnalyticsResult(BaseModel):
    """Portfolio-level view of every analyzed defect submission."""

    generated_at: str
    submissions_analyzed: int = Field(default=0, ge=0)
    submissions_with_pipeline_output: int = Field(default=0, ge=0)
    recurrence_rate: int = Field(default=0, ge=0, le=100)
    themes: list[DefectTheme] = Field(default_factory=list)
    component_hotspots: list[ComponentHotspot] = Field(default_factory=list)
    systemic_patterns: list[SystemicPattern] = Field(default_factory=list)
    severity_distribution: dict[str, int] = Field(default_factory=dict)
    priority_distribution: dict[str, int] = Field(default_factory=dict)
    exception_distribution: dict[str, int] = Field(default_factory=dict)
    remediation_basis_distribution: dict[str, int] = Field(default_factory=dict)
    duplicate_rate: int = Field(default=0, ge=0, le=100)
    knowledge_base_entries: int = Field(default=0, ge=0)
    notes: list[str] = Field(default_factory=list)

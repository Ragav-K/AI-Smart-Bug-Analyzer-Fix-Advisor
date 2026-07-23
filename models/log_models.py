"""Pydantic contracts produced by the log analysis agent."""

from __future__ import annotations

from pydantic import BaseModel, Field


class StackFrame(BaseModel):
    """A normalized frame from any supported stack-trace language."""

    file: str | None = None
    line: int | None = None
    function: str | None = None
    raw: str = ""


class LogAnalysisResult(BaseModel):
    """Language-neutral structured interpretation of an error log."""

    language: str = "Unknown"
    exception_type: str | None = None
    error_message: str | None = None
    root_exception: str | None = None
    file: str | None = None
    line: int | None = None
    function: str | None = None
    method: str | None = None
    module: str | None = None
    package: str | None = None
    failure_point: str = "Unable to determine from the supplied log"
    call_stack: list[StackFrame] = Field(default_factory=list)
    call_stack_summary: list[str] = Field(default_factory=list)
    probable_cause: str = "Insufficient log context to infer a probable cause."
    probable_module: str = "Other"
    confidence: int = Field(ge=0, le=100)
    warnings: list[str] = Field(default_factory=list)


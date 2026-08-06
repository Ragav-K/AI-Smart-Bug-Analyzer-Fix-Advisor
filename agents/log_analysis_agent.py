"""Language-neutral log interpretation agent."""

from __future__ import annotations

from typing import Any

from models.log_models import LogAnalysisResult, StackFrame
from utils.component_classifier import classify_component
from utils.confidence import bounded_confidence
from utils.logging_config import get_agent_logger
from utils.parser import module_from_path, parse_log

CAUSE_HINTS = {
    "NullPointerException": "An object is null before it is dereferenced; validate initialization and input guards.",
    "TypeError": "A value has an unexpected type or an operation received incompatible operands.",
    "ValueError": "A function received a value outside the expected format or range.",
    "KeyError": "A required mapping key is absent; validate input fields or use a guarded lookup.",
    "AttributeError": "The object is missing the requested attribute, often because it is null or the wrong type.",
    "ModuleNotFoundError": "A required dependency or import path is missing from the runtime environment.",
    "ImportError": "A module or symbol could not be imported; verify dependency versions and paths.",
    "SQLException": "A database operation failed; inspect the query, connection, and transaction state.",
    "IOException": "An input/output operation failed; verify paths, permissions, connectivity, and resource state.",
    "ReferenceError": "Code referenced an identifier that is not defined in the current JavaScript scope.",
    "SyntaxError": "The runtime could not parse the source or structured input.",
    "RangeError": "A value exceeded the valid JavaScript range or recursion depth.",
}


# Ordered from the most specific log source to the broadest. The first group
# that yields any content is the one analyzed.
# ``submitted_text`` is the retrieval query, built by concatenating the form
# fields, so it is used only when the individual fields are unavailable.
SOURCE_PRECEDENCE = (
    ("log_text", "stack_trace"),
    ("bug_description", "actual_result"),
    ("submitted_text",),
)


class LogAnalysisAgent:
    def __init__(self) -> None:
        self.logger = get_agent_logger(__name__)
        self.initialized = False
        self.initialize()

    def initialize(self) -> None:
        self.initialized = True

    def preprocess(self, log: str | dict[str, Any] | None) -> str:
        """Select the most specific log source rather than concatenating all.

        These fields overlap: ``submitted_text`` is assembled from the form
        fields, and users routinely paste the same trace into both the
        description and the actual result. Concatenating every source fed the
        same stack trace to the parser several times, which reported phantom
        repeated frames and an inflated frame count.
        """
        if not isinstance(log, dict):
            return str(log or "")
        for group in SOURCE_PRECEDENCE:
            collected: list[str] = []
            for key in group:
                part = str(log.get(key) or "").strip()
                # Skip a source already represented by one that was collected.
                if not part or any(part in seen for seen in collected):
                    continue
                collected = [seen for seen in collected if seen not in part]
                collected.append(part)
            if collected:
                return "\n".join(collected)
        return ""

    @staticmethod
    def _failure_frame(parsed: Any) -> dict[str, Any]:
        """Return the frame that best identifies where the failure happened.

        Python prints the innermost call last, so the final frame is the one
        that raised. Java and JavaScript print it first. Picking the wrong end
        would name the entry point instead of the failing code.
        """
        if not parsed.frames:
            return {}
        return parsed.frames[-1] if parsed.language == "Python" else parsed.frames[0]

    def predict(self, log: str | dict[str, Any] | None) -> LogAnalysisResult:
        text = self.preprocess(log)
        parsed = parse_log(text)
        failure_frame = self._failure_frame(parsed)
        file_name = failure_frame.get("file")
        function = failure_frame.get("function")
        module, package = module_from_path(file_name)
        probable_module, _, component_strength = classify_component(
            " ".join(filter(None, [text, file_name, module]))
        )
        exception = parsed.root_exception or parsed.exception_type
        signal_count = sum((
            bool(exception),
            bool(parsed.error_message),
            bool(file_name),
            bool(function),
            bool(parsed.frames),
        ))
        confidence = bounded_confidence(
            48,
            signal_count + min(component_strength, 2),
            int(parsed.language == "Unknown"),
        )
        if not text.strip():
            confidence = 5
        frames = [
            StackFrame(
                file=frame.get("file"),
                line=frame.get("line"),
                function=frame.get("function"),
                raw=frame.get("raw", ""),
            )
            for frame in parsed.frames
        ]
        result = LogAnalysisResult(
            language=parsed.language,
            exception_type=parsed.exception_type,
            error_message=parsed.error_message,
            root_exception=parsed.root_exception,
            file=file_name,
            line=failure_frame.get("line"),
            function=function,
            method=function,
            module=module,
            package=package,
            failure_point=self._failure_point(module, function, file_name),
            call_stack=frames,
            call_stack_summary=self._summarize(frames),
            probable_cause=self._probable_cause(parsed.root_exception, parsed.exception_type, parsed.error_message),
            probable_module=probable_module,
            confidence=confidence,
            warnings=parsed.warnings,
        )
        self.logger.info("Log analysis completed", extra={"agent": "LogAnalysis", "confidence": confidence})
        return result

    @staticmethod
    def _failure_point(module: str | None, function: str | None, file_name: str | None) -> str:
        if function and file_name:
            return f"{function} in {file_name}"
        return function or file_name or module or "Unable to determine from the supplied log"

    @staticmethod
    def _summarize(frames: list[StackFrame]) -> list[str]:
        if not frames:
            return ["No complete call stack was available."]
        selected = frames if len(frames) <= 4 else [frames[0], *frames[-3:]]
        summaries = []
        for frame in selected:
            location = f"{frame.file}:{frame.line}" if frame.file and frame.line else frame.file or "unknown source"
            summaries.append(f"{frame.function or '<anonymous>'} at {location}")
        return summaries

    @classmethod
    def _probable_cause(
        cls,
        root_exception: str | None,
        thrown_exception: str | None,
        message: str | None,
    ) -> str:
        """Explain the deepest known cause, falling back to what surfaced."""
        for candidate in (root_exception, thrown_exception):
            hint = CAUSE_HINTS.get(candidate or "")
            if hint:
                return hint
        return cls._fallback_cause(message)

    @staticmethod
    def _fallback_cause(message: str | None) -> str:
        if message:
            return f"The failure is associated with: {message[:240]}"
        return "Insufficient log context to infer a probable cause."


"""Reusable, bounded parsers for common stack trace formats."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from utils.language_detector import detect_language


MAX_LOG_CHARS = 1_000_000
MAX_FRAMES = 200


@dataclass(slots=True)
class ParsedLog:
    language: str = "Unknown"
    exception_type: str | None = None
    error_message: str | None = None
    root_exception: str | None = None
    frames: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


PYTHON_FRAME = re.compile(r'^\s*File "(?P<file>[^"]+)", line (?P<line>\d+), in (?P<function>.+?)\s*$', re.MULTILINE)
PYTHON_EXCEPTION = re.compile(r"^\s*(?P<type>[A-Za-z_][\w.]*(?:Error|Exception))(?::\s*(?P<message>.*))?\s*$", re.MULTILINE)
JAVA_FRAME = re.compile(r"^\s*at\s+(?P<qualified>[\w.$<>]+)\((?P<file>[^():]+)(?::(?P<line>\d+))?\)\s*$", re.MULTILINE)
JAVA_EXCEPTION = re.compile(r"^\s*(?:Caused by:\s*)?(?P<type>[\w.$]+(?:Exception|Error))(?::\s*(?P<message>.*))?\s*$", re.MULTILINE)
JS_FRAME_PAREN = re.compile(r"^\s*at\s+(?P<function>.*?)\s+\((?P<file>(?:[A-Za-z]:)?[^()]+?\.(?:js|ts|jsx|tsx)):(?P<line>\d+):\d+\)\s*$", re.MULTILINE)
JS_FRAME_BARE = re.compile(r"^\s*at\s+(?P<file>(?:[A-Za-z]:)?\S+?\.(?:js|ts|jsx|tsx)):(?P<line>\d+):\d+\s*$", re.MULTILINE)
JS_EXCEPTION = re.compile(r"^\s*(?:Uncaught\s+)?(?P<type>ReferenceError|SyntaxError|TypeError|RangeError|Error)(?::\s*(?P<message>.*))?\s*$", re.MULTILINE)
GENERIC_EXCEPTION = re.compile(r"(?P<type>[A-Za-z_][\w.]*(?:Exception|Error|Failure))\s*:\s*(?P<message>[^\r\n]+)")


def parse_log(log_text: str | None) -> ParsedLog:
    """Parse a log without raising for empty, malformed, or very large input."""
    original = str(log_text or "")
    warnings: list[str] = []
    if not original.strip():
        return ParsedLog(warnings=["No log content was supplied."])
    if len(original) > MAX_LOG_CHARS:
        original = original[-MAX_LOG_CHARS:]
        warnings.append("Log was truncated to the most recent 1,000,000 characters.")

    language = detect_language(original)
    if language == "Python":
        parsed = _parse_python(original)
    elif language == "Java":
        parsed = _parse_java(original)
    elif language in {"NodeJS", "JavaScript", "React"}:
        parsed = _parse_javascript(original, language)
    else:
        parsed = _parse_fallback(original)
    parsed.warnings.extend(warnings)
    if len(parsed.frames) >= MAX_FRAMES:
        parsed.warnings.append(f"Call stack limited to {MAX_FRAMES} frames.")
    return parsed


def _parse_python(text: str) -> ParsedLog:
    frames = [
        {"file": match.group("file"), "line": int(match.group("line")),
         "function": match.group("function").strip(), "raw": match.group(0).strip()}
        for match in PYTHON_FRAME.finditer(text)
    ][-MAX_FRAMES:]
    exceptions = list(PYTHON_EXCEPTION.finditer(text))
    root = exceptions[-1] if exceptions else None
    return ParsedLog(
        language="Python",
        exception_type=root.group("type").split(".")[-1] if root else None,
        error_message=(root.group("message") or "").strip() or None if root else None,
        root_exception=root.group("type").split(".")[-1] if root else None,
        frames=frames,
    )


def _parse_java(text: str) -> ParsedLog:
    frames = []
    for match in JAVA_FRAME.finditer(text):
        qualified = match.group("qualified")
        frames.append({
            "file": match.group("file"),
            "line": int(match.group("line")) if match.group("line") else None,
            "function": qualified.rsplit(".", 1)[-1],
            "qualified": qualified,
            "raw": match.group(0).strip(),
        })
    exceptions = list(JAVA_EXCEPTION.finditer(text))
    root = exceptions[-1] if exceptions else None
    return ParsedLog(
        language="Java",
        exception_type=root.group("type").split(".")[-1] if root else None,
        error_message=(root.group("message") or "").strip() or None if root else None,
        root_exception=root.group("type").split(".")[-1] if root else None,
        frames=frames[:MAX_FRAMES],
    )


def _parse_javascript(text: str, language: str) -> ParsedLog:
    frames = []
    for match in JS_FRAME_PAREN.finditer(text):
        frames.append({"file": match.group("file"), "line": int(match.group("line")),
                       "function": match.group("function").strip() or "<anonymous>", "raw": match.group(0).strip()})
    for match in JS_FRAME_BARE.finditer(text):
        frames.append({"file": match.group("file"), "line": int(match.group("line")),
                       "function": "<anonymous>", "raw": match.group(0).strip()})
    exception = JS_EXCEPTION.search(text)
    return ParsedLog(
        language=language,
        exception_type=exception.group("type") if exception else None,
        error_message=(exception.group("message") or "").strip() or None if exception else None,
        root_exception=exception.group("type") if exception else None,
        frames=frames[:MAX_FRAMES],
    )


def _parse_fallback(text: str) -> ParsedLog:
    matches = list(GENERIC_EXCEPTION.finditer(text))
    match = matches[-1] if matches else None
    message = match.group("message").strip() if match else _fallback_error_line(text)
    return ParsedLog(
        language="Unknown",
        exception_type=match.group("type").split(".")[-1] if match else None,
        error_message=message,
        root_exception=match.group("type").split(".")[-1] if match else None,
        warnings=[] if match else ["Unknown or incomplete log format; fallback parser used."],
    )


def _fallback_error_line(text: str) -> str | None:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    error_lines = [line for line in lines if re.search(r"\b(error|failed|fatal)\b", line, re.IGNORECASE)]
    return (error_lines[-1] if error_lines else lines[-1] if lines else None)


def module_from_path(file_name: str | None) -> tuple[str | None, str | None]:
    """Infer a module and dotted package from a frame path."""
    if not file_name:
        return None, None
    normalized = file_name.replace("\\", "/")
    parts = [part for part in normalized.split("/") if part and part not in {".", ".."}]
    module = Path(parts[-1]).stem if parts else None
    package = ".".join(parts[-4:-1]) or None
    return module, package


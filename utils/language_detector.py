"""Fast language detection for heterogeneous error logs."""

from __future__ import annotations

import re


def detect_language(log_text: str) -> str:
    text = log_text or ""
    patterns = (
        ("Python", (r"Traceback \(most recent call last\)", r'File "[^"]+", line \d+')),
        ("Java", (r"(?:Caused by:\s*)?[\w.$]+(?:Exception|Error)(?::|$)", r"\bat [\w.$]+\([^:()]+\.java:\d+\)")),
        ("React", (r"Invalid hook call", r"The above error occurred in the <", r"react-dom")),
        ("NodeJS", (r"\bat .+ \([^()]+\.(?:js|ts):\d+:\d+\)", r"node:internal", r"npm ERR!")),
        ("JavaScript", (r"(?:ReferenceError|SyntaxError|TypeError|RangeError):", r"\.(?:js|ts|jsx|tsx):\d+:\d+")),
        ("Container", (r"kubectl|docker|containerd|CrashLoopBackOff", r"pod[/ ]")),
    )
    best = ("Unknown", 0)
    for language, language_patterns in patterns:
        score = sum(bool(re.search(pattern, text, re.IGNORECASE | re.MULTILINE)) for pattern in language_patterns)
        if score > best[1]:
            best = (language, score)
    return best[0]


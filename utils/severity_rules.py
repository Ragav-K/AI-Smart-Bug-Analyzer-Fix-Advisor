"""Reusable severity rule definitions and weighted phrase scoring."""

from __future__ import annotations

import re

SEVERITY_RULES: dict[str, dict[str, int]] = {
    "Critical": {
        "production outage": 10, "system down": 10, "data loss": 10,
        "data corruption": 10, "security vulnerability": 10,
        # Reporters phrase the same payment outage as a noun or a verb, so both
        # forms carry the same weight. End-to-end validation found "payment
        # fails for all customers" triaged as Medium purely because only the
        # noun form was listed.
        "payment failure": 9, "payments failing": 9,
        "payment fails": 9, "payments fail": 9,
        "cannot login": 8,
        "unable to log in": 8, "authentication completely broken": 10,
        "memory leak": 7, "application crash": 7, "crashes": 6,
        "ransomware": 10, "breach": 10,
    },
    "High": {
        "major feature": 7, "unusable": 7, "database unavailable": 8,
        "connection refused": 6, "repeated": 4, "all users": 7,
        "all customers": 7, "every customer": 7,
        "many users": 6, "cannot complete": 7, "unable to complete": 7,
        "timeout": 4, "service unavailable": 7, "500 internal": 6,
        "significant performance": 6, "api failure": 6,
    },
    "Medium": {
        "validation": 4, "incorrect calculation": 5, "partially": 4,
        "occasional": 3, "intermittent": 3, "wrong result": 4,
        "not saved": 4, "fails sometimes": 4, "degraded": 3,
    },
    "Low": {
        "typo": 5, "spacing": 4, "color": 3, "alignment": 4,
        "cosmetic": 5, "minor enhancement": 5, "ui bug": 3,
        "label": 2, "icon": 2, "font": 3,
    },
}


NEGATIONS = ("not a production", "no data loss", "does not crash", "without crashing")


def score_severity(text: str) -> tuple[dict[str, int], dict[str, list[str]]]:
    """Score severity phrases using word boundaries and simple negation guards."""
    normalized = " ".join(text.lower().split())
    guarded = normalized
    for phrase in NEGATIONS:
        guarded = guarded.replace(phrase, " ")
    scores = dict.fromkeys(SEVERITY_RULES, 0)
    matches: dict[str, list[str]] = {level: [] for level in SEVERITY_RULES}
    for level, rules in SEVERITY_RULES.items():
        for phrase, weight in rules.items():
            if re.search(rf"(?<!\w){re.escape(phrase)}(?!\w)", guarded):
                scores[level] += weight
                matches[level].append(phrase)
    return scores, matches


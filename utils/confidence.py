"""Shared confidence calculations for deterministic agents."""


def bounded_confidence(base: int, signals: int, ambiguity: int = 0) -> int:
    """Turn evidence strength into a conservative percentage."""
    return max(0, min(99, round(base + min(signals, 8) * 6 - ambiguity * 5)))


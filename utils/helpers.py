from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[1]
STYLE_PATH = ROOT_DIR / "styles" / "style.css"


def load_css() -> str:
    """Return the custom CSS used by the Streamlit app."""
    if not STYLE_PATH.exists():
        return ""
    return STYLE_PATH.read_text(encoding="utf-8")


def format_file_size(size_bytes: int) -> str:
    """Format bytes into a compact human-readable size."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    if size_bytes < 1024**2:
        return f"{size_bytes / 1024:.1f} KB"
    return f"{size_bytes / 1024**2:.1f} MB"


def readable_timestamp(timestamp: str) -> str:
    """Convert an ISO timestamp into a dashboard-friendly date string."""
    try:
        parsed = datetime.fromisoformat(timestamp)
    except ValueError:
        return timestamp
    return parsed.strftime("%d %b %Y, %I:%M %p")


def as_bool_label(value: Any) -> str:
    """Return Yes or No for truthy values."""
    return "Yes" if value else "No"


def severity_badge_class(severity: str) -> str:
    """Map a severity label to a CSS class."""
    return {
        "Critical": "severity-critical",
        "High": "severity-high",
        "Medium": "severity-medium",
        "Low": "severity-low",
    }.get(severity, "severity-medium")

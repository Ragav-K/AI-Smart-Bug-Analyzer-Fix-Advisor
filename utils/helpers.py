from __future__ import annotations

from pathlib import Path

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

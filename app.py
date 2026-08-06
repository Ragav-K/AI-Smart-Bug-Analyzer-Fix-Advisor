import sys
from pathlib import Path

# Streamlit may launch this file while the shell is in another directory.
# Pin local imports to this project so the generic "pages" package cannot
# resolve to a stale copy from another workspace.
PROJECT_ROOT = str(Path(__file__).resolve().parent)
if PROJECT_ROOT in sys.path:
    sys.path.remove(PROJECT_ROOT)
sys.path.insert(0, PROJECT_ROOT)

from pages.bug_submission import render_bug_submission  # noqa: E402 - must follow the sys.path pin above


def main() -> None:
    """Application entry point."""
    render_bug_submission()


if __name__ == "__main__":
    main()

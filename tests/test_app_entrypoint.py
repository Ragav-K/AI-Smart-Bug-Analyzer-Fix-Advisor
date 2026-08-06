"""Tests for reliable project-local module resolution and app rendering."""

import json
import subprocess
import sys

import pytest

import app


def test_project_root_has_import_priority() -> None:
    assert sys.path[0] == app.PROJECT_ROOT


# Rendering the real application registers it as a Streamlit multipage app,
# because the project has a `pages/` directory. That is process-global state,
# and it makes every later AppTest.from_string() fail while deriving a page
# title. The smoke test therefore runs in its own interpreter.
RENDER_SCRIPT = """
import json
from streamlit.testing.v1 import AppTest

rendered = AppTest.from_file("streamlit_app.py", default_timeout=300).run()
print("@@@" + json.dumps({
    "exceptions": [item.value for item in rendered.exception],
    "markdown": [item.value for item in rendered.markdown],
    "metrics": [metric.label for metric in rendered.metric],
}))
"""


@pytest.fixture(scope="module")
def rendered_app() -> dict:
    """Render the real application once, exactly as Streamlit would."""
    completed = subprocess.run(
        [sys.executable, "-c", RENDER_SCRIPT],
        cwd=app.PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=600,
    )
    assert completed.returncode == 0, completed.stderr[-2000:]
    payload = [line for line in completed.stdout.splitlines() if line.startswith("@@@")]
    assert payload, completed.stdout[-2000:]
    return json.loads(payload[-1][3:])


def test_the_application_renders_without_raising(rendered_app: dict) -> None:
    assert rendered_app["exceptions"] == []


def test_the_submission_form_is_present(rendered_app: dict) -> None:
    assert any("Bug Submission" in heading for heading in rendered_app["markdown"])


def test_analytics_and_growth_sections_render_for_an_analyzed_submission(
    rendered_app: dict,
) -> None:
    """These sections only exist once a submission has been analyzed.

    Saved reports are per-machine runtime data, so a fresh clone legitimately
    has none. The test asserts the wiring wherever a submission exists rather
    than requiring one.
    """
    headings = " ".join(rendered_app["markdown"])
    if "AI Analysis Dashboard" not in headings:
        pytest.skip("no analyzed submission is saved on this machine")

    assert "Confirm the Fix (Knowledge Base Growth)" in headings
    assert "Defect Pattern Analytics" in headings
    assert "Recurring defect themes" in headings
    assert "High-frequency affected components" in headings
    assert "Systemic issue patterns" in headings
    assert "Defects analyzed" in rendered_app["metrics"]

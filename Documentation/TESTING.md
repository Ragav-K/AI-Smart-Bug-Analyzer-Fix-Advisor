# Testing and Evaluation

## Run the tests

```powershell
python -m pytest -q
```

The suite currently covers:

- Python, Java, Node.js, malformed, empty, nested, and oversized logs
- severity, priority, component, confidence, and missing-field behavior
- orchestrator integration, dependency injection, and fault isolation
- vector-search safety and timeout fallback behavior
- grounded root-cause confidence and evidence provenance
- duplicate thresholds and diagnostic re-ranking
- remediation with and without recorded historical resolutions
- one-time retrieval reuse and five-stage execution
- Streamlit dashboard rendering and portable report generation

## Run one test module

```powershell
python -m pytest -q tests/test_log_analysis.py
python -m pytest -q tests/test_triage.py
python -m pytest -q tests/test_orchestrator.py
python -m pytest -q tests/test_rag_search.py
python -m pytest -q tests/test_milestone3_agents.py
python -m pytest -q tests/test_milestone3_orchestrator.py
python -m pytest -q tests/test_findings.py
python -m pytest -q tests/test_milestone4_analytics.py
python -m pytest -q tests/test_milestone4_knowledge_base.py
python -m pytest -q tests/test_milestone4_end_to_end.py
```

The Milestone 4 knowledge base tests redirect the learned corpus to a temporary
directory, so they never write to `gitbugs/`.

## Evaluation suite

```powershell
python -m evaluation.evaluate_agents
```

The evaluation runner writes:

- `evaluation/evaluation_report.json`
- `evaluation/evaluation_report.csv`
- `Documentation/evaluation/evaluation_summary.md`

## End-to-end validation

```powershell
python evaluation/end_to_end_validation.py
```

Runs 12 labelled submissions across 4 historical dataset sizes (48 pipeline
runs) and scores agent accuracy, duplicate precision/recall/F1 against planted
ground truth, and recommendation relevance. It writes:

- `Documentation/evaluation/milestone4_e2e_validation.md`
- `evaluation/milestone4_e2e_report.json`

## Demonstration

```powershell
python scripts/demo_milestone4.py
```

Writes `Documentation/evaluation/milestone4_demo_report.md`. It does not modify
`data/bug_reports.json`; undo its knowledge base write with
`python scripts/demo_milestone4.py --cleanup`.

Evaluation artifacts provide reproducible measurements, but they do not replace
manual inspection of diagnostic quality.

## Before opening a pull request

Run:

```powershell
python -m pytest -q
python -m pytest --cov=agents --cov=models --cov=utils.scoring --cov=ui.findings --cov-report=term-missing
git diff --check
```

Do not commit generated caches, local reports, uploads, vector indexes, or raw
oversized datasets.

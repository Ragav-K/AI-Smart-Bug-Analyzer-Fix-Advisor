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

## Run one test module

```powershell
python -m pytest -q tests/test_log_analysis.py
python -m pytest -q tests/test_triage.py
python -m pytest -q tests/test_orchestrator.py
python -m pytest -q tests/test_rag_search.py
```

## Evaluation suite

```powershell
python -m evaluation.evaluate_agents
```

The evaluation runner writes:

- `evaluation/evaluation_report.json`
- `evaluation/evaluation_report.csv`
- `evaluation/evaluation_summary.md`

Evaluation artifacts provide reproducible measurements, but they do not replace
manual inspection of diagnostic quality.

## Before opening a pull request

Run:

```powershell
python -m pytest -q
git diff --check
```

Do not commit generated caches, local reports, uploads, vector indexes, or raw
oversized datasets.

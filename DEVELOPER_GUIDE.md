# Developer Guide

## Runtime contracts

Every agent implements `predict(payload)` and returns a Pydantic model. The
orchestrator serializes both Pydantic 1.x and 2.x models into JSON-compatible
dictionaries. New public functions and classes require type hints and docstrings.

Milestone 3 contracts live in `models/analysis_models.py`:

- `RootCauseResult`
- `DuplicateResult` and `DuplicateMatch`
- `RemediationResult`
- `EvidenceItem`

Confidence is always an integer from 0 to 100.

## Shared context

Root cause, duplicate detection, and remediation receive the same dictionary:

```python
{
    "submission": submission,
    "log_analysis": log_analysis,
    "triage": triage,
    "retrieved_bugs": top_ten_matches,
    "root_cause": root_cause,                 # after that stage
    "duplicate_detection": duplicate_result, # after that stage
}
```

Do not call the retriever inside an agent. Retrieval belongs to the orchestrator
and must run at most once per analysis. The Streamlit submission path performs
the search before orchestration, so the orchestrator reuses `similar_bugs`.

## Evidence rules

1. Preserve historical bug IDs in conclusions and remediation.
2. Do not turn missing dataset fields into asserted facts.
3. Filter weak duplicates instead of presenting them as likely matches.
4. When no recorded resolution exists, request more evidence rather than
   inventing a fix.
5. Keep confidence conservative when logs or history are incomplete.

## Adding an agent

1. Add its Pydantic result model.
2. Implement one responsibility in `agents/`.
3. Inject it through `BugAnalysisOrchestrator.__init__`.
4. Add a fault-isolated `_execute` stage.
5. Pass existing context forward; do not repeat parsing or retrieval.
6. Add unit, failure, empty-input, and orchestrator integration tests.
7. Add a structured dashboard section rather than a raw text dump.

## Analytics and the knowledge base

The analytics agent has a different shape from the five pipeline agents: it
takes the list of saved reports, not one submission, and issues no retrieval.

- Put aggregation arithmetic in `utils/defect_analytics.py`, which is pure and
  Streamlit-free, so the dashboard, tests, and generated reports share it.
- A new systemic rule belongs in `DefectPatternAnalyticsAgent._systemic_patterns`
  and must populate `evidence` with the observations that triggered it, and set
  a minimum count so it cannot fire on a single incident.
- `utils/knowledge_base.py` writes confirmed fixes as a CSV under
  `gitbugs/learned/`. Keep the column names aligned with the aliases in
  `utils.rag_search.FIELD_ALIASES` and the reader in `utils.bug_similarity`, so
  one write stays retrievable on both backends without special-casing.

## Quality checks

```powershell
python -m pytest -q
python -m pytest --cov=agents --cov=models --cov=utils.scoring --cov=ui.findings --cov-report=term-missing
git diff --check
```

For UI changes, keep the Streamlit render test and manually verify both light
and dark themes at desktop and narrow widths.

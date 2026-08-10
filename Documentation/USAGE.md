# Usage Guide

## Start the application

```powershell
python -m streamlit run streamlit_app.py
```

## Submit a bug

Choose one of the submission methods:

- **Text** for a manually written report
- **File** for logs or other supporting documents
- **Text + File** for the most complete analysis

Text submissions can include a title, description, reproduction steps, expected
result, actual result, and environment. Supported upload types include TXT, LOG,
PDF, DOCX, PNG, JPG, JPEG, ZIP, Java, Python, JavaScript, TypeScript, C++, JSON,
and XML.

Never upload secrets or confidential production data.

## Understand the results

### Triage

The triage agent estimates:

- severity and priority
- likely software component
- confidence
- evidence and reasoning signals

These values are deterministic heuristics and should be treated as decision
support rather than final incident classification.

### Log analysis

The log-analysis agent detects the likely language, exception type, error
message, source location, and call-stack frames. Parsing is bounded to protect
the interface from excessively large logs.

### Similar historical bugs

The search panel shows up to five similar defects. Results include a similarity
score, source project, matching reasons, and the active backend:

- `all-MiniLM-L6-v2` means the persistent Chroma vector index was used.
- `Local token similarity` means the app used its bounded local fallback.

### Confirm the fix (knowledge base growth)

Once a defect has actually been repaired, describe the corrective action in
**Confirm the Fix** and submit it. The fix is written into the Historical Defect
Knowledge Base and becomes retrievable evidence for every later submission, so
the next report of the same failure is answered from a proven fix instead of a
diagnostic inference.

- Describe what was changed, not that it was closed. A bare status such as
  `Fixed` is rejected, because it would tell a future reader nothing.
- Re-confirming the same submission replaces its recorded fix rather than
  adding a competing second entry.
- If the vector index has not been built, the fix is searchable immediately
  through the local matcher and joins the semantic index at the next
  `python scripts/build_index.py` run. The interface says which happened.

Confirmed fixes are stored in `gitbugs/learned/learned_bugs.csv`, which is
excluded from Git as per-deployment operational data.

### Defect pattern analytics

The analytics panel measures patterns across every analyzed submission rather
than the current one:

- **Recurring themes** group defects by the failure the pipeline extracted
  (root exception) and the component it affected, so differently worded reports
  of the same failure land together.
- **High-frequency affected components** show which areas absorb defects and how
  many are Critical or High severity.
- **Systemic issue patterns** fire only on rules with enough evidence, and each
  one lists the observations that triggered it. Nothing is reported below three
  analyzed submissions, because a proportion over one or two defects describes
  an incident rather than a system.

A `knowledge-base-gap` pattern means most recommendations are inferred rather
than grounded in a recorded fix. Confirming fixes is what clears it.

## Local storage

Submitted reports are appended to `data/bug_reports.json`. Uploaded files are
stored below `uploads/` using a generated submission identifier. Both locations
are excluded from Git.

To clear stored data, stop the application and back up any reports you need
before removing those local artifacts.

## Evaluate the agents

```powershell
python -m evaluation.evaluate_agents
```

This writes evaluation artifacts under `evaluation/`.

## Validate the whole pipeline

```powershell
python evaluation/end_to_end_validation.py
```

Runs 12 labelled submissions across 4 historical dataset sizes and scores agent
accuracy, duplicate precision/recall/F1, and recommendation relevance. See
[Milestone 4](MILESTONE4.md) for the measured results.

## Run the demonstration

```powershell
python scripts/demo_milestone4.py
```

Processes five distinct defects end to end, then shows a recommendation moving
from inferred to historically grounded after one confirmed fix. Undo its
knowledge base write with `python scripts/demo_milestone4.py --cleanup`.

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

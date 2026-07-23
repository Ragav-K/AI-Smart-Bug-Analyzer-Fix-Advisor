# Triage and Log Analysis Agent Validation Report

## Executive summary

The Triage and Log Analysis agents were evaluated against a deterministic,
seeded dataset of **60 bug reports**. The dataset contains
12 labelled scenarios repeated across five supported input representations.

| Metric | Correct | Accuracy |
|---|---:|---:|
| Severity classification | 60/60 | 100.00% |
| Priority classification | 60/60 | 100.00% |
| Component classification | 60/60 | 100.00% |
| Exception-type detection | 60/60 | 100.00% |
| Exact match across all four fields | 60/60 | 100.00% |

**Result:** all seeded cases passed. There were **0**
exception false positives and **0** exception false
negatives.

## Validation scope

Each case supplies labelled ground truth for severity, priority, component, and
exception type. The same scenario set is exercised through these input shapes:

| Input format | Cases | Exact matches | Accuracy |
|---|---:|---:|---:|
| `full_form_record` | 12 | 12/12 | 100.00% |
| `minimal_record` | 12 | 12/12 | 100.00% |
| `plain_text` | 12 | 12/12 | 100.00% |
| `structured_record` | 12 | 12/12 | 100.00% |
| `uploaded_log_record` | 12 | 12/12 | 100.00% |

The input representations cover a normal structured submission, combined plain
text, text extracted from an uploaded log, a sparse/minimal record, and a
complete form-style record.

## Triage coverage

### Severity

| Expected severity | Cases | Exact matches | Accuracy |
|---|---:|---:|---:|
| Critical | 25 | 25/25 | 100.00% |
| High | 15 | 15/15 | 100.00% |
| Low | 10 | 10/10 | 100.00% |
| Medium | 10 | 10/10 | 100.00% |

### Product component

| Expected component | Cases | Exact matches | Accuracy |
|---|---:|---:|---:|
| Authentication | 5 | 5/5 | 100.00% |
| Backend | 10 | 10/10 | 100.00% |
| Database | 10 | 10/10 | 100.00% |
| Frontend | 5 | 5/5 | 100.00% |
| Notifications | 5 | 5/5 | 100.00% |
| Payment | 5 | 5/5 | 100.00% |
| Performance | 5 | 5/5 | 100.00% |
| REST API | 5 | 5/5 | 100.00% |
| Security | 5 | 5/5 | 100.00% |
| UI | 5 | 5/5 | 100.00% |

Priority labels P0 through P3 are represented. The scenarios include production
outages, security exposure, payment failure, data corruption, service
unavailability, performance degradation, partial workflow failures, intermittent
failures, and cosmetic defects.

## Log Analysis coverage

| Expected exception | Cases | Exact matches | Accuracy |
|---|---:|---:|---:|
| AttributeError | 5 | 5/5 | 100.00% |
| Error | 5 | 5/5 | 100.00% |
| IOException | 5 | 5/5 | 100.00% |
| No exception | 10 | 10/10 | 100.00% |
| RuntimeError | 5 | 5/5 | 100.00% |
| SQLException | 10 | 10/10 | 100.00% |
| SecurityError | 5 | 5/5 | 100.00% |
| TimeoutError | 5 | 5/5 | 100.00% |
| TypeError | 5 | 5/5 | 100.00% |
| ValueError | 5 | 5/5 | 100.00% |

The log samples cover Python tracebacks, Java stack traces, JavaScript/Node stack
traces, single-line generic errors, incomplete warning-only logs, and explicit
no-exception controls.

## Reliability and execution time

| Measure | Result |
|---|---:|
| Average Triage confidence | 84.50% |
| Average Log Analysis confidence | 82.17% |
| Mean end-to-end execution time | 0.007250 seconds |
| P95 end-to-end execution time | 0.011217 seconds |
| Exception false positives | 0 |
| Exception false negatives | 0 |

## Failed cases

No seeded case failed any evaluated field.

## Methodology

1. `build_seed_dataset()` creates 60 deterministic labelled cases from 12 base
   scenarios and five input-format variants.
2. Each case is passed through `BugAnalysisOrchestrator`, which executes the
   Triage and Log Analysis agents independently.
3. Predicted severity, priority, component, and exception type are compared
   using exact equality against ground truth.
4. Execution time and agent confidence are recorded per case.
5. CSV and JSON artifacts retain the complete per-case evidence.

## Interpretation and limitations

The measured result validates deterministic behaviour on this seeded,
in-distribution dataset. It does **not** establish 100% accuracy on arbitrary
production reports. The 60 cases are format variants of 12 base scenarios, and
their labels align with the rules implemented by the agents. Future validation
should add independently authored reports, misspellings, mixed-language logs,
contradictory impact statements, previously unseen exception families, and
human-reviewed production samples.

## Reproduction

Run:

```powershell
python evaluation/evaluate_agents.py
```

Generated artifacts:

- `evaluation/triage_log_analysis_validation.md`
- `evaluation/evaluation_report.json`
- `evaluation/evaluation_report.csv`
- `evaluation/evaluation_summary.md`

Generated at: `2026-07-20T11:41:11.847674+00:00`

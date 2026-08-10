# Changelog

All notable changes to this project are documented here. The format follows the
principles of Keep a Changelog, and versions should use semantic versioning once
formal releases begin.

## Unreleased

### Added — Milestone 4

- Defect pattern analytics: recurring failure themes keyed on (root exception,
  component), high-frequency component hotspots, and five rule-based systemic
  issue detectors, each carrying the counts that triggered it
  (`agents/pattern_analytics_agent.py`, `utils/defect_analytics.py`,
  `models/analytics_models.py`, `ui/analytics.py`)
- Knowledge base growth: a confirmed fix on a resolved submission is written to
  `gitbugs/learned/learned_bugs.csv`, which both retrieval backends already
  discover, and upserted into the vector index when one is built
  (`utils/knowledge_base.py`). A bare workflow status is rejected as a
  resolution, and re-confirming replaces rather than duplicates
- `evaluation/end_to_end_validation.py`: 12 labelled submissions across 4
  historical dataset sizes (48 pipeline runs), scoring agent accuracy, duplicate
  precision/recall/F1 against planted ground truth, and recommendation relevance
- `scripts/demo_milestone4.py`: five-submission demonstration showing full
  pipeline output, then `diagnostic -> historical` remediation after one
  confirmed fix, then analytics
- `MILESTONE4.md` technical documentation and project report
- 48 Milestone 4 tests plus an out-of-process app render smoke test
  (suite total: 124)

### Fixed — found by end-to-end validation

- An exception prefixed by a log level or field name (`FATAL: SecurityError: ...`,
  `stack: java.io.IOException: ...`) was missed entirely: the language-specific
  exception patterns are line-anchored. The generic scanner now gets a turn when,
  and only when, the language parser found no exception at all
- Plural component keywords were unclassified, so "notifications" fell to `Other`
- A payment outage phrased as a verb ("payment fails for all customers") triaged
  as Medium because only the noun form was in the severity rules
- Retrieval ignored the stack trace for submissions assembled without
  `submitted_text`, so the same defect matched its duplicate as plain text and
  missed it as a record. Duplicate recall 57% -> 86%, F1 0.73 -> 0.92
- The fallback retrieval path discarded the `resolution` and `root_cause`
  columns, so a confirmed fix could not ground a recommendation until the vector
  index was rebuilt -- which would have left knowledge base growth inert on the
  default path
- Writing a confirmed fix left the fallback corpus cache cold, so the next
  search had to reload the whole corpus inside the 2.5-second interactive
  budget and could silently return nothing. The corpus is now rebuilt at
  confirmation time

### Fixed

- The committed knowledge base was unusable: the only committed datasets held
  just issue and duplicate ids, and the local matcher globbed the gitignored
  full exports, so a fresh clone retrieved nothing. `gitbugs/samples/` is now
  committed and both retrieval paths read it
- The vector index had no build entry point, so semantic retrieval never ran.
  Added `scripts/build_index.py` and clearer in-app status
- Duplicate detection was effectively silent on the fallback backend, whose
  scores never reached the semantic threshold; the floor is now backend-aware
- Issue-tracker `Resolution` statuses such as "Fixed" were treated as fix text
  and could be recommended as a remediation; they are now kept separately as
  `resolution_status`
- `agents/__init__.py` and `models/__init__.py` contained duplicated module
  bodies whose second `__all__` dropped earlier exports
- Bug submission caught every exception and reported one generic message; the
  cause is now logged and surfaced
- A crashed agent was rendered as a clean negative finding rather than a failure
- Overall confidence averaged duplicate similarity together with agent
  confidence percentages, conflating two different units
- Log analysis concatenated five overlapping submission fields, and
  `submitted_text` is assembled from the others, so a single stack trace was
  parsed up to five times and reported as repeated phantom frames
- Remediation could never recommend a fix: issue-tracker exports record a
  workflow status rather than fix text, so every submission reached the
  "no recommendation" branch. It now falls back to a diagnostic
  recommendation derived from the exception and root cause, labelled
  `basis="diagnostic"` and capped below any historically grounded confidence
- An uploaded JSON log kept its stack trace as an escaped string, so the
  line-anchored parsers found no frames at all; JSON uploads are now decoded
  to plain text before parsing
- Java `exception_type` and `root_exception` were always identical, hiding the
  `Caused by:` chain. The thrown exception and the underlying cause are now
  reported separately (Python chaining semantics are unchanged: the final
  exception is the one that propagated)
- The fallback parser could quote a structural line such as `}` as the failure
- The sidebar was hidden by `display: none` while `render_sidebar()` kept
  writing submission history into it, making that feature unreachable

### Added

- `scripts/build_index.py` and `scripts/build_sample_corpus.py` build tooling
- `gitbugs/samples/` committed corpus (9 projects, 3,600 defects)
- Regression tests covering each review fix (`tests/test_review_fixes.py`)
- `sample_uploads/` fixtures covering the Java, Python, JavaScript, JSON, zip,
  and fallback paths, with expected results documented

- Comprehensive project, installation, usage, testing, dataset, security,
  troubleshooting, and roadmap documentation
- Grounded root-cause, semantic duplicate-detection, and remediation agents
- Pydantic contracts for evidence, causes, duplicates, and remediation
- Shared confidence scoring across semantic, diagnostic, and log signals
- Tabbed findings dashboard, submission history, and Markdown/JSON downloads
- Developer guide, architecture sequence diagram, and Milestone 3 test suite

### Changed

- Recoloured the interface to a single deep-teal identity. Layout is
  unchanged; the blue-to-teal gradients on the header and buttons became flat
  fills, and severity keeps a conventional red/amber/green scale so status is
  never read as branding
- All custom properties are namespaced `--ba-*`. The previous plain names
  (`--primary`) collided with variables Streamlit sets on its own containers,
  which silently changed button colours deep in the tree
- Scheme-dependent colour now lives only in the variable block, so the dark
  media query swaps variables instead of re-declaring component rules. The
  previous arrangement let light and dark disagree about the same element,
  leaving white button text on a light teal fill at 2.49:1
- The application is now light-only. The dark media query was removed, and
  `.streamlit/config.toml` pins Streamlit's own theme to light; without that
  pin its widgets follow the operating system into dark and render dark
  underneath the light cards
- The header subtitle rendered dark grey on the teal header at 1.38:1, all
  but invisible. The generic markdown paragraph rule matched it at equal
  specificity but later in the file; the header selector is now qualified so
  it wins without `!important`
- Streamlit's `st.json` viewer uses a Solarized-derived palette tuned for a
  darker canvas, leaving strings, numbers, keys and booleans between 3.0:1
  and 4.4:1. Each value type is now darkened to match the theme
- `st.caption` text sat at 2.8:1: Streamlit applies `opacity: 0.6` to the
  caption container, so the sidebar's current-submission line and the form
  hints were faded almost out of view. Secondary weight now comes from the
  muted colour rather than transparency
- The sidebar page-navigation links rendered at reduced alpha; both the
  active and inactive states are pinned to full-strength ink
- The fade applied to stale widgets during a rerun was deep enough to look
  broken while a five-agent analysis runs, and is now capped at 0.75
- The contrast sweep now folds cumulative ancestor opacity into the measured
  ratio. Without it, text that computes to a dark colour but paints faded -
  exactly the caption case - passed silently
- `run_app.ps1` no longer hardcodes an absolute interpreter path and accepts
  `-Python` and `-Port`
- Removed the unused `schemas/` package, unused helpers in `utils/helpers.py`
  and `utils/bug_similarity.py`, a pass-through dashboard wrapper, and
  committed upload artifacts

- Architecture, agent, retrieval, and technology documents now match the current
  implementation
- Orchestration now executes five fault-isolated stages with one reused retrieval
- Historical search returns ten candidates for re-ranking and five for display
- Local fallback retrieval now respects the interactive latency budget

## 0.2.0 - 2026-07-23

### Added

- Triage and log-analysis agents
- Fault-isolated orchestration
- Historical-defect retrieval with ChromaDB and local fallback
- Compact historical bug samples
- Evaluation reports
- Automated tests for agents, parsing, orchestration, and retrieval

### Changed

- Expanded Streamlit submission and analysis interface
- Added Git ignore rules for generated, sensitive, and oversized artifacts

## 0.1.0

### Added

- Initial Streamlit bug-submission interface
- Local JSON report storage and file uploads
- Initial architecture, technology, RAG, and multi-agent design notes

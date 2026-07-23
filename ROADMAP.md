# Roadmap

This roadmap describes intended directions, not guaranteed release dates.

## Near term

- Add a portable command-line index builder with progress reporting
- Add linting, formatting, and continuous-integration checks
- Improve file-extraction tests for PDF, DOCX, ZIP, and spreadsheet inputs
- Add configurable storage paths and retention controls
- Improve dataset attribution and reproducible sample-generation tooling

## Agent expansion

- Duplicate-detection agent with an explicit result schema
- Root-cause agent grounded in retrieved defects and parsed evidence
- Remediation agent with ranked, testable suggestions
- Cross-agent evidence citations and disagreement handling

## Retrieval improvements

- Incremental index updates and dataset fingerprints
- Hybrid lexical and vector ranking
- Retrieval-quality benchmarks
- Configurable embedding models
- Clear index-management controls in the UI

## Product hardening

- Authentication and authorization for shared deployments
- Encrypted or external persistence options
- Configurable redaction for secrets and personal information
- Exportable analysis reports
- Accessibility and responsive-layout review

Completed work should be moved to [CHANGELOG.md](CHANGELOG.md).

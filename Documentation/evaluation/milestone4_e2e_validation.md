# Milestone 4 End-to-End Validation Report

Generated at: `2026-08-05T13:43:09.197860+00:00`

## Scope

12 labelled bug submissions were executed through the complete
five-agent pipeline at 4 historical dataset sizes
(0, 6, 30, 120 records), for
**48 total pipeline runs**.

**Bug types covered:** API payload validation, Authentication crash, Authentication crash, re-reported, Cosmetic UI defect, Database exhaustion, Empty submission, Payment failure, Security exposure, Sparse report, Storage exhaustion, Upstream dependency timeout, Very large log.

**Stack-trace formats covered:** Chained Python traceback, Empty record, Java SQL stack trace, Java stack trace with Caused by, Java trace inside 20k lines of noise, Key-value log with embedded trace, Minimal record, no title, No trace, prose only, Node.js stack trace, Plain-text submission string, Python traceback, Single-line generic error.

## Headline results (all runs)

| Measure | Result |
|---|---:|
| Pipeline completion (5/5 agents) | 100.00% |
| Runs with an agent error | 0 |
| Exception detection accuracy | 100.00% |
| Component classification accuracy | 100.00% |
| Severity classification accuracy | 100.00% |
| Stack-trace parse correctness | 100.00% |
| Duplicate precision | 100.00% |
| Duplicate recall | 85.71% |
| Duplicate F1 | 92.31% |
| Recommendation relevance | 100.00% |
| Historically grounded recommendations | 56.25% |
| Average overall confidence | 50.9% |
| Average pipeline time | 0.518030 s |
| Slowest pipeline run | 6.236523 s |

## Effect of historical dataset size

| Corpus size | Pipeline completion | Exception accuracy | Duplicate precision | Duplicate recall | Duplicate F1 | Recommendation relevance | Historically grounded |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 0 | 100.00% | 100.00% | n/a | n/a | n/a | 100.00% | 0.00% |
| 6 | 100.00% | 100.00% | 100.00% | 85.71% | 92.31% | 100.00% | 75.00% |
| 30 | 100.00% | 100.00% | 100.00% | 85.71% | 92.31% | 100.00% | 75.00% |
| 120 | 100.00% | 100.00% | 100.00% | 85.71% | 92.31% | 100.00% | 75.00% |

An empty corpus is included deliberately: with no history the pipeline must
still complete, report no duplicates, and fall back to a clearly labelled
diagnostic recommendation rather than fabricating a historical one.

## Per-case results at the largest corpus

| Case | Bug type | Trace format | Exception | Correct | Component | Frames | Duplicates | Remediation basis |
|---|---|---|---|---|---|---:|---|---|
| `E2E-01` | Authentication crash | Java stack trace with Caused by | IllegalStateException | yes | Authentication | 4 | HIST-AUTH-01 | historical |
| `E2E-02` | API payload validation | Python traceback | KeyError | yes | REST API | 1 | HIST-API-02 | historical |
| `E2E-03` | Payment failure | Node.js stack trace | TypeError | yes | Payment | 3 | HIST-PAY-03 | historical |
| `E2E-04` | Database exhaustion | Java SQL stack trace | SQLException | yes | Database | 2 | HIST-DB-04 | historical |
| `E2E-05` | Upstream dependency timeout | Chained Python traceback | ConnectionError | yes | Backend | 2 | none | historical |
| `E2E-06` | Security exposure | Single-line generic error | SecurityError | yes | Security | 0 | none | historical |
| `E2E-07` | Storage exhaustion | Key-value log with embedded trace | IOException | yes | Search | 1 | HIST-IDX-07 | historical |
| `E2E-08` | Cosmetic UI defect | No trace, prose only | None | yes | UI | 0 | none | diagnostic |
| `E2E-09` | Authentication crash, re-reported | Plain-text submission string | IllegalStateException | yes | Authentication | 4 | HIST-AUTH-01 | historical |
| `E2E-10` | Sparse report | Minimal record, no title | None | yes | Notifications | 0 | none | diagnostic |
| `E2E-11` | Empty submission | Empty record | None | yes | Other | 0 | none | none |
| `E2E-12` | Very large log | Java trace inside 20k lines of noise | IllegalStateException | yes | Authentication | 4 | none | historical |

## Duplicate detection quality

Ground truth is planted: each case declares the historical defect that is
genuinely its duplicate, or `None` when no true duplicate exists in the corpus.
Precision and recall are computed against that label, so a match to a plausible
but incorrect historical defect counts as a false positive.

- True positives: 18
- False positives: 0
- False negatives: 3

## Recommendation relevance

A recommendation counts as relevant only when the remediation agent grounded it
in the specific historical defect that actually records the fix
(`basis == "historical"` and the expected bug id present in `evidence_bug_ids`).
Where no history exists, a recommendation is relevant when it is correctly
labelled `diagnostic` or `none` rather than presented as historically proven.

## Defect pattern analytics on the validated corpus

| Recurring theme | Occurrences | Share |
|---|---:|---:|
| IllegalStateException in Authentication | 3 | 25% |
| ConnectionError in Backend | 1 | 8% |
| IOException in Search | 1 | 8% |
| KeyError in REST API | 1 | 8% |
| SQLException in Database | 1 | 8% |
| SecurityError in Security | 1 | 8% |
| TypeError in Payment | 1 | 8% |
| Unclassified failure in Notifications | 1 | 8% |

- **Known defects keep being re-reported** (6 submissions): 6 of 12 analyzed defects (50%) matched a high-confidence historical duplicate, so reporting effort is being spent on failures the organisation has already seen.
- **IllegalStateException is a recurring failure mode** (3 submissions): IllegalStateException accounts for 3 of 12 analyzed defects (25%), spanning 1 component(s).
- **One code location fails repeatedly** (3 submissions): 3 separate submissions failed at validate in LoginService.java, which indicates an unresolved defect rather than independent incidents.

## Deviations from expectation

Every case completed all five agents and met its labelled expectations at every dataset size.

## Reproduction

```bash
python evaluation/end_to_end_validation.py
```

Artifacts:

- `Documentation/evaluation/milestone4_e2e_validation.md`
- `evaluation/milestone4_e2e_report.json`

## Limitations

Retrieval uses a deterministic token matcher over a synthetic corpus so the run
is offline and reproducible. Absolute duplicate scores therefore differ from a
semantic-index deployment, where similarity is better scaled and the duplicate
agent applies a higher threshold. The labelled expectations were authored
alongside the agent rules, so these figures characterise deterministic
in-distribution behaviour and are not an estimate of accuracy on arbitrary
production reports.

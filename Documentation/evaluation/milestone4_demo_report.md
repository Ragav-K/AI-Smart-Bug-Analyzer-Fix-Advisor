# Milestone 4 Demonstration

Generated at: `2026-08-06T09:15:23.424679+00:00`

Five distinct bug submissions were processed by the complete five-agent
pipeline, followed by a knowledge base growth demonstration and defect pattern
analytics across all five.

## 1. Full agent pipeline output

### DEMO-001 — Login crashes for every user in production

- **Log Analysis:** Java log, IllegalStateException at validate in LoginService.java (90% confidence)
- **Triage:** Critical / P0 / Authentication (91% confidence)
- **Root Cause:** An object is null before it is dereferenced; validate initialization and input guards. (36% confidence)
- **Duplicates:** none above threshold
- **Remediation (diagnostic, 51% confidence):** Guard the dereferenced reference before use and return or raise a domain error when it is absent.
- **Overall confidence:** 67% in 0.3496s
### DEMO-002 — Order creation returns 500 when the amount field is missing

- **Log Analysis:** Python log, KeyError at create_order in /srv/api/orders.py (90% confidence)
- **Triage:** Medium / P2 / REST API (99% confidence)
- **Root Cause:** A required mapping key is absent; validate input fields or use a guarded lookup. (23% confidence)
- **Duplicates:** none above threshold
- **Remediation (diagnostic, 48% confidence):** Replace the direct mapping lookup with a guarded lookup and handle the missing key explicitly.
- **Overall confidence:** 65% in 0.0888s
### DEMO-003 — Checkout payment fails for all customers

- **Log Analysis:** JavaScript log, TypeError at chargeCard in /srv/payment/checkout.js (90% confidence)
- **Triage:** Critical / P0 / Payment (91% confidence)
- **Root Cause:** A value has an unexpected type or an operation received incompatible operands. (23% confidence)
- **Duplicates:** none above threshold
- **Remediation (diagnostic, 48% confidence):** Normalize or validate the operand types before the failing operation.
- **Overall confidence:** 63% in 0.0973s
### DEMO-004 — Database connection pool exhausted under load

- **Log Analysis:** Java log, SQLException at createTimeoutException in HikariPool.java (90% confidence)
- **Triage:** Medium / P2 / Database (80% confidence)
- **Root Cause:** A database operation failed; inspect the query, connection, and transaction state. (37% confidence)
- **Duplicates:** none above threshold
- **Remediation (diagnostic, 51% confidence):** Inspect the failing query, connection lifetime, and transaction boundary, and release connections on error.
- **Overall confidence:** 64% in 0.0949s
### DEMO-005 — Users cannot sign in after the evening deployment

- **Log Analysis:** Java log, IllegalStateException at validate in LoginService.java (90% confidence)
- **Triage:** Critical / P0 / Authentication (85% confidence)
- **Root Cause:** An object is null before it is dereferenced; validate initialization and input guards. (40% confidence)
- **Duplicates:** none above threshold
- **Remediation (diagnostic, 52% confidence):** Guard the dereferenced reference before use and return or raise a domain error when it is absent.
- **Overall confidence:** 67% in 0.1361s


## 2. Knowledge base growth

The confirmed fix for `DEMO-001` was written back to the Historical Defect
Knowledge Base as `KB-DEMO-001`:

> Guard the session lookup in LoginService.validate: when SessionStore.lookup returns no user for a token, return a 401 authentication failure instead of dereferencing the null reference, and cover the missing-session path with a regression test.

`DEMO-005` reports the same failure. It was then re-analyzed with the knowledge
base grown by exactly that one confirmed fix.

| Measure | Before the confirmed fix | After |
|---|---|---|
| Remediation basis | `diagnostic` | `historical` |
| Remediation confidence | 52% | 77% |
| Duplicates detected | 0 | KB-DEMO-001 (88%) |
| Evidence bug ids | none | KB-DEMO-001 |

**Recommendation after growth:**

> Guard the session lookup in LoginService.validate: when SessionStore.lookup returns no user for a token, return a 401 authentication failure instead of dereferencing the null reference, and cover the missing-session path with a regression test.

## 3. Defect pattern analytics

- Submissions analyzed: 5
- Recurrence rate: 40%
- Duplicate rate: 0%
- Confirmed fixes in the knowledge base: 1

### Recurring themes

| Theme | Occurrences | Share | Submissions |
|---|---:|---:|---|
| IllegalStateException in Authentication | 2 | 40% | DEMO-001, DEMO-005 |
| KeyError in REST API | 1 | 20% | DEMO-002 |
| SQLException in Database | 1 | 20% | DEMO-004 |
| TypeError in Payment | 1 | 20% | DEMO-003 |

### High-frequency affected components

| Component | Defects | Share | Critical/High | Top exceptions |
|---|---:|---:|---:|---|
| Authentication | 2 | 40% | 2 | IllegalStateException |
| Database | 1 | 20% | 0 | SQLException |
| Payment | 1 | 20% | 1 | TypeError |
| REST API | 1 | 20% | 0 | KeyError |

### Systemic issue patterns

**Recommendations are rarely grounded in a recorded fix** (5 submissions)

5 of 5 recommendations (100%) were inferred from diagnostics because no retrieved defect carried a recorded resolution.

- DEMO-001: basis 'diagnostic'
- DEMO-002: basis 'diagnostic'
- DEMO-003: basis 'diagnostic'
- DEMO-004: basis 'diagnostic'
- DEMO-005: basis 'diagnostic'

*Recommendation:* Confirm the fix on resolved submissions so they are written back into the Historical Defect Knowledge Base. Each confirmed fix converts a future diagnostic guess into an evidence-backed recommendation.

**IllegalStateException is a recurring failure mode** (2 submissions)

IllegalStateException accounts for 2 of 5 analyzed defects (40%), spanning 1 component(s).

- Components affected: Authentication
- DEMO-001: Login crashes for every user in production
- DEMO-005: Users cannot sign in after the evening deployment

*Recommendation:* Treat IllegalStateException as a class of defect rather than a series of incidents: add a shared guard or validation utility at the component boundary and a lint or test rule that catches the pattern before release.

**One code location fails repeatedly** (2 submissions)

2 separate submissions failed at validate in LoginService.java, which indicates an unresolved defect rather than independent incidents.

- Submissions: DEMO-001, DEMO-005

*Recommendation:* Re-open the investigation at validate in LoginService.java. Verify that the previously applied fix addressed the cause rather than the symptom, and add a regression test that reproduces the original failure.

## 4. Full structured report for the first submission

# AI Smart Bug Analysis Report

- Submission: DEMO-001
- Title: Login crashes for every user in production
- Severity / Priority: Critical / P0
- Component: Authentication
- Overall confidence: 67%

## Log analysis

- Exception: IllegalStateException
- Failure point: validate in LoginService.java

## Root cause

An object is null before it is dereferenced; validate initialization and input guards.

The conclusion uses current log diagnostics, checked against retrieved defects. It compares the IllegalStateException failure in Authentication with 5 retrieved historical defect(s).

## Duplicate bugs

- No high-confidence duplicate found.

## Recommended fix

Guard the dereferenced reference before use and return or raise a domain error when it is absent.

### Repair steps

1. Reproduce the IllegalStateException failure at validate in LoginService.java with diagnostic logging enabled.
2. Guard the dereferenced reference before use and return or raise a domain error when it is absent.
3. Apply and review the change in LoginService.java.
4. Add a regression test that fails on the current behaviour and passes after the change.
5. Run the affected component's unit and integration tests, then verify the original reproduction steps.


## Reproduction

```bash
python scripts/demo_milestone4.py
```

Undo the knowledge base write with:

```bash
python scripts/demo_milestone4.py --cleanup
```

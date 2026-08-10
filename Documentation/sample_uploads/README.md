# Sample Uploads

Ready-made files for exercising the submission form and the five-agent
pipeline. Each one targets a different parser or code path.

Upload them from the **Bug Submission** form using the `File` or `Text + File`
submission method.

| File | Exercises | Expected analysis |
|---|---|---|
| `java_nullpointer.log` | Java parser, `Caused by:` chain | Thrown `NullPointerException`, root `IllegalStateException`, 6 frames, failure point `validate in LoginService.java`, Authentication |
| `python_keyerror.txt` | Python traceback, `<listcomp>` frames | `KeyError`, 4 frames, failure point `build_row in /srv/reporting/export.py`, Backend |
| `nodejs_typeerror.log` | Node/JavaScript parser, async frames | `TypeError`, 3 frames, failure point `charge in /srv/checkout/payment.js`, Payment |
| `database_connection_errors.json` | JSON upload with an embedded stack trace | `SQLException`, 3 frames, Database, High/P1 |
| `legacy_app_unknown_format.log` | Fallback parser, unrecognised format | Language `Unknown`, no frames, Critical severity from "data corruption" |
| `LoginService.java` | Source upload with no stack trace | Low confidence; shows the agents degrading honestly rather than guessing |
| `incident_bundle.zip` | Archive extraction across several files | Same Java analysis, escalated to Critical/P0 by the impact statement in `notes.txt` |

## Things worth demonstrating

**Severity depends on impact, not just on the exception.** `java_nullpointer.log`
alone triages as Medium/P2, because a raw stack trace states no user impact.
`incident_bundle.zip` contains the same trace plus a note saying "production
outage, all users unable to log in", and triages Critical/P0. This is the
triage agent behaving correctly, not inconsistently.

**Remediation is labelled by provenance.** These samples produce
`basis="diagnostic"` recommendations, because the GitBugs corpus records a
workflow status (`Fixed`, `WontFix`) rather than fix text. The interface says
so explicitly, and diagnostic confidence is capped below the historical path.
To see a `historical` recommendation, the knowledge base needs defects that
carry a written resolution.

**Pair the log with its source.** Upload `java_nullpointer.log` and
`LoginService.java` together: the log analysis agent identifies
`LoginService.java:52` as the failure point, and the file shows the unguarded
`sessionStore.lookup(token)` dereference that causes it.

## Notes

- Semantic duplicate detection needs the vector index (`python scripts/build_index.py`).
  Without it the app uses the local token matcher at a lower threshold, and these
  samples will usually report no duplicate — correctly, since the GitBugs corpus
  contains no comparable defects.
- All content is synthetic. No real credentials, hosts, or customer data.

# Multi-Agent Design

## Implemented agents

### Triage agent

The triage agent combines the report fields into a bounded text input and
returns a structured Pydantic result containing severity, priority, likely
component, confidence, evidence, and reasoning signals.

### Log-analysis agent

The log-analysis agent detects the likely language and parses Python, Java,
JavaScript, or generic logs. It returns the exception, message, likely source
location, call-stack frames, confidence, and warnings.

## Orchestration

`BugAnalysisOrchestrator` runs each agent independently. An exception from one
agent is recorded under `metadata.agent_errors` and does not stop the other
agent. Results use a stable envelope with:

- submission ID and UTC timestamp
- triage and log-analysis results
- executed-agent names and errors
- processing duration
- schema version
- context reserved for future agents

An optional injected result store allows persistence without coupling agents to
the Streamlit interface.

## Planned agents

- **Duplicate detection** will formalize historical-match decisions.
- **Root cause** will synthesize parsed evidence and retrieved defects.
- **Remediation** will rank practical fixes and verification steps.

New agents should preserve fault isolation, deterministic schemas, bounded
processing, and evidence-based explanations.

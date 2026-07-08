# Multi-Agent Design

The system uses five agents so one large task can be split into smaller, easier checks. Each agent focuses on a specific question and shares its result with the final response module.

- **Triage Agent**  
  Reads the bug title, description, and severity. It decides how urgent the issue looks and what type of bug it might be.

- **Log Analysis Agent**  
  Looks at stack traces, console logs, and error messages. It tries to find the exact failure point, such as a missing file, null value, failed API call, or dependency issue.

- **Duplicate Agent**  
  Compares the new bug with old bug reports in the historical knowledge base. It helps answer: "Have we seen this before?"

- **Root Cause Agent**  
  Uses the report details and similar past bugs to explain the most likely reason for the failure. The goal is to give a practical explanation, not just repeat the error message.

- **Remediation Agent**  
  Suggests a possible fix or next debugging step. It should point the developer toward the most useful action based on the evidence found by the other agents.

# Security Policy

## Supported versions

Security fixes are applied to the latest revision of the `main` branch. Older
commits and private forks are not maintained by this repository.

## Reporting a vulnerability

Do not open a public issue containing exploit details, credentials, private bug
reports, or personal data. Contact the repository owner privately through the
contact method listed on the GitHub profile and include:

- affected component and revision
- impact and realistic attack scenario
- reproduction steps or a minimal proof of concept
- suggested mitigation, if known

Allow reasonable time for investigation before public disclosure.

## Sensitive-data guidance

The application stores reports in `data/bug_reports.json` and uploaded files
below `uploads/`. These paths are ignored by Git but are not encrypted.

- Do not upload passwords, API keys, access tokens, or customer secrets.
- Treat stack traces and logs as potentially sensitive.
- Restrict filesystem access on shared machines.
- Back up and remove local data according to your retention policy.
- Do not expose the development server directly to the public internet.

## Scope limitations

The project is a diagnostic advisor. Its severity, root-cause, and remediation
outputs may be incomplete or incorrect. Review suggestions, test fixes in an
isolated environment, and use normal secure-development practices before
deploying changes.

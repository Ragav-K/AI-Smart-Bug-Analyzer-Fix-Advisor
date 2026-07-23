# Contributing

Contributions that improve diagnostic accuracy, reliability, documentation, or
test coverage are welcome.

## Development workflow

1. Fork the repository and create a focused branch.
2. Create and activate a virtual environment.
3. Install `requirements.txt`.
4. Make the smallest coherent change.
5. Add or update tests and documentation.
6. Run the full test suite and `git diff --check`.
7. Open a pull request with a clear description and verification notes.

```powershell
git checkout -b feature/short-description
python -m pytest -q
git diff --check
```

## Code expectations

- Keep agent outputs deterministic and structured.
- Preserve fault isolation in the orchestrator.
- Bound input size, processing time, and retrieved result counts.
- Avoid hidden network calls in the interactive request path.
- Keep Pydantic compatibility within the supported requirement range.
- Add regression tests for every bug fix.
- Use plain language for user-facing diagnostic explanations.

## Data contributions

Do not commit raw datasets over GitHub's file-size limit, generated Chroma
indexes, user uploads, credentials, or private reports. Follow
[DATASETS.md](DATASETS.md) and include source, license, attribution, and
transformation details for new samples.

## Pull request checklist

- [ ] The change has a single clear purpose.
- [ ] Tests pass locally.
- [ ] New behavior is tested.
- [ ] User-facing behavior is documented.
- [ ] No secrets, private reports, or generated artifacts are included.
- [ ] Dataset licensing and attribution have been checked.

By participating, contributors agree to follow
[CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).

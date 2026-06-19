# Hermes Ershov test matrix

This project treats test coverage as release evidence, not just a percentage.

## Local gates

Run these before a release-facing change:

```bash
uv run --extra dev python -m pytest -q --cov=hermes_dreaming --cov=hermes_ershov --cov=hermes_mnemos --cov-report=term-missing:skip-covered --cov-report=xml --cov-fail-under=80
uv run --extra dev python -m pytest -q tests/test_pbt.py
python3 -m compileall -q __init__.py src scripts
git diff --check
uv run --extra dev python -m build
python3 scripts/hermes_plugin_smoke.py
```

For installed-artifact confidence, smoke the wheel in a temporary virtualenv and run at least:

```bash
ershov --help
ershov providers list
ershov providers doctor --provider offline-marker --strict
ershov status --release-gate --state-root /tmp/hermes-ershov-state
ershov revert --help
```

## CI gates

GitHub Actions runs the same release-shaped matrix:

- Python 3.11 and 3.12
- whitespace check with `git diff --check`
- bytecode compile with `compileall`
- full pytest suite
- coverage report for `hermes_dreaming`, `hermes_ershov`, and `hermes_mnemos`, with an 80% minimum gate
- property-based tests from `tests/test_pbt.py`
- Hermes plugin wrapper smoke
- wheel and source distribution build
- installed wheel smoke for every public console and module alias
- installed source distribution smoke for every public console and module alias
- CodeQL on push, pull request, schedule, and manual dispatch

## Coverage shape

The suite is intentionally mixed:

- unit tests for pure validation, scoring, policy, memory IO, provider parsing, and artifact state
- CLI tests for user-facing command behavior and exit codes
- integration smokes for create, validate, apply, revert, status, update, nightly, and plugin wrapping
- property-based tests for path safety, scoring thresholds, systemd escaping, and soak commit matching
- docs guards that fail when release-facing text drifts from shipped behavior
- negative tests for malformed provider output, fabricated provenance, fabricated quotes/snippets, unsafe paths, missing backups, and no-op nightlies

## Stable-release evidence

Passing CI is not enough for stable wording. Stable promotion also needs scheduled-run evidence from the installed VPS checkout:

```bash
hermes ershov soak --state-root ~/.hermes/ershov --since-hours 96 --min-successful 3 --strict-systemd
```

Manual service starts and transient timer smokes are useful debug evidence, but they do not satisfy the stable gate.

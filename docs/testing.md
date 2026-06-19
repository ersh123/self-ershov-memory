# Hermes Ershov test matrix

This project treats test coverage as release evidence, not just a percentage.

## Practice baseline

The matrix follows the current public docs for:

- pytest good integration practices: https://docs.pytest.org/en/stable/explanation/goodpractices.html
- Hypothesis property-based and stateful testing: https://hypothesis.readthedocs.io/en/latest/stateful.html
- GitHub Actions Python build/test workflows: https://docs.github.com/actions/guides/building-and-testing-python
- GitHub Actions workflow syntax, timeouts, and concurrency: https://docs.github.com/actions/using-workflows/workflow-syntax-for-github-actions
- GitHub CodeQL workflow configuration: https://docs.github.com/en/code-security/reference/code-scanning/workflow-configuration-options
- GitHub Dependabot configuration: https://docs.github.com/en/code-security/reference/supply-chain-security/dependabot-options-reference
- OpenSSF Scorecard GitHub Action: https://github.com/ossf/scorecard-action

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
ershov providers doctor --provider offline-marker --from-systemd --strict
ershov providers doctor --provider deepseek --from-systemd --strict
ershov providers doctor --provider deepseek --from-systemd --fix-plan --strict
ershov providers doctor --provider deepseek --env-file ~/.config/hermes-ershov/nightly.env --env-file ~/.config/hermes-ershov/nightly.secrets.env --strict
ershov status --release-gate --state-root ~/.hermes/ershov --require-provider deepseek
ershov status --release-gate --state-root ~/.hermes/ershov --require-provider deepseek --fix-plan
ershov soak --state-root ~/.hermes/ershov --since-hours 30 --min-successful 1 --strict-systemd --require-provider deepseek
ershov soak --state-root ~/.hermes/ershov --since-hours 30 --min-successful 1 --strict-systemd --require-provider deepseek --fix-plan
ershov status --release-gate --state-root /tmp/hermes-ershov-state
ershov revert --help
```

The status release gate is state-root scoped: with `--state-root`, the default artifact root and ledger/diary paths come from that state root unless `--artifact-root` is passed explicitly.
The provider env-file smoke is timer-visible only: `--from-systemd` reads the default Hermes Ershov systemd `EnvironmentFile` paths, explicit `--env-file` values can test non-default layouts, missing optional secret files are ignored, and secret values are never printed. When `--provider` is explicit, `providers doctor` also fails closed if `HERMES_ERSHOV_PROVIDER` points at a different timer provider. `--fix-plan` is still read-only across `providers doctor`, `status --release-gate`, and text-mode `soak`; it prints remediation commands and `<secret>` placeholders only. `--require-provider deepseek` is stricter than readiness alone: it also fails when the timer is still configured for `offline-marker`.

## CI gates

GitHub Actions runs the same release-shaped matrix:

- Python 3.11, 3.12, and 3.13
- whitespace check with `git diff --check`
- bytecode compile with `compileall`
- full pytest suite
- coverage report for `hermes_dreaming`, `hermes_ershov`, and `hermes_mnemos`, with an 80% minimum gate
- property-based tests from `tests/test_pbt.py`
- timer-visible provider readiness smoke with `providers doctor --from-systemd`, `status --release-gate --fix-plan`, `soak --fix-plan`, and explicit `--env-file`
- strict systemd release-gate tests that include timer-visible provider readiness and required-provider mismatch checks
- Hermes plugin wrapper smoke
- wheel and source distribution build
- installed wheel smoke for every public console and module alias
- installed source distribution smoke for every public console and module alias
- CodeQL on push, pull request, schedule, and manual dispatch
- Dependabot weekly version-update checks for GitHub Actions and Python package metadata
- OpenSSF Scorecard on weekly schedule and manual dispatch, with SARIF uploaded to code scanning
- checkout-token hardening through `persist-credentials: false` on repository checkout steps
- workflow action pinning to full commit SHAs with adjacent version comments
- workflow-level concurrency for repeatable analysis jobs and job-level `timeout-minutes` on every GitHub Actions job
- release asset workflow build runs under read-only repository permissions; asset upload is isolated to a separate `release`-event-only job with `contents: write`

## Coverage shape

The suite is intentionally mixed:

- unit tests for pure validation, scoring, policy, memory IO, provider parsing, and artifact state
- CLI tests for user-facing command behavior and exit codes
- integration smokes for create, validate, apply, revert, status, update, nightly, and plugin wrapping
- property-based tests for path safety, scoring thresholds, systemd escaping, and soak commit matching
- docs guards that fail when release-facing text drifts from shipped behavior
- local markdown link/image guards for release-facing docs
- release workflow guards that prevent accidental PyPI publishing or release creation
- supply-chain workflow guards for Scorecard permissions, SARIF output, checkout token persistence, full-SHA action pinning, and workflow timeout/concurrency controls
- negative tests for malformed provider output, fabricated provenance, fabricated quotes/snippets, unsafe paths, missing backups, and no-op nightlies

## Stable-release evidence

Passing CI is not enough for stable wording. Stable promotion also needs scheduled-run evidence from the installed VPS checkout:

```bash
hermes ershov soak --state-root ~/.hermes/ershov --since-hours 96 --min-successful 3 --strict-systemd
```

Plain `--strict-systemd` defaults to this 96h/3-run public-stable gate and checks the configured timer provider from the systemd env files. Add `--require-provider deepseek` when the gate must prove DeepSeek specifically, not just any ready provider. Use `--since-hours 30 --min-successful 1 --strict-systemd` only for a fast one-night release-candidate smoke.

Manual service starts and transient timer smokes are useful debug evidence, but they do not satisfy the stable gate.

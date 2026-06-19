# Hermes Ershov Release Checklist

This is a pre-release checklist only.

**Do not tag, publish, or release this repo until Niko explicitly says so.**
Contributor documentation and GitHub templates are welcome, but they do not constitute release approval.

## 1. First pass

- [ ] Read `reviews/final-sanity.md`
- [ ] Read `brief.md`
- [ ] Read `specs/mvp-implementation-plan.md`
- [ ] Confirm no new blockers were introduced after the last QA pass

## 2. Repo hygiene

- [ ] `git status -sb` is clean, or only contains intentional release-facing changes
- [ ] `git diff --check` is clean
- [ ] No stray temp files, caches, or local artifacts are present
- [ ] No secrets, tokens, passwords, or personal paths are in docs or source

## 3. Documentation consistency

- [ ] `README.md` matches the current CLI and artifact layout
- [ ] `brief.md` matches the current contract and non-goals
- [ ] `specs/mvp-implementation-plan.md` matches the shipped implementation
- [ ] `CHANGELOG.md` only lists features that actually exist

## 4. Verification

- [ ] `pytest -q --cov=hermes_dreaming --cov=hermes_ershov --cov=hermes_mnemos --cov-report=term-missing:skip-covered --cov-report=xml --cov-fail-under=80`
- [ ] `pytest -q tests/test_pbt.py`
- [ ] `python -m compileall -q __init__.py src scripts`
- [ ] `git diff --check`
- [ ] `uv sync --locked --extra dev`
- [ ] `python -m build`
- [ ] `python scripts/generate_release_sbom.py --output dist/hermes-ershov-sbom.spdx.json`
- [ ] `python scripts/generate_release_checksums.py --dist dist`
- [ ] `python scripts/verify_release_artifacts.py --dist dist`
- [ ] Smoke wheel and source distribution installs against all public CLI aliases
- [ ] Smoke `ershov providers doctor --provider offline-marker --strict` and confirm it is described as configuration readiness, not end-to-end generation
- [ ] Smoke the CLI with `ershov status`
- [ ] Smoke `ershov create`, `review`, `diff`, `validate`, `apply`, and `discard` on temp fixtures
- [ ] Smoke `ershov compact` on terminal artifacts
- [ ] Smoke `ershov nightly --no-llm`
- [ ] Smoke `ershov nightly --no-llm` with no eligible markers: exits `no-op`, creates no invalid empty artifact
- [ ] Smoke `HERMES_ERSHOV_SESSION_DB=/tmp/state.db ershov nightly --no-llm` with controlled marker input through the installed CLI
- [ ] Smoke the root Hermes plugin wrapper: `python scripts/hermes_plugin_smoke.py`
- [ ] Smoke the local fuzz harness: `pytest -q tests/test_fuzz_harness.py`
- [ ] Smoke `ershov install-cron`
- [ ] Smoke `ershov install-systemd --dry-run`
- [ ] After a real scheduled run, smoke the fast RC gate: `hermes ershov soak --state-root ~/.hermes/ershov --since-hours 30 --min-successful 1 --strict-systemd`
- [ ] When provider readiness is blocked, smoke the secret-safe remediation output: `hermes ershov status --release-gate --state-root ~/.hermes/ershov --require-provider deepseek --fix-plan`
- [ ] Before public stable promotion, smoke the default stable gate: `hermes ershov soak --state-root ~/.hermes/ershov --since-hours 96 --min-successful 3 --strict-systemd`
- [ ] Smoke `ershov update --check` and the real `ershov update --no-verify` path on a disposable repo
- [ ] Confirm `docs/testing.md` still matches the GitHub Actions matrix
- [ ] Confirm local markdown links/images pass the docs guard
- [ ] Confirm the release workflow exports an SPDX SBOM and only uploads attested assets on a GitHub `release` event, without publishing to package indexes
- [ ] Confirm the publish workflow can only publish to PyPI from a GitHub `release` event through the `pypi` environment, PyPI Trusted Publishing, OIDC, and artifact attestations
- [ ] Confirm Dependabot is enabled for GitHub Actions and uv-managed Python package metadata
- [ ] Confirm OpenSSF Scorecard is enabled and uploads SARIF to GitHub code scanning
- [ ] Confirm ClusterFuzzLite PR/manual fuzzing is wired to `.clusterfuzzlite/` and uses pinned actions
- [ ] Confirm PyPI Trusted Publishing is configured on PyPI for `.github/workflows/publish.yml` before any real PyPI release
- [ ] Confirm checkout steps use `persist-credentials: false` unless a job explicitly needs a persisted token
- [ ] Confirm workflow `uses:` actions are pinned to full commit SHAs with version comments
- [ ] Confirm CI, release, and publish workflows use locked uv installs and contain no `pip install` commands
- [ ] Confirm every GitHub Actions job has `timeout-minutes` and repeatable analysis workflows use concurrency cancellation
- [ ] Confirm write permissions for SARIF/code-scanning uploads are scoped to the upload/analyze job

## 5. Release gate

- [ ] Confirm Niko has explicitly approved release
- [ ] Confirm the intended version/tag is still correct
- [ ] Confirm nothing is half-finished in sibling worktrees or other release notes
- [ ] Only then consider a commit, tag, or publish step

## Verdict rule

- If any box is unchecked, the answer is **not released yet**.
- If all boxes are checked, pause and wait for explicit release approval before tagging.

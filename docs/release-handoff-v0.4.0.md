# Hermes Ershov v0.4.0 — Handoff

This is the short follow-up note for the v0.4.0 release lane.

## Read these first

- `docs/release-notes-v0.4.0.md` for the shipped change summary
- `CHANGELOG.md` for the version history
- `docs/install-update.md` for the install and update path
- `docs/safety.md` for the new revert section
- `docs/release-integrity.md` for release asset checksum, SBOM, and attestation verification

## Current release facts

- Plugin version: `0.4.0`
- GitHub release: NOT YET TAGGED — Niko's explicit release gate required
- PyPI publishing: workflow prepared through Trusted Publishing, but NOT RUN — Niko's explicit release gate and PyPI trusted publisher setup required
- PR #3 (`codex/ershov-exit-code-macos-path`) status: still separate, must not be merged as part of this sprint

## What shipped

- **Trust loop**: `ershov revert`, `apply --dry-run`, `apply --priority`, `apply --target-kind`
- **Friction-killer**: `create --from-sessions N`, `create --from-since 7d` (with `--recent` alias), `--no-llm`
- **Discovery**: `providers list`, `providers doctor`, `inbox --apply-ready`, inbox digest "Ready to apply" section
- **Hardening**: `reject --reason` enforced at the command layer

## Files of note

- `src/hermes_dreaming/apply.py` — `revert_artifact`, `ApplyDryRunReport`, filter validation, `_write_proposal` dry-run branch
- `src/hermes_dreaming/artifact.py` — `reverted_at`, `revert_audit_events`, ephemeral `dry_run_report` field
- `src/hermes_dreaming/cli.py` — `revert` subparser, `apply` flags, `inbox --apply-ready`, `providers` subparser, `--from-sessions` / `--from-since` / `--no-llm` flags, time-window parser
- `src/hermes_dreaming/commands/inbox.py` — `apply_ready` filter and `_is_apply_ready`
- `src/hermes_dreaming/commands/digest.py` — `apply_ready_count` / `apply_ready_rows` and the "Ready to apply" section in `render_inbox_digest`
- `src/hermes_dreaming/commands/review.py` — `reject_artifact` reason enforcement at command layer
- `src/hermes_dreaming/providers.py` — `list_providers`, `doctor_providers`, and provider table renderers
- `docs/testing.md` — release test matrix and stable soak evidence boundary
- `docs/release-integrity.md` — consumer-facing release asset verification runbook
- `tests/test_revert.py` (NEW), `tests/test_inbox.py` (NEW), extended `test_apply.py`, `test_cli.py`, `test_providers.py`, `test_review_actions.py`

## Verification gates

- `python -m pytest -q` (266 tests pass)
- `python -m pytest -q tests/test_pbt.py` (property-based safety invariants pass)
- `python -m pytest -q tests/test_fuzz_harness.py` (local fuzz harness seed smoke passes)
- coverage gate `--cov-fail-under=80` (current local total: 84.52%)
- `git diff --check` (clean)
- `python3 -m build` (succeeds)
- `python scripts/generate_release_sbom.py --output dist/hermes-ershov-sbom.spdx.json` (succeeds)
- `python scripts/generate_release_checksums.py --dist dist` (writes `SHA256SUMS`)
- `python scripts/verify_release_artifacts.py --dist dist` (wheel, sdist, SBOM, and checksum bundle pass)
- `docs/release-integrity.md` (documents checksum, SBOM, `gh release verify-asset`, `gh attestation verify`, and stable-soak boundaries)
- Temp-only Ershov smoke with `HERMES_ERSHOV_STATE_ROOT`:
  - `status --release-gate --fix-plan` shows stable blockers, last nightly rows, timer health, next scheduled elapse, and secret-safe provider remediation
  - apply→revert roundtrip on a real fixture
  - `revert --validate` pass/fail audit paths
  - revert without `--validate` reports `post_revert_validation: not-run`
  - post-apply sha no-drift and drift audit paths
  - revert on a non-applied artifact raises and leaves live state untouched
  - revert with a missing backup fails loud
  - revert with live drift still restores from backup and records the event; legacy drift fallback is marked `legacy-degraded`
  - `apply --dry-run` writes nothing and produces a structured report
  - `apply --priority high --target-kind memory` filters correctly
  - `inbox --apply-ready` filters correctly
  - `providers list` prints the table without pinging
  - `providers doctor` checks local configuration readiness and timer-visible env files without network calls, model pings, or secret output; `--fix-plan` prints read-only remediation steps
  - `status --release-gate --fix-plan` and `soak --strict-systemd --fix-plan` surface timer-visible provider readiness and secret-safe remediation; `--require-provider deepseek` blocks offline-marker drift
  - `create --from-sessions 5` prints redaction stats and feeds the bundle
  - provider output rejects schema-valid invented `source_quote` / `snippet` evidence
  - `--no-llm` overrides `--provider` to `offline-marker`
  - `reject` without a reason returns exit 1

## Definition of done (for the release gate)

- [x] `git status -sb` clean (except intentional v0.4.0 changes)
- [x] `git diff --check` clean
- [x] `pytest -q` passes (266 tests)
- [x] `pytest -q tests/test_pbt.py` passes
- [x] `pytest -q tests/test_fuzz_harness.py` passes
- [x] `python -m build` succeeds
- [x] Each new + modified command smoke-tested on temp fixtures
- [x] CHANGELOG, release notes, handoff all written
- [ ] NO tag, NO GitHub release, NO PyPI publish — Niko's call
- [ ] PyPI Trusted Publisher must be configured for `.github/workflows/publish.yml` / environment `pypi` before publish

## What needs Niko's eyes

- **Revert command behavior**: new successful applies record per-write post-apply shas in `backup_records`, so drift detection can distinguish a clean applied file from an operator edit after apply. Legacy artifacts still fall back to backup-vs-live drift comparison, but those events are labeled `legacy-degraded` in audit output and `REVERT.md`.
- **Provider doctor behavior**: `providers doctor --strict` is a local configuration gate only. With `--from-systemd`, it checks the default Hermes Ershov systemd `EnvironmentFile` paths the timer will see; repeatable `--env-file` remains available for explicit layouts; `--fix-plan` prints secret-safe remediation commands and `<secret>` placeholders without changing files. These paths avoid prompt/model calls, never print secret values, and fail closed when explicit `--provider` disagrees with `HERMES_ERSHOV_PROVIDER`. It is not an end-to-end generation test.
- **Update command behavior**: `ershov update` still refuses dirty/diverged branches and rolls back failed verification, but now retries one transient network/timeout failure during `git fetch` or `git pull --ff-only`; `--git-timeout-seconds` can be raised for slow VPS/GitHub links.
- **Apply filter behavior**: filtered-out proposals stay `approved` so a later apply with a different filter can still land them. This is the right behavior for the use case, but it's a state-machine subtlety. Read `apply_artifact` to confirm.
- **Re-run of reject without reason**: the CLI now exits 1 instead of erroring in argparse. If you want a different code, it's a one-liner in `cli.py`.
- **`--from-since` count heuristic**: 4 sessions per day, capped at 50. If you want a different default, change the constant in `_resolve_creation_sources`.

## Bottom line

`v0.4.0` is built, verified, and ready for the release gate. It is **not** tagged or published yet. Niko's explicit approval is required for the tag, GitHub release, and PyPI publish.

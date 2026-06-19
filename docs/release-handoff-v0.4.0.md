# Hermes Ershov v0.4.0 — Handoff

This is the short follow-up note for the v0.4.0 release lane.

## Read these first

- `docs/release-notes-v0.4.0.md` for the shipped change summary
- `CHANGELOG.md` for the version history
- `docs/install-update.md` for the install and update path
- `docs/safety.md` for the new revert section

## Current release facts

- Plugin version: `0.4.0`
- GitHub release: NOT YET TAGGED — Niko's explicit release gate required
- PR #3 (`codex/ershov-exit-code-macos-path`) status: still separate, must not be merged as part of this sprint

## What shipped

- **Trust loop**: `ershov revert`, `apply --dry-run`, `apply --priority`, `apply --target-kind`
- **Friction-killer**: `create --from-sessions N`, `create --from-since 7d` (with `--recent` alias), `--no-llm`
- **Discovery**: `providers list`, `inbox --apply-ready`, inbox digest "Ready to apply" section
- **Hardening**: `reject --reason` enforced at the command layer

## Files of note

- `src/hermes_dreaming/apply.py` — `revert_artifact`, `ApplyDryRunReport`, filter validation, `_write_proposal` dry-run branch
- `src/hermes_dreaming/artifact.py` — `reverted_at`, `revert_audit_events`, ephemeral `dry_run_report` field
- `src/hermes_dreaming/cli.py` — `revert` subparser, `apply` flags, `inbox --apply-ready`, `providers` subparser, `--from-sessions` / `--from-since` / `--no-llm` flags, time-window parser
- `src/hermes_dreaming/commands/inbox.py` — `apply_ready` filter and `_is_apply_ready`
- `src/hermes_dreaming/commands/digest.py` — `apply_ready_count` / `apply_ready_rows` and the "Ready to apply" section in `render_inbox_digest`
- `src/hermes_dreaming/commands/review.py` — `reject_artifact` reason enforcement at command layer
- `src/hermes_dreaming/providers.py` — `list_providers` and `render_providers_table`
- `tests/test_revert.py` (NEW), `tests/test_inbox.py` (NEW), extended `test_apply.py`, `test_cli.py`, `test_providers.py`, `test_review_actions.py`

## Verification gates

- `python -m pytest -q` (182 tests pass)
- `git diff --check` (clean)
- `python3 -m build` (succeeds)
- Temp-only Ershov smoke with `HERMES_ERSHOV_STATE_ROOT`:
  - apply→revert roundtrip on a real fixture
  - revert on a non-applied artifact raises and leaves live state untouched
  - revert with a missing backup fails loud
  - revert with live drift still restores from backup and records the event
  - `apply --dry-run` writes nothing and produces a structured report
  - `apply --priority high --target-kind memory` filters correctly
  - `inbox --apply-ready` filters correctly
  - `providers list` prints the table without pinging
  - `create --from-sessions 5` prints redaction stats and feeds the bundle
  - `--no-llm` overrides `--provider` to `offline-marker`
  - `reject` without a reason returns exit 1

## Definition of done (for the release gate)

- [x] `git status -sb` clean (except intentional v0.4.0 changes)
- [x] `git diff --check` clean
- [x] `pytest -q` passes (182 tests)
- [x] `python -m build` succeeds
- [x] Each new + modified command smoke-tested on temp fixtures
- [x] CHANGELOG, release notes, handoff all written
- [ ] NO tag, NO GitHub release, NO PyPI publish — Niko's call

## What needs Niko's eyes

- **Revert command behavior**: the drift detection compares live content to the recorded backup snapshot before restoring. If you want per-write post-apply shas tracked in the manifest (for stronger post-apply audit), that's a small follow-up.
- **Apply filter behavior**: filtered-out proposals stay `approved` so a later apply with a different filter can still land them. This is the right behavior for the use case, but it's a state-machine subtlety. Read `apply_artifact` to confirm.
- **Re-run of reject without reason**: the CLI now exits 1 instead of erroring in argparse. If you want a different code, it's a one-liner in `cli.py`.
- **`--from-since` count heuristic**: 4 sessions per day, capped at 50. If you want a different default, change the constant in `_resolve_creation_sources`.

## Bottom line

`v0.4.0` is built, verified, and ready for the release gate. It is **not** tagged or published yet. Niko's explicit approval is required for the tag, GitHub release, and PyPI publish.

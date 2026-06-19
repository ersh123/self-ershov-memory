# Hermes Ershov v0.4.0 — Release Notes

**Headline:** *The trust loop and the friction-killer.*

v0.4.0 makes Ershov much safer to trial in real operator loops (revert, dry-run, selective apply) and removes the harvest-to-create two-step (one command, real sessions, redacted). It is a public beta / release candidate, not a stable release claim until scheduled-run soak evidence exists.

## What's new

### Trust loop

- **`ershov revert <artifact>`** restores live files from the recorded backups and rolls an `applied` artifact back to a `reverted` state. Requires the artifact to be in `applied` status; anything else fails loud.
  - Drift detection: if the live file changed after apply, a `drift_detected` audit event is recorded, but the restore still runs from backup.
  - On a missing backup file, revert aborts, leaves live state untouched, and records a `revert_failed` audit event.
  - Writes a `REVERT.md` next to the artifact summarizing what was restored, what was rolled back, what drifted, and what failed.
  - Non-interactive callers (cron, pipe) must pass `--yes`. The CLI exits with code 2 when a confirmation prompt is needed, so scripts can distinguish "needs confirmation" from a real failure.
- **`ershov apply --dry-run`** previews the apply path without writing live state or creating backups. The result includes a structured `dry_run_report` (would-apply / would-skip / would-backup lists, and per-filter exclusions).
- **`ershov apply --priority {low,normal,high}`** and **`--target-kind {memory,user,skill,fact}`** filter which approved proposals land. Filters compose. Filtered-out proposals stay `approved` so a later apply with a different filter can still land them.

### Friction-killer

- **`ershov create --from-sessions N`** auto-harvests N recent local Hermes sessions from the SessionDB, feeds the resulting redacted bundle as a source, and stages the artifact in one step. Always prints `harvest:`, `sessions:`, and `redactions:` to stdout before staging.
- **`ershov create --from-since 7d`** (also `12h`, `2w`) is a time-window alternative. The count is derived from the window and capped at 50 sessions.
- **`--recent N`** is preserved as a back-compat alias for `--from-sessions N`.
- **`--no-llm`** is a shorthand for `--provider offline-marker` on `create`, `review`, and `nightly`. Useful for cron jobs that should never reach an external LLM by accident.

### Discovery and inbox

- **`ershov providers list`** prints a table with `NAME`, `KIND`, `STATUS` (always | optional | missing), and `NOTES` for the built-in providers. No external services are pinged.
- **`ershov inbox --apply-ready`** filters to artifacts where every non-rejected proposal is approved (or already applied) and the artifact is in `staged`, `approved`, or `applied` status. Composes with `--state` and `--priority`.
- The **inbox digest** (`ershov digest --inbox`) now surfaces a "Ready to apply" section and an `Apply-ready count` field at the top.

### Hardening

- **`reject --reason`** is enforced at the command layer (`commands/review.py:reject_artifact()`), not just the CLI parser. Any caller (CLI, library, plugin) is constrained by the same rule. `ReviewError` is raised on missing, empty, or whitespace-only reasons.
- **`ershov nightly --no-llm`** now exits as a clean `no-op` when the recent harvest has no eligible `MEMORY:` / `DREAM:` markers. It records the run and writes digests, but does not create an invalid empty artifact.
- **`ershov nightly`** takes a state-root lock before harvesting. A concurrent run fails before writing source bundles, artifacts, digests, or ledger state, so unattended timers and manual smokes cannot race each other.
- **`ershov nightly`** records a failed run in `runs.jsonl` when the pipeline crashes before normal completion. `soak` can therefore catch recent unattended failures instead of silently trusting older success evidence.
- **`HERMES_ERSHOV_SESSION_DB=/path/to/state.db`** forces harvest/nightly to use a specific SessionDB-compatible SQLite file before the live Hermes SessionDB. This makes installed-CLI smoke tests deterministic.
- **`ershov soak`** is the read-only scheduled-run gate. It checks recent successful `nightly` runs in `runs.jsonl`, fails on recent nightly failures by default, can require the user systemd timer to be enabled, active, loaded, pointed at `hermes-ershov-nightly.service`, and scheduled for a next elapse, and can require a matching ledger source, code revision, and clean checkout such as `--require-source systemd --require-commit <sha> --require-clean`. Commit matching requires at least 7 git hash characters on both sides.
- The root Hermes plugin wrapper now propagates non-zero CLI failures, so `hermes ershov ...` can be used as a real shell gate instead of only a human-readable wrapper.

## Data model

Two additive fields on `DreamArtifact`:

- `reverted_at: str | None` — ISO timestamp of the last revert, if any
- `revert_audit_events: list[dict]` — the revert audit trail (drift events, restore summary, partial-failure summary)

A third field, `dry_run_report`, is attached in-memory only during a single apply dry-run call and excluded from `manifest.json` so the on-disk contract stays stable across the dry-run feature.

## Migration / compatibility

- The `recent` flag is unchanged in behavior; `--from-sessions` is the new preferred name. Both work.
- The `reject` enforcement is stricter than v0.3.0. Library callers that previously passed `reason=None` to `reject_artifact` will now raise `ReviewError`.
- `apply` gained three optional flags (`--dry-run`, `--priority`, `--target-kind`). Existing invocations are unchanged.

## Verification

- `pytest -q` passes (163 tests).
- `python scripts/hermes_plugin_smoke.py` passes and exercises the root Hermes plugin wrapper with a controlled SessionDB nightly run.
- `python -m build` succeeds, and both wheel and source distribution installs are smoked against all public CLI aliases.
- `git diff --check` clean.
- Smoke-tested on temp fixtures for: `revert` (roundtrip, drift, missing backup, partial failure), `apply --dry-run` (preview without writes), `apply --priority` and `--target-kind` (filters), `inbox --apply-ready`, `providers list`, `--from-sessions` with redaction stats, `nightly --no-llm` no-op/staged paths, nightly lock rejection, nightly crash ledger recording, deterministic SessionDB override, plugin wrapper failure propagation, and source/commit/clean-checkout-aware `soak` pass/fail gates.

## Known limitations

- Stable release wording waits for at least one real scheduled systemd/cron run followed by a passing `ershov soak --require-timer --require-source systemd --require-commit <installed-sha> --require-clean`. Manual service starts and transient timer smokes are useful evidence, but they are not the same as an overnight scheduled run.
- Revert does not re-run validation. It is a restore from backup, not a re-apply. If a reverted proposal is reapplied, validation runs normally as part of the apply path.
- Drift detection compares the live file's pre-restore content to the recorded backup snapshot, but does not currently track per-write post-apply shas. Adding a per-write post-apply sha is a v0.5.0 candidate.
- The `--from-since` window-to-count heuristic is conservative (4 sessions per day, capped at 50). If you want a more aggressive count, use `--from-sessions N` directly.
- `soak` proves scheduled-run evidence only after a real timer/cron run has occurred; it does not itself wait overnight or run providers.

## Bottom line

This release delivers the two things that turn Ershov from "demo-able" to "operator's default nightly loop":

1. **You can undo an apply.** Revert is the trust headline.
2. **You can stage from real sessions in one command.** `--from-sessions` is the friction-killer.

Direction A (operator trust) and Direction B (friction-killer) from the brainstorm — both shipped, both tested, both documented.

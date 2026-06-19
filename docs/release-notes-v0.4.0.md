# Hermes Ershov v0.4.0 — Release Notes

**Headline:** *The trust loop and the friction-killer.*

v0.4.0 makes Ershov much safer to trial in real operator loops (revert, dry-run, selective apply) and removes the harvest-to-create two-step (one command, real sessions, redacted). It is a public beta / release candidate, not a stable release claim until scheduled-run soak evidence exists.

## What's new

### Trust loop

- **`ershov revert <artifact>`** restores live files from the recorded backups, removes files that were created by apply, and rolls an `applied` artifact back to a `reverted` state. Requires the artifact to be in `applied` status; anything else fails loud.
  - Drift detection: if the live file changed after apply, a `drift_detected` audit event is recorded with live and expected shas when available, but the restore still runs from backup.
  - On a missing backup file, revert aborts, leaves live state untouched, and records a `revert_failed` audit event.
  - `--validate` runs the existing artifact validator after restore and records `revert_validation_passed` or `revert_validation_failed` in the audit trail and `REVERT.md`. Without `--validate`, the CLI and `REVERT.md` explicitly report `post_revert_validation: not-run`.
  - Writes a `REVERT.md` next to the artifact summarizing what was restored, what was rolled back, what drifted, what validation found, and what failed.
  - Non-interactive callers (cron, pipe) must pass `--yes`. The CLI exits with code 2 when a confirmation prompt is needed, so scripts can distinguish "needs confirmation" from a real failure.
- **`ershov apply --dry-run`** previews the apply path without writing live state or creating backups. The result includes a structured `dry_run_report` (would-apply / would-skip / would-backup lists, and per-filter exclusions).
- **`ershov apply --priority {low,normal,high}`** and **`--target-kind {memory,user,skill,fact}`** filter which approved proposals land. Filters compose. Filtered-out proposals stay `approved` so a later apply with a different filter can still land them.

### Friction-killer

- **`ershov create --from-sessions N`** auto-harvests N recent local Hermes sessions from the SessionDB, feeds the resulting redacted bundle as a source, and stages the artifact in one step. Always prints `harvest:`, `sessions:`, and `redactions:` to stdout before staging.
- **`ershov create --from-since 7d`** (also `12h`, `2w`) is a time-window alternative. The count is derived from the window and capped at 50 sessions.
- **`--recent N`** is preserved as a back-compat alias for `--from-sessions N`.
- **`--no-llm`** is a shorthand for `--provider offline-marker` on `create`, `review`, and `nightly`. Useful for cron jobs that should never reach an external LLM by accident.

### Discovery and inbox

- **`ershov providers list`** prints a table with `NAME`, `KIND`, `STATUS` (always | optional | missing), and `NOTES` for the built-in providers (`offline-marker`, `openai-compatible`, `deepseek`, `openrouter`, `ollama`). No external services are pinged.
- **`ershov providers doctor`** checks local provider configuration readiness without sending prompts or pinging model APIs. It reports dependency presence, API-key env-var presence, base URL shape, and local-only notes without printing secret values. `--from-systemd` checks the default Hermes Ershov timer `EnvironmentFile` paths; repeatable `--env-file` flags test explicit systemd layouts; `--fix-plan` prints secret-safe remediation steps for blocked providers. These paths avoid printing secret values and, when `--provider` is explicit, fail closed if `HERMES_ERSHOV_PROVIDER` points at a different provider. It is not an end-to-end generation test; use an explicit review/create run when you want to exercise a model call. `--strict` turns the local readiness check into a shell gate.
- **`ershov inbox --apply-ready`** filters to artifacts where every non-rejected proposal is approved (or already applied) and the artifact is in `staged`, `approved`, or `applied` status. Composes with `--state` and `--priority`.
- The **inbox digest** (`ershov digest --inbox`) now surfaces a "Ready to apply" section and an `Apply-ready count` field at the top.

### Hardening

- **`reject --reason`** is enforced at the command layer (`commands/review.py:reject_artifact()`), not just the CLI parser. Any caller (CLI, library, plugin) is constrained by the same rule. `ReviewError` is raised on missing, empty, or whitespace-only reasons.
- **`ershov nightly --no-llm`** now exits as a clean `no-op` when the recent harvest has no eligible `MEMORY:` / `DREAM:` markers. It records the run and writes digests, but does not create an invalid empty artifact.
- **`ershov nightly`** takes a state-root lock before harvesting. A concurrent run fails before writing source bundles, artifacts, digests, or ledger state, so unattended timers and manual smokes cannot race each other.
- **`ershov nightly`** records a failed run in `runs.jsonl` when the pipeline crashes before normal completion. `soak` can therefore catch recent unattended failures instead of silently trusting older success evidence.
- **`HERMES_ERSHOV_SESSION_DB=/path/to/state.db`** forces harvest/nightly to use a specific SessionDB-compatible SQLite file before the live Hermes SessionDB. This makes installed-CLI smoke tests deterministic.
- **`ershov soak`** is the read-only scheduled-run gate. It checks recent successful `nightly` runs in `runs.jsonl`, fails on recent nightly failures by default, can require the user systemd timer to be enabled, active, loaded, pointed at `hermes-ershov-nightly.service`, and scheduled for a next elapse, can check timer-visible provider readiness from systemd env files, and can require a matching ledger source, code revision, and clean checkout such as `--require-source systemd --require-commit <sha> --require-clean`. `--strict-systemd` bundles the stable release gate, auto-detects the current checkout commit, reads timer-visible provider readiness, and refuses a dirty current git checkout. Add `--require-provider deepseek` when the gate must prove DeepSeek specifically instead of any ready provider. Add `--fix-plan` to append the secret-safe provider remediation plan to text output when readiness is blocked. With no explicit overrides it defaults to the public-stable promotion gate: `--min-successful 3 --since-hours 96 --strict-systemd`. Use `--since-hours 30 --min-successful 1 --strict-systemd` only as a fast one-night release-candidate smoke. Commit matching requires at least 7 git hash characters on both sides.
- **`report-card` and `digest` backup details** now separate real backup file copies from rollback evidence records and created-file tombstones, so apply-created files do not look like missing backup coverage.
- **`ershov revert --validate`** adds a post-restore validation gate for rollback drills and release smokes without changing the default restore semantics.
- **Per-write post-apply shas** are now stored in `backup_records` on successful apply and used by revert drift detection, so a normal apply→revert is not mislabeled as drift while operator edits after apply still are.
- **Legacy revert evidence** is now labeled as `legacy-degraded` when an old artifact lacks post-apply shas and revert has to infer drift from backup-vs-live comparison.
- **Provider quote grounding** now rejects schema-valid model proposals whose `source_quote` or `snippet` does not match a cited source line, closing the easy "valid JSON, invented evidence" path.
- **`ershov status --release-gate`** now renders the strict systemd stable gate inline: current commit, dirty state, last nightly run, last successful nightly, last failed nightly, timer next elapse, timer-visible provider readiness, matching scheduled runs, recent failures, and exact blockers. Add `--fix-plan` for the same secret-safe provider remediation plan inline with the blockers.
- **`ershov update` verification** uses an isolated uv editable test environment with pytest and Hypothesis when the checkout has `pyproject.toml`, so installed plugin updates do not depend on the runtime Python already having dev dependencies.
- **`ershov update` fetch/pull resilience** retries one transient network/timeout failure during `git fetch` or `git pull --ff-only` and exposes `--git-timeout-seconds` for slow VPS/GitHub links without weakening dirty-tree, fast-forward, or verification checks.
- The root Hermes plugin wrapper now propagates non-zero CLI failures, so `hermes ershov ...` can be used as a real shell gate instead of only a human-readable wrapper.

## Data model

Three additive fields on `DreamArtifact`:

- `reverted_at: str | None` — ISO timestamp of the last revert, if any
- `revert_audit_events: list[dict]` — the revert audit trail (drift events, restore summary, partial-failure summary)
- `backup_records: list[dict]` — per-target backup evidence; existing files point at a backup path, files created by apply are recorded as `existed_before=false` tombstones so revert can remove them, and successful applies record `post_apply_exists` plus `post_apply_sha256` for drift checks

`dry_run_report` is attached in-memory only during a single apply dry-run call and excluded from `manifest.json` so the on-disk contract stays stable across the dry-run feature.

## Migration / compatibility

- The `recent` flag is unchanged in behavior; `--from-sessions` is the new preferred name. Both work.
- The `reject` enforcement is stricter than v0.3.0. Library callers that previously passed `reason=None` to `reject_artifact` will now raise `ReviewError`.
- `apply` gained three optional flags (`--dry-run`, `--priority`, `--target-kind`). Existing invocations are unchanged.

## Verification

- `pytest -q` passes (266 tests).
- `pytest -q tests/test_pbt.py` passes and keeps the property-based path safety, systemd escaping, scoring, and soak commit-prefix invariants visible in the release matrix.
- `pytest -q tests/test_fuzz_harness.py` passes and keeps the ClusterFuzzLite/Atheris Python fuzz harness locally smoke-tested.
- Coverage gate passes with `--cov-fail-under=80` (current local total: 84.52%).
- `python scripts/hermes_plugin_smoke.py` passes and exercises the root Hermes plugin wrapper with a controlled SessionDB nightly run.
- `python -m build` succeeds, and both wheel and source distribution installs are smoked against all public CLI aliases.
- `python scripts/generate_release_checksums.py --dist dist` writes `SHA256SUMS` for the wheel, source distribution, and SPDX SBOM release assets.
- `python scripts/verify_release_artifacts.py --dist dist` verifies wheel metadata, source distribution metadata, SPDX SBOM package coverage, purl refs, locked SHA256 checksums, root dependency relationships, and `SHA256SUMS` integrity.
- `docs/release-integrity.md` documents the public checksum, SBOM, `gh release verify-asset`, `gh attestation verify`, and stable-soak boundary for future GitHub Release consumers.
- `git diff --check` clean.
- Smoke-tested on temp fixtures for: `revert` (roundtrip, `--validate`, validation failure after restore, post-apply sha no-drift path, post-apply sha drift path, `legacy-degraded` drift fallback, missing backup, partial failure), `apply --dry-run` (preview without writes), `apply --priority` and `--target-kind` (filters), `inbox --apply-ready`, `providers list`, `providers doctor` configuration readiness plus `--from-systemd`, `--fix-plan`, and explicit env-file checks, `--from-sessions` with redaction stats, `nightly --no-llm` no-op/staged paths, nightly lock rejection, nightly crash ledger recording, deterministic SessionDB override, plugin wrapper failure propagation, and source/commit/clean-checkout/provider-aware `soak` pass/fail gates.

## Known limitations

- Stable release wording waits for several real scheduled systemd runs followed by a passing `hermes ershov soak --strict-systemd`. The strict shortcut defaults to `hermes ershov soak --since-hours 96 --min-successful 3 --strict-systemd` and now checks timer-visible provider readiness; add `--require-provider deepseek` when DeepSeek is part of the release claim. A one-night `--since-hours 30 --min-successful 1 --strict-systemd` run is only release-candidate smoke evidence. Manual service starts and transient timer smokes are useful evidence, but they are not the same as overnight scheduled runs.
- Revert does not re-run validation by default. Use `ershov revert --validate` for a post-restore validation gate. Without it, the CLI and `REVERT.md` say `post_revert_validation: not-run`. If a reverted proposal is reapplied, validation runs normally as part of the apply path.
- Legacy artifacts created before post-apply shas still use backup-vs-live drift comparison. Those events are labeled `legacy-degraded`; new successful applies use recorded post-apply shas.
- The `--from-since` window-to-count heuristic is conservative (4 sessions per day, capped at 50). If you want a more aggressive count, use `--from-sessions N` directly.
- `soak` proves scheduled-run evidence only after a real timer/cron run has occurred; it does not itself wait overnight or run providers.

## Bottom line

This release delivers the two things that turn Ershov from "demo-able" to "operator's default nightly loop":

1. **You can undo an apply.** Revert is the trust headline.
2. **You can stage from real sessions in one command.** `--from-sessions` is the friction-killer.

Direction A (operator trust) and Direction B (friction-killer) from the brainstorm — both shipped, both tested, both documented.

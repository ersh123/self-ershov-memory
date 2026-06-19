# What Ershov can and cannot mutate

Hermes Ershov is staged self-improvement. It can make durable changes, but only through a reviewable artifact and an explicit apply step.

## It can mutate

- live memory entries in `memory.md`
- live user entries in `user.md`
- staged skill files matching `skills/<name>.md`, such as `skills/review.md`
- staged JSONL fact records in `facts.jsonl`

It does not write arbitrary "safe-looking" relative paths. Every staged proposal must match the target-kind allowlist before apply can write it.

In the current offline fixture, the demo shows three target kinds:

- `fact`
- `memory`
- `user`

## It cannot mutate

- the live root during `review`, `summarize`, `diff`, or `validate`
- the live root during `nightly`
- the source bundle itself
- paths outside the live root
- absolute paths or path traversal targets like `..`
- safe relative paths that are not in the target-kind allowlist
- hidden side channels or a second source of truth

## Guard rails

- proposals are staged first, then reviewed
- `approve` and `reject` only touch artifact metadata until you apply
- `apply` validates before it writes
- `apply --dry-run` previews the change without writing live state or creating a backup
- `apply --priority` and `apply --target-kind` filter which approved proposals land; filtered-out proposals stay approved so a later apply with a different filter can still land them
- `revert` restores live files from the recorded backups and rolls the artifact back to a `reverted` state. Drift detection records a `drift_detected` audit event when the live file changed after apply, but the restore still runs from backup
- backups are taken before live writes
- unsafe proposal paths are rejected instead of being normalized into something dangerous
- `reject` requires a non-empty reason at the command layer; the same rule applies to any library or plugin caller
- `nightly` is an orchestration loop only: it harvests, stages, writes digests, compacts terminal artifacts, and records the run ledger. It never applies live memory.
- `install-systemd` only installs a timer/service/wrapper for `nightly`; the timer runs outside the Hermes gateway process and does not restart Hermes.
- `soak` is read-only: it inspects the run ledger and optionally the user systemd timer state, expected timer unit, next scheduled elapse, run source, git commit, and clean-checkout marker. It does not create artifacts, run providers, or mutate live memory.

## Revert in plain English

`ershov revert <artifact>` does three things, in this order:

1. Loads the artifact and checks that it is in the `applied` state. Anything else fails loud.
2. For each path in `artifact.backup_paths`, copies the recorded backup back to its original live location. If the live file was missing at apply time, the file is recreated from the backup. Drift between the live file and the pre-apply snapshot is recorded as a `drift_detected` audit event, but the restore still runs.
3. Marks the artifact's `applied` proposals back to `approved` and writes a `REVERT.md` summary next to the artifact describing what was restored and what failed.

Revert does **not** re-run validation. It is a restore from backup, not a re-apply. If you want to re-apply the same proposals, run `ershov apply <artifact>` again with the same filters. If you want to apply a subset, pass `--priority` or `--target-kind`.

Non-interactive callers (cron, pipe) must pass `--yes`. The CLI exits with code 2 when a confirmation prompt is needed, so scripts can distinguish "needs confirmation" from a real failure.

## Practical rule

If you would not be comfortable restoring it from a backup, do not point Ershov at it. Keep the live root boring, explicit, and easy to inspect on disk.

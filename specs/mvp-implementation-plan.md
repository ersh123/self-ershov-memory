# Hermes Ershov MVP Implementation Plan

## Purpose

Hermes Ershov is a standalone, artifact-first self-improvement engine for staged memory, user, skill, and fact updates.

The repo has one job: read explicit local inputs, stage reviewable proposals, and apply only approved changes through a guarded write path.

## What shipped
The current MVP includes:

- `ershov create`, `diff`, `validate`, `apply`, `discard`, `report-card`, `status`, `revert`, `providers list`
- `apply --dry-run`, `apply --priority`, `apply --target-kind` for selective and preview-only applies
- `inbox --apply-ready` to surface artifacts that are unblocked
- `create --from-sessions N` / `--from-since 7d` (and the `--recent` alias) for friction-killer session harvesting with redacted bundle output
- `--no-llm` shorthand for `--provider offline-marker` on `create`, `review`, and `nightly`
- a directory-based artifact format with `manifest.json`, `REPORT.md`, `sources.jsonl`, `proposals.jsonl`, `audit.jsonl`, and `REVERT.md` (after revert)
- deterministic offline proposal extraction from explicit `MEMORY:` / `DREAM:` markers
- OpenAI-compatible providers behind the `llm` extra: generic `openai-compatible`, DeepSeek, and OpenRouter
- an Ollama provider that targets a local server
- validation for path safety, duplicate targets, provenance, and secret-like content
- backups before apply, plus explicit discard/archive behavior
- reject reason enforcement at the command layer (not just the CLI)
- unit and integration tests for the data model, validation, CLI flow, apply/discard semantics, revert roundtrip, apply filters, and provider discovery

## Scope and non-goals

### In scope
- explicit source bundles or imported snapshots
- staged artifact creation
- diff rendering for review
- guarded apply with backups
- discard without live mutation
- reproducible tests

### Out of scope
- background ershov or idle-time auto consolidation
- implicit mutation during analysis
- gateway or dashboard integration
- broad sync to arbitrary external systems
- secret ingestion or private operational data capture

## Package layout

```text
src/hermes_dreaming/
├── __init__.py
├── __main__.py
├── analyze.py
├── apply.py
├── artifact.py
├── cli.py
├── collect.py
├── providers.py
└── validation.py
```

### Roles
- `artifact.py` owns the dataclasses, JSON serialization, and load/save helpers.
- `collect.py` turns explicit source roots into source snapshots.
- `providers.py` contains the offline marker parser and the optional OpenAI-compatible provider.
- `analyze.py` builds artifacts and renders diffs.
- `validation.py` blocks unsafe or malformed proposals.
- `apply.py` performs guarded apply and discard actions.
- `cli.py` stays thin and only handles argument parsing and output.

## Command surface

### `ershov create`
Creates a staged artifact from one or more `--source` roots, or from local sessions via `--from-sessions N` / `--from-since 7d` (with `--recent N` as a back-compat alias). Always prints `harvest:`, `sessions:`, and `redactions:` to stdout before staging when harvest ran. `--no-llm` is a shorthand for `--provider offline-marker`.

Defaults:
- `--live-root` defaults to the current directory
- `--artifact-root` defaults to `./.ershov/artifacts`
- `--provider` defaults to `offline-marker`

### `ershov apply`
Applies approved proposals, writes backups first, and updates the artifact status. `--approve` remains as a compatibility shortcut that records approvals before apply. New flags:
- `--dry-run` previews the apply without writing live state or creating backups. Returns a structured report.
- `--priority low,normal,high` filters which approved proposals land by priority.
- `--target-kind memory,user,skill,fact` filters by destination. Filters compose; filtered-out proposals stay approved so a later apply with a different filter can still land them.

### `ershov revert`
Restores live files from the recorded backups and rolls the artifact back to a `reverted` state. Requires the artifact to be in `applied` status. Drift detection records a `drift_detected` audit event when the live file changed after apply, but the restore still runs from backup. Writes `REVERT.md` next to the artifact with a summary. Non-interactive callers must pass `--yes`.

### `ershov review`
Creates a staged artifact from one or more `--source` roots, or opens an existing artifact with `--open` to print the artifact path and next commands.

### `ershov summarize`
Prints a concise decision brief for an existing artifact, including proposal state counts and recent audit entries.

### `ershov approve`
Records approvals in artifact metadata without applying anything to live state.

### `ershov reject`
Records rejected proposals and a reason in artifact metadata without applying anything to live state.

### `ershov diff`
Prints live-target unified diffs for each proposal when a live root is available, otherwise falls back to the staged report and proposal summary.

### `ershov report-card`
Prints a redacted shareable summary for an existing artifact, with an optional JSON companion.

### `ershov validate`
Runs the validation gate without mutating live state.

### `ershov apply`
Applies approved proposals, writes backups first, and updates the artifact status. `--approve` remains as a compatibility shortcut that records approvals before apply.

### `ershov discard`
Marks the artifact discarded and moves it into the archive root without touching live files.

### `ershov status`
Lists known artifacts in the artifact root.

### `ershov providers list`
Prints a table of the built-in providers (`offline-marker`, `openai-compatible`, `deepseek`, `ollama`) with their `STATUS` (always, optional, missing) and `NOTES`. Does not ping external services.

## Artifact format

Canonical artifact directory contents:

- `manifest.json` stores the machine-readable state
- `REPORT.md` stores the human-readable summary
- `sources.jsonl` stores source snapshots and provenance
- `proposals.jsonl` stores the staged proposal records
- `audit.jsonl` stores the proposal decision audit trail

Required proposal fields:
- `id`
- `target_kind`
- `target_path`
- `mode`
- `summary`
- `provenance`
- `proposed_text`
- `approved`
- `rejected`
- `rejection_reason`
- `applied`

Current supported proposal modes:
- `append_text`
- `jsonl_append`

## Validation and safety

The validation layer rejects or flags:

- target paths that escape the live root
- duplicate targets with conflicting payloads
- provider output that fails schema validation before artifact write
- missing provenance
- secret-like content in source or proposal text
- malformed JSON payloads for JSONL append proposals
- live roots that do not exist

Apply is intentionally boring:

1. validate first
2. back up the target file if it exists
3. write the new content
4. update the artifact status to `applied`

Discard is intentionally boring too:

1. update the artifact status to `discarded`
2. move the artifact directory into the archive root
3. leave live files untouched

## Tests

- artifact round-trip coverage
- validation edge cases
- apply and discard behavior
- CLI command flow
- smoke coverage for the public package surface

## Release note

The MVP shipped as `v0.1.1` after the release checklist and explicit Niko approval. Use `docs/release-checklist.md` before any future tag, publish, or public handoff.

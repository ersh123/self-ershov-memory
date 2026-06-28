# self-ershov-memory

<p align="center">
  <img src="assets/readme/hero-memory-factory.png" alt="self-ershov-memory isometric memory factory" width="100%">
</p>

[![CI](https://github.com/ersh123/self-ershov-memory/actions/workflows/ci.yml/badge.svg)](https://github.com/ersh123/self-ershov-memory/actions/workflows/ci.yml)
[![CodeQL](https://github.com/ersh123/self-ershov-memory/actions/workflows/codeql.yml/badge.svg)](https://github.com/ersh123/self-ershov-memory/actions/workflows/codeql.yml)
![tests](https://img.shields.io/badge/tests-passing-brightgreen)
![coverage](https://img.shields.io/badge/product%20coverage-100%25-brightgreen)

Self-audit memory engine for Hermes operators. It reads Hermes dialogue history, extracts durable operator corrections, snapshots memory files, and updates `USER.md` / `MEMORY.md` only through explicit, reviewable runs.

## What it does

<p align="center">
  <img src="assets/readme/memory-audit-pipeline.png" alt="Memory audit pipeline" width="100%">
</p>

```text
~/.hermes/state.db dialogs
  -> correction/rule extraction
  -> Error Bank extraction for fixed compiler/runtime/test failures
  -> controlled context checkpoint/rebuild sidecar
  -> topic classification + dedup
  -> snapshot before write
  -> USER.md / MEMORY.md / error-bank / context / skill updates
```

- **Idempotent**: repeat runs skip already-known corrections.
- **Grounded**: durable memory comes from dialogue evidence, not fabricated assumptions.
- **Safe by default**: `--dry-run` is the default; `--execute` is explicit.
- **Provider policy**: direct `deepseek` is the fallback LLM path.


## Before → approval → after

<p align="center">
  <img src="assets/readme/before-approval-after.png" alt="Before approval after evidence" width="100%">
</p>

`self-ershov-memory` is built around an explicit memory approval loop. The engine never silently rewrites operator memory. Real fixture with before/after files and approval transcript: [`docs/before-after-approval.md`](docs/before-after-approval.md).

| Stage | What happens | Write access |
|---|---|---|
| **Before** | Raw Hermes dialogues stay in `~/.hermes/state.db`; memory files remain unchanged. | none |
| **Review / approval** | `self-ershov-memory --dry-run --full` extracts candidate corrections, deduplicates them, shows the proposed memory delta, and leaves files untouched. | none |
| **After** | `self-ershov-memory --execute --full` applies only reviewed corrections, creates snapshots first, updates `USER.md` / `MEMORY.md`, and records skill changes when needed. | explicit |


## Test evidence

<p align="center">
  <img src="assets/readme/test-evidence-dashboard.png" alt="Test evidence dashboard" width="100%">
</p>

Current product gate: **pytest suite passing** and **100% coverage for `self_ershov_memory` and the Hermes plugin wrapper**. Legacy staged-memory code is intentionally removed from the public package instead of being kept as dead compatibility surface.

```bash
uv run --locked --extra dev pytest -q
uv run --locked --extra dev pytest --cov=src/self_ershov_memory --cov=__init__ --cov-report=term-missing --cov-fail-under=100 -q
uv run --locked --extra dev ruff check --select F401,F841,E731 __init__.py src tests
```

GitHub Actions repeats the package gates on Python 3.11, 3.12, and 3.13; CodeQL runs separately.

## Architecture

The CLI keeps a small compatibility facade in `audit.py`, while the implementation is split into focused modules:

- `context.py` — `AuditContext` paths, limits, skill-topic mapping.
- `db.py` — SQLite dialogue reads.
- `cleaner.py` — compaction / attachment / machine-noise cleanup.
- `analyzer.py` — correction extraction, topic classification, fuzzy deduplication.
- `error_bank.py` — Engram-style Error Bank entries (`error_bank/<language>/<code>`) for fixed compiler/runtime/test failures.
- `checkpoint.py` — MiMo-style `checkpoint.md`, budgeted rebuild packets, and local Markdown FTS5 index under `~/.hermes/context`.
- `memory_store.py` — `USER.md` / `MEMORY.md` sections, snapshots, validation, compression.
- `skills.py` — skill creation / sync.
- `runner.py` — dry-run / execute orchestration.

`AuditContext` allows custom state and memory directories without monkeypatching globals; legacy `self_ershov_memory.audit` functions remain available for plugin and test compatibility.

## Install

```bash
hermes plugins install ersh123/self-ershov-memory --enable
```

## Quick start

```bash
# Inspect proposed changes
self-ershov-memory --dry-run --quick

# Full 30-day pass, still dry-run unless --execute is present
self-ershov-memory --dry-run --full

# Apply after review
self-ershov-memory --execute --full

# MiMo-style controlled context rebuild sidecar
self-ershov-memory checkpoint --session <session-id>
self-ershov-memory rebuild --session <session-id> --budget 48000
self-ershov-memory fts-index
self-ershov-memory fts-search "MiMo checkpoint"
```


## Development

```bash
uv sync --locked --extra dev
uv run --locked --extra dev pytest -q
uv run --locked --extra dev python -m build
uv run --locked --extra dev twine check --strict dist/*.whl dist/*.tar.gz
```

## Safety

- Snapshots before memory writes.
- Error Bank upserts are file-backed and keyed by `error_bank/<language>/<code>` so repeated failures consolidate instead of flooding hot memory.
- Size validation for memory files.
- No secret values in docs, logs, or provider doctor output.
- GitHub CLI credentials are for repository operations only, never LLM access.

When the audit loop stalls — two fix rounds with no progress — see [`docs/stop-and-research-rule.md`](docs/stop-and-research-rule.md): stop, re-read the source, and check how others hit the same issue before grinding another pass.

## Release and testing gates

The public package is intentionally narrow: one product CLI, one package, one memory self-audit loop. Release candidates must pass product coverage at 100%, package build, Twine metadata checks, CI, and CodeQL.

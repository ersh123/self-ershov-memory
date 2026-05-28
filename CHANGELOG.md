# Changelog

## 0.2.0 - 2026-05-28

- Added the review decision loop: `summarize`, `approve`, `reject`, and `review --open`.
- Hardened provider output validation so malformed proposals fail closed instead of sneaking into artifacts.
- Added provenance checks so proposals must cite the source bundle instead of fabricated paths.
- Added a deterministic local digest generator with priority scoring, change-since-last-dream summaries, and optional weekly rollups.
- Added onboarding docs, install/update guidance, persona examples, and a safety page that spells out what Dreaming can and cannot mutate.
- Added `dreaming report-card` as a redacted shareable phase-7 slice with JSON output support.
- Added live-memory policy guardrails around idempotence and capacity.

## 0.1.1 - 2026-05-27

- Added real `dreaming diff` output with unified diffs against `--live-root` or the artifact workspace root.
- Added atomic artifact apply behavior with preflight checks, up-front file snapshots, rollback on write or verification failure, and persisted audit fields.
- Added an offline quickstart fixture under `examples/quickstart/` plus copy/paste docs at `docs/quickstart.md`.
- Added pytest isolation and a `HERMES_DREAMING_STATE_ROOT` override so tests and demos do not write to the real `~/.hermes/dreaming` run ledger.
- Added a safe `dreaming update` command for fast-forward plugin updates with dirty-tree protection and optional pytest verification.
- Added a proper Hermes plugin wrapper so the repo can install as `hermes-dreaming`.
- Bundled a Hermes skill for the staged self-improvement workflow.
- Added an install-time handoff note for the Hermes plugin path.

## 0.1.0 - 2026-05-25

- Added the Hermes Dreaming artifact-first MVP.
- Added `create`, `diff`, `validate`, `apply`, `discard`, and `status` commands.
- Added directory-based dream artifacts with `manifest.json`, `REPORT.md`, `sources.jsonl`, and `proposals.jsonl`.
- Added validation, backups, and discard/archive semantics.
- Added offline marker parsing plus an optional OpenAI-compatible provider.
- Added tests for the core model, validation, CLI flow, and apply/discard behavior.
- Added initial scaffold and repository setup.

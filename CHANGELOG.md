# Changelog

## 0.4.0 - 2026-06-06

- Added the **trust loop**: `ershov revert` restores live files from the recorded backups and rolls an `applied` artifact back to a `reverted` state, with drift detection (`drift_detected` audit event), `REVERT.md` summary, and `--yes` for non-interactive callers.
- Added the **friction-killer**: `ershov create --from-sessions N` (and `--from-since 7d`, with `--recent N` as a back-compat alias) auto-harvests local sessions in one step and prints `harvest:`, `sessions:`, and `redactions:` to stdout before staging.
- Added `ershov apply --dry-run`, `--priority {low,normal,high}`, and `--target-kind {memory,user,skill,fact}` for preview-only and selective applies. Filters compose; filtered-out proposals stay approved so a later apply with a different filter can still land them.
- Added `ershov inbox --apply-ready` to surface artifacts where every proposal is approved (or already applied). The inbox digest also renders a "Ready to apply" section.
- Added `ershov providers list` to introspect the built-in providers (`offline-marker`, `openai-compatible`, `deepseek`, `ollama`) without pinging external services. `--no-llm` is a shorthand for `--provider offline-marker` on `create`, `review`, and `nightly`.
- Added `ershov providers doctor` for safe local provider configuration readiness checks without sending prompts, pinging model APIs, or printing secret values. `--from-systemd` checks the default Self Ershov Memory timer `EnvironmentFile` paths, repeatable `--env-file` checks explicit layouts, and `--fix-plan` prints secret-safe remediation steps for blocked providers; all paths avoid printing secret values and fail closed when an explicit `--provider` disagrees with `HERMES_ERSHOV_PROVIDER`. It is intentionally not an end-to-end generation test.
- Added `ershov soak` as a read-only release gate for scheduled self-audit: it checks recent successful `nightly` runs, recent failures, and optionally the user systemd timer.
- Added provider-aware release gating: `status --release-gate` and `soak --strict-systemd` surface timer-visible provider readiness, and `--require-provider deepseek` blocks offline-marker drift or missing provider keys without printing secrets.
- Added nightly-aware status rows so `status` shows the last nightly run, last successful nightly, and last failed nightly even when update/check commands are newer in the shared run ledger.
- Hardened provider output grounding: schema-valid model proposals are rejected if `source_quote` or `snippet` does not match a cited source line.
- Hardened legacy revert evidence: artifacts without post-apply shas now label backup-vs-live drift inference as `legacy-degraded` in the audit trail and `REVERT.md`.
- Hardened the root Hermes plugin wrapper so `ershov ...` propagates non-zero CLI failures to the shell instead of returning success after printing an error.
- Hardened `ershov update` verification so installed checkouts use an isolated uv editable test environment with pytest and Hypothesis instead of failing when the runtime environment lacks dev dependencies.
- Hardened `ershov update` against transient network stalls: `git fetch` and `git pull --ff-only` retry one transient network/timeout failure, and `--git-timeout-seconds` lets operators raise the per-git-command timeout without disabling verification.
- Hardened `nightly --no-llm` so harvests without eligible `MEMORY:` / `DREAM:` markers exit as clean `no-op` runs instead of invalid empty artifacts.
- Added `HERMES_ERSHOV_SESSION_DB` for deterministic harvest/nightly smoke tests against a specific SessionDB-compatible SQLite file.
- Tightened the `reject` reason enforcement: the non-empty reason check is now in `commands/review.py:reject_artifact()`, so any caller (CLI, library, plugin) is constrained by the same rule.
- Bumped the `DreamArtifact` model with `reverted_at` and `revert_audit_events`. The `dry_run_report` is attached in-memory only and excluded from `manifest.json` so the on-disk contract stays stable.

## 0.3.0 - 2026-06-02

- Added the Ershov Inbox command with JSON and text output so staged artifacts can be reviewed as a queue instead of only one at a time.
- Added `ershov harvest --recent` and wired `create`/`review` to the local session-reader fallback path.
- Surfaced proposal `risk`, `priority`, `reason`, `source_quote`, and `policy_flags` across summarize, digest, report-card, and inbox views.
- Added `digest --inbox` plus the inbox-digest cron mode for stdout-only operator reporting.
- Tightened writeback path policy so staged proposals fail closed unless they target the approved paths for their kind.
- Added source preflight secret checks so external-compatible providers are not called when source bundles contain secret-like content.
- Preserved existing uppercase `MEMORY.md`/`USER.md` files during apply instead of creating duplicate lowercase files.
- Bumped the plugin to `0.3.0` and refreshed the release docs/tests.

## 0.2.0 - 2026-05-28

- Added the review decision loop: `summarize`, `approve`, `reject`, and `review --open`.
- Hardened provider output validation so malformed proposals fail closed instead of sneaking into artifacts.
- Added provenance checks so proposals must cite the source bundle instead of fabricated paths.
- Added a deterministic local digest generator with priority scoring, change-since-last-memory-run summaries, and optional weekly rollups.
- Added onboarding docs, install/update guidance, persona examples, and a safety page that spells out what Ershov can and cannot mutate.
- Added `ershov report-card` as a redacted shareable phase-7 slice with JSON output support.
- Added live-memory policy guardrails around idempotence and capacity.

## 0.1.1 - 2026-05-27

- Added real `ershov diff` output with unified diffs against `--live-root` or the artifact workspace root.
- Added atomic artifact apply behavior with preflight checks, up-front file snapshots, rollback on write or verification failure, and persisted audit fields.
- Added an offline quickstart fixture under `examples/quickstart/` plus copy/paste docs at `docs/quickstart.md`.
- Added pytest isolation and a `HERMES_ERSHOV_STATE_ROOT` override so tests and demos do not write to the real `~/.hermes/ershov` run ledger.
- Added a safe `ershov update` command for fast-forward plugin updates with dirty-tree protection and optional pytest verification.
- Added a proper Hermes plugin wrapper so the repo can install as `self-ershov-memory`.
- Bundled a Hermes skill for the staged self-improvement workflow.
- Added an install-time handoff note for the Hermes plugin path.

## 0.1.0 - 2026-05-25

- Added the Self Ershov Memory artifact-first MVP.
- Added `create`, `diff`, `validate`, `apply`, `discard`, and `status` commands.
- Added directory-based memory artifacts with `manifest.json`, `REPORT.md`, `sources.jsonl`, and `proposals.jsonl`.
- Added validation, backups, and discard/archive semantics.
- Added offline marker parsing plus an optional OpenAI-compatible provider.
- Added tests for the core model, validation, CLI flow, and apply/discard behavior.
- Added initial scaffold and repository setup.

## v0.5.0 — Self-Audit Engine (2026-06-28)

**Концептуальный переход: nightly memory → self-audit.**

- **Self-audit pipeline** — основной механизм памяти
  - Анализ диалогов из state.db (режимы: quick 24ч / full 30д)
  - Извлечение коррекций по regex-паттернам
  - Классификация по темам (keyword-based)
  - Dedup — не дублирует существующие правила в USER.md
  - Snapshot — бэкап перед каждой правкой
  - Авто-создание скиллов для новых тем
- **Удалён старый nightly cron** (`c03d3e130c54`)
- **Plugin.yaml** v0.4.0 → v0.5.0, описание: «self-audit engine»
- **Policy** (DEBI): max_changes 3→8, max_new_chars 250→2500, max_targets 3→8
- **Providers**: retry на validation failure, relaxed provenance, single-bundle fallback
- **Cron**: daily quick (22:00) + weekly full (Вс 20:00)
- **README**: полная переработка под self-audit концепцию

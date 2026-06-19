# hermes-ershov

[![CI](https://github.com/ersh123/hermes-ershov/actions/workflows/ci.yml/badge.svg)](https://github.com/ersh123/hermes-ershov/actions/workflows/ci.yml)
[![CodeQL](https://github.com/ersh123/hermes-ershov/actions/workflows/codeql.yml/badge.svg)](https://github.com/ersh123/hermes-ershov/actions/workflows/codeql.yml)
[![Scorecard](https://github.com/ersh123/hermes-ershov/actions/workflows/scorecard.yml/badge.svg)](https://github.com/ersh123/hermes-ershov/actions/workflows/scorecard.yml)

![Hermes Ershov hero banner](assets/readme/hermes-ershov-hero.png)

Hermes Ershov is a staged nightly memory engine for Hermes operators.
It turns recent sessions and explicit notes into reviewable memory proposals, then keeps live memory untouched until an explicit approve/apply step.

What makes it useful:

- nightly review loop that survives gateway restarts
- artifact-first workflow: inspect, diff, validate, approve, reject, apply, revert
- no silent live-memory mutation
- offline mode for deterministic demos and tests
- LLM connectors for DeepSeek, OpenRouter, OpenAI-compatible endpoints, and Ollama
- local run ledger plus `ERSHOV.md` diary for auditability

## Hermes plugin

This repo now ships as a proper Hermes plugin too.

Install from GitHub with:

```bash
hermes plugins install ersh123/hermes-ershov --enable
```

For a local checkout during development:

```bash
hermes plugins install file:///path/to/hermes-ershov --enable
```

Once installed, use:

```bash
hermes ershov review --help
```

Update the installed checkout with:

```bash
hermes ershov update
```

Use `hermes ershov update --check` if you only want the status check.

The plugin also bundles a Hermes skill named `ershov`. Load that bare name inside Hermes if you want the guided staged workflow.

## Onboarding docs

- [docs/onboarding.md](docs/onboarding.md) is the shortest path from "what is this" to the full loop.
- [docs/install-update.md](docs/install-update.md) covers plugin install and safe fast-forward updates.
- [docs/quickstart.md](docs/quickstart.md) is the copy/paste offline demo.
- [docs/personas.md](docs/personas.md) shows how different operators use the same loop.
- [docs/safety.md](docs/safety.md) spells out what Ershov can and cannot mutate.
- [docs/testing.md](docs/testing.md) shows the release test matrix behind the GitHub checks.

## Current status

- **Release posture:** public beta / release candidate. The current code, tests, plugin smoke, CI, and CodeQL gates are green, but stable wording waits for several clean scheduled systemd runs followed by `hermes ershov soak --strict-systemd`. The stable shortcut defaults to the 3-run public promotion gate: `hermes ershov soak --since-hours 96 --min-successful 3 --strict-systemd`.
- **Full feature set:** create, review/open, nightly, summarize, approve, reject, diff, validate, apply, discard, compact, report-card, install-cron, install-systemd, status, update, all implemented
- **Live memory mutation** with score gating, idempotence, backups, and capacity enforcement
- **Run ledger + ERSHOV.md diary** for auditability
- **Hermes-native plugin:** install once, use everywhere
- **Recent-session reader** with fallback chain (SessionDB → SQLite → pointer-log)
- **Nightly memory pipeline** for dialogue harvest, staged review artifacts, digests, inbox digest, compaction, and run-ledger audit
- **Cron and user-systemd installers** for the full nightly memory pipeline
- **Test suite, plugin smoke, CI, and CodeQL pass**
- **Repo hygiene:** `uv.lock`, private security advisory path, issue/PR templates, CODEOWNERS, weekly Dependabot checks, OpenSSF Scorecard SARIF, and checkout-token hardening for GitHub Actions

## Install

For end-user installs, use the plugin path in `docs/install-update.md`. For local development:

```bash
uv sync --extra dev
```

If you want the optional OpenAI-compatible provider:

```bash
uv sync --extra llm
```

## LLM connectors

The default `offline-marker` provider needs no key and never calls the network. For model-backed review, install the `llm` extra and choose a provider explicitly:

```bash
# DeepSeek, OpenAI-compatible endpoint
export DEEPSEEK_API_KEY="..."
ershov review --provider deepseek --model deepseek-v4-flash --source ./sources --live-root ./live --artifact-root ./artifacts

# OpenRouter, auto-routed model selection
export OPENROUTER_API_KEY="..."
ershov review --provider openrouter --model openrouter/auto --source ./sources --live-root ./live --artifact-root ./artifacts

# Any OpenAI-compatible endpoint
ershov review --provider openai-compatible --api-key "$OPENAI_API_KEY" --base-url https://api.openai.com/v1 --model gpt-4o-mini --source ./sources

# Local Ollama, no cloud key
ershov review --provider ollama --model qwen2.5:3b --base-url http://127.0.0.1:11434 --source ./sources
```

Provider calls fail closed before writeback: source bundles are preflighted for secret-like content, model output must be valid JSON, provenance must point at scanned source lines, and every proposal is staged as unapproved.
Schema-valid model output is still treated as untrusted: `source_quote` and `snippet` must match the cited source lines, so invented evidence fails before staging.

## CLI

```bash
# Create an artifact from sources

ershov create --live-root ./live --artifact-root ./artifacts --source ./sources

# Review: create and validate without applying

ershov review --live-root ./live --artifact-root ./artifacts --source ./sources

# Open an existing artifact and print next steps

ershov review --open ./artifacts/<artifact-id>

ershov summarize ./artifacts/<artifact-id>
ershov approve ./artifacts/<artifact-id> all
ershov reject ./artifacts/<artifact-id> <proposal-id> --reason "too broad"

# Inspect an artifact

ershov diff ./artifacts/<artifact-id> --live-root ./live

# Validate a staged artifact

ershov validate ./artifacts/<artifact-id> --live-root ./live

# Apply approved changes

ershov apply ./artifacts/<artifact-id> --live-root ./live --backup-root ./backups
# Preview the apply without writing live state or creating backups
ershov apply ./artifacts/<artifact-id> --live-root ./live --backup-root ./backups --dry-run
# Apply only high-priority memory and user updates, skip skills and facts
ershov apply ./artifacts/<artifact-id> --live-root ./live --backup-root ./backups --priority high --target-kind memory,user
# Undo an apply: restore live files from the recorded backups
ershov revert ./artifacts/<artifact-id> --live-root ./live --backup-root ./backups --yes --validate
# Discard a staged artifact
ershov discard ./artifacts/<artifact-id> --archive-root ./archive
# Show artifacts that are approved and ready to apply
ershov inbox --artifact-root ./artifacts --apply-ready
# List available analysis providers
ershov providers list
# Check provider configuration readiness without sending prompts or pinging model APIs
ershov providers doctor --provider deepseek --strict
# Check the exact env files a systemd timer will see, without printing values
ershov providers doctor --provider deepseek --from-systemd --strict
# Print secret-safe remediation steps if that timer-visible check is blocked
ershov providers doctor --provider deepseek --from-systemd --fix-plan --strict
# Or pass explicit env files when testing a non-default service layout
ershov providers doctor --provider deepseek --env-file ~/.config/hermes-ershov/nightly.env --env-file ~/.config/hermes-ershov/nightly.secrets.env --strict
# Stage from the last 5 local sessions in one step (replaces manual harvest + create)
ershov create --from-sessions 5 --live-root ./live --artifact-root ./artifacts

# Run the full nightly memory pipeline locally
ershov nightly --live-root ./live --artifact-root ./artifacts --no-llm

# Compact terminal (applied/discarded) artifacts to an archive

ershov compact --artifact-root ./artifacts --archive-root ./archive

# Install a nightly memory cron job

ershov install-cron --mode nightly-memory --schedule "0 3 * * *"

# Or install a user systemd timer that runs outside the Hermes gateway process

ershov install-systemd --on-calendar "*-*-* 03:00:00"

# Render a local operator digest

ershov digest ./artifacts/<artifact-id> --weekly

# Show artifact status

ershov status --artifact-root ./artifacts

# Fast one-night RC smoke after the first scheduled nightly run

hermes ershov soak --state-root ~/.hermes/ershov --since-hours 30 --min-successful 1 --strict-systemd

# Fast one-night RC smoke that also requires the timer-visible DeepSeek env to be ready

hermes ershov soak --state-root ~/.hermes/ershov --since-hours 30 --min-successful 1 --strict-systemd --require-provider deepseek
hermes ershov soak --state-root ~/.hermes/ershov --since-hours 30 --min-successful 1 --strict-systemd --require-provider deepseek --fix-plan

# Public-stable promotion gate after several scheduled nights

hermes ershov soak --state-root ~/.hermes/ershov --since-hours 96 --min-successful 3 --strict-systemd
hermes ershov status --release-gate --state-root ~/.hermes/ershov --require-provider deepseek --fix-plan

# Safely update the installed checkout

ershov update
ershov update --check
ershov update --git-timeout-seconds 180
```

## Quickstart demo fixture

If you want the shortest path to "oh, I get it," use `examples/quickstart/`. It is an offline fixture, so no API key or external model access is required.
If the `ershov` entrypoint is not installed yet, swap in `python -m hermes_ershov` for the same commands.

- Fixture notes: [examples/quickstart/README.md](examples/quickstart/README.md)
- Onboarding path: [docs/onboarding.md](docs/onboarding.md)
- Install and update: [docs/install-update.md](docs/install-update.md)
- Runnable walkthrough: [docs/quickstart.md](docs/quickstart.md)
- Persona examples: [docs/personas.md](docs/personas.md)
- Safety boundaries: [docs/safety.md](docs/safety.md)

### Command notes
- `report-card` renders a redacted shareable summary from an existing artifact and can write a JSON companion with `--json`. Applied summaries separate real backup file copies from rollback evidence records and created-file tombstones.
- `digest` renders a local operator brief to stdout only. It can include `--weekly` rollups, but it does not send anything to Telegram. If you want delivery later, wrap the command in a separate transport layer that consumes stdout.
- `create` and `review` accept repeatable `--source`, `--from-sessions N` (or `--recent N` alias), `--from-since 7d`, and `--no-llm` (shorthand for `--provider offline-marker`). Harvest stats (`sessions`, `redactions`) print to stdout before staging. `review --open` prints the artifact path and the next commands.
- `nightly` runs the full local ershov loop: dialogue harvest, staged artifact creation, artifact `NIGHTLY.md`, latest inbox digest, terminal artifact compaction, and run-ledger / `ERSHOV.md` update. It takes a state-root lock so overlapping runs fail before writing sources/artifacts, and it never applies live memory automatically.
- `nightly --no-llm` only stages explicit `MEMORY:` / `DREAM:` markers. When the harvest has no eligible markers, it exits successfully as `no-op`, writes source and inbox digests, and does not create an invalid empty review artifact.
- `install-systemd` writes a user-level systemd service/timer for nightly memory. This is the safer VPS path when the Hermes gateway itself may be down: the timer runs the no-agent `nightly` script outside the gateway process and does not restart Hermes.
- Provider secrets are not written by `install-systemd`; put them in `~/.config/hermes-ershov/nightly.secrets.env` when the timer needs cloud model access.
- `apply` accepts `--dry-run` for previews, `--priority low,normal,high` to filter proposals, and `--target-kind memory,user,skill,fact` to filter by destination. Filters compose; filtered-out proposals stay approved so a later apply with a different filter can still land them.
- `apply` records backup evidence in the artifact manifest before live writes: existing files get backup paths, files created by apply get `backup_records` tombstones, and successful writes get post-apply shas for drift checks. `--dry-run` deliberately creates no backups and writes no live files, so it is safe as the first trust check.
- `revert` restores existing live files from recorded backups, removes files that were created by apply, and rolls the artifact back from `applied` to `reverted`. Requires `--yes` for non-interactive use. Add `--validate` to run the existing artifact validator after restore; validation results are written to the revert audit and `REVERT.md`. Without `--validate`, the CLI and `REVERT.md` explicitly report `post_revert_validation: not-run`. Drift detection compares the live file to the recorded post-apply sha when available, then restores from backup. Legacy artifacts without post-apply shas are marked as `legacy-degraded` evidence when revert has to infer drift from backup-vs-live comparison.
- `inbox` supports `--apply-ready` to show only artifacts where every proposal is approved (or already applied) and the artifact is in `staged`, `approved`, or `applied` status. The inbox digest also surfaces a "Ready to apply" section.
- `providers list` introspects the built-in providers (offline-marker, openai-compatible, deepseek, openrouter, ollama) without pinging external services. `--no-llm` is a shorthand for `--provider offline-marker` on `create`, `review`, and `nightly`.
- `providers doctor` checks local configuration readiness without sending prompts or pinging model APIs: optional dependency import, expected API-key env var presence, configured base URL shape, and local-only notes. It never prints secret values. Use `--from-systemd` to check the default Hermes Ershov timer `EnvironmentFile` paths, or add repeatable `--env-file` flags to check an explicit systemd layout; when `--provider` is explicit, env-file checks also fail closed if `HERMES_ERSHOV_PROVIDER` is configured for a different provider. Add `--fix-plan` to print secret-safe remediation steps for blocked providers, including the non-secret `install-systemd` refresh command and the follow-up doctor/soak checks. Missing files are ignored and secret values are never printed. It is not an end-to-end generation test; use an explicit review/create run when you want to exercise a model call. Add `--strict` when you want a shell gate that exits non-zero unless every checked provider is locally ready.
- OpenAI-compatible, DeepSeek, OpenRouter, and Ollama providers fail closed on malformed output, and each proposal must carry confidence, snippet, provenance, and approved fields before it can be written.
- `HERMES_ERSHOV_SESSION_DB=/path/to/state.db` forces harvest/nightly to read a specific SessionDB-compatible SQLite file before trying the live Hermes SessionDB. This is useful for deterministic smoke tests.
- `status --release-gate --state-root ~/.hermes/ershov` renders the strict systemd stable gate inline: current commit, dirty state, last nightly run, last successful nightly, last failed nightly, timer health/next elapse, timer-visible provider readiness, matching scheduled runs, recent failures, and the exact blockers keeping stable wording off. Add `--require-provider deepseek` when the release gate must prove the timer is configured for DeepSeek, not just any ready provider. Add `--fix-plan` to include the same secret-safe provider remediation plan inline with the blockers. When `--state-root` is passed and `--artifact-root` is omitted, status reads artifacts, `state.json`, `runs.jsonl`, and `ERSHOV.md` from that same state root so installed-checkout evidence is not mixed with the caller's current directory.
- `soak` is a read-only release gate for scheduled nightly memory. It checks the run ledger for recent successful `nightly` runs, fails on recent nightly failures unless `--allow-failures` is set, can require the user systemd timer with `--require-timer`, can require timer-visible provider readiness with `--check-provider` or `--require-provider deepseek`, and can require evidence from a specific runner, code revision, and clean checkout with `--require-source systemd --require-commit <sha> --require-clean`. `--strict-systemd` is the stable release shortcut: it requires the timer, checks the configured timer provider from systemd env files, requires `run_source=systemd`, the current git commit, a clean current git checkout, and clean scheduled-run evidence. Add `--fix-plan` to append a secret-safe provider remediation plan to text output when readiness is blocked. With no explicit window overrides it defaults to the public-stable promotion gate: `--since-hours 96 --min-successful 3 --strict-systemd`. Use `--since-hours 30 --min-successful 1 --strict-systemd` only as a fast one-night RC smoke. The timer gate checks that the timer is enabled, active, loaded, points at `hermes-ershov-nightly.service`, and has a next scheduled elapse. Commit matches require at least 7 git hash characters on both sides; shorter prefixes do not satisfy the gate.
- `summarize` prints a concise decision brief for an existing artifact.
- `approve` and `reject` update artifact metadata only, they do not touch live roots. `reject` requires a non-empty `--reason` at the command layer; any code path (CLI, library, plugin) is constrained by the same rule.
- `diff` accepts optional `--live-root` and renders unified diffs when the live target root is available.
- `apply` applies already approved proposals. `--approve` still works as a compatibility shortcut for recording approvals before apply.
- `update` supports `--remote`, `--branch`, `--check`, `--no-verify`, and `--git-timeout-seconds`. The fetch and fast-forward pull steps retry one transient network/timeout failure before failing, while dirty trees, local-ahead/diverged branches, and failed verification still block the update.

## Memory markers

The offline provider looks for explicit `MEMORY:` or `DREAM:` lines in the source bundle.

```text
MEMORY: memory: Keep updates short and concrete.
MEMORY: user: Prefer concise status updates.
MEMORY: fact: {"type": "preference", "key": "tone", "value": "casual"}
MEMORY: skill: path=skills/review.md | Preserve review gates and backups.
DREAM: user: Legacy compatibility marker.
```

## Artifact layout

Each run writes a staged artifact directory containing:

- `manifest.json`
- `REPORT.md`
- `sources.jsonl`
- `proposals.jsonl`
- `audit.jsonl`

The artifact is intentionally simple, deterministic, and easy to review on disk or in git.

## Repo docs

- [CONTRIBUTING.md](CONTRIBUTING.md) is the contributor guide and local workflow contract
- [SECURITY.md](SECURITY.md) covers private vulnerability reporting
- [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) sets the collaboration rules
- [brief.md](brief.md) has the project brief and non-goals
- [specs/mvp-implementation-plan.md](specs/mvp-implementation-plan.md) describes the current implementation contract and package layout
- [docs/release-checklist.md](docs/release-checklist.md) is the pre-release checklist
- [reviews/final-sanity.md](reviews/final-sanity.md) records the most recent QA pass
- [research/upstream-overlap.md](research/upstream-overlap.md) captures the upstream overlap notes and references

## Contributing

If you want to contribute, start with [CONTRIBUTING.md](CONTRIBUTING.md).

- Use the issue templates so the scope and intent are clear.
- Run `uv run --locked --extra dev pytest -q`, `uv run --locked --extra dev python -m build --wheel`, and `git diff --check` before requesting review.
- If your change touches live roots, artifact roots, or writeback behavior, state that explicitly.
- If you change release-facing text or safety rules, make sure the docs still match shipped behavior.

## Development

```bash
uv sync --locked --extra dev
uv run --locked --extra dev pytest -q
uv run --locked --extra dev python -m build --wheel
```

The public release gate uses the fuller matrix in `docs/testing.md`: unit and CLI tests, property-based tests, plugin wrapper smoke, build/wheel/sdist smoke, docs guards, CodeQL, and scheduled-run soak evidence.

The repo is intentionally self-contained and ready for public beta / release-candidate review.

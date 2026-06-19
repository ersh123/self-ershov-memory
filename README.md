# hermes-ershov

[![CI](https://github.com/ersh123/hermes-ershov/actions/workflows/ci.yml/badge.svg)](https://github.com/ersh123/hermes-ershov/actions/workflows/ci.yml)
[![CodeQL](https://github.com/ersh123/hermes-ershov/actions/workflows/codeql.yml/badge.svg)](https://github.com/ersh123/hermes-ershov/actions/workflows/codeql.yml)

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

- `docs/onboarding.md` is the shortest path from "what is this" to the full loop.
- `docs/install-update.md` covers plugin install and safe fast-forward updates.
- `docs/quickstart.md` is the copy/paste offline demo.
- `docs/personas.md` shows how different operators use the same loop.
- `docs/safety.md` spells out what Ershov can and cannot mutate.

## Current status

- **Release posture:** public beta / release candidate. The current code, tests, plugin smoke, CI, and CodeQL gates are green, but stable wording waits for a real overnight systemd run followed by `hermes ershov soak --strict-systemd`.
- **Full feature set:** create, review/open, nightly, summarize, approve, reject, diff, validate, apply, discard, compact, report-card, install-cron, install-systemd, status, update, all implemented
- **Live memory mutation** with score gating, idempotence, backups, and capacity enforcement
- **Run ledger + ERSHOV.md diary** for auditability
- **Hermes-native plugin:** install once, use everywhere
- **Recent-session reader** with fallback chain (SessionDB → SQLite → pointer-log)
- **Nightly memory pipeline** for dialogue harvest, staged review artifacts, digests, inbox digest, compaction, and run-ledger audit
- **Cron and user-systemd installers** for the full nightly memory pipeline
- **Test suite, plugin smoke, CI, and CodeQL pass**

## Install

For end-user installs, use the plugin path in `docs/install-update.md`. For local development:

```bash
python -m pip install -e .[dev]
```

If you want the optional OpenAI-compatible provider:

```bash
python -m pip install -e .[llm]
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
ershov revert ./artifacts/<artifact-id> --live-root ./live --backup-root ./backups --yes
# Discard a staged artifact
ershov discard ./artifacts/<artifact-id> --archive-root ./archive
# Show artifacts that are approved and ready to apply
ershov inbox --artifact-root ./artifacts --apply-ready
# List available analysis providers
ershov providers list
# Stage from the last 5 local sessions in one step (replaces manual harvest + create)
ershov create --from-sessions 5 --live-root ./live --artifact-root ./artifacts

# Run the full nightly memory pipeline locally
ershov nightly --live-root ./live --artifact-root ./artifacts --no-llm

ershov discard ./artifacts/<artifact-id> --archive-root ./archive

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

# Verify overnight soak evidence after a scheduled nightly run

hermes ershov soak --state-root ~/.hermes/ershov --since-hours 30 --strict-systemd

# Safely update the installed checkout

ershov update
ershov update --check
```

## Quickstart demo fixture

If you want the shortest path to "oh, I get it," use `examples/quickstart/`. It is an offline fixture, so no API key or external model access is required.
If the `ershov` entrypoint is not installed yet, swap in `python -m hermes_ershov` for the same commands.

- Fixture notes: `examples/quickstart/README.md`
- Onboarding path: `docs/onboarding.md`
- Install and update: `docs/install-update.md`
- Runnable walkthrough: `docs/quickstart.md`
- Persona examples: `docs/personas.md`
- Safety boundaries: `docs/safety.md`

### Command notes
- `report-card` renders a redacted shareable summary from an existing artifact and can write a JSON companion with `--json`.
- `digest` renders a local operator brief to stdout only. It can include `--weekly` rollups, but it does not send anything to Telegram. If you want delivery later, wrap the command in a separate transport layer that consumes stdout.
- `create` and `review` accept repeatable `--source`, `--from-sessions N` (or `--recent N` alias), `--from-since 7d`, and `--no-llm` (shorthand for `--provider offline-marker`). Harvest stats (`sessions`, `redactions`) print to stdout before staging. `review --open` prints the artifact path and the next commands.
- `nightly` runs the full local ershov loop: dialogue harvest, staged artifact creation, artifact `NIGHTLY.md`, latest inbox digest, terminal artifact compaction, and run-ledger / `ERSHOV.md` update. It takes a state-root lock so overlapping runs fail before writing sources/artifacts, and it never applies live memory automatically.
- `nightly --no-llm` only stages explicit `MEMORY:` / `DREAM:` markers. When the harvest has no eligible markers, it exits successfully as `no-op`, writes source and inbox digests, and does not create an invalid empty review artifact.
- `install-systemd` writes a user-level systemd service/timer for nightly memory. This is the safer VPS path when the Hermes gateway itself may be down: the timer runs the no-agent `nightly` script outside the gateway process and does not restart Hermes.
- Provider secrets are not written by `install-systemd`; put them in `~/.config/hermes-ershov/nightly.secrets.env` when the timer needs cloud model access.
- `apply` accepts `--dry-run` for previews, `--priority low,normal,high` to filter proposals, and `--target-kind memory,user,skill,fact` to filter by destination. Filters compose; filtered-out proposals stay approved so a later apply with a different filter can still land them.
- `revert` restores live files from the recorded backups and rolls the artifact back from `applied` to `reverted`. Requires `--yes` for non-interactive use. Drift detection records an audit event when the live file changed after apply, but the restore still runs.
- `inbox` supports `--apply-ready` to show only artifacts where every proposal is approved (or already applied) and the artifact is in `staged`, `approved`, or `applied` status. The inbox digest also surfaces a "Ready to apply" section.
- `providers list` introspects the built-in providers (offline-marker, openai-compatible, deepseek, openrouter, ollama) without pinging external services. `--no-llm` is a shorthand for `--provider offline-marker` on `create`, `review`, and `nightly`.
- OpenAI-compatible, DeepSeek, OpenRouter, and Ollama providers fail closed on malformed output, and each proposal must carry confidence, snippet, provenance, and approved fields before it can be written.
- `HERMES_ERSHOV_SESSION_DB=/path/to/state.db` forces harvest/nightly to read a specific SessionDB-compatible SQLite file before trying the live Hermes SessionDB. This is useful for deterministic smoke tests.
- `soak` is a read-only release gate for scheduled nightly memory. It checks the run ledger for recent successful `nightly` runs, fails on recent nightly failures unless `--allow-failures` is set, can require the user systemd timer with `--require-timer`, and can require evidence from a specific runner, code revision, and clean checkout with `--require-source systemd --require-commit <sha> --require-clean`. `--strict-systemd` is the stable release shortcut: it requires the timer, `run_source=systemd`, the current git commit, a clean current git checkout, and clean scheduled-run evidence. The timer gate checks that the timer is enabled, active, loaded, points at `hermes-ershov-nightly.service`, and has a next scheduled elapse. Commit matches require at least 7 git hash characters on both sides; shorter prefixes do not satisfy the gate.
- `summarize` prints a concise decision brief for an existing artifact.
- `approve` and `reject` update artifact metadata only, they do not touch live roots. `reject` requires a non-empty `--reason` at the command layer; any code path (CLI, library, plugin) is constrained by the same rule.
- `diff` accepts optional `--live-root` and renders unified diffs when the live target root is available.
- `apply` applies already approved proposals. `--approve` still works as a compatibility shortcut for recording approvals before apply.
- `update` supports `--remote`, `--branch`, `--check`, and `--no-verify`.

## Memory markers

The offline provider looks for explicit `MEMORY:` lines in the source bundle.

```text
MEMORY: memory: Keep updates short and concrete.
MEMORY: user: Prefer concise status updates.
MEMORY: fact: {"type": "preference", "key": "tone", "value": "casual"}
MEMORY: skill: path=skills/review.md | Preserve review gates and backups.
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

- `CONTRIBUTING.md` is the contributor guide and local workflow contract
- `SECURITY.md` covers private vulnerability reporting
- `CODE_OF_CONDUCT.md` sets the collaboration rules
- `brief.md` has the project brief and non-goals
- `specs/mvp-implementation-plan.md` describes the current implementation contract and package layout
- `docs/release-checklist.md` is the pre-release checklist
- `reviews/final-sanity.md` records the most recent QA pass
- `research/upstream-overlap.md` captures the upstream overlap notes and references

## Contributing

If you want to contribute, start with `CONTRIBUTING.md`.

- Use the issue templates so the scope and intent are clear.
- Run `pytest -q`, `python -m build --wheel`, and `git diff --check` before requesting review.
- If your change touches live roots, artifact roots, or writeback behavior, state that explicitly.
- If you change release-facing text or safety rules, make sure the docs still match shipped behavior.

## Development

```bash
pytest -q
python -m pip install build
python -m build --wheel
```

The repo is intentionally self-contained and ready for public beta / release-candidate review.

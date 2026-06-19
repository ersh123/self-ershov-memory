# Hermes Ershov onboarding

Start here if you want the whole loop in one place.

Hermes Ershov is a staged self-improvement loop. It scans explicit source inputs, stages proposed changes in an artifact directory, and only touches live state after an explicit apply step.

## The short path in

1. Install the plugin or point at a local checkout.
2. Run the offline quickstart.
3. Read the persona examples if you want to see how different operators use the same loop.
4. Read the safety page before you point it at anything sensitive.
5. Use the update doc when you want to fast-forward the installed checkout safely.

## Start with these docs

- Install and update, `docs/install-update.md`
- Offline demo, `docs/quickstart.md`
- Persona examples, `docs/personas.md`
- Safety boundaries, `docs/safety.md`

## First run (new)

The shortest path from "what is this" to a usable artifact is now one command. `ershov create --from-sessions 5` harvests the last 5 local Hermes sessions, prints redaction stats to stdout, and stages an artifact in one step. No manual `harvest` + `create --source` two-step required.

```bash
ershov create --from-sessions 5 --live-root ./live --artifact-root ./artifacts
```

For a no-network run, add `--no-llm` to skip any external provider:

```bash
ershov create --from-sessions 5 --no-llm --live-root ./live --artifact-root ./artifacts
```

If you want a more targeted window, use `--from-since 7d` (or `12h` / `2w`):

```bash
ershov create --from-since 7d --no-llm --live-root ./live --artifact-root ./artifacts
```

After staging, the rest of the loop is unchanged: `summarize`, `approve`/`reject`, `validate`, `apply`. To preview the apply without touching live state, add `--dry-run`. To undo a real apply, run `ershov revert <artifact> --yes`.

## Nightly memory loop

For the full nightly flow, run `nightly`. It harvests recent dialogue, stages a review artifact, writes an artifact-local `NIGHTLY.md`, refreshes the latest inbox digest, compacts terminal artifacts, and records the run in `runs.jsonl` / `ERSHOV.md`.

```bash
ershov nightly --live-root ./live --artifact-root ./artifacts --no-llm
```

With an LLM provider, set the provider key in the runtime environment and omit `--no-llm`. The nightly loop still does not apply live memory by itself; you approve and apply explicitly after review.

In offline `--no-llm` mode, the nightly loop is marker-driven. If the recent harvest has no eligible `MEMORY:` / `DREAM:` lines, Ershov returns a clean `no-op` and does not create an invalid empty artifact.

To schedule the loop inside Hermes, use the cron bridge:

```bash
ershov install-cron --mode nightly-memory --schedule "0 3 * * *"
```

On VPS/systemd stacks, prefer the gateway-independent timer:

```bash
ershov install-systemd --on-calendar "*-*-* 03:00:00"
```

The systemd installer writes non-secret runtime knobs only. Put provider keys in
`~/.config/hermes-ershov/nightly.secrets.env`; reinstalling the timer does not
touch that file.

For deterministic smoke tests, set `HERMES_ERSHOV_SESSION_DB=/path/to/state.db` to force harvest/nightly to read a specific SessionDB-compatible SQLite file before the live Hermes SessionDB.

After a scheduled run has had time to fire, use `soak` as the release gate:

```bash
COMMIT="$(git -C ~/.hermes/plugins/hermes-ershov rev-parse --short HEAD)"
ershov soak --state-root ~/.hermes/ershov --since-hours 30 --require-timer --require-source systemd --require-commit "$COMMIT" --require-clean
```

It is read-only. It checks `runs.jsonl` for recent successful `nightly` runs, fails on recent nightly failures, verifies the user systemd timer when `--require-timer` is set, and can require the successful run to come from the installed systemd checkout/commit.
The timer check requires an enabled, active, loaded timer pointing at `hermes-ershov-nightly.service` with a next scheduled elapse.
Add `--require-clean` when using it as a release gate so dirty installed checkouts cannot count as stable evidence.

## What to expect

- The offline demo works without API keys or external model access.
- Review comes before apply.
- Approvals and rejections stay in the artifact until you explicitly apply.
- The default flow is local-first and reviewable, not a silent background write.

If you only want one thing to copy and paste, open `docs/quickstart.md` next.

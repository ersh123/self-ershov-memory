# Install and update Hermes Ershov

Hermes Ershov ships as a Hermes plugin. Install it through Hermes, then use the `hermes ershov ...` commands inside your Hermes session.

## Install from GitHub

```bash
hermes plugins install ersh123/hermes-ershov --enable
```

## Install from a local checkout

```bash
hermes plugins install file:///path/to/hermes-ershov --enable
```

## Confirm the plugin is available

```bash
hermes ershov review --help
```

If you are outside Hermes, the repo still exposes the same CLI as the `ershov` console script, and `python -m hermes_ershov` works as a fallback during local development.

## Install nightly memory outside the gateway

For VPS deployments, prefer a user systemd timer when you want the nightly memory
loop to survive Hermes gateway restarts or crashes:

```bash
ershov install-systemd --on-calendar "*-*-* 03:00:00"
```

The timer runs `ershov nightly` through a generated no-agent script. It stages
artifacts, writes digests, compacts terminal artifacts, and updates the run
ledger. It does not apply live memory automatically and does not restart Hermes.
Provider secrets are not written by the installer. If the timer needs DeepSeek,
put the key in `~/.config/hermes-ershov/nightly.secrets.env`; the generated
service reads that file if it exists and leaves it untouched on reinstall.
Before switching a timer to a cloud provider, check the timer-visible
environment files directly:

```bash
hermes ershov providers doctor --provider deepseek --from-systemd --strict
hermes ershov providers doctor --provider deepseek --from-systemd --fix-plan --strict
```

This is still a local readiness check only. It proves the generated service
files can see the requested provider key and that `HERMES_ERSHOV_PROVIDER`
matches the requested provider without printing secret values; it does not send
a prompt or call the model API. Add `--fix-plan` when the check is blocked and
you want the exact secret-safe remediation commands without changing files.
Use explicit `--env-file` values only when testing a non-default service layout:

```bash
hermes ershov providers doctor --provider deepseek --env-file ~/.config/hermes-ershov/nightly.env --env-file ~/.config/hermes-ershov/nightly.secrets.env --strict
```

After the first scheduled run has actually fired, verify it with:

```bash
hermes ershov soak --state-root ~/.hermes/ershov --since-hours 30 --min-successful 1 --strict-systemd
```

If this deployment is meant to run DeepSeek, require that provider explicitly:

```bash
hermes ershov soak --state-root ~/.hermes/ershov --since-hours 30 --min-successful 1 --strict-systemd --require-provider deepseek
```

Manual starts prove the service command works. `--require-timer` checks that the
user timer is enabled, active, loaded, points at `hermes-ershov-nightly.service`,
and has a next scheduled elapse. The stricter `--require-source systemd` gate
only accepts ledger entries written by the systemd service environment.
`--require-commit` ties the evidence to the installed checkout that will be
released. Commit matches require at least 7 git hash characters on both sides,
so a too-short historical ledger prefix cannot satisfy the gate. `--require-clean`
rejects runs produced by a dirty installed checkout.
`--strict-systemd` applies those release gates and auto-detects the current
checkout commit. It also reads the timer-visible provider env files and blocks
when the configured provider is not locally ready. It refuses a dirty current git
checkout; if the checkout is not a git repo, pass `--require-commit`.
A passing one-night `soak` after the real schedule fires is the minimum release-candidate
evidence. For public stable promotion, require several scheduled nights; the
strict shortcut defaults to this gate when no window overrides are passed:

```bash
hermes ershov soak --state-root ~/.hermes/ershov --since-hours 96 --min-successful 3 --strict-systemd
```

## Update the installed checkout

```bash
hermes ershov update
hermes ershov update --check
hermes ershov update --no-verify
hermes ershov update --git-timeout-seconds 180
```

The update command is conservative on purpose:

- default remote: `origin`
- default branch: `main`
- it refuses a dirty working tree
- it refuses local-ahead or diverged history
- it runs pytest after a real update unless you disable verification
- it retries one transient network/timeout failure during `git fetch` or `git pull --ff-only`; raise `--git-timeout-seconds` when GitHub or the VPS network is slow

You can override the remote or branch if your install tracks something else:

```bash
hermes ershov update --remote upstream --branch release
```

## When to use the update check

Use `hermes ershov update --check` before a real pull if you just want to see whether the install is behind.
Use the real update when you are ready to fast-forward the checkout and run verification.

For the offline walkthrough, jump to `docs/quickstart.md`.

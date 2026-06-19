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

After the first scheduled run has actually fired, verify it with:

```bash
COMMIT="$(git -C ~/.hermes/plugins/hermes-ershov rev-parse --short HEAD)"
ershov soak --state-root ~/.hermes/ershov --since-hours 30 --require-timer --require-source systemd --require-commit "$COMMIT" --require-clean
```

Manual starts prove the service command works. The stricter `--require-source
systemd` gate only accepts ledger entries written by the systemd service
environment. `--require-commit` ties the evidence to the installed checkout that
will be released. Commit matches require at least 7 git hash characters on both
sides, so a too-short historical ledger prefix cannot satisfy the gate.
`--require-clean` rejects runs produced by a dirty installed checkout.
A passing `soak` after the real schedule fires is the stronger
evidence for stable operations.

## Update the installed checkout

```bash
hermes ershov update
hermes ershov update --check
hermes ershov update --no-verify
```

The update command is conservative on purpose:

- default remote: `origin`
- default branch: `main`
- it refuses a dirty working tree
- it refuses local-ahead or diverged history
- it runs pytest after a real update unless you disable verification

You can override the remote or branch if your install tracks something else:

```bash
hermes ershov update --remote upstream --branch release
```

## When to use the update check

Use `hermes ershov update --check` before a real pull if you just want to see whether the install is behind.
Use the real update when you are ready to fast-forward the checkout and run verification.

For the offline walkthrough, jump to `docs/quickstart.md`.

# Hermes Ershov v0.2.0 Handoff

This is the short follow-up note for the shipped `v0.2.0` line.

## Read these first

- `docs/release-notes-v0.2.0.md` for the shipped change summary
- `CHANGELOG.md` for the version history
- `docs/install-update.md` for the install and update path

## Install / update path

```bash
hermes plugins install ersh123/hermes-ershov --enable
hermes ershov review --help
hermes ershov update
hermes ershov update --check
```

If you are outside Hermes, the repo still exposes the `ershov` console script for local use, and `python -m hermes_ershov` remains the development fallback.

## Current release facts

- GitHub release: `v0.2.0`
- GitHub release URL: https://github.com/ersh123/self-ershov-memory/releases/tag/v0.2.0
- PyPI is still skipped; GitHub Release assets are the distribution path until a PyPI token and policy exist
- PR #3 is still draft and untouched

## Verification already run

- `python -m pytest -q`
- `python -m build`
- `git diff --check`
- exact-tag install smoke from `v0.2.0`

## Bottom line

`v0.2.0` is shipped, the plugin path is documented, and the repo can be installed or updated through Hermes without any PyPI dependency.

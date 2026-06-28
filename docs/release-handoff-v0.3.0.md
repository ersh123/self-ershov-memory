# Self Ershov Memory v0.3.0 Handoff

This is the short follow-up note for the v0.3.0 release lane.

## Read these first

- `docs/release-notes-v0.3.0.md` for the shipped change summary
- `CHANGELOG.md` for the version history
- `docs/install-update.md` for the install and update path

## Current release facts

- Plugin version: `0.3.0`
- GitHub release: `v0.3.0`
- GitHub release URL: https://github.com/ersh123/self-ershov-memory/releases/tag/v0.3.0
- PR #3 stays separate while draft and must not be merged as part of this sprint

## Verification gates

- `python -m pytest -q`
- `git diff --check`
- `python3 -m build`
- temp-only Ershov smoke with `HERMES_ERSHOV_STATE_ROOT`, including a negative path-policy smoke that rejects `skill -> README.md` before live writeback and a source-secret preflight smoke that blocks provider calls before source serialization

## Bottom line

`v0.3.0` is built, verified, tagged, and published.
It is the Ershov Inbox release: queue-level operator review, recent-session harvest plumbing, proposal metadata surfacing, and inbox digest cron support.

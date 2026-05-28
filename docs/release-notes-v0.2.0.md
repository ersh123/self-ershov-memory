# Hermes Dreaming v0.2.0 Release Notes

Status: approved for release and shipped as `v0.2.0` on 2026-05-28.

## What changed since v0.1.1

- Review UX got a real decision loop: `dreaming summarize <artifact>`, `dreaming approve <artifact> <proposal-id|all>`, `dreaming reject <artifact> <proposal-id> --reason ...`, and `dreaming review --open` now make the artifact easier to inspect and act on.
- Approvals and rejections persist in artifact metadata and audit history. They do not touch live roots until `apply` runs.
- Provider output is now stricter and safer. Proposal blobs must validate before they become real proposals, and provenance has to point back to the source bundle instead of some made-up path.
- The digest flow is now local and deterministic. It can rank artifacts and proposals, show what changed since the last dream, and render a weekly rollup without sending anything to Telegram by default.
- Onboarding is finally honest and usable. The repo now includes install/update docs, an offline quickstart, persona examples, and a safety page that spells out what Dreaming can and cannot mutate.
- The first phase-7 slice landed as a real dogfoodable feature: `dreaming report-card` now renders a redacted shareable report card from an artifact and can emit a JSON companion.
- Live-memory policy work added idempotence and capacity guardrails, plus test coverage that keeps the real `~/.hermes` state out of the way during verification.

## Verification run

Commands run during integration:

- `python -m pytest -q`
- `python -m build`
- `git diff --check`
- docs grep for stale PyPI claims and false release text

Results:

- full test suite passed
- build passed
- diff check passed
- docs stayed honest about the PyPI namespace collision and did not claim a PyPI release

## Packaging and distribution notes

- PyPI is still skipped. The `hermes-dreaming` namespace is already taken by someone else, so do not publish under that name.
- If distribution is revisited, it probably needs a new package name, likely `hermes-agent-dreaming`.
- GitHub release/tag creation is handled in this shipping step for `v0.2.0`.

## Release verdict

This is the next obvious release after `v0.1.1`.
It is materially better for both Tony and external users, and it is now the shipped `v0.2.0` line.

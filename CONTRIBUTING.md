# Contributing to Self Ershov Memory

Self Ershov Memory is shipped, but contributor support is still being tightened up.
Please follow the safety and review expectations below before opening a pull request.

## Before you start

Read these first:

- `README.md`
- `brief.md`
- `specs/mvp-implementation-plan.md`
- `docs/release-checklist.md`
- `reviews/final-sanity.md`

## Local setup

```bash
python -m pip install -e .[dev]
pytest -q
python -m build --wheel
```

Useful smoke checks:

```bash
ershov --help
ershov status
```

## Repo rules

- Do not tag, publish, or release anything without Niko's explicit approval.
- Only repo admins can create releases or tags unless Niko explicitly grants write access.
- Keep live roots and artifact roots separate.
- `.ershov/` is runtime output, not source.
- If you touch memory, user, skill, or fact writeback behavior, include provenance and tests.
- Do not put secrets, private tokens, passwords, or personal data into docs, fixtures, examples, or proposal text.
- If you change apply, discard, validation, or backup behavior, add or update tests.
- Keep PRs small enough that a human can review them without squinting.

## Pre-merge checklist

- [ ] `git diff --check`
- [ ] `pytest -q`
- [ ] `python -m build --wheel`
- [ ] no secrets or private data in the diff
- [ ] docs updated if behavior changed
- [ ] release-facing text reviewed if you touched user-visible commands or safety rules

## Where to open changes

Use the issue templates under `.github/ISSUE_TEMPLATE/` for bugs, feature requests, and docs fixes.
If the change affects writeback safety or release behavior, call that out explicitly in the issue or PR.

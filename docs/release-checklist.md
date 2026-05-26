# Hermes Dreaming Release Checklist

This is a pre-release checklist only.

**Do not tag, publish, or release this repo until Tony explicitly says so.**

## 1. First pass

- [ ] Read `reviews/final-sanity.md`
- [ ] Read `brief.md`
- [ ] Read `specs/mvp-implementation-plan.md`
- [ ] Confirm no new blockers were introduced after the last QA pass

## 2. Repo hygiene

- [ ] `git status -sb` is clean, or only contains intentional release-facing changes
- [ ] `git diff --check` is clean
- [ ] No stray temp files, caches, or local artifacts are present
- [ ] No secrets, tokens, passwords, or personal paths are in docs or source

## 3. Documentation consistency

- [ ] `README.md` matches the current CLI and artifact layout
- [ ] `brief.md` matches the current contract and non-goals
- [ ] `specs/mvp-implementation-plan.md` matches the shipped implementation
- [ ] `CHANGELOG.md` only lists features that actually exist

## 4. Verification

- [ ] `pytest -q`
- [ ] `python -m pip install build` if needed
- [ ] `python -m build --wheel`
- [ ] Smoke the CLI with `dreaming status`
- [ ] Smoke `dreaming create`, `validate`, `apply`, and `discard` on temp fixtures

## 5. Release gate

- [ ] Confirm Tony has explicitly approved release
- [ ] Confirm the intended version/tag is still correct
- [ ] Confirm nothing is half-finished in sibling worktrees or other release notes
- [ ] Only then consider a commit, tag, or publish step

## Verdict rule

- If any box is unchecked, the answer is **not released yet**.
- If all boxes are checked, pause and wait for explicit release approval before tagging.

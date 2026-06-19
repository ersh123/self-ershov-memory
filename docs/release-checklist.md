# Hermes Ershov Release Checklist

This is a pre-release checklist only.

**Do not tag, publish, or release this repo until Niko explicitly says so.**
Contributor documentation and GitHub templates are welcome, but they do not constitute release approval.

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
- [ ] `python -m build`
- [ ] Smoke wheel and source distribution installs against all public CLI aliases
- [ ] Smoke the CLI with `ershov status`
- [ ] Smoke `ershov create`, `review`, `diff`, `validate`, `apply`, and `discard` on temp fixtures
- [ ] Smoke `ershov compact` on terminal artifacts
- [ ] Smoke `ershov nightly --no-llm`
- [ ] Smoke `ershov nightly --no-llm` with no eligible markers: exits `no-op`, creates no invalid empty artifact
- [ ] Smoke `HERMES_ERSHOV_SESSION_DB=/tmp/state.db ershov nightly --no-llm` with controlled marker input through the installed CLI
- [ ] Smoke the root Hermes plugin wrapper: `python scripts/hermes_plugin_smoke.py`
- [ ] Smoke `ershov install-cron`
- [ ] Smoke `ershov install-systemd --dry-run`
- [ ] After a real scheduled run, smoke `ershov soak --state-root ~/.hermes/ershov --since-hours 30 --require-timer`
- [ ] Smoke `ershov update --check` and the real `ershov update --no-verify` path on a disposable repo

## 5. Release gate

- [ ] Confirm Niko has explicitly approved release
- [ ] Confirm the intended version/tag is still correct
- [ ] Confirm nothing is half-finished in sibling worktrees or other release notes
- [ ] Only then consider a commit, tag, or publish step

## Verdict rule

- If any box is unchecked, the answer is **not released yet**.
- If all boxes are checked, pause and wait for explicit release approval before tagging.

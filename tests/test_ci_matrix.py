from __future__ import annotations

from pathlib import Path
import re


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_ci_workflow_shows_release_shaped_test_matrix() -> None:
    text = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    for version in ("'3.11'", "'3.12'", "'3.13'"):
        assert version in text
    for gate in (
        "git diff --check",
        "uses: astral-sh/setup-uv@fac544c07dec837d0ccb6301d7b5580bf5edae39 # v8.2.0",
        "uv sync --locked --extra dev",
        "python -m compileall -q __init__.py src scripts",
        "pytest -q",
        "--cov=hermes_dreaming",
        "--cov-report=xml",
        "--cov-fail-under=80",
        "pytest -q tests/test_pbt.py",
        "python scripts/hermes_plugin_smoke.py",
        "python -m build",
        "dist/*.whl",
        "dist/*.tar.gz",
        "uv run --no-project --isolated --with dist/*.whl ershov --help",
        "uv run --no-project --isolated --with dist/*.tar.gz ershov --help",
        "providers doctor --provider offline-marker --strict",
        "providers doctor --provider deepseek --env-file /tmp/ershov-wheel-nightly.env --fix-plan --strict",
        "status --release-gate",
        "status --release-gate --state-root /tmp/ershov-wheel-smoke-state --require-provider deepseek --provider-env-file /tmp/ershov-wheel-nightly.env --fix-plan",
        "soak --state-root /tmp/ershov-wheel-smoke-state --since-hours 30 --min-successful 1 --require-timer --require-source systemd",
        "DEEPSEEK_API_KEY=<secret>",
        "sk-ci-do-not-print",
        "secret leaked from soak fix-plan",
    ):
        assert gate in text


def test_codeql_workflow_is_scheduled_and_pr_gated() -> None:
    text = (REPO_ROOT / ".github" / "workflows" / "codeql.yml").read_text(encoding="utf-8")
    top_level_permissions = text.split("concurrency:", 1)[0]
    analyze_job = text.split("  analyze:", 1)[1]

    assert "pull_request:" in text
    assert "schedule:" in text
    assert "workflow_dispatch:" in text
    assert "languages: python" in text
    assert "security-events: write" not in top_level_permissions
    assert "permissions:\n      contents: read\n      security-events: write" in analyze_job
    assert "persist-credentials: false" in text


def test_checkouts_do_not_persist_github_tokens() -> None:
    workflow_paths = sorted((REPO_ROOT / ".github" / "workflows").glob("*.yml"))

    for path in workflow_paths:
        text = path.read_text(encoding="utf-8")
        if "uses: actions/checkout@" in text:
            assert "persist-credentials: false" in text, path


def test_repeatable_analysis_workflows_cancel_stale_runs() -> None:
    for workflow_name in ("ci.yml", "codeql.yml", "scorecard.yml"):
        text = (REPO_ROOT / ".github" / "workflows" / workflow_name).read_text(encoding="utf-8")
        assert "concurrency:" in text, workflow_name
        assert "group: ${{ github.workflow }}-${{ github.ref }}" in text, workflow_name
        assert "cancel-in-progress: true" in text, workflow_name


def test_every_github_actions_job_has_a_timeout() -> None:
    workflow_paths = sorted((REPO_ROOT / ".github" / "workflows").glob("*.yml"))

    for path in workflow_paths:
        lines = path.read_text(encoding="utf-8").splitlines()
        job_lines = [
            index
            for index, line in enumerate(lines)
            if line.startswith("  ") and not line.startswith("    ") and line.rstrip().endswith(":")
        ]
        for index, start in enumerate(job_lines):
            end = job_lines[index + 1] if index + 1 < len(job_lines) else len(lines)
            chunk = "\n".join(lines[start:end])
            if "runs-on:" in chunk:
                assert "timeout-minutes:" in chunk, (path, lines[start].strip())


def test_github_actions_are_pinned_to_full_commit_shas() -> None:
    workflow_paths = sorted((REPO_ROOT / ".github" / "workflows").glob("*.yml"))
    action_line = re.compile(r"uses:\s+[-\w./]+@[0-9a-f]{40}\s+#\s+v?[0-9][-\w.]*$")

    for path in workflow_paths:
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped.startswith("uses: "):
                continue
            assert action_line.search(stripped), (path, stripped)


def test_scorecard_workflow_reports_supply_chain_security_to_code_scanning() -> None:
    text = (REPO_ROOT / ".github" / "workflows" / "scorecard.yml").read_text(encoding="utf-8")

    for phrase in (
        "schedule:",
        "workflow_dispatch:",
        "contents: read",
        "security-events: write",
        "id-token: write",
        "uses: ossf/scorecard-action@4eaacf0543bb3f2c246792bd56e8cdeffafb205a # v2.4.3",
        "uses: actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a # v7",
        "uses: actions/download-artifact@3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c # v8",
        "results_file: scorecard-results.sarif",
        "results_format: sarif",
        "publish_results: true",
        "uses: github/codeql-action/upload-sarif@8aad20d150bbac5944a9f9d289da16a4b0d87c1e # v4",
        "sarif_file: scorecard-results.sarif",
        "persist-credentials: false",
    ):
        assert phrase in text
    top_level_permissions = text.split("jobs:", 1)[0]
    assert "security-events: write" not in top_level_permissions
    assert "id-token: write" not in top_level_permissions


def test_dependabot_monitors_actions_and_python_dependencies() -> None:
    text = (REPO_ROOT / ".github" / "dependabot.yml").read_text(encoding="utf-8")

    assert "version: 2" in text
    for ecosystem in ('package-ecosystem: "github-actions"', 'package-ecosystem: "uv"'):
        assert ecosystem in text
    assert text.count('directory: "/"') == 2
    assert text.count('interval: "weekly"') == 2
    assert "open-pull-requests-limit: 5" in text

    for workflow_name in ("ci.yml", "release.yml"):
        workflow = (REPO_ROOT / ".github" / "workflows" / workflow_name).read_text(encoding="utf-8")
        assert "uv sync --locked --extra dev" in workflow
        assert "uv run --locked --extra dev" in workflow
        assert "pip install" not in workflow


def test_python_classifier_matches_ci_matrix() -> None:
    pyproject = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    ci = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    testing_doc = (REPO_ROOT / "docs" / "testing.md").read_text(encoding="utf-8")

    for version in ("3.11", "3.12", "3.13"):
        assert f"'{version}'" in ci
        assert f"Programming Language :: Python :: {version}" in pyproject
        assert version in testing_doc

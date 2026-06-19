from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_ci_workflow_shows_release_shaped_test_matrix() -> None:
    text = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    for version in ("'3.11'", "'3.12'", "'3.13'"):
        assert version in text
    for gate in (
        "git diff --check",
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
        "/tmp/ershov-wheel-smoke/bin/ershov --help",
        "/tmp/ershov-sdist-smoke/bin/ershov --help",
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

    assert "pull_request:" in text
    assert "schedule:" in text
    assert "workflow_dispatch:" in text
    assert "languages: python" in text
    assert "security-events: write" in text
    assert "persist-credentials: false" in text


def test_checkouts_do_not_persist_github_tokens() -> None:
    workflow_paths = sorted((REPO_ROOT / ".github" / "workflows").glob("*.yml"))

    for path in workflow_paths:
        text = path.read_text(encoding="utf-8")
        if "uses: actions/checkout@" in text:
            assert "persist-credentials: false" in text, path


def test_scorecard_workflow_reports_supply_chain_security_to_code_scanning() -> None:
    text = (REPO_ROOT / ".github" / "workflows" / "scorecard.yml").read_text(encoding="utf-8")

    for phrase in (
        "schedule:",
        "workflow_dispatch:",
        "contents: read",
        "security-events: write",
        "id-token: write",
        "uses: ossf/scorecard-action@v2.4.3",
        "uses: actions/upload-artifact@v7",
        "uses: actions/download-artifact@v8",
        "results_file: scorecard-results.sarif",
        "results_format: sarif",
        "publish_results: true",
        "uses: github/codeql-action/upload-sarif@v4",
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
    for ecosystem in ('package-ecosystem: "github-actions"', 'package-ecosystem: "pip"'):
        assert ecosystem in text
    assert text.count('directory: "/"') == 2
    assert text.count('interval: "weekly"') == 2
    assert "open-pull-requests-limit: 5" in text


def test_python_classifier_matches_ci_matrix() -> None:
    pyproject = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    ci = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    testing_doc = (REPO_ROOT / "docs" / "testing.md").read_text(encoding="utf-8")

    for version in ("3.11", "3.12", "3.13"):
        assert f"'{version}'" in ci
        assert f"Programming Language :: Python :: {version}" in pyproject
        assert version in testing_doc

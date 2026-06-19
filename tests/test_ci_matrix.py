from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_ci_workflow_shows_release_shaped_test_matrix() -> None:
    text = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    for version in ("'3.11'", "'3.12'"):
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
        "status --release-gate",
    ):
        assert gate in text


def test_codeql_workflow_is_scheduled_and_pr_gated() -> None:
    text = (REPO_ROOT / ".github" / "workflows" / "codeql.yml").read_text(encoding="utf-8")

    assert "pull_request:" in text
    assert "schedule:" in text
    assert "workflow_dispatch:" in text
    assert "languages: python" in text

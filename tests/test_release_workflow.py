from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def _release_workflow() -> str:
    return (REPO_ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")


def test_release_workflow_build_job_uses_ci_strength_gates() -> None:
    text = _release_workflow()

    for gate in (
        "git diff --check",
        "uses: astral-sh/setup-uv@fac544c07dec837d0ccb6301d7b5580bf5edae39 # v8.2.0",
        'uv sync --locked --extra dev --python "3.12"',
        "python -m compileall -q __init__.py src scripts",
        "pytest -q --cov=hermes_dreaming",
        "--cov-fail-under=80",
        "pytest -q tests/test_pbt.py",
        "python scripts/hermes_plugin_smoke.py",
        "python -m build",
        "ershov providers doctor --provider offline-marker --strict",
        "ershov providers doctor --provider deepseek --env-file /tmp/ershov-release-nightly.env --fix-plan --strict",
        "ershov status --release-gate",
        "ershov status --release-gate --state-root /tmp/ershov-release-smoke-state --require-provider deepseek --provider-env-file /tmp/ershov-release-nightly.env --fix-plan",
        "ershov soak --state-root /tmp/ershov-release-smoke-state --since-hours 30 --min-successful 1 --require-timer --require-source systemd",
        "DEEPSEEK_API_KEY=<secret>",
        "sk-release-do-not-print",
        "secret leaked from soak fix-plan",
        "uv run --no-project --isolated --with dist/*.whl ershov revert --help",
        "uv run --no-project --isolated --with dist/*.tar.gz ershov --help",
    ):
        assert gate in text


def test_release_workflow_uploads_assets_only_for_release_event() -> None:
    text = _release_workflow()
    build_chunk, upload_chunk = text.split("  upload-release-assets:", 1)

    assert "workflow_dispatch:" in text
    assert "permissions:\n  contents: read" in text
    assert "contents: write" not in build_chunk
    assert "if: github.event_name == 'release'" in upload_chunk
    assert "permissions:\n      contents: write" in upload_chunk
    assert "uses: actions/upload-artifact@" in build_chunk
    assert "uses: actions/download-artifact@" in upload_chunk
    assert 'gh release upload "$GITHUB_REF_NAME" dist/* --clobber' in upload_chunk


def test_release_workflow_does_not_publish_to_package_indexes_or_create_releases() -> None:
    text = _release_workflow().lower()

    forbidden = (
        "twine",
        "pypa/gh-action-pypi-publish",
        "pypi-token",
        "id-token: write",
        "gh release create",
    )
    for phrase in forbidden:
        assert phrase not in text

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_readme_documents_product_only_contract_and_approval_loop() -> None:
    text = (REPO_ROOT / "README.md").read_text(encoding="utf-8")

    assert "# self-ershov-memory" in text
    assert "## Before → approval → after" in text
    assert "docs/before-after-approval.md" in text
    assert "Raw Hermes dialogues stay in `~/.hermes/state.db`" in text
    assert "`self-ershov-memory --dry-run --full`" in text
    assert "leaves files untouched" in text
    assert "`self-ershov-memory --execute --full`" in text
    assert "creates snapshots first" in text
    assert "## Test evidence" in text
    assert "42 pytest tests passing" in text
    assert "100% coverage for `self_ershov_memory`" in text
    assert "--cov-fail-under=100" in text
    assert "https://img.shields.io/badge/tests-42%20passing-brightgreen" in text


def test_readme_does_not_advertise_removed_legacy_cli_surface() -> None:
    text = (REPO_ROOT / "README.md").read_text(encoding="utf-8")

    forbidden = (
        "## Legacy compatibility",
        "ershov nightly",
        "ershov review",
        "ershov apply",
        "mnemos",
        "nightmem",
        "dreaming",
        "hermes-ershov",
        "OpenRouter",
    )
    for phrase in forbidden:
        assert phrase not in text


def test_pyproject_exports_only_product_package_and_cli() -> None:
    text = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")

    assert 'name = "self-ershov-memory"' in text
    assert 'self-ershov-memory = "self_ershov_memory.audit:main"' in text
    assert 'packages = ["src/self_ershov_memory"]' in text
    assert 'source = ["src/self_ershov_memory"]' in text
    assert "fail_under = 100" in text
    for phrase in (
        "hermes_dreaming",
        "hermes_ershov",
        "hermes_mnemos",
        "hermes-ershov =",
        "ershov =",
        "mnemos =",
        "nightmem =",
        "dreaming =",
    ):
        assert phrase not in text


def test_public_docs_have_no_staged_memory_brand_leaks() -> None:
    public_paths = [REPO_ROOT / "README.md", REPO_ROOT / "pyproject.toml"]
    public_paths.extend((REPO_ROOT / ".github" / "workflows").glob("*.yml"))

    forbidden = (
        "hermes_dreaming",
        "hermes_ershov",
        "hermes_mnemos",
        "hermes-ershov",
        "ershov nightly",
        "ershov review",
        "ershov apply",
        "OpenRouter",
    )
    for path in public_paths:
        text = path.read_text(encoding="utf-8")
        for phrase in forbidden:
            assert phrase not in text, path


def test_before_after_approval_evidence_doc_is_real() -> None:
    text = (REPO_ROOT / "docs" / "before-after-approval.md").read_text(encoding="utf-8")

    assert "## Raw dialogue evidence" in text
    assert "## BEFORE" in text
    assert "## APPROVAL" in text
    assert "## AFTER" in text
    assert "self-ershov-memory --dry-run --full" in text
    assert "self-ershov-memory --execute --full" in text
    assert "BEFORE files are unchanged after dry-run" in text
    assert "CI covers this exact loop" in text

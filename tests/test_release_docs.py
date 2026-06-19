from __future__ import annotations

from pathlib import Path
import re


REPO_ROOT = Path(__file__).resolve().parents[1]
PROVIDER_IDS = ("offline-marker", "openai-compatible", "deepseek", "openrouter", "ollama")


def test_changelog_provider_list_matches_public_provider_surface() -> None:
    text = (REPO_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "three built-in providers" not in text

    provider_line = next(line for line in text.splitlines() if "`ershov providers list`" in line)
    for provider in PROVIDER_IDS:
        assert provider in provider_line


def test_provider_specs_match_public_provider_surface() -> None:
    docs = [
        REPO_ROOT / "README.md",
        REPO_ROOT / "CHANGELOG.md",
        REPO_ROOT / "docs" / "release-notes-v0.4.0.md",
        REPO_ROOT / "specs" / "mvp-implementation-plan.md",
        REPO_ROOT / "specs" / "v0.4.0-plan.md",
    ]
    forbidden = ("three built-in providers", "existing three")
    for path in docs:
        text = path.read_text(encoding="utf-8")
        for phrase in forbidden:
            assert phrase not in text, path
        if "providers list" in text:
            for provider in PROVIDER_IDS:
                assert provider in text, path


def test_no_llm_docs_include_nightly_support() -> None:
    docs = [
        REPO_ROOT / "README.md",
        REPO_ROOT / "CHANGELOG.md",
        REPO_ROOT / "docs" / "release-notes-v0.4.0.md",
        REPO_ROOT / "specs" / "mvp-implementation-plan.md",
        REPO_ROOT / "specs" / "v0.4.0-plan.md",
    ]
    stale_phrases = (
        "`--no-llm` is a shorthand for `--provider offline-marker` on `create` and `review`",
        "`--no-llm` shorthand for `--provider offline-marker` on `create` and `review`",
        "The CLI accepts it on `create` and `review`",
    )
    for path in docs:
        text = path.read_text(encoding="utf-8")
        for phrase in stale_phrases:
            assert phrase not in text, path

    assert "`--no-llm` is a shorthand for `--provider offline-marker` on `create`, `review`, and `nightly`" in (
        REPO_ROOT / "CHANGELOG.md"
    ).read_text(encoding="utf-8")


def test_safety_doc_matches_current_quickstart_target_surface() -> None:
    text = (REPO_ROOT / "docs" / "safety.md").read_text(encoding="utf-8")
    assert "any other safe relative path" not in text
    assert "three target kinds" in text

    fixture_section = re.search(
        r"In the current offline fixture, the demo shows three target kinds:\n\n(?P<body>.*?)\n\n## It cannot mutate",
        text,
        flags=re.DOTALL,
    )
    assert fixture_section is not None
    assert fixture_section.group("body").splitlines() == [
        "- `fact`",
        "- `memory`",
        "- `user`",
    ]

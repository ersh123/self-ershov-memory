from __future__ import annotations

from pathlib import Path
import re


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_changelog_provider_list_matches_public_provider_surface() -> None:
    text = (REPO_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "three built-in providers" not in text

    provider_line = next(line for line in text.splitlines() if "`ershov providers list`" in line)
    for provider in ("offline-marker", "openai-compatible", "deepseek", "openrouter", "ollama"):
        assert provider in provider_line


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

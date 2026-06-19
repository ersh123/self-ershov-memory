from __future__ import annotations

from pathlib import Path
import re

from hermes_dreaming.providers import list_providers


REPO_ROOT = Path(__file__).resolve().parents[1]
PROVIDER_IDS = tuple(row.name for row in list_providers())


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


def test_quickstart_uses_temp_live_root_and_dry_run_before_apply() -> None:
    text = (REPO_ROOT / "docs" / "quickstart.md").read_text(encoding="utf-8")

    assert 'export DEMO_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/hermes-ershov-quickstart.XXXXXX")"' in text
    assert 'cp -R "$FIXTURE_ROOT/live" "$LIVE_ROOT"' in text
    assert 'export LIVE_ROOT="$(pwd)/examples/quickstart/live"' not in text

    dry_run = 'ershov apply "$ARTIFACT_DIR" --live-root "$LIVE_ROOT" --backup-root "$BACKUP_ROOT" --dry-run'
    real_apply = 'ershov apply "$ARTIFACT_DIR" --live-root "$LIVE_ROOT" --backup-root "$BACKUP_ROOT"'
    lines = text.splitlines()
    assert dry_run in lines
    assert real_apply in lines
    assert lines.index(dry_run) < lines.index(real_apply)
    assert "`apply: dry-run`" in text
    assert "`mode: dry-run`" not in text
    assert "leave `$LIVE_ROOT` and `$BACKUP_ROOT` unchanged" in text
    assert "records backup evidence in `manifest.json`" in text
    assert "remove files that were created by apply" in text
    assert 'ershov revert "$ARTIFACT_DIR" --live-root "$LIVE_ROOT" --backup-root "$BACKUP_ROOT" --yes --validate' in text
    assert "/tmp/hermes-ershov-quickstart/artifacts" not in text
    assert "/tmp/hermes-ershov-quickstart.<suffix>/artifacts" in text


def test_readme_has_single_discard_example_and_trust_loop_notes() -> None:
    text = (REPO_ROOT / "README.md").read_text(encoding="utf-8")

    assert text.count("ershov discard ./artifacts/<artifact-id> --archive-root ./archive") == 1
    assert "`--dry-run` deliberately creates no backups and writes no live files" in text
    assert "records backup evidence in the artifact manifest before live writes" in text
    assert "`backup_records` tombstones" in text


def test_release_docs_use_current_test_count() -> None:
    docs = [
        REPO_ROOT / "docs" / "release-notes-v0.4.0.md",
        REPO_ROOT / "docs" / "release-handoff-v0.4.0.md",
    ]
    for path in docs:
        text = path.read_text(encoding="utf-8")
        assert "183 tests" not in text, path
        assert "185 tests" not in text, path
        assert "186 tests" not in text, path
        assert "187 tests" not in text, path
        assert "188 tests" not in text, path
        assert "189 tests" not in text, path
        assert "190 tests" not in text, path
        assert "191 tests" not in text, path
        assert "192 tests" not in text, path
        assert "193 tests" not in text, path
        assert "194 tests" in text, path


def test_release_docs_document_stronger_public_stable_promotion_gate() -> None:
    docs = [
        REPO_ROOT / "README.md",
        REPO_ROOT / "docs" / "release-checklist.md",
        REPO_ROOT / "docs" / "install-update.md",
        REPO_ROOT / "docs" / "onboarding.md",
        REPO_ROOT / "docs" / "release-notes-v0.4.0.md",
    ]
    gate = "--since-hours 96 --min-successful 3 --strict-systemd"
    for path in docs:
        text = path.read_text(encoding="utf-8")
        assert gate in text, path

from __future__ import annotations

from pathlib import Path

from hermes_dreaming.artifact import DreamArtifact, DreamProposal
from hermes_dreaming.validation import validate_artifact, validate_memory_op


def _artifact_with(proposal: DreamProposal, tmp_path: Path) -> DreamArtifact:
    return DreamArtifact(
        artifact_id="artifact-001",
        created_at="2026-05-25T12:00:00Z",
        provider="offline-marker",
        status="staged",
        workspace_root=str(tmp_path),
        source_roots=[str(tmp_path)],
        report="# Report",
        sources=[],
        proposals=[proposal],
    )


def test_validate_rejects_path_traversal(tmp_path: Path) -> None:
    proposal = DreamProposal(
        id="proposal-bad-path",
        target_kind="memory",
        target_path="../outside.md",
        mode="append_text",
        summary="bad path",
        provenance=["sessions/1.md:1"],
        proposed_text="- Do not write outside roots.",
        approved=True,
    )
    artifact = _artifact_with(proposal, tmp_path)

    errors = validate_artifact(artifact, live_root=tmp_path)

    assert errors
    assert any("outside" in error.lower() for error in errors)


def test_validate_rejects_secret_like_content(tmp_path: Path) -> None:
    proposal = DreamProposal(
        id="proposal-secret",
        target_kind="memory",
        target_path="memory.md",
        mode="append_text",
        summary="contains secret-like string",
        provenance=["sessions/1.md:1"],
        proposed_text="- api_key = 'ghp_1234567890abcdef1234567890abcdef1234'",
        approved=True,
    )
    artifact = _artifact_with(proposal, tmp_path)

    errors = validate_artifact(artifact, live_root=tmp_path)

    assert errors
    assert any("secret" in error.lower() for error in errors)


def test_validate_rejects_missing_provenance(tmp_path: Path) -> None:
    proposal = DreamProposal(
        id="proposal-no-provenance",
        target_kind="fact",
        target_path="facts.jsonl",
        mode="jsonl_append",
        summary="missing provenance",
        provenance=[],
        proposed_text='{"type": "preference", "value": "concise"}',
        approved=True,
    )
    artifact = _artifact_with(proposal, tmp_path)

    errors = validate_artifact(artifact, live_root=tmp_path)

    assert errors
    assert any("provenance" in error.lower() for error in errors)


def test_validate_memory_op_rejects_non_live_targets() -> None:
    errors = validate_memory_op(
        op="remove",
        target="fact",
        old_text='{"key": "tone"}',
        new_text=None,
        reason="facts are staged artifact writes, not live memory ops",
        sources=["sessions/1.md:4"],
        score=0.9,
        supersession_confidence=0.9,
    )

    assert any("unsupported live target kind" in error for error in errors)

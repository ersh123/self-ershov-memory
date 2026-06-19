from __future__ import annotations

from pathlib import Path

import pytest

from hermes_dreaming.artifact import DreamArtifact, DreamProposal, load_artifact, text_sha256, write_artifact
from hermes_dreaming.apply import (
    REVERT_FILE,
    DreamRevertError,
    apply_artifact,
    revert_artifact,
)
from hermes_dreaming.cli import main


def _write_artifact(
    tmp_path: Path,
    *,
    artifact_id: str = "artifact-revert",
    live_root: Path,
    proposals: list[DreamProposal],
    status: str = "validated",
    applied: bool = False,
    backup_paths: list[str] | None = None,
) -> Path:
    artifact = DreamArtifact(
        artifact_id=artifact_id,
        created_at="2026-05-25T12:00:00Z",
        provider="offline-marker",
        status="applied" if applied else status,
        workspace_root=str(live_root),
        source_roots=[str(tmp_path / "sources")],
        report="# Report",
        sources=[],
        proposals=proposals,
        applied_proposal_ids=[p.id for p in proposals if p.applied] if applied else [],
        backup_paths=backup_paths or [],
    )
    artifact_dir = tmp_path / artifact_id
    write_artifact(artifact, artifact_dir)
    return artifact_dir


def _memory_proposal(tmp_path: Path, *, target_path: str = "memory.md", priority: str = "normal", risk: str = "low", approved: bool = True, id_suffix: str = "") -> DreamProposal:
    return DreamProposal(
        id=f"proposal-{target_path}{id_suffix}",
        target_kind="memory",
        target_path=target_path,
        mode="append_text",
        summary="append memory note",
        provenance=["sessions/1.md:1"],
        proposed_text="- Keep updates short and concrete.",
        approved=approved,
        priority=priority,
        risk=risk,
    )


def _skill_proposal(*, target_path: str = "skills/review.md", approved: bool = True) -> DreamProposal:
    return DreamProposal(
        id=f"proposal-{target_path}",
        target_kind="skill",
        target_path=target_path,
        mode="append_text",
        summary="append skill note",
        provenance=["sessions/1.md:2"],
        proposed_text="- Preserve review gates.",
        approved=approved,
        priority="normal",
        risk="low",
    )


def test_apply_then_revert_roundtrip_restores_live_state(tmp_path: Path) -> None:
    live_root = tmp_path / "live"
    live_root.mkdir()
    memory = live_root / "memory.md"
    memory.write_text("# MEMORY\n\n- Existing note\n", encoding="utf-8")

    proposal = _memory_proposal(tmp_path)
    proposal.applied = True
    artifact_dir = _write_artifact(
        tmp_path,
        live_root=live_root,
        proposals=[proposal],
        applied=True,
    )
    backup_root = tmp_path / "backups"
    # Simulate the post-apply state and backup snapshot that apply_artifact would produce.
    memory.write_text("# MEMORY\n\n- Existing note\n- Keep updates short and concrete.\n", encoding="utf-8")
    backup_root.mkdir(parents=True, exist_ok=True)
    backup_path = backup_root / "memory.md"
    backup_path.write_text("# MEMORY\n\n- Existing note\n", encoding="utf-8")
    loaded = load_artifact(artifact_dir)
    loaded.backup_paths = [str(backup_path)]
    write_artifact(loaded, artifact_dir)

    reverted = revert_artifact(
        artifact_dir,
        live_root=live_root,
        backup_root=backup_root,
        yes=True,
        validate_after=True,
    )

    assert reverted.status == "reverted"
    assert reverted.reverted_at is not None
    assert reverted.validation_errors == []
    assert memory.read_text(encoding="utf-8") == "# MEMORY\n\n- Existing note\n"
    assert (artifact_dir / REVERT_FILE).exists()
    revert_md = (artifact_dir / REVERT_FILE).read_text(encoding="utf-8")
    assert "Restored files" in revert_md
    assert "Rolled-back proposals" in revert_md
    assert "Post-revert validation" in revert_md
    assert "- passed" in revert_md
    # Applied proposal was rolled back to approved state.
    assert reverted.proposals[0].approved is True
    assert reverted.proposals[0].applied is False
    assert any(event["action"] == "reverted" for event in reverted.revert_audit_events)
    assert any(event["action"] == "revert_validation_passed" for event in reverted.revert_audit_events)


def test_apply_then_revert_removes_file_created_by_apply(tmp_path: Path) -> None:
    live_root = tmp_path / "live"
    live_root.mkdir()
    artifact_dir = _write_artifact(
        tmp_path,
        artifact_id="artifact-revert-created-file",
        live_root=live_root,
        proposals=[_skill_proposal(target_path="skills/new-review.md")],
        status="validated",
    )
    backup_root = tmp_path / "backups"

    applied = apply_artifact(artifact_dir, live_root=live_root, backup_root=backup_root)

    created_file = live_root / "skills" / "new-review.md"
    assert created_file.exists()
    assert applied.backup_paths == []
    assert applied.backup_records == [
        {
            "proposal_id": "proposal-skills/new-review.md",
            "target_relative": "skills/new-review.md",
            "existed_before": False,
            "post_apply_exists": True,
            "post_apply_sha256": text_sha256(created_file.read_text(encoding="utf-8")),
        }
    ]

    reverted = revert_artifact(artifact_dir, live_root=live_root, backup_root=backup_root, yes=True)

    assert reverted.status == "reverted"
    assert not created_file.exists()
    assert reverted.proposals[0].approved is True
    assert reverted.proposals[0].applied is False
    revert_md = (artifact_dir / REVERT_FILE).read_text(encoding="utf-8")
    assert "Removed files: `1`" in revert_md
    assert str(created_file) in revert_md
    assert "not run; pass `--validate`" in revert_md
    assert any(event["action"] == "revert_validation_not_run" for event in reverted.revert_audit_events)


def test_revert_rejects_non_applied_artifact(tmp_path: Path) -> None:
    live_root = tmp_path / "live"
    live_root.mkdir()
    proposal = _memory_proposal(tmp_path)
    artifact_dir = _write_artifact(
        tmp_path,
        live_root=live_root,
        proposals=[proposal],
        status="validated",
    )

    with pytest.raises(DreamRevertError, match="must be 'applied'"):
        revert_artifact(artifact_dir, live_root=live_root, backup_root=tmp_path / "backups", yes=True)


def test_revert_without_yes_prints_confirmation_and_returns_via_cli(tmp_path: Path, capsys) -> None:
    live_root = tmp_path / "live"
    live_root.mkdir()
    memory = live_root / "memory.md"
    memory.write_text("# MEMORY\n\n- Existing note\n", encoding="utf-8")

    proposal = _memory_proposal(tmp_path)
    proposal.applied = True
    artifact_dir = _write_artifact(
        tmp_path,
        live_root=live_root,
        proposals=[proposal],
        applied=True,
    )
    backup_root = tmp_path / "backups"
    backup_root.mkdir(parents=True, exist_ok=True)
    backup_path = backup_root / "memory.md"
    backup_path.write_text("# MEMORY\n\n- Existing note\n", encoding="utf-8")
    memory.write_text("# MEMORY\n\n- Existing note\n- Keep updates short and concrete.\n", encoding="utf-8")
    loaded = load_artifact(artifact_dir)
    loaded.backup_paths = [str(backup_path)]
    write_artifact(loaded, artifact_dir)

    # CLI without --yes prints the confirmation prompt and returns exit 2.
    exit_code = main(["revert", str(artifact_dir), "--live-root", str(live_root), "--backup-root", str(backup_root)])
    assert exit_code == 2
    output = capsys.readouterr().out
    assert "Re-run with --yes to confirm" in output
    # Live file is untouched.
    assert "- Keep updates short and concrete." in memory.read_text(encoding="utf-8")


def test_revert_fails_loud_on_missing_backup_and_leaves_live_state(tmp_path: Path) -> None:
    live_root = tmp_path / "live"
    live_root.mkdir()
    memory = live_root / "memory.md"
    memory.write_text("# MEMORY\n\n- Existing note\n", encoding="utf-8")

    proposal = _memory_proposal(tmp_path)
    proposal.applied = True
    artifact_dir = _write_artifact(
        tmp_path,
        live_root=live_root,
        proposals=[proposal],
        applied=True,
        backup_paths=[str(tmp_path / "backups" / "memory.md")],
    )

    with pytest.raises(DreamRevertError, match="missing backup file"):
        revert_artifact(artifact_dir, live_root=live_root, backup_root=tmp_path / "backups", yes=True)

    # Live state is untouched.
    assert memory.read_text(encoding="utf-8") == "# MEMORY\n\n- Existing note\n"
    # Audit event recorded.
    loaded = load_artifact(artifact_dir)
    assert any(event["action"] == "revert_failed" for event in loaded.revert_audit_events)


def test_apply_then_revert_uses_post_apply_sha_to_avoid_false_drift(tmp_path: Path) -> None:
    live_root = tmp_path / "live"
    live_root.mkdir()
    memory = live_root / "memory.md"
    memory.write_text("# MEMORY\n\n- Existing note\n", encoding="utf-8")

    artifact_dir = _write_artifact(
        tmp_path,
        artifact_id="artifact-revert-post-apply-sha",
        live_root=live_root,
        proposals=[_memory_proposal(tmp_path)],
        status="validated",
    )
    backup_root = tmp_path / "backups"

    apply_artifact(artifact_dir, live_root=live_root, backup_root=backup_root)
    reverted = revert_artifact(artifact_dir, live_root=live_root, backup_root=backup_root, yes=True)

    assert memory.read_text(encoding="utf-8") == "# MEMORY\n\n- Existing note\n"
    assert not [event for event in reverted.revert_audit_events if event["action"] == "drift_detected"]


def test_revert_records_drift_against_post_apply_sha(tmp_path: Path) -> None:
    live_root = tmp_path / "live"
    live_root.mkdir()
    memory = live_root / "memory.md"
    memory.write_text("# MEMORY\n\n- Existing note\n", encoding="utf-8")

    artifact_dir = _write_artifact(
        tmp_path,
        artifact_id="artifact-revert-post-apply-drift",
        live_root=live_root,
        proposals=[_memory_proposal(tmp_path)],
        status="validated",
    )
    backup_root = tmp_path / "backups"

    applied = apply_artifact(artifact_dir, live_root=live_root, backup_root=backup_root)
    expected_sha = str(applied.backup_records[0]["post_apply_sha256"])
    memory.write_text(memory.read_text(encoding="utf-8") + "- Operator edit after apply\n", encoding="utf-8")
    drift_sha = text_sha256(memory.read_text(encoding="utf-8"))

    reverted = revert_artifact(artifact_dir, live_root=live_root, backup_root=backup_root, yes=True)

    drift_events = [event for event in reverted.revert_audit_events if event["action"] == "drift_detected"]
    assert len(drift_events) == 1
    assert drift_events[0]["expected_sha256"] == expected_sha
    assert drift_events[0]["live_sha256"] == drift_sha
    assert "recorded post-apply snapshot" in drift_events[0]["detail"]
    assert drift_events[0].get("evidence_strength") is None
    assert memory.read_text(encoding="utf-8") == "# MEMORY\n\n- Existing note\n"


def test_revert_validate_after_records_failure_after_restore(tmp_path: Path) -> None:
    live_root = tmp_path / "live"
    live_root.mkdir()
    memory = live_root / "memory.md"
    memory.write_text("# MEMORY\n\n- Existing note\n- Bad applied text\n", encoding="utf-8")

    proposal = _memory_proposal(tmp_path)
    proposal.summary = ""
    proposal.applied = True
    artifact_dir = _write_artifact(
        tmp_path,
        live_root=live_root,
        proposals=[proposal],
        applied=True,
    )
    backup_root = tmp_path / "backups"
    backup_root.mkdir(parents=True, exist_ok=True)
    backup_path = backup_root / "memory.md"
    backup_path.write_text("# MEMORY\n\n- Existing note\n", encoding="utf-8")
    loaded = load_artifact(artifact_dir)
    loaded.backup_paths = [str(backup_path)]
    write_artifact(loaded, artifact_dir)

    with pytest.raises(DreamRevertError, match="post-revert validation failed"):
        revert_artifact(
            artifact_dir,
            live_root=live_root,
            backup_root=backup_root,
            yes=True,
            validate_after=True,
        )

    assert memory.read_text(encoding="utf-8") == "# MEMORY\n\n- Existing note\n"
    manifest = load_artifact(artifact_dir)
    assert manifest.status == "reverted"
    assert manifest.validation_errors == ["proposal proposal-memory.md is missing a summary"]
    assert any(event["action"] == "revert_validation_failed" for event in manifest.revert_audit_events)
    revert_md = (artifact_dir / REVERT_FILE).read_text(encoding="utf-8")
    assert "Post-revert validation" in revert_md
    assert "- failed" in revert_md
    assert "proposal proposal-memory.md is missing a summary" in revert_md


def test_revert_records_drift_event_when_live_drifted_after_apply(tmp_path: Path) -> None:
    live_root = tmp_path / "live"
    live_root.mkdir()
    memory = live_root / "memory.md"
    backup_root = tmp_path / "backups"
    backup_root.mkdir(parents=True, exist_ok=True)
    backup_path = backup_root / "memory.md"
    backup_path.write_text("# MEMORY\n\n- Existing note\n", encoding="utf-8")

    # Simulate: backup has pre-apply content; live has drifted to something else
    # after the apply, before revert. Revert should still restore from backup and
    # record a drift_detected audit event.
    memory.write_text(
        "# MEMORY\n\n- Existing note\n- Keep updates short and concrete.\n- Operator edit after apply\n",
        encoding="utf-8",
    )

    proposal = _memory_proposal(tmp_path)
    proposal.applied = True
    artifact_dir = _write_artifact(
        tmp_path,
        live_root=live_root,
        proposals=[proposal],
        applied=True,
        backup_paths=[str(backup_path)],
    )

    reverted = revert_artifact(artifact_dir, live_root=live_root, backup_root=backup_root, yes=True)

    # Live state was restored from backup despite drift.
    assert memory.read_text(encoding="utf-8") == "# MEMORY\n\n- Existing note\n"
    # Drift was recorded.
    drift_events = [event for event in reverted.revert_audit_events if event["action"] == "drift_detected"]
    assert drift_events
    assert any("memory.md" in event.get("target", "") for event in drift_events)
    assert drift_events[0]["evidence_strength"] == "legacy-degraded"
    assert "post_apply_sha256 missing" in drift_events[0]["evidence_reason"]
    revert_md = (artifact_dir / REVERT_FILE).read_text(encoding="utf-8")
    assert "evidence: legacy-degraded" in revert_md


def test_revert_marks_missing_legacy_live_file_as_degraded_evidence(tmp_path: Path) -> None:
    live_root = tmp_path / "live"
    live_root.mkdir()
    backup_root = tmp_path / "backups"
    backup_root.mkdir(parents=True, exist_ok=True)
    backup_path = backup_root / "memory.md"
    backup_path.write_text("# MEMORY\n\n- Existing note\n", encoding="utf-8")

    proposal = _memory_proposal(tmp_path)
    proposal.applied = True
    artifact_dir = _write_artifact(
        tmp_path,
        live_root=live_root,
        proposals=[proposal],
        applied=True,
        backup_paths=[str(backup_path)],
    )

    reverted = revert_artifact(artifact_dir, live_root=live_root, backup_root=backup_root, yes=True)

    memory = live_root / "memory.md"
    assert memory.read_text(encoding="utf-8") == "# MEMORY\n\n- Existing note\n"
    drift_events = [event for event in reverted.revert_audit_events if event["action"] == "drift_detected"]
    assert len(drift_events) == 1
    assert drift_events[0]["detail"] == "live file was missing at revert time"
    assert drift_events[0]["evidence_strength"] == "legacy-degraded"
    assert "legacy backup record" in drift_events[0]["evidence_reason"]
    assert "evidence: legacy-degraded" in (artifact_dir / REVERT_FILE).read_text(encoding="utf-8")


def test_revert_writes_manifest_audit_and_revert_md(tmp_path: Path) -> None:
    live_root = tmp_path / "live"
    live_root.mkdir()
    memory = live_root / "memory.md"
    memory.write_text("# MEMORY\n\n- Existing note\n", encoding="utf-8")

    proposal = _memory_proposal(tmp_path)
    proposal.applied = True
    artifact_dir = _write_artifact(
        tmp_path,
        live_root=live_root,
        proposals=[proposal],
        applied=True,
    )
    backup_root = tmp_path / "backups"
    backup_root.mkdir(parents=True, exist_ok=True)
    backup_path = backup_root / "memory.md"
    backup_path.write_text("# MEMORY\n\n- Existing note\n", encoding="utf-8")
    memory.write_text("# MEMORY\n\n- Existing note\n- Keep updates short and concrete.\n", encoding="utf-8")
    loaded = load_artifact(artifact_dir)
    loaded.backup_paths = [str(backup_path)]
    write_artifact(loaded, artifact_dir)

    revert_artifact(artifact_dir, live_root=live_root, backup_root=backup_root, yes=True)

    # Manifest updated to reverted + reverted_at
    manifest = load_artifact(artifact_dir)
    assert manifest.status == "reverted"
    assert manifest.reverted_at is not None
    # Revert events are persisted in manifest.revert_audit_events.
    assert any(event["action"] == "reverted" for event in manifest.revert_audit_events)
    # REVERT.md present
    assert (artifact_dir / REVERT_FILE).exists()


def test_cli_revert_end_to_end_with_yes(tmp_path: Path, capsys) -> None:
    live_root = tmp_path / "live"
    live_root.mkdir()
    memory = live_root / "memory.md"
    memory.write_text("# MEMORY\n\n- Existing note\n", encoding="utf-8")

    proposal = _memory_proposal(tmp_path)
    proposal.applied = True
    artifact_dir = _write_artifact(
        tmp_path,
        live_root=live_root,
        proposals=[proposal],
        applied=True,
    )
    backup_root = tmp_path / "backups"
    backup_root.mkdir(parents=True, exist_ok=True)
    backup_path = backup_root / "memory.md"
    backup_path.write_text("# MEMORY\n\n- Existing note\n", encoding="utf-8")
    memory.write_text("# MEMORY\n\n- Existing note\n- Keep updates short and concrete.\n", encoding="utf-8")
    loaded = load_artifact(artifact_dir)
    loaded.backup_paths = [str(backup_path)]
    write_artifact(loaded, artifact_dir)

    exit_code = main(
        [
            "revert",
            str(artifact_dir),
            "--live-root",
            str(live_root),
            "--backup-root",
            str(backup_root),
            "--yes",
            "--validate",
        ]
    )
    output = capsys.readouterr().out
    assert exit_code == 0
    assert "reverted artifact" in output
    assert "post_revert_validation: passed" in output
    assert memory.read_text(encoding="utf-8") == "# MEMORY\n\n- Existing note\n"


def test_cli_revert_without_validate_warns_validation_not_run(tmp_path: Path, capsys) -> None:
    live_root = tmp_path / "live"
    live_root.mkdir()
    memory = live_root / "memory.md"
    memory.write_text("# MEMORY\n\n- Existing note\n", encoding="utf-8")

    proposal = _memory_proposal(tmp_path)
    artifact_dir = _write_artifact(
        tmp_path,
        live_root=live_root,
        proposals=[proposal],
        status="validated",
    )
    backup_root = tmp_path / "backups"

    apply_artifact(artifact_dir, live_root=live_root, backup_root=backup_root)

    exit_code = main(
        [
            "revert",
            str(artifact_dir),
            "--live-root",
            str(live_root),
            "--backup-root",
            str(backup_root),
            "--yes",
        ]
    )
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "post_revert_validation: not-run" in output
    assert "pass --validate" in output
    assert "not run; pass `--validate`" in (artifact_dir / REVERT_FILE).read_text(encoding="utf-8")

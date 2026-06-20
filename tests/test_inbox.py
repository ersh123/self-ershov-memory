from __future__ import annotations

from pathlib import Path

from hermes_dreaming.artifact import DreamArtifact, DreamProposal, write_artifact
from hermes_dreaming.commands.digest import build_inbox_digest, render_inbox_digest
from hermes_dreaming.commands.inbox import build_inbox, render_inbox
from hermes_dreaming.cli import main


def _write_inbox_artifact(
    root: Path,
    *,
    artifact_id: str,
    status: str,
    proposals: list[DreamProposal],
) -> Path:
    artifact = DreamArtifact(
        artifact_id=artifact_id,
        created_at="2026-05-25T12:00:00Z",
        provider="offline-marker",
        status=status,
        workspace_root=str(root),
        source_roots=[str(root / "sources")],
        report="# Report",
        sources=[],
        proposals=proposals,
    )
    artifact_dir = root / artifact_id
    write_artifact(artifact, artifact_dir)
    return artifact_dir


def _memory_proposal(*, id: str, approved: bool = False, applied: bool = False, rejected: bool = False) -> DreamProposal:
    return DreamProposal(
        id=id,
        target_kind="memory",
        target_path="memory.md",
        mode="append_text",
        summary="memory",
        provenance=["sessions/1.md:1"],
        proposed_text="- memory",
        approved=approved,
        applied=applied,
        rejected=rejected,
    )


def test_inbox_apply_ready_filter_includes_only_approved_or_applied_rows(tmp_path: Path) -> None:
    live_root = tmp_path / "live"
    live_root.mkdir()

    _write_inbox_artifact(
        live_root,
        artifact_id="artifact-apply-ready",
        status="staged",
        proposals=[_memory_proposal(id="p-approved", approved=True)],
    )
    _write_inbox_artifact(
        live_root,
        artifact_id="artifact-blocked",
        status="staged",
        proposals=[_memory_proposal(id="p-pending", approved=False)],
    )
    _write_inbox_artifact(
        live_root,
        artifact_id="artifact-already-applied",
        status="applied",
        proposals=[_memory_proposal(id="p-applied", approved=True, applied=True)],
    )
    _write_inbox_artifact(
        live_root,
        artifact_id="artifact-invalid",
        status="invalid",
        proposals=[_memory_proposal(id="p-any", approved=True)],
    )

    result = build_inbox(live_root, apply_ready=True)

    artifact_ids = [row.artifact_id for row in result.rows]
    assert "artifact-apply-ready" in artifact_ids
    assert "artifact-already-applied" in artifact_ids
    assert "artifact-blocked" not in artifact_ids
    assert "artifact-invalid" not in artifact_ids


def test_inbox_apply_ready_filter_composes_with_state_and_priority(tmp_path: Path) -> None:
    live_root = tmp_path / "live"
    live_root.mkdir()

    _write_inbox_artifact(
        live_root,
        artifact_id="artifact-high-staged-approved",
        status="staged",
        proposals=[
            DreamProposal(
                id="p",
                target_kind="memory",
                target_path="memory.md",
                mode="append_text",
                summary="memory",
                provenance=["sessions/1.md:1"],
                proposed_text="- memory",
                approved=True,
                priority="high",
            )
        ],
    )
    _write_inbox_artifact(
        live_root,
        artifact_id="artifact-normal-staged-approved",
        status="staged",
        proposals=[_memory_proposal(id="p", approved=True, applied=False)],
    )

    # _inbox_state for a fully-approved artifact is "approved", so include
    # it in the state filter alongside "staged".
    filtered = build_inbox(
        live_root,
        state_filter={"staged", "approved"},
        priority_filter={"high"},
        apply_ready=True,
    )
    artifact_ids = [row.artifact_id for row in filtered.rows]
    assert artifact_ids == ["artifact-high-staged-approved"]


def test_inbox_render_includes_apply_ready_artifact(tmp_path: Path) -> None:
    live_root = tmp_path / "live"
    live_root.mkdir()
    _write_inbox_artifact(
        live_root,
        artifact_id="artifact-apply-ready-render",
        status="staged",
        proposals=[_memory_proposal(id="p", approved=True)],
    )
    result = build_inbox(live_root, apply_ready=True)
    rendered = render_inbox(result)
    assert "artifact-apply-ready-render" in rendered


def test_inbox_digest_includes_ready_to_apply_section(tmp_path: Path) -> None:
    live_root = tmp_path / "live"
    live_root.mkdir()
    _write_inbox_artifact(
        live_root,
        artifact_id="artifact-digest-ready",
        status="staged",
        proposals=[_memory_proposal(id="p", approved=True)],
    )
    _write_inbox_artifact(
        live_root,
        artifact_id="artifact-digest-pending",
        status="staged",
        proposals=[_memory_proposal(id="p", approved=False)],
    )
    digest = build_inbox_digest(live_root)
    rendered = render_inbox_digest(digest)
    assert "## Ready to apply" in rendered
    assert "Apply-ready count" in rendered
    assert "artifact-digest-ready" in rendered
    assert "artifact-digest-pending" in rendered
    # Apply-ready count is 1 (only the staged+approved row).
    assert digest.apply_ready_count == 1
    assert len(digest.apply_ready_rows) == 1


def test_inbox_cli_apply_ready_flag_filters_output(tmp_path: Path, capsys) -> None:
    live_root = tmp_path / "live"
    live_root.mkdir()
    _write_inbox_artifact(
        live_root,
        artifact_id="artifact-cli-apply-ready",
        status="staged",
        proposals=[_memory_proposal(id="p", approved=True)],
    )
    _write_inbox_artifact(
        live_root,
        artifact_id="artifact-cli-pending",
        status="staged",
        proposals=[_memory_proposal(id="p", approved=False)],
    )
    exit_code = main(["inbox", "--artifact-root", str(live_root), "--apply-ready"])
    output = capsys.readouterr().out
    assert exit_code == 0
    assert "artifact-cli-apply-ready" in output
    assert "artifact-cli-pending" not in output

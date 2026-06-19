from __future__ import annotations

import json
from pathlib import Path

from hermes_dreaming.artifact import DreamArtifact, DreamProposal, SourceSnapshot, load_artifact, write_artifact
from hermes_dreaming.cli import main
from hermes_dreaming.commands import nightly as nightly_module
from hermes_dreaming.commands.harvest import HarvestResult
from hermes_dreaming.commands.nightly import render_nightly_memory, run_nightly_memory
from hermes_dreaming.session_reader import SessionDigest
from hermes_dreaming.state import read_run_ledger


def _live_root(root: Path) -> Path:
    live_root = root / "live"
    live_root.mkdir()
    (live_root / "memory.md").write_text("# MEMORY\n", encoding="utf-8")
    (live_root / "user.md").write_text("# USER\n", encoding="utf-8")
    return live_root


def _terminal_artifact(artifact_root: Path) -> Path:
    proposal = DreamProposal(
        id="old-proposal",
        target_kind="memory",
        target_path="memory.md",
        mode="append_text",
        summary="old applied note",
        provenance=["old.md:1"],
        proposed_text="- Old note.",
        approved=True,
        applied=True,
    )
    artifact = DreamArtifact(
        artifact_id="old-applied",
        created_at="2026-05-25T12:00:00Z",
        provider="offline-marker",
        status="applied",
        workspace_root=str(artifact_root),
        source_roots=[str(artifact_root / "sources")],
        report="# Old report\n",
        sources=[],
        proposals=[proposal],
        applied_proposal_ids=[proposal.id],
        applied_at="2026-05-25T12:05:00Z",
    )
    artifact_dir = artifact_root / artifact.artifact_id
    write_artifact(artifact, artifact_dir)
    return artifact_dir


def _fake_harvest(*, recent: int, output_path: Path | None = None, **_kwargs) -> HarvestResult:  # type: ignore[no-untyped-def]
    assert recent > 0
    path = Path(output_path)
    content = "\n".join(
        [
            "# Recent sessions",
            "",
            "MEMORY: memory: Keep nightly updates staged and reviewed.",
            "MEMORY: user: Prefer a morning digest with exact next commands.",
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return HarvestResult(
        output_path=path,
        sessions=[
            SessionDigest(
                session_id="session-1",
                title="Night work",
                started_at=1_772_000_000.0,
                message_count=2,
                source="test",
                user_turns=["Build nightly memory"],
                context_lines=["user: Build nightly memory", "assistant: Staged review is safer"],
            )
        ],
        content=content,
        redaction_count=1,
    )


def _empty_harvest(*, recent: int, output_path: Path | None = None, **_kwargs) -> HarvestResult:  # type: ignore[no-untyped-def]
    assert recent > 0
    path = Path(output_path)
    content = "# Recent sessions\n\nNo recent sessions found.\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return HarvestResult(
        output_path=path,
        sessions=[],
        content=content,
        redaction_count=0,
    )


def test_run_nightly_memory_stages_reports_compacts_and_records_ledger(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(nightly_module, "harvest_recent", _fake_harvest)
    live_root = _live_root(tmp_path)
    artifact_root = tmp_path / "artifacts"
    archive_root = tmp_path / "archive"
    state_root = tmp_path / "state"
    old_dir = _terminal_artifact(artifact_root)

    result = run_nightly_memory(
        live_root=live_root,
        artifact_root=artifact_root,
        archive_root=archive_root,
        state_root=state_root,
        recent=3,
        provider_name="offline-marker",
        model=None,
        base_url=None,
    )

    assert result.success is True
    assert result.artifact_status == "staged"
    assert result.proposal_count == 2
    assert result.source_bundle.exists()
    assert result.digest_path.exists()
    assert result.inbox_digest_path.exists()
    assert "Hermes Ershov digest" in result.digest_path.read_text(encoding="utf-8")
    inbox_digest = result.inbox_digest_path.read_text(encoding="utf-8")
    assert "Hermes Ershov inbox digest" in inbox_digest
    assert "old-applied" not in inbox_digest
    assert not old_dir.exists()
    assert (archive_root / "old-applied").exists()
    assert (live_root / "memory.md").read_text(encoding="utf-8") == "# MEMORY\n"
    assert (live_root / "user.md").read_text(encoding="utf-8") == "# USER\n"

    assert result.artifact_dir is not None
    artifact = load_artifact(result.artifact_dir)
    assert artifact.status == "staged"
    assert [proposal.target_kind for proposal in artifact.proposals] == ["memory", "user"]

    ledger = read_run_ledger(ledger_path=state_root / "runs.jsonl")
    assert len(ledger) == 1
    assert ledger[0]["command"] == "nightly"
    assert ledger[0]["success"] is True
    assert ledger[0]["artifact_id"] == result.artifact_id
    assert ledger[0]["sessions"] == 1
    assert ledger[0]["redactions"] == 1
    assert json.loads((state_root / "state.json").read_text(encoding="utf-8"))["last_run"]["command"] == "nightly"


def test_run_nightly_memory_noops_without_offline_markers_and_does_not_create_artifact(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(nightly_module, "harvest_recent", _empty_harvest)
    live_root = _live_root(tmp_path)
    artifact_root = tmp_path / "artifacts"
    state_root = tmp_path / "state"

    result = run_nightly_memory(
        live_root=live_root,
        artifact_root=artifact_root,
        state_root=state_root,
        provider_name="offline-marker",
        model=None,
        base_url=None,
        compact=False,
    )

    assert result.success is True
    assert result.artifact_status == "no-op"
    assert result.artifact_id is None
    assert result.artifact_dir is None
    assert result.proposal_count == 0
    assert result.validation_errors == []
    assert result.digest_path == artifact_root / "_digests" / "latest-nightly.md"
    assert result.digest_path.exists()
    assert result.inbox_digest_path.exists()
    assert result.source_bundle.exists()
    assert list(artifact_root.glob("*/manifest.json")) == []

    output = render_nightly_memory(result)
    assert "Status: `no-op`" in output
    assert "Artifact: `none`" in output
    assert "No eligible MEMORY/DREAM markers" in output
    assert "ershov summarize" not in output

    ledger = read_run_ledger(ledger_path=state_root / "runs.jsonl")
    assert ledger[0]["success"] is True
    assert ledger[0]["artifact_status"] == "no-op"
    assert ledger[0]["artifact_dir"] is None
    assert ledger[0]["proposals"] == 0
    assert ledger[0]["run_source"] == "manual"


def test_run_nightly_memory_records_sanitized_run_source(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(nightly_module, "harvest_recent", _empty_harvest)
    monkeypatch.setenv("HERMES_ERSHOV_RUN_SOURCE", "Systemd Timer\nInjected=bad")
    live_root = _live_root(tmp_path)
    artifact_root = tmp_path / "artifacts"
    state_root = tmp_path / "state"

    result = run_nightly_memory(
        live_root=live_root,
        artifact_root=artifact_root,
        state_root=state_root,
        provider_name="offline-marker",
        model=None,
        base_url=None,
        compact=False,
    )

    assert result.success is True
    assert result.run_source == "systemd-timer-injected-bad"
    assert read_run_ledger(ledger_path=state_root / "runs.jsonl")[0]["run_source"] == "systemd-timer-injected-bad"


def test_run_nightly_memory_records_invalid_artifact_without_live_write(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(nightly_module, "harvest_recent", _fake_harvest)
    missing_live_root = tmp_path / "missing-live"
    artifact_root = tmp_path / "artifacts"
    state_root = tmp_path / "state"

    result = run_nightly_memory(
        live_root=missing_live_root,
        artifact_root=artifact_root,
        state_root=state_root,
        provider_name="offline-marker",
        model=None,
        base_url=None,
        compact=False,
    )

    assert result.success is False
    assert result.artifact_status == "invalid"
    assert any("live root does not exist" in error for error in result.validation_errors)
    assert result.digest_path.exists()
    assert result.compact_result is None
    assert "Validation errors" in render_nightly_memory(result)
    assert read_run_ledger(ledger_path=state_root / "runs.jsonl")[0]["success"] is False
    assert not missing_live_root.exists()


def test_nightly_cli_runs_full_pipeline(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setattr(nightly_module, "harvest_recent", _fake_harvest)
    live_root = _live_root(tmp_path)
    artifact_root = tmp_path / "artifacts"
    state_root = tmp_path / "state"

    assert (
        main(
            [
                "nightly",
                "--live-root",
                str(live_root),
                "--artifact-root",
                str(artifact_root),
                "--state-root",
                str(state_root),
                "--recent",
                "2",
                "--no-llm",
                "--no-compact",
                "--no-weekly",
            ]
        )
        == 0
    )

    output = capsys.readouterr().out
    assert "# Hermes Ershov nightly memory" in output
    assert "Live memory writes: disabled" in output
    assert "Sessions harvested: `1`" in output
    assert read_run_ledger(ledger_path=state_root / "runs.jsonl")[0]["command"] == "nightly"

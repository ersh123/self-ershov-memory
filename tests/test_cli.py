from __future__ import annotations

import json
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

import pytest

from hermes_dreaming.artifact import DreamArtifact, DreamProposal, SourceSnapshot, load_artifact, write_artifact
from hermes_dreaming.cli import main


@dataclass(slots=True)
class _FakeHarvestResult:
    output_path: Path
    sessions: list
    content: str
    redaction_count: int


def _write_source_tree(root: Path) -> Path:
    sources = root / "sources"
    sources.mkdir(parents=True, exist_ok=True)
    (sources / "session-1.md").write_text(
        "# Session 1\n\nMEMORY: memory: Keep updates short and concrete.\nMEMORY: fact: {\"type\": \"preference\", \"key\": \"tone\", \"value\": \"casual\"}\nMEMORY: skill: path=skills/review.md | Preserve review gates and backups.\n",
        encoding="utf-8",
    )
    return sources


def _write_report_card_artifact(root: Path, *, status: str = "staged") -> Path:
    artifact = DreamArtifact(
        artifact_id="artifact-report-card",
        created_at="2026-05-25T12:00:00Z",
        provider="offline-marker",
        status=status,
        workspace_root=str(root),
        source_roots=[str(root / "sources")],
        report="# report\nprivate report body: TOP-SECRET-REPORT\n",
        sources=[
            SourceSnapshot(
                path="sources/session-1.md",
                kind="session",
                content="MEMORY: memory: TOP-SECRET-SOURCE\n",
                sha256=sha256(b"MEMORY: memory: TOP-SECRET-SOURCE\n").hexdigest(),
                line_count=1,
            )
        ],
        proposals=[
            DreamProposal(
                id="proposal-memory",
                target_kind="memory",
                target_path="memory.md",
                mode="append_text",
                summary="TOP-SECRET-PROPOSAL-SUMMARY",
                provenance=["sources/session-1.md:1"],
                proposed_text="- TOP-SECRET-PROPOSAL-TEXT",
                approved=True,
            )
        ],
        validation_errors=["source bundle needs review"],
        applied_proposal_ids=["proposal-memory"] if status == "applied" else [],
        backup_paths=[str(root / "backups" / "memory.md")] if status == "applied" else [],
        applied_at="2026-05-25T13:00:00Z" if status == "applied" else None,
        discarded_at="2026-05-25T14:00:00Z" if status == "discarded" else None,
    )
    artifact_dir = root / artifact.artifact_id
    write_artifact(artifact, artifact_dir)
    return artifact_dir



def test_create_validate_apply_and_status_command_flow(tmp_path: Path, capsys) -> None:
    live_root = tmp_path / "live"
    live_root.mkdir()
    (live_root / "memory.md").write_text("# MEMORY\n", encoding="utf-8")
    (live_root / "user.md").write_text("# USER\n", encoding="utf-8")
    (live_root / "skills").mkdir()
    (live_root / "skills" / "review.md").write_text("# Review\n", encoding="utf-8")
    sources = _write_source_tree(tmp_path)
    artifact_root = tmp_path / "artifacts"
    backup_root = tmp_path / "backups"

    assert (
        main(
            [
                "create",
                "--live-root",
                str(live_root),
                "--artifact-root",
                str(artifact_root),
                "--source",
                str(sources),
            ]
        )
        == 0
    )
    create_output = capsys.readouterr().out.strip().splitlines()
    artifact_dir = Path(create_output[0].split(":", 1)[1].strip())
    assert artifact_dir.exists()

    assert main(["diff", str(artifact_dir)]) == 0
    diff_output = capsys.readouterr().out
    assert "memory" in diff_output.lower()
    assert "fact" in diff_output.lower()
    assert "confidence" in diff_output.lower()
    assert "snippet" in diff_output.lower()

    assert main(["validate", str(artifact_dir), "--live-root", str(live_root)]) == 0
    validate_output = capsys.readouterr().out
    assert "valid" in validate_output.lower()

    assert (
        main(
            [
                "apply",
                str(artifact_dir),
                "--live-root",
                str(live_root),
                "--backup-root",
                str(backup_root),
                "--approve",
                "all",
            ]
        )
        == 0
    )
    apply_output = capsys.readouterr().out
    assert "applied" in apply_output.lower()

    memory = (live_root / "memory.md").read_text(encoding="utf-8")
    assert "Keep updates short and concrete." in memory
    facts = (live_root / "facts.jsonl").read_text(encoding="utf-8").splitlines()
    assert any(json.loads(line)["key"] == "tone" for line in facts)
    skill = (live_root / "skills" / "review.md").read_text(encoding="utf-8")
    assert "Preserve review gates and backups." in skill
    assert (backup_root / "memory.md").exists()
    assert load_artifact(artifact_dir).status == "applied"

    assert main(["status", "--artifact-root", str(artifact_root)]) == 0
    status_output = capsys.readouterr().out
    assert "applied" in status_output.lower()


def test_report_card_command_redacts_private_content_and_writes_json_companion(
    tmp_path: Path, capsys
) -> None:
    artifact_dir = _write_report_card_artifact(tmp_path, status="staged")
    json_path = tmp_path / "report-card.json"

    assert main(["report-card", str(artifact_dir), "--json", str(json_path)]) == 0
    output = capsys.readouterr().out
    json_text = json_path.read_text(encoding="utf-8")
    payload = json.loads(json_text)

    assert "artifact-report-card" in output
    assert "TOP-SECRET" not in output
    assert "TOP-SECRET" not in json_text
    assert "memory updates" in output
    assert "validation state" in output.lower()
    assert payload["artifact_id"] == "artifact-report-card"
    assert payload["status"] == "staged"
    assert payload["validation_state"] == "invalid"
    assert payload["apply_state"] == "not applied"
    assert payload["discard_state"] == "not discarded"
    assert payload["target_kind_breakdown"] == {"memory": 1}
    assert payload["theme_labels"] == ["memory updates"]


def test_discard_command_archives_artifact(tmp_path: Path, capsys) -> None:
    live_root = tmp_path / "live"
    live_root.mkdir()
    (live_root / "memory.md").write_text("# MEMORY\n", encoding="utf-8")
    sources = _write_source_tree(tmp_path)
    artifact_root = tmp_path / "artifacts"
    archive_root = tmp_path / "archive"

    assert (
        main(
            [
                "create",
                "--live-root",
                str(live_root),
                "--artifact-root",
                str(artifact_root),
                "--source",
                str(sources),
            ]
        )
        == 0
    )
    artifact_dir = Path(capsys.readouterr().out.strip().splitlines()[0].split(":", 1)[1].strip())

    assert main(["discard", str(artifact_dir), "--archive-root", str(archive_root)]) == 0
    discard_output = capsys.readouterr().out
    assert "discarded" in discard_output.lower()

    assert not artifact_dir.exists()
    archived_dir = archive_root / artifact_dir.name
    assert archived_dir.exists()
    assert (live_root / "memory.md").read_text(encoding="utf-8") == "# MEMORY\n"


def test_providers_list_prints_table_with_builtin_providers(tmp_path: Path, capsys) -> None:
    exit_code = main(["providers", "list"])
    output = capsys.readouterr().out
    assert exit_code == 0
    assert "NAME" in output
    assert "offline-marker" in output
    assert "openai-compatible" in output
    assert "ollama" in output


def test_providers_doctor_prints_safe_readiness_table(capsys) -> None:
    exit_code = main(["providers", "doctor", "--provider", "offline-marker"])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "READINESS" in output
    assert "offline-marker" in output
    assert "api key: not required" in output
    assert "configuration readiness only" in output
    assert "network probe skipped" in output
    assert "not an end-to-end generation test" in output


def test_providers_doctor_json_output(capsys) -> None:
    exit_code = main(["providers", "doctor", "--provider", "offline-marker", "--json"])
    output = capsys.readouterr().out
    payload = json.loads(output)

    assert exit_code == 0
    assert payload[0]["name"] == "offline-marker"
    assert payload[0]["readiness"] == "ready"


def test_providers_doctor_strict_returns_nonzero_for_unready_provider(capsys) -> None:
    exit_code = main(["providers", "doctor", "--provider", "deepseek", "--strict"])
    output = capsys.readouterr().out

    assert exit_code == 1
    assert "deepseek" in output
    assert "blocked" in output or "missing" in output


def test_providers_doctor_can_check_systemd_env_file_without_printing_secret(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setattr("hermes_dreaming.providers._openai_compat_available", lambda: True)
    env_file = tmp_path / "nightly.secrets.env"
    env_file.write_text('DEEPSEEK_API_KEY="sk-do-not-print"\n', encoding="utf-8")

    exit_code = main(["providers", "doctor", "--provider", "deepseek", "--env-file", str(env_file), "--strict"])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "deepseek" in output
    assert "DEEPSEEK_API_KEY: present" in output
    assert "sk-do-not-print" not in output


def test_providers_doctor_from_systemd_uses_default_env_files_without_printing_secret(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setattr("hermes_dreaming.providers._openai_compat_available", lambda: True)
    env_file = tmp_path / "nightly.secrets.env"
    env_file.write_text('DEEPSEEK_API_KEY="sk-systemd-do-not-print"\n', encoding="utf-8")
    monkeypatch.setattr("hermes_dreaming.cli.default_env_files", lambda: [tmp_path / "missing.env", env_file])

    exit_code = main(["providers", "doctor", "--provider", "deepseek", "--from-systemd", "--strict"])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "deepseek" in output
    assert "DEEPSEEK_API_KEY: present" in output
    assert "sk-systemd-do-not-print" not in output


def test_providers_doctor_from_systemd_blocks_configured_provider_mismatch_without_printing_secret(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setattr("hermes_dreaming.providers._openai_compat_available", lambda: True)
    env_file = tmp_path / "nightly.env"
    env_file.write_text(
        "\n".join(
            [
                'HERMES_ERSHOV_PROVIDER="offline-marker"',
                'DEEPSEEK_API_KEY="sk-systemd-do-not-print"',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("hermes_dreaming.cli.default_env_files", lambda: [env_file])

    exit_code = main(["providers", "doctor", "--provider", "deepseek", "--from-systemd", "--strict"])
    output = capsys.readouterr().out

    assert exit_code == 1
    assert "configured provider: offline-marker" in output
    assert "expected provider: deepseek" in output
    assert "DEEPSEEK_API_KEY: present" in output
    assert "sk-systemd-do-not-print" not in output


def test_providers_doctor_fix_plan_is_secret_safe(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setattr("hermes_dreaming.providers._openai_compat_available", lambda: True)
    env_file = tmp_path / "nightly.env"
    env_file.write_text('HERMES_ERSHOV_PROVIDER="offline-marker"\n', encoding="utf-8")
    secret_file = tmp_path / "nightly.secrets.env"
    secret_file.write_text('DEEPSEEK_API_KEY="sk-systemd-do-not-print"\n', encoding="utf-8")
    monkeypatch.setattr("hermes_dreaming.cli.default_env_files", lambda: [env_file, secret_file])

    exit_code = main(
        [
            "providers",
            "doctor",
            "--provider",
            "deepseek",
            "--from-systemd",
            "--fix-plan",
            "--strict",
        ]
    )
    output = capsys.readouterr().out

    assert exit_code == 1
    assert "Hermes Ershov provider fix plan" in output
    assert "HERMES_ERSHOV_PROVIDER=deepseek" in output
    assert "DEEPSEEK_API_KEY=<secret>" in output
    assert "sk-systemd-do-not-print" not in output
    assert "install-systemd --provider deepseek" in output
    assert "providers doctor --provider deepseek --from-systemd --strict" in output


def test_providers_doctor_fix_plan_rejects_json(capsys) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["providers", "doctor", "--json", "--fix-plan"])
    captured = capsys.readouterr()

    assert exc_info.value.code == 2
    assert "--fix-plan cannot be combined with --json" in captured.err


def test_create_with_no_llm_shorthand_uses_offline_marker(tmp_path: Path, monkeypatch, capsys) -> None:
    """`--no-llm` should set the provider to offline-marker regardless of --provider."""
    from hermes_dreaming.analyze import DreamRunConfig

    captured: dict[str, object] = {}

    def fake_create(config: DreamRunConfig):  # type: ignore[no-untyped-def]
        captured["provider_name"] = config.provider_name
        # Return a minimal result-like object so the CLI can render.
        from hermes_dreaming.artifact import DreamArtifact
        from dataclasses import dataclass
        from pathlib import Path

        @dataclass(slots=True)
        class _Result:
            artifact: DreamArtifact
            artifact_dir: Path
            validation_errors: list[str]

        artifact = DreamArtifact(
            artifact_id="artifact-nollm",
            created_at="2026-05-25T12:00:00Z",
            provider=config.provider_name,
            status="staged",
            workspace_root=str(config.live_root),
            source_roots=[str(p) for p in config.source_paths],
            report="# Report",
            sources=[],
            proposals=[],
        )
        artifact_dir = Path(tmp_path) / "artifact-nollm"
        artifact_dir.mkdir(parents=True, exist_ok=True)
        from hermes_dreaming.artifact import write_artifact
        write_artifact(artifact, artifact_dir)
        return _Result(artifact=artifact, artifact_dir=artifact_dir, validation_errors=[])

    monkeypatch.setattr("hermes_dreaming.cli.create_dream_artifact", fake_create)

    live_root = tmp_path / "live"
    live_root.mkdir()
    sources = _write_source_tree(tmp_path)
    artifact_root = tmp_path / "artifacts"

    # Pass --provider openai-compatible but also --no-llm. The latter must win.
    assert (
        main(
            [
                "create",
                "--live-root",
                str(live_root),
                "--artifact-root",
                str(artifact_root),
                "--source",
                str(sources),
                "--provider",
                "openai-compatible",
                "--no-llm",
            ]
        )
        == 0
    )
    assert captured["provider_name"] == "offline-marker"


def test_create_with_from_sessions_prints_redaction_count_and_sessions_count(tmp_path: Path, monkeypatch, capsys) -> None:
    """`--from-sessions N` should print the harvest stats and feed the bundle as a source."""
    from dataclasses import dataclass
    from pathlib import Path

    from hermes_dreaming.analyze import DreamRunConfig
    from hermes_dreaming.artifact import DreamArtifact, write_artifact

    @dataclass(slots=True)
    class _Result:
        artifact: DreamArtifact
        artifact_dir: Path
        validation_errors: list[str]

    captured: dict[str, object] = {}

    def fake_create(config: DreamRunConfig):  # type: ignore[no-untyped-def]
        captured["provider_name"] = config.provider_name
        captured["source_paths"] = [str(p) for p in config.source_paths]
        artifact = DreamArtifact(
            artifact_id="artifact-from-sessions",
            created_at="2026-05-25T12:00:00Z",
            provider=config.provider_name,
            status="staged",
            workspace_root=str(config.live_root),
            source_roots=[str(p) for p in config.source_paths],
            report="# Report",
            sources=[],
            proposals=[],
        )
        artifact_dir = Path(tmp_path) / "artifact-from-sessions"
        artifact_dir.mkdir(parents=True, exist_ok=True)
        write_artifact(artifact, artifact_dir)
        return _Result(artifact=artifact, artifact_dir=artifact_dir, validation_errors=[])

    monkeypatch.setattr("hermes_dreaming.cli.create_dream_artifact", fake_create)
    monkeypatch.setattr(
        "hermes_dreaming.cli.harvest_recent",
        lambda *, recent, output_path, **_kwargs: _FakeHarvestResult(
            output_path=Path(output_path),
            sessions=[],
            content="",
            redaction_count=3,
        ),
    )

    live_root = tmp_path / "live"
    live_root.mkdir()
    artifact_root = tmp_path / "artifacts"

    exit_code = main(
        [
            "create",
            "--live-root",
            str(live_root),
            "--artifact-root",
            str(artifact_root),
            "--from-sessions",
            "5",
        ]
    )
    output = capsys.readouterr().out
    assert exit_code == 0
    # Re-redaction and session stats printed.
    assert "redactions: 3" in output
    assert "sessions: 0" in output
    # The harvested bundle was fed as a source.
    assert len(captured["source_paths"]) == 1  # type: ignore[arg-type]


def test_create_with_recent_alias_keeps_back_compat(tmp_path: Path, monkeypatch, capsys) -> None:
    """`--recent N` is preserved as an alias for --from-sessions N."""
    from dataclasses import dataclass
    from pathlib import Path

    from hermes_dreaming.analyze import DreamRunConfig
    from hermes_dreaming.artifact import DreamArtifact, write_artifact

    @dataclass(slots=True)
    class _Result:
        artifact: DreamArtifact
        artifact_dir: Path
        validation_errors: list[str]

    def fake_create(config: DreamRunConfig):  # type: ignore[no-untyped-def]
        artifact = DreamArtifact(
            artifact_id="artifact-recent-alias",
            created_at="2026-05-25T12:00:00Z",
            provider=config.provider_name,
            status="staged",
            workspace_root=str(config.live_root),
            source_roots=[str(p) for p in config.source_paths],
            report="# Report",
            sources=[],
            proposals=[],
        )
        artifact_dir = Path(tmp_path) / "artifact-recent-alias"
        artifact_dir.mkdir(parents=True, exist_ok=True)
        write_artifact(artifact, artifact_dir)
        return _Result(artifact=artifact, artifact_dir=artifact_dir, validation_errors=[])

    monkeypatch.setattr("hermes_dreaming.cli.create_dream_artifact", fake_create)
    monkeypatch.setattr(
        "hermes_dreaming.cli.harvest_recent",
        lambda *, recent, output_path, **_kwargs: _FakeHarvestResult(
            output_path=Path(output_path),
            sessions=[],
            content="",
            redaction_count=0,
        ),
    )

    live_root = tmp_path / "live"
    live_root.mkdir()
    artifact_root = tmp_path / "artifacts"

    assert (
        main(
            [
                "create",
                "--live-root",
                str(live_root),
                "--artifact-root",
                str(artifact_root),
                "--recent",
                "3",
            ]
        )
        == 0
    )


def test_install_cron_cli_forwards_nightly_review_options(tmp_path: Path, monkeypatch, capsys) -> None:
    captured: dict[str, object] = {}

    def fake_install_cron(**kwargs):  # type: ignore[no-untyped-def]
        captured.update(kwargs)
        return "## hermes ershov install-cron\n\n**Cron job registered.**"

    monkeypatch.setattr("hermes_dreaming.cli.install_cron_command", fake_install_cron)
    live_root = tmp_path / "live"
    artifact_root = tmp_path / "artifacts"
    archive_root = tmp_path / "archive"
    state_root = tmp_path / "state"

    exit_code = main(
        [
            "install-cron",
            "--mode",
            "nightly-memory",
            "--recent",
            "9",
            "--live-root",
            str(live_root),
            "--artifact-root",
            str(artifact_root),
            "--archive-root",
            str(archive_root),
            "--state-root",
            str(state_root),
            "--provider",
            "deepseek",
            "--model",
            "deepseek-v4-flash",
            "--base-url",
            "https://api.deepseek.com/v1",
        ]
    )

    assert exit_code == 0
    assert captured["mode"] == "nightly-memory"
    assert captured["recent"] == 9
    assert captured["live_root"] == live_root
    assert captured["artifact_root"] == artifact_root
    assert captured["archive_root"] == archive_root
    assert captured["state_root"] == state_root
    assert captured["provider"] == "deepseek"
    assert captured["model"] == "deepseek-v4-flash"
    assert captured["base_url"] == "https://api.deepseek.com/v1"

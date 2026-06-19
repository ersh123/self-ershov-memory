from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from hermes_dreaming.commands.install_systemd import SERVICE_NAME
from hermes_dreaming.commands.soak import build_soak_report
from hermes_dreaming.commands.status import build_status_snapshot, render_status
from hermes_dreaming import cli as cli_module
from hermes_dreaming.cli import main


NOW = datetime(2026, 6, 19, 12, 0, tzinfo=timezone.utc)


def _write_ledger(state_root: Path, records: list[dict[str, object]]) -> None:
    state_root.mkdir(parents=True, exist_ok=True)
    (state_root / "runs.jsonl").write_text(
        "".join(json.dumps(record, sort_keys=True) + "\n" for record in records),
        encoding="utf-8",
    )


def _timer_runner(command):  # type: ignore[no-untyped-def]
    if command[2] == "is-enabled":
        return subprocess.CompletedProcess(list(command), 0, "enabled\n", "")
    if command[2] == "is-active":
        return subprocess.CompletedProcess(list(command), 0, "active\n", "")
    if command[2] == "show":
        return subprocess.CompletedProcess(
            list(command),
            0,
            f"LoadState=loaded\nUnit={SERVICE_NAME}\nNextElapseUSecRealtime=Sat 2026-06-20 03:00:49 +07\n",
            "",
        )
    raise AssertionError(f"unexpected command: {command}")


def test_status_can_show_blocked_stable_release_gate(tmp_path: Path) -> None:
    artifact_root = tmp_path / "artifacts"
    artifact_root.mkdir()
    state_root = tmp_path / "state"
    _write_ledger(
        state_root,
        [
            {
                "command": "nightly",
                "success": True,
                "timestamp": "2026-06-19T10:00:00Z",
                "artifact_status": "no-op",
                "run_source": "manual",
                "git_commit": "old1111",
                "git_dirty": False,
            }
        ],
    )

    snapshot = build_status_snapshot(
        artifact_root=artifact_root,
        state_path=state_root / "state.json",
        ledger_path=state_root / "runs.jsonl",
        diary_path=state_root / "ERSHOV.md",
    )
    gate = build_soak_report(
        state_root=state_root,
        now=NOW,
        require_timer=True,
        required_source="systemd",
        required_commit="abc1234",
        require_clean=True,
        runner=_timer_runner,
    )

    output = render_status(snapshot, release_gate=gate, current_commit="abc1234", current_dirty=False)

    assert "Stable release gate:" in output
    assert "Status: `blocked`" in output
    assert "Required run source: `systemd`" in output
    assert "Required git commit: `abc1234`" in output
    assert "Gate-matching successful runs: `0`" in output
    assert f"unit={SERVICE_NAME}" in output
    assert "next=Sat 2026-06-20 03:00:49 +07" in output
    assert "found 0 successful nightly run(s) matching source 'systemd'" in output


def test_status_release_gate_blocks_dirty_current_checkout(tmp_path: Path) -> None:
    artifact_root = tmp_path / "artifacts"
    artifact_root.mkdir()
    state_root = tmp_path / "state"
    _write_ledger(
        state_root,
        [
            {
                "command": "nightly",
                "success": True,
                "timestamp": "2026-06-19T10:00:00Z",
                "artifact_status": "no-op",
                "run_source": "systemd",
                "git_commit": "abc1234",
                "git_dirty": False,
            }
        ],
    )

    snapshot = build_status_snapshot(
        artifact_root=artifact_root,
        state_path=state_root / "state.json",
        ledger_path=state_root / "runs.jsonl",
        diary_path=state_root / "ERSHOV.md",
    )
    gate = build_soak_report(
        state_root=state_root,
        now=NOW,
        require_timer=True,
        required_source="systemd",
        required_commit="abc1234",
        require_clean=True,
        runner=_timer_runner,
    )

    assert gate.passed is True
    output = render_status(snapshot, release_gate=gate, current_commit="abc1234", current_dirty=True)

    assert "Status: `blocked`" in output
    assert "current git checkout is dirty" in output
    assert f"Timer: `enabled=True, active=True, load=loaded, unit={SERVICE_NAME}" in output


def test_status_cli_release_gate_uses_strict_systemd_defaults(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    artifact_root = tmp_path / "artifacts"
    artifact_root.mkdir()
    state_root = tmp_path / "state"
    _write_ledger(state_root, [])
    captured: dict[str, object] = {}

    def fake_build_soak_report(**kwargs):  # type: ignore[no-untyped-def]
        captured.update(kwargs)
        return build_soak_report(
            state_root=state_root,
            since_hours=kwargs["since_hours"],
            min_successful=kwargs["min_successful"],
            now=NOW,
            require_timer=True,
            required_source="systemd",
            required_commit="abc1234",
            require_clean=True,
            runner=_timer_runner,
        )

    monkeypatch.setattr(cli_module, "_current_git_commit", lambda: "abc1234")
    monkeypatch.setattr(cli_module, "_current_git_dirty", lambda: False)
    monkeypatch.setattr(cli_module, "build_soak_report", fake_build_soak_report)

    exit_code = main(
        [
            "status",
            "--artifact-root",
            str(artifact_root),
            "--release-gate",
            "--state-root",
            str(state_root),
        ]
    )
    output = capsys.readouterr().out

    assert exit_code == 0
    assert captured["state_root"] == state_root
    assert captured["since_hours"] == 96
    assert captured["min_successful"] == 3
    assert captured["require_timer"] is True
    assert captured["required_source"] == "systemd"
    assert captured["required_commit"] == "abc1234"
    assert captured["require_clean"] is True
    assert "Stable release gate:" in output
    assert "Status: `blocked`" in output
    assert "Window: `96h`" in output
    assert "Required successful scheduled runs: `3`" in output
    assert "next=Sat 2026-06-20 03:00:49 +07" in output


def test_status_cli_state_root_drives_default_artifact_root_and_ledger(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    state_root = tmp_path / "state"
    artifact_root = state_root / "artifacts"
    artifact_root.mkdir(parents=True)
    _write_ledger(
        state_root,
        [
            {
                "command": "nightly",
                "success": True,
                "timestamp": "2026-06-19T10:00:00Z",
                "artifact_status": "no-op",
                "run_source": "systemd",
                "git_commit": "abc1234",
                "git_dirty": False,
                "summary": "nightly no-op",
            }
        ],
    )

    def fake_build_soak_report(**kwargs):  # type: ignore[no-untyped-def]
        return build_soak_report(
            state_root=kwargs["state_root"],
            since_hours=kwargs["since_hours"],
            min_successful=kwargs["min_successful"],
            now=NOW,
            require_timer=True,
            required_source="systemd",
            required_commit="abc1234",
            require_clean=True,
            runner=_timer_runner,
        )

    monkeypatch.setattr(cli_module, "_current_git_commit", lambda: "abc1234")
    monkeypatch.setattr(cli_module, "_current_git_dirty", lambda: False)
    monkeypatch.setattr(cli_module, "build_soak_report", fake_build_soak_report)

    exit_code = main(["status", "--release-gate", "--state-root", str(state_root)])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert f"Artifact root: {artifact_root}" in output
    assert "Run ledger: 1 run(s), 1 successful" in output
    assert "Last run: 2026-06-19T10:00:00Z" in output
    assert "Stable release gate:" in output

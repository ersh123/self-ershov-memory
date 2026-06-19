from __future__ import annotations

import json
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

from hermes_dreaming.cli import main
from hermes_dreaming.commands.soak import build_soak_report, render_soak_report, render_soak_report_json


NOW = datetime(2026, 6, 19, 12, 0, tzinfo=timezone.utc)


def _iso(delta_hours: int = 0) -> str:
    return (NOW + timedelta(hours=delta_hours)).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _write_ledger(state_root: Path, records: list[dict[str, object]]) -> None:
    state_root.mkdir(parents=True, exist_ok=True)
    (state_root / "runs.jsonl").write_text(
        "".join(json.dumps(record, sort_keys=True) + "\n" for record in records),
        encoding="utf-8",
    )


def _nightly(*, success: bool, hours_ago: int, status: str = "staged") -> dict[str, object]:
    return {
        "command": "nightly",
        "success": success,
        "timestamp": _iso(-hours_ago),
        "artifact_id": "artifact-1" if success else None,
        "artifact_status": status,
        "summary": "nightly staged proposals" if success else "nightly failed",
    }


def test_soak_report_passes_with_recent_successful_nightly(tmp_path: Path) -> None:
    state_root = tmp_path / "state"
    _write_ledger(state_root, [_nightly(success=True, hours_ago=2)])

    report = build_soak_report(state_root=state_root, now=NOW)

    assert report.passed is True
    assert report.recent_successful_nightly_runs[0]["artifact_status"] == "staged"
    output = render_soak_report(report)
    assert "Status: `pass`" in output
    assert "PASS: nightly soak evidence" in output


def test_soak_report_fails_without_recent_success(tmp_path: Path) -> None:
    state_root = tmp_path / "state"
    _write_ledger(state_root, [_nightly(success=True, hours_ago=40)])

    report = build_soak_report(state_root=state_root, since_hours=30, now=NOW)

    assert report.passed is False
    assert "required 1" in report.reasons[0]
    assert "Status: `fail`" in render_soak_report(report)


def test_soak_report_fails_on_recent_failed_nightly_unless_allowed(tmp_path: Path) -> None:
    state_root = tmp_path / "state"
    _write_ledger(
        state_root,
        [
            _nightly(success=True, hours_ago=2),
            _nightly(success=False, hours_ago=1, status="invalid"),
        ],
    )

    strict = build_soak_report(state_root=state_root, now=NOW)
    lenient = build_soak_report(state_root=state_root, now=NOW, allow_failures=True)

    assert strict.passed is False
    assert "failed nightly" in strict.reasons[0]
    assert lenient.passed is True


def test_soak_report_can_require_healthy_systemd_timer(tmp_path: Path) -> None:
    state_root = tmp_path / "state"
    _write_ledger(state_root, [_nightly(success=True, hours_ago=2, status="no-op")])
    calls: list[list[str]] = []

    def runner(command):  # type: ignore[no-untyped-def]
        calls.append(list(command))
        if command[2] == "is-enabled":
            return subprocess.CompletedProcess(list(command), 0, "enabled\n", "")
        if command[2] == "is-active":
            return subprocess.CompletedProcess(list(command), 0, "active\n", "")
        raise AssertionError(f"unexpected command: {command}")

    report = build_soak_report(state_root=state_root, now=NOW, require_timer=True, runner=runner)

    assert report.passed is True
    assert report.timer.enabled is True
    assert report.timer.active is True
    assert calls == [
        ["systemctl", "--user", "is-enabled", "hermes-ershov-nightly.timer"],
        ["systemctl", "--user", "is-active", "hermes-ershov-nightly.timer"],
    ]


def test_soak_report_json_is_machine_readable(tmp_path: Path) -> None:
    state_root = tmp_path / "state"
    _write_ledger(state_root, [_nightly(success=True, hours_ago=2)])

    payload = json.loads(render_soak_report_json(build_soak_report(state_root=state_root, now=NOW)))

    assert payload["passed"] is True
    assert payload["state_root"] == str(state_root)
    assert payload["recent_successful_nightly_runs"][0]["command"] == "nightly"


def test_soak_cli_returns_nonzero_when_gate_fails(tmp_path: Path, capsys) -> None:
    state_root = tmp_path / "state"
    _write_ledger(state_root, [])

    assert main(["soak", "--state-root", str(state_root), "--since-hours", "30"]) == 1

    output = capsys.readouterr().out
    assert "# Hermes Ershov soak report" in output
    assert "Status: `fail`" in output


def test_soak_cli_returns_zero_when_gate_passes(tmp_path: Path, capsys) -> None:
    state_root = tmp_path / "state"
    _write_ledger(state_root, [_nightly(success=True, hours_ago=2)])

    assert main(["soak", "--state-root", str(state_root), "--since-hours", "72", "--json"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["passed"] is True

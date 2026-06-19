from __future__ import annotations

import json
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

from hermes_dreaming import cli as cli_module
from hermes_dreaming.cli import main
from hermes_dreaming.commands.install_systemd import SERVICE_NAME, TIMER_NAME
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


def _nightly(
    *,
    success: bool,
    hours_ago: int,
    status: str = "staged",
    run_source: str = "manual",
    git_commit: str = "abc1234",
    git_dirty: bool = False,
) -> dict[str, object]:
    return {
        "command": "nightly",
        "success": success,
        "timestamp": _iso(-hours_ago),
        "artifact_id": "artifact-1" if success else None,
        "artifact_status": status,
        "run_source": run_source,
        "git_commit": git_commit,
        "git_dirty": git_dirty,
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
        if command[2] == "show":
            return subprocess.CompletedProcess(
                list(command),
                0,
                f"LoadState=loaded\nUnit={SERVICE_NAME}\nNextElapseUSecRealtime=Sat 2026-06-20 03:00:00 UTC\n",
                "",
            )
        raise AssertionError(f"unexpected command: {command}")

    report = build_soak_report(state_root=state_root, now=NOW, require_timer=True, runner=runner)

    assert report.passed is True
    assert report.timer.enabled is True
    assert report.timer.active is True
    assert calls == [
        ["systemctl", "--user", "is-enabled", TIMER_NAME],
        ["systemctl", "--user", "is-active", TIMER_NAME],
        [
            "systemctl",
            "--user",
            "show",
            TIMER_NAME,
            "-p",
            "LoadState",
            "-p",
            "Unit",
            "-p",
            "NextElapseUSecRealtime",
            "--no-pager",
        ],
    ]


def test_soak_report_fails_when_required_timer_points_to_wrong_unit(tmp_path: Path) -> None:
    state_root = tmp_path / "state"
    _write_ledger(state_root, [_nightly(success=True, hours_ago=2, status="no-op")])

    def runner(command):  # type: ignore[no-untyped-def]
        if command[2] == "is-enabled":
            return subprocess.CompletedProcess(list(command), 0, "enabled\n", "")
        if command[2] == "is-active":
            return subprocess.CompletedProcess(list(command), 0, "active\n", "")
        if command[2] == "show":
            return subprocess.CompletedProcess(
                list(command),
                0,
                "LoadState=loaded\nUnit=other.service\nNextElapseUSecRealtime=Sat 2026-06-20 03:00:00 UTC\n",
                "",
            )
        raise AssertionError(f"unexpected command: {command}")

    report = build_soak_report(state_root=state_root, now=NOW, require_timer=True, runner=runner)

    assert report.passed is False
    assert report.timer.unit == "other.service"
    assert "Unit=other.service" in report.reasons[-1]


def test_soak_report_fails_when_required_timer_has_no_next_elapse(tmp_path: Path) -> None:
    state_root = tmp_path / "state"
    _write_ledger(state_root, [_nightly(success=True, hours_ago=2, status="no-op")])

    def runner(command):  # type: ignore[no-untyped-def]
        if command[2] == "is-enabled":
            return subprocess.CompletedProcess(list(command), 0, "enabled\n", "")
        if command[2] == "is-active":
            return subprocess.CompletedProcess(list(command), 0, "active\n", "")
        if command[2] == "show":
            return subprocess.CompletedProcess(list(command), 0, f"LoadState=loaded\nUnit={SERVICE_NAME}\n", "")
        raise AssertionError(f"unexpected command: {command}")

    report = build_soak_report(state_root=state_root, now=NOW, require_timer=True, runner=runner)

    assert report.passed is False
    assert report.timer.next_elapse is None
    assert "NextElapseUSecRealtime=empty" in report.reasons[-1]


def test_soak_report_can_require_successful_run_source(tmp_path: Path) -> None:
    state_root = tmp_path / "state"
    _write_ledger(
        state_root,
        [
            _nightly(success=True, hours_ago=2, status="no-op", run_source="manual"),
            _nightly(success=True, hours_ago=1, status="no-op", run_source="systemd"),
        ],
    )

    report = build_soak_report(state_root=state_root, now=NOW, required_source="systemd")

    assert report.passed is True
    assert report.required_source == "systemd"
    assert len(report.recent_successful_nightly_runs) == 2
    assert len(report.source_matched_successful_nightly_runs) == 1
    assert len(report.commit_matched_successful_nightly_runs) == 1
    assert len(report.clean_matched_successful_nightly_runs) == 1
    assert len(report.gate_matched_successful_nightly_runs) == 1
    assert "Required run source: `systemd`" in render_soak_report(report)
    assert "source=systemd" in render_soak_report(report)


def test_soak_report_fails_when_required_source_is_missing(tmp_path: Path) -> None:
    state_root = tmp_path / "state"
    _write_ledger(state_root, [_nightly(success=True, hours_ago=2, status="no-op", run_source="manual")])

    report = build_soak_report(state_root=state_root, now=NOW, required_source="systemd")

    assert report.passed is False
    assert "source 'systemd'" in report.reasons[0]
    assert "Source-matching successful nightly runs: `0`" in render_soak_report(report)
    assert "Commit-matching successful nightly runs: `0`" in render_soak_report(report)
    assert "Clean successful nightly runs: `0`" in render_soak_report(report)


def test_soak_report_can_require_successful_git_commit(tmp_path: Path) -> None:
    state_root = tmp_path / "state"
    _write_ledger(
        state_root,
        [
            _nightly(success=True, hours_ago=2, run_source="systemd", git_commit="old1111"),
            _nightly(success=True, hours_ago=1, run_source="systemd", git_commit="new2222"),
        ],
    )

    report = build_soak_report(
        state_root=state_root,
        now=NOW,
        required_source="systemd",
        required_commit="new2222",
    )

    assert report.passed is True
    assert report.required_commit == "new2222"
    assert len(report.recent_successful_nightly_runs) == 2
    assert len(report.source_matched_successful_nightly_runs) == 2
    assert len(report.commit_matched_successful_nightly_runs) == 1
    output = render_soak_report(report)
    assert "Required git commit: `new2222`" in output
    assert "commit=new2222" in output


def test_soak_report_rejects_too_short_required_git_commit(tmp_path: Path) -> None:
    state_root = tmp_path / "state"
    _write_ledger(state_root, [_nightly(success=True, hours_ago=1, run_source="systemd", git_commit="abc1234")])

    report = build_soak_report(
        state_root=state_root,
        now=NOW,
        required_source="systemd",
        required_commit="abc",
    )

    assert report.passed is False
    assert report.required_commit == "abc"
    assert len(report.commit_matched_successful_nightly_runs) == 0
    assert "commit 'abc'" in report.reasons[0]


def test_soak_report_rejects_too_short_ledger_git_commit_prefix(tmp_path: Path) -> None:
    state_root = tmp_path / "state"
    _write_ledger(state_root, [_nightly(success=True, hours_ago=1, run_source="systemd", git_commit="abc")])

    report = build_soak_report(
        state_root=state_root,
        now=NOW,
        required_source="systemd",
        required_commit="abc1234",
    )

    assert report.passed is False
    assert len(report.commit_matched_successful_nightly_runs) == 0
    assert "commit 'abc1234'" in report.reasons[0]


def test_soak_report_distinguishes_gate_matches_from_clean_matches(tmp_path: Path) -> None:
    state_root = tmp_path / "state"
    _write_ledger(
        state_root,
        [_nightly(success=True, hours_ago=1, run_source="systemd", git_commit="abc1234", git_dirty=True)],
    )

    report = build_soak_report(
        state_root=state_root,
        now=NOW,
        required_source="systemd",
        required_commit="abc1234",
    )

    assert report.passed is True
    assert report.require_clean is False
    assert len(report.commit_matched_successful_nightly_runs) == 1
    assert len(report.gate_matched_successful_nightly_runs) == 1
    assert len(report.clean_matched_successful_nightly_runs) == 0
    output = render_soak_report(report)
    assert "Gate-matching successful nightly runs: `1`" in output
    assert "Clean successful nightly runs: `0`" in output
    assert "dirty=true" in output


def test_soak_report_fails_when_required_git_commit_is_missing(tmp_path: Path) -> None:
    state_root = tmp_path / "state"
    _write_ledger(state_root, [_nightly(success=True, hours_ago=2, run_source="systemd", git_commit="old1111")])

    report = build_soak_report(
        state_root=state_root,
        now=NOW,
        required_source="systemd",
        required_commit="new2222",
    )

    assert report.passed is False
    assert "commit 'new2222'" in report.reasons[0]
    assert "Commit-matching successful nightly runs: `0`" in render_soak_report(report)


def test_soak_report_can_require_clean_checkout(tmp_path: Path) -> None:
    state_root = tmp_path / "state"
    _write_ledger(
        state_root,
        [
            _nightly(success=True, hours_ago=2, run_source="systemd", git_commit="abc1234", git_dirty=True),
            _nightly(success=True, hours_ago=1, run_source="systemd", git_commit="abc1234", git_dirty=False),
        ],
    )

    report = build_soak_report(
        state_root=state_root,
        now=NOW,
        required_source="systemd",
        required_commit="abc1234",
        require_clean=True,
    )

    assert report.passed is True
    assert report.require_clean is True
    assert len(report.commit_matched_successful_nightly_runs) == 2
    assert len(report.clean_matched_successful_nightly_runs) == 1
    assert len(report.gate_matched_successful_nightly_runs) == 1
    output = render_soak_report(report)
    assert "Require clean checkout: `true`" in output
    assert "Gate-matching successful nightly runs: `1`" in output
    assert "dirty=false" in output


def test_soak_report_fails_when_clean_checkout_is_required_but_missing(tmp_path: Path) -> None:
    state_root = tmp_path / "state"
    _write_ledger(
        state_root,
        [_nightly(success=True, hours_ago=2, run_source="systemd", git_commit="abc1234", git_dirty=True)],
    )

    report = build_soak_report(
        state_root=state_root,
        now=NOW,
        required_source="systemd",
        required_commit="abc1234",
        require_clean=True,
    )

    assert report.passed is False
    assert "clean checkout" in report.reasons[0]
    assert "Clean successful nightly runs: `0`" in render_soak_report(report)


def test_soak_report_fails_when_clean_checkout_is_required_but_ledger_is_legacy(tmp_path: Path) -> None:
    state_root = tmp_path / "state"
    legacy_record = _nightly(success=True, hours_ago=2, run_source="systemd", git_commit="abc1234")
    legacy_record.pop("git_dirty")
    _write_ledger(state_root, [legacy_record])

    report = build_soak_report(
        state_root=state_root,
        now=NOW,
        required_source="systemd",
        required_commit="abc1234",
        require_clean=True,
    )

    assert report.passed is False
    assert len(report.commit_matched_successful_nightly_runs) == 1
    assert len(report.clean_matched_successful_nightly_runs) == 0
    assert len(report.gate_matched_successful_nightly_runs) == 0
    assert "clean checkout" in report.reasons[0]
    output = render_soak_report(report)
    assert "Gate-matching successful nightly runs: `0`" in output
    assert "Clean successful nightly runs: `0`" in output


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
    _write_ledger(state_root, [_nightly(success=True, hours_ago=2, run_source="systemd", git_commit="abc1234")])

    assert (
        main(
            [
                "soak",
                "--state-root",
                str(state_root),
                "--since-hours",
                "72",
                "--require-source",
                "systemd",
                "--require-commit",
                "abc1234",
                "--require-clean",
                "--json",
            ]
        )
        == 0
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload["passed"] is True
    assert payload["required_source"] == "systemd"
    assert payload["required_commit"] == "abc1234"
    assert payload["require_clean"] is True


def test_soak_cli_strict_systemd_fills_release_gate_defaults(tmp_path: Path, monkeypatch, capsys) -> None:
    state_root = tmp_path / "state"
    _write_ledger(state_root, [_nightly(success=True, hours_ago=2, run_source="systemd", git_commit="abc1234")])
    captured: dict[str, object] = {}

    def fake_build_soak_report(**kwargs):  # type: ignore[no-untyped-def]
        captured.update(kwargs)
        return build_soak_report(
            state_root=kwargs["state_root"],
            since_hours=kwargs["since_hours"],
            min_successful=kwargs["min_successful"],
            require_timer=False,
            required_source=kwargs["required_source"],
            required_commit=kwargs["required_commit"],
            require_clean=kwargs["require_clean"],
            allow_failures=kwargs["allow_failures"],
            now=NOW,
    )

    monkeypatch.setattr(cli_module, "_current_git_commit", lambda: "abc1234")
    monkeypatch.setattr(cli_module, "_current_git_dirty", lambda: False)
    monkeypatch.setattr(cli_module, "build_soak_report", fake_build_soak_report)

    assert main(["soak", "--state-root", str(state_root), "--since-hours", "30", "--strict-systemd", "--json"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["passed"] is True
    assert captured["require_timer"] is True
    assert captured["required_source"] == "systemd"
    assert captured["required_commit"] == "abc1234"
    assert captured["require_clean"] is True
    assert captured["allow_failures"] is False


def test_soak_cli_strict_systemd_rejects_allow_failures(tmp_path: Path) -> None:
    try:
        main(["soak", "--state-root", str(tmp_path / "state"), "--strict-systemd", "--allow-failures"])
    except SystemExit as exc:
        assert exc.code == 2
    else:  # pragma: no cover - assertion branch
        raise AssertionError("strict systemd soak should reject --allow-failures")


def test_soak_cli_strict_systemd_rejects_dirty_current_checkout(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(cli_module, "_current_git_commit", lambda: "abc1234")
    monkeypatch.setattr(cli_module, "_current_git_dirty", lambda: True)

    try:
        main(["soak", "--state-root", str(tmp_path / "state"), "--strict-systemd"])
    except SystemExit as exc:
        assert exc.code == 2
    else:  # pragma: no cover - assertion branch
        raise AssertionError("strict systemd soak should reject a dirty current checkout")

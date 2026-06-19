from __future__ import annotations

import subprocess
from importlib import import_module
from pathlib import Path

from hermes_dreaming.cli import main
from hermes_dreaming.commands.install_systemd import SERVICE_NAME, TIMER_NAME, handle, render_result

systemd_module = import_module("hermes_dreaming.commands.install_systemd")


def test_install_systemd_writes_nightly_units_without_secrets(tmp_path: Path, monkeypatch) -> None:
    hermes_home = tmp_path / ".hermes"
    monkeypatch.setattr(systemd_module, "get_hermes_home", lambda: hermes_home)
    calls: list[list[str]] = []

    def runner(command):  # type: ignore[no-untyped-def]
        calls.append(list(command))
        return subprocess.CompletedProcess(list(command), 0, "", "")

    result = handle(
        on_calendar="*-*-* 02:30:00",
        recent=9,
        live_root=tmp_path / "live",
        artifact_root=tmp_path / "artifacts",
        archive_root=tmp_path / "archive",
        state_root=tmp_path / "state",
        systemd_dir=tmp_path / "systemd",
        script_dir=tmp_path / "scripts",
        env_dir=tmp_path / "env",
        runner=runner,
    )

    assert result.enabled is True
    assert calls == [
        ["systemctl", "--user", "daemon-reload"],
        ["systemctl", "--user", "enable", "--now", TIMER_NAME],
    ]
    assert result.service_path.name == SERVICE_NAME
    assert result.timer_path.name == TIMER_NAME

    service_text = result.service_path.read_text(encoding="utf-8")
    timer_text = result.timer_path.read_text(encoding="utf-8")
    script_text = result.script_path.read_text(encoding="utf-8")
    env_text = result.env_path.read_text(encoding="utf-8")

    assert "Type=oneshot" in service_text
    assert f"EnvironmentFile=-{result.env_path}" in service_text
    assert f"EnvironmentFile=-{result.secret_env_path}" in service_text
    assert "Environment=HERMES_ERSHOV_RUN_SOURCE=systemd" in service_text
    assert f"ExecStart={result.script_path}" in service_text
    assert "OnCalendar=*-*-* 02:30:00" in timer_text
    assert "Persistent=true" in timer_text
    assert "RandomizedDelaySec=10m" in timer_text
    assert '"nightly"' in script_text
    assert "manual-script" in script_text
    assert "HERMES_ERSHOV_RUN_SOURCE" in script_text
    assert "--state-root" in script_text
    assert "--archive-root" in script_text
    assert 'HERMES_ERSHOV_RECENT_SESSIONS="9"' in env_text
    assert "deepseek-v4-flash" in env_text
    assert "DEEPSEEK_API_KEY" not in service_text
    assert "DEEPSEEK_API_KEY" not in script_text
    assert "DEEPSEEK_API_KEY" not in env_text
    assert not result.secret_env_path.exists()


def test_install_systemd_dry_run_does_not_write_or_enable(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(systemd_module, "get_hermes_home", lambda: tmp_path / ".hermes")
    called = False

    def runner(command):  # type: ignore[no-untyped-def]
        nonlocal called
        called = True
        return subprocess.CompletedProcess(list(command), 0, "", "")

    result = handle(
        systemd_dir=tmp_path / "systemd",
        script_dir=tmp_path / "scripts",
        env_dir=tmp_path / "env",
        dry_run=True,
        runner=runner,
    )

    assert result.dry_run is True
    assert result.enabled is False
    assert called is False
    assert not result.service_path.exists()
    assert not result.timer_path.exists()
    assert "Dry run" in render_result(result)


def test_install_systemd_rejects_multiline_timer_values(tmp_path: Path) -> None:
    for kwargs in (
        {"on_calendar": "*-*-* 03:00:00\nEnvironment=BAD=1"},
        {"randomized_delay": "10m\nEnvironment=BAD=1"},
    ):
        try:
            handle(
                systemd_dir=tmp_path / "systemd",
                script_dir=tmp_path / "scripts",
                env_dir=tmp_path / "env",
                dry_run=True,
                **kwargs,
            )
        except ValueError as exc:
            assert "single line" in str(exc)
        else:  # pragma: no cover - assertion branch
            raise AssertionError("multiline systemd value should be rejected")


def test_install_systemd_cli_forwards_options(tmp_path: Path, monkeypatch, capsys) -> None:
    captured: dict[str, object] = {}

    def fake_install_systemd(**kwargs):  # type: ignore[no-untyped-def]
        captured.update(kwargs)
        return systemd_module.SystemdInstallResult(
            service_path=tmp_path / "systemd" / SERVICE_NAME,
            timer_path=tmp_path / "systemd" / TIMER_NAME,
            script_path=tmp_path / "scripts" / systemd_module.SCRIPT_NAME,
            env_path=tmp_path / "env" / systemd_module.ENV_FILE_NAME,
            secret_env_path=tmp_path / "env" / systemd_module.SECRET_ENV_FILE_NAME,
            on_calendar=str(kwargs["on_calendar"]),
            enabled=False,
            dry_run=bool(kwargs["dry_run"]),
            commands=[],
        )

    monkeypatch.setattr("hermes_dreaming.cli.install_systemd_command", fake_install_systemd)
    monkeypatch.setattr(
        "hermes_dreaming.cli.record_run",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("dry-run must not record a run")),
    )

    exit_code = main(
        [
            "install-systemd",
            "--on-calendar",
            "*-*-* 04:00:00",
            "--randomized-delay",
            "20m",
            "--recent",
            "5",
            "--live-root",
            str(tmp_path / "live"),
            "--artifact-root",
            str(tmp_path / "artifacts"),
            "--archive-root",
            str(tmp_path / "archive"),
            "--state-root",
            str(tmp_path / "state"),
            "--systemd-dir",
            str(tmp_path / "systemd"),
            "--script-dir",
            str(tmp_path / "scripts"),
            "--env-dir",
            str(tmp_path / "env"),
            "--provider",
            "offline-marker",
            "--model",
            "",
            "--base-url",
            "",
            "--no-enable",
            "--dry-run",
        ]
    )

    assert exit_code == 0
    assert captured["on_calendar"] == "*-*-* 04:00:00"
    assert captured["randomized_delay"] == "20m"
    assert captured["recent"] == 5
    assert captured["provider"] == "offline-marker"
    assert captured["model"] == ""
    assert captured["base_url"] == ""
    assert captured["enable"] is False
    assert captured["dry_run"] is True
    assert "# Hermes Ershov systemd timer" in capsys.readouterr().out

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence

try:
    from hermes_constants import get_hermes_home  # type: ignore
except Exception:  # pragma: no cover - fallback for direct source inspection
    def get_hermes_home() -> Path:
        return Path.home() / ".hermes"

from .install_cron import _repo_root, render_nightly_script

SERVICE_NAME = "hermes-ershov-nightly.service"
TIMER_NAME = "hermes-ershov-nightly.timer"
SCRIPT_NAME = "hermes_ershov_nightly.py"
ENV_FILE_NAME = "nightly.env"
SECRET_ENV_FILE_NAME = "nightly.secrets.env"
DEFAULT_ON_CALENDAR = "*-*-* 03:00:00"
DEFAULT_RANDOMIZED_DELAY = "10m"

Runner = Callable[[Sequence[str]], subprocess.CompletedProcess[str]]


@dataclass(slots=True)
class SystemdInstallResult:
    service_path: Path
    timer_path: Path
    script_path: Path
    env_path: Path
    secret_env_path: Path
    on_calendar: str
    enabled: bool
    dry_run: bool
    commands: list[list[str]]


def _default_systemd_dir() -> Path:
    return Path.home() / ".config" / "systemd" / "user"


def _default_script_dir() -> Path:
    return Path(get_hermes_home()) / "scripts"


def _default_env_dir() -> Path:
    return Path.home() / ".config" / "hermes-ershov"


def _env_quote(value: object) -> str:
    text = str(value)
    escaped = (
        text.replace("\\", "\\\\")
        .replace("\r", "\\r")
        .replace("\n", "\\n")
        .replace('"', '\\"')
        .replace("$", "\\$")
    )
    return f'"{escaped}"'


def _unit_quote(value: Path) -> str:
    text = str(value)
    if not text:
        return '""'
    if any(char.isspace() for char in text):
        return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return text


def _single_line_unit_value(name: str, value: str) -> str:
    if "\n" in value or "\r" in value:
        raise ValueError(f"{name} must be a single line")
    return value


def _render_env_file(
    *,
    hermes_home: Path,
    live_root: Path,
    artifact_root: Path,
    archive_root: Path,
    state_root: Path,
    provider: str,
    model: str,
    base_url: str | None,
    recent: int,
) -> str:
    lines = [
        "# Hermes Ershov nightly memory runtime knobs.",
        "# Store provider secrets outside this generated file when possible.",
        f"HERMES_HOME={_env_quote(hermes_home)}",
        f"HERMES_ERSHOV_LIVE_ROOT={_env_quote(live_root)}",
        f"HERMES_ERSHOV_ARTIFACT_ROOT={_env_quote(artifact_root)}",
        f"HERMES_ERSHOV_ARCHIVE_ROOT={_env_quote(archive_root)}",
        f"HERMES_ERSHOV_STATE_ROOT={_env_quote(state_root)}",
        f"HERMES_ERSHOV_PROVIDER={_env_quote(provider)}",
        f"HERMES_ERSHOV_MODEL={_env_quote(model or '')}",
        f"HERMES_ERSHOV_BASE_URL={_env_quote(base_url or '')}",
        f"HERMES_ERSHOV_RECENT_SESSIONS={_env_quote(recent)}",
        "",
    ]
    return "\n".join(lines)


def _render_service(*, script_path: Path, env_path: Path, secret_env_path: Path, repo_root: Path) -> str:
    return (
        "[Unit]\n"
        "Description=Hermes Ershov nightly memory\n"
        "After=network-online.target\n"
        "Wants=network-online.target\n\n"
        "[Service]\n"
        "Type=oneshot\n"
        f"WorkingDirectory={_unit_quote(repo_root)}\n"
        "Environment=PYTHONUNBUFFERED=1\n"
        f"EnvironmentFile=-{_unit_quote(env_path)}\n"
        f"EnvironmentFile=-{_unit_quote(secret_env_path)}\n"
        "Environment=HERMES_ERSHOV_RUN_SOURCE=systemd\n"
        f"ExecStart={_unit_quote(script_path)}\n"
        "Nice=5\n"
        "StandardOutput=journal\n"
        "StandardError=journal\n"
    )


def _render_timer(*, on_calendar: str, randomized_delay: str) -> str:
    return (
        "[Unit]\n"
        "Description=Run Hermes Ershov nightly memory\n\n"
        "[Timer]\n"
        f"OnCalendar={on_calendar}\n"
        "Persistent=true\n"
        f"RandomizedDelaySec={randomized_delay}\n"
        f"Unit={SERVICE_NAME}\n\n"
        "[Install]\n"
        "WantedBy=timers.target\n"
    )


def _write_if_changed(path: Path, text: str, *, executable: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    current = path.read_text(encoding="utf-8") if path.exists() else None
    if current != text:
        path.write_text(text, encoding="utf-8")
    if executable:
        try:
            path.chmod(0o755)
        except OSError:
            pass


def _run_systemctl(command: Sequence[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(command),
        capture_output=True,
        text=True,
        check=False,
    )


def handle(
    *,
    on_calendar: str = DEFAULT_ON_CALENDAR,
    randomized_delay: str = DEFAULT_RANDOMIZED_DELAY,
    recent: int = 14,
    provider: str = "deepseek",
    model: str = "deepseek-v4-flash",
    base_url: str | None = "https://api.deepseek.com/v1",
    live_root: Path | None = None,
    artifact_root: Path | None = None,
    archive_root: Path | None = None,
    state_root: Path | None = None,
    systemd_dir: Path | None = None,
    script_dir: Path | None = None,
    env_dir: Path | None = None,
    enable: bool = True,
    dry_run: bool = False,
    runner: Runner | None = None,
) -> SystemdInstallResult:
    if recent <= 0:
        raise ValueError("recent must be greater than 0")
    on_calendar = _single_line_unit_value("on-calendar", on_calendar.strip())
    randomized_delay = _single_line_unit_value("randomized-delay", randomized_delay.strip())
    if not on_calendar:
        raise ValueError("on-calendar must not be empty")
    if not randomized_delay:
        raise ValueError("randomized-delay must not be empty")

    repo_root = _repo_root()
    hermes_home = Path(get_hermes_home())
    resolved_live_root = Path(live_root) if live_root is not None else hermes_home / "memories"
    resolved_artifact_root = Path(artifact_root) if artifact_root is not None else repo_root / ".ershov" / "artifacts"
    resolved_archive_root = Path(archive_root) if archive_root is not None else repo_root / ".ershov" / "archive"
    resolved_state_root = Path(state_root) if state_root is not None else hermes_home / "ershov"
    resolved_systemd_dir = Path(systemd_dir) if systemd_dir is not None else _default_systemd_dir()
    resolved_script_dir = Path(script_dir) if script_dir is not None else _default_script_dir()
    resolved_env_dir = Path(env_dir) if env_dir is not None else _default_env_dir()

    service_path = resolved_systemd_dir / SERVICE_NAME
    timer_path = resolved_systemd_dir / TIMER_NAME
    script_path = resolved_script_dir / SCRIPT_NAME
    env_path = resolved_env_dir / ENV_FILE_NAME
    secret_env_path = resolved_env_dir / SECRET_ENV_FILE_NAME

    script_text = render_nightly_script(
        repo_root=repo_root,
        recent=recent,
        provider=provider,
        model=model,
        base_url=base_url,
        live_root=resolved_live_root,
        artifact_root=resolved_artifact_root,
        archive_root=resolved_archive_root,
        state_root=resolved_state_root,
        run_source="manual-script",
    )
    env_text = _render_env_file(
        hermes_home=hermes_home,
        live_root=resolved_live_root,
        artifact_root=resolved_artifact_root,
        archive_root=resolved_archive_root,
        state_root=resolved_state_root,
        provider=provider,
        model=model,
        base_url=base_url,
        recent=recent,
    )
    service_text = _render_service(
        script_path=script_path,
        env_path=env_path,
        secret_env_path=secret_env_path,
        repo_root=repo_root,
    )
    timer_text = _render_timer(on_calendar=on_calendar, randomized_delay=randomized_delay)

    commands = [
        ["systemctl", "--user", "daemon-reload"],
        ["systemctl", "--user", "enable", "--now", TIMER_NAME],
    ]
    if not dry_run:
        _write_if_changed(script_path, script_text, executable=True)
        _write_if_changed(env_path, env_text)
        _write_if_changed(service_path, service_text)
        _write_if_changed(timer_path, timer_text)
        if enable:
            run = runner or _run_systemctl
            for command in commands:
                result = run(command)
                if result.returncode != 0:
                    error = (result.stderr or result.stdout or "").strip()
                    raise RuntimeError(f"{' '.join(command)} failed: {error or 'unknown error'}")

    return SystemdInstallResult(
        service_path=service_path,
        timer_path=timer_path,
        script_path=script_path,
        env_path=env_path,
        secret_env_path=secret_env_path,
        on_calendar=on_calendar,
        enabled=enable and not dry_run,
        dry_run=dry_run,
        commands=commands if enable else [],
    )


def render_result(result: SystemdInstallResult) -> str:
    action = "Dry run" if result.dry_run else ("Installed and enabled" if result.enabled else "Installed")
    lines = [
        "# Hermes Ershov systemd timer",
        "",
        f"- Status: `{action}`",
        f"- Service: `{result.service_path}`",
        f"- Timer: `{result.timer_path}`",
        f"- Script: `{result.script_path}`",
        f"- Env file: `{result.env_path}`",
        f"- Secret env file: `{result.secret_env_path}`",
        f"- Schedule: `{result.on_calendar}`",
        "",
        "## Safety",
        "",
        "- Runs outside the Hermes gateway process.",
        "- Does not restart Hermes.",
        "- Does not apply live memory automatically.",
        "- Provider secrets are not written by the installer.",
        "- The optional secret env file is read if present and is never generated.",
    ]
    if result.commands:
        lines.extend(["", "## Commands", ""])
        for command in result.commands:
            lines.append(f"- `{' '.join(command)}`")
    return "\n".join(lines).rstrip() + "\n"

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import subprocess
from typing import Any, Callable, Sequence

from .. import state as state_module
from .install_systemd import TIMER_NAME

Runner = Callable[[Sequence[str]], subprocess.CompletedProcess[str]]


@dataclass(slots=True)
class TimerProbe:
    timer_name: str
    checked: bool
    enabled: bool | None
    active: bool | None
    error: str | None = None


@dataclass(slots=True)
class SoakReport:
    passed: bool
    state_root: Path
    ledger_path: Path
    since_hours: int
    min_successful: int
    require_timer: bool
    allow_failures: bool
    total_nightly_runs: int
    recent_successful_nightly_runs: list[dict[str, Any]]
    recent_failed_nightly_runs: list[dict[str, Any]]
    timer: TimerProbe
    reasons: list[str]


def _now_utc() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _parse_timestamp(value: object) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _record_in_window(record: dict[str, Any], *, cutoff: datetime) -> bool:
    timestamp = _parse_timestamp(record.get("timestamp"))
    return timestamp is not None and timestamp >= cutoff


def _run_systemctl(command: Sequence[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(list(command), capture_output=True, text=True, check=False)


def _probe_timer(*, timer_name: str = TIMER_NAME, runner: Runner | None = None, checked: bool = True) -> TimerProbe:
    if not checked:
        return TimerProbe(timer_name=timer_name, checked=False, enabled=None, active=None)

    run = runner or _run_systemctl
    try:
        enabled_result = run(["systemctl", "--user", "is-enabled", timer_name])
        active_result = run(["systemctl", "--user", "is-active", timer_name])
    except FileNotFoundError:
        return TimerProbe(timer_name=timer_name, checked=True, enabled=None, active=None, error="systemctl not found")
    except OSError as exc:
        return TimerProbe(timer_name=timer_name, checked=True, enabled=None, active=None, error=str(exc))

    enabled_text = (enabled_result.stdout or enabled_result.stderr or "").strip()
    active_text = (active_result.stdout or active_result.stderr or "").strip()
    enabled = enabled_result.returncode == 0 and enabled_text in {"enabled", "static", "generated", "linked"}
    active = active_result.returncode == 0 and active_text == "active"
    error = None
    if not enabled:
        error = f"is-enabled={enabled_text or enabled_result.returncode}"
    if not active:
        active_error = f"is-active={active_text or active_result.returncode}"
        error = f"{error}; {active_error}" if error else active_error
    return TimerProbe(timer_name=timer_name, checked=True, enabled=enabled, active=active, error=error)


def build_soak_report(
    *,
    state_root: Path | None = None,
    since_hours: int = 30,
    min_successful: int = 1,
    require_timer: bool = False,
    timer_name: str = TIMER_NAME,
    allow_failures: bool = False,
    now: datetime | None = None,
    runner: Runner | None = None,
) -> SoakReport:
    if since_hours <= 0:
        raise ValueError("since-hours must be greater than 0")
    if min_successful <= 0:
        raise ValueError("min-successful must be greater than 0")

    resolved_state_root = Path(state_root) if state_root is not None else state_module.STATE_ROOT
    ledger_path = resolved_state_root / "runs.jsonl"
    current_time = (now or _now_utc()).astimezone(timezone.utc)
    cutoff = current_time - timedelta(hours=since_hours)

    runs = state_module.read_run_ledger(ledger_path=ledger_path)
    nightly_runs = [record for record in runs if str(record.get("command", "")).lower() == "nightly"]
    recent_nightly = [record for record in nightly_runs if _record_in_window(record, cutoff=cutoff)]
    recent_successes = [record for record in recent_nightly if bool(record.get("success"))]
    recent_failures = [record for record in recent_nightly if not bool(record.get("success"))]

    timer = _probe_timer(timer_name=timer_name, runner=runner, checked=require_timer)
    reasons: list[str] = []
    if len(recent_successes) < min_successful:
        reasons.append(
            f"found {len(recent_successes)} successful nightly run(s) in the last {since_hours}h; "
            f"required {min_successful}"
        )
    if recent_failures and not allow_failures:
        reasons.append(f"found {len(recent_failures)} failed nightly run(s) in the last {since_hours}h")
    if require_timer:
        if timer.error:
            reasons.append(f"timer {timer.timer_name} is not healthy: {timer.error}")
        elif timer.enabled is not True or timer.active is not True:
            reasons.append(f"timer {timer.timer_name} is not enabled and active")

    return SoakReport(
        passed=not reasons,
        state_root=resolved_state_root,
        ledger_path=ledger_path,
        since_hours=since_hours,
        min_successful=min_successful,
        require_timer=require_timer,
        allow_failures=allow_failures,
        total_nightly_runs=len(nightly_runs),
        recent_successful_nightly_runs=recent_successes,
        recent_failed_nightly_runs=recent_failures,
        timer=timer,
        reasons=reasons,
    )


def _format_record(record: dict[str, Any]) -> str:
    timestamp = str(record.get("timestamp") or "unknown time")
    status = str(record.get("artifact_status") or "unknown")
    summary = str(record.get("summary") or "").strip()
    artifact_id = str(record.get("artifact_id") or "none")
    parts = [f"{timestamp}", f"status={status}", f"artifact={artifact_id}"]
    if summary:
        parts.append(summary)
    return " | ".join(parts)


def render_soak_report(report: SoakReport) -> str:
    timer_state = "not checked"
    if report.timer.checked:
        timer_state = (
            f"enabled={report.timer.enabled}, active={report.timer.active}"
            + (f", error={report.timer.error}" if report.timer.error else "")
        )

    lines = [
        "# Hermes Ershov soak report",
        "",
        f"- Status: `{'pass' if report.passed else 'fail'}`",
        f"- State root: `{report.state_root}`",
        f"- Ledger: `{report.ledger_path}`",
        f"- Window: `{report.since_hours}h`",
        f"- Required successful nightly runs: `{report.min_successful}`",
        f"- Successful nightly runs in window: `{len(report.recent_successful_nightly_runs)}`",
        f"- Failed nightly runs in window: `{len(report.recent_failed_nightly_runs)}`",
        f"- Total nightly runs in ledger: `{report.total_nightly_runs}`",
        f"- Timer required: `{str(report.require_timer).lower()}`",
        f"- Timer: `{timer_state}`",
        "",
        "## Latest successful nightly",
        "",
    ]
    if report.recent_successful_nightly_runs:
        lines.append(f"- {_format_record(report.recent_successful_nightly_runs[-1])}")
    else:
        lines.append("- none")

    lines.extend(["", "## Recent failures", ""])
    if report.recent_failed_nightly_runs:
        for record in report.recent_failed_nightly_runs[-5:]:
            lines.append(f"- {_format_record(record)}")
    else:
        lines.append("- none")

    lines.extend(["", "## Verdict", ""])
    if report.passed:
        lines.append("- PASS: nightly soak evidence satisfies the configured gate.")
    else:
        for reason in report.reasons:
            lines.append(f"- FAIL: {reason}")
    return "\n".join(lines).rstrip() + "\n"


def render_soak_report_json(report: SoakReport) -> str:
    payload = asdict(report)
    payload["state_root"] = str(report.state_root)
    payload["ledger_path"] = str(report.ledger_path)
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n"

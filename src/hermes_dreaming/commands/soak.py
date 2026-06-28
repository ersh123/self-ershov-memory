from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import subprocess
from typing import Any, Callable, Sequence

from .. import state as state_module
from ..providers import ProviderDoctorRow, doctor_providers, load_env_files, render_provider_fix_plan
from .install_systemd import SERVICE_NAME, TIMER_NAME, default_env_files

Runner = Callable[[Sequence[str]], subprocess.CompletedProcess[str]]
MIN_COMMIT_MATCH_CHARS = 7
FIX_PLAN_PROVIDERS = {"offline-marker", "openai-compatible", "deepseek", "ollama"}


@dataclass(slots=True)
class TimerProbe:
    timer_name: str
    checked: bool
    enabled: bool | None
    active: bool | None
    load_state: str | None = None
    unit: str | None = None
    next_elapse: str | None = None
    error: str | None = None


@dataclass(slots=True)
class ProviderProbe:
    checked: bool
    env_files: list[str]
    expected_provider: str | None = None
    configured_provider: str | None = None
    readiness: str | None = None
    checks: str | None = None
    notes: str | None = None
    error: str | None = None


@dataclass(slots=True)
class SoakReport:
    passed: bool
    state_root: Path
    ledger_path: Path
    since_hours: int
    min_successful: int
    require_timer: bool
    required_source: str | None
    required_commit: str | None
    require_clean: bool
    allow_failures: bool
    total_nightly_runs: int
    recent_successful_nightly_runs: list[dict[str, Any]]
    source_matched_successful_nightly_runs: list[dict[str, Any]]
    commit_matched_successful_nightly_runs: list[dict[str, Any]]
    clean_matched_successful_nightly_runs: list[dict[str, Any]]
    gate_matched_successful_nightly_runs: list[dict[str, Any]]
    recent_failed_nightly_runs: list[dict[str, Any]]
    timer: TimerProbe
    provider: ProviderProbe
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


def _normalize_source(value: object) -> str:
    text = str(value or "manual").strip().lower()
    normalized = "".join(char if char.isalnum() or char in {"-", "_", "."} else "-" for char in text)
    return normalized[:64] or "manual"


def _normalize_commit(value: object) -> str | None:
    text = str(value or "").strip().lower()
    if not text:
        return None
    normalized = "".join(char for char in text if char.isalnum())
    return normalized or None


def _commit_matches(record: dict[str, Any], *, required_commit: str | None) -> bool:
    if required_commit is None:
        return True
    commit = _normalize_commit(record.get("git_commit"))
    if commit is None:
        return False
    if len(commit) < MIN_COMMIT_MATCH_CHARS or len(required_commit) < MIN_COMMIT_MATCH_CHARS:
        return False
    return commit == required_commit or commit.startswith(required_commit) or required_commit.startswith(commit)


def _is_clean(record: dict[str, Any]) -> bool:
    return record.get("git_dirty") is False


def _run_systemctl(command: Sequence[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(list(command), capture_output=True, text=True, check=False)


def _parse_systemctl_show(output: str) -> dict[str, str]:
    properties: dict[str, str] = {}
    for line in output.splitlines():
        key, separator, value = line.partition("=")
        if separator:
            properties[key] = value.strip()
    return properties


def _probe_timer(*, timer_name: str = TIMER_NAME, runner: Runner | None = None, checked: bool = True) -> TimerProbe:
    if not checked:
        return TimerProbe(timer_name=timer_name, checked=False, enabled=None, active=None)

    run = runner or _run_systemctl
    try:
        enabled_result = run(["systemctl", "--user", "is-enabled", timer_name])
        active_result = run(["systemctl", "--user", "is-active", timer_name])
        show_result = run(
            [
                "systemctl",
                "--user",
                "show",
                timer_name,
                "-p",
                "LoadState",
                "-p",
                "Unit",
                "-p",
                "NextElapseUSecRealtime",
                "--no-pager",
            ]
        )
    except FileNotFoundError:
        return TimerProbe(timer_name=timer_name, checked=True, enabled=None, active=None, error="systemctl not found")
    except OSError as exc:
        return TimerProbe(timer_name=timer_name, checked=True, enabled=None, active=None, error=str(exc))

    enabled_text = (enabled_result.stdout or enabled_result.stderr or "").strip()
    active_text = (active_result.stdout or active_result.stderr or "").strip()
    show_text = (show_result.stdout or show_result.stderr or "").strip()
    show_properties = _parse_systemctl_show(show_result.stdout or "")
    load_state = show_properties.get("LoadState") or None
    unit = show_properties.get("Unit") or None
    next_elapse = show_properties.get("NextElapseUSecRealtime") or None
    enabled = enabled_result.returncode == 0 and enabled_text in {"enabled", "static", "generated", "linked"}
    active = active_result.returncode == 0 and active_text == "active"
    errors = []
    if not enabled:
        errors.append(f"is-enabled={enabled_text or enabled_result.returncode}")
    if not active:
        errors.append(f"is-active={active_text or active_result.returncode}")
    if show_result.returncode != 0:
        errors.append(f"show={show_text or show_result.returncode}")
    if load_state != "loaded":
        errors.append(f"LoadState={load_state or 'empty'}")
    if unit != SERVICE_NAME:
        errors.append(f"Unit={unit or 'empty'}")
    if next_elapse in {None, "", "n/a"}:
        errors.append("NextElapseUSecRealtime=empty")
    return TimerProbe(
        timer_name=timer_name,
        checked=True,
        enabled=enabled,
        active=active,
        load_state=load_state,
        unit=unit,
        next_elapse=next_elapse,
        error="; ".join(errors) or None,
    )


def _first_doctor_row(rows: list[ProviderDoctorRow]) -> ProviderDoctorRow | None:
    return rows[0] if rows else None


def _probe_provider(
    *,
    checked: bool,
    env_files: list[Path] | None = None,
    required_provider: str | None = None,
) -> ProviderProbe:
    resolved_env_files = [Path(path) for path in (env_files if env_files is not None else default_env_files())]
    if not checked:
        return ProviderProbe(checked=False, env_files=[str(path) for path in resolved_env_files])

    env = load_env_files(resolved_env_files)
    configured_provider = str(env.get("HERMES_ERSHOV_PROVIDER", "")).strip() or None
    expected_provider = str(required_provider).strip() if required_provider is not None else None
    provider_to_check = expected_provider or configured_provider
    if not provider_to_check:
        return ProviderProbe(
            checked=True,
            env_files=[str(path) for path in resolved_env_files],
            expected_provider=expected_provider,
            configured_provider=configured_provider,
            readiness="blocked",
            checks="HERMES_ERSHOV_PROVIDER: missing",
            notes="timer-visible provider readiness only; values are never printed",
        )

    model = str(env.get("HERMES_ERSHOV_MODEL", "")).strip() or None
    base_url = str(env.get("HERMES_ERSHOV_BASE_URL", "")).strip() or None
    try:
        row = _first_doctor_row(doctor_providers(provider=provider_to_check, model=model, base_url=base_url, env=env))
    except ValueError as exc:
        return ProviderProbe(
            checked=True,
            env_files=[str(path) for path in resolved_env_files],
            expected_provider=expected_provider,
            configured_provider=configured_provider,
            readiness="blocked",
            checks=str(exc),
            notes="timer-visible provider readiness only; values are never printed",
            error=str(exc),
        )

    if row is None:  # pragma: no cover - doctor_providers returns one row for a selected provider.
        return ProviderProbe(
            checked=True,
            env_files=[str(path) for path in resolved_env_files],
            expected_provider=expected_provider,
            configured_provider=configured_provider,
            readiness="blocked",
            checks="provider doctor returned no rows",
            notes="timer-visible provider readiness only; values are never printed",
            error="provider doctor returned no rows",
        )

    readiness = row.readiness
    checks = row.checks

    return ProviderProbe(
        checked=True,
        env_files=[str(path) for path in resolved_env_files],
        expected_provider=expected_provider,
        configured_provider=configured_provider,
        readiness=readiness,
        checks=checks,
        notes=row.notes + "; timer-visible provider readiness only; values are never printed",
    )


def build_soak_report(
    *,
    state_root: Path | None = None,
    since_hours: int = 30,
    min_successful: int = 1,
    require_timer: bool = False,
    required_source: str | None = None,
    required_commit: str | None = None,
    require_clean: bool = False,
    timer_name: str = TIMER_NAME,
    allow_failures: bool = False,
    check_provider: bool = False,
    required_provider: str | None = None,
    provider_env_files: list[Path] | None = None,
    now: datetime | None = None,
    runner: Runner | None = None,
) -> SoakReport:
    if since_hours <= 0:
        raise ValueError("since-hours must be greater than 0")
    if min_successful <= 0:
        raise ValueError("min-successful must be greater than 0")
    normalized_required_source = _normalize_source(required_source) if required_source is not None else None
    normalized_required_commit = _normalize_commit(required_commit)

    resolved_state_root = Path(state_root) if state_root is not None else state_module.STATE_ROOT
    ledger_path = resolved_state_root / "runs.jsonl"
    current_time = (now or _now_utc()).astimezone(timezone.utc)
    cutoff = current_time - timedelta(hours=since_hours)

    runs = state_module.read_run_ledger(ledger_path=ledger_path)
    nightly_runs = [record for record in runs if str(record.get("command", "")).lower() == "nightly"]
    recent_nightly = [record for record in nightly_runs if _record_in_window(record, cutoff=cutoff)]
    recent_successes = [record for record in recent_nightly if bool(record.get("success"))]
    source_matched_successes = (
        recent_successes
        if normalized_required_source is None
        else [record for record in recent_successes if _normalize_source(record.get("run_source")) == normalized_required_source]
    )
    commit_matched_successes = [
        record for record in source_matched_successes if _commit_matches(record, required_commit=normalized_required_commit)
    ]
    clean_matched_successes = [record for record in commit_matched_successes if _is_clean(record)]
    gate_matched_successes = clean_matched_successes if require_clean else commit_matched_successes
    recent_failures = [record for record in recent_nightly if not bool(record.get("success"))]

    timer = _probe_timer(timer_name=timer_name, runner=runner, checked=require_timer)
    provider = _probe_provider(
        checked=check_provider or required_provider is not None,
        env_files=provider_env_files,
        required_provider=required_provider,
    )
    reasons: list[str] = []
    if len(gate_matched_successes) < min_successful:
        filters = []
        if normalized_required_source is not None:
            filters.append(f"source '{normalized_required_source}'")
        if normalized_required_commit is not None:
            filters.append(f"commit '{normalized_required_commit}'")
        if require_clean:
            filters.append("clean checkout")
        filter_suffix = "" if not filters else " matching " + " and ".join(filters)
        reasons.append(
            f"found {len(gate_matched_successes)} successful nightly run(s){filter_suffix} in the last {since_hours}h; "
            f"required {min_successful}"
        )
    if recent_failures and not allow_failures:
        reasons.append(f"found {len(recent_failures)} failed nightly run(s) in the last {since_hours}h")
    if require_timer:
        if timer.error:
            reasons.append(f"timer {timer.timer_name} is not healthy: {timer.error}")
        elif timer.enabled is not True or timer.active is not True:
            reasons.append(f"timer {timer.timer_name} is not enabled and active")
    if provider.checked:
        if provider.error:
            reasons.append(f"timer provider readiness failed: {provider.error}")
        elif provider.readiness != "ready":
            provider_name = provider.expected_provider or provider.configured_provider or "unknown"
            reasons.append(f"timer provider {provider_name} is not ready: {provider.checks or 'unknown readiness'}")

    return SoakReport(
        passed=not reasons,
        state_root=resolved_state_root,
        ledger_path=ledger_path,
        since_hours=since_hours,
        min_successful=min_successful,
        require_timer=require_timer,
        required_source=normalized_required_source,
        required_commit=normalized_required_commit,
        require_clean=require_clean,
        allow_failures=allow_failures,
        total_nightly_runs=len(nightly_runs),
        recent_successful_nightly_runs=recent_successes,
        source_matched_successful_nightly_runs=source_matched_successes,
        commit_matched_successful_nightly_runs=commit_matched_successes,
        clean_matched_successful_nightly_runs=clean_matched_successes,
        gate_matched_successful_nightly_runs=gate_matched_successes,
        recent_failed_nightly_runs=recent_failures,
        timer=timer,
        provider=provider,
        reasons=reasons,
    )


def _format_record(record: dict[str, Any]) -> str:
    timestamp = str(record.get("timestamp") or "unknown time")
    status = str(record.get("artifact_status") or "unknown")
    summary = str(record.get("summary") or "").strip()
    artifact_id = str(record.get("artifact_id") or "none")
    source = _normalize_source(record.get("run_source"))
    commit = _normalize_commit(record.get("git_commit")) or "unknown"
    dirty = record.get("git_dirty")
    dirty_text = "unknown" if dirty is None else str(bool(dirty)).lower()
    parts = [
        f"{timestamp}",
        f"source={source}",
        f"commit={commit}",
        f"dirty={dirty_text}",
        f"status={status}",
        f"artifact={artifact_id}",
    ]
    if summary:
        parts.append(summary)
    return " | ".join(parts)


def _provider_fix_plan_row(report: SoakReport) -> ProviderDoctorRow | None:
    if not report.provider.checked or report.provider.readiness == "ready":
        return None
    provider_name = (report.provider.expected_provider or report.provider.configured_provider or "").strip()
    if provider_name not in FIX_PLAN_PROVIDERS:
        return None
    return ProviderDoctorRow(
        name=provider_name,
        kind="provider",
        readiness=report.provider.readiness or "blocked",
        checks=report.provider.checks or "",
        notes=report.provider.notes or "",
    )


def render_provider_probe_fix_plan(report: SoakReport) -> str:
    row = _provider_fix_plan_row(report)
    if row is None:
        return ""
    env_files = [Path(path) for path in report.provider.env_files]
    return render_provider_fix_plan([row], env_files=env_files)


def render_soak_report(report: SoakReport, *, include_fix_plan: bool = False) -> str:
    timer_state = "not checked"
    if report.timer.checked:
        timer_state = (
            f"enabled={report.timer.enabled}, active={report.timer.active}"
            + (f", load={report.timer.load_state}" if report.timer.load_state is not None else "")
            + (f", unit={report.timer.unit}" if report.timer.unit is not None else "")
            + (f", next={report.timer.next_elapse}" if report.timer.next_elapse is not None else "")
            + (f", error={report.timer.error}" if report.timer.error else "")
        )
    provider_state = "not checked"
    if report.provider.checked:
        provider_state = (
            f"expected={report.provider.expected_provider or 'any'}, "
            f"configured={report.provider.configured_provider or 'missing'}, "
            f"readiness={report.provider.readiness or 'unknown'}"
            + (f", checks={report.provider.checks}" if report.provider.checks else "")
            + (f", error={report.provider.error}" if report.provider.error else "")
        )

    lines = [
        "# Hermes Ershov soak report",
        "",
        f"- Status: `{'pass' if report.passed else 'fail'}`",
        f"- State root: `{report.state_root}`",
        f"- Ledger: `{report.ledger_path}`",
        f"- Window: `{report.since_hours}h`",
        f"- Required successful nightly runs: `{report.min_successful}`",
        f"- Required run source: `{report.required_source or 'any'}`",
        f"- Required git commit: `{report.required_commit or 'any'}`",
        f"- Require clean checkout: `{str(report.require_clean).lower()}`",
        f"- Successful nightly runs in window: `{len(report.recent_successful_nightly_runs)}`",
        f"- Source-matching successful nightly runs: `{len(report.source_matched_successful_nightly_runs)}`",
        f"- Commit-matching successful nightly runs: `{len(report.commit_matched_successful_nightly_runs)}`",
        f"- Gate-matching successful nightly runs: `{len(report.gate_matched_successful_nightly_runs)}`",
        f"- Clean successful nightly runs: `{len(report.clean_matched_successful_nightly_runs)}`",
        f"- Failed nightly runs in window: `{len(report.recent_failed_nightly_runs)}`",
        f"- Total nightly runs in ledger: `{report.total_nightly_runs}`",
        f"- Timer required: `{str(report.require_timer).lower()}`",
        f"- Timer: `{timer_state}`",
        f"- Timer provider: `{provider_state}`",
        "",
        "## Latest successful nightly",
        "",
    ]
    latest_successes = report.gate_matched_successful_nightly_runs
    if latest_successes:
        lines.append(f"- {_format_record(latest_successes[-1])}")
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

    if include_fix_plan:
        fix_plan = render_provider_probe_fix_plan(report)
        if fix_plan:
            lines.extend(["", "## Fix plan", "", fix_plan.rstrip()])
    return "\n".join(lines).rstrip() + "\n"


def render_soak_report_json(report: SoakReport) -> str:
    payload = asdict(report)
    payload["state_root"] = str(report.state_root)
    payload["ledger_path"] = str(report.ledger_path)
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n"

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .. import dreams_md as dreams_md_module
from .. import state as state_module
from ..analyze import list_artifacts
from .soak import SoakReport


@dataclass(slots=True)
class StatusSnapshot:
    artifact_root: Path
    artifact_count: int
    artifact_state_counts: dict[str, int]
    last_run: dict[str, Any] | None
    last_successful_run: dict[str, Any] | None
    last_nightly_run: dict[str, Any] | None
    last_successful_nightly_run: dict[str, Any] | None
    last_failed_nightly_run: dict[str, Any] | None
    run_count: int
    successful_run_count: int
    memory_usage: dict[str, int]
    state_path: Path
    ledger_path: Path
    diary_path: Path


def _file_size(path: Path) -> int:
    try:
        return path.stat().st_size if path.exists() else 0
    except OSError:
        return 0


def _format_run(record: dict[str, Any] | None) -> str:
    if not record:
        return "none"
    timestamp = str(record.get("timestamp", "unknown time"))
    command = str(record.get("command", "unknown"))
    outcome = "success" if record.get("success") else "failure"
    parts = [f"{timestamp} — {command} ({outcome})"]

    artifact_id = record.get("artifact_id")
    if artifact_id:
        parts.append(f"artifact={artifact_id}")

    artifact_status = record.get("artifact_status")
    if artifact_status:
        parts.append(f"status={artifact_status}")

    summary = record.get("summary")
    if summary:
        parts.append(str(summary))

    return " | ".join(parts)


def _artifact_state_counts(artifacts: list) -> dict[str, int]:
    counts = Counter(artifact.status for artifact in artifacts)
    return dict(sorted(counts.items()))


def _is_nightly_run(record: dict[str, Any]) -> bool:
    return str(record.get("command", "")).lower() == "nightly"


def _coerce_int(value: Any, default: int) -> int:
    return value if isinstance(value, int) else default


def build_status_snapshot(
    *,
    artifact_root: Path,
    state_path: Path | None = None,
    ledger_path: Path | None = None,
    diary_path: Path | None = None,
) -> StatusSnapshot:
    artifact_root = Path(artifact_root)
    state_path = Path(state_path) if state_path is not None else state_module.STATE_JSON
    ledger_path = Path(ledger_path) if ledger_path is not None else state_module.RUN_LEDGER_JSONL
    diary_path = Path(diary_path) if diary_path is not None else dreams_md_module.DREAMS_MD_PATH

    state = state_module.read(state_path=state_path)
    runs = state_module.read_run_ledger(ledger_path=ledger_path)
    artifacts = list_artifacts(artifact_root)

    last_run = state.get("last_run") if isinstance(state.get("last_run"), dict) else None
    if last_run is None and runs:
        last_run = runs[-1]

    last_successful_run = state.get("last_successful_run") if isinstance(state.get("last_successful_run"), dict) else None
    if last_successful_run is None:
        for record in reversed(runs):
            if record.get("success"):
                last_successful_run = record
                break
    nightly_runs = [record for record in runs if _is_nightly_run(record)]
    last_nightly_run = nightly_runs[-1] if nightly_runs else None
    last_successful_nightly_run = None
    last_failed_nightly_run = None
    for record in reversed(nightly_runs):
        if last_successful_nightly_run is None and record.get("success"):
            last_successful_nightly_run = record
        if last_failed_nightly_run is None and not record.get("success"):
            last_failed_nightly_run = record
        if last_successful_nightly_run is not None and last_failed_nightly_run is not None:
            break

    run_count = _coerce_int(state.get("run_count"), len(runs))
    successful_run_count = _coerce_int(state.get("successful_run_count"), sum(1 for record in runs if record.get("success")))

    return StatusSnapshot(
        artifact_root=artifact_root,
        artifact_count=len(artifacts),
        artifact_state_counts=_artifact_state_counts(artifacts),
        last_run=last_run,
        last_successful_run=last_successful_run,
        last_nightly_run=last_nightly_run,
        last_successful_nightly_run=last_successful_nightly_run,
        last_failed_nightly_run=last_failed_nightly_run,
        run_count=run_count,
        successful_run_count=successful_run_count,
        memory_usage={
            "state": _file_size(state_path),
            "ledger": _file_size(ledger_path),
            "diary": _file_size(diary_path),
        },
        state_path=state_path,
        ledger_path=ledger_path,
        diary_path=diary_path,
    )


def _release_gate_timer_state(report: SoakReport) -> str:
    if not report.timer.checked:
        return "not checked"
    return (
        f"enabled={report.timer.enabled}, active={report.timer.active}"
        + (f", load={report.timer.load_state}" if report.timer.load_state is not None else "")
        + (f", unit={report.timer.unit}" if report.timer.unit is not None else "")
        + (f", next={report.timer.next_elapse}" if report.timer.next_elapse is not None else "")
        + (f", error={report.timer.error}" if report.timer.error else "")
    )


def _release_gate_provider_state(report: SoakReport) -> str:
    if not report.provider.checked:
        return "not checked"
    return (
        f"expected={report.provider.expected_provider or 'any'}, "
        f"configured={report.provider.configured_provider or 'missing'}, "
        f"readiness={report.provider.readiness or 'unknown'}"
        + (f", checks={report.provider.checks}" if report.provider.checks else "")
        + (f", error={report.provider.error}" if report.provider.error else "")
    )


def render_release_gate_status(
    report: SoakReport,
    *,
    current_commit: str | None = None,
    current_dirty: bool | None = None,
) -> str:
    extra_reasons: list[str] = []
    if current_commit is None:
        extra_reasons.append("current git commit could not be detected")
    if current_dirty is True:
        extra_reasons.append("current git checkout is dirty")

    passed = report.passed and not extra_reasons
    lines = [
        "",
        "Stable release gate:",
        f"- Status: `{'ready' if passed else 'blocked'}`",
        f"- Current commit: `{current_commit or 'unknown'}`",
        f"- Current checkout dirty: `{str(current_dirty).lower() if current_dirty is not None else 'unknown'}`",
        f"- Window: `{report.since_hours}h`",
        f"- Required successful scheduled runs: `{report.min_successful}`",
        f"- Required run source: `{report.required_source or 'any'}`",
        f"- Required git commit: `{report.required_commit or 'any'}`",
        f"- Require clean checkout evidence: `{str(report.require_clean).lower()}`",
        f"- Gate-matching successful runs: `{len(report.gate_matched_successful_nightly_runs)}`",
        f"- Recent failed nightly runs: `{len(report.recent_failed_nightly_runs)}`",
        f"- Timer: `{_release_gate_timer_state(report)}`",
        f"- Timer provider: `{_release_gate_provider_state(report)}`",
    ]
    reasons = [*report.reasons, *extra_reasons]
    if reasons:
        lines.extend(["", "Stable blockers:"])
        for reason in reasons:
            lines.append(f"- {reason}")
    else:
        lines.extend(["", "Stable blockers:", "- none"])
    return "\n".join(lines)


def render_status(
    snapshot: StatusSnapshot,
    *,
    release_gate: SoakReport | None = None,
    current_commit: str | None = None,
    current_dirty: bool | None = None,
) -> str:
    lines = [
        "# Hermes Ershov status",
        "",
        f"Artifact root: {snapshot.artifact_root}",
        f"Artifacts: {snapshot.artifact_count} total",
    ]
    if snapshot.artifact_state_counts:
        artifact_state = ", ".join(f"{status}={count}" for status, count in snapshot.artifact_state_counts.items())
        lines.append(f"Artifact state: {artifact_state}")
    else:
        lines.append("Artifact state: none")

    lines.extend(
        [
            "",
            f"Run ledger: {snapshot.run_count} run(s), {snapshot.successful_run_count} successful",
            f"Last run: {_format_run(snapshot.last_run)}",
            f"Last successful run: {_format_run(snapshot.last_successful_run)}",
            f"Last nightly run: {_format_run(snapshot.last_nightly_run)}",
            f"Last successful nightly: {_format_run(snapshot.last_successful_nightly_run)}",
            f"Last failed nightly: {_format_run(snapshot.last_failed_nightly_run)}",
            "",
            "Memory usage:",
            f"- state.json: {snapshot.memory_usage['state']} B",
            f"- runs.jsonl: {snapshot.memory_usage['ledger']} B",
            f"- ERSHOV.md: {snapshot.memory_usage['diary']} B",
        ]
    )
    if release_gate is not None:
        lines.append(render_release_gate_status(release_gate, current_commit=current_commit, current_dirty=current_dirty))
    return "\n".join(lines) + "\n"

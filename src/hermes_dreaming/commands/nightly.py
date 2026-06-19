from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path

from ..analyze import DreamRunConfig, create_dream_artifact
from ..providers import MARKER_RE
from ..state import STATE_ROOT, record_run
from .compact import CompactResult, handle as compact_artifacts
from .digest import build_digest, build_inbox_digest, render_digest, render_inbox_digest
from .harvest import HarvestResult, harvest_recent

_OFFLINE_MARKER_PROVIDERS = {"offline", "offline-marker", "marker"}


@dataclass(slots=True)
class NightlyMemoryResult:
    live_root: Path
    artifact_root: Path
    archive_root: Path
    state_root: Path
    source_bundle: Path
    artifact_dir: Path | None
    artifact_id: str | None
    artifact_status: str
    proposal_count: int
    validation_errors: list[str]
    digest_path: Path
    inbox_digest_path: Path
    compact_result: CompactResult | None
    harvest_result: HarvestResult
    success: bool
    summary: str
    run_source: str


def _state_root(path: Path | None) -> Path:
    return Path(path) if path is not None else STATE_ROOT


def _source_bundle_path(artifact_root: Path) -> Path:
    return artifact_root / "_sources" / "nightly-recent-sessions.md"


def _inbox_digest_path(artifact_root: Path) -> Path:
    return artifact_root / "_digests" / "latest-inbox.md"


def _nightly_digest_path(artifact_root: Path) -> Path:
    return artifact_root / "_digests" / "latest-nightly.md"


def _uses_offline_marker_provider(provider_name: str) -> bool:
    return provider_name.strip().lower() in _OFFLINE_MARKER_PROVIDERS


def _has_offline_memory_markers(content: str) -> bool:
    return any(MARKER_RE.match(line) for line in content.splitlines())


def _run_source_from_env() -> str:
    value = os.environ.get("HERMES_ERSHOV_RUN_SOURCE", "manual")
    normalized = "".join(char if char.isalnum() or char in {"-", "_", "."} else "-" for char in value.strip().lower())
    return normalized[:64] or "manual"


def _write_noop_digest(*, path: Path, result: NightlyMemoryResult) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Hermes Ershov nightly no-op",
        "",
        f"- Status: `{result.artifact_status}`",
        f"- Success: `{str(result.success).lower()}`",
        f"- Sessions harvested: `{len(result.harvest_result.sessions)}`",
        f"- Redactions: `{result.harvest_result.redaction_count}`",
        f"- Proposals: `{result.proposal_count}`",
        f"- Source bundle: `{result.source_bundle}`",
        f"- Inbox digest: `{result.inbox_digest_path}`",
        "",
        "## Summary",
        "",
        f"- {result.summary}",
        "",
        "## Safety",
        "",
        "- No review artifact was created.",
        "- Live memory writes stayed disabled.",
        "- Apply still requires an explicit staged artifact, approval, and apply command.",
    ]
    if result.validation_errors:
        lines.extend(["", "## Validation errors", ""])
        for error in result.validation_errors:
            lines.append(f"- {error}")
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def _record_nightly_run(result: NightlyMemoryResult) -> None:
    record_run(
        {
            "command": "nightly",
            "success": result.success,
            "artifact_id": result.artifact_id,
            "artifact_status": result.artifact_status,
            "artifact_dir": str(result.artifact_dir) if result.artifact_dir is not None else None,
            "artifact_root": str(result.artifact_root),
            "live_root": str(result.live_root),
            "run_source": result.run_source,
            "summary": result.summary,
            "sessions": len(result.harvest_result.sessions),
            "redactions": result.harvest_result.redaction_count,
            "proposals": result.proposal_count,
            "digest_path": str(result.digest_path),
            "inbox_digest_path": str(result.inbox_digest_path),
            "compacted": len(result.compact_result.moved) if result.compact_result is not None else 0,
            "errors": list(result.validation_errors),
        },
        state_path=result.state_root / "state.json",
        ledger_path=result.state_root / "runs.jsonl",
        diary_path=result.state_root / "ERSHOV.md",
    )


def run_nightly_memory(
    *,
    live_root: Path,
    artifact_root: Path,
    archive_root: Path | None = None,
    state_root: Path | None = None,
    recent: int = 14,
    provider_name: str = "deepseek",
    model: str | None = "deepseek-v4-flash",
    base_url: str | None = "https://api.deepseek.com/v1",
    compact: bool = True,
    include_weekly: bool = True,
) -> NightlyMemoryResult:
    if recent <= 0:
        raise ValueError("recent must be greater than 0")

    live_root = Path(live_root)
    artifact_root = Path(artifact_root)
    archive_root = Path(archive_root) if archive_root is not None else artifact_root.parent / "archive"
    resolved_state_root = _state_root(state_root)
    run_source = _run_source_from_env()
    source_bundle = _source_bundle_path(artifact_root)

    harvest = harvest_recent(
        recent=recent,
        output_path=source_bundle,
        include_assistant=True,
    )
    inbox_path = _inbox_digest_path(artifact_root)

    if _uses_offline_marker_provider(provider_name) and not _has_offline_memory_markers(harvest.content):
        validation_errors = [] if live_root.exists() else [f"live root does not exist: {live_root}"]
        compact_result = compact_artifacts(artifact_root=artifact_root, archive_root=archive_root) if compact else None
        inbox_digest = build_inbox_digest(
            artifact_root,
            state_root=resolved_state_root,
        )
        inbox_text = render_inbox_digest(inbox_digest)
        inbox_path.parent.mkdir(parents=True, exist_ok=True)
        inbox_path.write_text(inbox_text, encoding="utf-8")

        success = not validation_errors
        summary = (
            "Nightly no-op: No eligible MEMORY/DREAM markers found for offline provider"
            if success
            else "nightly no-op preflight failed: " + "; ".join(validation_errors)
        )
        digest_path = _nightly_digest_path(artifact_root)
        result = NightlyMemoryResult(
            live_root=live_root,
            artifact_root=artifact_root,
            archive_root=archive_root,
            state_root=resolved_state_root,
            source_bundle=source_bundle,
            artifact_dir=None,
            artifact_id=None,
            artifact_status="no-op" if success else "invalid",
            proposal_count=0,
            validation_errors=validation_errors,
            digest_path=digest_path,
            inbox_digest_path=inbox_path,
            compact_result=compact_result,
            harvest_result=harvest,
            success=success,
            summary=summary,
            run_source=run_source,
        )
        _write_noop_digest(path=digest_path, result=result)
        _record_nightly_run(result)
        return result

    creation = create_dream_artifact(
        DreamRunConfig(
            live_root=live_root,
            artifact_root=artifact_root,
            source_paths=[source_bundle],
            provider_name=provider_name,
            model=model,
            api_key=None,
            base_url=base_url,
        )
    )

    digest = build_digest(
        creation.artifact_dir,
        artifact_root=artifact_root,
        state_root=resolved_state_root,
        include_weekly=include_weekly,
    )
    digest_text = render_digest(digest)
    digest_path = creation.artifact_dir / "NIGHTLY.md"
    digest_path.write_text(digest_text, encoding="utf-8")

    compact_result = compact_artifacts(artifact_root=artifact_root, archive_root=archive_root) if compact else None

    inbox_digest = build_inbox_digest(
        artifact_root,
        state_root=resolved_state_root,
    )
    inbox_text = render_inbox_digest(inbox_digest)
    inbox_path.parent.mkdir(parents=True, exist_ok=True)
    inbox_path.write_text(inbox_text, encoding="utf-8")

    success = not creation.validation_errors and creation.artifact.status != "invalid"
    summary = (
        f"nightly staged {len(creation.artifact.proposals)} proposal(s) "
        f"from {len(harvest.sessions)} session(s)"
        if success
        else "nightly staged invalid artifact: " + "; ".join(creation.validation_errors or ["unknown validation failure"])
    )
    result = NightlyMemoryResult(
        live_root=live_root,
        artifact_root=artifact_root,
        archive_root=archive_root,
        state_root=resolved_state_root,
        source_bundle=source_bundle,
        artifact_dir=creation.artifact_dir,
        artifact_id=creation.artifact.artifact_id,
        artifact_status=creation.artifact.status,
        proposal_count=len(creation.artifact.proposals),
        validation_errors=list(creation.validation_errors),
        digest_path=digest_path,
        inbox_digest_path=inbox_path,
        compact_result=compact_result,
        harvest_result=harvest,
        success=success,
        summary=summary,
        run_source=run_source,
    )
    _record_nightly_run(result)
    return result


def render_nightly_memory(result: NightlyMemoryResult) -> str:
    compacted = len(result.compact_result.moved) if result.compact_result is not None else 0
    lines = [
        "# Hermes Ershov nightly memory",
        "",
        f"- Artifact: `{result.artifact_id or 'none'}`",
        f"- Status: `{result.artifact_status}`",
        f"- Success: `{str(result.success).lower()}`",
        f"- Live root: `{result.live_root}`",
        f"- Artifact root: `{result.artifact_root}`",
        f"- Source bundle: `{result.source_bundle}`",
        f"- Run source: `{result.run_source}`",
        f"- Digest: `{result.digest_path}`",
        f"- Inbox digest: `{result.inbox_digest_path}`",
        f"- Sessions harvested: `{len(result.harvest_result.sessions)}`",
        f"- Redactions: `{result.harvest_result.redaction_count}`",
        f"- Proposals: `{result.proposal_count}`",
        f"- Compacted terminal artifacts: `{compacted}`",
        "",
        "## Safety",
        "",
        "- Live memory writes: disabled.",
        "- Apply requires explicit `ershov approve` / `ershov apply`.",
        "- Provider keys are read from the runtime environment, not persisted in the nightly script.",
    ]
    if result.artifact_dir is None:
        lines.extend(
            [
                "",
                "## No-op",
                "",
                f"- {result.summary}",
                "",
                "## Next",
                "",
                f"- Inbox: `ershov inbox --artifact-root {result.artifact_root}`",
            ]
        )
    else:
        lines.extend(
            [
                "",
                "## Next",
                "",
                f"- Review: `ershov summarize {result.artifact_dir}`",
                f"- Inbox: `ershov inbox --artifact-root {result.artifact_root}`",
            ]
        )
    if result.validation_errors:
        lines.extend(["", "## Validation errors", ""])
        for error in result.validation_errors:
            lines.append(f"- {error}")
    return "\n".join(lines).rstrip() + "\n"

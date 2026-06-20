from __future__ import annotations

"""
Apply Hermes Ershov memory operations with threshold gating and backups.

This stays deliberately small: validate the proposal, skip idempotent repeats,
create a backup before a live write, verify the write, and record the result.
"""

import fcntl
import hashlib
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from .. import memory_io as mio
from .. import state as state_module
from ..policy import evaluate_live_op
from ..scoring import ProposedOp, thresholds_for_prompt, validate_op
from ..validation import validate_memory_op

SCHEMA = {
    "name": "ershov_apply_memory_op",
    "description": (
        "Propose or apply a durable memory operation (add / replace / remove). "
        "In dry-run mode this records the proposal without touching MEMORY.md or USER.md. "
        "In live mode this mutates the file after validating score thresholds, safety checks, "
        "and idempotence."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "op": {
                "type": "string",
                "enum": ["add", "replace", "remove"],
                "description": "Memory operation to perform.",
            },
            "target": {
                "type": "string",
                "enum": ["memory", "user"],
                "description": "Which file to modify: 'memory' or 'user'.",
            },
            "old_text": {
                "type": "string",
                "description": "Exact existing bullet entry to replace or remove.",
            },
            "new_text": {
                "type": "string",
                "description": "New memory entry text. Required for add and replace.",
            },
            "reason": {
                "type": "string",
                "description": "One sentence explaining why this operation is warranted.",
            },
            "sources": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Session IDs or turn references that ground this operation.",
            },
            "score": {
                "type": "number",
                "description": "Composite future-usefulness score (0.0–1.0) from REM scoring.",
            },
            "supersession_confidence": {
                "type": "number",
                "description": "Confidence that old_text is truly superseded or obsolete (0.0–1.0).",
            },
            "dry_run": {
                "type": "boolean",
                "description": "If true, do not mutate the live file.",
            },
        },
        "required": ["op", "target", "reason", "sources", "score"],
    },
}


def _content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def _op_hash(op: str, target: str, old_text: str | None, new_text: str | None) -> str:
    sig = f"{op}:{target}:{old_text or ''}:{new_text or ''}"
    return _content_hash(sig)


def _default_live_root() -> Path:
    return Path.home() / ".hermes" / "ershov"


def _coerce_sources(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value]
    return [str(value)]


def _coerce_float(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


@contextmanager
def _exclusive_lock(lock_path: Path):
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _preview(op: ProposedOp, raw: str, path: Path):
    if op.op == "add":
        return mio.preview_add(raw, op.new_text or "")
    if op.op == "replace":
        return mio.preview_replace(raw, path, op.old_text or "", op.new_text or "")
    if op.op == "remove":
        return mio.preview_remove(raw, path, op.old_text or "")
    return mio.MutationResult(ok=False, error=f"unknown op: {op.op!r}")


def _record_live_run(
    *,
    success: bool,
    command: str,
    hash_value: str,
    target: str,
    live_root: Path,
    backup_root: Path,
    path: Path,
    summary: str,
    error: str | None = None,
    char_delta: int | None = None,
) -> None:
    record: dict[str, Any] = {
        "command": command,
        "success": success,
        "summary": summary,
        "live_root": str(live_root),
        "backup_root": str(backup_root),
        "target": target,
        "path": str(path),
        "hash": hash_value,
    }
    if char_delta is not None:
        record["char_delta"] = char_delta
    if error:
        record["errors"] = [error]
    try:
        state_module.record_run(record)
    except Exception:
        # State/ledger bookkeeping must never clobber the live memory mutation.
        return


def _live_validation_errors(
    *,
    op_str: str,
    target: str,
    old_text: str | None,
    new_text: str | None,
    reason: str,
    sources: list[str],
    score: float,
    supersession_confidence: float,
) -> list[str]:
    errors = validate_memory_op(
        op=op_str,
        target=target,
        old_text=old_text,
        new_text=new_text,
        reason=reason,
        sources=sources,
        score=score,
        supersession_confidence=supersession_confidence,
    )
    proposed = ProposedOp(
        op=op_str,  # type: ignore[arg-type]
        target=target,  # type: ignore[arg-type]
        old_text=old_text,
        new_text=new_text,
        reason=reason,
        sources=sources,
        score=score,
        supersession_confidence=supersession_confidence,
    )
    scoring = validate_op(proposed)
    if not scoring.ok:
        errors.append(scoring.error)
    return errors


def handler(params: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
    live_root = Path(kwargs.get("live_root") or params.get("live_root") or _default_live_root())
    backup_root = Path(kwargs.get("backup_root") or params.get("backup_root") or mio.BACKUPS_DIR)
    dry_run = bool(params.get("dry_run", True))

    op_str = str(params.get("op", ""))
    target = str(params.get("target", ""))
    old_text = params.get("old_text") or None
    new_text = params.get("new_text") or None
    reason = str(params.get("reason", ""))
    sources = _coerce_sources(params.get("sources"))
    score = _coerce_float(params.get("score"), 0.0)
    supersession_confidence = _coerce_float(params.get("supersession_confidence"), 0.0)

    if target not in ("memory", "user"):
        return {
            "applied": False,
            "dry_run": dry_run,
            "error": f"unknown target: {target!r}. Use 'memory' or 'user'.",
        }

    validation_errors = _live_validation_errors(
        op_str=op_str,
        target=target,
        old_text=old_text,
        new_text=new_text,
        reason=reason,
        sources=sources,
        score=score,
        supersession_confidence=supersession_confidence,
    )
    if validation_errors:
        return {
            "applied": False,
            "dry_run": dry_run,
            "error": f"unsafe live memory op: {validation_errors[0]}",
            "validation_errors": validation_errors,
            "thresholds": thresholds_for_prompt(),
        }

    proposed = ProposedOp(
        op=op_str,  # type: ignore[arg-type]
        target=target,  # type: ignore[arg-type]
        old_text=old_text,
        new_text=new_text,
        reason=reason,
        sources=sources,
        score=score,
        supersession_confidence=supersession_confidence,
    )

    live_policy = evaluate_live_op(
        op=op_str,
        target=target,
        old_text=old_text,
        new_text=new_text,
        reason=reason,
        sources=sources,
    )
    op_hash = live_policy.idempotence_key or _op_hash(op_str, target, old_text, new_text)
    if dry_run:
        return {
            "applied": False,
            "dry_run": True,
            "proposed": True,
            "op": op_str,
            "target": target,
            "old_text": old_text,
            "new_text": new_text,
            "score": score,
            "reason": reason,
            "hash": op_hash,
        }

    lock_path = backup_root / ".memory_mutations.lock"
    with _exclusive_lock(lock_path):
        path = mio.resolve_target_path(live_root, target)
        raw = path.read_text(encoding="utf-8") if path.exists() else ""
        preview = _preview(proposed, raw, path)
        if not preview.ok:
            return {
                "applied": False,
                "dry_run": False,
                "error": preview.error,
                "hash": op_hash,
            }

        if preview.new_text == raw:
            return {
                "applied": False,
                "dry_run": False,
                "skipped": True,
                "reason": "idempotent duplicate mutation",
                "hash": op_hash,
            }

        # Capacity gate — never let a live write push a file past its size cap.
        _limit_path, capacity_limit = mio._target_info(target)
        if len(preview.new_text) > capacity_limit:
            return {
                "applied": False,
                "dry_run": False,
                "error": (
                    f"capacity gate: {target.upper()}.md would reach "
                    f"{len(preview.new_text)} chars (limit {capacity_limit})"
                ),
                "hash": op_hash,
            }

        backup_path = mio.backup_target(path, backup_root, target=target)
        try:
            if proposed.op == "add":
                result = mio.apply_add(path, proposed.new_text or "")
            elif proposed.op == "replace":
                result = mio.apply_replace(path, proposed.old_text or "", proposed.new_text or "")
            elif proposed.op == "remove":
                result = mio.apply_remove(path, proposed.old_text or "")
            else:
                return {"applied": False, "error": f"unknown op: {proposed.op!r}", "hash": op_hash}

            if not result.ok:
                raise RuntimeError(result.error or "mutation failed")

            actual = path.read_text(encoding="utf-8") if path.exists() else ""
            if actual != result.new_text:
                raise RuntimeError(f"verification failed after writing {path.name}")

        except Exception as exc:
            rollback_error = None
            try:
                mio.restore_target(path, backup_root, target=target)
            except Exception as restore_exc:  # pragma: no cover - hard failure path
                rollback_error = f"rollback failed: {restore_exc}"

            _record_live_run(
                success=False,
                command="apply_memory_op",
                hash_value=op_hash,
                target=target,
                live_root=live_root,
                backup_root=backup_root,
                path=path,
                summary=f"live memory {proposed.op} failed",
                error=f"{exc}{'; ' + rollback_error if rollback_error else ''}",
            )
            return {
                "applied": False,
                "dry_run": False,
                "error": f"{exc}{'; ' + rollback_error if rollback_error else ''}",
                "hash": op_hash,
                "backup_path": str(backup_path),
            }

        _record_live_run(
            success=True,
            command="apply_memory_op",
            hash_value=op_hash,
            target=target,
            live_root=live_root,
            backup_root=backup_root,
            path=path,
            summary=f"live memory {proposed.op} applied",
            char_delta=result.char_delta,
        )
        return {
            "applied": True,
            "dry_run": False,
            "op": proposed.op,
            "target": proposed.target,
            "old_text": proposed.old_text,
            "new_text": proposed.new_text,
            "score": proposed.score,
            "reason": proposed.reason,
            "char_delta": result.char_delta,
            "hash": op_hash,
            "backup_path": str(backup_path),
        }


def apply_memory_op(params: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
    """Alias for handler(), kept for call sites that want a descriptive name."""
    return handler(params, **kwargs)

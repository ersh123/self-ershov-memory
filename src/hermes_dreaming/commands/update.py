from __future__ import annotations

from dataclasses import dataclass
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

DEFAULT_REMOTE = "origin"
DEFAULT_BRANCH = "main"
DEFAULT_GIT_TIMEOUT_SECONDS = 120
DEFAULT_FETCH_RETRIES = 1
TRANSIENT_GIT_ERROR_MARKERS = (
    "timed out after",
    "connection timed out",
    "operation timed out",
    "failed to connect",
    "couldn't connect",
    "could not resolve host",
    "the network connection was lost",
    "gnutls recv error",
)


@dataclass(slots=True)
class UpdateResult:
    success: bool
    repo_root: Path
    remote: str
    branch: str
    current_rev: str
    upstream_rev: str | None
    behind: int
    ahead: int
    dirty: bool
    checked_only: bool
    updated: bool
    verified: bool
    message: str


def _discover_repo_root(start: Path | None = None) -> Path:
    if start is not None:
        candidate = Path(start).resolve()
        return candidate if candidate.is_dir() else candidate.parent

    candidate = Path(__file__).resolve()
    for path in [candidate, *candidate.parents]:
        if (path / "pyproject.toml").exists() and (path / "plugin.yaml").exists():
            return path
    raise RuntimeError("Could not locate the Hermes Ershov repository root.")


def _run_git(
    args: list[str],
    *,
    cwd: Path,
    timeout_seconds: int = DEFAULT_GIT_TIMEOUT_SECONDS,
) -> subprocess.CompletedProcess[str]:
    command = ["git", *args]
    try:
        proc = subprocess.run(command, cwd=cwd, text=True, capture_output=True, timeout=timeout_seconds)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"{' '.join(command)} timed out after {timeout_seconds}s") from exc
    if proc.returncode != 0:
        details = proc.stderr.strip() or proc.stdout.strip() or f"git {' '.join(args)} failed"
        raise RuntimeError(details)
    return proc


def _git_output(args: list[str], *, cwd: Path, timeout_seconds: int = DEFAULT_GIT_TIMEOUT_SECONDS) -> str:
    return _run_git(args, cwd=cwd, timeout_seconds=timeout_seconds).stdout.strip()


def _is_transient_git_error(error: RuntimeError) -> bool:
    text = str(error).lower()
    return any(marker in text for marker in TRANSIENT_GIT_ERROR_MARKERS)


def _run_git_retrying_transient(
    args: list[str],
    *,
    cwd: Path,
    timeout_seconds: int = DEFAULT_GIT_TIMEOUT_SECONDS,
    retries: int = DEFAULT_FETCH_RETRIES,
) -> subprocess.CompletedProcess[str]:
    attempts = max(0, retries) + 1
    last_error: RuntimeError | None = None
    for attempt in range(attempts):
        try:
            return _run_git(args, cwd=cwd, timeout_seconds=timeout_seconds)
        except RuntimeError as exc:
            last_error = exc
            if not _is_transient_git_error(exc) or attempt == attempts - 1:
                raise
    if last_error is not None:  # pragma: no cover - loop either returns or raises.
        raise last_error
    raise RuntimeError("git retry loop exited without result")  # pragma: no cover


def _fetch_remote(
    *,
    cwd: Path,
    remote: str,
    timeout_seconds: int = DEFAULT_GIT_TIMEOUT_SECONDS,
    retries: int = DEFAULT_FETCH_RETRIES,
) -> None:
    _run_git_retrying_transient(
        ["fetch", "--prune", remote],
        cwd=cwd,
        timeout_seconds=timeout_seconds,
        retries=retries,
    )


def _verification_command(repo_root: Path, *, cache_dir: Path) -> list[str]:
    pytest_args = ["-m", "pytest", "-q", "-o", f"cache_dir={cache_dir}"]
    if (repo_root / "pyproject.toml").exists() and shutil.which("uv"):
        return [
            "uv",
            "run",
            "--no-project",
            "--with-editable",
            ".",
            "--with",
            "pytest",
            "--with",
            "hypothesis",
            "python",
            *pytest_args,
        ]
    return [sys.executable, *pytest_args]


def _format_update_report(result: UpdateResult) -> str:
    lines = ["# Hermes Ershov update", ""]
    lines.extend(
        [
            f"- Repo: `{result.repo_root}`",
            f"- Remote: `{result.remote}`",
            f"- Branch: `{result.branch}`",
            f"- Current: `{result.current_rev[:7]}`",
        ]
    )
    if result.upstream_rev:
        lines.append(f"- Upstream: `{result.upstream_rev[:7]}`")
    lines.extend(
        [
            f"- Ahead: `{result.ahead}`",
            f"- Behind: `{result.behind}`",
            f"- Dirty: `{result.dirty}`",
            f"- Mode: `{ 'check' if result.checked_only else 'update' }`",
            f"- Updated: `{result.updated}`",
            f"- Verified: `{result.verified}`",
            f"- Status: `{ 'ok' if result.success else 'failed' }`",
            "",
            result.message,
            "",
        ]
    )
    return "\n".join(lines)


def handle(
    *,
    repo_root: Path | None = None,
    remote: str = DEFAULT_REMOTE,
    branch: str = DEFAULT_BRANCH,
    check: bool = False,
    verify: bool = True,
    git_timeout_seconds: int = DEFAULT_GIT_TIMEOUT_SECONDS,
) -> UpdateResult:
    repo_root = _discover_repo_root(repo_root)
    if git_timeout_seconds <= 0:
        return UpdateResult(
            success=False,
            repo_root=repo_root,
            remote=remote,
            branch=branch,
            current_rev="unknown",
            upstream_rev=None,
            behind=0,
            ahead=0,
            dirty=False,
            checked_only=check,
            updated=False,
            verified=False,
            message="git-timeout-seconds must be greater than 0.",
        )

    try:
        current_rev = _git_output(["rev-parse", "HEAD"], cwd=repo_root, timeout_seconds=git_timeout_seconds)
        dirty = bool(_git_output(["status", "--porcelain"], cwd=repo_root, timeout_seconds=git_timeout_seconds))
    except Exception as exc:
        return UpdateResult(
            success=False,
            repo_root=repo_root,
            remote=remote,
            branch=branch,
            current_rev="unknown",
            upstream_rev=None,
            behind=0,
            ahead=0,
            dirty=False,
            checked_only=check,
            updated=False,
            verified=False,
            message=f"Could not inspect repository state: {exc}",
        )

    if dirty:
        return UpdateResult(
            success=False,
            repo_root=repo_root,
            remote=remote,
            branch=branch,
            current_rev=current_rev,
            upstream_rev=None,
            behind=0,
            ahead=0,
            dirty=True,
            checked_only=check,
            updated=False,
            verified=False,
            message="Working tree is dirty. Commit or stash your changes before updating.",
        )

    try:
        _fetch_remote(cwd=repo_root, remote=remote, timeout_seconds=git_timeout_seconds)
        upstream_ref = f"{remote}/{branch}"
        upstream_rev = _git_output(["rev-parse", upstream_ref], cwd=repo_root, timeout_seconds=git_timeout_seconds)
        ahead_text = _git_output(
            ["rev-list", "--left-right", "--count", f"HEAD...{upstream_ref}"],
            cwd=repo_root,
            timeout_seconds=git_timeout_seconds,
        )
        ahead, behind = (int(part) for part in ahead_text.split())
    except Exception as exc:
        return UpdateResult(
            success=False,
            repo_root=repo_root,
            remote=remote,
            branch=branch,
            current_rev=current_rev,
            upstream_rev=None,
            behind=0,
            ahead=0,
            dirty=False,
            checked_only=check,
            updated=False,
            verified=False,
            message=f"Could not inspect update status: {exc}",
        )

    if ahead > 0 and behind > 0:
        return UpdateResult(
            success=False,
            repo_root=repo_root,
            remote=remote,
            branch=branch,
            current_rev=current_rev,
            upstream_rev=upstream_rev,
            behind=behind,
            ahead=ahead,
            dirty=False,
            checked_only=check,
            updated=False,
            verified=False,
            message=(
                f"Local branch has diverged from {remote}/{branch} ({ahead} ahead, {behind} behind). "
                "Refusing to update automatically."
            ),
        )

    if ahead > 0:
        return UpdateResult(
            success=False,
            repo_root=repo_root,
            remote=remote,
            branch=branch,
            current_rev=current_rev,
            upstream_rev=upstream_rev,
            behind=behind,
            ahead=ahead,
            dirty=False,
            checked_only=check,
            updated=False,
            verified=False,
            message=(
                f"Local branch has {ahead} commit(s) ahead of {remote}/{branch}. "
                "Refusing to overwrite local commits."
            ),
        )

    if behind == 0:
        return UpdateResult(
            success=True,
            repo_root=repo_root,
            remote=remote,
            branch=branch,
            current_rev=current_rev,
            upstream_rev=upstream_rev,
            behind=behind,
            ahead=ahead,
            dirty=False,
            checked_only=check,
            updated=False,
            verified=False,
            message="Already up to date.",
        )

    if check:
        return UpdateResult(
            success=True,
            repo_root=repo_root,
            remote=remote,
            branch=branch,
            current_rev=current_rev,
            upstream_rev=upstream_rev,
            behind=behind,
            ahead=ahead,
            dirty=False,
            checked_only=True,
            updated=False,
            verified=False,
            message=f"Update available: {behind} commit(s) behind {remote}/{branch}.",
        )

    pre_update_rev = current_rev
    try:
        _run_git_retrying_transient(
            ["pull", "--ff-only", remote, branch],
            cwd=repo_root,
            timeout_seconds=git_timeout_seconds,
        )
        updated_rev = _git_output(["rev-parse", "HEAD"], cwd=repo_root, timeout_seconds=git_timeout_seconds)
        upstream_rev = _git_output(["rev-parse", upstream_ref], cwd=repo_root, timeout_seconds=git_timeout_seconds)
        refreshed_counts = _git_output(
            ["rev-list", "--left-right", "--count", f"HEAD...{upstream_ref}"],
            cwd=repo_root,
            timeout_seconds=git_timeout_seconds,
        )
        ahead, behind = (int(part) for part in refreshed_counts.split())
        dirty = bool(_git_output(["status", "--porcelain"], cwd=repo_root, timeout_seconds=git_timeout_seconds))
    except Exception as exc:
        return UpdateResult(
            success=False,
            repo_root=repo_root,
            remote=remote,
            branch=branch,
            current_rev=current_rev,
            upstream_rev=upstream_rev,
            behind=behind,
            ahead=ahead,
            dirty=False,
            checked_only=False,
            updated=False,
            verified=False,
            message=f"Update failed: {exc}",
        )

    verified = False
    if verify:
        env = os.environ.copy()
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        with tempfile.TemporaryDirectory(prefix="hermes-ershov-update-pytest-cache-") as cache_dir:
            verify_command = _verification_command(repo_root, cache_dir=Path(cache_dir))
            verify_proc = subprocess.run(
                verify_command,
                cwd=repo_root,
                text=True,
                capture_output=True,
                env=env,
            )
        if verify_proc.returncode != 0:
            rollback_error: str | None = None
            try:
                _run_git(["reset", "--hard", pre_update_rev], cwd=repo_root, timeout_seconds=git_timeout_seconds)
            except Exception as rollback_exc:
                rollback_error = str(rollback_exc)
            stderr = (verify_proc.stderr or "").strip()
            stdout = (verify_proc.stdout or "").strip()
            verify_bits = ["Post-update verification failed. The repo was rolled back to the previous commit."]
            if stdout:
                verify_bits.append(stdout)
            if stderr:
                verify_bits.append(stderr)
            if rollback_error:
                verify_bits.append(f"Rollback error: {rollback_error}")
            return UpdateResult(
                success=False,
                repo_root=repo_root,
                remote=remote,
                branch=branch,
                current_rev=pre_update_rev,
                upstream_rev=upstream_rev,
                behind=behind,
                ahead=ahead,
                dirty=False,
                checked_only=False,
                updated=False,
                verified=False,
                message="\n".join(verify_bits),
            )
        verified = True

    return UpdateResult(
        success=True,
        repo_root=repo_root,
        remote=remote,
        branch=branch,
        current_rev=updated_rev,
        upstream_rev=upstream_rev,
        behind=behind,
        ahead=ahead,
        dirty=dirty,
        checked_only=False,
        updated=True,
        verified=verified,
        message=f"Updated from {pre_update_rev[:7]} to {updated_rev[:7]} successfully.",
    )


__all__ = ["DEFAULT_BRANCH", "DEFAULT_REMOTE", "UpdateResult", "handle", "render_update_result"]


def render_update_result(result: UpdateResult) -> str:
    return _format_update_report(result)

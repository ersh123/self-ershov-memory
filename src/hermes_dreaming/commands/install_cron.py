from __future__ import annotations

import textwrap
from pathlib import Path

try:
    from hermes_constants import get_hermes_home  # type: ignore
except Exception:  # pragma: no cover - fallback for direct source inspection
    def get_hermes_home() -> Path:
        return Path.home() / ".hermes"

JOB_NAME = "hermes-ershov"
DEFAULT_SCHEDULE = "0 3 * * *"
SCRIPT_NAME = "hermes_ershov_status_digest.py"
NIGHTLY_REVIEW_SCRIPT_NAME = "hermes_ershov_nightly.py"
_PROMPT = "Hermes Ershov daily digest"
_INBOX_PROMPT = "Hermes Ershov inbox digest"
_REVIEW_PROMPT = "Hermes Ershov nightly memory"


_DIGEST_SCRIPT_TEMPLATE = textwrap.dedent(
    '''
    #!/usr/bin/env python3
    from __future__ import annotations

    import json
    import os
    import subprocess
    from pathlib import Path

    REPO_ROOT = Path(__REPO_ROOT__)


    def _read_json(path: Path) -> dict:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}


    def _read_jsonl(path: Path) -> list[dict]:
        rows: list[dict] = []
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                entry = line.strip()
                if not entry:
                    continue
                try:
                    parsed = json.loads(entry)
                except Exception:
                    continue
                if isinstance(parsed, dict):
                    rows.append(parsed)
        except Exception:
            return []
        return rows


    def _git_status(repo_root: Path) -> list[str]:
        try:
            result = subprocess.run(
                ["git", "-C", str(repo_root), "status", "--short", "--branch"],
                capture_output=True,
                text=True,
                check=False,
            )
        except Exception as exc:
            return [f"git unavailable: {exc}"]

        output = (result.stdout or "").strip()
        if not output:
            return ["clean"]
        return output.splitlines()


    def _artifact_summary(artifact_root: Path) -> tuple[dict[str, int], list[str]]:
        counts: dict[str, int] = {}
        latest: list[tuple[float, str]] = []
        if not artifact_root.exists():
            return counts, []

        for manifest in sorted(artifact_root.glob("*/manifest.json")):
            try:
                data = json.loads(manifest.read_text(encoding="utf-8"))
            except Exception:
                data = {}
            status = str(data.get("status") or "unknown")
            counts[status] = counts.get(status, 0) + 1
            artifact_id = str(data.get("artifact_id") or manifest.parent.name)
            try:
                stamp = manifest.stat().st_mtime
            except OSError:
                stamp = 0.0
            latest.append((stamp, f"{artifact_id} [{status}]"))

        latest.sort(key=lambda item: item[0], reverse=True)
        return counts, [item[1] for item in latest[:3]]


    def _format_run(record: dict | None) -> str:
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


    def main() -> int:
        state_root = Path(
            os.environ.get(
                "HERMES_ERSHOV_STATE_ROOT",
                os.environ.get(
                    "HERMES_MNEMOS_STATE_ROOT",
                    os.environ.get(
                        "HERMES_NIGHT_MEMORY_STATE_ROOT",
                        os.environ.get("HERMES_DREAMING_STATE_ROOT", str(Path.home() / ".hermes" / "ershov")),
                    ),
                ),
            )
        )
        artifact_root = REPO_ROOT / ".ershov" / "artifacts"
        state = _read_json(state_root / "state.json")
        runs = _read_jsonl(state_root / "runs.jsonl")
        git_lines = _git_status(REPO_ROOT)
        artifact_counts, latest_artifacts = _artifact_summary(artifact_root)

        successful_runs = state.get("successful_run_count")
        if not isinstance(successful_runs, int):
            successful_runs = sum(1 for record in runs if record.get("success"))
        run_count = state.get("run_count")
        if not isinstance(run_count, int):
            run_count = len(runs)

        last_run = state.get("last_run") if isinstance(state.get("last_run"), dict) else None
        if last_run is None and runs:
            last_run = runs[-1]
        last_successful_run = state.get("last_successful_run") if isinstance(state.get("last_successful_run"), dict) else None
        if last_successful_run is None:
            for record in reversed(runs):
                if record.get("success"):
                    last_successful_run = record
                    break

        print("## Hermes Ershov daily digest")
        print("")
        print(f"- Repo: `{REPO_ROOT}`")
        print(f"- Artifact root: `{artifact_root}`")
        print(f"- State root: `{state_root}`")
        print("")
        print("## Git status")
        print("")
        for line in git_lines:
            print(f"- `{line}`")
        print("")
        print("## Ershov runtime")
        print("")
        print(f"- Runs: `{run_count}` total, `{successful_runs}` successful")
        print(f"- Last run: `{_format_run(last_run)}`")
        print(f"- Last successful run: `{_format_run(last_successful_run)}`")
        print(f"- Ledger bytes: `{(state_root / 'runs.jsonl').stat().st_size if (state_root / 'runs.jsonl').exists() else 0}`")
        print(f"- Diary bytes: `{(state_root / 'ERSHOV.md').stat().st_size if (state_root / 'ERSHOV.md').exists() else 0}`")
        print("")
        print("## Staged artifacts")
        print("")
        if not artifact_root.exists():
            print("- No `.ershov/artifacts` directory under the repo root.")
        elif not artifact_counts:
            print("- No artifacts staged yet.")
        else:
            for status, count in sorted(artifact_counts.items()):
                print(f"- {status}: `{count}`")
            if latest_artifacts:
                print("")
                print("### Latest artifacts")
                print("")
                for item in latest_artifacts:
                    print(f"- `{item}`")
        return 0


    if __name__ == "__main__":
        raise SystemExit(main())
    '''
).lstrip()


_INBOX_DIGEST_SCRIPT_TEMPLATE = textwrap.dedent(
    '''
    #!/usr/bin/env python3
    from __future__ import annotations

    import subprocess
    import sys
    from pathlib import Path

    REPO_ROOT = Path(__REPO_ROOT__)

    def main() -> int:
        cmd = [sys.executable, "-m", "hermes_ershov", "digest", "--inbox", "--artifact-root", str(REPO_ROOT / ".ershov" / "artifacts")]
        result = subprocess.run(cmd, cwd=str(REPO_ROOT), text=True, capture_output=True, check=False)
        if result.stdout:
            print(result.stdout.rstrip())
        if result.returncode != 0 and result.stderr:
            print(result.stderr.rstrip())
        return result.returncode

    if __name__ == "__main__":
        raise SystemExit(main())
    '''
).lstrip()


_NIGHTLY_REVIEW_SCRIPT_TEMPLATE = textwrap.dedent(
    '''
    #!/usr/bin/env python3
    from __future__ import annotations

    import os
    import subprocess
    import sys
    from pathlib import Path

    REPO_ROOT = Path(__REPO_ROOT__)
    DEFAULT_LIVE_ROOT = Path(__LIVE_ROOT__)
    DEFAULT_ARTIFACT_ROOT = Path(__ARTIFACT_ROOT__)
    DEFAULT_ARCHIVE_ROOT = Path(__ARCHIVE_ROOT__)
    DEFAULT_STATE_ROOT = Path(__STATE_ROOT__)
    DEFAULT_PROVIDER = __PROVIDER__
    DEFAULT_MODEL = __MODEL__
    DEFAULT_BASE_URL = __BASE_URL__
    DEFAULT_RECENT = __RECENT__
    DEFAULT_RUN_SOURCE = __RUN_SOURCE__


    def _positive_int(name: str, default: int) -> int:
        value = os.environ.get(name)
        if not value:
            return default
        try:
            parsed = int(value)
        except ValueError:
            return default
        return parsed if parsed > 0 else default


    def main() -> int:
        live_root = Path(os.environ.get("HERMES_ERSHOV_LIVE_ROOT", os.environ.get("HERMES_MNEMOS_LIVE_ROOT", os.environ.get("HERMES_NIGHT_MEMORY_LIVE_ROOT", os.environ.get("HERMES_DREAMING_LIVE_ROOT", str(DEFAULT_LIVE_ROOT))))))
        artifact_root = Path(os.environ.get("HERMES_ERSHOV_ARTIFACT_ROOT", os.environ.get("HERMES_MNEMOS_ARTIFACT_ROOT", os.environ.get("HERMES_NIGHT_MEMORY_ARTIFACT_ROOT", os.environ.get("HERMES_DREAMING_ARTIFACT_ROOT", str(DEFAULT_ARTIFACT_ROOT))))))
        archive_root = Path(os.environ.get("HERMES_ERSHOV_ARCHIVE_ROOT", os.environ.get("HERMES_MNEMOS_ARCHIVE_ROOT", os.environ.get("HERMES_NIGHT_MEMORY_ARCHIVE_ROOT", os.environ.get("HERMES_DREAMING_ARCHIVE_ROOT", str(DEFAULT_ARCHIVE_ROOT))))))
        state_root = Path(os.environ.get("HERMES_ERSHOV_STATE_ROOT", os.environ.get("HERMES_MNEMOS_STATE_ROOT", os.environ.get("HERMES_NIGHT_MEMORY_STATE_ROOT", os.environ.get("HERMES_DREAMING_STATE_ROOT", str(DEFAULT_STATE_ROOT))))))
        provider = os.environ.get("HERMES_ERSHOV_PROVIDER", os.environ.get("HERMES_MNEMOS_PROVIDER", os.environ.get("HERMES_NIGHT_MEMORY_PROVIDER", os.environ.get("HERMES_DREAMING_PROVIDER", DEFAULT_PROVIDER))))
        model = os.environ.get("HERMES_ERSHOV_MODEL", os.environ.get("HERMES_MNEMOS_MODEL", os.environ.get("HERMES_NIGHT_MEMORY_MODEL", os.environ.get("HERMES_DREAMING_MODEL", DEFAULT_MODEL))))
        base_url = os.environ.get("HERMES_ERSHOV_BASE_URL", os.environ.get("HERMES_MNEMOS_BASE_URL", os.environ.get("HERMES_NIGHT_MEMORY_BASE_URL", os.environ.get("HERMES_DREAMING_BASE_URL", DEFAULT_BASE_URL))))
        recent = _positive_int("HERMES_ERSHOV_RECENT_SESSIONS", _positive_int("HERMES_MNEMOS_RECENT_SESSIONS", _positive_int("HERMES_NIGHT_MEMORY_RECENT_SESSIONS", _positive_int("HERMES_DREAMING_RECENT_SESSIONS", DEFAULT_RECENT))))
        run_source = os.environ.get("HERMES_ERSHOV_RUN_SOURCE", DEFAULT_RUN_SOURCE)

        cmd = [
            sys.executable,
            "-m",
            "hermes_ershov",
            "nightly",
            "--recent",
            str(recent),
            "--live-root",
            str(live_root),
            "--artifact-root",
            str(artifact_root),
            "--archive-root",
            str(archive_root),
            "--state-root",
            str(state_root),
            "--provider",
            provider,
        ]
        if model:
            cmd.extend(["--model", model])
        if base_url:
            cmd.extend(["--base-url", base_url])

        env = os.environ.copy()
        env["HERMES_ERSHOV_RUN_SOURCE"] = run_source
        src_path = str(REPO_ROOT / "src")
        env["PYTHONPATH"] = src_path + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")

        print("## Hermes Ershov nightly memory")
        print("")
        print(f"- Repo: `{REPO_ROOT}`")
        print(f"- Live root: `{live_root}`")
        print(f"- Artifact root: `{artifact_root}`")
        print(f"- Archive root: `{archive_root}`")
        print(f"- State root: `{state_root}`")
        print(f"- Provider: `{provider}`")
        print(f"- Model: `{model or 'provider-default'}`")
        print(f"- Recent sessions: `{recent}`")
        print(f"- Run source: `{run_source}`")
        print("")

        result = subprocess.run(cmd, cwd=str(REPO_ROOT), env=env, text=True, capture_output=True, check=False)
        if result.stdout:
            print(result.stdout.rstrip())
        if result.returncode != 0 and result.stderr:
            print(result.stderr.rstrip())
        return result.returncode


    if __name__ == "__main__":
        raise SystemExit(main())
    '''
).lstrip()


def _repo_root() -> Path:
    """Best-effort repo root lookup for the installed plugin checkout."""

    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "pyproject.toml").exists() and (parent / "plugin.yaml").exists():
            return parent
    return here.parents[3]


def _script_name(mode: str) -> str:
    return NIGHTLY_REVIEW_SCRIPT_NAME if mode in {"nightly-review", "nightly-memory"} else SCRIPT_NAME


def _script_path(*, mode: str = "status-digest") -> Path:
    return Path(get_hermes_home()) / "scripts" / _script_name(mode)


def _default_live_root() -> Path:
    return Path(get_hermes_home()) / "memories"


def _default_artifact_root() -> Path:
    return _repo_root() / ".ershov" / "artifacts"


def _default_archive_root() -> Path:
    return _repo_root() / ".ershov" / "archive"


def _default_state_root() -> Path:
    return Path(get_hermes_home()) / "ershov"


def render_nightly_script(
    *,
    repo_root: Path | None = None,
    recent: int = 14,
    provider: str = "deepseek",
    model: str = "deepseek-v4-flash",
    base_url: str | None = "https://api.deepseek.com/v1",
    live_root: Path | None = None,
    artifact_root: Path | None = None,
    archive_root: Path | None = None,
    state_root: Path | None = None,
    run_source: str = "cron",
) -> str:
    resolved_repo_root = repo_root or _repo_root()
    return (
        _NIGHTLY_REVIEW_SCRIPT_TEMPLATE.replace("__REPO_ROOT__", repr(str(resolved_repo_root)))
        .replace("__LIVE_ROOT__", repr(str(live_root or _default_live_root())))
        .replace("__ARTIFACT_ROOT__", repr(str(artifact_root or _default_artifact_root())))
        .replace("__ARCHIVE_ROOT__", repr(str(archive_root or _default_archive_root())))
        .replace("__STATE_ROOT__", repr(str(state_root or _default_state_root())))
        .replace("__PROVIDER__", repr(provider))
        .replace("__MODEL__", repr(model or ""))
        .replace("__BASE_URL__", repr(base_url or ""))
        .replace("__RECENT__", str(recent))
        .replace("__RUN_SOURCE__", repr(run_source))
    )


def _ensure_digest_script(
    *,
    mode: str = "status-digest",
    recent: int = 14,
    provider: str = "deepseek",
    model: str = "deepseek-v4-flash",
    base_url: str | None = "https://api.deepseek.com/v1",
    live_root: Path | None = None,
    artifact_root: Path | None = None,
    archive_root: Path | None = None,
    state_root: Path | None = None,
) -> Path:
    script_path = _script_path(mode=mode)
    script_path.parent.mkdir(parents=True, exist_ok=True)
    current = script_path.read_text(encoding="utf-8") if script_path.exists() else None
    if mode in {"nightly-review", "nightly-memory"}:
        script_text = render_nightly_script(
            recent=recent,
            provider=provider,
            model=model,
            base_url=base_url,
            live_root=live_root,
            artifact_root=artifact_root,
            archive_root=archive_root,
            state_root=state_root,
        )
    else:
        template = _INBOX_DIGEST_SCRIPT_TEMPLATE if mode == "inbox-digest" else _DIGEST_SCRIPT_TEMPLATE
        script_text = template.replace("__REPO_ROOT__", repr(str(_repo_root())))
    if current != script_text:
        script_path.write_text(script_text, encoding="utf-8")
        try:
            script_path.chmod(0o755)
        except OSError:
            pass
    return script_path


def _find_existing(list_jobs_fn) -> dict | None:
    try:
        for job in list_jobs_fn(include_disabled=True):
            if job.get("name") == JOB_NAME:
                return job
    except Exception:
        return None
    return None


def _prompt(mode: str) -> str:
    if mode == "inbox-digest":
        return _INBOX_PROMPT
    if mode in {"nightly-review", "nightly-memory"}:
        return _REVIEW_PROMPT
    return _PROMPT


def _desired_job_fields(schedule: str, *, mode: str = "status-digest") -> dict:
    return {
        "prompt": _prompt(mode),
        "schedule": schedule,
        "name": JOB_NAME,
        "deliver": "local",
        "script": _script_name(mode),
        "no_agent": True,
        "workdir": str(_repo_root()),
    }


def _job_matches(job: dict, desired: dict) -> bool:
    return all(job.get(key) == value for key, value in desired.items())


def _render_job_block(header: str, job: dict, schedule_display: str) -> str:
    script_name = str(job.get("script") or SCRIPT_NAME)
    mode_label = "no-agent nightly memory script" if script_name == NIGHTLY_REVIEW_SCRIPT_NAME else "no-agent digest script"
    tail = (
        "Each night Hermes will run the full memory pipeline: dialogue harvest, staged artifact, digest, inbox digest, and compaction. Live memory is not applied automatically."
        if script_name == NIGHTLY_REVIEW_SCRIPT_NAME
        else "Each night Hermes will run a deterministic status digest, so you get an actual report instead of a polite little tombstone."
    )
    return (
        "## hermes ershov install-cron\n\n"
        f"**{header}.**\n\n"
        f"- Job ID:    `{job['id']}`\n"
        f"- Name:      `{JOB_NAME}`\n"
        f"- Schedule:  {schedule_display}\n"
        f"- Next run:  {job.get('next_run_at', 'unknown')}\n"
        f"- Mode:      {mode_label}\n"
        f"- Script:    `{script_name}`\n"
        f"- Workdir:   `{_repo_root()}`\n\n"
        f"{tail}"
    )


def handle(
    schedule: str | None = None,
    *,
    mode: str = "status-digest",
    recent: int = 14,
    provider: str = "deepseek",
    model: str = "deepseek-v4-flash",
    base_url: str | None = "https://api.deepseek.com/v1",
    live_root: Path | None = None,
    artifact_root: Path | None = None,
    archive_root: Path | None = None,
    state_root: Path | None = None,
) -> str:
    """Register or refresh the nightly Hermes Ershov digest cron job."""

    try:
        from cron.jobs import create_job, list_jobs, update_job
    except ImportError:
        return (
            "## hermes ershov install-cron\n\n"
            "**Error:** Hermes cron module not available in this environment.\n\n"
            "Start Hermes in an environment that exposes `cron.jobs`, then retry."
        )

    schedule = (schedule or DEFAULT_SCHEDULE).strip()
    if mode not in {"status-digest", "inbox-digest", "nightly-review", "nightly-memory"}:
        return "## hermes ershov install-cron\n\n**Error:** unsupported mode."
    if recent <= 0:
        return "## hermes ershov install-cron\n\n**Error:** recent must be greater than 0."
    _ensure_digest_script(
        mode=mode,
        recent=recent,
        provider=provider,
        model=model,
        base_url=base_url,
        live_root=live_root,
        artifact_root=artifact_root,
        archive_root=archive_root,
        state_root=state_root,
    )
    desired = _desired_job_fields(schedule, mode=mode)

    existing = _find_existing(list_jobs)
    if existing:
        if _job_matches(existing, desired):
            schedule_display = existing.get("schedule_display", existing.get("schedule", "?"))
            return _render_job_block("Already installed", existing, schedule_display)

        updated = update_job(existing["id"], desired)
        if not updated:
            return (
                "## hermes ershov install-cron\n\n"
                f"**Error updating cron job `{existing['id']}`.**\n\n"
                "The job exists, but Hermes could not refresh it. Check the cron registry and retry."
            )
        schedule_display = updated.get("schedule_display", updated.get("schedule", "?"))
        return _render_job_block("Cron job updated", updated, schedule_display)

    try:
        job = create_job(**desired)
    except Exception as exc:
        return (
            "## hermes ershov install-cron\n\n"
            f"**Error creating cron job:** {exc}\n\n"
            f"Check that the schedule expression `{schedule}` is valid "
            "(for example, `0 3 * * *` for nightly at 03:00)."
        )

    schedule_display = job.get("schedule_display", schedule)
    return _render_job_block("Cron job registered", job, schedule_display)

from __future__ import annotations

import subprocess
from importlib import import_module
from pathlib import Path
import types

import pytest

from hermes_dreaming.commands.update import handle, render_update_result
from hermes_dreaming.cli import main

update_module = import_module("hermes_dreaming.commands.update")


def _run_git(args: list[str], *, cwd: Path) -> str:
    proc = subprocess.run(["git", *args], cwd=cwd, text=True, capture_output=True)
    if proc.returncode != 0:
        raise AssertionError(proc.stderr or proc.stdout or f"git {' '.join(args)} failed")
    return proc.stdout.strip()


def _init_repo(tmp_path: Path) -> tuple[Path, Path]:
    remote = tmp_path / "remote.git"
    repo = tmp_path / "repo"
    _run_git(["init", "--bare", str(remote)], cwd=tmp_path)
    _run_git(["symbolic-ref", "HEAD", "refs/heads/main"], cwd=remote)
    repo.mkdir()
    try:
        _run_git(["init", "-b", "main"], cwd=repo)
    except AssertionError:
        _run_git(["init"], cwd=repo)
        _run_git(["checkout", "-b", "main"], cwd=repo)
    _run_git(["config", "user.name", "Hermes Test"], cwd=repo)
    _run_git(["config", "user.email", "hermes@test.local"], cwd=repo)
    (repo / "tests").mkdir()
    (repo / "tests" / "test_smoke.py").write_text("def test_smoke():\n    assert True\n", encoding="utf-8")
    (repo / "README.md").write_text("# test repo\n", encoding="utf-8")
    _run_git(["add", "."], cwd=repo)
    _run_git(["commit", "-m", "initial commit"], cwd=repo)
    _run_git(["remote", "add", "origin", str(remote)], cwd=repo)
    _run_git(["push", "-u", "origin", "main"], cwd=repo)
    return repo, remote


def _add_remote_commit(remote: Path, tmp_path: Path) -> str:
    other = tmp_path / "other"
    _run_git(["clone", "-b", "main", str(remote), str(other)], cwd=tmp_path)
    _run_git(["config", "user.name", "Hermes Test"], cwd=other)
    _run_git(["config", "user.email", "hermes@test.local"], cwd=other)
    (other / "update.txt").write_text("update\n", encoding="utf-8")
    _run_git(["add", "update.txt"], cwd=other)
    _run_git(["commit", "-m", "upstream update"], cwd=other)
    _run_git(["push"], cwd=other)
    return _run_git(["rev-parse", "HEAD"], cwd=other)


def test_update_check_reports_up_to_date(tmp_path: Path) -> None:
    repo, _remote = _init_repo(tmp_path)

    result = handle(repo_root=repo, check=True)

    assert result.success is True
    assert result.checked_only is True
    assert result.updated is False
    assert result.behind == 0
    assert "Already up to date." in result.message


def test_update_fast_forwards_and_verifies(tmp_path: Path) -> None:
    repo, remote = _init_repo(tmp_path)
    updated_rev = _add_remote_commit(remote, tmp_path)

    result = handle(repo_root=repo)

    assert result.success is True
    assert result.updated is True
    assert result.verified is True
    assert result.current_rev == updated_rev
    assert result.upstream_rev == updated_rev
    assert result.ahead == 0
    assert result.behind == 0
    assert result.dirty is False
    rendered = render_update_result(result)
    assert "- Upstream: `" in rendered
    assert "- Ahead: `0`" in rendered
    assert "- Behind: `0`" in rendered
    assert _run_git(["rev-parse", "HEAD"], cwd=repo) == updated_rev
    assert (repo / "update.txt").read_text(encoding="utf-8") == "update\n"


def test_update_refuses_dirty_tree(tmp_path: Path) -> None:
    repo, _remote = _init_repo(tmp_path)
    (repo / "README.md").write_text("# dirty repo\n", encoding="utf-8")

    result = handle(repo_root=repo)

    assert result.success is False
    assert result.dirty is True
    assert "dirty" in result.message.lower()


def test_update_git_commands_have_timeout(monkeypatch, tmp_path: Path) -> None:
    def timeout_run(*_args, **_kwargs):  # type: ignore[no-untyped-def]
        raise subprocess.TimeoutExpired(["git", "fetch"], timeout=60)

    monkeypatch.setattr(update_module.subprocess, "run", timeout_run)

    with pytest.raises(RuntimeError, match="timed out after 60s"):
        update_module._run_git(["fetch", "--prune", "origin"], cwd=tmp_path, timeout_seconds=60)


def test_update_fetch_retries_one_timeout(monkeypatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_run_git(args, *, cwd, timeout_seconds=120):  # type: ignore[no-untyped-def]
        calls.append(list(args))
        if len(calls) == 1:
            raise RuntimeError(f"git fetch --prune origin timed out after {timeout_seconds}s")
        return subprocess.CompletedProcess(["git", *args], 0, "", "")

    monkeypatch.setattr(update_module, "_run_git", fake_run_git)

    update_module._fetch_remote(cwd=tmp_path, remote="origin", timeout_seconds=120, retries=1)

    assert calls == [["fetch", "--prune", "origin"], ["fetch", "--prune", "origin"]]


def test_update_fetch_does_not_retry_non_timeout_errors(monkeypatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_run_git(args, *, cwd, timeout_seconds=120):  # type: ignore[no-untyped-def]
        calls.append(list(args))
        raise RuntimeError("fatal: authentication failed")

    monkeypatch.setattr(update_module, "_run_git", fake_run_git)

    with pytest.raises(RuntimeError, match="authentication failed"):
        update_module._fetch_remote(cwd=tmp_path, remote="origin", timeout_seconds=120, retries=1)

    assert calls == [["fetch", "--prune", "origin"]]


def test_update_pull_retries_transient_network_error(monkeypatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_run_git(args, *, cwd, timeout_seconds=120):  # type: ignore[no-untyped-def]
        calls.append(list(args))
        if len(calls) == 1:
            raise RuntimeError(
                "fatal: unable to access 'https://github.com/example/repo.git/': "
                "Failed to connect to github.com port 443"
            )
        return subprocess.CompletedProcess(["git", *args], 0, "", "")

    monkeypatch.setattr(update_module, "_run_git", fake_run_git)

    result = update_module._run_git_retrying_transient(
        ["pull", "--ff-only", "origin", "main"],
        cwd=tmp_path,
        timeout_seconds=120,
        retries=1,
    )

    assert result.returncode == 0
    assert calls == [
        ["pull", "--ff-only", "origin", "main"],
        ["pull", "--ff-only", "origin", "main"],
    ]


def test_update_pull_does_not_retry_non_transient_errors(monkeypatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_run_git(args, *, cwd, timeout_seconds=120):  # type: ignore[no-untyped-def]
        calls.append(list(args))
        raise RuntimeError("fatal: Not possible to fast-forward, aborting.")

    monkeypatch.setattr(update_module, "_run_git", fake_run_git)

    with pytest.raises(RuntimeError, match="fast-forward"):
        update_module._run_git_retrying_transient(
            ["pull", "--ff-only", "origin", "main"],
            cwd=tmp_path,
            timeout_seconds=120,
            retries=1,
        )

    assert calls == [["pull", "--ff-only", "origin", "main"]]


def test_update_rejects_non_positive_git_timeout(tmp_path: Path) -> None:
    repo, _remote = _init_repo(tmp_path)

    result = handle(repo_root=repo, git_timeout_seconds=0)

    assert result.success is False
    assert "git-timeout-seconds" in result.message


def test_update_verifier_uses_uv_ephemeral_env_for_pyproject(monkeypatch, tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'example'\nversion = '0.1.0'\n", encoding="utf-8")
    monkeypatch.setattr(update_module.shutil, "which", lambda name: "/usr/bin/uv" if name == "uv" else None)

    command = update_module._verification_command(tmp_path, cache_dir=tmp_path / ".pytest-cache")

    assert command[:5] == ["uv", "run", "--no-project", "--with-editable", "."]
    assert "--with" in command
    assert "hypothesis" in command
    assert "pytest" in command
    assert "-m" in command


def test_cli_update_wires_through_parser(monkeypatch, tmp_path: Path) -> None:
    captured = {}

    def fake_update_command(**kwargs):
        captured.update(kwargs)
        return types.SimpleNamespace(
            success=True,
            message="Updated from abc1234 to def5678 successfully.",
            repo_root=kwargs["repo_root"],
            remote=kwargs["remote"],
            branch=kwargs["branch"],
            current_rev="abc1234",
            upstream_rev="def5678",
            behind=1,
            ahead=0,
            dirty=False,
            checked_only=kwargs["check"],
            updated=not kwargs["check"],
            verified=not kwargs["check"] and kwargs["verify"],
        )

    monkeypatch.setattr("hermes_dreaming.cli.update_command", fake_update_command)
    monkeypatch.setattr("hermes_dreaming.cli.render_update_result", lambda result: f"rendered:{result.message}")

    assert (
        main(
            [
                "update",
                "--check",
                "--remote",
                "upstream",
                "--branch",
                "dev",
                "--no-verify",
                "--git-timeout-seconds",
                "180",
            ]
        )
        == 0
    )
    assert captured["remote"] == "upstream"
    assert captured["branch"] == "dev"
    assert captured["check"] is True
    assert captured["verify"] is False
    assert captured["git_timeout_seconds"] == 180
    assert captured["repo_root"].is_dir()
    assert (captured["repo_root"] / "src" / "hermes_dreaming").exists()

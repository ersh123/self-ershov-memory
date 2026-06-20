from __future__ import annotations

import argparse
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import sqlite3
import tempfile


ROOT = Path(__file__).resolve().parents[1]


class DummyHermesContext:
    def __init__(self) -> None:
        self.cli_commands: dict[str, dict] = {}
        self.skills: list[tuple[str, Path]] = []

    def register_cli_command(self, **kwargs) -> None:
        self.cli_commands[kwargs["name"]] = kwargs

    def register_skill(self, bare_name: str, skill_path: Path) -> None:
        self.skills.append((bare_name, Path(skill_path)))


def _load_root_plugin():
    spec = importlib.util.spec_from_file_location("hermes_ershov_root_plugin_smoke", ROOT / "__init__.py")
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load root plugin module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_session_db(db_path: Path) -> None:
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(
            """
            CREATE TABLE sessions (
                id TEXT PRIMARY KEY,
                title TEXT,
                started_at REAL,
                message_count INTEGER,
                source TEXT,
                parent_session_id TEXT,
                end_reason TEXT
            );
            CREATE TABLE messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT,
                timestamp REAL NOT NULL
            );
            """
        )
        conn.execute(
            "INSERT INTO sessions (id, title, started_at, message_count, source, parent_session_id, end_reason) VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("smoke-1", "Plugin smoke", 2_000.0, 1, "cli", None, None),
        )
        conn.execute(
            "INSERT INTO messages (session_id, role, content, timestamp) VALUES (?, ?, ?, ?)",
            (
                "smoke-1",
                "user",
                "MEMORY: memory: Keep Hermes Ershov plugin smoke gates strict.",
                2_000.0,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _assert_bad_command_exits(handler) -> None:
    stdout = io.StringIO()
    stderr = io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        try:
            handler(argparse.Namespace(dreaming_args=["__definitely_unknown__"]))
        except SystemExit as exc:
            if exc.code == 2:
                return
            raise AssertionError(f"bad command raised exit {exc.code!r}, expected 2") from exc
    raise AssertionError("bad command returned success instead of raising SystemExit(2)")


def _assert_nightly_stages_proposal(handler) -> None:
    old_env = os.environ.get("HERMES_ERSHOV_SESSION_DB")
    with tempfile.TemporaryDirectory(prefix="hermes-ershov-plugin-smoke-") as raw_tmp:
        tmp = Path(raw_tmp)
        db_path = tmp / "state.db"
        live_root = tmp / "live"
        artifact_root = tmp / "artifacts"
        archive_root = tmp / "archive"
        state_root = tmp / "state"
        for path in (live_root, artifact_root, archive_root, state_root):
            path.mkdir(parents=True, exist_ok=True)
        (live_root / "memory.md").write_text("# MEMORY\n", encoding="utf-8")
        (live_root / "user.md").write_text("# USER\n", encoding="utf-8")
        _write_session_db(db_path)

        os.environ["HERMES_ERSHOV_SESSION_DB"] = str(db_path)
        code: int | None = None
        try:
            stdout = io.StringIO()
            stderr = io.StringIO()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                try:
                    code = handler(
                        argparse.Namespace(
                            dreaming_args=[
                                "nightly",
                                "--no-llm",
                                "--live-root",
                                str(live_root),
                                "--artifact-root",
                                str(artifact_root),
                                "--archive-root",
                                str(archive_root),
                                "--state-root",
                                str(state_root),
                                "--recent",
                                "1",
                            ]
                        )
                    )
                except SystemExit as exc:
                    raise AssertionError(f"nightly smoke raised exit {exc.code!r}, expected return 0") from exc
        finally:
            if old_env is None:
                os.environ.pop("HERMES_ERSHOV_SESSION_DB", None)
            else:
                os.environ["HERMES_ERSHOV_SESSION_DB"] = old_env

        if code != 0:
            raise AssertionError(f"nightly smoke returned {code}, expected 0")

        manifests = list(artifact_root.glob("*/manifest.json"))
        if len(manifests) != 1:
            raise AssertionError(f"expected one staged artifact, found {len(manifests)}")
        manifest = json.loads(manifests[0].read_text(encoding="utf-8"))
        proposals = manifest.get("proposals", [])
        if manifest.get("status") != "staged" or len(proposals) != 1:
            raise AssertionError(
                f"expected staged artifact with one proposal, got status={manifest.get('status')!r}, proposals={len(proposals)}"
            )

        ledger_path = state_root / "runs.jsonl"
        runs = [json.loads(line) for line in ledger_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        if not runs or runs[-1].get("success") is not True or runs[-1].get("artifact_status") != "staged":
            raise AssertionError("nightly smoke did not record a successful staged run")


def main() -> int:
    plugin = _load_root_plugin()
    ctx = DummyHermesContext()
    plugin.register(ctx)

    required = {"ershov", "mnemos", "nightmem", "dreaming"}
    missing = required.difference(ctx.cli_commands)
    if missing:
        raise AssertionError(f"missing plugin CLI commands: {sorted(missing)}")
    if not ctx.skills:
        raise AssertionError("plugin did not register its skill")

    handler = ctx.cli_commands["ershov"]["handler_fn"]
    _assert_bad_command_exits(handler)
    _assert_nightly_stages_proposal(handler)

    print("Hermes plugin smoke: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

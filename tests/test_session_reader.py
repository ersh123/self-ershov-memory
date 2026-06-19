from __future__ import annotations

import json
import sqlite3
import sys
import types
from pathlib import Path

from hermes_dreaming import session_reader as reader


def _make_session_digest(session_id: str, source: str) -> reader.SessionDigest:
    return reader.SessionDigest(
        session_id=session_id,
        title=None,
        started_at=None,
        message_count=1,
        source=source,
        user_turns=[f"{source} hit"],
    )


def _build_sqlite_session_db(db_path: Path) -> None:
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
            ("s1", "One", 1000.0, 2, "cli", None, None),
        )
        conn.execute(
            "INSERT INTO sessions (id, title, started_at, message_count, source, parent_session_id, end_reason) VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("s2", "Two", 2000.0, 3, "cli", None, None),
        )
        conn.executemany(
            "INSERT INTO messages (session_id, role, content, timestamp) VALUES (?, ?, ?, ?)",
            [
                ("s1", "user", "first user turn for session one", 1000.0),
                ("s1", "assistant", "assistant reply for session one", 1001.0),
                ("s1", "user", "second user turn for session one", 1002.0),
                ("s2", "user", "first user turn for session two", 2000.0),
                ("s2", "assistant", "assistant reply for session two", 2001.0),
            ],
        )
        conn.commit()
    finally:
        conn.close()


def test_list_recent_stops_at_session_db(monkeypatch) -> None:
    calls: list[str] = []

    def session_db(limit: int):
        calls.append("sessiondb")
        return [_make_session_digest("sdb-1", "sessiondb")]

    def sqlite(limit: int):
        calls.append("sqlite")
        return [_make_session_digest("sqlite-1", "sqlite")]

    def pointer(limit: int):
        calls.append("pointer")
        return [_make_session_digest("pointer-1", "pointer-log")]

    monkeypatch.setattr(reader, "_read_via_session_db", session_db)
    monkeypatch.setattr(reader, "_read_via_sqlite", sqlite)
    monkeypatch.setattr(reader, "_read_via_pointer_log", pointer)

    sessions = reader.list_recent(limit=3)

    assert [session.session_id for session in sessions] == ["sdb-1"]
    assert calls == ["sessiondb"]


def test_read_via_session_db_closes_primary_database(monkeypatch) -> None:
    closed = False

    class FakeSessionDB:
        def list_sessions_rich(self, *, limit: int, order_by_last_active: bool):  # noqa: ARG002
            return [
                {
                    "id": "session-1",
                    "title": "One",
                    "started_at": 1000.0,
                    "message_count": 1,
                    "source": "sessiondb",
                }
            ]

        def get_messages(self, _sid: str):
            return [{"role": "user", "content": "User turn long enough to keep"}]

        def close(self) -> None:
            nonlocal closed
            closed = True

    monkeypatch.setitem(sys.modules, "hermes_state", types.SimpleNamespace(SessionDB=FakeSessionDB))

    sessions = reader._read_via_session_db(limit=1)

    assert sessions is not None
    assert [session.session_id for session in sessions] == ["session-1"]
    assert closed is True


def test_list_recent_falls_back_to_sqlite_then_pointer_log(monkeypatch) -> None:
    calls: list[str] = []

    def session_db(limit: int):
        calls.append("sessiondb")
        return None

    def sqlite(limit: int):
        calls.append("sqlite")
        return [_make_session_digest("sqlite-1", "sqlite")]

    def pointer(limit: int):
        calls.append("pointer")
        return [_make_session_digest("pointer-1", "pointer-log")]

    monkeypatch.setattr(reader, "_read_via_session_db", session_db)
    monkeypatch.setattr(reader, "_read_via_sqlite", sqlite)
    monkeypatch.setattr(reader, "_read_via_pointer_log", pointer)

    sessions = reader.list_recent(limit=3)

    assert [session.session_id for session in sessions] == ["sqlite-1"]
    assert calls == ["sessiondb", "sqlite"]


def test_list_recent_uses_configured_session_db_before_session_db(
    tmp_path: Path, monkeypatch
) -> None:
    db_path = tmp_path / "state.db"
    _build_sqlite_session_db(db_path)
    monkeypatch.setenv("HERMES_ERSHOV_SESSION_DB", str(db_path))

    def session_db(*_args, **_kwargs):
        raise AssertionError("SessionDB should be skipped when a DB override is configured")

    monkeypatch.setattr(reader, "_read_via_session_db", session_db)

    sessions = reader.list_recent(limit=1, include_assistant=True)

    assert [session.session_id for session in sessions] == ["s2"]
    assert sessions[0].context_lines == [
        "user: first user turn for session two",
        "assistant: assistant reply for session two",
    ]


def test_list_recent_falls_back_to_pointer_log_when_the_first_two_paths_fail(monkeypatch) -> None:
    calls: list[str] = []

    def session_db(limit: int):
        calls.append("sessiondb")
        return None

    def sqlite(limit: int):
        calls.append("sqlite")
        return None

    def pointer(limit: int):
        calls.append("pointer")
        return [_make_session_digest("pointer-1", "pointer-log")]

    monkeypatch.setattr(reader, "_read_via_session_db", session_db)
    monkeypatch.setattr(reader, "_read_via_sqlite", sqlite)
    monkeypatch.setattr(reader, "_read_via_pointer_log", pointer)

    sessions = reader.list_recent(limit=3)

    assert [session.session_id for session in sessions] == ["pointer-1"]
    assert calls == ["sessiondb", "sqlite", "pointer"]


def test_read_recent_session_context_returns_empty_prompt_when_no_sessions(monkeypatch) -> None:
    monkeypatch.setattr(reader, "_read_via_session_db", lambda limit: [])
    monkeypatch.setattr(reader, "_read_via_sqlite", lambda limit: [])
    monkeypatch.setattr(reader, "_read_via_pointer_log", lambda limit: [])

    assert reader.read_recent_session_context() == "No recent sessions found.\n"


def test_read_via_sqlite_prefers_most_recent_session_and_compacts_user_turns(tmp_path: Path) -> None:
    db_path = tmp_path / "state.db"
    _build_sqlite_session_db(db_path)

    sessions = reader._read_via_sqlite(limit=5, db_path=db_path)

    assert sessions is not None
    assert [session.session_id for session in sessions] == ["s2", "s1"]
    assert sessions[0].user_turns == ["first user turn for session two"]
    assert sessions[1].user_turns == [
        "first user turn for session one",
        "second user turn for session one",
    ]


def test_read_via_sqlite_can_include_dialogue_lines(tmp_path: Path) -> None:
    db_path = tmp_path / "state.db"
    _build_sqlite_session_db(db_path)

    sessions = reader._read_via_sqlite(limit=1, db_path=db_path, include_assistant=True)

    assert sessions is not None
    assert sessions[0].session_id == "s2"
    assert sessions[0].user_turns == ["first user turn for session two"]
    assert sessions[0].context_lines == [
        "user: first user turn for session two",
        "assistant: assistant reply for session two",
    ]
    assert "assistant: assistant reply for session two" in reader.format_for_prompt(sessions)


def test_read_via_pointer_log_returns_recent_ids_in_reverse_order(tmp_path: Path) -> None:
    state_path = tmp_path / "state.json"
    state_path.write_text(
        json.dumps({"recent_session_ids": ["old-a", "old-b", "new-c"]}),
        encoding="utf-8",
    )

    sessions = reader._read_via_pointer_log(limit=2, state_path=state_path)

    assert [session.session_id for session in sessions] == ["new-c", "old-b"]
    assert all(session.source == "pointer-log" for session in sessions)

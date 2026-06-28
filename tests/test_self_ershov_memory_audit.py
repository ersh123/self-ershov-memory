from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from self_ershov_memory import audit


def test_clean_content_strips_compaction_attachment_and_technical_noise() -> None:
    raw = """
[CONTEXT COMPACTION START]
noise
--- END OF CONTEXT SUMMARY ---
Никита: запомни на будущее: логи кратко
[The user sent an image~ giant attachment text]
{"tool": "result", "data": "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"}
[If you need a closer look, use vision_analyze]
"""

    cleaned = audit.clean_content(raw)

    assert "CONTEXT COMPACTION" not in cleaned
    assert "The user sent" not in cleaned
    assert "vision_analyze" not in cleaned
    assert "логи кратко" in cleaned


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("логи и diff только кратко, без полного дампа", {"логи"}),
        ("опять отвечаешь на старый закрытый вопрос", {"повтор"}),
        ("это максимально иишно, убери ai слоп", {"ai-слоп"}),
        ("Руслан не Рослайн, перепроверяй названия", {"названия"}),
        ("надо глубокий ресерч и live поиск", {"ресерч"}),
        ("очевидное ищи сам, не переспрашивай", {"очевидное"}),
        ("DeepSeek прямой ключ, не через омнироут", {"deepseek"}),
        ("договор: убрать пункт 1.2.2", {"договоры"}),
        ("opencode provider подключать по докам", {"opencode"}),
        ("vibe coding обязателен для программирования", {"vibe-coding"}),
        ("обнови скилл, старый скил мусор", {"скиллы"}),
        ("скриншоты не слать если не просил", {"скриншоты"}),
    ],
)
def test_classify_topic_maps_operator_corrections(text: str, expected: set[str]) -> None:
    assert expected <= audit.classify_topic(text)


def test_find_corrections_detects_rules_deduplicates_and_ignores_tasks() -> None:
    messages = [
        {
            "content": "зачем ты опять отвечаешь на старые вопросы?",
            "title": "s1",
            "timestamp": 1,
        },
        {
            "content": "зачем ты опять отвечаешь на старые вопросы?",
            "title": "s1 duplicate",
            "timestamp": 2,
        },
        {
            "content": "запомни на будущее: логи в Telegram одной строкой",
            "title": "s2",
            "timestamp": 3,
        },
        {
            "content": "сделай README красивее",
            "title": "task only",
            "timestamp": 4,
        },
    ]

    corrections = audit.find_corrections(messages)

    assert [c["type"] for c in corrections] == ["correction", "rule"]
    assert corrections[0]["session"] == "s1"
    assert corrections[1]["session"] == "s2"
    assert all("README" not in c["text"] for c in corrections)


def test_memory_sections_parse_dedup_format_and_compress(tmp_path: Path, monkeypatch) -> None:
    user_md = tmp_path / "USER.md"
    user_md.write_text(
        "intro\n§\nКОРРЕКЦИИ ОТ НИКО (old)\n- **Логи** — кратко\n- повтор старого — стоп\n§\n",
        encoding="utf-8",
    )

    sections = audit.read_memory_sections(user_md)
    assert audit.find_corrections_section(sections) == 1
    norms, labels = audit.parse_existing_corrections(sections)
    assert "Логи" in labels
    assert audit.is_duplicate("повтор старого надо прекращать", norms)
    assert not audit.is_duplicate("новая уникальная правка", norms)

    formatted = audit.format_corrections_entry(
        [{"text": "Никита: всегда проверяй live search перед выводом"}]
    )
    assert formatted.startswith("КОРРЕКЦИИ ОТ НИКО (self-audit ")
    assert "Никита:" not in formatted
    assert "live search" in formatted

    noisy_section = "КОРРЕКЦИИ ОТ НИКО (old)\n" + "\n".join(
        ["- **Логи** — кратко"] * 20 + ["- **Ресерч** — глубоко"] * 15
    )
    compressed, removed = audit.compress_corrections_section(["intro", noisy_section])
    assert removed > 0
    assert compressed[1].count("**Логи**") == 1
    assert compressed[1].count("**Ресерч**") == 1

    out = tmp_path / "OUT.md"
    audit.write_sections(out, ["a", "b"])
    assert out.read_text(encoding="utf-8") == "a\n§\nb\n§\n"


def test_validate_snapshot_and_skill_sync_are_safe(tmp_path: Path, monkeypatch, capsys) -> None:
    user_md = tmp_path / "USER.md"
    memory_md = tmp_path / "MEMORY.md"
    snapshot_dir = tmp_path / "snapshots"
    skills_dir = tmp_path / "skills"
    existing_skill = skills_dir / "software-development" / "vibe-coding" / "SKILL.md"
    existing_skill.parent.mkdir(parents=True)
    existing_skill.write_text("---\nname: vibe-coding\n---\n", encoding="utf-8")
    user_md.write_text("u" * (audit.USER_LIMIT + 1), encoding="utf-8")
    memory_md.write_text("ok", encoding="utf-8")

    monkeypatch.setattr(audit, "USER_MD", user_md)
    monkeypatch.setattr(audit, "MEMORY_MD", memory_md)
    monkeypatch.setattr(audit, "SNAPSHOT_DIR", snapshot_dir)
    monkeypatch.setattr(audit, "SKILLS_DIR", skills_dir)

    issues = audit.validate_memory_files()
    assert issues == [f"USER.md: {audit.USER_LIMIT + 1} > {audit.USER_LIMIT} chars"]

    audit.snapshot(user_md)
    assert list(snapshot_dir.glob("USER.md.*.bak"))

    dry_count = audit.sync_skills(
        [
            {"text": "vibe coding теперь обязательно"},
            {"text": "opencode подключать по докам"},
        ],
        dry_run=True,
    )
    assert dry_count == 1
    dry_output = capsys.readouterr().out
    assert "vibe-coding" in dry_output
    assert "opencode-setup" in dry_output
    assert not (skills_dir / "opencode-setup" / "SKILL.md").exists()

    execute_count = audit.sync_skills(
        [{"text": "opencode подключать по докам"}],
        dry_run=False,
    )
    assert execute_count == 1
    assert "name: opencode-setup" in (skills_dir / "opencode-setup" / "SKILL.md").read_text(
        encoding="utf-8"
    )


def test_fetch_messages_and_run_pipeline_dry_run(tmp_path: Path, monkeypatch, capsys) -> None:
    state_db = tmp_path / "state.db"
    conn = sqlite3.connect(state_db)
    conn.execute("CREATE TABLE sessions (id TEXT PRIMARY KEY, source TEXT, title TEXT, started_at REAL)")
    conn.execute("CREATE TABLE messages (session_id TEXT, role TEXT, content TEXT, timestamp REAL)")
    conn.execute(
        "INSERT INTO sessions VALUES ('s1', 'telegram', 'audit session', strftime('%s','now'))"
    )
    conn.execute(
        "INSERT INTO messages VALUES ('s1', 'user', 'запомни на будущее: не печатай полные логи', strftime('%s','now'))"
    )
    conn.execute(
        "INSERT INTO messages VALUES ('s1', 'assistant', 'ignored', strftime('%s','now'))"
    )
    conn.commit()
    conn.close()

    user_md = tmp_path / "USER.md"
    memory_md = tmp_path / "MEMORY.md"
    user_md.write_text("intro\n§\n", encoding="utf-8")
    memory_md.write_text("АНТИПАТТЕРНЫ\n§\n", encoding="utf-8")

    monkeypatch.setattr(audit, "STATE_DB", state_db)
    monkeypatch.setattr(audit, "USER_MD", user_md)
    monkeypatch.setattr(audit, "MEMORY_MD", memory_md)
    monkeypatch.setattr(audit, "SKILLS_DIR", tmp_path / "skills")
    monkeypatch.setattr(audit, "SNAPSHOT_DIR", tmp_path / "snapshots")

    connected = audit.connect_db()
    assert connected is not None
    try:
        rows = audit.fetch_user_messages(connected, days=1)
    finally:
        connected.close()
    assert len(rows) == 1
    assert rows[0]["title"] == "audit session"

    assert audit.run_pipeline(mode="quick", dry_run=True) is True
    output = capsys.readouterr().out
    assert "Fetched 1 user messages" in output
    assert "DRY-RUN" in output
    assert "would update USER.md" in output
    assert user_md.read_text(encoding="utf-8") == "intro\n§\n"


def test_run_pipeline_execute_merges_memory_and_main_modes(tmp_path: Path, monkeypatch, capsys) -> None:
    state_db = tmp_path / "state.db"
    conn = sqlite3.connect(state_db)
    conn.execute("CREATE TABLE sessions (id TEXT PRIMARY KEY, source TEXT, title TEXT, started_at REAL)")
    conn.execute("CREATE TABLE messages (session_id TEXT, role TEXT, content TEXT, timestamp REAL)")
    conn.execute(
        "INSERT INTO sessions VALUES ('s1', 'telegram', 'audit session', strftime('%s','now'))"
    )
    conn.execute(
        "INSERT INTO messages VALUES ('s1', 'user', 'зачем ты опять повторяешь старый закрытый вопрос', strftime('%s','now'))"
    )
    conn.commit()
    conn.close()

    user_md = tmp_path / "USER.md"
    memory_md = tmp_path / "MEMORY.md"
    user_md.write_text("intro\n§\nКОРРЕКЦИИ ОТ НИКО (old)\n- логи — кратко\n§\nfooter\n§\n", encoding="utf-8")
    memory_md.write_text("АНТИПАТТЕРНЫ\n§\n", encoding="utf-8")

    monkeypatch.setattr(audit, "STATE_DB", state_db)
    monkeypatch.setattr(audit, "USER_MD", user_md)
    monkeypatch.setattr(audit, "MEMORY_MD", memory_md)
    monkeypatch.setattr(audit, "SKILLS_DIR", tmp_path / "skills")
    monkeypatch.setattr(audit, "SNAPSHOT_DIR", tmp_path / "snapshots")

    assert audit.run_pipeline(mode="full", dry_run=False) is True
    user_text = user_md.read_text(encoding="utf-8")
    memory_text = memory_md.read_text(encoding="utf-8")
    assert "зачем ты опять повторяешь старый закрытый вопрос" in user_text
    assert "повтор старого" in memory_text
    assert list((tmp_path / "snapshots").glob("*.bak"))
    assert "Validation passed" in capsys.readouterr().out

    assert audit.main(["--help"]) == 0
    assert "self-ershov-memory" in capsys.readouterr().out

    monkeypatch.setattr(audit, "run_pipeline", lambda mode, dry_run: (mode, dry_run) == ("full", False))
    assert audit.main(["--execute", "--full"]) == 0
    assert audit.main(["--dry-run", "--quick"]) == 1


def test_connect_db_missing_file_returns_none(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setattr(audit, "STATE_DB", tmp_path / "missing.db")

    assert audit.connect_db() is None
    assert "state.db not found" in capsys.readouterr().out



def _make_state_db(path: Path, messages: list[str]) -> None:
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE sessions (id TEXT PRIMARY KEY, source TEXT, title TEXT, started_at REAL)")
    conn.execute("CREATE TABLE messages (session_id TEXT, role TEXT, content TEXT, timestamp REAL)")
    conn.execute("INSERT INTO sessions VALUES ('s1', 'telegram', 'audit session', strftime('%s','now'))")
    for idx, message in enumerate(messages):
        conn.execute(
            "INSERT INTO messages VALUES ('s1', 'user', ?, strftime('%s','now') + ?)",
            (message, idx),
        )
    conn.commit()
    conn.close()


def test_product_audit_edge_cases_cover_defensive_branches(tmp_path: Path, monkeypatch, capsys) -> None:
    assert audit.clean_content("") == ""
    assert audit.clean_content(None) == ""
    assert audit.clean_content(123) == ""
    assert audit.find_corrections([{"content": "short", "title": "t", "timestamp": 1}]) == []
    assert audit.read_memory_sections(tmp_path / "missing.md") == []
    assert audit.find_antipatterns_section(["intro", "nothing"]) is None
    assert audit.parse_existing_corrections(["intro"]) == (set(), set())
    assert audit.is_duplicate("abc def ghi", {"abc def ghi plus"})
    assert audit.snapshot(tmp_path / "missing.md") is None
    assert audit.compress_corrections_section(["intro", "no corrections"]) == (["intro", "no corrections"], 0)
    assert audit.compress_corrections_section(["КОРРЕКЦИИ ОТ НИКО\n- one"]) == (["КОРРЕКЦИИ ОТ НИКО\n- one"], 0)

    memory_md = tmp_path / "MEMORY.md"
    user_md = tmp_path / "USER.md"
    memory_md.write_text("m" * (audit.MEMORY_LIMIT + 1), encoding="utf-8")
    user_md.write_text("ok", encoding="utf-8")
    monkeypatch.setattr(audit, "MEMORY_MD", memory_md)
    monkeypatch.setattr(audit, "USER_MD", user_md)
    assert audit.validate_memory_files() == [f"MEMORY.md: {audit.MEMORY_LIMIT + 1} > {audit.MEMORY_LIMIT} chars"]

    formatted = audit.format_corrections_entry([
        {"text": ""},
        {"text": "Никита: " + "проверяй " * 40},
    ])
    assert "..." in formatted

    noisy = "КОРРЕКЦИИ ОТ НИКО\nnot a bullet\n" + "\n".join(["- **A** — one"] * 31)
    compressed, removed = audit.compress_corrections_section([noisy])
    assert removed > 0
    assert "not a bullet" in compressed[0]
    assert capsys.readouterr().out == ""


def test_skill_sync_execute_existing_and_unreadable_skill_branch(tmp_path: Path, monkeypatch, capsys) -> None:
    skills_dir = tmp_path / "skills"
    broken = skills_dir / "broken" / "SKILL.md"
    broken.parent.mkdir(parents=True)
    broken.write_text("---\nname: broken\n---\n", encoding="utf-8")
    existing = skills_dir / "cat" / "vibe" / "SKILL.md"
    existing.parent.mkdir(parents=True)
    existing.write_text("---\nname: vibe-coding\n---\n", encoding="utf-8")

    real_read = Path.read_text

    def flaky_read(path: Path, *args, **kwargs):
        if path == broken:
            raise OSError("boom")
        return real_read(path, *args, **kwargs)

    monkeypatch.setattr(audit, "SKILLS_DIR", skills_dir)
    monkeypatch.setattr(Path, "read_text", flaky_read)

    assert audit.sync_skills([{"text": "vibe coding обязателен"}], dry_run=False) == 0
    assert "up-to-date" in capsys.readouterr().out


def test_run_pipeline_missing_db_and_no_messages(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setattr(audit, "STATE_DB", tmp_path / "missing.db")
    assert audit.run_pipeline(mode="quick", dry_run=True) is False

    state_db = tmp_path / "state.db"
    _make_state_db(state_db, [])
    monkeypatch.setattr(audit, "STATE_DB", state_db)
    assert audit.run_pipeline(mode="quick", dry_run=True) is True
    output = capsys.readouterr().out
    assert "state.db not found" in output
    assert "No messages found" in output


def test_run_pipeline_no_new_corrections_compresses_and_warns(tmp_path: Path, monkeypatch, capsys) -> None:
    state_db = tmp_path / "state.db"
    _make_state_db(state_db, ["запомни на будущее: повтор старого не поднимать"])
    user_md = tmp_path / "USER.md"
    memory_md = tmp_path / "MEMORY.md"
    duplicate_lines = "\n".join(["- **Повтор** — старое"] * 35)
    user_md.write_text(
        f"intro\n§\nКОРРЕКЦИИ ОТ НИКО (old)\n{duplicate_lines}\n§\n" + "u" * (audit.USER_LIMIT + 1),
        encoding="utf-8",
    )
    memory_md.write_text("АНТИПАТТЕРНЫ\n§\n", encoding="utf-8")

    monkeypatch.setattr(audit, "STATE_DB", state_db)
    monkeypatch.setattr(audit, "USER_MD", user_md)
    monkeypatch.setattr(audit, "MEMORY_MD", memory_md)
    monkeypatch.setattr(audit, "SKILLS_DIR", tmp_path / "skills")
    monkeypatch.setattr(audit, "SNAPSHOT_DIR", tmp_path / "snapshots")

    assert audit.run_pipeline(mode="full", dry_run=False) is True
    output = capsys.readouterr().out
    assert "No new corrections found" in output
    assert "Compressed USER.md" in output
    assert "WARN: USER.md" in output


def test_run_pipeline_execute_creates_section_and_handles_validation_overflow(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    state_db = tmp_path / "state.db"
    _make_state_db(
        state_db,
        [
            "зачем ты опять печатаешь полные логи и уведомления",
            "зачем ты опять путаешь названия Руслан Рослайн",
            "зачем ты опять делаешь поверхностный ресерч без проверки",
            "зачем ты опять путаешь desktop и vps, пк это десктоп",
        ],
    )
    user_md = tmp_path / "USER.md"
    memory_md = tmp_path / "MEMORY.md"
    user_md.write_text("intro\n§\nfooter\n§\n", encoding="utf-8")
    memory_md.write_text("АНТИПАТТЕРНЫ\n§\n" + "m" * (audit.MEMORY_LIMIT + 1), encoding="utf-8")

    monkeypatch.setattr(audit, "STATE_DB", state_db)
    monkeypatch.setattr(audit, "USER_MD", user_md)
    monkeypatch.setattr(audit, "MEMORY_MD", memory_md)
    monkeypatch.setattr(audit, "SKILLS_DIR", tmp_path / "skills")
    monkeypatch.setattr(audit, "SNAPSHOT_DIR", tmp_path / "snapshots")

    assert audit.run_pipeline(mode="full", dry_run=False) is True
    output = capsys.readouterr().out
    assert "Created new corrections section" in output
    assert "MEMORY.md over limit" in output
    memory_text = memory_md.read_text(encoding="utf-8")
    assert "логи/уведомления" in memory_text
    assert "названия клиентов" in memory_text
    assert "поверхностный ресерч" in memory_text
    assert "путаница VPS/Desktop" in memory_text


def test_run_pipeline_dry_run_lists_more_than_ten_and_checks_skills(tmp_path: Path, monkeypatch, capsys) -> None:
    state_db = tmp_path / "state.db"
    _make_state_db(state_db, [f"зачем ты опять делаешь ошибку номер {i}" for i in range(12)])
    user_md = tmp_path / "USER.md"
    memory_md = tmp_path / "MEMORY.md"
    user_md.write_text("intro\n§\n", encoding="utf-8")
    memory_md.write_text("АНТИПАТТЕРНЫ\n§\n", encoding="utf-8")

    monkeypatch.setattr(audit, "STATE_DB", state_db)
    monkeypatch.setattr(audit, "USER_MD", user_md)
    monkeypatch.setattr(audit, "MEMORY_MD", memory_md)
    monkeypatch.setattr(audit, "SKILLS_DIR", tmp_path / "skills")
    monkeypatch.setattr(audit, "SNAPSHOT_DIR", tmp_path / "snapshots")

    assert audit.run_pipeline(mode="full", dry_run=True) is True
    output = capsys.readouterr().out
    assert "... and 2 more" in output
    assert "--- Skills check (dry-run) ---" in output


def test_run_pipeline_existing_section_topic_filter_no_merge(tmp_path: Path, monkeypatch, capsys) -> None:
    state_db = tmp_path / "state.db"
    _make_state_db(state_db, ["зачем ты опять возвращаешь старый закрытый вопрос"])
    user_md = tmp_path / "USER.md"
    memory_md = tmp_path / "MEMORY.md"
    user_md.write_text("intro\n§\nКОРРЕКЦИИ ОТ НИКО (old)\n- повтор старого уже закрыт\n§\n", encoding="utf-8")
    memory_md.write_text("АНТИПАТТЕРНЫ\n§\n", encoding="utf-8")

    monkeypatch.setattr(audit, "STATE_DB", state_db)
    monkeypatch.setattr(audit, "USER_MD", user_md)
    monkeypatch.setattr(audit, "MEMORY_MD", memory_md)
    monkeypatch.setattr(audit, "SKILLS_DIR", tmp_path / "skills")
    monkeypatch.setattr(audit, "SNAPSHOT_DIR", tmp_path / "snapshots")

    assert audit.run_pipeline(mode="full", dry_run=False) is True
    assert "All corrections already present, no merge needed" in capsys.readouterr().out


def test_module_entrypoint_import_is_covered() -> None:
    import self_ershov_memory.__main__ as module

    assert module.main is audit.main



def test_run_pipeline_no_new_corrections_dry_run_checks_skills(tmp_path: Path, monkeypatch, capsys) -> None:
    state_db = tmp_path / "state.db"
    _make_state_db(state_db, ["запомни на будущее: повтор старого не поднимать"])
    user_md = tmp_path / "USER.md"
    memory_md = tmp_path / "MEMORY.md"
    user_md.write_text("intro\n§\nКОРРЕКЦИИ ОТ НИКО (old)\n- повтор старого не поднимать\n§\n", encoding="utf-8")
    memory_md.write_text("АНТИПАТТЕРНЫ\n§\n", encoding="utf-8")

    monkeypatch.setattr(audit, "STATE_DB", state_db)
    monkeypatch.setattr(audit, "USER_MD", user_md)
    monkeypatch.setattr(audit, "MEMORY_MD", memory_md)
    monkeypatch.setattr(audit, "SKILLS_DIR", tmp_path / "skills")
    monkeypatch.setattr(audit, "SNAPSHOT_DIR", tmp_path / "snapshots")

    assert audit.run_pipeline(mode="quick", dry_run=True) is True
    output = capsys.readouterr().out
    assert "No new corrections found" in output
    assert "--- Skills check (dry-run) ---" in output


def test_run_pipeline_merge_skips_malformed_and_existing_topic_then_compresses_user(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    state_db = tmp_path / "state.db"
    _make_state_db(state_db, ["зачем ты опять печатаешь полные логи"])
    user_md = tmp_path / "USER.md"
    memory_md = tmp_path / "MEMORY.md"
    user_md.write_text(
        "intro\n§\nКОРРЕКЦИИ ОТ НИКО (old)\n- логи уже кратко\n" + "\n".join(["- **D** — x"] * 35) + "\n§\n",
        encoding="utf-8",
    )
    memory_md.write_text("АНТИПАТТЕРНЫ\n§\n", encoding="utf-8")

    monkeypatch.setattr(audit, "STATE_DB", state_db)
    monkeypatch.setattr(audit, "USER_MD", user_md)
    monkeypatch.setattr(audit, "MEMORY_MD", memory_md)
    monkeypatch.setattr(audit, "SKILLS_DIR", tmp_path / "skills")
    monkeypatch.setattr(audit, "SNAPSHOT_DIR", tmp_path / "snapshots")
    monkeypatch.setattr(
        audit,
        "format_corrections_entry",
        lambda _corrections: "КОРРЕКЦИИ ОТ НИКО\nnot a bullet\n- повтор старого",
    )
    monkeypatch.setattr(audit, "USER_LIMIT", 1)

    assert audit.run_pipeline(mode="full", dry_run=False) is True
    output = capsys.readouterr().out
    assert "Auto-compressed USER.md" in output



def test_format_entry_skips_empty_after_nikita_prefix() -> None:
    formatted = audit.format_corrections_entry([{"text": "Никита:"}])
    assert formatted.startswith("КОРРЕКЦИИ ОТ НИКО")
    assert formatted.count("\n-") == 0


def test_skill_sync_ignores_unreadable_skill_file_then_creates_missing_skill(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    skills_dir = tmp_path / "skills"
    broken = skills_dir / "broken" / "SKILL.md"
    broken.parent.mkdir(parents=True)
    broken.write_text("---\nname: broken\n---\n", encoding="utf-8")
    real_read = Path.read_text

    def flaky_read(path: Path, *args, **kwargs):
        if path == broken:
            raise OSError("boom")
        return real_read(path, *args, **kwargs)

    monkeypatch.setattr(audit, "SKILLS_DIR", skills_dir)
    monkeypatch.setattr(Path, "read_text", flaky_read)

    assert audit.sync_skills([{"text": "opencode provider подключай по докам"}], dry_run=False) == 1
    assert "CREATED" in capsys.readouterr().out
    assert (skills_dir / "opencode-setup" / "SKILL.md").exists()



def test_real_before_after_approval_loop_is_documented_and_enforced(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    state_db = tmp_path / "state.db"
    _make_state_db(
        state_db,
        [
            "запомни на будущее: логи в Telegram только кратко",
            "зачем ты опять возвращаешь старый закрытый вопрос",
        ],
    )
    user_md = tmp_path / "USER.md"
    memory_md = tmp_path / "MEMORY.md"
    before_user = "Нико профиль\n§\n"
    before_memory = "АНТИПАТТЕРНЫ\n§\n"
    user_md.write_text(before_user, encoding="utf-8")
    memory_md.write_text(before_memory, encoding="utf-8")

    monkeypatch.setattr(audit, "STATE_DB", state_db)
    monkeypatch.setattr(audit, "USER_MD", user_md)
    monkeypatch.setattr(audit, "MEMORY_MD", memory_md)
    monkeypatch.setattr(audit, "SKILLS_DIR", tmp_path / "skills")
    monkeypatch.setattr(audit, "SNAPSHOT_DIR", tmp_path / "snapshots")

    assert audit.run_pipeline(mode="full", dry_run=True) is True
    dry_run_output = capsys.readouterr().out
    assert "DRY-RUN: would update USER.md and MEMORY.md" in dry_run_output
    assert "New (non-duplicate) corrections: 2" in dry_run_output
    assert user_md.read_text(encoding="utf-8") == before_user
    assert memory_md.read_text(encoding="utf-8") == before_memory
    assert not list((tmp_path / "snapshots").glob("*.bak"))

    assert audit.run_pipeline(mode="full", dry_run=False) is True
    execute_output = capsys.readouterr().out
    after_user = user_md.read_text(encoding="utf-8")
    after_memory = memory_md.read_text(encoding="utf-8")

    assert "Snapshot saved:" in execute_output
    assert "Created new corrections section" in execute_output
    assert "запомни на будущее: логи в Telegram только кратко" in after_user
    assert "зачем ты опять возвращаешь старый закрытый вопрос" in after_user
    assert "логи/уведомления" in after_memory
    assert "повтор старого" in after_memory
    assert list((tmp_path / "snapshots").glob("USER.md.*.bak"))
    assert list((tmp_path / "snapshots").glob("MEMORY.md.*.bak"))

    evidence = Path("docs/before-after-approval.md").read_text(encoding="utf-8")
    assert "## BEFORE" in evidence
    assert "## APPROVAL" in evidence
    assert "## AFTER" in evidence
    assert "self-ershov-memory --dry-run --full" in evidence
    assert "self-ershov-memory --execute --full" in evidence
    assert "BEFORE files are unchanged after dry-run" in evidence

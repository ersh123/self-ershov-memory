#!/usr/bin/env python3
"""Compatibility facade for the self-ershov-memory CLI.

The implementation is split into focused modules:
- context.py: path/limit configuration
- db.py: SQLite reads
- cleaner.py: dialogue cleanup
- analyzer.py: correction extraction and dedup
- memory_store.py: USER.md/MEMORY.md IO and snapshots
- skills.py: skill sync
- runner.py: pipeline orchestration
"""

from __future__ import annotations

from pathlib import Path

from .analyzer import (
    classify_topic as classify_topic,
    find_corrections as find_corrections,
    format_corrections_entry as format_corrections_entry,
    is_duplicate as is_duplicate,
    normalize_for_dedup as normalize_for_dedup,
    semantic_tokens as semantic_tokens,
)
from .cleaner import clean_content as clean_content
from .cleaner import is_machine_noise_line as is_machine_noise_line
from .context import AuditContext, default_skill_topics
from .db import fetch_user_messages as _fetch_user_messages
from .db import connect_db as _connect_db
from .memory_store import (
    compress_corrections_section as compress_corrections_section,
    find_antipatterns_section as find_antipatterns_section,
    find_corrections_section as find_corrections_section,
    parse_existing_corrections as parse_existing_corrections,
    read_memory_sections as read_memory_sections,
    write_sections as write_sections,
)
from .memory_store import snapshot as _snapshot
from .memory_store import validate_memory_files as _validate_memory_files
from .runner import run_pipeline as _run_pipeline
from .skills import sync_skills as _sync_skills

HOME = Path.home()
STATE_DB = HOME / ".hermes" / "state.db"
MEMORIES = HOME / ".hermes" / "memories"
USER_MD = MEMORIES / "USER.md"
MEMORY_MD = MEMORIES / "MEMORY.md"
SNAPSHOT_DIR = MEMORIES / "snapshots"
SKILLS_DIR = HOME / ".hermes" / "skills"

USER_LIMIT = 4000
MEMORY_LIMIT = 8000
SKILL_TOPICS = default_skill_topics()


def log(msg):
    print(f"[self-audit] {msg}")


def current_context() -> AuditContext:
    """Build context from legacy module globals so old monkeypatch tests still work."""
    return AuditContext(
        state_db=STATE_DB,
        user_md=USER_MD,
        memory_md=MEMORY_MD,
        snapshot_dir=SNAPSHOT_DIR,
        skills_dir=SKILLS_DIR,
        user_limit=USER_LIMIT,
        memory_limit=MEMORY_LIMIT,
        skill_topics=SKILL_TOPICS,
    )


def connect_db(context: AuditContext | None = None):
    return _connect_db(current_context() if context is None else context, log=log)


def fetch_user_messages(conn, days=1):
    return _fetch_user_messages(conn, days=days)


def snapshot(path, context: AuditContext | None = None):
    return _snapshot(
        path, context=current_context() if context is None else context, log=log
    )


def validate_memory_files(context: AuditContext | None = None):
    return _validate_memory_files(current_context() if context is None else context)


def sync_skills(corrections, dry_run=True, context: AuditContext | None = None):
    return _sync_skills(
        corrections,
        context=current_context() if context is None else context,
        dry_run=dry_run,
        log=log,
    )


def run_pipeline(mode="quick", dry_run=True, context: AuditContext | None = None):
    return _run_pipeline(
        current_context() if context is None else context,
        mode=mode,
        dry_run=dry_run,
        log=log,
    )


def main(argv=None):
    import sys

    args = set(sys.argv[1:] if argv is None else argv)
    if "--help" in args or "-h" in args:
        print("self-ershov-memory — dialog-driven Hermes memory self-audit")
        print("Usage: self-ershov-memory [--dry-run|--execute] [--quick|--full]")
        print("Default: --dry-run --quick")
        return 0
    mode = "full" if "--full" in args else "quick"
    dry_run = "--dry-run" in args or "--execute" not in args
    success = run_pipeline(mode=mode, dry_run=dry_run)
    return 0 if success else 1


if __name__ == "__main__":
    import sys

    sys.exit(main())

from __future__ import annotations

from .analyzer import (
    classify_topic,
    find_corrections,
    format_corrections_entry,
    is_duplicate,
)
from .context import AuditContext
from .db import connect_db, fetch_user_messages
from .memory_store import (
    compress_corrections_section,
    find_antipatterns_section,
    find_corrections_section,
    parse_existing_corrections,
    read_memory_sections,
    snapshot,
    validate_memory_files,
    write_sections,
)
from .skills import sync_skills


def run_pipeline(context: AuditContext, mode="quick", dry_run=True, log=print):
    """Главный пайплайн: quick=24h, full=30d."""
    log(f"=== self-audit {mode} mode {'DRY-RUN' if dry_run else 'EXECUTE'} ===")
    conn = connect_db(context, log)
    if not conn:
        return False

    days = 1 if mode == "quick" else 30
    messages = fetch_user_messages(conn, days)
    log(f"Fetched {len(messages)} user messages (last {days} days)")
    if not messages:
        log("No messages found, nothing to audit")
        conn.close()
        return True

    corrections = find_corrections(messages)
    log(f"Found {len(corrections)} potential corrections/instructions")
    user_sections = read_memory_sections(context.user_md)
    memory_sections = read_memory_sections(context.memory_md)
    existing_norms, _existing_labels = parse_existing_corrections(user_sections)
    new_corrections = [
        correction
        for correction in corrections
        if not is_duplicate(correction["text"], existing_norms)
    ]
    log(f"New (non-duplicate) corrections: {len(new_corrections)}")

    if not new_corrections:
        _handle_no_new_corrections(
            context, corrections, user_sections, dry_run=dry_run, log=log
        )
        conn.close()
        return True

    _log_new_corrections(new_corrections, log=log)
    if dry_run:
        log("DRY-RUN: would update USER.md and MEMORY.md")
        log("--- Skills check (dry-run) ---")
        sync_skills(corrections, context=context, dry_run=True, log=log)
        conn.close()
        return True

    snapshot(context.user_md, context=context, log=log)
    snapshot(context.memory_md, context=context, log=log)
    _apply_user_corrections(context, user_sections, new_corrections, log=log)
    _apply_memory_antipatterns(context, memory_sections, new_corrections)
    _validate_after_write(context, log=log)
    sync_skills(corrections, context=context, dry_run=False, log=log)
    conn.close()
    log("Pipeline complete.")
    return True


def _handle_no_new_corrections(
    context: AuditContext, corrections, user_sections, dry_run=True, log=print
):
    log("No new corrections found. Checking compression needs...")
    if not dry_run:
        user_compressed, removed = compress_corrections_section(user_sections)
        if removed > 0:
            write_sections(context.user_md, user_compressed)
            log(f"Compressed USER.md: removed {removed} duplicate lines")
        issues = validate_memory_files(context)
        if issues:
            for issue in issues:
                log(f"WARN: {issue}")
    if dry_run:
        log("--- Skills check (dry-run) ---")
    sync_skills(corrections, context=context, dry_run=dry_run, log=log)


def _log_new_corrections(new_corrections, log=print):
    log("--- New corrections ---")
    for correction in new_corrections[:10]:
        preview = correction["text"].replace("\n", " | ")[:120]
        log(f"  [{correction.get('type', 'correction')}] {preview}")
    if len(new_corrections) > 10:
        log(f"  ... and {len(new_corrections) - 10} more")


def _apply_user_corrections(
    context: AuditContext, user_sections, new_corrections, log=print
):
    new_corrections_text = format_corrections_entry(new_corrections)
    correction_idx = find_corrections_section(user_sections)
    if correction_idx is None:
        user_sections.insert(-1, new_corrections_text)
        write_sections(context.user_md, user_sections)
        log("Created new corrections section")
        return

    existing_text = user_sections[correction_idx]
    existing_topics = _existing_topics(existing_text)
    added = 0
    new_lines = new_corrections_text.split("\n")
    for bullet in new_lines[1:] if len(new_lines) > 1 else []:
        bullet_stripped = bullet.strip()
        if not bullet_stripped.startswith("- "):
            continue
        bullet_topics = classify_topic(bullet_stripped[2:])
        if bullet_topics & existing_topics:
            continue
        existing_text += "\n" + bullet_stripped
        added += 1
        existing_topics.update(bullet_topics)

    if added > 0:
        user_sections[correction_idx] = existing_text
        write_sections(context.user_md, user_sections)
        log(f"Merged {added} new corrections into existing section")
    else:
        log("All corrections already present, no merge needed")


def _existing_topics(existing_text):
    topics = set()
    for line in existing_text.split("\n"):
        line_stripped = line.strip()
        if line_stripped.startswith("- "):
            topics.update(classify_topic(line_stripped[2:]))
    return topics


def _apply_memory_antipatterns(context: AuditContext, memory_sections, new_corrections):
    anti_idx = find_antipatterns_section(memory_sections)
    error_types = _error_types(new_corrections)
    if not error_types or anti_idx is None:
        return
    anti_text = memory_sections[anti_idx]
    for error_type in error_types:
        if error_type not in anti_text.lower():
            anti_text += f"\n- {error_type}"
    memory_sections[anti_idx] = anti_text
    write_sections(context.memory_md, memory_sections)


def _error_types(new_corrections):
    error_types = set()
    for correction in new_corrections:
        text_lower = correction["text"].lower()
        if "лог" in text_lower or "diff" in text_lower or "уведомл" in text_lower:
            error_types.add("логи/уведомления")
        if "назван" in text_lower or "имен" in text_lower:
            error_types.add("названия клиентов")
        if "повтор" in text_lower or "старый" in text_lower or "опять" in text_lower:
            error_types.add("повтор старого")
        if "ресерч" in text_lower or "гугл" in text_lower or "провер" in text_lower:
            error_types.add("поверхностный ресерч")
        if (
            "vps" in text_lower
            or "desktop" in text_lower
            or "инстанс" in text_lower
            or "пк" in text_lower
        ):
            error_types.add("путаница VPS/Desktop")
    return error_types


def _validate_after_write(context: AuditContext, log=print):
    issues = validate_memory_files(context)
    if not issues:
        log("✅ Validation passed: both files within limits and valid format")
        return

    log("VALIDATION ISSUES:")
    for issue in issues:
        log(f"  ⚠️  {issue}")
    if any("USER.md" in issue for issue in issues):
        user_sections = read_memory_sections(context.user_md)
        user_sections, removed = compress_corrections_section(user_sections)
        write_sections(context.user_md, user_sections)
        log(f"Auto-compressed USER.md: removed {removed} lines")
    if any("MEMORY.md" in issue for issue in issues):
        log("MEMORY.md over limit — manual review needed")

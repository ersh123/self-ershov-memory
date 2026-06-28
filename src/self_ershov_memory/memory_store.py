from __future__ import annotations

import re
import shutil
from datetime import datetime
from pathlib import Path

from .context import AuditContext


def read_memory_sections(path: Path):
    """Читает секции USER/MEMORY.md, разделённые §."""
    if not path.exists():
        return []
    sections = path.read_text().split("§")
    return [section.strip() for section in sections if section.strip()]


def write_sections(path: Path, sections):
    """Записывает секции обратно."""
    content = "\n§\n".join(sections) + "\n§\n"
    path.write_text(content)


def find_corrections_section(sections):
    """Найти индекс секции КОРРЕКЦИИ."""
    for index, section in enumerate(sections):
        if section.startswith("КОРРЕКЦИИ ОТ НИКО") or section.startswith(
            "КОРРЕКЦИИ ОТ НИКО (self-audit"
        ):
            return index
    return None


def find_antipatterns_section(sections):
    """Найти индекс секции АНТИПАТТЕРНЫ."""
    for index, section in enumerate(sections):
        if section.startswith("ГЛАВНЫЙ АНТИПАТТЕРН") or section.startswith(
            "АНТИПАТТЕРНЫ"
        ):
            return index
    return None


def parse_existing_corrections(sections):
    """Извлечь существующие коррекции из секции."""
    index = find_corrections_section(sections)
    if index is None:
        return set(), set()
    text = sections[index]
    items = set(re.findall(r"\*\*(.+?)\*\*", text))
    norms = {item.lower().strip() for item in items}
    for line in re.findall(r"^- (.+)", text, re.MULTILINE):
        essence = re.split(r"[—–•]", line)[0].strip()
        if essence:
            norms.add(essence.lower().strip())
    return norms, items


def snapshot(path: Path, context: AuditContext, log):
    """Сделать снапшот перед изменениями."""
    if not path.exists():
        return None
    context.snapshot_dir.mkdir(parents=True, exist_ok=True)
    backup = (
        context.snapshot_dir
        / f"{path.name}.{datetime.now().strftime('%Y%m%d_%H%M%S')}.bak"
    )
    shutil.copy2(path, backup)
    log(f"Snapshot saved: {backup}")
    return None


def validate_memory_files(context: AuditContext):
    """Проверить что файлы в порядке."""
    issues = []
    if context.user_md.exists():
        size = len(context.user_md.read_text())
        if size > context.user_limit:
            issues.append(f"USER.md: {size} > {context.user_limit} chars")
    if context.memory_md.exists():
        size = len(context.memory_md.read_text())
        if size > context.memory_limit:
            issues.append(f"MEMORY.md: {size} > {context.memory_limit} chars")
    return issues


def compress_corrections_section(sections):
    """Сжать секцию коррекций если слишком большая."""
    index = find_corrections_section(sections)
    if index is None:
        return sections, 0
    lines = sections[index].split("\n")
    if len(lines) < 30:
        return sections, 0

    header = lines[:1]
    body = lines[1:]
    new_body = []
    seen_keys = set()
    for line in body:
        key_match = re.match(r"-\s*\*\*(.+?)\*\*", line)
        if key_match:
            key = key_match.group(1).lower().strip()
            if key in seen_keys:
                continue
            seen_keys.add(key)
        new_body.append(line)

    sections[index] = "\n".join(header + new_body)
    return sections, len(body) - len(new_body)

#!/usr/bin/env python3
"""
self-audit.py — Debi self-audit pipeline.

Режимы:
  --dry-run     : показать что изменится, ничего не писать
  --execute     : реально применить изменения
  --quick       : режим A (24 часа)
  --full        : режим B (30 дней)

Без флагов = --dry-run --quick
"""
import sqlite3
import re
import shutil
from difflib import SequenceMatcher
from datetime import datetime, timezone
from pathlib import Path

HOME = Path.home()
STATE_DB = HOME / ".hermes" / "state.db"
MEMORIES = HOME / ".hermes" / "memories"
USER_MD = MEMORIES / "USER.md"
MEMORY_MD = MEMORIES / "MEMORY.md"
SNAPSHOT_DIR = MEMORIES / "snapshots"
SKILLS_DIR = HOME / ".hermes" / "skills"

USER_LIMIT = 4000
MEMORY_LIMIT = 8000

# Маппинг тем → скиллы для авто-создания/обновления
SKILL_TOPICS = {
    "vibe-coding": {"skill": "vibe-coding", "label": "Vibe Coding"},
    "opencode": {"skill": "opencode-setup", "label": "OpenCode Setup"},
    "ресерч": {"skill": "deep-research", "label": "Deep Research"},
    "скиллы": {"skill": "skill-quality", "label": "Skill Quality"},
    "deepseek": {"skill": "deepseek-setup", "label": "DeepSeek Setup"},
}

def log(msg):
    print(f"[self-audit] {msg}")

def connect_db():
    if not STATE_DB.exists():
        log(f"ERROR: state.db not found at {STATE_DB}")
        return None
    conn = sqlite3.connect(str(STATE_DB))
    conn.row_factory = sqlite3.Row
    return conn

def fetch_user_messages(conn, days=1):
    cutoff = datetime.now(timezone.utc).timestamp() - days * 86400
    cursor = conn.execute("""
        SELECT m.content, m.timestamp, s.title
        FROM messages m
        JOIN sessions s ON m.session_id = s.id
        WHERE s.source='telegram'
          AND m.role='user'
          AND s.started_at > ?
        ORDER BY m.timestamp DESC
    """, (cutoff,))
    return [row for row in cursor.fetchall() if row["content"]]

def clean_content(text):
    """Убрать контекст-компрешн блоки и артефакты."""
    if not text:
        return ""
    if not isinstance(text, str):
        return ""
    # Убрать маркеры контекст-компрешна (разные форматы)
    text = re.sub(r'(?s)\[CONTEXT COMPACTION.*?(?:--- END OF CONTEXT SUMMARY ---|END OF CONTEXT SUMMARY).*?(?:\n|$)', '', text)
    # Убрать однострочные маркеры
    text = re.sub(r'^\[CONTEXT COMPACTION.*$', '', text, flags=re.MULTILINE)
    text = re.sub(r'^--- END OF CONTEXT SUMMARY.*$', '', text, flags=re.MULTILINE)
    # Убрать блоки "Historical Task Snapshot" etc
    text = re.sub(r'(?s)## Historical (Task Snapshot|In-Progress|Pending|Remaining|Critical).*?(?=\n## |\n---|$)', '', text)
    # Убрать блоки "Last Dropped Turns"
    text = re.sub(r'(?s)## Last Dropped Turns.*?(?=\n## |\n---|$)', '', text)
    # Убрать блоки "Active State", "Blocked", "Key Decisions", "Resolved Questions"
    text = re.sub(r'(?s)## (Active State|Blocked|Key Decisions|Resolved Questions).*?(?=\n## |\n---|$)', '', text)
    # Убрать вложения [The user sent...
    text = re.sub(r'(?s)\[The user sent.*?\].*?(?:\n|$)', '', text)
    # Убрать системные промпты
    text = re.sub(r'(?s)User asked:.*?(?:\n|$)', '', text)
    text = re.sub(r'(?s)Session source:.*?(?:\n|$)', '', text)
    # Убрать [If you need a closer look... типы технических рекомендаций
    text = re.sub(r'(?s)\[If you need.*?\].*?(?:\n|$)', '', text)
    # Убрать машинные артефакты, но сохранить английские коррекции, команды и код.
    lines = text.split('\n')
    cleaned = []
    for line in lines:
        stripped = line.strip()
        if stripped and is_machine_noise_line(stripped):
            continue
        cleaned.append(line)
    text = '\n'.join(cleaned)
    return text.strip()


def is_machine_noise_line(line):
    """Return True for serialized tool/attachment noise, not human English/code."""
    if len(line) <= 100:
        return False
    lower = line.lower()
    if line.startswith(("{", "[")) and any(
        marker in lower
        for marker in (
            '"tool"',
            '"data"',
            '"image_url"',
            '"screenshot"',
            '"content"',
            "vision_analyze",
        )
    ):
        return True
    alpha_chars = len(re.findall(r'[A-Za-zА-Яа-яЁё]', line))
    dense_structural = sum(line.count(ch) for ch in '{}[]":,')
    if dense_structural > 30 and alpha_chars / max(len(line), 1) < 0.35:
        return True
    if len(line) > 300 and " " not in line:
        return True
    return False

def classify_topic(text):
    """Классифицировать коррекцию по теме."""
    tl = text.lower()
    topics = set()
    if any(w in tl for w in ["лог", "diff", "уведомл", "обновлен"]):
        topics.add("логи")
    if any(w in tl for w in ["повтор", "опять", "снова", "старый"]):
        topics.add("повтор")
    if any(w in tl for w in ["иишно", "ai", "слоп", "рад помочь"]):
        topics.add("ai-слоп")
    if any(w in tl for w in ["назван", "руслан", "рослайн", "атс"]):
        topics.add("названия")
    if any(w in tl for w in ["ресерч", "гугл", "поиск"]):
        topics.add("ресерч")
    if any(w in tl for w in ["очевидн", "переспраш"]):
        topics.add("очевидное")
    if any(w in tl for w in ["deepseek", "дипсик", "омнироут"]):
        topics.add("deepseek")
    if any(w in tl for w in ["договор", "1.2.2", "пункт", "обращений"]):
        topics.add("договоры")
    if any(w in tl for w in ["opencode", "опенкод", "провайдер"]):
        topics.add("opencode")
    if any(w in tl for w in ["vibe", "coding", "программир"]):
        topics.add("vibe-coding")
    if any(w in tl for w in ["скилл", "скил"]):
        topics.add("скиллы")
    if any(w in tl for w in ["скриншот", "картинк"]):
        topics.add("скриншоты")
    return topics or {"other"}

def find_corrections(messages):
    """
    Искать коррекции в user-сообщениях.
    Возвращает список коррекций.
    
    КОРРЕКЦИИ = жалобы, критика, «не так», «зачем ты», исправления поведения.
    ИНСТРУКЦИИ = правила, конвенции, настройки на будущее (не просто задачи).
    """
    correction_patterns = [
        r'(?:не|нельзя|прекрати|перестань|хватит)\s+(?:надо|нужно|следует)\s+(?:было|делать)',
        r'(?:зачем|почему|нахуя)\s+ты\s+(?:это|так|опять|снова|мне|эту)',
        r'я\s+же\s+(?:тебе|просил|говорил|сказал|писал|объяснял)',
        r'(?:ошиб|неправильн|не так|не то|не туда|не верно|некорректн)',
        r'ты\s+(?:чё|чего|что)\s+(?:творишь|вытворяешь|делаешь|несёшь)',
        r'почему\s+ты\s+(?:не\s+)?(?:сделал|написал|проверил|посмотрел|удалил)',
        r'сука\s+(?:зачем|почему|опять)',
        r'блять\s+(?:ну\s+)?(?:зачем|почему|опять|ты)',
        r'(?:опять|снова)\s+(?:ты|это|зачем|одно\s+и\s+то\s+же)',
    ]
    
    # Инструкции = долгосрочные правила, не одноразовые задачи
    rule_patterns = [
        r'(?:запомни|запиши|сохрани|учти)\s+на\s+будущее',
        r'(?:всегда|никогда|отныне|впредь)\s+(?:делай|используй|пиши|проверяй)',
        r'(?:должен|обязан|нужно)\s+(?:всегда|теперь|отныне)',
        r'правило|конвенци|договорённость',
    ]
    
    corrections = []
    seen_normalized = set()
    
    for msg in messages:
        text = clean_content(msg["content"])
        if not text or len(text) < 10:
            continue
            
        session_title = msg["title"] if "title" in msg and msg["title"] else ""
        ts = msg["timestamp"] if "timestamp" in msg else 0
        
        # Сначала ищем коррекции
        is_correction = False
        for pat in correction_patterns:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                norm = text[:200].lower().strip()
                if norm not in seen_normalized:
                    seen_normalized.add(norm)
                    corrections.append({
                        "text": text[:300],
                        "norm": norm,
                        "session": session_title,
                        "timestamp": ts,
                        "type": "correction"
                    })
                is_correction = True
                break
        
        if is_correction:
            continue
        
        # Потом ищем правила (не задачи, а конвенции)
        for pat in rule_patterns:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                norm = text[:200].lower().strip()
                if norm not in seen_normalized:
                    seen_normalized.add(norm)
                    corrections.append({
                        "text": text[:300],
                        "norm": norm,
                        "session": session_title,
                        "timestamp": ts,
                        "type": "rule"
                    })
                break
                    
    return corrections

def read_memory_sections(path):
    """Читает секции USER/MEMORY.md, разделённые §."""
    if not path.exists():
        return []
    content = path.read_text()
    sections = content.split("§")
    return [s.strip() for s in sections if s.strip()]

def write_sections(path, sections):
    """Записывает секции обратно."""
    content = "\n§\n".join(sections) + "\n§\n"
    path.write_text(content)

def find_corrections_section(sections):
    """Найти индекс секции КОРРЕКЦИИ."""
    for i, s in enumerate(sections):
        if s.startswith("КОРРЕКЦИИ ОТ НИКО") or s.startswith("КОРРЕКЦИИ ОТ НИКО (self-audit"):
            return i
    return None

def find_antipatterns_section(sections):
    """Найти индекс секции АНТИПАТТЕРНЫ."""
    for i, s in enumerate(sections):
        if s.startswith("ГЛАВНЫЙ АНТИПАТТЕРН") or s.startswith("АНТИПАТТЕРНЫ"):
            return i
    return None

def parse_existing_corrections(sections):
    """Извлечь существующие коррекции из секции."""
    idx = find_corrections_section(sections)
    if idx is None:
        return set(), set()
    text = sections[idx]
    # Ищем маркдаун-список
    items = set(re.findall(r'\*\*(.+?)\*\*', text))
    norms = set()
    for item in items:
        norms.add(item.lower().strip())
    # Также ищем целые строки списка
    lines = re.findall(r'^- (.+)', text, re.MULTILINE)
    for line in lines:
        # Извлекаем суть: первая фраза до тире/двоеточия
        essence = re.split(r'[—–•]', line)[0].strip()
        if essence:
            norms.add(essence.lower().strip())
    return norms, items

def normalize_for_dedup(text):
    """Normalize memory correction text for fuzzy deduplication."""
    text = re.sub(r'[`*_>#+\-]', ' ', text.lower())
    text = re.sub(r'[^0-9a-zа-яё]+', ' ', text)
    return re.sub(r'\s+', ' ', text).strip()


def semantic_tokens(text):
    """Tokens worth comparing for correction deduplication."""
    stopwords = {
        "и", "в", "во", "на", "не", "но", "а", "я", "ты", "это", "как", "что",
        "the", "a", "an", "to", "of", "in", "on", "and", "or", "not", "do", "don",
    }
    return [tok for tok in normalize_for_dedup(text).split() if len(tok) > 2 and tok not in stopwords]


def is_duplicate(new_text, existing_norms):
    """Проверить, дублируется ли новая коррекция без потери уточняющих правил."""
    new_norm = normalize_for_dedup(new_text)
    if not new_norm:
        return False
    new_tokens = semantic_tokens(new_norm)
    new_set = set(new_tokens)
    for existing in existing_norms:
        existing_norm = normalize_for_dedup(existing)
        if not existing_norm:
            continue
        if new_norm == existing_norm:
            return True
        ratio = SequenceMatcher(None, new_norm, existing_norm).ratio()
        if ratio >= 0.86:
            return True
        existing_tokens = semantic_tokens(existing_norm)
        existing_set = set(existing_tokens)
        if not existing_set or not new_set:
            continue
        shared = existing_set & new_set
        # Very short topic labels in memory (for example "повтор старого") should
        # still suppress obvious expansions, but imperative rules can be refined.
        action_tokens = {
            "используй", "делай", "пиши", "проверяй", "добавляй", "удаляй",
            "use", "write", "check", "add", "remove", "keep", "drop",
        }
        if len(existing_set) >= 3 and existing_set <= new_set:
            return True
        if len(new_set) >= 3 and new_set <= existing_set:
            return True
        if len(existing_set) <= 2 and existing_set <= new_set and not (existing_set & action_tokens):
            return True
        if len(new_set) <= 2 and new_set <= existing_set and not (new_set & action_tokens):
            return True
        if len(shared) >= 4 and len(shared) / max(len(existing_set), len(new_set)) >= 0.8:
            return True
    return False

def format_corrections_entry(corrections):
    """Форматирует список коррекций для USER.md в читаемом виде."""
    date_str = datetime.now().strftime("%Y-%m-%d")
    lines = [f"КОРРЕКЦИИ ОТ НИКО (self-audit {date_str})"]
    
    for c in corrections:
        text = c["text"]
        
        # Извлекаем суть из полного текста
        # Отрезаем первые 100-200 символов, очищаем
        essence = clean_content(text)
        if not essence:
            continue
        
        # Убираем шум в начале
        essence = re.sub(r'^(?:\[\d+\.\d+\.\d+ \d+:\d+\]\s*)?Никита:\s*', '', essence)
        essence = essence.strip().rstrip('|').strip()
        
        # Убираем дублирующиеся пробелы и символы разделения
        essence = re.sub(r'\s*\|\s*', ' | ', essence)
        essence = re.sub(r' {2,}', ' ', essence)
        
        # Обрезаем
        if len(essence) > 160:
            essence = essence[:157] + "..."
        
        if not essence:
            continue
            
        lines.append(f"- {essence}")
    
    return "\n".join(lines)

def snapshot(path):
    """Сделать снапшот перед изменениями."""
    if not path.exists():
        return
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    bak = SNAPSHOT_DIR / f"{path.name}.{ts}.bak"
    shutil.copy2(path, bak)
    log(f"Snapshot saved: {bak}")

def validate_memory_files():
    """Проверить что файлы в порядке."""
    issues = []
    
    if USER_MD.exists():
        size = len(USER_MD.read_text())
        if size > USER_LIMIT:
            issues.append(f"USER.md: {size} > {USER_LIMIT} chars")
    
    if MEMORY_MD.exists():
        size = len(MEMORY_MD.read_text())
        if size > MEMORY_LIMIT:
            issues.append(f"MEMORY.md: {size} > {MEMORY_LIMIT} chars")
    
    return issues

def compress_corrections_section(sections):
    """Сжать секцию коррекций если слишком большая."""
    idx = find_corrections_section(sections)
    if idx is None:
        return sections, 0
    
    text = sections[idx]
    lines = text.split("\n")
    
    # Если меньше 30 строк — не надо
    if len(lines) < 30:
        return sections, 0
    
    # Оставляем первые 10 и последние 10 строк
    header = lines[:1]  # заголовок "КОРРЕКЦИИ ОТ НИКО..."
    body = lines[1:]
    
    # Группируем по темам
    themes = {}
    for line in body:
        line = line.strip()
        if not line.startswith("-"):
            continue
        # Извлекаем ключевое слово
        key_match = re.match(r'-\s*\*\*(.+?)\*\*', line)
        if key_match:
            key = key_match.group(1).lower().strip()
            if key in themes:
                themes[key].append(line)
            else:
                themes[key] = [line]
    
    # Сворачиваем: если тема повторяется >2 раз → обобщаем
    new_body = []
    seen_keys = set()
    for line in body:
        key_match = re.match(r'-\s*\*\*(.+?)\*\*', line)
        if key_match:
            key = key_match.group(1).lower().strip()
            if key in seen_keys:
                continue  # пропускаем дубль
            seen_keys.add(key)
        new_body.append(line)
    
    sections[idx] = "\n".join(header + new_body)
    return sections, len(body) - len(new_body)

def sync_skills(corrections, dry_run=True):
    """Создать/обновить скиллы на основе найденных коррекций."""
    updated = 0
    created = 0
    
    # Собираем уникальные темы из коррекций
    topics_found = set()
    for c in corrections:
        topics = classify_topic(c["text"])
        topics_found.update(topics)
    
    # Маппим темы в скиллы
    for topic in topics_found:
        if topic not in SKILL_TOPICS:
            continue
        skill_info = SKILL_TOPICS[topic]
        skill_name = skill_info["skill"]
        
        # Ищем скилл в любой категории (рекурсивно)
        exists = False
        for sk_path in SKILLS_DIR.rglob("SKILL.md"):
            try:
                content = sk_path.read_text()
                if f"name: {skill_name}" in content:
                    exists = True
                    skill_dir = sk_path.parent
                    skill_path = sk_path
                    break
            except:
                continue
        
        if not exists:
            skill_dir = SKILLS_DIR / skill_name
            skill_path = skill_dir / "SKILL.md"
        
        if exists:
            if dry_run:
                log(f"  SKILL {skill_name}: exists, would check for updates")
                continue
            # Скилл уже есть — проверим не пора ли обновить
            # (пока только проверяем существование, content update в будущем)
            log(f"  SKILL {skill_name}: exists, up-to-date")
            continue
        
        if dry_run:
            created += 1
            log(f"  SKILL {skill_name}: would CREATE (topic: {topic})")
            continue
        
        # EXECUTE: создаём новый скилл
        skill_dir.mkdir(parents=True, exist_ok=True)
        content = f"""---
name: {skill_name}
description: Auto-generated by self-audit from dialog analysis.
---

# {skill_info['label']}

Авто-сгенерирован {datetime.now().strftime('%Y-%m-%d')} на основе анализа диалогов с Нико.

## Контекст
Создан по результатам self-audit. Тема: {topic}.

## Правила
- Следовать указаниям Нико по этой теме
- Обновлять при новых находках в диалогах
"""
        skill_path.write_text(content)
        created += 1
        log(f"  SKILL {skill_name}: CREATED (topic: {topic})")
    
    if dry_run:
        if created == 0 and updated == 0:
            log("  Skills: no changes needed")
        elif created > 0:
            log(f"  Skills: {created} would be CREATED")
    else:
        if created > 0 or updated > 0:
            log(f"  Skills: {created} created, {updated} updated")
        else:
            log("  Skills: all up-to-date")
    return created + updated

def run_pipeline(mode="quick", dry_run=True):
    """
    Главный пайплайн.
    mode: 'quick' (24ч) или 'full' (30д)
    dry_run: True = только показать, False = применить
    """
    log(f"=== self-audit {mode} mode {'DRY-RUN' if dry_run else 'EXECUTE'} ===")
    
    conn = connect_db()
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
    
    # Читаем существующие файлы
    user_sections = read_memory_sections(USER_MD)
    memory_sections = read_memory_sections(MEMORY_MD)
    
    # Проверяем dedup
    existing_norms, existing_labels = parse_existing_corrections(user_sections)
    new_corrections = [c for c in corrections if not is_duplicate(c["text"], existing_norms)]
    log(f"New (non-duplicate) corrections: {len(new_corrections)}")
    
    if not new_corrections:
        log("No new corrections found. Checking compression needs...")
        # Всё равно проверить надо ли сжать
        if not dry_run:
            user_compressed, removed = compress_corrections_section(user_sections)
            if removed > 0:
                write_sections(USER_MD, user_compressed)
                log(f"Compressed USER.md: removed {removed} duplicate lines")
            issues = validate_memory_files()
            if issues:
                for i in issues:
                    log(f"WARN: {i}")
        # Всё равно проверяем скиллы (могут быть новые темы от старых коррекций)
        if dry_run:
            log("--- Skills check (dry-run) ---")
        sync_skills(corrections, dry_run=dry_run)
        conn.close()
        return True
    
    # Показываем что нашли
    log("--- New corrections ---")
    for c in new_corrections[:10]:
        preview = c["text"].replace("\n", " | ")[:120]
        log(f"  [{c.get('type', 'correction')}] {preview}")
    if len(new_corrections) > 10:
        log(f"  ... and {len(new_corrections)-10} more")
    
    if dry_run:
        log("DRY-RUN: would update USER.md and MEMORY.md")
        log("--- Skills check (dry-run) ---")
        sync_skills(corrections, dry_run=True)
        conn.close()
        return True
    
    # EXECUTE: применяем изменения
    # Снапшоты
    snapshot(USER_MD)
    snapshot(MEMORY_MD)
    
    # Форматируем новые коррекции
    new_corrections_text = format_corrections_entry(new_corrections)
    
    # ДОБАВЛЯЕМ только новые коррекции к существующим, не заменяем
    correction_idx = find_corrections_section(user_sections)
    if correction_idx is not None:
        # Читаем существующие bullet points
        existing_text = user_sections[correction_idx]
        existing_lines = existing_text.split("\n")
        # Собираем темы существующих правил
        existing_topics = set()
        for line in existing_lines:
            line_stripped = line.strip()
            if line_stripped.startswith("- "):
                topics = classify_topic(line_stripped[2:])
                existing_topics.update(topics)
        
        # Новые bullet points (после заголовка)
        new_lines = new_corrections_text.split("\n")
        new_bullets = new_lines[1:] if len(new_lines) > 1 else []
        
        # Добавляем только те, чьи темы ещё не покрыты
        added = 0
        for bullet in new_bullets:
            bullet_stripped = bullet.strip()
            if not bullet_stripped.startswith("- "):
                continue
            bullet_text = bullet_stripped[2:]
            bullet_topics = classify_topic(bullet_text)
            # Если тема уже есть — пропускаем
            if bullet_topics & existing_topics:
                continue
            existing_text += "\n" + bullet_stripped
            added += 1
            existing_topics.update(bullet_topics)
        
        if added > 0:
            user_sections[correction_idx] = existing_text
            write_sections(USER_MD, user_sections)
            log(f"Merged {added} new corrections into existing section")
        else:
            log("All corrections already present, no merge needed")
    else:
        # Нет существующей секции — добавляем новую
        user_sections.insert(-1, new_corrections_text)
        write_sections(USER_MD, user_sections)
        log("Created new corrections section")
    
    # Добавляем антипаттерны в MEMORY.md
    anti_idx = find_antipatterns_section(memory_sections)
    # Собираем типы ошибок
    error_types = set()
    for c in new_corrections:
        text_lower = c["text"].lower()
        if "лог" in text_lower or "diff" in text_lower or "уведомл" in text_lower:
            error_types.add("логи/уведомления")
        if "назван" in text_lower or "имен" in text_lower:
            error_types.add("названия клиентов")
        if "повтор" in text_lower or "старый" in text_lower or "опять" in text_lower:
            error_types.add("повтор старого")
        if "ресерч" in text_lower or "гугл" in text_lower or "провер" in text_lower:
            error_types.add("поверхностный ресерч")
        if "vps" in text_lower or "desktop" in text_lower or "инстанс" in text_lower or "пк" in text_lower:
            error_types.add("путаница VPS/Desktop")
    
    if error_types and anti_idx is not None:
        anti_text = memory_sections[anti_idx]
        # Добавляем только новые типы
        for et in error_types:
            if et not in anti_text.lower():
                anti_text += f"\n- {et}"
        memory_sections[anti_idx] = anti_text
        write_sections(MEMORY_MD, memory_sections)
    
    # Валидация
    issues = validate_memory_files()
    if issues:
        log("VALIDATION ISSUES:")
        for i in issues:
            log(f"  ⚠️  {i}")
        # Сжать если over
        if any("USER.md" in i for i in issues):
            user_sections = read_memory_sections(USER_MD)
            user_sections, removed = compress_corrections_section(user_sections)
            write_sections(USER_MD, user_sections)
            log(f"Auto-compressed USER.md: removed {removed} lines")
        if any("MEMORY.md" in i for i in issues):
            log("MEMORY.md over limit — manual review needed")
    else:
        log("✅ Validation passed: both files within limits and valid format")
    
    # Синхронизация скиллов по всем найденным темам.
    # Dry-run returns earlier after printing the proposed delta.
    sync_skills(corrections, dry_run=False)
    
    conn.close()
    log("Pipeline complete.")
    return True


def main(argv=None):
    import sys
    args = set(sys.argv[1:] if argv is None else argv)
    if "--help" in args or "-h" in args:
        print("self-ershov-memory — dialog-driven Hermes memory self-audit")
        print("Usage: self-ershov-memory [--dry-run|--execute] [--quick|--full]")
        print("Default: --dry-run --quick")
        return 0
    mode = "full" if "--full" in args else "quick"
    dry_run = "--dry-run" in args or not ("--execute" in args)
    success = run_pipeline(mode=mode, dry_run=dry_run)
    return 0 if success else 1


if __name__ == "__main__":
    import sys
    sys.exit(main())

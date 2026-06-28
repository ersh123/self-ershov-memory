from __future__ import annotations

import re
from datetime import datetime
from difflib import SequenceMatcher

from .cleaner import clean_content


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
    """Искать коррекции и долгосрочные правила в user-сообщениях."""
    correction_patterns = [
        r"(?:не|нельзя|прекрати|перестань|хватит)\s+(?:надо|нужно|следует)\s+(?:было|делать)",
        r"(?:зачем|почему|нахуя)\s+ты\s+(?:это|так|опять|снова|мне|эту)",
        r"я\s+же\s+(?:тебе|просил|говорил|сказал|писал|объяснял)",
        r"(?:ошиб|неправильн|не так|не то|не туда|не верно|некорректн)",
        r"ты\s+(?:чё|чего|что)\s+(?:творишь|вытворяешь|делаешь|несёшь)",
        r"почему\s+ты\s+(?:не\s+)?(?:сделал|написал|проверил|посмотрел|удалил)",
        r"сука\s+(?:зачем|почему|опять)",
        r"блять\s+(?:ну\s+)?(?:зачем|почему|опять|ты)",
        r"(?:опять|снова)\s+(?:ты|это|зачем|одно\s+и\s+то\s+же)",
    ]
    rule_patterns = [
        r"(?:запомни|запиши|сохрани|учти)\s+на\s+будущее",
        r"(?:всегда|никогда|отныне|впредь)\s+(?:делай|используй|пиши|проверяй)",
        r"(?:должен|обязан|нужно)\s+(?:всегда|теперь|отныне)",
        r"правило|конвенци|договорённость",
    ]

    corrections = []
    seen_normalized = set()
    for msg in messages:
        text = clean_content(msg["content"])
        if not text or len(text) < 10:
            continue
        session_title = msg["title"] if "title" in msg and msg["title"] else ""
        ts = msg["timestamp"] if "timestamp" in msg else 0

        is_correction = False
        for pat in correction_patterns:
            if re.search(pat, text, re.IGNORECASE):
                norm = text[:200].lower().strip()
                if norm not in seen_normalized:
                    seen_normalized.add(norm)
                    corrections.append(
                        {
                            "text": text[:300],
                            "norm": norm,
                            "session": session_title,
                            "timestamp": ts,
                            "type": "correction",
                        }
                    )
                is_correction = True
                break
        if is_correction:
            continue

        for pat in rule_patterns:
            if re.search(pat, text, re.IGNORECASE):
                norm = text[:200].lower().strip()
                if norm not in seen_normalized:
                    seen_normalized.add(norm)
                    corrections.append(
                        {
                            "text": text[:300],
                            "norm": norm,
                            "session": session_title,
                            "timestamp": ts,
                            "type": "rule",
                        }
                    )
                break
    return corrections


def normalize_for_dedup(text):
    """Normalize memory correction text for fuzzy deduplication."""
    text = re.sub(r"[`*_>#+\-]", " ", text.lower())
    text = re.sub(r"[^0-9a-zа-яё]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def semantic_tokens(text):
    """Tokens worth comparing for correction deduplication."""
    stopwords = {
        "и",
        "в",
        "во",
        "на",
        "не",
        "но",
        "а",
        "я",
        "ты",
        "это",
        "как",
        "что",
        "the",
        "a",
        "an",
        "to",
        "of",
        "in",
        "on",
        "and",
        "or",
        "not",
        "do",
        "don",
    }
    return [
        tok
        for tok in normalize_for_dedup(text).split()
        if len(tok) > 2 and tok not in stopwords
    ]


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
        if SequenceMatcher(None, new_norm, existing_norm).ratio() >= 0.86:
            return True
        existing_tokens = semantic_tokens(existing_norm)
        existing_set = set(existing_tokens)
        if not existing_set or not new_set:
            continue
        shared = existing_set & new_set
        action_tokens = {
            "используй",
            "делай",
            "пиши",
            "проверяй",
            "добавляй",
            "удаляй",
            "use",
            "write",
            "check",
            "add",
            "remove",
            "keep",
            "drop",
        }
        if len(existing_set) >= 3 and existing_set <= new_set:
            return True
        if len(new_set) >= 3 and new_set <= existing_set:
            return True
        if (
            len(existing_set) <= 2
            and existing_set <= new_set
            and not (existing_set & action_tokens)
        ):
            return True
        if (
            len(new_set) <= 2
            and new_set <= existing_set
            and not (new_set & action_tokens)
        ):
            return True
        if (
            len(shared) >= 4
            and len(shared) / max(len(existing_set), len(new_set)) >= 0.8
        ):
            return True
    return False


def format_corrections_entry(corrections):
    """Форматирует список коррекций для USER.md в читаемом виде."""
    lines = [f"КОРРЕКЦИИ ОТ НИКО (self-audit {datetime.now().strftime('%Y-%m-%d')})"]
    for correction in corrections:
        essence = clean_content(correction["text"])
        if not essence:
            continue
        essence = re.sub(r"^(?:\[\d+\.\d+\.\d+ \d+:\d+\]\s*)?Никита:\s*", "", essence)
        essence = essence.strip().rstrip("|").strip()
        essence = re.sub(r"\s*\|\s*", " | ", essence)
        essence = re.sub(r" {2,}", " ", essence)
        if len(essence) > 160:
            essence = essence[:157] + "..."
        if essence:
            lines.append(f"- {essence}")
    return "\n".join(lines)

from __future__ import annotations

import re


def clean_content(text):
    """Убрать контекст-компрешн блоки и артефакты."""
    if not text:
        return ""
    if not isinstance(text, str):
        return ""
    text = re.sub(
        r"(?s)\[CONTEXT COMPACTION.*?(?:--- END OF CONTEXT SUMMARY ---|END OF CONTEXT SUMMARY).*?(?:\n|$)",
        "",
        text,
    )
    text = re.sub(r"^\[CONTEXT COMPACTION.*$", "", text, flags=re.MULTILINE)
    text = re.sub(r"^--- END OF CONTEXT SUMMARY.*$", "", text, flags=re.MULTILINE)
    text = re.sub(
        r"(?s)## Historical (Task Snapshot|In-Progress|Pending|Remaining|Critical).*?(?=\n## |\n---|$)",
        "",
        text,
    )
    text = re.sub(r"(?s)## Last Dropped Turns.*?(?=\n## |\n---|$)", "", text)
    text = re.sub(
        r"(?s)## (Active State|Blocked|Key Decisions|Resolved Questions).*?(?=\n## |\n---|$)",
        "",
        text,
    )
    text = re.sub(r"(?s)\[The user sent.*?\].*?(?:\n|$)", "", text)
    text = re.sub(r"(?s)User asked:.*?(?:\n|$)", "", text)
    text = re.sub(r"(?s)Session source:.*?(?:\n|$)", "", text)
    text = re.sub(r"(?s)\[If you need.*?\].*?(?:\n|$)", "", text)

    cleaned = []
    for line in text.split("\n"):
        stripped = line.strip()
        if stripped and is_machine_noise_line(stripped):
            continue
        cleaned.append(line)
    return "\n".join(cleaned).strip()


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
    alpha_chars = len(re.findall(r"[A-Za-zА-Яа-яЁё]", line))
    dense_structural = sum(line.count(ch) for ch in '{}[]":,')
    if dense_structural > 30 and alpha_chars / max(len(line), 1) < 0.35:
        return True
    if len(line) > 300 and " " not in line:
        return True
    return False

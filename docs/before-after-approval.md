# Real before → approval → after evidence

This fixture documents the real approval loop tested in CI. It is intentionally small and reproducible.

## Raw dialogue evidence

```text
[USER] запомни на будущее: логи в Telegram только кратко
[USER] зачем ты опять возвращаешь старый закрытый вопрос
```

## BEFORE

`USER.md`:

```markdown
Нико профиль
§
```

`MEMORY.md`:

```markdown
АНТИПАТТЕРНЫ
§
```

## APPROVAL

First run is review-only:

```bash
self-ershov-memory --dry-run --full
```

Expected transcript excerpt:

```text
[self-audit] === self-audit full mode DRY-RUN ===
[self-audit] Found 2 potential corrections/instructions
[self-audit] New (non-duplicate) corrections: 2
[self-audit] DRY-RUN: would update USER.md and MEMORY.md
```

Approval is explicit. The operator reviews the dry-run delta, then runs:

```bash
self-ershov-memory --execute --full
```

## AFTER

`USER.md` contains the approved corrections:

```markdown
Нико профиль
§
КОРРЕКЦИИ ОТ НИКО (self-audit <date>)
- запомни на будущее: логи в Telegram только кратко
- зачем ты опять возвращаешь старый закрытый вопрос
§
```

`MEMORY.md` contains the durable anti-pattern extracted from the approved corrections:

```markdown
АНТИПАТТЕРНЫ
- логи/уведомления
- повтор старого
§
```

## Guarantees

- BEFORE files are unchanged after dry-run.
- AFTER files change only after explicit `--execute` approval.
- Snapshots are created before writes.
- CI covers this exact loop with `test_real_before_after_approval_loop_is_documented_and_enforced`.

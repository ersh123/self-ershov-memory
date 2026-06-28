from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if SRC.exists() and str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


PRIMARY_COMMAND = "ershov"
SELF_MEMORY_COMMAND = "self-memory"
SELF_AUDIT_COMMAND = "self-audit"
LEGACY_MNEMOS_COMMAND = "mnemos"
LEGACY_NIGHTMEM_COMMAND = "nightmem"
LEGACY_COMMAND = "dreaming"
PRODUCT_NAME = "Self Ershov Memory"

def _run_self_audit(args: argparse.Namespace) -> int:
    from hermes_dreaming.cli import main as dreaming_main

    dream_args = list(getattr(args, "dreaming_args", []) or [])
    if dream_args[:1] == ["--"]:
        dream_args = dream_args[1:]
    if not dream_args:
        dream_args = ["--help"]

    try:
        result = dreaming_main(dream_args)
    except SystemExit as exc:
        code = exc.code
        code = code if isinstance(code, int) else 0 if code in (None, "") else 1
    else:
        code = int(result or 0)

    if code:
        raise SystemExit(code)
    return code


def _setup_dreaming_cli(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "dreaming_args",
        nargs=argparse.REMAINDER,
        help="Arguments forwarded to the Self Ershov Memory CLI.",
    )


def register(ctx) -> None:
    for name, help_text in (
        (PRIMARY_COMMAND, "Run the personal Hermes Ershov engine"),
        (SELF_MEMORY_COMMAND, "Run the Self Ershov Memory engine"),
        (SELF_AUDIT_COMMAND, "Run the Self Ershov Memory engine"),
        (LEGACY_MNEMOS_COMMAND, "Run the legacy compatibility command"),
        (LEGACY_NIGHTMEM_COMMAND, "Run the legacy compatibility command"),
        (LEGACY_COMMAND, "Run the legacy compatibility command"),
    ):
        ctx.register_cli_command(
            name=name,
            help=help_text,
            setup_fn=_setup_dreaming_cli,
            handler_fn=_run_self_audit,
            description=(
                f"Expose the standalone {PRODUCT_NAME} CLI inside Hermes. "
                "Dialog-driven self-audit engine — analyzes conversations, "
                "extracts corrections, updates USER.md/MEMORY.md."
            ),
        )

    skill_candidates = [ROOT / "skills" / "self-ershov-memory" / "SKILL.md", ROOT / "skills" / "hermes-ershov" / "SKILL.md"]
    skill_md = next((path for path in skill_candidates if path.exists()), None)
    if skill_md is not None:
        ctx.register_skill("ershov", skill_md)
        ctx.register_skill("self-ershov-memory", skill_md)
        ctx.register_skill("self-memory", skill_md)
        ctx.register_skill("self-audit", skill_md)
        ctx.register_skill(LEGACY_MNEMOS_COMMAND, skill_md)
        ctx.register_skill(LEGACY_NIGHTMEM_COMMAND, skill_md)
        ctx.register_skill(LEGACY_COMMAND, skill_md)

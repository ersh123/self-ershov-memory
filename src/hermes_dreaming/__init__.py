"""Hermes Ershov, staged personal memory ops for Hermes."""

from __future__ import annotations

import argparse
import contextlib
import io
import shlex
from pathlib import Path

from . import session_reader
from .artifact import DreamArtifact, DreamProposal, SourceSnapshot

__all__ = ["DreamArtifact", "DreamProposal", "SourceSnapshot", "__version__", "register", "session_reader"]
__version__ = "0.4.0"

PRIMARY_COMMAND = "ershov"
LEGACY_MNEMOS_COMMAND = "mnemos"
LEGACY_NIGHTMEM_COMMAND = "nightmem"
LEGACY_COMMAND = "dreaming"
PRODUCT_NAME = "Hermes Ershov"


def _repo_root() -> Path:
    """Best-effort repo root lookup for bundled resources."""

    here = Path(__file__).resolve()
    for parent in here.parents:
        skill_path = parent / "skills" / "hermes-ershov" / "SKILL.md"
        if skill_path.exists():
            return parent
    return here.parents[2]


def _skill_path() -> Path:
    return _repo_root() / "skills" / "hermes-ershov" / "SKILL.md"


def _normalize_dreaming_args(raw_args: list[str] | tuple[str, ...] | None) -> list[str]:
    dream_args = list(raw_args or [])
    if dream_args[:1] == ["--"]:
        dream_args = dream_args[1:]
    if not dream_args:
        dream_args = ["--help"]
    return dream_args


def _invoke_dreaming_main(raw_args: list[str] | tuple[str, ...] | None) -> int:
    from .cli import main as dreaming_main

    try:
        result = dreaming_main(_normalize_dreaming_args(raw_args))
    except SystemExit as exc:
        code = exc.code
        if isinstance(code, int):
            return code
        return 0 if code in (None, "") else 1

    return int(result or 0)


def _setup_dreaming_cli(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "dreaming_args",
        nargs=argparse.REMAINDER,
        help="Arguments forwarded to the Ershov CLI.",
    )


def _run_dreaming_cli(args: argparse.Namespace) -> int:
    return _invoke_dreaming_main(list(getattr(args, "dreaming_args", []) or []))


def _run_dreaming_slash(raw_args: str) -> str:
    tokens = shlex.split(raw_args) if raw_args else []
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(buffer):
        code = _invoke_dreaming_main(tokens)
    output = buffer.getvalue().strip()
    if output:
        return output
    if code == 0:
        return f"{PRODUCT_NAME} finished."
    return f"{PRODUCT_NAME} exited with status {code}."


def _register_cli_alias(ctx, *, name: str, legacy: bool = False) -> None:
    help_text = (
        "Run the legacy hermes-ershov compatibility command"
        if legacy
        else "Run the personal Hermes Ershov engine"
    )

    ctx.register_cli_command(
        name=name,
        help=help_text,
        setup_fn=_setup_dreaming_cli,
        handler_fn=_run_dreaming_cli,
        description=(
            f"Expose the standalone {PRODUCT_NAME} CLI inside Hermes. "
            "Use it to create, inspect, validate, apply, or discard staged personal memory artifacts."
        ),
    )


def _register_slash_alias(ctx, *, name: str, legacy: bool = False) -> None:
    ctx.register_command(
        name=name,
        handler=_run_dreaming_slash,
        description=(
            f"Route {PRODUCT_NAME} artifact commands through the chat surface "
            "without mutating live memory until apply time."
            if not legacy
            else f"Legacy alias for {PRODUCT_NAME} commands."
        ),
        args_hint="create|review|nightly|summarize|approve|reject|diff|validate|apply|revert|discard|compact|digest|inbox|report-card|install-cron|install-systemd|providers|status|soak|update",
    )


def register(ctx) -> None:
    """Register the Hermes Ershov CLI commands, slash commands, and skill."""

    _register_cli_alias(ctx, name=PRIMARY_COMMAND)
    _register_cli_alias(ctx, name=LEGACY_MNEMOS_COMMAND, legacy=True)
    _register_cli_alias(ctx, name=LEGACY_NIGHTMEM_COMMAND, legacy=True)
    _register_cli_alias(ctx, name=LEGACY_COMMAND, legacy=True)
    _register_slash_alias(ctx, name=PRIMARY_COMMAND)
    _register_slash_alias(ctx, name=LEGACY_MNEMOS_COMMAND, legacy=True)
    _register_slash_alias(ctx, name=LEGACY_NIGHTMEM_COMMAND, legacy=True)
    _register_slash_alias(ctx, name=LEGACY_COMMAND, legacy=True)

    skill_md = _skill_path()
    if skill_md.exists():
        ctx.register_skill("ershov", skill_md)
        ctx.register_skill(LEGACY_MNEMOS_COMMAND, skill_md)
        ctx.register_skill(LEGACY_NIGHTMEM_COMMAND, skill_md)
        ctx.register_skill(LEGACY_COMMAND, skill_md)

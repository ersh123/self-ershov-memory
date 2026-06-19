from __future__ import annotations

import argparse
from pathlib import Path

from hermes_dreaming import register


class DummyCtx:
    def __init__(self) -> None:
        self.cli_commands: dict[str, dict] = {}
        self.commands: dict[str, dict] = {}
        self.skills: list[tuple[str, Path]] = []

    def register_cli_command(self, **kwargs) -> None:
        self.cli_commands[kwargs["name"]] = kwargs

    def register_command(self, **kwargs) -> None:
        self.commands[kwargs["name"]] = kwargs

    def register_skill(self, bare_name: str, skill_path: Path) -> None:
        self.skills.append((bare_name, Path(skill_path)))


def test_register_exposes_cli_slash_and_skill() -> None:
    ctx = DummyCtx()

    register(ctx)

    assert "ershov" in ctx.cli_commands
    assert "ershov" in ctx.commands
    assert "mnemos" in ctx.cli_commands
    assert "mnemos" in ctx.commands
    assert "nightmem" in ctx.cli_commands
    assert "nightmem" in ctx.commands
    assert "dreaming" in ctx.cli_commands
    assert "dreaming" in ctx.commands
    assert ctx.cli_commands["ershov"]["help"] == "Run the personal Hermes Ershov engine"
    assert ctx.commands["ershov"]["description"] == (
        "Route Hermes Ershov artifact commands through the chat surface "
        "without mutating live memory until apply time."
    )
    assert ctx.commands["mnemos"]["description"] == "Legacy alias for Hermes Ershov commands."
    assert ctx.commands["nightmem"]["description"] == "Legacy alias for Hermes Ershov commands."
    assert ctx.commands["dreaming"]["description"] == "Legacy alias for Hermes Ershov commands."
    assert "update" in ctx.commands["ershov"]["args_hint"]
    assert "nightly" in ctx.commands["ershov"]["args_hint"]
    assert "install-systemd" in ctx.commands["ershov"]["args_hint"]
    assert "soak" in ctx.commands["ershov"]["args_hint"]

    assert ctx.skills
    skill_name, skill_path = ctx.skills[0]
    assert skill_name == "ershov"
    assert skill_path.name == "SKILL.md"
    assert skill_path.exists()


def test_registered_handlers_route_to_dreaming_cli(monkeypatch) -> None:
    calls: list[list[str]] = []

    def fake_main(argv: list[str]) -> int:
        calls.append(list(argv))
        return 0

    monkeypatch.setattr("hermes_dreaming.cli.main", fake_main)

    ctx = DummyCtx()
    register(ctx)

    cli_handler = ctx.cli_commands["ershov"]["handler_fn"]
    slash_handler = ctx.commands["ershov"]["handler"]

    assert cli_handler(argparse.Namespace(dreaming_args=["create", "--source", "notes"])) == 0
    assert calls == [["create", "--source", "notes"]]

    slash_output = slash_handler("status --artifact-root /tmp/artifacts")
    assert calls[-1] == ["status", "--artifact-root", "/tmp/artifacts"]
    assert slash_output == "Hermes Ershov finished."

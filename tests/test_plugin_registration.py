from __future__ import annotations

import argparse
import importlib
import importlib.util
from pathlib import Path

import pytest

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


def _load_root_plugin_module():
    root_init = Path(__file__).resolve().parents[1] / "__init__.py"
    spec = importlib.util.spec_from_file_location("hermes_ershov_root_plugin_for_test", root_init)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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


def test_registered_cli_handler_propagates_nonzero_exit(monkeypatch) -> None:
    monkeypatch.setattr("hermes_dreaming.cli.main", lambda _argv: 7)

    ctx = DummyCtx()
    register(ctx)

    with pytest.raises(SystemExit) as exc:
        ctx.cli_commands["ershov"]["handler_fn"](argparse.Namespace(dreaming_args=["soak"]))

    assert exc.value.code == 7
    assert ctx.commands["ershov"]["handler"]("soak") == "Hermes Ershov exited with status 7."


def test_root_plugin_cli_handler_propagates_nonzero_exit(monkeypatch) -> None:
    root_plugin = _load_root_plugin_module()
    monkeypatch.setattr("hermes_dreaming.cli.main", lambda _argv: 7)

    ctx = DummyCtx()
    root_plugin.register(ctx)

    with pytest.raises(SystemExit) as exc:
        ctx.cli_commands["ershov"]["handler_fn"](argparse.Namespace(dreaming_args=["soak"]))

    assert exc.value.code == 7


def test_public_alias_packages_import_under_coverage() -> None:
    for module_name in (
        "hermes_ershov",
        "hermes_ershov.__main__",
        "hermes_mnemos",
        "hermes_mnemos.__main__",
    ):
        module = importlib.import_module(module_name)
        assert module is not None

from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path

import pytest


class DummyCtx:
    def __init__(self) -> None:
        self.cli_commands = {}
        self.skills = []

    def register_cli_command(self, **kwargs) -> None:
        self.cli_commands[kwargs["name"]] = kwargs

    def register_skill(self, bare_name: str, skill_path: Path) -> None:
        self.skills.append((bare_name, Path(skill_path)))


def load_root_plugin():
    root_init = Path(__file__).resolve().parents[1] / "__init__.py"
    spec = importlib.util.spec_from_file_location(
        "self_ershov_root_plugin_test", root_init
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_register_exposes_only_product_commands() -> None:
    module = load_root_plugin()
    ctx = DummyCtx()

    module.register(ctx)

    assert set(ctx.cli_commands) == {"self-ershov-memory", "self-memory", "self-audit"}
    assert all(
        "Self Ershov Memory" in item["help"] for item in ctx.cli_commands.values()
    )
    assert "ershov" not in ctx.cli_commands


def test_cli_setup_forwards_remainder_and_handler_uses_product_cli(monkeypatch) -> None:
    module = load_root_plugin()
    calls = []

    def fake_main(argv):
        calls.append(list(argv))
        return 0

    monkeypatch.setattr("self_ershov_memory.audit.main", fake_main)
    ctx = DummyCtx()
    module.register(ctx)
    command = ctx.cli_commands["self-ershov-memory"]

    parser = argparse.ArgumentParser()
    command["setup_fn"](parser)
    args = parser.parse_args(["--", "--dry-run", "--full"])
    assert command["handler_fn"](args) == 0
    assert calls == [["--dry-run", "--full"]]

    assert command["handler_fn"](argparse.Namespace(audit_args=[])) == 0
    assert calls[-1] == ["--help"]


def test_handler_propagates_nonzero_system_exit(monkeypatch) -> None:
    module = load_root_plugin()
    monkeypatch.setattr("self_ershov_memory.audit.main", lambda _argv: 7)

    with pytest.raises(SystemExit) as exc:
        module._run_self_audit(argparse.Namespace(audit_args=["--execute"]))
    assert exc.value.code == 7


def test_handler_normalizes_system_exit_values(monkeypatch) -> None:
    module = load_root_plugin()

    def raises_empty(_argv):
        raise SystemExit("")

    monkeypatch.setattr("self_ershov_memory.audit.main", raises_empty)
    assert module._run_self_audit(argparse.Namespace(audit_args=["--help"])) == 0

    def raises_text(_argv):
        raise SystemExit("boom")

    monkeypatch.setattr("self_ershov_memory.audit.main", raises_text)
    with pytest.raises(SystemExit) as exc:
        module._run_self_audit(argparse.Namespace(audit_args=["--help"]))
    assert exc.value.code == 1


def test_root_plugin_adds_src_to_syspath_when_missing(monkeypatch) -> None:
    import sys

    root = Path(__file__).resolve().parents[1]
    src = str(root / "src")
    monkeypatch.setattr(sys, "path", [item for item in sys.path if item != src])

    module = load_root_plugin()

    assert src in sys.path
    assert module.SRC == root / "src"

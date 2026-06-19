from __future__ import annotations

import importlib.util
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_test_one_input():
    path = REPO_ROOT / "fuzzers" / "ershov_safety_fuzzer.py"
    spec = importlib.util.spec_from_file_location("ershov_safety_fuzzer", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.TestOneInput


def test_ershov_safety_fuzzer_handles_seed_inputs() -> None:
    test_one_input = _load_test_one_input()

    for seed in (
        b"",
        b"memory.md",
        b"../escape",
        b'{"fact":"remember staged writes"}',
        b"line\nbreak",
        b"sk-not-a-real-secret-000",
    ):
        test_one_input(seed)

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_release_checksums_module():
    path = REPO_ROOT / "scripts" / "generate_release_checksums.py"
    spec = importlib.util.spec_from_file_location("generate_release_checksums", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_release_checksums_are_sorted_and_exclude_manifest(tmp_path: Path) -> None:
    module = _load_release_checksums_module()
    (tmp_path / "z.whl").write_text("wheel", encoding="utf-8")
    (tmp_path / "a.tar.gz").write_text("sdist", encoding="utf-8")
    (tmp_path / "SHA256SUMS").write_text("stale", encoding="utf-8")

    lines = module.build_checksum_lines(dist_dir=tmp_path)

    assert [line.rsplit("  ", 1)[1] for line in lines] == ["a.tar.gz", "z.whl"]
    assert all(len(line.split()[0]) == 64 for line in lines)


def test_release_checksums_cli_writes_manifest(tmp_path: Path, monkeypatch, capsys) -> None:
    module = _load_release_checksums_module()
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "asset.whl").write_text("asset", encoding="utf-8")
    output = dist / "SHA256SUMS"

    monkeypatch.setattr(sys, "argv", ["generate_release_checksums.py", "--dist", str(dist)])

    assert module.main() == 0

    captured = capsys.readouterr()
    assert f"wrote checksums: {output}" in captured.out
    assert output.read_text(encoding="utf-8").endswith("  asset.whl\n")

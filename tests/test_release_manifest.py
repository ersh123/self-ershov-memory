from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_release_manifest_module():
    path = REPO_ROOT / "scripts" / "generate_release_manifest.py"
    spec = importlib.util.spec_from_file_location("generate_release_manifest", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_minimal_pyproject(path: Path) -> None:
    path.write_text(
        "\n".join(
            [
                "[project]",
                'name = "self-ershov-memory"',
                'version = "0.4.0"',
                "",
            ]
        ),
        encoding="utf-8",
    )


def _write_minimal_dist(dist: Path) -> None:
    dist.mkdir()
    (dist / "self_ershov_memory-0.4.0-py3-none-any.whl").write_text("wheel", encoding="utf-8")
    (dist / "self_ershov_memory-0.4.0.tar.gz").write_text("sdist", encoding="utf-8")
    (dist / "self-ershov-memory-sbom.spdx.json").write_text("sbom", encoding="utf-8")


def test_release_manifest_records_subject_digests_and_source_metadata(tmp_path: Path) -> None:
    module = _load_release_manifest_module()
    pyproject = tmp_path / "pyproject.toml"
    dist = tmp_path / "dist"
    _write_minimal_pyproject(pyproject)
    _write_minimal_dist(dist)

    manifest = module.build_release_manifest(
        dist_dir=dist,
        pyproject_path=pyproject,
        created="2026-06-19T00:00:00Z",
        commit="abcdef1234567890",
        ref="main",
        github_run_id="123",
        github_run_attempt="1",
        github_workflow="Release",
    )

    assert manifest["schema_version"] == 1
    assert manifest["created_at"] == "2026-06-19T00:00:00Z"
    assert manifest["project"] == {"name": "self-ershov-memory", "version": "0.4.0"}
    assert manifest["source"] == {
        "repository": "https://github.com/ersh123/self-ershov-memory",
        "ref": "main",
        "commit": "abcdef1234567890",
    }
    assert manifest["build"] == {"workflow": "Release", "run_id": "123", "run_attempt": "1"}

    subjects = {subject["name"]: subject for subject in manifest["subjects"]}
    assert set(subjects) == {
        "self_ershov_memory-0.4.0-py3-none-any.whl",
        "self_ershov_memory-0.4.0.tar.gz",
        "self-ershov-memory-sbom.spdx.json",
    }
    assert subjects["self_ershov_memory-0.4.0-py3-none-any.whl"]["kind"] == "wheel"
    assert subjects["self_ershov_memory-0.4.0.tar.gz"]["kind"] == "sdist"
    assert subjects["self-ershov-memory-sbom.spdx.json"]["kind"] == "spdx-sbom"
    assert all(len(subject["digest"]["sha256"]) == 64 for subject in subjects.values())
    assert manifest["checksum_manifest"] == {
        "name": "SHA256SUMS",
        "generated_after_manifest": True,
        "covers": [
            "release-manifest.json",
            "self-ershov-memory-sbom.spdx.json",
            "self_ershov_memory-0.4.0-py3-none-any.whl",
            "self_ershov_memory-0.4.0.tar.gz",
        ],
    }


def test_release_manifest_cli_writes_manifest(tmp_path: Path, monkeypatch, capsys) -> None:
    module = _load_release_manifest_module()
    pyproject = tmp_path / "pyproject.toml"
    dist = tmp_path / "dist"
    output = dist / "release-manifest.json"
    _write_minimal_pyproject(pyproject)
    _write_minimal_dist(dist)

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "generate_release_manifest.py",
            "--dist",
            str(dist),
            "--pyproject",
            str(pyproject),
            "--commit",
            "abcdef1",
            "--ref",
            "main",
        ],
    )

    assert module.main() == 0

    captured = capsys.readouterr()
    assert f"wrote release manifest: {output}" in captured.out
    assert '"release-manifest.json"' in output.read_text(encoding="utf-8")


def test_release_manifest_rejects_missing_required_asset(tmp_path: Path) -> None:
    module = _load_release_manifest_module()
    pyproject = tmp_path / "pyproject.toml"
    dist = tmp_path / "dist"
    _write_minimal_pyproject(pyproject)
    dist.mkdir()
    (dist / "self_ershov_memory-0.4.0-py3-none-any.whl").write_text("wheel", encoding="utf-8")
    (dist / "self-ershov-memory-sbom.spdx.json").write_text("sbom", encoding="utf-8")

    with pytest.raises(ValueError, match="expected exactly one sdist"):
        module.build_release_manifest(dist_dir=dist, pyproject_path=pyproject)

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_release_artifact_module():
    path = REPO_ROOT / "scripts" / "verify_release_artifacts.py"
    spec = importlib.util.spec_from_file_location("verify_release_artifacts", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def release_dist(tmp_path_factory: pytest.TempPathFactory) -> Path:
    dist = tmp_path_factory.mktemp("release-dist") / "dist"
    subprocess.run(
        [
            "uv",
            "run",
            "--locked",
            "--extra",
            "dev",
            "python",
            "-m",
            "build",
            "--outdir",
            str(dist),
        ],
        cwd=REPO_ROOT,
        check=True,
        stdout=subprocess.DEVNULL,
    )
    subprocess.run(
        [
            "uv",
            "run",
            "--locked",
            "--extra",
            "dev",
            "python",
            "scripts/generate_release_sbom.py",
            "--pyproject",
            str(REPO_ROOT / "pyproject.toml"),
            "--lock",
            str(REPO_ROOT / "uv.lock"),
            "--output",
            str(dist / "hermes-ershov-sbom.spdx.json"),
        ],
        cwd=REPO_ROOT,
        check=True,
        stdout=subprocess.DEVNULL,
    )
    subprocess.run(
        [
            "uv",
            "run",
            "--locked",
            "--extra",
            "dev",
            "python",
            "scripts/generate_release_checksums.py",
            "--dist",
            str(dist),
        ],
        cwd=REPO_ROOT,
        check=True,
        stdout=subprocess.DEVNULL,
    )
    return dist


def test_release_artifact_verifier_accepts_built_dist(release_dist: Path) -> None:
    module = _load_release_artifact_module()

    evidence = module.verify_release_artifacts(
        dist_dir=release_dist,
        pyproject_path=REPO_ROOT / "pyproject.toml",
        lock_path=REPO_ROOT / "uv.lock",
    )

    assert len(evidence) == 4
    assert any(line.startswith("wheel hermes_ershov-0.4.0") for line in evidence)
    assert any(line.startswith("sdist hermes_ershov-0.4.0") for line in evidence)
    assert any(line.startswith("sbom hermes-ershov-sbom.spdx.json") for line in evidence)
    assert "checksums SHA256SUMS entries=3" in evidence


def test_release_artifact_verifier_rejects_sbom_missing_locked_package(
    release_dist: Path,
    tmp_path: Path,
) -> None:
    module = _load_release_artifact_module()
    dist = tmp_path / "dist"
    dist.mkdir()
    for artifact in release_dist.iterdir():
        target = dist / artifact.name
        target.write_bytes(artifact.read_bytes())

    sbom_path = dist / "hermes-ershov-sbom.spdx.json"
    sbom = json.loads(sbom_path.read_text(encoding="utf-8"))
    sbom["packages"] = [package for package in sbom["packages"] if package["name"] != "pytest"]
    sbom_path.write_text(json.dumps(sbom), encoding="utf-8")

    with pytest.raises(module.VerificationError, match="SBOM package set mismatch"):
        module.verify_release_artifacts(
            dist_dir=dist,
            pyproject_path=REPO_ROOT / "pyproject.toml",
            lock_path=REPO_ROOT / "uv.lock",
        )


def test_release_artifact_verifier_rejects_stale_checksums(
    release_dist: Path,
    tmp_path: Path,
) -> None:
    module = _load_release_artifact_module()
    dist = tmp_path / "dist"
    dist.mkdir()
    for artifact in release_dist.iterdir():
        target = dist / artifact.name
        target.write_bytes(artifact.read_bytes())

    sbom_path = dist / "hermes-ershov-sbom.spdx.json"
    sbom_path.write_text(sbom_path.read_text(encoding="utf-8") + "\n", encoding="utf-8")

    with pytest.raises(module.VerificationError, match="SHA256SUMS digest mismatch"):
        module.verify_release_artifacts(
            dist_dir=dist,
            pyproject_path=REPO_ROOT / "pyproject.toml",
            lock_path=REPO_ROOT / "uv.lock",
        )

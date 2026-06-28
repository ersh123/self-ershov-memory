from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_release_sbom_module():
    path = REPO_ROOT / "scripts" / "generate_release_sbom.py"
    spec = importlib.util.spec_from_file_location("generate_release_sbom", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_release_sbom_is_spdx_and_uses_locked_package_hashes(tmp_path: Path) -> None:
    pyproject = tmp_path / "pyproject.toml"
    lock = tmp_path / "uv.lock"
    pyproject.write_text(
        """
[project]
name = "demo-package"
version = "1.2.3"
license = {file = "LICENSE"}
""".strip(),
        encoding="utf-8",
    )
    lock.write_text(
        """
version = 1
revision = 3
requires-python = ">=3.11"

[[package]]
name = "demo-package"
version = "1.2.3"
source = { editable = "." }

[[package]]
name = "demo-dep"
version = "4.5.6"
source = { registry = "https://pypi.org/simple" }
sdist = { url = "https://files.pythonhosted.org/packages/demo-dep.tar.gz", hash = "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa" }
""".strip(),
        encoding="utf-8",
    )

    module = _load_release_sbom_module()
    sbom = module.build_sbom(pyproject_path=pyproject, lock_path=lock, created="2026-06-20T00:00:00Z")
    encoded = json.dumps(sbom)

    assert sbom["spdxVersion"] == "SPDX-2.3"
    assert sbom["creationInfo"]["creators"] == ["Tool: self-ershov-memory-release-sbom"]
    assert sbom["creationInfo"]["created"] == "2026-06-20T00:00:00Z"
    assert "pkg:pypi/demo-package@1.2.3" in encoded
    assert "pkg:pypi/demo-dep@4.5.6" in encoded
    assert "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa" in encoded
    assert any(item["relationshipType"] == "DEPENDS_ON" for item in sbom["relationships"])


def test_release_sbom_cli_writes_reproducible_output_with_wheel_hash(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    (tmp_path / "pyproject.toml").write_text(
        """
[project]
name = "demo-package"
version = "1.2.3"
""".strip(),
        encoding="utf-8",
    )
    (tmp_path / "uv.lock").write_text(
        """
version = 1
revision = 3
requires-python = ">=3.11"

[[package]]
name = "wheel-dep"
version = "0.1.0"
source = { registry = "https://pypi.org/simple" }
wheels = [{ url = "https://files.pythonhosted.org/packages/wheel-dep.whl", hash = "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb" }]
""".strip(),
        encoding="utf-8",
    )
    output = tmp_path / "dist" / "sbom.spdx.json"

    module = _load_release_sbom_module()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1767225600")
    monkeypatch.setattr(sys, "argv", ["generate_release_sbom.py", "--output", str(output)])

    assert module.main() == 0

    captured = capsys.readouterr()
    sbom = json.loads(output.read_text(encoding="utf-8"))
    encoded = json.dumps(sbom)
    assert f"wrote SBOM: {output}" in captured.out
    assert sbom["creationInfo"]["created"] == "2026-01-01T00:00:00Z"
    assert "pkg:pypi/wheel-dep@0.1.0" in encoded
    assert "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb" in encoded

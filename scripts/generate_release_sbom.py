from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import tomllib
from pathlib import Path
from typing import Any


REPO_URL = "https://github.com/ersh123/self-ershov-memory"
TOOL_NAME = "self-ershov-memory-release-sbom"


def _load_toml(path: Path) -> dict[str, Any]:
    return tomllib.loads(path.read_text(encoding="utf-8"))


def _created_timestamp() -> str:
    epoch = os.environ.get("SOURCE_DATE_EPOCH")
    if epoch:
        created = dt.datetime.fromtimestamp(int(epoch), tz=dt.UTC)
    else:
        created = dt.datetime.now(tz=dt.UTC)
    return created.replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def _spdx_id(name: str, version: str, *, prefix: str = "Package") -> str:
    digest = hashlib.sha256(f"{name}@{version}".encode("utf-8")).hexdigest()[:10]
    safe = re.sub(r"[^A-Za-z0-9.-]+", "-", name).strip("-") or "package"
    return f"SPDXRef-{prefix}-{safe}-{digest}"


def _hash_from_lock_entry(package: dict[str, Any]) -> str | None:
    sdist = package.get("sdist")
    if isinstance(sdist, dict) and isinstance(sdist.get("hash"), str):
        return sdist["hash"]
    wheels = package.get("wheels")
    if isinstance(wheels, list):
        for wheel in wheels:
            if isinstance(wheel, dict) and isinstance(wheel.get("hash"), str):
                return wheel["hash"]
    return None


def _url_from_lock_entry(package: dict[str, Any]) -> str:
    sdist = package.get("sdist")
    if isinstance(sdist, dict) and isinstance(sdist.get("url"), str):
        return sdist["url"]
    wheels = package.get("wheels")
    if isinstance(wheels, list):
        for wheel in wheels:
            if isinstance(wheel, dict) and isinstance(wheel.get("url"), str):
                return wheel["url"]
    return "NOASSERTION"


def _checksum(hash_value: str | None) -> list[dict[str, str]]:
    if not hash_value:
        return []
    if ":" not in hash_value:
        return []
    algorithm, value = hash_value.split(":", 1)
    if algorithm.lower() != "sha256":
        return []
    return [{"algorithm": "SHA256", "checksumValue": value}]


def _purl(name: str, version: str) -> str:
    normalized = name.lower().replace("_", "-")
    return f"pkg:pypi/{normalized}@{version}"


def _package(
    *,
    name: str,
    version: str,
    spdx_id: str,
    download_location: str,
    license_declared: str,
    checksum: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    package: dict[str, Any] = {
        "name": name,
        "SPDXID": spdx_id,
        "versionInfo": version,
        "downloadLocation": download_location,
        "filesAnalyzed": False,
        "licenseConcluded": "NOASSERTION",
        "licenseDeclared": license_declared,
        "copyrightText": "NOASSERTION",
        "primaryPackagePurpose": "LIBRARY",
        "externalRefs": [
            {
                "referenceCategory": "PACKAGE-MANAGER",
                "referenceType": "purl",
                "referenceLocator": _purl(name, version),
            }
        ],
    }
    if checksum:
        package["checksums"] = checksum
    return package


def build_sbom(
    *,
    pyproject_path: Path,
    lock_path: Path,
    created: str | None = None,
) -> dict[str, Any]:
    pyproject = _load_toml(pyproject_path)
    lock = _load_toml(lock_path)
    project = pyproject["project"]
    project_name = str(project["name"])
    project_version = str(project["version"])
    lock_digest = hashlib.sha256(lock_path.read_bytes()).hexdigest()
    root_id = _spdx_id(project_name, project_version, prefix="Root")

    packages = [
        _package(
            name=project_name,
            version=project_version,
            spdx_id=root_id,
            download_location=REPO_URL,
            license_declared="MIT",
        )
    ]
    relationships = [
        {
            "spdxElementId": "SPDXRef-DOCUMENT",
            "relationshipType": "DESCRIBES",
            "relatedSpdxElement": root_id,
        }
    ]

    for package in sorted(lock.get("package", []), key=lambda item: (item.get("name", ""), item.get("version", ""))):
        source = package.get("source")
        if isinstance(source, dict) and source.get("editable") == ".":
            continue
        name = str(package["name"])
        version = str(package["version"])
        spdx_id = _spdx_id(name, version)
        packages.append(
            _package(
                name=name,
                version=version,
                spdx_id=spdx_id,
                download_location=_url_from_lock_entry(package),
                license_declared="NOASSERTION",
                checksum=_checksum(_hash_from_lock_entry(package)),
            )
        )
        relationships.append(
            {
                "spdxElementId": root_id,
                "relationshipType": "DEPENDS_ON",
                "relatedSpdxElement": spdx_id,
            }
        )

    return {
        "spdxVersion": "SPDX-2.3",
        "dataLicense": "CC0-1.0",
        "SPDXID": "SPDXRef-DOCUMENT",
        "name": f"{project_name}-{project_version}-release-sbom",
        "documentNamespace": f"{REPO_URL}/sbom/{project_name}-{project_version}-{lock_digest[:16]}",
        "creationInfo": {
            "created": created or _created_timestamp(),
            "creators": [f"Tool: {TOOL_NAME}"],
        },
        "packages": packages,
        "relationships": relationships,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate the Self Ershov Memory release SPDX SBOM.")
    parser.add_argument("--pyproject", type=Path, default=Path("pyproject.toml"))
    parser.add_argument("--lock", type=Path, default=Path("uv.lock"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    sbom = build_sbom(pyproject_path=args.pyproject, lock_path=args.lock)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(sbom, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote SBOM: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

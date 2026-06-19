from __future__ import annotations

import argparse
from email.parser import Parser
import hashlib
import json
from pathlib import Path
import sys
import tarfile
import tomllib
from typing import Any
import zipfile


EXPECTED_CONSOLE_SCRIPTS = {
    "ershov": "hermes_dreaming.cli:main",
    "mnemos": "hermes_dreaming.cli:main",
    "nightmem": "hermes_dreaming.cli:main",
    "dreaming": "hermes_dreaming.cli:main",
}
SBOM_NAME = "hermes-ershov-sbom.spdx.json"
CHECKSUM_MANIFEST = "SHA256SUMS"


class VerificationError(Exception):
    pass


def _load_toml(path: Path) -> dict[str, Any]:
    return tomllib.loads(path.read_text(encoding="utf-8"))


def _project_metadata(pyproject_path: Path) -> tuple[str, str]:
    project = _load_toml(pyproject_path)["project"]
    return str(project["name"]), str(project["version"])


def _normalized_distribution_name(name: str) -> str:
    return name.replace("-", "_").replace(".", "_")


def _single_file(dist_dir: Path, pattern: str, label: str) -> Path:
    matches = sorted(dist_dir.glob(pattern))
    if len(matches) != 1:
        names = ", ".join(path.name for path in matches) or "none"
        raise VerificationError(f"expected exactly one {label} matching {pattern}, found {len(matches)}: {names}")
    if matches[0].stat().st_size <= 0:
        raise VerificationError(f"{label} is empty: {matches[0]}")
    return matches[0]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_checksum_manifest(path: Path) -> dict[str, str]:
    entries: dict[str, str] = {}
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        parts = line.split()
        if len(parts) != 2:
            raise VerificationError(f"{path.name}:{line_number} must contain '<sha256>  <filename>'")
        digest, filename = parts
        if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
            raise VerificationError(f"{path.name}:{line_number} has invalid SHA256 digest")
        if "/" in filename or "\\" in filename or filename in {".", ".."}:
            raise VerificationError(f"{path.name}:{line_number} has unsafe filename {filename!r}")
        if filename in entries:
            raise VerificationError(f"{path.name}:{line_number} duplicates {filename!r}")
        entries[filename] = digest
    if not entries:
        raise VerificationError(f"{path.name} is empty")
    return entries


def _read_zip_text(zip_path: Path, suffix: str) -> str:
    with zipfile.ZipFile(zip_path) as archive:
        matches = [name for name in archive.namelist() if name.endswith(suffix)]
        if len(matches) != 1:
            raise VerificationError(f"{zip_path.name} expected one {suffix}, found {len(matches)}")
        return archive.read(matches[0]).decode("utf-8")


def _assert_wheel(wheel_path: Path, *, project_name: str, project_version: str) -> None:
    expected_prefix = f"{_normalized_distribution_name(project_name)}-{project_version}"
    if not wheel_path.name.startswith(expected_prefix) or not wheel_path.name.endswith("-py3-none-any.whl"):
        raise VerificationError(f"unexpected wheel filename: {wheel_path.name}")

    metadata = Parser().parsestr(_read_zip_text(wheel_path, "/METADATA"))
    if metadata.get("Name") != project_name:
        raise VerificationError(f"wheel METADATA Name mismatch: {metadata.get('Name')!r}")
    if metadata.get("Version") != project_version:
        raise VerificationError(f"wheel METADATA Version mismatch: {metadata.get('Version')!r}")

    entry_points = _read_zip_text(wheel_path, "/entry_points.txt")
    for name, target in EXPECTED_CONSOLE_SCRIPTS.items():
        expected_line = f"{name} = {target}"
        if expected_line not in entry_points:
            raise VerificationError(f"wheel entry_points.txt missing {expected_line!r}")

    with zipfile.ZipFile(wheel_path) as archive:
        names = set(archive.namelist())
    for suffix in (
        "/RECORD",
        "hermes_dreaming/cli.py",
        "hermes_ershov/__main__.py",
        "hermes_mnemos/__main__.py",
    ):
        if not any(name.endswith(suffix) for name in names):
            raise VerificationError(f"wheel missing {suffix}")


def _read_tar_text(tar_path: Path, suffix: str) -> str:
    with tarfile.open(tar_path, "r:gz") as archive:
        matches = [member for member in archive.getmembers() if member.name.endswith(suffix)]
        if len(matches) != 1:
            raise VerificationError(f"{tar_path.name} expected one {suffix}, found {len(matches)}")
        extracted = archive.extractfile(matches[0])
        if extracted is None:
            raise VerificationError(f"{tar_path.name} could not read {suffix}")
        return extracted.read().decode("utf-8")


def _assert_sdist(sdist_path: Path, *, project_name: str, project_version: str) -> None:
    expected_name = f"{_normalized_distribution_name(project_name)}-{project_version}.tar.gz"
    if sdist_path.name != expected_name:
        raise VerificationError(f"unexpected sdist filename: {sdist_path.name}")

    metadata = Parser().parsestr(_read_tar_text(sdist_path, "/PKG-INFO"))
    if metadata.get("Name") != project_name:
        raise VerificationError(f"sdist PKG-INFO Name mismatch: {metadata.get('Name')!r}")
    if metadata.get("Version") != project_version:
        raise VerificationError(f"sdist PKG-INFO Version mismatch: {metadata.get('Version')!r}")

    pyproject = _read_tar_text(sdist_path, "/pyproject.toml")
    if f'name = "{project_name}"' not in pyproject:
        raise VerificationError("sdist pyproject.toml does not carry the expected project name")

    with tarfile.open(sdist_path, "r:gz") as archive:
        names = set(archive.getnames())
    for suffix in (
        "/src/hermes_dreaming/cli.py",
        "/src/hermes_ershov/__main__.py",
        "/src/hermes_mnemos/__main__.py",
    ):
        if not any(name.endswith(suffix) for name in names):
            raise VerificationError(f"sdist missing {suffix}")


def _purl(name: str, version: str) -> str:
    return f"pkg:pypi/{name.lower().replace('_', '-')}@{version}"


def _lock_hash(package: dict[str, Any]) -> str | None:
    sdist = package.get("sdist")
    if isinstance(sdist, dict) and isinstance(sdist.get("hash"), str):
        return sdist["hash"]
    wheels = package.get("wheels")
    if isinstance(wheels, list):
        for wheel in wheels:
            if isinstance(wheel, dict) and isinstance(wheel.get("hash"), str):
                return wheel["hash"]
    return None


def _locked_packages(lock_path: Path) -> dict[tuple[str, str], str | None]:
    lock = _load_toml(lock_path)
    packages: dict[tuple[str, str], str | None] = {}
    for package in lock.get("package", []):
        source = package.get("source")
        if isinstance(source, dict) and source.get("editable") == ".":
            continue
        name = str(package["name"])
        version = str(package["version"])
        packages[(name, version)] = _lock_hash(package)
    return packages


def _external_ref_locators(package: dict[str, Any]) -> set[str]:
    refs = package.get("externalRefs")
    if not isinstance(refs, list):
        return set()
    return {
        str(ref.get("referenceLocator"))
        for ref in refs
        if isinstance(ref, dict)
        and ref.get("referenceCategory") == "PACKAGE-MANAGER"
        and ref.get("referenceType") == "purl"
    }


def _sha256_checksums(package: dict[str, Any]) -> set[str]:
    checksums = package.get("checksums")
    if not isinstance(checksums, list):
        return set()
    return {
        str(item.get("checksumValue"))
        for item in checksums
        if isinstance(item, dict) and item.get("algorithm") == "SHA256"
    }


def _assert_spdx_package_basics(package: dict[str, Any]) -> None:
    for field in (
        "name",
        "SPDXID",
        "versionInfo",
        "downloadLocation",
        "filesAnalyzed",
        "licenseConcluded",
        "licenseDeclared",
        "copyrightText",
    ):
        if field not in package:
            raise VerificationError(f"SBOM package {package.get('name', '<unknown>')!r} missing {field}")


def _assert_sbom(
    sbom_path: Path,
    *,
    project_name: str,
    project_version: str,
    lock_path: Path,
) -> None:
    sbom = json.loads(sbom_path.read_text(encoding="utf-8"))
    if sbom.get("spdxVersion") != "SPDX-2.3":
        raise VerificationError(f"SBOM spdxVersion mismatch: {sbom.get('spdxVersion')!r}")
    if sbom.get("SPDXID") != "SPDXRef-DOCUMENT":
        raise VerificationError(f"SBOM SPDXID mismatch: {sbom.get('SPDXID')!r}")
    if sbom.get("dataLicense") != "CC0-1.0":
        raise VerificationError(f"SBOM dataLicense mismatch: {sbom.get('dataLicense')!r}")

    packages = sbom.get("packages")
    if not isinstance(packages, list):
        raise VerificationError("SBOM packages must be a list")
    for package in packages:
        if not isinstance(package, dict):
            raise VerificationError("SBOM package entries must be objects")
        _assert_spdx_package_basics(package)

    ids = [str(package["SPDXID"]) for package in packages]
    if len(ids) != len(set(ids)):
        raise VerificationError("SBOM package SPDXIDs are not unique")

    package_by_key = {(str(package["name"]), str(package["versionInfo"])): package for package in packages}
    root = package_by_key.get((project_name, project_version))
    if root is None:
        raise VerificationError(f"SBOM missing root package {project_name}@{project_version}")
    root_id = str(root["SPDXID"])
    if _purl(project_name, project_version) not in _external_ref_locators(root):
        raise VerificationError("SBOM root package missing purl externalRef")

    locked = _locked_packages(lock_path)
    expected_keys = {(project_name, project_version), *locked.keys()}
    if set(package_by_key) != expected_keys:
        missing = sorted(expected_keys - set(package_by_key))
        extra = sorted(set(package_by_key) - expected_keys)
        raise VerificationError(f"SBOM package set mismatch: missing={missing}, extra={extra}")

    relationships = sbom.get("relationships")
    if not isinstance(relationships, list):
        raise VerificationError("SBOM relationships must be a list")
    relationship_keys = {
        (
            str(item.get("spdxElementId")),
            str(item.get("relationshipType")),
            str(item.get("relatedSpdxElement")),
        )
        for item in relationships
        if isinstance(item, dict)
    }
    if ("SPDXRef-DOCUMENT", "DESCRIBES", root_id) not in relationship_keys:
        raise VerificationError("SBOM missing SPDXRef-DOCUMENT DESCRIBES root relationship")

    for key, lock_hash in locked.items():
        package = package_by_key[key]
        if _purl(*key) not in _external_ref_locators(package):
            raise VerificationError(f"SBOM package {key[0]}@{key[1]} missing purl externalRef")
        if (root_id, "DEPENDS_ON", str(package["SPDXID"])) not in relationship_keys:
            raise VerificationError(f"SBOM missing root DEPENDS_ON relationship for {key[0]}@{key[1]}")
        if lock_hash and lock_hash.startswith("sha256:"):
            expected_hash = lock_hash.split(":", 1)[1]
            if expected_hash not in _sha256_checksums(package):
                raise VerificationError(f"SBOM package {key[0]}@{key[1]} missing locked SHA256 checksum")


def verify_release_artifacts(*, dist_dir: Path, pyproject_path: Path, lock_path: Path) -> list[str]:
    project_name, project_version = _project_metadata(pyproject_path)
    normalized_name = _normalized_distribution_name(project_name)

    wheel = _single_file(dist_dir, f"{normalized_name}-{project_version}-*.whl", "wheel")
    sdist = _single_file(dist_dir, f"{normalized_name}-{project_version}.tar.gz", "sdist")
    sbom = _single_file(dist_dir, SBOM_NAME, "SPDX SBOM")
    checksum_manifest = _single_file(dist_dir, CHECKSUM_MANIFEST, "checksum manifest")

    _assert_wheel(wheel, project_name=project_name, project_version=project_version)
    _assert_sdist(sdist, project_name=project_name, project_version=project_version)
    _assert_sbom(sbom, project_name=project_name, project_version=project_version, lock_path=lock_path)

    expected_files = {wheel.name, sdist.name, sbom.name}
    checksum_entries = _read_checksum_manifest(checksum_manifest)
    if set(checksum_entries) != expected_files:
        missing = sorted(expected_files - set(checksum_entries))
        extra = sorted(set(checksum_entries) - expected_files)
        raise VerificationError(f"{CHECKSUM_MANIFEST} file set mismatch: missing={missing}, extra={extra}")
    for path in (wheel, sdist, sbom):
        actual = _sha256(path)
        if checksum_entries[path.name] != actual:
            raise VerificationError(f"{CHECKSUM_MANIFEST} digest mismatch for {path.name}")

    return [
        f"wheel {wheel.name} sha256={_sha256(wheel)}",
        f"sdist {sdist.name} sha256={_sha256(sdist)}",
        f"sbom {sbom.name} sha256={_sha256(sbom)}",
        f"checksums {checksum_manifest.name} entries={len(checksum_entries)}",
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify Hermes Ershov release artifacts before upload/attestation.")
    parser.add_argument("--dist", type=Path, default=Path("dist"))
    parser.add_argument("--pyproject", type=Path, default=Path("pyproject.toml"))
    parser.add_argument("--lock", type=Path, default=Path("uv.lock"))
    args = parser.parse_args()

    try:
        evidence = verify_release_artifacts(dist_dir=args.dist, pyproject_path=args.pyproject, lock_path=args.lock)
    except (OSError, KeyError, json.JSONDecodeError, zipfile.BadZipFile, tarfile.TarError, VerificationError) as exc:
        print(f"release artifact verification failed: {exc}", file=sys.stderr)
        return 1

    print("release artifacts verified")
    for line in evidence:
        print(f"- {line}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

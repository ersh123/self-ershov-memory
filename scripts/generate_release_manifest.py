from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tomllib
from typing import Any


REPO_URL = "https://github.com/ersh123/self-ershov-memory"
TOOL_NAME = "self-ershov-memory-release-manifest"
MANIFEST_NAME = "release-manifest.json"
SBOM_NAME = "self-ershov-memory-sbom.spdx.json"
CHECKSUM_MANIFEST = "SHA256SUMS"


def _load_toml(path: Path) -> dict[str, Any]:
    return tomllib.loads(path.read_text(encoding="utf-8"))


def _created_timestamp() -> str:
    epoch = os.environ.get("SOURCE_DATE_EPOCH")
    if epoch:
        created = dt.datetime.fromtimestamp(int(epoch), tz=dt.UTC)
    else:
        created = dt.datetime.now(tz=dt.UTC)
    return created.replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _normalized_distribution_name(name: str) -> str:
    return name.replace("-", "_").replace(".", "_")


def _single_file(dist_dir: Path, pattern: str, label: str) -> Path:
    matches = sorted(dist_dir.glob(pattern))
    if len(matches) != 1:
        names = ", ".join(path.name for path in matches) or "none"
        raise ValueError(f"expected exactly one {label} matching {pattern}, found {len(matches)}: {names}")
    if matches[0].stat().st_size <= 0:
        raise ValueError(f"{label} is empty: {matches[0]}")
    return matches[0]


def _git_value(args: list[str]) -> str | None:
    try:
        result = subprocess.run(
            ["git", *args],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    value = result.stdout.strip()
    return value or None


def _source_commit(explicit: str | None) -> str:
    return explicit or os.environ.get("GITHUB_SHA") or _git_value(["rev-parse", "HEAD"]) or "unknown"


def _source_ref(explicit: str | None) -> str:
    return (
        explicit
        or os.environ.get("GITHUB_REF_NAME")
        or _git_value(["rev-parse", "--abbrev-ref", "HEAD"])
        or "unknown"
    )


def _subject(path: Path, *, kind: str) -> dict[str, Any]:
    return {
        "name": path.name,
        "kind": kind,
        "digest": {"sha256": _sha256(path)},
        "size": path.stat().st_size,
    }


def build_release_manifest(
    *,
    dist_dir: Path,
    pyproject_path: Path,
    manifest_name: str = MANIFEST_NAME,
    created: str | None = None,
    commit: str | None = None,
    ref: str | None = None,
    github_run_id: str | None = None,
    github_run_attempt: str | None = None,
    github_workflow: str | None = None,
) -> dict[str, Any]:
    project = _load_toml(pyproject_path)["project"]
    project_name = str(project["name"])
    project_version = str(project["version"])
    normalized_name = _normalized_distribution_name(project_name)

    wheel = _single_file(dist_dir, f"{normalized_name}-{project_version}-*.whl", "wheel")
    sdist = _single_file(dist_dir, f"{normalized_name}-{project_version}.tar.gz", "sdist")
    sbom = _single_file(dist_dir, SBOM_NAME, "SPDX SBOM")
    subjects = [
        _subject(wheel, kind="wheel"),
        _subject(sdist, kind="sdist"),
        _subject(sbom, kind="spdx-sbom"),
    ]

    return {
        "schema_version": 1,
        "created_at": created or _created_timestamp(),
        "generator": TOOL_NAME,
        "project": {
            "name": project_name,
            "version": project_version,
        },
        "source": {
            "repository": REPO_URL,
            "ref": _source_ref(ref),
            "commit": _source_commit(commit),
        },
        "build": {
            "workflow": github_workflow or os.environ.get("GITHUB_WORKFLOW") or "unknown",
            "run_id": github_run_id or os.environ.get("GITHUB_RUN_ID") or "unknown",
            "run_attempt": github_run_attempt or os.environ.get("GITHUB_RUN_ATTEMPT") or "unknown",
        },
        "subjects": subjects,
        "sbom": {
            "name": SBOM_NAME,
        },
        "checksum_manifest": {
            "name": CHECKSUM_MANIFEST,
            "generated_after_manifest": True,
            "covers": sorted([manifest_name, *(subject["name"] for subject in subjects)]),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate the Self Ershov Memory release manifest.")
    parser.add_argument("--dist", type=Path, default=Path("dist"))
    parser.add_argument("--pyproject", type=Path, default=Path("pyproject.toml"))
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--commit", default=None)
    parser.add_argument("--ref", default=None)
    args = parser.parse_args()

    output = args.output or (args.dist / MANIFEST_NAME)
    manifest = build_release_manifest(
        dist_dir=args.dist,
        pyproject_path=args.pyproject,
        manifest_name=output.name,
        commit=args.commit,
        ref=args.ref,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote release manifest: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

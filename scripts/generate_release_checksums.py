from __future__ import annotations

import argparse
import hashlib
from pathlib import Path


CHECKSUM_MANIFEST = "SHA256SUMS"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_checksum_lines(*, dist_dir: Path, output_name: str = CHECKSUM_MANIFEST) -> list[str]:
    files = sorted(path for path in dist_dir.iterdir() if path.is_file() and path.name != output_name)
    if not files:
        raise ValueError(f"no release files found in {dist_dir}")
    return [f"{_sha256(path)}  {path.name}" for path in files]


def write_checksum_manifest(*, dist_dir: Path, output: Path | None = None) -> Path:
    target = output or (dist_dir / CHECKSUM_MANIFEST)
    lines = build_checksum_lines(dist_dir=dist_dir, output_name=target.name)
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return target


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate SHA256SUMS for Hermes Ershov release assets.")
    parser.add_argument("--dist", type=Path, default=Path("dist"))
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    output = write_checksum_manifest(dist_dir=args.dist, output=args.output)
    print(f"wrote checksums: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

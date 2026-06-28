# Self Ershov Memory release integrity

This is the public verification runbook for future GitHub Release assets.

It is not release approval. Until a tag and GitHub Release exist, treat these
commands as the contract the release workflow must satisfy.

## What every release must contain

A release asset bundle must include exactly these integrity artifacts:

- wheel: `self_ershov_memory-<version>-py3-none-any.whl`
- source distribution: `self_ershov_memory-<version>.tar.gz`
- SPDX SBOM: `self-ershov-memory-sbom.spdx.json`
- release manifest: `release-manifest.json`
- checksum manifest: `SHA256SUMS`

The verifier rejects missing files, unexpected digest drift, unsafe names,
wheel/sdist metadata mismatch, release-manifest subject drift, SBOM package
gaps, missing package URLs, and root dependency relationship drift.

## Maintainer check before upload

Build and verify locally before a release-facing workflow run:

```bash
uv run --locked --extra dev python -m build
uv run --locked --extra dev python scripts/generate_release_sbom.py --output dist/self-ershov-memory-sbom.spdx.json
uv run --locked --extra dev python scripts/generate_release_manifest.py --dist dist
uv run --locked --extra dev python scripts/generate_release_checksums.py --dist dist
uv run --locked --extra dev python scripts/verify_release_artifacts.py --dist dist
(cd dist && sha256sum -c SHA256SUMS)
```

`release-manifest.json` records subject names, kinds, sizes, SHA256 digests,
source commit/ref, and GitHub Actions run hints. `scripts/verify_release_artifacts.py`
is the project-specific gate. `sha256sum -c` is the portable consumer-facing
checksum check.

## Consumer check after release

Replace `<tag>` with the approved release tag:

```bash
TAG=<tag>
OUT="$(mktemp -d "${TMPDIR:-/tmp}/self-ershov-memory-release.XXXXXX")"

gh release download "$TAG" \
  --repo ersh123/self-ershov-memory \
  --pattern "self_ershov_memory-*.whl" \
  --pattern "self_ershov_memory-*.tar.gz" \
  --pattern "self-ershov-memory-sbom.spdx.json" \
  --pattern "release-manifest.json" \
  --pattern "SHA256SUMS" \
  --dir "$OUT"

(cd "$OUT" && sha256sum -c SHA256SUMS)
uv run --locked --extra dev python scripts/verify_release_artifacts.py --dist "$OUT"
```

If GitHub Release asset attestations are present, also verify each downloaded
asset against the release:

```bash
gh release verify-asset "$TAG" --repo ersh123/self-ershov-memory "$OUT"/self_ershov_memory-*.whl
gh release verify-asset "$TAG" --repo ersh123/self-ershov-memory "$OUT"/self_ershov_memory-*.tar.gz
gh release verify-asset "$TAG" --repo ersh123/self-ershov-memory "$OUT"/self-ershov-memory-sbom.spdx.json
gh release verify-asset "$TAG" --repo ersh123/self-ershov-memory "$OUT"/release-manifest.json
```

For lower-level provenance checks, use GitHub artifact attestations:

```bash
gh attestation verify "$OUT"/self_ershov_memory-*.whl --repo ersh123/self-ershov-memory
gh attestation verify "$OUT"/self_ershov_memory-*.tar.gz --repo ersh123/self-ershov-memory
gh attestation verify "$OUT"/self-ershov-memory-sbom.spdx.json --repo ersh123/self-ershov-memory
gh attestation verify "$OUT"/release-manifest.json --repo ersh123/self-ershov-memory
```

## What this does not prove

Release integrity proves the downloaded files match the release workflow output
and checksum manifest. It does not prove the product is stable.

Stable wording still requires scheduled-run evidence from the installed VPS
checkout:

```bash
hermes ershov soak --state-root ~/.hermes/ershov --since-hours 96 --min-successful 3 --strict-systemd --require-provider deepseek
```

Manual runs, local artifact verification, and green CI are release-candidate evidence only until that systemd gate passes on a clean target commit.

## Source baseline

This runbook follows the current public guidance for:

- GitHub release integrity verification: https://docs.github.com/code-security/supply-chain-security/understanding-your-software-supply-chain/verifying-the-integrity-of-a-release
- GitHub CLI release asset verification: https://cli.github.com/manual/gh_release_verify-asset
- GitHub CLI artifact attestation verification: https://cli.github.com/manual/gh_attestation_verify
- GitHub artifact attestations: https://docs.github.com/actions/security-for-github-actions/using-artifact-attestations/using-artifact-attestations-to-establish-provenance-for-builds
- SLSA build provenance subject/digest model: https://slsa.dev/spec/v1.2/build-provenance
- in-toto Statement subject/digest model: https://github.com/in-toto/attestation/blob/v1.0/spec/v1.0/statement.md

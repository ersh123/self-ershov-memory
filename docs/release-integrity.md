# Hermes Ershov release integrity

This is the public verification runbook for future GitHub Release assets.

It is not release approval. Until a tag and GitHub Release exist, treat these
commands as the contract the release workflow must satisfy.

## What every release must contain

A release asset bundle must include exactly these integrity artifacts:

- wheel: `hermes_ershov-<version>-py3-none-any.whl`
- source distribution: `hermes_ershov-<version>.tar.gz`
- SPDX SBOM: `hermes-ershov-sbom.spdx.json`
- checksum manifest: `SHA256SUMS`

The verifier rejects missing files, unexpected digest drift, unsafe names,
wheel/sdist metadata mismatch, SBOM package gaps, missing package URLs, and
root dependency relationship drift.

## Maintainer check before upload

Build and verify locally before a release-facing workflow run:

```bash
uv run --locked --extra dev python -m build
uv run --locked --extra dev python scripts/generate_release_sbom.py --output dist/hermes-ershov-sbom.spdx.json
uv run --locked --extra dev python scripts/generate_release_checksums.py --dist dist
uv run --locked --extra dev python scripts/verify_release_artifacts.py --dist dist
(cd dist && sha256sum -c SHA256SUMS)
```

`scripts/verify_release_artifacts.py` is the project-specific gate. `sha256sum
-c` is the portable consumer-facing checksum check.

## Consumer check after release

Replace `<tag>` with the approved release tag:

```bash
TAG=<tag>
OUT="$(mktemp -d "${TMPDIR:-/tmp}/hermes-ershov-release.XXXXXX")"

gh release download "$TAG" \
  --repo ersh123/hermes-ershov \
  --pattern "hermes_ershov-*.whl" \
  --pattern "hermes_ershov-*.tar.gz" \
  --pattern "hermes-ershov-sbom.spdx.json" \
  --pattern "SHA256SUMS" \
  --dir "$OUT"

(cd "$OUT" && sha256sum -c SHA256SUMS)
uv run --locked --extra dev python scripts/verify_release_artifacts.py --dist "$OUT"
```

If GitHub Release asset attestations are present, also verify each downloaded
asset against the release:

```bash
gh release verify-asset "$TAG" --repo ersh123/hermes-ershov "$OUT"/hermes_ershov-*.whl
gh release verify-asset "$TAG" --repo ersh123/hermes-ershov "$OUT"/hermes_ershov-*.tar.gz
gh release verify-asset "$TAG" --repo ersh123/hermes-ershov "$OUT"/hermes-ershov-sbom.spdx.json
```

For lower-level provenance checks, use GitHub artifact attestations:

```bash
gh attestation verify "$OUT"/hermes_ershov-*.whl --repo ersh123/hermes-ershov
gh attestation verify "$OUT"/hermes_ershov-*.tar.gz --repo ersh123/hermes-ershov
gh attestation verify "$OUT"/hermes-ershov-sbom.spdx.json --repo ersh123/hermes-ershov
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

from __future__ import annotations

from pathlib import Path
import re

from hermes_dreaming.providers import list_providers


REPO_ROOT = Path(__file__).resolve().parents[1]
PROVIDER_IDS = tuple(row.name for row in list_providers())


def test_changelog_provider_list_matches_public_provider_surface() -> None:
    text = (REPO_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "three built-in providers" not in text

    provider_line = next(line for line in text.splitlines() if "`ershov providers list`" in line)
    for provider in PROVIDER_IDS:
        assert provider in provider_line
    assert "`ershov providers doctor`" in text


def test_provider_specs_match_public_provider_surface() -> None:
    docs = [
        REPO_ROOT / "README.md",
        REPO_ROOT / "CHANGELOG.md",
        REPO_ROOT / "docs" / "release-notes-v0.4.0.md",
        REPO_ROOT / "specs" / "mvp-implementation-plan.md",
        REPO_ROOT / "specs" / "v0.4.0-plan.md",
    ]
    forbidden = ("three built-in providers", "existing three")
    for path in docs:
        text = path.read_text(encoding="utf-8")
        for phrase in forbidden:
            assert phrase not in text, path
        if "providers list" in text:
            for provider in PROVIDER_IDS:
                assert provider in text, path


def test_no_llm_docs_include_nightly_support() -> None:
    docs = [
        REPO_ROOT / "README.md",
        REPO_ROOT / "CHANGELOG.md",
        REPO_ROOT / "docs" / "release-notes-v0.4.0.md",
        REPO_ROOT / "specs" / "mvp-implementation-plan.md",
        REPO_ROOT / "specs" / "v0.4.0-plan.md",
    ]
    stale_phrases = (
        "`--no-llm` is a shorthand for `--provider offline-marker` on `create` and `review`",
        "`--no-llm` shorthand for `--provider offline-marker` on `create` and `review`",
        "The CLI accepts it on `create` and `review`",
    )
    for path in docs:
        text = path.read_text(encoding="utf-8")
        for phrase in stale_phrases:
            assert phrase not in text, path

    assert "`--no-llm` is a shorthand for `--provider offline-marker` on `create`, `review`, and `nightly`" in (
        REPO_ROOT / "CHANGELOG.md"
    ).read_text(encoding="utf-8")


def test_safety_doc_matches_current_quickstart_target_surface() -> None:
    text = (REPO_ROOT / "docs" / "safety.md").read_text(encoding="utf-8")
    assert "any other safe relative path" not in text
    assert "three target kinds" in text

    fixture_section = re.search(
        r"In the current offline fixture, the demo shows three target kinds:\n\n(?P<body>.*?)\n\n## It cannot mutate",
        text,
        flags=re.DOTALL,
    )
    assert fixture_section is not None
    assert fixture_section.group("body").splitlines() == [
        "- `fact`",
        "- `memory`",
        "- `user`",
    ]


def test_quickstart_uses_temp_live_root_and_dry_run_before_apply() -> None:
    text = (REPO_ROOT / "docs" / "quickstart.md").read_text(encoding="utf-8")

    assert 'export DEMO_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/hermes-ershov-quickstart.XXXXXX")"' in text
    assert 'cp -R "$FIXTURE_ROOT/live" "$LIVE_ROOT"' in text
    assert 'export LIVE_ROOT="$(pwd)/examples/quickstart/live"' not in text

    dry_run = 'ershov apply "$ARTIFACT_DIR" --live-root "$LIVE_ROOT" --backup-root "$BACKUP_ROOT" --dry-run'
    real_apply = 'ershov apply "$ARTIFACT_DIR" --live-root "$LIVE_ROOT" --backup-root "$BACKUP_ROOT"'
    lines = text.splitlines()
    assert dry_run in lines
    assert real_apply in lines
    assert lines.index(dry_run) < lines.index(real_apply)
    assert "`apply: dry-run`" in text
    assert "`mode: dry-run`" not in text
    assert "leave `$LIVE_ROOT` and `$BACKUP_ROOT` unchanged" in text
    assert "records backup evidence in `manifest.json`" in text
    assert "remove files that were created by apply" in text
    assert 'ershov revert "$ARTIFACT_DIR" --live-root "$LIVE_ROOT" --backup-root "$BACKUP_ROOT" --yes --validate' in text
    assert "/tmp/hermes-ershov-quickstart/artifacts" not in text
    assert "/tmp/hermes-ershov-quickstart.<suffix>/artifacts" in text


def test_readme_has_single_discard_example_and_trust_loop_notes() -> None:
    text = (REPO_ROOT / "README.md").read_text(encoding="utf-8")

    assert text.count("ershov discard ./artifacts/<artifact-id> --archive-root ./archive") == 1
    assert "`--dry-run` deliberately creates no backups and writes no live files" in text
    assert "records backup evidence in the artifact manifest before live writes" in text
    assert "`backup_records` tombstones" in text
    assert "Schema-valid model output is still treated as untrusted" in text


def test_release_docs_use_current_test_count() -> None:
    docs = [
        REPO_ROOT / "docs" / "release-notes-v0.4.0.md",
        REPO_ROOT / "docs" / "release-handoff-v0.4.0.md",
    ]
    for path in docs:
        text = path.read_text(encoding="utf-8")
        assert "183 tests" not in text, path
        assert "185 tests" not in text, path
        assert "186 tests" not in text, path
        assert "187 tests" not in text, path
        assert "188 tests" not in text, path
        assert "189 tests" not in text, path
        assert "190 tests" not in text, path
        assert "191 tests" not in text, path
        assert "192 tests" not in text, path
        assert "193 tests" not in text, path
        assert "194 tests" not in text, path
        assert "198 tests" not in text, path
        assert "201 tests" not in text, path
        assert "208 tests" not in text, path
        assert "209 tests" not in text, path
        assert "214 tests" not in text, path
        assert "215 tests" not in text, path
        assert "216 tests" not in text, path
        assert "218 tests" not in text, path
        assert "221 tests" not in text, path
        assert "222 tests" not in text, path
        assert "223 tests" not in text, path
        assert "224 tests" not in text, path
        assert "225 tests" not in text, path
        assert "226 tests" not in text, path
        assert "227 tests" not in text, path
        assert "228 tests" not in text, path
        assert "230 tests" not in text, path
        assert "232 tests" not in text, path
        assert "233 tests" not in text, path
        assert "235 tests" not in text, path
        assert "238 tests" not in text, path
        assert "241 tests" not in text, path
        assert "242 tests" not in text, path
        assert "244 tests" not in text, path
        assert "248 tests" not in text, path
        assert "249 tests" not in text, path
        assert "250 tests" not in text, path
        assert "251 tests" not in text, path
        assert "252 tests" not in text, path
        assert "254 tests" not in text, path
        assert "255 tests" not in text, path
        assert "256 tests" not in text, path
        assert "258 tests" not in text, path
        assert "259 tests" not in text, path
        assert "260 tests" not in text, path
        assert "261 tests" not in text, path
        assert "262 tests" not in text, path
        assert "263 tests" not in text, path
        assert "264 tests" not in text, path
        assert "265 tests" not in text, path
        assert "266 tests" not in text, path
        assert "267 tests" not in text, path
        assert "268 tests" not in text, path
        assert "269 tests" not in text, path
        assert "272 tests" not in text, path
        assert "273 tests" in text, path


def test_release_docs_document_stronger_public_stable_promotion_gate() -> None:
    docs = [
        REPO_ROOT / "README.md",
        REPO_ROOT / "docs" / "release-checklist.md",
        REPO_ROOT / "docs" / "install-update.md",
        REPO_ROOT / "docs" / "onboarding.md",
        REPO_ROOT / "docs" / "release-notes-v0.4.0.md",
    ]
    gate = "--since-hours 96 --min-successful 3 --strict-systemd"
    for path in docs:
        text = path.read_text(encoding="utf-8")
        assert gate in text, path
        assert "--since-hours 30 --min-successful 1 --strict-systemd" in text, path
    assert "status --release-gate" in (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    assert "status --release-gate" in (REPO_ROOT / "docs" / "release-notes-v0.4.0.md").read_text(encoding="utf-8")
    assert "last nightly run" in (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    assert "last successful nightly" in (REPO_ROOT / "docs" / "release-notes-v0.4.0.md").read_text(
        encoding="utf-8"
    )
    assert "defaults to" in (REPO_ROOT / "docs" / "testing.md").read_text(encoding="utf-8")


def test_release_docs_keep_revert_validation_and_provider_grounding_honest() -> None:
    docs = [
        REPO_ROOT / "README.md",
        REPO_ROOT / "CHANGELOG.md",
        REPO_ROOT / "docs" / "safety.md",
        REPO_ROOT / "docs" / "release-notes-v0.4.0.md",
        REPO_ROOT / "docs" / "release-handoff-v0.4.0.md",
    ]
    for path in docs:
        text = path.read_text(encoding="utf-8")
        if "revert" in text:
            assert "not-run" in text or path.name == "CHANGELOG.md", path
        if "provider" in text.lower() or "Provider" in text:
            assert "source_quote" in text or "provenance" in text, path


def test_release_docs_document_provider_doctor_safety() -> None:
    docs = [
        REPO_ROOT / "README.md",
        REPO_ROOT / "CHANGELOG.md",
        REPO_ROOT / "docs" / "release-notes-v0.4.0.md",
        REPO_ROOT / "docs" / "release-handoff-v0.4.0.md",
    ]
    for path in docs:
        text = path.read_text(encoding="utf-8")
        assert "providers doctor" in text, path
        assert "--fix-plan" in text, path
        assert "without" in text.lower(), path
        assert "configuration" in text.lower(), path
        assert "not an end-to-end generation test" in text, path
    assert "never prints secret values" in (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    assert "--from-systemd" in (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    assert "--from-systemd" in (REPO_ROOT / "docs" / "release-notes-v0.4.0.md").read_text(
        encoding="utf-8"
    )
    assert "--from-systemd" in (REPO_ROOT / "docs" / "release-handoff-v0.4.0.md").read_text(
        encoding="utf-8"
    )
    assert "--env-file" in (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    assert "timer-visible" in (REPO_ROOT / "docs" / "testing.md").read_text(encoding="utf-8")
    assert "HERMES_ERSHOV_PROVIDER" in (REPO_ROOT / "docs" / "testing.md").read_text(encoding="utf-8")
    assert "HERMES_ERSHOV_PROVIDER" in (REPO_ROOT / "docs" / "install-update.md").read_text(
        encoding="utf-8"
    )
    assert "without printing secret values" in (REPO_ROOT / "docs" / "install-update.md").read_text(
        encoding="utf-8"
    )
    assert "--require-provider deepseek" in (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    assert "offline-marker drift" in (REPO_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "provider-aware `soak`" in (REPO_ROOT / "docs" / "release-notes-v0.4.0.md").read_text(
        encoding="utf-8"
    )
    assert "--git-timeout-seconds" in (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    assert "`git fetch` or `git pull --ff-only`" in (REPO_ROOT / "docs" / "release-notes-v0.4.0.md").read_text(
        encoding="utf-8"
    )
    assert "<secret>" in (REPO_ROOT / "docs" / "release-handoff-v0.4.0.md").read_text(encoding="utf-8")


def test_release_docs_label_legacy_revert_evidence_as_degraded() -> None:
    docs = [
        REPO_ROOT / "README.md",
        REPO_ROOT / "CHANGELOG.md",
        REPO_ROOT / "docs" / "safety.md",
        REPO_ROOT / "docs" / "release-notes-v0.4.0.md",
        REPO_ROOT / "docs" / "release-handoff-v0.4.0.md",
    ]
    for path in docs:
        text = path.read_text(encoding="utf-8")
        assert "legacy-degraded" in text, path
        assert "post-apply sha" in text or "post-apply shas" in text, path


def test_testing_matrix_is_linked_and_mentions_diverse_release_gates() -> None:
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    testing = (REPO_ROOT / "docs" / "testing.md").read_text(encoding="utf-8")
    checklist = (REPO_ROOT / "docs" / "release-checklist.md").read_text(encoding="utf-8")

    assert "docs/testing.md" in readme
    for phrase in (
        "property-based tests",
        "coverage report",
        "80% minimum gate",
        "plugin wrapper smoke",
        "wheel and source distribution",
        "docs guards",
        "local markdown link/image guards",
        "release workflow guards",
        "Dependabot weekly version-update checks",
        "uv-managed Python package metadata",
        "uv.lock",
        "uv sync --locked --extra dev",
        "uv run --no-cache --no-project --isolated --with dist/*",
        "avoid `pip install`",
        "state-root scoped",
        "required-provider mismatch checks",
        "--fix-plan",
        "CodeQL",
        "OpenSSF Scorecard",
        "ClusterFuzzLite",
        "Atheris",
        "local fuzz harness smoke",
        "ClusterFuzzLite PR/manual fuzzing",
        "ClusterFuzzLite wiring",
        "PyPI Trusted Publishing",
        "Twine package metadata checks",
        "Zizmor GitHub Actions security lint",
        "pip-audit known-vulnerability scan",
        "runtime artifact workflow cache disabled",
        "uploading only wheel/source-distribution files to the PyPI publishing artifact",
        "GitHub artifact attestations",
        "GitHub Release asset attestations",
        "SPDX release SBOM generation",
        "release-manifest.json",
        "release subject names, kinds, sizes, SHA256 digests",
        "SHA256SUMS",
        "release manifest subject digests",
        "public release integrity runbook",
        "docs/release-integrity.md",
        "sha256sum -c",
        "gh release verify-asset",
        "gh attestation verify",
        "release artifact verification",
        "release-event-only PyPI publishing",
        "SARIF uploaded to code scanning",
        "persist-credentials: false",
        "full commit SHAs",
        "timeout-minutes",
        "workflow timeout/concurrency controls",
        "top-level permission minimization",
        "accidental non-package assets in the PyPI upload artifact",
        "https://docs.github.com/actions/using-workflows/workflow-syntax-for-github-actions",
        "https://docs.astral.sh/uv/guides/integration/github/",
        "https://docs.astral.sh/uv/guides/integration/dependabot/",
        "https://github.com/ossf/scorecard-action",
        "https://github.com/ossf/scorecard/blob/main/docs/checks.md#fuzzing",
        "https://google.github.io/clusterfuzzlite/running-clusterfuzzlite/github-actions/",
        "https://google.github.io/clusterfuzzlite/build-integration/python-lang/",
        "https://docs.pypi.org/trusted-publishers/using-a-publisher/",
        "https://docs.github.com/actions/security-for-github-actions/using-artifact-attestations/using-artifact-attestations-to-establish-provenance-for-builds",
        "https://docs.github.com/code-security/supply-chain-security/understanding-your-software-supply-chain/verifying-the-integrity-of-a-release",
        "https://cli.github.com/manual/gh_release_verify-asset",
        "https://cli.github.com/manual/gh_attestation_verify",
        "https://slsa.dev/spec/v1.2/build-provenance",
        "https://github.com/in-toto/attestation/blob/v1.0/spec/v1.0/statement.md",
        "https://spdx.github.io/spdx-spec/v2.3/package-information/",
        "https://github.com/ossf/scorecard/blob/main/docs/checks.md#packaging",
        "https://github.com/pypa/pip-audit",
        "--min-successful 3 --strict-systemd",
        "https://docs.pytest.org/en/stable/explanation/goodpractices.html",
        "https://hypothesis.readthedocs.io/en/latest/stateful.html",
        "https://docs.github.com/actions/guides/building-and-testing-python",
        "https://docs.github.com/en/code-security/reference/code-scanning/workflow-configuration-options",
        "https://docs.github.com/en/code-security/reference/supply-chain-security/dependabot-options-reference",
    ):
        assert phrase in testing
    assert "docs/testing.md" in checklist


def test_release_integrity_runbook_is_public_and_honest() -> None:
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    checklist = (REPO_ROOT / "docs" / "release-checklist.md").read_text(encoding="utf-8")
    notes = (REPO_ROOT / "docs" / "release-notes-v0.4.0.md").read_text(encoding="utf-8")
    handoff = (REPO_ROOT / "docs" / "release-handoff-v0.4.0.md").read_text(encoding="utf-8")
    integrity = (REPO_ROOT / "docs" / "release-integrity.md").read_text(encoding="utf-8")

    assert "docs/release-integrity.md" in readme
    assert "docs/release-integrity.md" in checklist
    assert "docs/release-integrity.md" in notes
    assert "docs/release-integrity.md" in handoff

    for phrase in (
        "It is not release approval.",
        "wheel: `hermes_ershov-<version>-py3-none-any.whl`",
        "source distribution: `hermes_ershov-<version>.tar.gz`",
        "SPDX SBOM: `hermes-ershov-sbom.spdx.json`",
        "release manifest: `release-manifest.json`",
        "checksum manifest: `SHA256SUMS`",
        "scripts/generate_release_sbom.py",
        "scripts/generate_release_manifest.py",
        "scripts/generate_release_checksums.py",
        "scripts/verify_release_artifacts.py",
        "subject names, kinds, sizes, SHA256 digests",
        "(cd dist && sha256sum -c SHA256SUMS)",
        '(cd "$OUT" && sha256sum -c SHA256SUMS)',
        "gh release download",
        "gh release verify-asset",
        "gh attestation verify",
        "--repo ersh123/hermes-ershov",
        "does not prove the product is stable",
        "--since-hours 96 --min-successful 3 --strict-systemd --require-provider deepseek",
        "Manual runs, local artifact verification, and green CI are release-candidate evidence only",
        "https://docs.github.com/code-security/supply-chain-security/understanding-your-software-supply-chain/verifying-the-integrity-of-a-release",
        "https://cli.github.com/manual/gh_release_verify-asset",
        "https://cli.github.com/manual/gh_attestation_verify",
        "https://docs.github.com/actions/security-for-github-actions/using-artifact-attestations/using-artifact-attestations-to-establish-provenance-for-builds",
        "https://slsa.dev/spec/v1.2/build-provenance",
        "https://github.com/in-toto/attestation/blob/v1.0/spec/v1.0/statement.md",
    ):
        assert phrase in integrity

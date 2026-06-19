from __future__ import annotations

from pathlib import Path
import re
import tomllib


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_ci_workflow_shows_release_shaped_test_matrix() -> None:
    text = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    for version in ("'3.11'", "'3.12'", "'3.13'"):
        assert version in text
    for gate in (
        "git diff --check",
        "uses: astral-sh/setup-uv@fac544c07dec837d0ccb6301d7b5580bf5edae39 # v8.2.0",
        "uv sync --locked --extra dev",
        "zizmor .github/workflows",
        "pip-audit . --strict --progress-spinner off",
        "pip-audit --local --skip-editable --progress-spinner off",
        "python -m compileall -q __init__.py src scripts",
        "pytest -q",
        "--cov=hermes_dreaming",
        "--cov-report=xml",
        "--cov-fail-under=80",
        "pytest -q tests/test_pbt.py",
        "python scripts/hermes_plugin_smoke.py",
        "python -m build",
        "twine check --strict dist/*.whl dist/*.tar.gz",
        "python scripts/generate_release_sbom.py",
        "python scripts/generate_release_manifest.py --dist dist",
        "python scripts/generate_release_checksums.py --dist dist",
        "python scripts/verify_release_artifacts.py --dist dist",
        "dist/*.whl",
        "dist/*.tar.gz",
        "uv run --no-cache --no-project --isolated --with dist/*.whl ershov --help",
        "uv run --no-cache --no-project --isolated --with dist/*.whl hermes-ershov --help",
        "uv run --no-cache --no-project --isolated --with dist/*.tar.gz ershov --help",
        "uv run --no-cache --no-project --isolated --with dist/*.tar.gz hermes-ershov --help",
        "providers doctor --provider offline-marker --strict",
        "providers doctor --provider deepseek --env-file /tmp/ershov-wheel-nightly.env --fix-plan --strict",
        "status --release-gate",
        "status --release-gate --state-root /tmp/ershov-wheel-smoke-state --require-provider deepseek --provider-env-file /tmp/ershov-wheel-nightly.env --fix-plan",
        "soak --state-root /tmp/ershov-wheel-smoke-state --since-hours 30 --min-successful 1 --require-timer --require-source systemd",
        "DEEPSEEK_API_KEY=<secret>",
        "sk-ci-do-not-print",
        "secret leaked from soak fix-plan",
    ):
        assert gate in text


def test_codeql_workflow_is_scheduled_and_pr_gated() -> None:
    text = (REPO_ROOT / ".github" / "workflows" / "codeql.yml").read_text(encoding="utf-8")
    top_level_permissions = text.split("concurrency:", 1)[0]
    analyze_job = text.split("  analyze:", 1)[1]

    assert "pull_request:" in text
    assert "schedule:" in text
    assert "workflow_dispatch:" in text
    assert "languages: python" in text
    assert "security-events: write" not in top_level_permissions
    assert "permissions:\n      contents: read\n      security-events: write" in analyze_job
    assert "persist-credentials: false" in text


def test_checkouts_do_not_persist_github_tokens() -> None:
    workflow_paths = sorted((REPO_ROOT / ".github" / "workflows").glob("*.yml"))

    for path in workflow_paths:
        text = path.read_text(encoding="utf-8")
        if "uses: actions/checkout@" in text:
            assert "persist-credentials: false" in text, path


def test_repeatable_analysis_workflows_cancel_stale_runs() -> None:
    for workflow_name in ("ci.yml", "codeql.yml", "scorecard.yml", "cflite_pr.yml", "publish.yml"):
        text = (REPO_ROOT / ".github" / "workflows" / workflow_name).read_text(encoding="utf-8")
        assert "concurrency:" in text, workflow_name
        assert "group: ${{ github.workflow }}-${{ github.ref }}" in text, workflow_name
        assert "cancel-in-progress: true" in text, workflow_name


def test_every_github_actions_job_has_a_timeout() -> None:
    workflow_paths = sorted((REPO_ROOT / ".github" / "workflows").glob("*.yml"))

    for path in workflow_paths:
        lines = path.read_text(encoding="utf-8").splitlines()
        job_lines = [
            index
            for index, line in enumerate(lines)
            if line.startswith("  ") and not line.startswith("    ") and line.rstrip().endswith(":")
        ]
        for index, start in enumerate(job_lines):
            end = job_lines[index + 1] if index + 1 < len(job_lines) else len(lines)
            chunk = "\n".join(lines[start:end])
            if "runs-on:" in chunk:
                assert "timeout-minutes:" in chunk, (path, lines[start].strip())


def test_github_actions_are_pinned_to_full_commit_shas() -> None:
    workflow_paths = sorted((REPO_ROOT / ".github" / "workflows").glob("*.yml"))
    action_line = re.compile(r"uses:\s+[-\w./]+@[0-9a-f]{40}\s+#\s+v?[0-9][-\w.]*$")

    for path in workflow_paths:
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped.startswith("uses: "):
                continue
            assert action_line.search(stripped), (path, stripped)


def test_scorecard_workflow_reports_supply_chain_security_to_code_scanning() -> None:
    text = (REPO_ROOT / ".github" / "workflows" / "scorecard.yml").read_text(encoding="utf-8")

    for phrase in (
        "schedule:",
        "workflow_dispatch:",
        "contents: read",
        "security-events: write",
        "id-token: write",
        "uses: ossf/scorecard-action@4eaacf0543bb3f2c246792bd56e8cdeffafb205a # v2.4.3",
        "uses: actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a # v7",
        "uses: actions/download-artifact@3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c # v8",
        "results_file: scorecard-results.sarif",
        "results_format: sarif",
        "publish_results: true",
        "uses: github/codeql-action/upload-sarif@8aad20d150bbac5944a9f9d289da16a4b0d87c1e # v4",
        "sarif_file: scorecard-results.sarif",
        "persist-credentials: false",
    ):
        assert phrase in text
    top_level_permissions = text.split("jobs:", 1)[0]
    assert "security-events: write" not in top_level_permissions
    assert "id-token: write" not in top_level_permissions


def test_dependabot_monitors_actions_and_python_dependencies() -> None:
    text = (REPO_ROOT / ".github" / "dependabot.yml").read_text(encoding="utf-8")

    assert "version: 2" in text
    for ecosystem in ('package-ecosystem: "github-actions"', 'package-ecosystem: "uv"'):
        assert ecosystem in text
    assert text.count('directory: "/"') == 2
    assert text.count('interval: "weekly"') == 2
    assert "open-pull-requests-limit: 5" in text

    for workflow_name in ("ci.yml", "release.yml", "publish.yml"):
        workflow = (REPO_ROOT / ".github" / "workflows" / workflow_name).read_text(encoding="utf-8")
        assert "uv sync --locked --extra dev" in workflow
        assert "uv run --locked --extra dev" in workflow
        assert "pip install" not in workflow


def test_publish_workflow_uses_release_only_trusted_publishing() -> None:
    text = (REPO_ROOT / ".github" / "workflows" / "publish.yml").read_text(encoding="utf-8")
    top_level_permissions = text.split("jobs:", 1)[0]
    build_chunk, publish_chunk = text.split("  attest-and-publish:", 1)

    for phrase in (
        "release:",
        "types: [published]",
        "workflow_dispatch:",
        "permissions:\n  contents: read",
        "uv sync --locked --extra dev --python \"3.12\"",
        "uv run --locked --extra dev zizmor .github/workflows",
        "uv run --locked --extra dev pip-audit . --strict --progress-spinner off",
        "uv run --locked --extra dev pip-audit --local --skip-editable --progress-spinner off",
        "uv run --locked --extra dev python -m compileall -q __init__.py src scripts fuzzers",
        "uv run --locked --extra dev pytest -q --cov=hermes_dreaming",
        "uv run --locked --extra dev pytest -q tests/test_pbt.py tests/test_fuzz_harness.py",
        "uv run --locked --extra dev python scripts/hermes_plugin_smoke.py",
        "uv run --locked --extra dev python -m build",
        "uv run --locked --extra dev twine check --strict dist/*.whl dist/*.tar.gz",
        "uv run --locked --extra dev python scripts/generate_release_sbom.py --output dist/hermes-ershov-sbom.spdx.json",
        "uv run --locked --extra dev python scripts/generate_release_manifest.py --dist dist",
        "uv run --locked --extra dev python scripts/generate_release_checksums.py --dist dist",
        "uv run --locked --extra dev python scripts/verify_release_artifacts.py --dist dist",
        "uv run --no-cache --no-project --isolated --with dist/*.whl ershov --help",
        "uv run --no-cache --no-project --isolated --with dist/*.whl hermes-ershov --help",
        "uv run --no-cache --no-project --isolated --with dist/*.tar.gz hermes-ershov --help",
        "uv run --no-cache --no-project --isolated --with dist/*.tar.gz python -m hermes_ershov --help",
        "uses: actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a # v7",
        "uses: actions/download-artifact@3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c # v8",
        "uses: actions/attest-build-provenance@a2bbfa25375fe432b6a289bc6b6cd05ecd0c4c32 # v4.1.0",
        "uses: pypa/gh-action-pypi-publish@cef221092ed1bacb1cc03d23a2d87d1d172e277b # v1.14.0",
        "packages-dir: dist/",
        "attestations: true",
    ):
        assert phrase in text
    assert "path: |\n            dist/*.whl\n            dist/*.tar.gz" in build_chunk
    assert "dist/*.whl" in build_chunk
    assert "dist/*.tar.gz" in build_chunk
    assert "dist/*\n" not in build_chunk
    assert "id-token: write" not in top_level_permissions
    assert "attestations: write" not in top_level_permissions
    assert "id-token: write" not in build_chunk
    assert "attestations: write" not in build_chunk
    assert "if: github.event_name == 'release' && github.event.action == 'published'" in publish_chunk
    assert "environment: pypi" in publish_chunk
    assert "permissions:\n      contents: read\n      id-token: write\n      attestations: write" in publish_chunk
    assert "password:" not in publish_chunk
    assert "api-token" not in publish_chunk.lower()


def test_python_classifier_matches_ci_matrix() -> None:
    pyproject = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    ci = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    testing_doc = (REPO_ROOT / "docs" / "testing.md").read_text(encoding="utf-8")

    for version in ("3.11", "3.12", "3.13"):
        assert f"'{version}'" in ci
        assert f"Programming Language :: Python :: {version}" in pyproject
        assert version in testing_doc


def test_pyproject_exposes_documented_console_aliases() -> None:
    pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    scripts = pyproject["project"]["scripts"]

    for alias in ("ershov", "hermes-ershov", "mnemos", "nightmem", "dreaming"):
        assert scripts[alias] == "hermes_dreaming.cli:main"


def test_pyproject_dev_extra_includes_package_workflow_and_dependency_security_checkers() -> None:
    pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    dev_deps = pyproject["project"]["optional-dependencies"]["dev"]

    assert any(dep.startswith("twine>=") for dep in dev_deps)
    assert any(dep.startswith("pip-audit>=") for dep in dev_deps)
    assert any(dep.startswith("zizmor>=") for dep in dev_deps)


def test_release_and_publish_workflows_disable_uv_cache_for_runtime_artifacts() -> None:
    for workflow_name in ("release.yml", "publish.yml"):
        text = (REPO_ROOT / ".github" / "workflows" / workflow_name).read_text(encoding="utf-8")
        setup_chunk = text.split("Set up uv", 1)[1].split("Sync locked", 1)[0]

        assert "enable-cache: false" in setup_chunk
        assert "enable-cache: true" not in setup_chunk


def test_clusterfuzzlite_python_fuzzing_integration_is_present() -> None:
    workflow = (REPO_ROOT / ".github" / "workflows" / "cflite_pr.yml").read_text(encoding="utf-8")
    project_yaml = (REPO_ROOT / ".clusterfuzzlite" / "project.yaml").read_text(encoding="utf-8")
    dockerfile = (REPO_ROOT / ".clusterfuzzlite" / "Dockerfile").read_text(encoding="utf-8")
    build_script = (REPO_ROOT / ".clusterfuzzlite" / "build.sh").read_text(encoding="utf-8")
    fuzzer = (REPO_ROOT / "fuzzers" / "ershov_safety_fuzzer.py").read_text(encoding="utf-8")

    for phrase in (
        "pull_request:",
        "workflow_dispatch:",
        "contents: read",
        "timeout-minutes: 20",
        "uses: google/clusterfuzzlite/actions/build_fuzzers@884713a6c30a92e5e8544c39945cd7cb630abcd1 # v1",
        "uses: google/clusterfuzzlite/actions/run_fuzzers@884713a6c30a92e5e8544c39945cd7cb630abcd1 # v1",
        "language: python",
        "fuzz-seconds: 60",
        "persist-credentials: false",
    ):
        assert phrase in workflow
    assert project_yaml.strip() == "language: python"
    assert "base-builder-python@sha256:f9c1da511e00d7072cb2ca41ca02af9090f39581d2efb45a62da7b9fb9dac850" in dockerfile
    assert "PYTHONPATH=\"$SRC/hermes-ershov/src" in build_script
    assert "pip install" not in build_script
    assert "pyinstaller --distpath \"$OUT\" --onefile" in build_script
    assert "def TestOneInput(data: bytes) -> None:" in fuzzer
    assert "atheris.Setup(sys.argv, TestOneInput)" in fuzzer

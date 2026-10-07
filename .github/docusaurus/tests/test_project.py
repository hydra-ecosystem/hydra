import json
import os
import runpy
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

SHARED = Path(__file__).parents[1]
read_project = runpy.run_path(str(SHARED / "project.py"))["project"]
AUDIT = SHARED / "templates/dependency_audit.py"
WORKFLOW = Path(__file__).parents[2] / "workflows/docusaurus-audit.yml"
if not WORKFLOW.exists():
    WORKFLOW = SHARED / "templates/dependency-audit.yml"


def site(root, name="website"):
    directory = root / name
    directory.mkdir(parents=True)
    (directory / "package.json").write_text(
        json.dumps(
            {
                "packageManager": "pnpm@11.21.0",
                "dependencies": {"@docusaurus/core": "^3.10.2"},
                "scripts": {"build": "arbitrary project-owned build"},
            }
        )
    )
    (root / ".github").mkdir(exist_ok=True)
    (root / ".github/docusaurus.json").write_text(json.dumps({"directory": name}))
    return directory


def test_project_directory_is_configuration_and_build_is_opaque(tmp_path):
    directory = site(tmp_path, "docs/site with spaces")
    before = (directory / "package.json").read_bytes()
    actual, baseline = read_project(tmp_path)
    assert actual == directory
    assert baseline == {"node": "24", "pnpm": "11.21.0", "minimumReleaseAge": 14400}
    assert (directory / "package.json").read_bytes() == before
    env = tmp_path / "environment"
    subprocess.run(
        [
            sys.executable,
            str(SHARED / "project.py"),
            "--root",
            str(tmp_path),
            "--github-env",
            str(env),
        ],
        check=True,
    )
    assert (
        env.read_text()
        == "NPM_PROJECT=docs/site with spaces\nDOCUSAURUS_NODE_VERSION=24\n"
    )


@pytest.mark.parametrize(
    "name",
    [
        "../outside",
        "/outside",
        "website\nINJECTED=true",
        "website\rINJECTED=true",
        "docs/site+plus",
        "docs/site\twith-tab",
        "docs/siteé",
        "",
    ],
)
def test_project_rejects_invalid_directory(tmp_path, name):
    (tmp_path / ".github").mkdir()
    (tmp_path / ".github/docusaurus.json").write_text(json.dumps({"directory": name}))
    with pytest.raises(ValueError):
        read_project(tmp_path)


def test_reader_cli_output_is_accepted_by_helper_cli_without_network(
    tmp_path, monkeypatch
):
    directory = site(tmp_path, "docs/site with spaces")
    (directory / "pnpm-workspace.yaml").write_text("packages:\n  - .\n")
    (directory / "pnpm-lock.yaml").write_text(
        "lockfileVersion: '9.0'\nimporters:\n  .: {}\npackages: {}\n"
    )
    environment = tmp_path / "environment"
    subprocess.run(
        [
            sys.executable,
            str(SHARED / "project.py"),
            "--root",
            str(tmp_path),
            "--github-env",
            str(environment),
        ],
        check=True,
    )
    npm_project = environment.read_text().splitlines()[0].removeprefix("NPM_PROJECT=")

    audit = runpy.run_path(str(AUDIT))
    monkeypatch.setitem(
        audit["main"].__globals__, "prepare", lambda selected: "mocked report\n"
    )
    report = tmp_path / "report.md"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            str(AUDIT),
            "--directory",
            npm_project,
            "--report",
            str(report),
        ],
    )
    audit["main"]()
    assert report.read_text() == "mocked report\n"


@pytest.mark.parametrize(
    "name", ["docs/site+plus", "docs/site\twith-tab", "docs/siteé"]
)
def test_dependency_audit_rejects_unsupported_directory_syntax(tmp_path, name):
    result = subprocess.run(
        [
            sys.executable,
            str(AUDIT),
            "--directory",
            name,
            "--report",
            str(tmp_path / "report.md"),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert "directory must be a relative npm project path" in result.stderr


def test_project_rejects_configuration_overriding_standard(tmp_path):
    site(tmp_path)
    (tmp_path / ".github/docusaurus.json").write_text(
        json.dumps({"directory": "website", "pnpm": "latest"})
    )
    with pytest.raises(ValueError, match="only project directory and schedule"):
        read_project(tmp_path)


def test_project_rejects_symlink_outside_checkout(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (root / "website").symlink_to(outside, target_is_directory=True)
    (root / ".github").mkdir()
    (root / ".github/docusaurus.json").write_text('{"directory": "website"}')
    with pytest.raises(ValueError, match="outside"):
        read_project(root)


@pytest.mark.parametrize(
    "event, ref, succeeds",
    [
        ("workflow_dispatch", "refs/heads/main", True),
        ("workflow_dispatch", "refs/heads/feature", False),
        ("schedule", "refs/heads/main", True),
        ("schedule", "refs/heads/feature", True),
    ],
)
def test_manual_audit_requires_default_branch(event, ref, succeeds):
    workflow = yaml.safe_load(WORKFLOW.read_text())
    guard = workflow["jobs"]["audit"]["steps"][0]
    assert guard["name"] == "Validate manual dispatch ref"
    result = subprocess.run(
        ["bash", "-c", guard["run"]],
        env={
            **os.environ,
            "DEFAULT_BRANCH": "main",
            "GITHUB_EVENT_NAME": event,
            "GITHUB_REF": ref,
        },
        capture_output=True,
    )
    assert (result.returncode == 0) is succeeds


def test_publisher_loads_config_after_guard_before_download():
    steps = yaml.safe_load(WORKFLOW.read_text())["jobs"]["pull-request"]["steps"]
    guard = next(
        i
        for i, step in enumerate(steps)
        if step.get("name") == "Verify audit dependency state"
    )
    config = next(
        i
        for i, step in enumerate(steps)
        if step.get("name") == "Read project configuration"
    )
    download = next(
        i
        for i, step in enumerate(steps)
        if "download-artifact@" in step.get("uses", "")
    )
    assert guard < config < download

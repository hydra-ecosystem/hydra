# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved
import io
import logging
import os
import pathlib
import re
import subprocess
import sys
import tarfile
import tempfile
import textwrap
import zipfile
from contextlib import nullcontext
from typing import List, cast

import pytest
from omegaconf import OmegaConf

from tools.release import release
from tools.release.release import (
    DevReleasePackageInfo,
    LocalPackageInfo,
    Package,
    PackageInfo,
    fail_if_any_target_version_published,
    filter_packages,
    format_dev_release_package_table,
    is_publishable,
    parse_version,
    validate_dev_version,
    validate_local_version,
)


def test_publishable_when_local_version_is_older_than_latest_but_unpublished() -> None:
    info = PackageInfo(
        name="hydra-core",
        local_version=parse_version("1.3.5"),
        latest_version=parse_version("1.4.0"),
        local_version_published=False,
    )

    assert is_publishable(info)


def test_not_publishable_when_local_version_is_already_published() -> None:
    info = PackageInfo(
        name="hydra-core",
        local_version=parse_version("1.3.5"),
        latest_version=parse_version("1.4.0"),
        local_version_published=True,
    )

    assert not is_publishable(info)


def test_validate_local_version_accepts_expected_version() -> None:
    info = LocalPackageInfo(name="hydra-core", local_version=parse_version("1.4.0"))

    validate_local_version(info, parse_version("1.4.0"))


def test_validate_local_version_rejects_unexpected_version() -> None:
    info = LocalPackageInfo(name="hydra-core", local_version=parse_version("1.4.0"))

    with pytest.raises(
        ValueError,
        match="hydra-core version is 1.4.0; expected 1.4.1",
    ):
        validate_local_version(info, parse_version("1.4.1"))


def test_validate_dev_version_accepts_dev_version() -> None:
    validate_dev_version(parse_version("1.4.0.dev3"))


def test_validate_dev_version_rejects_non_dev_version() -> None:
    with pytest.raises(
        ValueError,
        match="Dev releases require a \\.devN version; got 1.4.0",
    ):
        validate_dev_version(parse_version("1.4.0"))


def test_format_dev_release_package_table_includes_publish_plan() -> None:
    table = format_dev_release_package_table(
        [
            DevReleasePackageInfo(
                name="hydra-core",
                local_version=parse_version("1.4.0.dev2"),
                target_version=parse_version("1.4.0.dev3"),
                latest_version=parse_version("1.4.0.dev2"),
                target_version_published=False,
            )
        ]
    )

    assert "Package" in table
    assert "Current local version" in table
    assert "Target version" in table
    assert "PyPI status" in table
    assert "hydra-core" in table
    assert "1.4.0.dev2" in table
    assert "1.4.0.dev3" in table
    assert "not published" in table


def test_fail_if_any_target_version_published_rejects_published_package() -> None:
    infos = [
        DevReleasePackageInfo(
            name="hydra-core",
            local_version=parse_version("1.4.0.dev2"),
            target_version=parse_version("1.4.0.dev3"),
            latest_version=parse_version("1.4.0.dev3"),
            target_version_published=True,
        )
    ]

    with pytest.raises(
        ValueError,
        match="Target version is already published for selected packages: hydra-core",
    ):
        fail_if_any_target_version_published(infos)


def test_filter_packages_keeps_requested_packages_in_order() -> None:
    packages = {
        "hydra": Package(path="."),
        "hydra_optuna_sweeper": Package(path="plugins/hydra_optuna_sweeper"),
        "hydra_ray_launcher": Package(path="plugins/hydra_ray_launcher"),
    }

    selected = filter_packages(packages, " hydra_ray_launcher, hydra_optuna_sweeper ")

    assert list(selected) == ["hydra_ray_launcher", "hydra_optuna_sweeper"]


def test_filter_packages_rejects_unknown_packages() -> None:
    packages = {
        "hydra": Package(path="."),
        "hydra_optuna_sweeper": Package(path="plugins/hydra_optuna_sweeper"),
    }

    with pytest.raises(
        ValueError,
        match=(
            "Unknown package filter: hydra_rq_launcher. "
            "Available packages in selected set: hydra, hydra_optuna_sweeper"
        ),
    ):
        filter_packages(packages, "hydra_rq_launcher")


def test_dispatch_publish_workflow_reports_approval_link(monkeypatch, caplog) -> None:
    calls = []
    run_url = "https://github.com/hydra-ecosystem/hydra/actions/runs/123"

    def fake_run_checked(cmd, cwd=None, stdin=None):
        calls.append((cmd, cwd, stdin))
        return f"{run_url}\n"

    monkeypatch.setattr(release, "_run_checked", fake_run_checked)
    monkeypatch.setattr(
        release,
        "get_remote_url",
        lambda hydra_root, vcs: "https://github.com/hydra-ecosystem/hydra",
    )

    with caplog.at_level(logging.INFO, logger=release.log.name):
        release.dispatch_publish_workflow(
            "/repo",
            "sl",
            "hydra-full-release",
            parse_version("1.4.0.dev3"),
            "main",
            "a" * 40,
            "hydra_optuna_sweeper",
        )

    assert calls == [
        (
            [
                "gh",
                "workflow",
                "run",
                "publish.yml",
                "--repo",
                "hydra-ecosystem/hydra",
                "--ref",
                "main",
                "--json",
            ],
            "/repo",
            '{"package_set": "hydra-full-release", '
            '"expected_version": "1.4.0.dev3", '
            f'"commit": "{"a" * 40}", '
            '"publish": "true", '
            '"only": "hydra_optuna_sweeper"}',
        )
    ]
    assert caplog.messages[-1] == (
        "The workflow will build and verify artifacts before waiting for "
        f"pypi-publish approval. Approve the PyPI upload within 7 days at: {run_url}"
    )


def test_publish_workflow_gates_only_the_pypi_upload() -> None:
    workflow = pathlib.Path(".github/workflows/publish.yml").read_text()

    assert workflow.count("environment: pypi-publish") == 1
    assert re.search(
        r"\n  pypi-publish:\n.*?\n    environment: pypi-publish\n",
        workflow,
        re.S,
    )


def test_publish_workflow_cleans_up_transient_artifacts() -> None:
    workflow = pathlib.Path(".github/workflows/publish.yml").read_text()
    cleanup_job = workflow.split("\n  cleanup-artifact:\n", maxsplit=1)[1]

    assert "retention-days: 7" in workflow
    assert "artifact_id: ${{ steps.upload-artifacts.outputs.artifact-id }}" in workflow
    assert "- pypi-publish" in cleanup_job
    assert "actions: write" in cleanup_job
    assert "contents:" not in cleanup_job
    assert "continue-on-error: true" in cleanup_job
    assert (
        "ARTIFACT_ID: ${{ needs.build-artifacts.outputs.artifact_id }}" in cleanup_job
    )
    assert "gh api --method DELETE" in cleanup_job


def _run_publish_plan(commit: str, head_sha: str = "b" * 40, ref: str = "main"):
    """Drive publish.yml's release-plan script directly.

    The script decides which commit the whole publish run builds, so it is
    exercised here rather than only in CI.
    """
    workflow = pathlib.Path(".github/workflows/publish.yml").read_text()
    match = re.search(r"python <<'PY'\n(.*?)\n\s*PY\n", workflow, re.S)
    assert match is not None, "release-plan script not found in publish.yml"
    script = textwrap.dedent(match.group(1))

    with tempfile.TemporaryDirectory() as tmp:
        output = pathlib.Path(tmp, "output")
        output.touch()
        pathlib.Path(tmp, "summary").touch()
        env = {
            **os.environ,
            "REF_NAME": ref,
            "HEAD_SHA": head_sha,
            "INPUT_COMMIT": commit,
            "INPUT_PACKAGE_SET": "hydra-full-release",
            "INPUT_ONLY": "",
            "INPUT_EXPECTED_VERSION": "1.4.0.dev9",
            "INPUT_PUBLISH": "true",
            "GITHUB_OUTPUT": str(output),
            "GITHUB_STEP_SUMMARY": str(pathlib.Path(tmp, "summary")),
        }
        proc = subprocess.run(
            [sys.executable, "-c", script], env=env, capture_output=True, text=True
        )
        outputs = dict(
            line.split("=", 1)
            for line in output.read_text().splitlines()
            if "=" in line
        )
    return proc.returncode, outputs.get("checkout_ref")


def test_publish_plan_pins_dispatched_branch_tip_without_a_commit_input() -> None:
    returncode, checkout_ref = _run_publish_plan("")

    assert returncode == 0
    assert checkout_ref == "b" * 40


def test_publish_plan_pins_the_requested_commit() -> None:
    returncode, checkout_ref = _run_publish_plan("f" * 40)

    assert returncode == 0
    assert checkout_ref == "f" * 40


@pytest.mark.parametrize(
    "commit",
    [
        "f67e393af44e",
        "F" * 40,
        "1.3_branch",
        "main; rm -rf /",
    ],
)
def test_publish_plan_rejects_a_commit_that_is_not_a_full_sha(commit: str) -> None:
    returncode, checkout_ref = _run_publish_plan(commit)

    assert returncode == 1
    assert checkout_ref is None


def test_dev_release_dispatches_the_commit_it_reports_after_bumping(
    monkeypatch, caplog
) -> None:
    """The recovery path creates a commit between reporting and dispatching.

    Whatever commit the operator is told about must be the commit that is
    published, so the two must be resolved from the same point in the sequence.
    """
    commits = iter(["a" * 40, "b" * 40])
    current = {"sha": next(commits)}
    dispatched = {}

    monkeypatch.setattr(release, "detect_vcs", lambda hydra_root: "sl")
    monkeypatch.setattr(release, "ensure_publish_tools", lambda *a: None)
    monkeypatch.setattr(release, "ensure_clean_worktree", lambda *a: None)
    monkeypatch.setattr(
        release, "ensure_publish_commit_exists_on_remote", lambda *a: None
    )
    monkeypatch.setattr(release, "collect_dev_release_package_info", lambda *a: [])
    monkeypatch.setattr(release, "format_dev_release_package_table", lambda infos: "")
    monkeypatch.setattr(release, "fail_if_any_target_version_published", lambda i: None)
    monkeypatch.setattr(release, "copy_release_workspace", lambda root, tmp: tmp)
    monkeypatch.setattr(
        release, "validate_dev_release_artifacts", lambda *a, **kw: None
    )
    monkeypatch.setattr(release, "set_package_versions", lambda *a: None)
    monkeypatch.setattr(
        release, "get_worktree_status", lambda *a: "M hydra/__init__.py"
    )
    monkeypatch.setattr(release, "push_current_ref", lambda *a: None)
    monkeypatch.setattr(
        release, "get_current_commit", lambda hydra_root, vcs: current["sha"]
    )

    def fake_commit_dev_release(hydra_root, vcs, target_version):
        current["sha"] = next(commits)

    def fake_dispatch(hydra_root, vcs, package_set, target_version, ref, commit, only):
        dispatched["commit"] = commit

    monkeypatch.setattr(release, "commit_dev_release", fake_commit_dev_release)
    monkeypatch.setattr(release, "dispatch_publish_workflow", fake_dispatch)

    cfg = cast(
        release.Config,
        OmegaConf.create(
            {
                "version": "1.4.0.dev3",
                "dry_run": False,
                "publish": True,
                "workflow_ref": "main",
                "commit": "",
                "only": "",
                "packages": {},
                "repository": {"name": "pypi"},
            }
        ),
    )

    with caplog.at_level(logging.INFO, logger=release.log.name):
        release.run_dev_release(cfg, "/repo", pathlib.Path("/repo/build"), "hydra-core")

    reported = [
        line.split("commit=")[1].split()[0]
        for line in caplog.messages
        if "commit=" in line
    ]

    assert dispatched["commit"] == "b" * 40
    assert reported == ["b" * 40]


def test_dev_release_pins_initial_current_commit_when_no_bump_is_needed(
    monkeypatch,
) -> None:
    commits = iter(["a" * 40, "b" * 40])
    dispatched = {}

    monkeypatch.setattr(release, "detect_vcs", lambda hydra_root: "sl")
    monkeypatch.setattr(release, "get_current_commit", lambda *a: next(commits))
    monkeypatch.setattr(
        release, "ensure_publish_commit_exists_on_remote", lambda *a: None
    )
    monkeypatch.setattr(release, "ensure_publish_tools", lambda *a: None)
    monkeypatch.setattr(release, "ensure_clean_worktree", lambda *a: None)
    monkeypatch.setattr(release, "collect_dev_release_package_info", lambda *a: [])
    monkeypatch.setattr(release, "format_dev_release_package_table", lambda infos: "")
    monkeypatch.setattr(release, "fail_if_any_target_version_published", lambda i: None)
    monkeypatch.setattr(release, "copy_release_workspace", lambda root, tmp: tmp)
    monkeypatch.setattr(
        release, "validate_dev_release_artifacts", lambda *a, **kw: None
    )
    monkeypatch.setattr(release, "set_package_versions", lambda *a: None)
    monkeypatch.setattr(release, "get_worktree_status", lambda *a: "")
    monkeypatch.setattr(
        release,
        "dispatch_publish_workflow",
        lambda *args: dispatched.update(commit=args[5]),
    )

    cfg = cast(
        release.Config,
        OmegaConf.create(
            {
                "version": "1.4.0.dev10",
                "dry_run": False,
                "publish": True,
                "workflow_ref": "main",
                "commit": "",
                "only": "",
                "packages": {},
                "repository": {"name": "pypi"},
            }
        ),
    )

    release.run_dev_release(cfg, "/repo", pathlib.Path("/repo/build"), "hydra-core")

    assert dispatched == {"commit": "a" * 40}


def test_missing_remote_commit_exits_with_clean_error(monkeypatch) -> None:
    commit = "a" * 40
    monkeypatch.setattr(
        release,
        "get_remote_url",
        lambda hydra_root, vcs: "https://github.com/hydra-ecosystem/hydra",
    )

    def fail_run_checked(cmd, cwd=None, stdin=None):
        raise subprocess.CalledProcessError(1, cmd)

    monkeypatch.setattr(release, "_run_checked", fail_run_checked)

    with pytest.raises(SystemExit) as exc_info:
        release.ensure_publish_commit_exists_on_remote("/repo", "sl", commit)

    assert str(exc_info.value) == (
        f"Cannot publish commit {commit}: it could not be confirmed on the "
        "configured GitHub remote.\n"
        "Push that commit to GitHub or fix GitHub access, then rerun."
    )


def test_publish_commit_check_queries_exact_sha_on_github(monkeypatch) -> None:
    commit = "a" * 40
    calls = []
    monkeypatch.setattr(
        release,
        "get_remote_url",
        lambda hydra_root, vcs: "git@github.com:hydra-ecosystem/hydra.git",
    )

    def fake_run_checked(cmd, cwd=None, stdin=None):
        calls.append((cmd, cwd, stdin))
        return ""

    monkeypatch.setattr(release, "_run_checked", fake_run_checked)

    release.ensure_publish_commit_exists_on_remote("/repo", "sl", commit)

    assert calls == [
        (
            [
                "gh",
                "api",
                "--silent",
                f"repos/hydra-ecosystem/hydra/commits/{commit}",
            ],
            "/repo",
            None,
        )
    ]


@pytest.mark.parametrize(
    ("requested_commit", "current_commit", "expected_commit"),
    [("c" * 40, "a" * 40, "c" * 40), ("", "a" * 40, "a" * 40)],
)
def test_dev_release_checks_selected_commit_on_remote_first(
    monkeypatch, tmp_path, requested_commit, current_commit, expected_commit
) -> None:
    events = []

    monkeypatch.setattr(release, "detect_vcs", lambda hydra_root: "sl")
    monkeypatch.setattr(release, "get_current_commit", lambda *a: current_commit)

    def check_publish_tools(*args):
        events.append("publish tools")

    def check_clean_worktree(*args):
        events.append("clean worktree")

    def fail_remote_commit(hydra_root, vcs, commit):
        events.append(f"remote commit {commit}")
        raise SystemExit("remote commit missing")

    def archive_workspace(*args):
        events.append("archive")
        pytest.fail("archive must not run before remote-commit validation")

    monkeypatch.setattr(release, "ensure_publish_tools", check_publish_tools)
    monkeypatch.setattr(release, "ensure_clean_worktree", check_clean_worktree)
    monkeypatch.setattr(
        release, "ensure_publish_commit_exists_on_remote", fail_remote_commit
    )
    monkeypatch.setattr(release, "archive_release_workspace", archive_workspace)

    cfg = cast(
        release.Config,
        OmegaConf.create(
            {
                "version": "1.4.0.dev9",
                "dry_run": False,
                "publish": True,
                "workflow_ref": "main",
                "commit": requested_commit,
                "only": "",
                "packages": {},
                "repository": {"name": "pypi"},
            }
        ),
    )

    with pytest.raises(SystemExit, match="remote commit missing"):
        release.run_dev_release(cfg, "/repo", tmp_path / "build", "hydra-core")

    assert events == [f"remote commit {expected_commit}"]


@pytest.mark.parametrize(
    "commit",
    [
        "f67e393af44e",
        "F" * 40,
        "main",
        "main; rm -rf /",
    ],
)
def test_validate_release_commit_rejects_invalid_commit(commit: str) -> None:
    with pytest.raises(ValueError, match="full 40-character lowercase SHA"):
        release.validate_release_commit(commit)


def test_archive_release_workspace_uses_selected_sapling_commit(
    monkeypatch, tmp_path
) -> None:
    calls = []
    commit = "a" * 40

    def fake_run_checked(cmd, cwd=None, stdin=None):
        calls.append((cmd, cwd, stdin))
        return ""

    monkeypatch.setattr(release, "_run_checked", fake_run_checked)

    workspace = release.archive_release_workspace("/repo", "sl", commit, tmp_path)

    assert workspace == tmp_path / "hydra"
    assert calls == [
        (
            ["sl", "archive", "-r", commit, "-I", "glob:**", str(workspace)],
            "/repo",
            None,
        )
    ]


def test_archive_release_workspace_uses_selected_git_commit(
    monkeypatch, tmp_path
) -> None:
    calls = []
    unpacked = []
    commit = "b" * 40

    def fake_run_checked(cmd, cwd=None, stdin=None):
        calls.append((cmd, cwd, stdin))
        pathlib.Path(cmd[4]).touch()
        return ""

    monkeypatch.setattr(release, "_run_checked", fake_run_checked)
    monkeypatch.setattr(
        release.shutil,
        "unpack_archive",
        lambda archive, workspace: unpacked.append((archive, workspace)),
    )

    workspace = release.archive_release_workspace("/repo", "git", commit, tmp_path)

    archive = tmp_path / "hydra.tar"
    assert workspace == tmp_path / "hydra"
    assert calls == [
        (
            [
                "git",
                "archive",
                "--format=tar",
                "--output",
                str(archive),
                commit,
            ],
            "/repo",
            None,
        )
    ]
    assert unpacked == [(str(archive), str(workspace))]
    assert not archive.exists()


def test_dev_release_dispatches_requested_commit_without_mutating_checkout(
    monkeypatch, tmp_path
) -> None:
    commit = "c" * 40
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    dispatched = {}
    mutations = []
    validation = {}

    monkeypatch.setattr(release, "detect_vcs", lambda hydra_root: "sl")
    monkeypatch.setattr(release, "ensure_publish_tools", lambda *a: None)
    monkeypatch.setattr(release, "ensure_clean_worktree", lambda *a: None)
    monkeypatch.setattr(
        release, "ensure_publish_commit_exists_on_remote", lambda *a: None
    )
    monkeypatch.setattr(
        release,
        "archive_release_workspace",
        lambda hydra_root, vcs, selected_commit, destination: workspace,
    )
    monkeypatch.setattr(release, "collect_dev_release_package_info", lambda *a: [])
    monkeypatch.setattr(release, "format_dev_release_package_table", lambda infos: "")
    monkeypatch.setattr(release, "fail_if_any_target_version_published", lambda i: None)

    def fake_validate_artifacts(
        cfg, release_root, build_dir, target_version, set_versions=True
    ):
        validation["root"] = release_root
        validation["set_versions"] = set_versions

    monkeypatch.setattr(
        release, "validate_dev_release_artifacts", fake_validate_artifacts
    )
    monkeypatch.setattr(
        release, "set_package_versions", lambda *a: mutations.append("set versions")
    )
    monkeypatch.setattr(
        release, "commit_dev_release", lambda *a: mutations.append("commit")
    )
    monkeypatch.setattr(
        release, "push_current_ref", lambda *a: mutations.append("push")
    )

    def fake_dispatch(
        hydra_root, vcs, package_set, target_version, ref, selected_commit, only
    ):
        dispatched["commit"] = selected_commit

    monkeypatch.setattr(release, "dispatch_publish_workflow", fake_dispatch)

    cfg = cast(
        release.Config,
        OmegaConf.create(
            {
                "version": "1.4.0.dev9",
                "dry_run": False,
                "publish": True,
                "workflow_ref": "main",
                "commit": commit,
                "only": "",
                "packages": {},
                "repository": {"name": "pypi"},
            }
        ),
    )

    release.run_dev_release(cfg, "/repo", tmp_path / "build", "hydra-core")

    assert dispatched["commit"] == commit
    assert mutations == []
    assert validation == {"root": str(workspace), "set_versions": False}


def test_check_build_artifacts_upgrades_smoke_environment_pip(
    monkeypatch, tmp_path
) -> None:
    wheel = _make_wheel(tmp_path / "package.whl", ["package/__init__.py"])
    smoke_dir = tmp_path / "smoke"
    calls = []

    def fake_run_checked(cmd, cwd=None, stdin=None):
        calls.append(cmd)
        return ""

    monkeypatch.setattr(release, "_run_checked", fake_run_checked)
    monkeypatch.setattr(
        release.tempfile,
        "TemporaryDirectory",
        lambda prefix: nullcontext(str(smoke_dir)),
    )

    release.check_build_artifacts(tmp_path)

    venv_path = smoke_dir / "venv"
    smoke_python = release._python_bin(venv_path)
    assert calls == [
        [release.sys.executable, "-m", "twine", "check", str(wheel)],
        [release.sys.executable, "-m", "venv", str(venv_path)],
        [str(smoke_python), "-m", "pip", "install", "--upgrade", "pip"],
        [str(smoke_python), "-m", "pip", "install", "--no-deps", str(wheel)],
    ]


@pytest.mark.parametrize(
    ("output", "expected"),
    [
        (
            "https://github.com/hydra-ecosystem/hydra",
            "https://github.com/hydra-ecosystem/hydra",
        ),
        (
            "default = https://github.com/hydra-ecosystem/hydra",
            "https://github.com/hydra-ecosystem/hydra",
        ),
    ],
)
def test_get_remote_url_accepts_sapling_path_output_formats(
    monkeypatch, output, expected
) -> None:
    monkeypatch.setattr(release, "_single_line", lambda cmd, cwd: output)

    assert release.get_remote_url("/repo", "sl") == expected


@pytest.mark.parametrize(
    "remote_url",
    [
        "https://github.com/hydra-ecosystem/hydra",
        "https://github.com/hydra-ecosystem/hydra.git",
        "ssh://git@github.com/hydra-ecosystem/hydra",
        "ssh://git@github.com/hydra-ecosystem/hydra.git",
        "git@github.com:hydra-ecosystem/hydra.git",
    ],
)
def test_get_github_repo_slug_accepts_common_github_remote_urls(remote_url) -> None:
    assert release.get_github_repo_slug(remote_url) == "hydra-ecosystem/hydra"


ANTLR_JAR = "build_helpers/bin/antlr-4.11.1-complete.jar"


def _make_sdist(path: pathlib.Path, names: List[str]) -> pathlib.Path:
    with tarfile.open(path, "w:gz") as tar:
        for name in names:
            tar.addfile(tarfile.TarInfo(name), io.BytesIO(b""))
    return path


def _make_wheel(path: pathlib.Path, names: List[str]) -> pathlib.Path:
    with zipfile.ZipFile(path, "w") as zf:
        for name in names:
            zf.writestr(name, b"")
    return path


def test_sdist_shipping_a_jar_must_ship_its_license(tmp_path) -> None:
    sdist = _make_sdist(
        tmp_path / "hydra-core-1.4.0.tar.gz",
        [
            f"hydra-core-1.4.0/{ANTLR_JAR}",
            "hydra-core-1.4.0/ATTRIBUTION/LICENSE-antlr4",
        ],
    )

    release.check_bundled_jar_licenses([sdist])


def test_sdist_shipping_a_jar_without_its_license_is_rejected(tmp_path) -> None:
    sdist = _make_sdist(
        tmp_path / "hydra-core-1.4.0.tar.gz", [f"hydra-core-1.4.0/{ANTLR_JAR}"]
    )

    with pytest.raises(ValueError, match="ATTRIBUTION/LICENSE-antlr4"):
        release.check_bundled_jar_licenses([sdist])


def test_sdist_without_a_jar_needs_no_license(tmp_path) -> None:
    sdist = _make_sdist(
        tmp_path / "hydra-colorlog-1.4.0.tar.gz", ["hydra-colorlog-1.4.0/setup.py"]
    )

    release.check_bundled_jar_licenses([sdist])


def test_wheel_carrying_a_build_only_jar_is_rejected(tmp_path) -> None:
    wheel = _make_wheel(
        tmp_path / "hydra_core-1.4.0-py3-none-any.whl",
        [
            "hydra/__init__.py",
            ANTLR_JAR,
            "hydra_core-1.4.0.dist-info/licenses/ATTRIBUTION/LICENSE-antlr4",
        ],
    )

    with pytest.raises(ValueError, match="is a wheel and contains a JAR"):
        release.check_bundled_jar_licenses([wheel])


def test_wheel_without_a_jar_is_accepted(tmp_path) -> None:
    wheel = _make_wheel(
        tmp_path / "hydra_core-1.4.0-py3-none-any.whl",
        [
            "hydra/__init__.py",
            "hydra_core-1.4.0.dist-info/licenses/ATTRIBUTION/LICENSE-antlr4",
        ],
    )

    release.check_bundled_jar_licenses([wheel])

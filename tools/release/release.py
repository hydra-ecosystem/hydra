# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from dataclasses import dataclass
from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import hydra
import requests  # type: ignore[import-untyped]
from hydra.core.config_store import ConfigStore
from hydra.core.hydra_config import HydraConfig
from hydra.test_utils.test_utils import find_parent_dir_containing, run_python_script
from omegaconf import II, MISSING, SI, DictConfig, OmegaConf
from packaging.version import Version, parse

log = logging.getLogger(__name__)


class Action(Enum):
    check = 1
    build = 2
    bump = 3
    set_version = 4
    validate_versions = 5
    dev_release = 6


class BuildPolicy(Enum):
    unpublished = 1
    all = 2


class Repository(Enum):
    pypi = 1
    testpypi = 2


class VersionType(Enum):
    SETUP = 1
    FILE = 2


@dataclass
class Package:
    name: str = II("parent_key:")
    module: str = II(".name")
    path: str = MISSING
    version_type: VersionType = VersionType.FILE
    version_file: str = SI("${.module}/__init__.py")


@dataclass
class Config:
    dry_run: bool = False
    action: Action = Action.check
    packages: Dict[str, Package] = MISSING
    build_targets: Tuple[str, ...] = ("--sdist", "--wheel")
    build_dir: str = "build"
    build_policy: BuildPolicy = BuildPolicy.unpublished
    clean_build_dir: bool = False
    repository: Repository = Repository.pypi
    require_artifacts: bool = False
    version: Optional[str] = None
    publish: bool = False
    workflow_ref: str = "main"
    commit: str = ""
    only: str = ""


ConfigStore.instance().store(name="config_schema", node=Config)


@lru_cache()
def get_metadata(repository: Repository, package_name: str) -> Optional[DictConfig]:
    host = {
        Repository.pypi: "pypi.org",
        Repository.testpypi: "test.pypi.org",
    }[repository]
    url = f"https://{host}/pypi/{package_name}/json"
    with requests.get(url, timeout=10) as response:
        if response.status_code == 404:
            return None
        response.raise_for_status()
        ret = OmegaConf.create(response.content.decode("utf-8"))
    response.close()
    assert isinstance(ret, DictConfig)
    return ret


def get_latest_release(metadata: Optional[DictConfig]) -> Optional[Version]:
    if metadata is None:
        return None
    ret: List[Version] = []
    for ver, files in metadata.releases.items():
        for file in files:
            if file.packagetype == "bdist_wheel" and file.yanked is not True:
                v = parse_version(ver)
                ret.append(v)
    if len(ret) == 0:
        return None
    return sorted(ret)[-1]


def is_version_published(metadata: Optional[DictConfig], version: Version) -> bool:
    if metadata is None:
        return False
    for ver in metadata.releases:
        if parse_version(ver) == version:
            return True
    return False


@dataclass
class PackageInfo:
    name: str
    local_version: Version
    latest_version: Optional[Version]
    local_version_published: bool


@dataclass
class LocalPackageInfo:
    name: str
    local_version: Version


@dataclass
class DevReleasePackageInfo:
    name: str
    local_version: Version
    target_version: Version
    latest_version: Optional[Version]
    target_version_published: bool


def parse_version(ver: str) -> Version:
    v = parse(ver)
    assert isinstance(v, Version)
    return v


def _last_output_line(out: str) -> str:
    lines = [line.strip() for line in out.splitlines() if line.strip()]
    if not lines:
        raise ValueError("Expected command output")
    return lines[-1]


def get_local_package_info(path: str) -> LocalPackageInfo:
    try:
        prev = os.getcwd()
        path = os.path.abspath(path)
        os.chdir(path)
        out, _err = run_python_script(
            cmd=[f"{path}/setup.py", "--version"], allow_warnings=True
        )
        package_name, _err = run_python_script(
            cmd=[f"{path}/setup.py", "--name"], allow_warnings=True
        )
    finally:
        os.chdir(prev)

    return LocalPackageInfo(
        name=_last_output_line(package_name),
        local_version=parse_version(_last_output_line(out)),
    )


def get_package_info(repository: Repository, path: str) -> PackageInfo:
    local = get_local_package_info(path)
    remote_metadata = get_metadata(repository, local.name)
    latest = get_latest_release(remote_metadata)
    return PackageInfo(
        name=local.name,
        local_version=local.local_version,
        latest_version=latest,
        local_version_published=is_version_published(
            remote_metadata, local.local_version
        ),
    )


def is_publishable(info: PackageInfo) -> bool:
    return not info.local_version_published


def validate_local_version(info: LocalPackageInfo, expected_version: Version) -> None:
    if info.local_version != expected_version:
        raise ValueError(
            f"{info.name} version is {info.local_version}; expected {expected_version}"
        )


def format_latest_version(version: Optional[Version]) -> str:
    if version is None:
        return "<not published>"
    return str(version)


def validate_dev_version(version: Version) -> None:
    if not version.is_devrelease:
        raise ValueError(f"Dev releases require a .devN version; got {version}")


def filter_packages(packages: Dict[str, Package], only: str) -> Dict[str, Package]:
    names = [name.strip() for name in only.split(",") if name.strip()]
    if not names:
        return packages

    unknown = sorted(set(names) - set(packages.keys()))
    if unknown:
        available = ", ".join(sorted(packages.keys()))
        requested = ", ".join(unknown)
        raise ValueError(
            f"Unknown package filter: {requested}. "
            f"Available packages in selected set: {available}"
        )

    return {name: packages[name] for name in names}


def collect_dev_release_package_info(
    repository: Repository,
    packages: Dict[str, Package],
    hydra_root: str,
    target_version: Version,
) -> List[DevReleasePackageInfo]:
    ret = []
    for package in packages.values():
        pkg_path = os.path.normpath(os.path.join(hydra_root, package.path))
        local = get_local_package_info(pkg_path)
        remote_metadata = get_metadata(repository, local.name)
        ret.append(
            DevReleasePackageInfo(
                name=local.name,
                local_version=local.local_version,
                target_version=target_version,
                latest_version=get_latest_release(remote_metadata),
                target_version_published=is_version_published(
                    remote_metadata, target_version
                ),
            )
        )
    return ret


def format_dev_release_package_table(infos: List[DevReleasePackageInfo]) -> str:
    rows = [
        (
            "Package",
            "Current local version",
            "Target version",
            "PyPI status",
            "Latest PyPI version",
        )
    ]
    for info in infos:
        status = (
            "already published" if info.target_version_published else "not published"
        )
        rows.append(
            (
                info.name,
                str(info.local_version),
                str(info.target_version),
                status,
                format_latest_version(info.latest_version),
            )
        )

    widths = [max(len(row[idx]) for row in rows) for idx in range(len(rows[0]))]
    lines = []
    for index, row in enumerate(rows):
        lines.append("  ".join(cell.ljust(widths[col]) for col, cell in enumerate(row)))
        if index == 0:
            lines.append("  ".join("-" * width for width in widths))
    return "\n".join(lines)


def fail_if_any_target_version_published(infos: List[DevReleasePackageInfo]) -> None:
    published = [info.name for info in infos if info.target_version_published]
    if published:
        packages = ", ".join(sorted(published))
        raise ValueError(
            f"Target version is already published for selected packages: {packages}"
        )


def build_package(cfg: Config, pkg_path: str, build_dir: str) -> None:
    try:
        prev = os.getcwd()
        os.chdir(pkg_path)
        local = get_local_package_info(".")
        log.info(f"Building {local.name} ({local.local_version})")
        shutil.rmtree("dist", ignore_errors=True)
        cmd = ["-m", "build", "-o", build_dir, *cfg.build_targets]
        run_python_script(
            cmd=cmd,
            allow_warnings=False,
        )
    finally:
        os.chdir(prev)


def prepare_build_dir(cfg: Config, build_dir_path: Path) -> None:
    if cfg.clean_build_dir and build_dir_path.exists():
        shutil.rmtree(build_dir_path)
    elif build_dir_path.exists() and any(build_dir_path.iterdir()):
        raise ValueError(
            f"Build directory {build_dir_path} is not empty. "
            "Use clean_build_dir=true or choose an empty build_dir."
        )
    build_dir_path.mkdir(parents=True, exist_ok=True)


def _next_version(version: str) -> str:
    cur = parse(version)
    assert isinstance(cur, Version)
    if cur.is_devrelease:
        prefix = "dev"
        assert cur.dev is not None
        num = cur.dev + 1
        new_version = f"{cur.major}.{cur.minor}.{cur.micro}.{prefix}{num}"
    elif cur.is_prerelease:
        assert cur.pre is not None
        prefix = cur.pre[0]
        num = cur.pre[1] + 1
        new_version = f"{cur.major}.{cur.minor}.{cur.micro}.{prefix}{num}"
    elif cur.is_postrelease:
        assert cur.post is not None
        num = cur.post + 1
        new_version = f"{cur.major}.{cur.minor}.{cur.micro}.{num}"
    else:
        micro = cur.micro + 1
        new_version = f"{cur.major}.{cur.minor}.{micro}"

    return str(new_version)


def bump_version_in_file(
    cfg: Config, name: str, ver_file: Path, target_version: Optional[str] = None
) -> None:
    loaded = ver_file.read_text("utf-8")
    # https://regex101.com/r/DoxaSI/1
    regex = r"((?:__)?version(?:__)?\s*=\s*)((?:\"|\')(.*?)(?:\"|\'))"

    matches = re.search(regex, loaded)

    if matches:
        new_version = target_version or _next_version(matches.group(3))
        parse_version(new_version)
        log.info(f"Setting version of {name} from {matches.group(3)} to {new_version}")
        subst = f'{matches.group(1)}"{new_version}"'
        result = re.sub(regex, subst, loaded, count=0)
        if not cfg.dry_run:
            ver_file.write_text(result)
    else:
        raise ValueError(f"Could not find version in {ver_file}")


def bump_version(
    cfg: Config,
    package: Package,
    hydra_root: str,
    target_version: Optional[str] = None,
) -> None:
    if package.version_type == VersionType.SETUP:
        ver_file = Path(hydra_root) / package.path / "setup.py"
        bump_version_in_file(cfg, package.name, ver_file, target_version)
    elif package.version_type == VersionType.FILE:
        ver_file = Path(hydra_root) / package.path / package.version_file
        bump_version_in_file(cfg, package.name, ver_file, target_version)
    else:
        raise ValueError()


def set_package_versions(cfg: Config, hydra_root: str, target_version: str) -> None:
    for package in cfg.packages.values():
        bump_version(cfg, package, hydra_root, target_version=target_version)


def validate_package_versions(
    packages: Dict[str, Package], hydra_root: str, expected_version: Version
) -> None:
    for package in packages.values():
        pkg_path = os.path.normpath(os.path.join(hydra_root, package.path))
        local = get_local_package_info(pkg_path)
        validate_local_version(local, expected_version)
        log.info(f"\U0000274a : {local.name} : {local.local_version}")


def _run_checked(
    cmd: List[str], cwd: Optional[str] = None, stdin: Optional[str] = None
) -> str:
    log.info("Running: %s", " ".join(cmd))
    result = subprocess.run(
        cmd,
        cwd=cwd,
        check=False,
        encoding="utf-8",
        input=stdin,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    if result.stdout:
        log.info(result.stdout.rstrip())
    if result.returncode != 0:
        raise subprocess.CalledProcessError(
            result.returncode,
            cmd,
            output=result.stdout,
            stderr=None,
        )
    return result.stdout


def _python_bin(venv_path: Path) -> Path:
    if os.name == "nt":
        return venv_path / "Scripts" / "python.exe"
    return venv_path / "bin" / "python"


# The ANTLR generator JAR is redistributed in the sdist, so the sdist has to
# carry ANTLR's license. It is a build-time tool and has no business in a wheel.
ANTLR_LICENSE = "ATTRIBUTION/LICENSE-antlr4"


def _archive_names(path: Path) -> List[str]:
    if path.name.endswith(".tar.gz"):
        with tarfile.open(path) as tar:
            return tar.getnames()
    with zipfile.ZipFile(path) as zf:
        return zf.namelist()


def check_bundled_jar_licenses(artifacts: List[Path]) -> None:
    """An sdist that ships a JAR must ship its license; a wheel must ship no JAR."""
    for path in artifacts:
        if not (path.name.endswith(".tar.gz") or path.suffix == ".whl"):
            continue
        names = _archive_names(path)
        jars = [name for name in names if name.endswith(".jar")]
        if not jars:
            continue
        if path.suffix == ".whl":
            raise ValueError(f"{path.name} is a wheel and contains a JAR: {jars}")
        if not any(name.endswith(ANTLR_LICENSE) for name in names):
            raise ValueError(f"{path.name} contains {jars} but no {ANTLR_LICENSE}")


def check_build_artifacts(build_dir_path: Path) -> None:
    artifacts = sorted(path for path in build_dir_path.iterdir() if path.is_file())
    if not artifacts:
        raise ValueError(f"No artifacts found in {build_dir_path}")

    check_bundled_jar_licenses(artifacts)

    _run_checked([sys.executable, "-m", "twine", "check", *map(str, artifacts)])

    wheels = [path for path in artifacts if path.suffix == ".whl"]
    if not wheels:
        raise ValueError(f"No wheels found in {build_dir_path}")

    with tempfile.TemporaryDirectory(prefix="hydra-release-smoke-") as tmp:
        venv_path = Path(tmp) / "venv"
        _run_checked([sys.executable, "-m", "venv", str(venv_path)])
        smoke_python = _python_bin(venv_path)
        _run_checked([str(smoke_python), "-m", "pip", "install", "--upgrade", "pip"])
        _run_checked(
            [
                str(smoke_python),
                "-m",
                "pip",
                "install",
                "--no-deps",
                *map(str, wheels),
            ]
        )


def validate_dev_release_artifacts(
    cfg: Config,
    hydra_root: str,
    build_dir_path: Path,
    target_version: Version,
    set_versions: bool = True,
) -> None:
    if set_versions:
        set_package_versions(cfg, hydra_root, str(target_version))
    else:
        validate_package_versions(cfg.packages, hydra_root, target_version)
    prepare_build_dir(cfg, build_dir_path)
    for package in cfg.packages.values():
        pkg_path = os.path.normpath(os.path.join(hydra_root, package.path))
        build_package(cfg, pkg_path, str(build_dir_path))
    check_build_artifacts(build_dir_path)


def copy_release_workspace(hydra_root: str, destination: Path) -> Path:
    workspace = destination / "hydra"
    shutil.copytree(
        hydra_root,
        workspace,
        ignore=shutil.ignore_patterns(
            ".git",
            ".sl",
            ".venv",
            ".nox",
            ".mypy_cache",
            ".pytest_cache",
            "build",
            "dist",
            "node_modules",
            "temp",
        ),
    )
    return workspace


def validate_release_commit(commit: str) -> str:
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError(
            f"commit must be a full 40-character lowercase SHA; got {commit!r}"
        )
    return commit


def archive_release_workspace(
    hydra_root: str, vcs: str, commit: str, destination: Path
) -> Path:
    workspace = destination / "hydra"
    if vcs == "sl":
        _run_checked(
            ["sl", "archive", "-r", commit, "-I", "glob:**", str(workspace)],
            cwd=hydra_root,
        )
    else:
        archive = destination / "hydra.tar"
        _run_checked(
            [
                "git",
                "archive",
                "--format=tar",
                "--output",
                str(archive),
                commit,
            ],
            cwd=hydra_root,
        )
        workspace.mkdir()
        shutil.unpack_archive(str(archive), str(workspace))
        archive.unlink()
    return workspace


def detect_vcs(hydra_root: str) -> str:
    root = Path(hydra_root)
    if (root / ".sl").exists():
        return "sl"
    if (root / ".git").exists():
        return "git"
    raise ValueError(f"Could not find a supported VCS checkout at {hydra_root}")


def ensure_clean_worktree(hydra_root: str, vcs: str) -> None:
    status = get_worktree_status(hydra_root, vcs)
    if status:
        raise ValueError(
            "Working tree must be clean before publishing a dev release. "
            f"Found:\n{status}"
        )


def _single_line(cmd: List[str], cwd: str) -> str:
    value = _run_checked(cmd, cwd=cwd).strip()
    if not value:
        raise ValueError(f"Command did not produce output: {' '.join(cmd)}")
    return value.splitlines()[-1].strip()


def get_remote_url(hydra_root: str, vcs: str) -> str:
    if vcs == "sl":
        line = _single_line(["sl", "paths", "default"], hydra_root)
        prefix = "default = "
        return line[len(prefix) :] if line.startswith(prefix) else line
    return _single_line(["git", "remote", "get-url", "origin"], hydra_root)


def get_github_repo_slug(remote_url: str) -> str:
    patterns = [
        r"^https://github\.com/(?P<slug>[^/]+/[^/]+?)(?:\.git)?$",
        r"^ssh://git@github\.com/(?P<slug>[^/]+/[^/]+?)(?:\.git)?$",
        r"^git@github\.com:(?P<slug>[^/]+/[^/]+?)(?:\.git)?$",
    ]
    for pattern in patterns:
        match = re.fullmatch(pattern, remote_url)
        if match is not None:
            return match.group("slug")
    raise ValueError(f"Could not determine GitHub repo from remote URL: {remote_url}")


def get_current_commit(hydra_root: str, vcs: str) -> str:
    if vcs == "sl":
        return _single_line(["sl", "log", "-r", ".", "-T", "{node}"], hydra_root)
    return _single_line(["git", "rev-parse", "HEAD"], hydra_root)


def ensure_publish_commit_exists_on_remote(
    hydra_root: str, vcs: str, commit: str
) -> None:
    try:
        repo_slug = get_github_repo_slug(get_remote_url(hydra_root, vcs))
        _run_checked(
            ["gh", "api", "--silent", f"repos/{repo_slug}/commits/{commit}"],
            cwd=hydra_root,
        )
    except (OSError, subprocess.CalledProcessError, ValueError):
        raise SystemExit(
            f"Cannot publish commit {commit}: it could not be confirmed on the "
            "configured GitHub remote.\n"
            "Push that commit to GitHub or fix GitHub access, then rerun."
        ) from None


def get_worktree_status(hydra_root: str, vcs: str) -> str:
    cmd = [vcs, "status"] if vcs == "sl" else ["git", "status", "--porcelain"]
    return _run_checked(cmd, cwd=hydra_root).strip()


def commit_dev_release(hydra_root: str, vcs: str, target_version: Version) -> None:
    message = f"Prepare Hydra {target_version}"
    if vcs == "sl":
        _run_checked(["sl", "commit", "-m", message], cwd=hydra_root)
    else:
        _run_checked(["git", "commit", "-am", message], cwd=hydra_root)


def push_current_ref(hydra_root: str, vcs: str, workflow_ref: str) -> None:
    if vcs == "sl":
        _run_checked(["sl", "push", "--to", workflow_ref, "-r", "."], cwd=hydra_root)
    else:
        _run_checked(["git", "push", "origin", f"HEAD:{workflow_ref}"], cwd=hydra_root)


def ensure_publish_tools(hydra_root: str, vcs: str) -> None:
    _run_checked([vcs, "--version"], cwd=hydra_root)
    _run_checked(["gh", "--version"], cwd=hydra_root)


def dispatch_publish_workflow(
    hydra_root: str,
    vcs: str,
    package_set: str,
    target_version: Version,
    workflow_ref: str,
    commit: str,
    only: str = "",
) -> None:
    repo_slug = get_github_repo_slug(get_remote_url(hydra_root, vcs))
    inputs = {
        "package_set": package_set,
        "expected_version": str(target_version),
        "commit": commit,
        "publish": "true",
        "only": only,
    }
    output = _run_checked(
        [
            "gh",
            "workflow",
            "run",
            "publish.yml",
            "--repo",
            repo_slug,
            "--ref",
            workflow_ref,
            "--json",
        ],
        cwd=hydra_root,
        stdin=json.dumps(inputs),
    )
    run_url = next(
        (line for line in reversed(output.splitlines()) if line.startswith("https://")),
        f"https://github.com/{repo_slug}/actions/workflows/publish.yml",
    )
    log.info(
        "The workflow will build and verify artifacts before waiting for "
        "pypi-publish approval. Approve the PyPI upload within 7 days at: %s",
        run_url,
    )


def selected_package_set_name() -> str:
    choices = HydraConfig.get().runtime.choices
    selected = choices.get("set", "hydra-full-release")
    return str(selected)


def run_dev_release(
    cfg: Config, hydra_root: str, build_dir_path: Path, package_set: str
) -> None:
    if not cfg.version:
        raise ValueError("action=dev_release requires version=<target version>")
    if cfg.dry_run:
        raise ValueError(
            "action=dev_release uses publish=false for dry runs; "
            "do not set dry_run=true"
        )
    target_version = parse_version(cfg.version)
    validate_dev_version(target_version)
    requested_commit = cfg.commit.strip()
    if requested_commit:
        validate_release_commit(requested_commit)

    workflow_ref = cfg.workflow_ref.strip()
    if not workflow_ref:
        raise ValueError("workflow_ref must not be empty")

    vcs = detect_vcs(hydra_root)
    release_commit = requested_commit or get_current_commit(hydra_root, vcs)
    if cfg.publish:
        ensure_publish_commit_exists_on_remote(hydra_root, vcs, release_commit)
        ensure_publish_tools(hydra_root, vcs)
        ensure_clean_worktree(hydra_root, vcs)

    with tempfile.TemporaryDirectory(prefix="hydra-dev-release-") as tmp:
        if requested_commit:
            workspace = archive_release_workspace(
                hydra_root, vcs, requested_commit, Path(tmp)
            )
        else:
            workspace = copy_release_workspace(hydra_root, Path(tmp))

        infos = collect_dev_release_package_info(
            cfg.repository, cfg.packages, str(workspace), target_version
        )
        log.info(
            "Dev release package plan:\n%s", format_dev_release_package_table(infos)
        )
        fail_if_any_target_version_published(infos)

        validate_dev_release_artifacts(
            cfg,
            str(workspace),
            build_dir_path,
            target_version,
            set_versions=not requested_commit,
        )

    def log_dispatch(verb: str, commit: str) -> None:
        log.info(
            "%s Publish to PyPI: ref=%s commit=%s package_set=%s "
            "expected_version=%s only=%s publish=true",
            verb,
            workflow_ref,
            commit,
            package_set,
            target_version,
            cfg.only or "<none>",
        )

    if not cfg.publish:
        log_dispatch("Would dispatch", release_commit)
        log.info(
            "Dry run complete. No commit, push, GitHub workflow dispatch, "
            "GitHub Release, or PyPI upload was performed."
        )
        return

    if requested_commit:
        commit = release_commit
    else:
        set_package_versions(cfg, hydra_root, str(target_version))
        if get_worktree_status(hydra_root, vcs):
            commit_dev_release(hydra_root, vcs, target_version)
            push_current_ref(hydra_root, vcs, workflow_ref)
            commit = get_current_commit(hydra_root, vcs)
        else:
            log.info(
                "Selected packages are already at %s; skipping commit",
                target_version,
            )
            commit = release_commit
    log_dispatch("Dispatching", commit)
    dispatch_publish_workflow(
        hydra_root, vcs, package_set, target_version, workflow_ref, commit, cfg.only
    )


OmegaConf.register_resolver("parent_key", lambda _parent_: _parent_._key())


@hydra.main(config_path="conf", config_name="config")
def main(cfg: Config) -> None:
    hydra_root = find_parent_dir_containing(target="ATTRIBUTION")
    package_set = selected_package_set_name()
    cfg.packages = filter_packages(cfg.packages, cfg.only)
    build_dir_path = Path(cfg.build_dir).expanduser()
    if not build_dir_path.is_absolute():
        build_dir_path = Path(os.getcwd()) / build_dir_path
    if cfg.action == Action.build:
        prepare_build_dir(cfg, build_dir_path)
    else:
        build_dir_path.mkdir(parents=True, exist_ok=True)
    build_dir = str(build_dir_path)
    log.info(f"Build outputs : {build_dir}")
    if cfg.action == Action.check:
        log.info(f"Checking for unpublished packages on {cfg.repository.name}")
        for package in cfg.packages.values():
            pkg_path = os.path.normpath(os.path.join(hydra_root, package.path))
            ret = get_package_info(cfg.repository, pkg_path)
            if ret.local_version_published and ret.local_version == ret.latest_version:
                log.info(f"\U0000274a : {ret.name} : match ({ret.latest_version})")
            elif ret.local_version_published:
                latest_version = format_latest_version(ret.latest_version)
                log.info(
                    f"\U0000274a : {ret.name} : already published "
                    f"(local={ret.local_version}, latest={latest_version})"
                )
            else:
                latest_version = format_latest_version(ret.latest_version)
                log.info(
                    f"\U0000274b : {ret.name} : unpublished "
                    f"(local={ret.local_version}, latest={latest_version})"
                )
    elif cfg.action == Action.build:
        log.info(
            f"Building packages with policy {cfg.build_policy.name} against {cfg.repository.name}"
        )
        built_any = False
        for package in cfg.packages.values():
            pkg_path = os.path.normpath(os.path.join(hydra_root, package.path))
            if cfg.build_policy == BuildPolicy.all:
                build_package(cfg, pkg_path, build_dir)
                built_any = True
            else:
                ret = get_package_info(cfg.repository, pkg_path)
                if is_publishable(ret):
                    build_package(cfg, pkg_path, build_dir)
                    built_any = True
                else:
                    latest_version = format_latest_version(ret.latest_version)
                    log.info(
                        f"Skipping {ret.name} ({ret.local_version}); "
                        f"version already exists on {cfg.repository.name} "
                        f"(latest={latest_version})"
                    )
        if cfg.require_artifacts and not built_any:
            raise ValueError(
                f"No publishable artifacts were built for {cfg.repository.name}"
            )
    elif cfg.action == Action.bump:
        log.info(f"Bumping version of packages published on {cfg.repository.name}")
        for package in cfg.packages.values():
            pkg_path = os.path.normpath(os.path.join(hydra_root, package.path))
            ret = get_package_info(cfg.repository, pkg_path)
            if ret.local_version == ret.latest_version:
                bump_version(cfg, package, hydra_root)
    elif cfg.action == Action.set_version:
        if not cfg.version:
            raise ValueError("action=set_version requires version=<target version>")
        parse_version(cfg.version)
        log.info(f"Setting package versions to {cfg.version}")
        for package in cfg.packages.values():
            bump_version(cfg, package, hydra_root, target_version=cfg.version)
    elif cfg.action == Action.validate_versions:
        if not cfg.version:
            raise ValueError(
                "action=validate_versions requires version=<target version>"
            )
        expected_version = parse_version(cfg.version)
        log.info(f"Validating package versions match {expected_version}")
        validate_package_versions(cfg.packages, hydra_root, expected_version)
    elif cfg.action == Action.dev_release:
        run_dev_release(cfg, hydra_root, build_dir_path, package_set)

    else:
        raise ValueError("Unexpected action type")


if __name__ == "__main__":
    main()

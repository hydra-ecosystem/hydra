# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved
import codecs
import errno
import logging
import os
import re
import shutil
import subprocess
from functools import partial
from os.path import abspath, basename, dirname, exists, isdir, join
from pathlib import Path

from setuptools import Command
from setuptools.command import build_py, develop, sdist

log = logging.getLogger(__name__)


def find_version(*file_paths: str) -> str:
    with codecs.open(os.path.join(*file_paths), "r") as fp:
        version_file = fp.read()
    version_match = re.search(r"^__version__ = ['\"]([^'\"]*)['\"]", version_file, re.M)
    if version_match:
        return version_match.group(1)
    raise RuntimeError("Unable to find version string.")


def matches(patterns: list[str], string: str) -> bool:
    string = string.replace("\\", "/")
    for pattern in patterns:
        if re.match(pattern, string):
            return True
    return False


def find_(
    root: str,
    rbase: str,
    include_files: list[str],
    include_dirs: list[str],
    excludes: list[str],
    scan_exclude: list[str],
) -> list[str]:
    files = []
    scan_root = os.path.join(root, rbase)
    with os.scandir(scan_root) as it:
        for entry in it:
            path = os.path.join(rbase, entry.name)
            if matches(scan_exclude, path):
                continue

            if entry.is_dir():
                if matches(include_dirs, path):
                    if not matches(excludes, path):
                        files.append(path)
                else:
                    ret = find_(
                        root=root,
                        rbase=path,
                        include_files=include_files,
                        include_dirs=include_dirs,
                        excludes=excludes,
                        scan_exclude=scan_exclude,
                    )
                    files.extend(ret)
            else:
                if matches(include_files, path) and not matches(excludes, path):
                    files.append(path)

    return files


def find(
    root: str,
    include_files: list[str],
    include_dirs: list[str],
    excludes: list[str],
    scan_exclude: list[str] | None = None,
) -> list[str]:
    if scan_exclude is None:
        scan_exclude = []
    return find_(
        root=root,
        rbase="",
        include_files=include_files,
        include_dirs=include_dirs,
        excludes=excludes,
        scan_exclude=scan_exclude,
    )


class CleanCommand(Command):  # type: ignore
    """
    Our custom command to clean out junk files.
    """

    description = "Cleans out generated and junk files we don't want in the repo"
    dry_run: bool
    user_options: list[str] = []

    def run(self) -> None:
        files = find(
            ".",
            include_files=["^hydra/grammar/gen/.*"],
            include_dirs=[
                "\\.egg-info$",
                "^.pytest_cache$",
                ".*/__pycache__$",
                ".*/multirun$",
                ".*/outputs$",
                "^build$",
            ],
            scan_exclude=["^.git$", "^.nox/.*$", "^website/.*$"],
            excludes=[".*\\.gitignore$"],
        )

        if self.dry_run:
            print("Would clean up the following files and dirs")
            print("\n".join(files))
        else:
            for f in files:
                if exists(f):
                    if isdir(f):
                        shutil.rmtree(f, ignore_errors=True)
                    else:
                        os.unlink(f)

    def initialize_options(self) -> None:
        pass

    def finalize_options(self) -> None:
        pass


def run_antlr(cmd: Command) -> None:
    try:
        log.info("Generating parsers with antlr4")
        cmd.run_command("antlr")
    except OSError as e:
        if e.errno == errno.ENOENT:
            msg = f"| Unable to generate parsers: {e} |"
            msg = "=" * len(msg) + "\n" + msg + "\n" + "=" * len(msg)
            log.critical(f"{msg}")
            exit(1)
        else:
            raise


class BuildPyCommand(build_py.build_py):
    def run(self) -> None:
        if not self.dry_run:
            self.run_command("clean")
            run_antlr(self)
        build_py.build_py.run(self)


class Develop(develop.develop):
    def run(self) -> None:
        if not self.dry_run:
            run_antlr(self)
        develop.develop.run(self)


class SDistCommand(sdist.sdist):
    dry_run: bool

    def run(self) -> None:
        if not self.dry_run:
            self.run_command("clean")
            run_antlr(self)
        sdist.sdist.run(self)


class ANTLRCommand(Command):  # type: ignore
    """Generate parsers using ANTLR."""

    description = "Run ANTLR"
    user_options: list[str] = []

    def run(self) -> None:
        """Run command."""
        root_dir = abspath(dirname(__file__))
        project_root = abspath(dirname(basename(__file__)))
        for grammar in [
            "hydra/grammar/OverrideLexer.g4",
            "hydra/grammar/OverrideParser.g4",
        ]:
            command = [
                "java",
                "-jar",
                join(root_dir, "bin/antlr-4.11.1-complete.jar"),
                "-Dlanguage=Python3",
                "-o",
                join(project_root, "hydra/grammar/gen/"),
                "-Xexact-output-dir",
                "-visitor",
                join(project_root, grammar),
            ]

            log.info(f"Generating parser for Python3: {command}")

            subprocess.check_call(command)

            log.info("Replacing imports of antlr4 in generated parsers")
            self._fix_imports()

    def initialize_options(self) -> None:
        pass

    def finalize_options(self) -> None:
        pass

    def _fix_imports(self) -> None:
        """Fix imports from the generated parsers to use the vendored antlr4 instead"""
        build_dir = Path(__file__).parent.absolute()
        project_root = build_dir.parent
        lib = "antlr4"
        pkgname = "omegaconf.vendor"

        replacements = [
            partial(  # import antlr4 -> import omegaconf.vendor.antlr4
                re.compile(r"(^\s*)import {}\n".format(lib), flags=re.M).sub,
                r"\1from {} import {}\n".format(pkgname, lib),
            ),
            partial(  # from antlr4 -> from fomegaconf.vendor.antlr4
                re.compile(r"(^\s*)from {}(\.|\s+)".format(lib), flags=re.M).sub,
                r"\1from {}.{}\2".format(pkgname, lib),
            ),
        ]

        path = project_root / "hydra" / "grammar" / "gen"
        for item in path.iterdir():
            if item.is_file() and item.name.endswith(".py"):
                text = item.read_text("utf8")
                for replacement in replacements:
                    text = replacement(text)
                item.write_text(text, "utf8")

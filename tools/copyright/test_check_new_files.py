# SPDX-FileCopyrightText: Contributors to Hydra
# SPDX-License-Identifier: MIT

import subprocess
from pathlib import Path

import check_new_files

NEW_HEADER = """\
# SPDX-FileCopyrightText: Contributors to Hydra
# SPDX-License-Identifier: MIT
"""


def write(root: Path, relative_path: str, content: str) -> Path:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return Path(relative_path)


def test_accepts_new_header(tmp_path: Path) -> None:
    path = write(tmp_path, "module.py", f"{NEW_HEADER}\nvalue = 10\n")

    assert check_new_files.check_paths([path], root=tmp_path) == []


def test_accepts_new_header_after_shebang(tmp_path: Path) -> None:
    path = write(tmp_path, "script.py", f"#!/usr/bin/env python3\n\n{NEW_HEADER}")

    assert check_new_files.check_paths([path], root=tmp_path) == []


def test_rejects_legacy_header(tmp_path: Path) -> None:
    path = write(
        tmp_path,
        "module.py",
        "# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved\n",
    )

    assert check_new_files.check_paths([path], root=tmp_path) == [
        "module.py: new Python files must not use the legacy Facebook or Meta "
        "copyright notice"
    ]


def test_rejects_meta_header_even_with_new_header(tmp_path: Path) -> None:
    path = write(
        tmp_path,
        "module.py",
        "# Copyright (c) Meta Platforms, Inc.\n" + NEW_HEADER,
    )

    assert check_new_files.check_paths([path], root=tmp_path) == [
        "module.py: new Python files must not use the legacy Facebook or Meta "
        "copyright notice"
    ]


def test_rejects_meta_header_without_platforms(tmp_path: Path) -> None:
    path = write(tmp_path, "module.py", "# Copyright (c) Meta, Inc.\n" + NEW_HEADER)

    assert check_new_files.check_paths([path], root=tmp_path) == [
        "module.py: new Python files must not use the legacy Facebook or Meta "
        "copyright notice"
    ]


def test_rejects_missing_header(tmp_path: Path) -> None:
    path = write(tmp_path, "module.py", "value = 10\n")

    assert check_new_files.check_paths([path], root=tmp_path) == [
        "module.py: missing the required Contributors to Hydra copyright and "
        "MIT license header"
    ]


def test_rejects_spdx_text_outside_leading_comments(tmp_path: Path) -> None:
    path = write(
        tmp_path,
        "module.py",
        'COPYRIGHT = "SPDX-FileCopyrightText: Contributors to Hydra"\n'
        'LICENSE = "SPDX-License-Identifier: MIT"\n',
    )

    assert check_new_files.check_paths([path], root=tmp_path) == [
        "module.py: missing the required Contributors to Hydra copyright and "
        "MIT license header"
    ]


def test_ignores_non_python_and_excluded_files(tmp_path: Path) -> None:
    paths = [
        write(tmp_path, "notes.md", "No source header\n"),
        write(tmp_path, "website/script.py", "value = 10\n"),
        write(tmp_path, "hydra/grammar/gen/parser.py", "value = 10\n"),
    ]

    assert check_new_files.check_paths(paths, root=tmp_path) == []


def test_added_paths_uses_nul_delimited_git_diff(tmp_path: Path) -> None:
    def git(*args: str) -> str:
        result = subprocess.run(
            ["git", *args],
            cwd=tmp_path,
            check=True,
            stdout=subprocess.PIPE,
            text=True,
        )
        return result.stdout.strip()

    git("init", "--quiet")
    git("config", "user.name", "Hydra test")
    git("config", "user.email", "hydra@example.com")
    write(tmp_path, "README.md", "base\n")
    git("add", "README.md")
    git("commit", "--quiet", "-m", "base")
    base = git("rev-parse", "HEAD")

    write(tmp_path, "new module.py", NEW_HEADER)
    git("add", "new module.py")
    git("commit", "--quiet", "-m", "add module")
    head = git("rev-parse", "HEAD")

    assert check_new_files.added_paths(base=base, head=head, root=tmp_path) == [
        Path("new module.py")
    ]


def test_main_skips_an_all_zero_base() -> None:
    assert check_new_files.main(["--base", "0" * 40]) == 0


def test_shared_docusaurus_exemption_is_scoped(tmp_path: Path) -> None:
    shared = write(tmp_path, ".github/docusaurus/project.py", "value = 10\n")
    ordinary = write(tmp_path, ".github/scripts/ordinary.py", "value = 10\n")
    assert check_new_files.check_paths([shared], root=tmp_path) == []
    assert len(check_new_files.check_paths([ordinary], root=tmp_path)) == 1

#!/usr/bin/env python3

# SPDX-FileCopyrightText: Contributors to Hydra
# SPDX-License-Identifier: MIT

"""Check copyright headers on newly added Python files."""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Sequence

REPO_ROOT = Path(__file__).resolve().parents[2]

NEW_COPYRIGHT = b"# SPDX-FileCopyrightText: Contributors to Hydra"
NEW_LICENSE = b"# SPDX-License-Identifier: MIT"
LEGACY_ORGANIZATION = re.compile(
    rb"\b(?:facebook|meta(?: platforms)?)\b", re.IGNORECASE
)

CHECKED_SUFFIXES = {".py", ".pyi"}
EXCLUDED_PREFIXES = (
    ".github/docusaurus/",
    ".stubs/",
    "hydra/grammar/gen/",
    "temp/",
    "tools/configen/example/gen/",
    "tools/configen/tests/test_modules/expected/",
    "website/",
)


def normalize_path(path: Path) -> str:
    normalized = path.as_posix()
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized


def is_checked_path(path: Path) -> bool:
    normalized = normalize_path(path)
    return path.suffix in CHECKED_SUFFIXES and not normalized.startswith(
        EXCLUDED_PREFIXES
    )


def leading_comment_lines(contents: bytes) -> list[bytes]:
    comments: list[bytes] = []
    for line_number, line in enumerate(contents.splitlines()):
        stripped = line.strip()
        if line_number == 0 and stripped.startswith(b"#!"):
            continue
        if not stripped:
            continue
        if not stripped.startswith(b"#"):
            break
        comments.append(stripped)
    return comments


def has_legacy_copyright(comments: Sequence[bytes]) -> bool:
    return any(
        b"copyright" in comment.lower()
        and LEGACY_ORGANIZATION.search(comment) is not None
        for comment in comments
    )


def check_paths(paths: Sequence[Path], *, root: Path) -> list[str]:
    errors: list[str] = []
    for relative_path in paths:
        if not is_checked_path(relative_path):
            continue

        normalized = normalize_path(relative_path)
        comments = leading_comment_lines((root / relative_path).read_bytes()[:4096])
        if has_legacy_copyright(comments):
            errors.append(
                f"{normalized}: new Python files must not use the legacy "
                "Facebook or Meta copyright notice"
            )
        elif NEW_COPYRIGHT not in comments or NEW_LICENSE not in comments:
            errors.append(
                f"{normalized}: missing the required Contributors to Hydra "
                "copyright and MIT license header"
            )
    return errors


def added_paths(*, base: str, head: str, root: Path) -> list[Path]:
    result = subprocess.run(
        [
            "git",
            "diff",
            "--diff-filter=A",
            "--name-only",
            "-z",
            base,
            head,
            "--",
        ],
        cwd=root,
        check=True,
        stdout=subprocess.PIPE,
    )
    return [Path(os.fsdecode(item)) for item in result.stdout.split(b"\0") if item]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True, help="Base commit SHA")
    parser.add_argument("--head", default="HEAD", help="Head commit SHA")
    args = parser.parse_args(argv)

    if not args.base or set(args.base) == {"0"}:
        print("Skipping new-file copyright check: no usable base commit")
        return 0

    errors = check_paths(
        added_paths(base=args.base, head=args.head, root=REPO_ROOT),
        root=REPO_ROOT,
    )
    if errors:
        print("\n".join(errors), file=sys.stderr)
        print(
            "New Python files must contain:\n"
            "# SPDX-FileCopyrightText: Contributors to Hydra\n"
            "# SPDX-License-Identifier: MIT",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

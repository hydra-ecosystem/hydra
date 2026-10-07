"""Read deployment identity without configuring the website's build internals."""

import argparse
import json
import re
from pathlib import Path

DIRECTORY_PATTERN = re.compile(r"[A-Za-z0-9_./ -]+")


def project(root: Path) -> tuple[Path, dict]:
    root = root.resolve()
    config = json.loads((root / ".github/docusaurus.json").read_text())
    if (
        not isinstance(config, dict)
        or not set(config) <= {"directory", "schedule"}
        or "directory" not in config
    ):
        raise ValueError("docusaurus.json accepts only project directory and schedule")
    name = config["directory"]
    schedules = config.get("schedule", ["0 2 30 1 *"])
    if (
        not isinstance(schedules, list)
        or not schedules
        or any(not isinstance(value, str) or not value.strip() for value in schedules)
    ):
        raise ValueError("schedule must be a nonempty list of cron expressions")
    if (
        not isinstance(name, str)
        or not name
        or DIRECTORY_PATTERN.fullmatch(name) is None
        or "\n" in name
        or "\r" in name
    ):
        raise ValueError("project directory must be a nonempty relative path")
    relative = Path(name)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("project directory must stay inside the repository")
    directory = (root / relative).resolve()
    if not directory.is_relative_to(root):
        raise ValueError("project directory resolves outside the repository")
    manifest = json.loads((directory / "package.json").read_text())
    dependencies = {
        **manifest.get("dependencies", {}),
        **manifest.get("devDependencies", {}),
    }
    if "@docusaurus/core" not in dependencies:
        raise ValueError("configured project does not declare @docusaurus/core")
    if not manifest.get("scripts", {}).get("build"):
        raise ValueError("configured project must own its normal build script")
    baseline = json.loads(Path(__file__).with_name("toolchain.json").read_text())
    if manifest.get("packageManager") != f"pnpm@{baseline['pnpm']}":
        raise ValueError("project packageManager differs from the shared pnpm pin")
    return directory, baseline


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--github-env", type=Path)
    args = parser.parse_args()
    directory, baseline = project(args.root)
    values = (
        f"NPM_PROJECT={directory.relative_to(args.root.resolve()).as_posix()}\n"
        f"DOCUSAURUS_NODE_VERSION={baseline['node']}\n"
    )
    if args.github_env:
        with args.github_env.open("a") as output:
            output.write(values)
    else:
        print(values, end="")


if __name__ == "__main__":
    main()

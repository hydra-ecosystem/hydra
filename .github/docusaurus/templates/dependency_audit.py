"""Prepare a best-effort npm or pnpm upgrade report for one documentation project."""

import argparse
import json
import re
import subprocess
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

import yaml

SEVERITY_ORDER = {"critical": 0, "high": 1, "moderate": 2, "low": 3, "info": 4}
DIRECTORY_PATTERN = re.compile(r"[A-Za-z0-9_./ -]+")


def manager(directory: Path) -> str:
    try:
        declared = json.loads((directory / "package.json").read_bytes()).get(
            "packageManager", ""
        )
    except (OSError, ValueError, AttributeError):
        declared = ""
    return (
        "pnpm"
        if declared.startswith("pnpm@") or (directory / "pnpm-workspace.yaml").exists()
        else "npm"
    )


def valid_snapshot(
    directory: Path,
) -> tuple[bytes, dict[str, bytes], dict, dict] | None:
    """Retain manifest, lockfile and pnpm policy together for safe restoration."""
    try:
        manifest_bytes = (directory / "package.json").read_bytes()
        manifest = json.loads(manifest_bytes)
        if manager(directory) == "pnpm":
            if (directory / "package-lock.json").exists():
                return None
            files = {
                name: (directory / name).read_bytes()
                for name in ("pnpm-lock.yaml", "pnpm-workspace.yaml")
            }
            policy = yaml.safe_load(files["pnpm-workspace.yaml"])
            lock = yaml.safe_load(files["pnpm-lock.yaml"])
            if (
                not isinstance(policy, dict)
                or policy.get("packages") != ["."]
                or not isinstance(policy.get("minimumReleaseAgeExclude", []), list)
                or any(
                    not isinstance(item, str)
                    for item in policy.get("minimumReleaseAgeExclude", [])
                )
                or not isinstance(lock, dict)
                or "lockfileVersion" not in lock
                or set(lock.get("importers", {})) != {"."}
                or not isinstance(lock.get("packages", {}), dict)
            ):
                return None
            packages = {}
            for key in lock.get("packages", {}):
                name, version = key.split("(", 1)[0].rsplit("@", 1)
                packages[f"{name}@{version}"] = {"name": name, "version": version}
            lock = {"packages": packages}
        else:
            if (directory / "pnpm-lock.yaml").exists():
                return None
            files = {
                "package-lock.json": (directory / "package-lock.json").read_bytes()
            }
            lock = json.loads(files["package-lock.json"])
    except (OSError, UnicodeDecodeError, ValueError, TypeError, yaml.YAMLError):
        return None
    if not isinstance(manifest, dict) or not isinstance(lock, dict):
        return None
    return manifest_bytes, files, manifest, lock


def restore_snapshot(
    directory: Path, snapshot: tuple[bytes, dict[str, bytes], dict, dict]
) -> None:
    (directory / "package.json").write_bytes(snapshot[0])
    for name, content in snapshot[1].items():
        (directory / name).write_bytes(content)


def exclusion_versions(exclusions: list[str]) -> set[str]:
    """Expand pnpm's exact-version unions without allowing broader new rules."""
    expanded = set()
    for exclusion in exclusions:
        name, separator, versions = exclusion.rpartition("@")
        if not separator or not name:
            expanded.add(exclusion)
        else:
            expanded.update(
                f"{name}@{version.strip()}" for version in versions.split("||")
            )
    return expanded


def stable_version(value: object) -> tuple[int, int, int] | None:
    if not isinstance(value, str):
        return None
    value = value.split("(", 1)[0]
    if not re.fullmatch(r"\d+\.\d+\.\d+", value):
        return None
    major, minor, patch = value.split(".")
    return int(major), int(minor), int(patch)


def stable_manifest_minimum(value: object) -> tuple[int, int, int] | None:
    if not isinstance(value, str) or not re.fullmatch(r"[~^]?\d+\.\d+\.\d+", value):
        return None
    return stable_version(value.lstrip("~^"))


def direct_pnpm_versions(
    files: dict[str, bytes],
) -> dict[tuple[str, str], tuple[int, int, int]]:
    try:
        lock = yaml.safe_load(files["pnpm-lock.yaml"])
        importer = lock["importers"]["."]
    except (KeyError, TypeError, ValueError, yaml.YAMLError):
        return {}
    versions = {}
    if not isinstance(importer, dict):
        return versions
    for section in ("dependencies", "devDependencies", "optionalDependencies"):
        entries = importer.get(section, {})
        if not isinstance(entries, dict):
            continue
        for name, entry in entries.items():
            if isinstance(name, str) and isinstance(entry, dict):
                version = stable_version(entry.get("version"))
                if version is not None:
                    versions[(section, name)] = version
    return versions


def direct_dependency_regressed(
    snapshot: tuple[bytes, dict[str, bytes], dict, dict],
    current: tuple[bytes, dict[str, bytes], dict, dict],
) -> bool:
    before_manifest = snapshot[2]
    after_manifest = current[2]
    before_locked = direct_pnpm_versions(snapshot[1])
    after_locked = direct_pnpm_versions(current[1])
    for section in ("dependencies", "devDependencies", "optionalDependencies"):
        before_entries = before_manifest.get(section, {})
        after_entries = after_manifest.get(section, {})
        if not isinstance(before_entries, dict):
            continue
        if not isinstance(after_entries, dict):
            after_entries = {}
        names = set(before_entries) | {
            name for section_name, name in before_locked if section_name == section
        }
        for name in names:
            before_specifier = before_entries.get(name)
            before_floor = stable_manifest_minimum(before_specifier)
            if before_floor is not None:
                after_floor = stable_manifest_minimum(after_entries.get(name))
                if after_floor is None or after_floor < before_floor:
                    return True
            before_version = before_locked.get((section, name))
            if before_version is not None:
                after_version = after_locked.get((section, name))
                if after_version is None or after_version < before_version:
                    return True
    return False


def restore_invalid_state(
    directory: Path,
    snapshot: tuple[bytes, dict[str, bytes], dict, dict],
    notes: list[str],
    operation: str,
    *,
    security_fix: bool = False,
    frozen: bool = False,
) -> bool:
    """Restore a valid snapshot when a command damaged package files or policy."""
    current = valid_snapshot(directory)
    if (
        current is not None
        and current[1].keys() == snapshot[1].keys()
        and (not frozen or (current[0] == snapshot[0] and current[1] == snapshot[1]))
    ):
        if "pnpm-workspace.yaml" not in current[1]:
            return False
        policy = yaml.safe_load(current[1]["pnpm-workspace.yaml"])
        reference = yaml.safe_load(snapshot[1]["pnpm-workspace.yaml"])
        if direct_dependency_regressed(snapshot, current):
            restore_snapshot(directory, snapshot)
            notes.append(
                f"{operation} changed protected pnpm policy or lowered a known direct "
                "pnpm dependency manifest floor or locked version; restored the last "
                "valid snapshot and did not claim its changes."
            )
            return True
        existing = reference.pop("minimumReleaseAgeExclude", [])
        exclusions = policy.pop("minimumReleaseAgeExclude", [])
        preserved_exclusions = exclusions == existing
        if security_fix:
            before = {
                (package["name"], package["version"])
                for package in snapshot[3]["packages"].values()
            }
            after = {
                (package["name"], package["version"])
                for package in current[3]["packages"].values()
            }
            allowed = {f"{name}@{version}" for name, version in after - before}
            existing_versions = exclusion_versions(existing)
            current_versions = exclusion_versions(exclusions)
            preserved_exclusions = existing_versions <= current_versions and all(
                re.fullmatch(r".+@\d+\.\d+\.\d+(?:-[\w.-]+)?(?:\+[\w.-]+)?", item)
                for item in current_versions - existing_versions
            )
            unused = current_versions - existing_versions - allowed
            if policy == reference and preserved_exclusions:
                retained = existing + sorted(
                    (current_versions - existing_versions) & allowed
                )
                workspace = directory / "pnpm-workspace.yaml"
                if retained == existing:
                    workspace.write_bytes(snapshot[1]["pnpm-workspace.yaml"])
                else:
                    # Reuse the original policy text: serializing the whole mapping
                    # would discard comments and reformat unrelated settings.
                    text = snapshot[1]["pnpm-workspace.yaml"].decode()
                    document = yaml.compose(text)
                    entry = next(
                        (
                            (key, value)
                            for key, value in document.value
                            if key.value == "minimumReleaseAgeExclude"
                        ),
                        None,
                    )
                    additions = sorted((current_versions - existing_versions) & allowed)
                    if entry is None:
                        index = end = document.end_mark.index
                        addition = "minimumReleaseAgeExclude:\n" + yaml.safe_dump(
                            additions
                        )
                    else:
                        key, sequence = entry
                        tokens = list(yaml.scan(text))
                        start = next(
                            token
                            for token in tokens
                            if token.start_mark.index >= key.end_mark.index
                            and isinstance(
                                token,
                                (
                                    yaml.AliasToken,
                                    yaml.FlowSequenceStartToken,
                                    yaml.BlockEntryToken,
                                ),
                            )
                        )
                        if isinstance(start, yaml.AliasToken):
                            index, end = start.start_mark.index, start.end_mark.index
                            addition = json.dumps(retained)
                        else:
                            flow = isinstance(start, yaml.FlowSequenceStartToken)
                            if flow:
                                closing_index = sequence.end_mark.index - 1
                                closing = next(
                                    index
                                    for index, token in enumerate(tokens)
                                    if isinstance(token, yaml.FlowSequenceEndToken)
                                    and token.start_mark.index == closing_index
                                )
                                trailing_comma = closing > 0 and isinstance(
                                    tokens[closing - 1], yaml.FlowEntryToken
                                )
                                items = json.dumps(additions)[1:-1]
                                if trailing_comma:
                                    index = end = closing_index
                                    addition = " " + items
                                elif sequence.value:
                                    index = end = sequence.value[-1].end_mark.index
                                    addition = ", " + items
                                else:
                                    index = end = closing_index
                                    addition = items
                            else:
                                index = end = sequence.end_mark.index
                                addition = "".join(
                                    " " * start.start_mark.column + line
                                    for line in yaml.safe_dump(additions).splitlines(
                                        keepends=True
                                    )
                                )
                    if addition.endswith("\n") and index and text[index - 1] != "\n":
                        addition = "\n" + addition
                    workspace.write_text(text[:index] + addition + text[end:])
                repaired = valid_snapshot(directory)
                repaired_policy = (
                    yaml.safe_load(repaired[1]["pnpm-workspace.yaml"])
                    if repaired is not None
                    else None
                )
                repaired_exclusions = (
                    repaired_policy.pop("minimumReleaseAgeExclude", [])
                    if isinstance(repaired_policy, dict)
                    else None
                )
                if (
                    repaired is None
                    or repaired_exclusions != retained
                    or repaired_policy != reference
                ):
                    restore_snapshot(directory, snapshot)
                    notes.append(
                        f"{operation} reconstructed an invalid pnpm policy; restored "
                        "the last valid snapshot and did not claim its changes."
                    )
                    return True
                if unused:
                    notes.append(
                        f"{operation}: removed unused release-age exceptions "
                        f"({', '.join(sorted(unused))}); retained resolved dependency changes."
                    )
                return False
        if policy == reference and preserved_exclusions:
            return False
    restore_snapshot(directory, snapshot)
    notes.append(
        f"{operation} changed protected pnpm policy, changed frozen package files, "
        "or left invalid package files; restored "
        "the last valid snapshot and did not claim its changes."
    )
    return True


def run(
    directory: Path, *args: str, deadline: float | None = None
) -> subprocess.CompletedProcess[str]:
    command = (
        ["corepack", "pnpm"] if manager(directory) == "pnpm" else ["npm"]
    ) + list(args)
    timeout = min(900, deadline - time.monotonic()) if deadline is not None else 900
    if timeout <= 0:
        return subprocess.CompletedProcess(
            command, 124, "", "Dependency audit time budget exhausted."
        )
    # GNU timeout owns the process group and kills npm and lifecycle/build children.
    result = subprocess.run(
        ["timeout", "--signal=KILL", f"{timeout}s", *command],
        cwd=directory,
        capture_output=True,
        text=True,
    )
    if result.returncode in (-9, 137):
        result = subprocess.CompletedProcess(
            command, 124, result.stdout, result.stderr + "\nCommand timed out."
        )
    print(f"{' '.join(command)}: exit {result.returncode}")
    if result.returncode:
        print(result.stdout)
        print(result.stderr)
    return result


def valid_npm_fix(candidate: object) -> bool:
    if isinstance(candidate, bool):
        return True
    return (
        isinstance(candidate, dict)
        and isinstance(candidate.get("name"), str)
        and bool(candidate["name"])
        and ("version" not in candidate or isinstance(candidate["version"], str))
        and (
            "isSemVerMajor" not in candidate or type(candidate["isSemVerMajor"]) is bool
        )
    )


def valid_npm_vulnerability(vulnerability: object) -> bool:
    if not isinstance(vulnerability, dict):
        return False
    if (
        not isinstance(vulnerability.get("severity"), str)
        or vulnerability["severity"] not in SEVERITY_ORDER
        or not isinstance(vulnerability.get("range"), str)
        or not vulnerability["range"]
        or not isinstance(vulnerability.get("nodes"), list)
        or any(not isinstance(node, str) or not node for node in vulnerability["nodes"])
        or not isinstance(vulnerability.get("via"), list)
        or "fixAvailable" not in vulnerability
        or not valid_npm_fix(vulnerability["fixAvailable"])
    ):
        return False
    for via in vulnerability["via"]:
        if isinstance(via, str):
            if not via:
                return False
        elif (
            not isinstance(via, dict)
            or not isinstance(via.get("title"), str)
            or not via["title"]
            or not isinstance(via.get("url"), str)
            or not via["url"]
            or not isinstance(via.get("severity"), str)
            or via.get("severity") not in SEVERITY_ORDER
            or not isinstance(via.get("range"), str)
            or not via["range"]
        ):
            return False
    return True


def counts_match_details(
    counts: object,
    vulnerabilities: dict,
    package_manager: str,
    advisories: dict | None = None,
) -> bool:
    if (
        not isinstance(counts, dict)
        or not counts
        or any(level not in SEVERITY_ORDER and level != "total" for level in counts)
        or any(type(count) is not int or count < 0 for count in counts.values())
    ):
        return False
    if package_manager == "npm":
        if "total" not in counts or counts["total"] != len(vulnerabilities):
            return False
        observed = {
            level: sum(
                vulnerability.get("severity") == level
                for vulnerability in vulnerabilities.values()
            )
            for level in SEVERITY_ORDER
        }
    else:
        if advisories is None:
            return False
        if "total" in counts and counts["total"] != len(advisories):
            return False
        observed = {
            level: sum(
                advisory.get("severity") == level
                for advisory in advisories.values()
                if isinstance(advisory, dict)
            )
            for level in SEVERITY_ORDER
        }
    return all(
        counts.get(level, 0) == observed[level] for level in SEVERITY_ORDER
    ) and ("total" not in counts or counts["total"] == sum(observed.values()))


def audit(directory: Path, *, deadline: float | None = None) -> dict | str:
    package_manager = manager(directory)
    if package_manager == "pnpm":
        policy = yaml.safe_load((directory / "pnpm-workspace.yaml").read_bytes())
        if policy.get("audit", {}).get("ignore") or policy.get("auditConfig", {}).get(
            "ignoreGhsas"
        ):
            return (
                "Audit unavailable: pnpm advisory-ignore rules would hide dependency "
                "findings; manual review required."
            )
        flags = ["--audit-level", "info"]
    else:
        flags = ["--audit", "--package-lock-only"]
    result = run(
        directory,
        "audit",
        "--json",
        *flags,
        deadline=deadline,
    )
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        return f"Audit unavailable (exit {result.returncode})."
    if not isinstance(data, dict):
        return f"Audit unavailable (exit {result.returncode})."
    if package_manager == "pnpm" and not isinstance(data.get("advisories"), dict):
        return "Audit unavailable: malformed pnpm advisory response."
    advisories = data.get("advisories") if package_manager == "pnpm" else None
    if package_manager == "pnpm":
        assert isinstance(advisories, dict)
        vulnerabilities: dict = {}
        for advisory in advisories.values():
            if (
                not isinstance(advisory, dict)
                or any(
                    not isinstance(advisory.get(key), str) or not advisory[key]
                    for key in (
                        "module_name",
                        "severity",
                        "title",
                        "url",
                        "vulnerable_versions",
                    )
                )
                or advisory["severity"] not in SEVERITY_ORDER
                or not isinstance(advisory.get("findings"), list)
                or any(
                    not isinstance(finding, dict)
                    or not isinstance(finding.get("version"), str)
                    or not finding["version"]
                    for finding in advisory["findings"]
                )
                or (
                    "patched_versions" not in advisory
                    or (
                        advisory["patched_versions"] is not None
                        and not isinstance(advisory["patched_versions"], str)
                    )
                )
            ):
                return "Audit unavailable: malformed pnpm advisory response."
            name = advisory["module_name"]
            ranges = {
                advisory["vulnerable_versions"],
            }
            vulnerability = vulnerabilities.setdefault(
                name,
                {
                    "severity": advisory["severity"],
                    "range": advisory["vulnerable_versions"],
                    "nodes": [],
                    "via": [],
                    "fixAvailable": False,
                },
            )
            if vulnerability["severity"] not in SEVERITY_ORDER or (
                SEVERITY_ORDER[advisory["severity"]]
                < SEVERITY_ORDER[vulnerability["severity"]]
            ):
                vulnerability["severity"] = advisory["severity"]
            ranges.update(vulnerability["range"].split(" || "))
            vulnerability["range"] = " || ".join(sorted(ranges))
            nodes = [
                f"{name}@{finding['version']}"
                for finding in advisory.get("findings", [])
            ]
            vulnerability["via"].append(
                {
                    "title": advisory["title"],
                    "url": advisory["url"],
                    "severity": advisory["severity"],
                    "range": advisory["vulnerable_versions"],
                    "nodes": nodes,
                    "patchedRange": advisory["patched_versions"],
                }
            )
            vulnerability["nodes"].extend(nodes)
            vulnerability["fixAvailable"] = vulnerability["fixAvailable"] or bool(
                advisory.get("patched_versions") not in (None, "<0.0.0")
            )
        data["vulnerabilities"] = vulnerabilities
        data["package_manager"] = package_manager
    metadata = data.get("metadata")
    counts = metadata.get("vulnerabilities") if isinstance(metadata, dict) else None
    if (
        result.returncode not in (0, 1)
        or data.get("error")
        or not isinstance(data.get("vulnerabilities"), dict)
    ):
        return f"Audit unavailable (exit {result.returncode})."
    if package_manager == "npm" and any(
        not isinstance(name, str)
        or not name
        or not valid_npm_vulnerability(vulnerability)
        for name, vulnerability in data["vulnerabilities"].items()
    ):
        return "Audit unavailable: malformed npm vulnerability response."
    if not counts_match_details(
        counts,
        data["vulnerabilities"],
        package_manager,
        advisories,
    ):
        return "Audit unavailable: vulnerability counts do not match advisory details."
    return data


def fix_security(
    directory: Path, deadline: float, notes: list[str] | None = None
) -> subprocess.CompletedProcess[str]:
    if manager(directory) == "pnpm":
        snapshot = valid_snapshot(directory)
        result = run(
            directory,
            "audit",
            "--fix=update",
            "--audit-level",
            "info",
            "--ignore-scripts",
            deadline=deadline,
        )
        current = valid_snapshot(directory)
        if result.returncode != 1 or snapshot is None or current is None:
            return result
        reference = yaml.safe_load(snapshot[1]["pnpm-workspace.yaml"])
        policy = yaml.safe_load(current[1]["pnpm-workspace.yaml"])
        existing = exclusion_versions(reference.pop("minimumReleaseAgeExclude", []))
        exclusions = exclusion_versions(policy.pop("minimumReleaseAgeExclude", []))
        # Refuse weakened policy before executing another dependency command.
        if (
            policy != reference
            or not existing <= exclusions
            or any(
                not re.fullmatch(r".+@\d+\.\d+\.\d+(?:-[\w.-]+)?(?:\+[\w.-]+)?", item)
                for item in exclusions - existing
            )
        ):
            return result
        # pnpm can reintroduce vulnerable pins during automatic peer resolution.
        # A fresh compatible resolution avoids those pins, including the installed
        # virtual store's lockfile, without adding overrides or running scripts.
        (directory / "pnpm-lock.yaml").unlink()
        with TemporaryDirectory(prefix="dependency-audit-resolution-") as modules:
            resolved = run(
                directory,
                "install",
                "--lockfile-only",
                "--no-frozen-lockfile",
                "--ignore-scripts",
                "--config.optimistic-repeat-install=false",
                "--modules-dir",
                modules,
                "--virtual-store-dir",
                str(Path(modules) / ".pnpm"),
                deadline=deadline,
            )
        failed = bool(resolved.returncode) or valid_snapshot(directory) is None
        if failed:
            restore_snapshot(directory, current)
        if notes is not None:
            notes.append(
                "Regenerated the pnpm lockfile within existing manifest constraints "
                "using isolated module metadata after audit --fix=update left findings."
                if not failed
                else f"Compatible lockfile regeneration failed (exit {resolved.returncode}); "
                "restored the preceding security-fix proposal."
            )
        return result
    return run(
        directory,
        "audit",
        "fix",
        "--package-lock-only",
        "--ignore-scripts",
        "--audit",
        deadline=deadline,
    )


def versions(lock: dict, vulnerability: dict) -> str:
    packages = lock.get("packages", {})
    found = {
        packages[node]["version"]
        for node in vulnerability.get("nodes", [])
        if node in packages and "version" in packages[node]
    }
    return ", ".join(sorted(found)) or "not recorded in lockfile"


def package_paths(lock: dict, name: str, package_manager: str) -> dict[str, str]:
    """Retain package locations and pnpm references lost by version deduplication."""
    if package_manager == "npm":
        return {
            node: package["version"]
            for node, package in lock.get("packages", {}).items()
            if "version" in package
            and (
                node == f"node_modules/{name}"
                or node.endswith(f"/node_modules/{name}")
                or package.get("name") == name
            )
        }
    paths = {}
    for group in ("packages", "snapshots", "importers"):
        entries = lock.get(group, {})
        if not isinstance(entries, dict):
            continue
        for node, entry in entries.items():
            if not isinstance(node, str):
                continue
            plain = node.split("(", 1)[0]
            if group != "importers" and plain.rsplit("@", 1)[0] == name:
                paths[f"{group}/{node}"] = plain.rsplit("@", 1)[-1]
            if group == "packages" or not isinstance(entry, dict):
                continue
            for section in ("dependencies", "devDependencies", "optionalDependencies"):
                references = entry.get(section, {})
                if not isinstance(references, dict):
                    continue
                for dependency, reference in references.items():
                    version = (
                        reference.get("version")
                        if isinstance(reference, dict)
                        else reference
                    )
                    if isinstance(version, str) and (
                        dependency == name or version.startswith(f"{name}@")
                    ):
                        paths[f"{group}/{node}/{section}/{dependency}"] = (
                            version.removeprefix(f"{name}@")
                        )
    return paths


def describe_pnpm_fixes(
    directory: Path,
    data: dict | str,
    files: dict[str, bytes],
    notes: list[str],
    deadline: float,
    cache: dict,
) -> None:
    """Verify published patches and explain constraints using registry metadata."""
    if not isinstance(data, dict) or data.get("package_manager") != "pnpm":
        return
    lock = yaml.safe_load(files["pnpm-lock.yaml"])

    def query(package: str, *fields: str) -> object:
        key = (package, fields)
        if key not in cache:
            snapshot = valid_snapshot(directory)
            result = run(
                directory, "view", package, *fields, "--json", deadline=deadline
            )
            if snapshot is None or restore_invalid_state(
                directory,
                snapshot,
                notes,
                f"Patch metadata lookup for {package}",
                frozen=True,
            ):
                cache[key] = None
            else:
                try:
                    value = json.loads(result.stdout)
                except ValueError:
                    value = None
                error = value.get("error", {}) if isinstance(value, dict) else {}
                if not isinstance(error, dict):
                    error = {}
                cache[key] = (
                    []
                    if error.get("code") == "ERR_PNPM_PACKAGE_NOT_FOUND"
                    else value
                    if result.returncode == 0
                    else None
                )
        return cache[key]

    def published(specifier: str) -> set[str] | None:
        value = query(specifier, "version")
        values = [value] if isinstance(value, str) else value
        if not isinstance(values, list) or any(not isinstance(v, str) for v in values):
            return None
        return {v for v in values if re.fullmatch(r"\d+\.\d+\.\d+", v)}

    for name, vulnerability in data["vulnerabilities"].items():
        vulnerability["fixAvailable"] = False
        for detail in vulnerability["via"]:
            patched = detail.get("patchedRange")
            if patched in (None, "<0.0.0", ""):
                detail["fixStatus"] = "No patched version declared by the registry."
                continue
            patches = published(f"{name}@{patched}")
            if patches is None:
                detail["fixStatus"] = (
                    f"Could not verify publication of patched range `{patched}`."
                )
                continue
            if not patches:
                detail["fixStatus"] = (
                    f"No published stable patch matches registry range `{patched}`."
                )
                continue
            vulnerability["fixAvailable"] = True
            blocked = []
            unknown = False
            for parent, snapshot in lock.get("snapshots", {}).items():
                edges = {
                    **snapshot.get("dependencies", {}),
                    **snapshot.get("optionalDependencies", {}),
                }
                reference = edges.get(name)
                if (
                    not isinstance(reference, str)
                    or f"{name}@{reference.split('(', 1)[0]}" not in detail["nodes"]
                ):
                    continue
                parent = parent.split("(", 1)[0]
                metadata = query(parent, "dependencies", "optionalDependencies")
                if not isinstance(metadata, dict) or any(
                    not isinstance(metadata.get(field, {}), dict)
                    for field in ("dependencies", "optionalDependencies")
                ):
                    unknown = True
                    continue
                constraint = {
                    **metadata.get("dependencies", {}),
                    **metadata.get("optionalDependencies", {}),
                }.get(name)
                if not isinstance(constraint, str):
                    unknown = True
                    continue
                intersections = [
                    published(f"{name}@{parent_range.strip()} {patch_range.strip()}")
                    for parent_range in constraint.split("||")
                    for patch_range in patched.split("||")
                ]
                if any(versions is None for versions in intersections):
                    unknown = True
                elif not any(intersections):
                    blocked.append(f"`{parent}` requires `{name} {constraint}`")
                for matches in intersections:
                    patches.update(matches or ())
            version = min(patches, key=lambda v: tuple(map(int, v.split("."))))
            detail["fixStatus"] = f"Published patch: `{name}@{version}`. " + (
                "Blocked by existing parent constraints: "
                + "; ".join(sorted(set(blocked)))
                + "."
                if blocked
                else "Parent compatibility could not be fully verified; manual review required."
                if unknown
                else "No checked parent constraint excludes published patches; review "
                "manifest constraints and resolution logs."
            )


def format_audit(data: dict | str, lock: dict) -> str:
    if isinstance(data, str):
        return data
    source = data.get("package_manager", "npm")
    summary = ", ".join(
        f"{level}: {count}"
        for level, count in data["metadata"]["vulnerabilities"].items()
    )
    findings = []
    for name, vulnerability in sorted(
        data.get("vulnerabilities", {}).items(),
        key=lambda item: (SEVERITY_ORDER.get(item[1]["severity"], 5), item[0]),
    ):
        candidate = vulnerability.get("fixAvailable")
        fix = "available" if candidate else f"not offered by {source}"
        if source == "pnpm":
            fix = (
                "published stable patch verified"
                if candidate
                else "publication not verified; see advisory details"
            )
        if isinstance(candidate, dict):
            fix = f"`{candidate['name']}@{candidate.get('version', 'unspecified')}`"
            if candidate.get("isSemVerMajor"):
                fix += "; requires breaking changes; manual review"
        findings.append(
            f"- **{name}**: {vulnerability['severity']}; locked versions "
            f"`{versions(lock, vulnerability)}`; affected range "
            f"`{vulnerability['range']}`; {source} fix candidate {fix}."
        )
        for via in vulnerability.get("via", []):
            if isinstance(via, dict):
                findings.append(
                    f"  - [{via['title']}]({via['url']}); "
                    f"{via['severity']}; affected range `{via['range']}`."
                    + (f" {via['fixStatus']}" if via.get("fixStatus") else "")
                )
            else:
                findings.append(f"  - Depends on affected `{via}` (see its entry).")
    return (
        summary
        + "\n\n"
        + (
            "\n".join(findings)
            if findings
            else f"No known vulnerabilities reported by {source}."
        )
    )


def format_remaining_audit(data: dict | str, lock: dict) -> str:
    if isinstance(data, str):
        return data
    source = data.get("package_manager", "npm")
    counts = ", ".join(
        f"{level}: {count}"
        for level, count in data["metadata"]["vulnerabilities"].items()
    )
    vulnerabilities = data.get("vulnerabilities", {})
    if not vulnerabilities:
        return f"No known vulnerabilities reported by {source}."
    advisories: dict = {}
    for name, vulnerability in vulnerabilities.items():
        for via in vulnerability.get("via", []):
            if isinstance(via, dict):
                advisory = advisories.setdefault(
                    via["url"], {"detail": via, "packages": set()}
                )
                affected = via if source == "pnpm" else vulnerability
                advisory["packages"].add(f"{name}@{versions(lock, affected)}")
    lines = []
    for advisory in sorted(
        advisories.values(),
        key=lambda item: (
            SEVERITY_ORDER.get(item["detail"]["severity"], 5),
            item["detail"]["url"],
        ),
    ):
        detail = advisory["detail"]
        packages = ", ".join(sorted(advisory["packages"]))
        lines.append(
            f"- [{detail['title']}]({detail['url']}): {detail['severity']}; "
            f"locked `{packages}`; affected range `{detail['range']}`."
            + (f" {detail['fixStatus']}" if detail.get("fixStatus") else "")
        )
    heading = (
        f"Registry advisory counts: {counts}.\n\n"
        if data.get("package_manager") == "pnpm"
        else f"Affected package entries: {counts}. These are not distinct advisory counts.\n\n"
    )
    return heading + (
        "\n".join(lines)
        or f"{source} supplied no direct advisory details; see the full findings below."
    )


def eligible_version(directory, name, latest, snapshot, notes, deadline):
    """Select a stable release within the deployment's publication-age policy."""
    result = run(directory, "view", name, "time", "--json", deadline=deadline)
    if restore_invalid_state(
        directory, snapshot, notes, f"Release-time lookup for {name}", frozen=True
    ):
        return None
    try:
        age = yaml.safe_load(snapshot[1]["pnpm-workspace.yaml"])["minimumReleaseAge"]
        releases = json.loads(result.stdout)
        if (
            result.returncode
            or type(age) is not int
            or age < 0
            or not isinstance(releases, dict)
        ):
            return None
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=age)
        limit = tuple(map(int, latest.split(".")))
        candidates = []
        for version, published in releases.items():
            if not re.fullmatch(r"\d+\.\d+\.\d+", version):
                continue
            number = tuple(map(int, version.split(".")))
            if (
                number <= limit
                and datetime.fromisoformat(published.replace("Z", "+00:00")) <= cutoff
            ):
                candidates.append((number, version))
        return max(candidates)[1] if candidates else None
    except (KeyError, ValueError, TypeError, AttributeError, OverflowError):
        return None


def prepare(directory: Path) -> str:
    # Leave time in the 60-minute job to write and upload a partial report.
    deadline = time.monotonic() + 45 * 60
    manifest_path = directory / "package.json"
    package_manager = manager(directory)
    notes = []
    initial_snapshot = valid_snapshot(directory)
    if initial_snapshot is None:
        raise ValueError(
            "Valid manifest, one deployment lockfile and package-manager policy are required"
        )
    before_lock = initial_snapshot[3]
    before = audit(directory, deadline=deadline)
    if restore_invalid_state(
        directory, initial_snapshot, notes, "Initial audit", frozen=True
    ):
        before = f"Audit unavailable: {package_manager} changed package files; restored the initial snapshot."
    initial_audit_available = isinstance(before, dict)
    if not initial_audit_available:
        notes.append(
            "Initial audit evidence was unavailable; retained security-fix changes "
            "are unconfirmed."
        )
    last_valid_snapshot = valid_snapshot(directory) or initial_snapshot
    affected = (
        set(before.get("vulnerabilities", {})) if isinstance(before, dict) else set()
    )
    changes = []

    # Give compatible security fixes the first use of the shared time budget.
    fixed = fix_security(directory, deadline, notes)
    restore_invalid_state(
        directory, last_valid_snapshot, notes, "Initial security fix", security_fix=True
    )
    if fixed.returncode:
        notes.append(
            f"Initial security fix returned exit {fixed.returncode}; remaining findings "
            "or a tool error require manual review."
        )
    # Preserve those fixes if the wider stable-version upgrade cannot resolve.
    security_snapshot = valid_snapshot(directory) or last_valid_snapshot
    last_valid_snapshot = security_snapshot
    manifest = json.loads(security_snapshot[0])

    # Preserve overrides and peer constraints for a maintainer to review.
    for section in ("dependencies", "devDependencies", "optionalDependencies"):
        for name, current in sorted(
            manifest.get(section, {}).items(),
            key=lambda item: (item[0] not in affected, item[0]),
        ):
            if not re.fullmatch(r"[~^]?\d+\.\d+\.\d+", current):
                notes.append(
                    f"Retained {name} specifier `{current}` for manual review."
                )
                continue
            result = run(
                directory,
                "view",
                f"{name}@latest",
                "version",
                "--json",
                deadline=deadline,
            )
            if restore_invalid_state(
                directory,
                security_snapshot,
                notes,
                f"Version lookup for {name}",
                frozen=True,
            ):
                continue
            try:
                latest = json.loads(result.stdout)
            except json.JSONDecodeError:
                latest = None
            if (
                result.returncode
                or not isinstance(latest, str)
                or not re.fullmatch(r"\d+\.\d+\.\d+", latest)
            ):
                notes.append(f"Could not look up {name}; retained `{current}`.")
                continue
            if package_manager == "pnpm" and latest != current.lstrip("~^"):
                latest = eligible_version(
                    directory, name, latest, security_snapshot, notes, deadline
                )
                if latest is None:
                    notes.append(
                        f"No eligible stable release verified for {name}; retained `{current}`."
                    )
                    continue
            resolved = current.lstrip("~^")
            if package_manager == "pnpm":
                importer = yaml.safe_load(security_snapshot[1]["pnpm-lock.yaml"])[
                    "importers"
                ]["."]
                resolved = (
                    importer.get(section, {}).get(name, {}).get("version", resolved)
                )
                if not isinstance(resolved, str) or not re.fullmatch(
                    r"\d+\.\d+\.\d+", resolved.split("(", 1)[0]
                ):
                    notes.append(f"Retained {name} resolved version for manual review.")
                    continue
                resolved = resolved.split("(", 1)[0]
            floor = max(
                tuple(map(int, current.lstrip("~^").split("."))),
                tuple(map(int, resolved.split("."))),
            )
            if tuple(map(int, latest.split("."))) > floor:
                manifest[section][name] = latest
                changes.append((name, f"- {name}: `{current}` → `{latest}`"))

    if changes:
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    lock_flags = (
        ["--lockfile-only", "--no-frozen-lockfile", "--ignore-scripts"]
        if package_manager == "pnpm"
        else ["--package-lock-only", "--ignore-scripts", "--no-audit"]
    )
    lock = run(
        directory,
        "install",
        *lock_flags,
        deadline=deadline,
    )
    invalid_stable_state = restore_invalid_state(
        directory, security_snapshot, notes, "Stable install"
    )
    if lock.returncode or invalid_stable_state:
        restore_snapshot(directory, security_snapshot)
        notes.append(
            f"Stable upgrade resolution failed (exit {lock.returncode}); restored "
            "the manifest and lockfile from the initial security fix attempt."
        )
        changes = []
    else:
        stable_snapshot = valid_snapshot(directory) or security_snapshot
        last_valid_snapshot = stable_snapshot
        stable_audit = audit(directory, deadline=deadline)
        if restore_invalid_state(
            directory, stable_snapshot, notes, "Stable proposal audit", frozen=True
        ):
            stable_audit = (
                "Audit unavailable: stable proposal audit changed package files."
            )
        if isinstance(stable_audit, dict):
            affected.update(stable_audit.get("vulnerabilities", {}))
        else:
            notes.append(
                "Stable proposal audit unavailable; follow-up security attribution is unconfirmed."
            )
        # Keep fixes within the proposed manifest constraints; never use --force.
        fixed = fix_security(directory, deadline, notes)
        restore_invalid_state(
            directory,
            stable_snapshot,
            notes,
            "Follow-up security fix",
            security_fix=True,
        )
        if fixed.returncode:
            notes.append(
                f"Automatic audit fix returned exit {fixed.returncode}; remaining findings "
                "or a tool error require manual review."
            )
        last_valid_snapshot = valid_snapshot(directory) or stable_snapshot

    validation_snapshot = last_valid_snapshot
    install_args = (
        ["install", "--frozen-lockfile"]
        if package_manager == "pnpm"
        else ["ci", "--no-audit"]
    )
    install = run(directory, *install_args, deadline=deadline)
    invalid_install_state = restore_invalid_state(
        directory, validation_snapshot, notes, "Frozen install", frozen=True
    )
    last_valid_snapshot = valid_snapshot(directory) or validation_snapshot
    if install.returncode or invalid_install_state:
        build_status = (
            f"Not run: {package_manager} frozen install failed "
            f"(exit {install.returncode}); validation failed."
        )
    else:
        build = run(directory, "run", "build", deadline=deadline)
        invalid_build_state = restore_invalid_state(
            directory,
            last_valid_snapshot,
            notes,
            f"{package_manager} run build",
            frozen=True,
        )
        last_valid_snapshot = valid_snapshot(directory) or last_valid_snapshot
        if invalid_build_state:
            build_status = (
                f"Failed: {package_manager} run build changed package files or left invalid "
                "package files; restored the "
                "last valid snapshot; validation failed; manual repair required."
            )
        elif build.returncode == 0:
            build_status = "Passed."
        else:
            build_status = f"Failed (exit {build.returncode}); manual repair required."
    after = audit(directory, deadline=deadline)
    if restore_invalid_state(
        directory, last_valid_snapshot, notes, "Final audit", frozen=True
    ):
        after = f"Audit unavailable: {package_manager} changed package files; restored the last valid snapshot."
    after_snapshot = valid_snapshot(directory) or last_valid_snapshot
    after_lock = after_snapshot[3]
    changes = [
        (name, f"- {name}: `{current}` → `{final}`")
        for section in ("dependencies", "devDependencies", "optionalDependencies")
        for name, current in initial_snapshot[2].get(section, {}).items()
        if (final := after_snapshot[2].get(section, {}).get(name)) != current
    ]
    cache: dict = {}
    describe_pnpm_fixes(directory, before, initial_snapshot[1], notes, deadline, cache)
    describe_pnpm_fixes(directory, after, after_snapshot[1], notes, deadline, cache)
    native_locks = [
        yaml.safe_load(snapshot[1]["pnpm-lock.yaml"])
        if package_manager == "pnpm"
        else snapshot[3]
        for snapshot in (initial_snapshot, after_snapshot)
    ]
    security_changes = []
    reported_changes = set()
    for name in affected:
        old, new = (
            versions(
                lock,
                {
                    "nodes": [
                        node
                        for node, package in lock.get("packages", {}).items()
                        if node == f"node_modules/{name}"
                        or node.endswith(f"/node_modules/{name}")
                        or package.get("name") == name
                    ]
                },
            )
            for lock in (before_lock, after_lock)
        )
        paths_changed = package_paths(native_locks[0], name, package_manager) != (
            package_paths(native_locks[1], name, package_manager)
        )
        if old != new or paths_changed:
            status = "after audit unavailable; fix unconfirmed"
            if isinstance(after, dict):
                status = (
                    f"still reported by {package_manager}"
                    if name in after.get("vulnerabilities", {})
                    else f"no longer reported by {package_manager}"
                )
            change = (
                f"`{old}` → `{new}`"
                if old != new
                else f"dependency paths changed; installed versions `{new}`"
            )
            security_changes.append(f"- {name}: {change}; {status}.")
            reported_changes.add(name)
    security_changes.extend(
        line
        for name, line in changes
        if name in affected and name not in reported_changes
    )
    if time.monotonic() >= deadline:
        notes.append(
            "The shared 45-minute dependency command time budget was exhausted; remaining commands were skipped."
        )
    count_explanation = (
        "pnpm reports registry advisory counts. Multiple affected dependency "
        "paths do not demonstrate exploitability."
        if package_manager == "pnpm"
        else "npm counts affected package entries, including propagated findings in "
        "parent packages. These are not counts of distinct advisories or "
        "demonstrated exploit paths."
    )
    return (
        "# Documentation dependency audit\n\n"
        f"Project: `{directory}`; package manager: `{package_manager}`\n\n"
        f"Run: {datetime.now(timezone.utc).isoformat()}\n\n"
        "This is a best-effort upgrade drive. Remaining vulnerabilities are accepted "
        "between maintenance reviews; this report does not certify that the project is "
        "free of vulnerabilities. Review compatibility and validation before merging.\n\n"
        "## Security findings and fixes\n\n"
        "### Changes to affected dependencies\n\n"
        + (
            "Initial audit evidence was unavailable; any retained security-fix "
            "changes are unconfirmed and cannot be attributed to affected "
            "dependencies. The final audit below describes only the final "
            "dependency state.\n\n"
            if not initial_audit_available
            else ""
        )
        + (
            "\n".join(security_changes)
            or (
                "Affected dependency changes cannot be confirmed because initial "
                "audit evidence was unavailable."
                if not initial_audit_available
                else "No upgrades to affected dependencies resolved."
            )
        )
        + "\n\n"
        f"{count_explanation} Fix candidates can require manual migrations.\n\n"
        "## Other stable dependency upgrades\n\n"
        + (
            "\n".join(line for name, line in changes if name not in affected)
            or "No other direct dependency upgrades resolved."
        )
        + "\n\n"
        f"## Remaining advisories\n\n{format_remaining_audit(after, after_lock)}\n\n"
        f"## Production build\n\n{build_status}\n\n"
        "## Remaining work\n\n"
        "Review retained overrides and peer constraints, transitive dependency fixes, "
        "and any major-version migration requirements. Build and installation logs "
        "are available in the workflow run.\n\n"
        + (
            "\n".join(f"- {note}" for note in notes)
            or "No additional tool errors recorded."
        )
        + "\n"
        f"\n<details>\n<summary>Full before/after {package_manager} audit</summary>\n\n"
        f"### Before\n\n{format_audit(before, before_lock)}\n\n"
        f"### After\n\n{format_audit(after, after_lock)}\n\n"
        "</details>\n"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", default="website")
    parser.add_argument(
        "--report", type=Path, required=True, help="Temporary output for the PR body"
    )
    args = parser.parse_args()
    directory = Path(args.directory)
    if (
        directory.is_absolute()
        or ".." in directory.parts
        or DIRECTORY_PATTERN.fullmatch(args.directory) is None
    ):
        parser.error("directory must be a relative npm project path without '..'")
    if valid_snapshot(directory) is None:
        parser.error(
            "directory must contain valid package files for one npm or pnpm deployment"
        )
    report = prepare(directory)
    args.report.write_text(report)
    print(report)


if __name__ == "__main__":
    main()

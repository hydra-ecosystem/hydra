# SPDX-FileCopyrightText: Contributors to Hydra
# SPDX-License-Identifier: MIT

"""Prepare a best-effort pnpm upgrade report for the website project."""

import argparse
import copy
import json
import re
import subprocess
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

SEVERITY_ORDER = {"critical": 0, "high": 1, "moderate": 2, "low": 3, "info": 4}

PROTECTED_POLICY_FIELDS = (
    "packages",
    "minimumReleaseAge",
    "overrides",
    "allowBuilds",
    "blockExoticSubdeps",
    "strictDepBuilds",
)


def valid_snapshot(
    directory: Path,
) -> tuple[bytes, dict[str, bytes], dict, dict, dict] | None:
    """Retain manifest, lockfile and pnpm policy together for safe restoration."""
    try:
        manifest_bytes = (directory / "package.json").read_bytes()
        manifest = json.loads(manifest_bytes)
        if (
            not isinstance(manifest, dict)
            or not isinstance(manifest.get("packageManager"), str)
            or not manifest["packageManager"].startswith("pnpm@")
        ):
            return None
        files = {
            name: (directory / name).read_bytes()
            for name in ("pnpm-lock.yaml", "pnpm-workspace.yaml")
        }
        policy = yaml.safe_load(files["pnpm-workspace.yaml"])
        lock = yaml.safe_load(files["pnpm-lock.yaml"])
        if (
            not isinstance(policy, dict)
            or any(field not in policy for field in PROTECTED_POLICY_FIELDS)
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
            package_id = key.split("(", 1)[0]
            name, version = package_id.rsplit("@", 1)
            packages[package_id] = {"name": name, "version": version}
        lock = {"packages": packages, "importers": lock["importers"]}
    except (OSError, UnicodeDecodeError, ValueError, TypeError, yaml.YAMLError):
        return None
    return manifest_bytes, files, manifest, lock, copy.deepcopy(policy)


def policy_matches(
    policy: dict,
    reference: dict,
    allowed_exclusions: set[str] | None = None,
) -> bool:
    if {
        key: value for key, value in policy.items() if key != "minimumReleaseAgeExclude"
    } != {
        key: value
        for key, value in reference.items()
        if key != "minimumReleaseAgeExclude"
    }:
        return False
    existing = reference.get("minimumReleaseAgeExclude", [])
    current = policy.get("minimumReleaseAgeExclude", [])
    if not isinstance(existing, list) or not isinstance(current, list):
        return False
    if current[: len(existing)] != existing:
        return False
    return set(current[len(existing) :]) <= (allowed_exclusions or set())


def snapshot_matches(
    directory: Path,
    snapshot: tuple,
    allowed_exclusions: set[str] | None = None,
    *,
    allow_package_changes: bool = False,
) -> bool:
    current = valid_snapshot(directory)
    return (
        current is not None
        and policy_matches(current[4], snapshot[4], allowed_exclusions)
        and (
            allow_package_changes
            or (
                current[0] == snapshot[0]
                and current[1]["pnpm-lock.yaml"] == snapshot[1]["pnpm-lock.yaml"]
            )
        )
    )


def restore_snapshot(
    directory: Path, snapshot: tuple[bytes, dict[str, bytes], dict, dict, dict]
) -> None:
    (directory / "package.json").write_bytes(snapshot[0])
    for name, content in snapshot[1].items():
        (directory / name).write_bytes(content)


def restore_invalid_state(
    directory: Path,
    snapshot: tuple[bytes, dict[str, bytes], dict, dict, dict],
    notes: list[str],
    operation: str,
    allowed_exclusions: set[str] | None = None,
    *,
    allow_package_changes: bool = False,
) -> bool:
    """Restore the last snapshot when a command damaged files or protected policy."""
    if snapshot_matches(
        directory,
        snapshot,
        allowed_exclusions,
        allow_package_changes=allow_package_changes,
    ):
        return False
    restore_snapshot(directory, snapshot)
    notes.append(
        f"{operation} changed protected pnpm policy or package files unexpectedly; "
        "restored the last valid snapshot and did not claim its changes."
    )
    return True


def run(
    directory: Path, *args: str, deadline: float | None = None
) -> subprocess.CompletedProcess[str]:
    command = ["corepack", "pnpm", *args]
    timeout = min(900, deadline - time.monotonic()) if deadline is not None else 900
    if timeout <= 0:
        return subprocess.CompletedProcess(
            command, 124, "", "Annual audit time budget exhausted."
        )
    # GNU timeout owns the process group and kills pnpm and lifecycle/build children.
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


def audit(directory: Path, *, deadline: float | None = None) -> dict | str:
    policy = yaml.safe_load((directory / "pnpm-workspace.yaml").read_bytes())
    if (policy.get("audit") or {}).get("ignore") or (
        policy.get("auditConfig") or {}
    ).get("ignoreGhsas"):
        return "Audit unavailable: pnpm advisory-ignore rules would hide annual findings; manual review required."
    result = run(
        directory,
        "audit",
        "--json",
        "--audit-level",
        "info",
        deadline=deadline,
    )
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        return f"Audit unavailable (exit {result.returncode})."
    if not isinstance(data, dict):
        return f"Audit unavailable (exit {result.returncode})."
    if "advisories" in data and isinstance(data["advisories"], dict):
        vulnerabilities = {}
        for advisory in data["advisories"].values():
            if (
                not isinstance(advisory, dict)
                or any(
                    not isinstance(advisory.get(key), str)
                    for key in (
                        "module_name",
                        "severity",
                        "title",
                        "url",
                        "vulnerable_versions",
                    )
                )
                or not isinstance(advisory.get("findings", []), list)
                or any(
                    not isinstance(finding, dict)
                    or not isinstance(finding.get("version"), str)
                    for finding in advisory.get("findings", [])
                )
            ):
                return "Audit unavailable: malformed pnpm advisory response."
            name = advisory["module_name"]
            nodes = [
                f"{name}@{finding['version']}"
                for finding in advisory.get("findings", [])
            ]
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
            vulnerability["via"].append(
                {
                    "title": advisory["title"],
                    "url": advisory["url"],
                    "severity": advisory["severity"],
                    "range": advisory["vulnerable_versions"],
                    "nodes": nodes,
                }
            )
            vulnerability["severity"] = min(
                vulnerability["severity"],
                advisory["severity"],
                key=lambda severity: SEVERITY_ORDER.get(severity, 5),
            )
            vulnerability["range"] = " || ".join(
                sorted({via["range"] for via in vulnerability["via"]})
            )
            vulnerability["nodes"].extend(nodes)
            vulnerability["fixAvailable"] = vulnerability["fixAvailable"] or bool(
                advisory.get("patched_versions") not in (None, "<0.0.0")
            )
        data["vulnerabilities"] = vulnerabilities
        data["package_manager"] = "pnpm"
    metadata = data.get("metadata")
    counts = metadata.get("vulnerabilities") if isinstance(metadata, dict) else None
    if (
        result.returncode not in (0, 1)
        or data.get("error")
        or not isinstance(counts, dict)
        or not isinstance(data.get("vulnerabilities", {}), dict)
    ):
        return f"Audit unavailable (exit {result.returncode})."
    return data


def fix_security(directory: Path, deadline: float) -> subprocess.CompletedProcess[str]:
    # Update the lockfile without introducing broad security overrides.
    return run(
        directory,
        "audit",
        "--fix=update",
        "--ignore-scripts",
        deadline=deadline,
    )


def eligible_version(
    directory: Path,
    name: str,
    latest: str,
    snapshot: tuple,
    notes: list[str],
    deadline: float,
) -> str | None:
    """Choose a stable version no newer than latest that has passed the age window."""
    result = run(directory, "view", name, "time", "--json", deadline=deadline)
    if restore_invalid_state(
        directory, snapshot, notes, f"Release-time lookup for {name}"
    ):
        return None
    cutoff = datetime.now(timezone.utc) - timedelta(
        minutes=snapshot[4]["minimumReleaseAge"]
    )
    try:
        releases = json.loads(result.stdout)
        if result.returncode or not isinstance(releases, dict):
            return None
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
    except (ValueError, TypeError, AttributeError):
        return None


def versions(lock: dict, vulnerability: dict) -> str:
    packages = lock.get("packages", {})
    found = {
        packages[node]["version"]
        for node in vulnerability.get("nodes", [])
        if node in packages and "version" in packages[node]
    }
    return ", ".join(sorted(found)) or "not recorded in lockfile"


def exclusion_candidates(before_lock: dict, current_lock: dict) -> set[str]:
    """Return package versions newly selected by one security-fix operation."""
    before = {
        (package.get("name"), package.get("version"))
        for package in before_lock.get("packages", {}).values()
    }
    after = {
        (package.get("name"), package.get("version"))
        for package in current_lock.get("packages", {}).values()
    }
    return {f"{name}@{version}" for name, version in after - before}


def format_audit(data: dict | str, lock: dict) -> str:
    if isinstance(data, str):
        return data
    source = "pnpm"
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
    source = "pnpm"
    counts = ", ".join(
        f"{level}: {count}"
        for level, count in data["metadata"]["vulnerabilities"].items()
    )
    vulnerabilities = data.get("vulnerabilities", {})
    if not vulnerabilities:
        return f"No known vulnerabilities reported by {source}."
    advisories = {}
    for name, vulnerability in vulnerabilities.items():
        for via in vulnerability.get("via", []):
            if isinstance(via, dict):
                advisory = advisories.setdefault(
                    via["url"], {"detail": via, "packages": set()}
                )
                affected_versions = versions(
                    lock, via if "nodes" in via else vulnerability
                )
                advisory["packages"].add(f"{name}@{affected_versions}")
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
        )
    return f"Registry advisory counts: {counts}.\n\n" + (
        "\n".join(lines)
        or f"{source} supplied no direct advisory details; see the full findings below."
    )


def prepare(directory: Path) -> str:
    # Leave time in the 60-minute job to write and upload a partial report.
    deadline = time.monotonic() + 45 * 60
    manifest_path = directory / "package.json"
    notes = []
    initial_snapshot = valid_snapshot(directory)
    if initial_snapshot is None:
        raise ValueError(
            "Valid manifest, one deployment lockfile and package-manager policy are required"
        )
    before_lock = initial_snapshot[3]
    before = audit(directory, deadline=deadline)
    if restore_invalid_state(directory, initial_snapshot, notes, "Initial audit"):
        before = (
            "Audit unavailable: pnpm changed protected policy or left invalid package "
            "files; restored the initial snapshot."
        )
    last_valid_snapshot = valid_snapshot(directory) or initial_snapshot
    affected = before.get("vulnerabilities", {}) if isinstance(before, dict) else {}
    changes = []

    # Give compatible security fixes the first use of the shared time budget.
    security_before_lock = last_valid_snapshot[3]
    fixed = fix_security(directory, deadline)
    candidate_snapshot = valid_snapshot(directory)
    allowed_exclusions = (
        exclusion_candidates(security_before_lock, candidate_snapshot[3])
        if candidate_snapshot is not None
        else set()
    )
    restore_invalid_state(
        directory,
        last_valid_snapshot,
        notes,
        "Initial security fix",
        allowed_exclusions,
        allow_package_changes=True,
    )
    if fixed.returncode:
        notes.append(
            f"Initial security fix returned exit {fixed.returncode}; remaining findings "
            "or a tool error require manual review."
        )
    # Preserve those fixes if the wider stable-version upgrade cannot resolve.
    security_snapshot = valid_snapshot(directory) or last_valid_snapshot
    last_valid_snapshot = security_snapshot
    manifest = security_snapshot[2]

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
                directory, security_snapshot, notes, f"Version lookup for {name}"
            ):
                continue
            try:
                latest = json.loads(result.stdout)
            except json.JSONDecodeError:
                latest = None
            if (
                not result.returncode
                and isinstance(latest, str)
                and re.fullmatch(r"\d+\.\d+\.\d+", latest)
                and latest != current.lstrip("~^")
            ):
                latest = eligible_version(
                    directory, name, latest, security_snapshot, notes, deadline
                )
            if (
                result.returncode
                or not isinstance(latest, str)
                or not re.fullmatch(r"\d+\.\d+\.\d+", latest)
            ):
                notes.append(f"Could not look up {name}; retained `{current}`.")
                continue
            resolved = (
                security_snapshot[3]["importers"]["."]
                .get(section, {})
                .get(name, {})
                .get("version", current.lstrip("~^"))
                .split("(", 1)[0]
            )
            if not re.fullmatch(r"\d+\.\d+\.\d+", resolved):
                notes.append(
                    f"Retained {name} locked version `{resolved}` for manual review."
                )
                continue
            floor = max(
                tuple(map(int, current.lstrip("~^").split("."))),
                tuple(map(int, resolved.split("."))),
            )
            if tuple(map(int, latest.split("."))) > floor:
                manifest[section][name] = latest
                changes.append((name, f"- {name}: `{current}` → `{latest}`"))

    if changes:
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    if not snapshot_matches(directory, security_snapshot, allow_package_changes=True):
        restore_snapshot(directory, security_snapshot)
        notes.append(
            "Stable upgrade preparation changed protected pnpm policy or left invalid "
            "package files; restored the last valid snapshot and discarded those upgrades."
        )
        changes = []
    lock = run(
        directory,
        "install",
        "--lockfile-only",
        "--no-frozen-lockfile",
        "--ignore-scripts",
        deadline=deadline,
    )
    invalid_stable_state = restore_invalid_state(
        directory,
        security_snapshot,
        notes,
        "Stable install",
        allow_package_changes=True,
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
        # Keep fixes within the proposed manifest constraints; never use --force.
        follow_up_before_lock = stable_snapshot[3]
        fixed = fix_security(directory, deadline)
        candidate_snapshot = valid_snapshot(directory)
        allowed_exclusions = (
            exclusion_candidates(follow_up_before_lock, candidate_snapshot[3])
            if candidate_snapshot is not None
            else set()
        )
        restore_invalid_state(
            directory,
            stable_snapshot,
            notes,
            "Follow-up security fix",
            allowed_exclusions,
            allow_package_changes=True,
        )
        if fixed.returncode:
            notes.append(
                f"Automatic audit fix returned exit {fixed.returncode}; remaining findings "
                "or a tool error require manual review."
            )
        last_valid_snapshot = valid_snapshot(directory) or stable_snapshot

    validation_snapshot = last_valid_snapshot
    install = run(directory, "install", "--frozen-lockfile", deadline=deadline)
    invalid_install_state = restore_invalid_state(
        directory, validation_snapshot, notes, "Frozen install"
    )
    last_valid_snapshot = valid_snapshot(directory) or validation_snapshot
    if install.returncode or invalid_install_state:
        build_status = (
            f"Not run: pnpm frozen install failed (exit {install.returncode})."
        )
    else:
        build = run(directory, "run", "build", deadline=deadline)
        invalid_build_state = restore_invalid_state(
            directory, last_valid_snapshot, notes, "pnpm run build"
        )
        last_valid_snapshot = valid_snapshot(directory) or last_valid_snapshot
        if invalid_build_state:
            build_status = (
                "Failed: pnpm run build left invalid package files; restored the "
                "last valid snapshot; manual repair required."
            )
        elif build.returncode == 0:
            build_status = "Passed."
        else:
            build_status = f"Failed (exit {build.returncode}); manual repair required."
    after = audit(directory, deadline=deadline)
    if restore_invalid_state(directory, last_valid_snapshot, notes, "Final audit"):
        after = (
            "Audit unavailable: pnpm changed protected policy or left invalid package "
            "files; restored the last valid snapshot."
        )
    after_snapshot = valid_snapshot(directory) or last_valid_snapshot
    after_lock = after_snapshot[3]
    after_affected = after.get("vulnerabilities", {}) if isinstance(after, dict) else {}
    security_changes = []
    reported_changes = set()
    for name, vulnerability in affected.items():
        old = versions(before_lock, vulnerability)
        current = after_affected.get(name)
        if current is None:
            current = {
                "nodes": [
                    node
                    for node, package in after_lock.get("packages", {}).items()
                    if package.get("name") == name
                ]
            }
        new = versions(after_lock, current)
        if old != new:
            status = "after audit unavailable; fix unconfirmed"
            if isinstance(after, dict):
                status = (
                    "still reported by pnpm"
                    if name in after.get("vulnerabilities", {})
                    else "no longer reported by pnpm"
                )
            security_changes.append(f"- {name}: `{old}` → `{new}`; {status}.")
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
    return (
        "# Annual documentation dependency audit\n\n"
        f"Project: `{directory}`; package manager: `pnpm`\n\n"
        f"Run: {datetime.now(timezone.utc).isoformat()}\n\n"
        "This is a best-effort upgrade drive. Remaining vulnerabilities are accepted "
        "between annual reviews; this report does not certify that the project is "
        "free of vulnerabilities. Review compatibility and validation before merging.\n\n"
        "## Security findings and fixes\n\n"
        "### Changes to affected dependencies\n\n"
        + (
            "\n".join(security_changes)
            or "No upgrades to affected dependencies resolved."
        )
        + "\n\n"
        "pnpm reports registry advisory counts. Multiple affected dependency paths "
        "do not demonstrate exploitability. Fix candidates can require manual migrations.\n\n"
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
        "\n<details>\n<summary>Full before/after pnpm audit</summary>\n\n"
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
        or not re.fullmatch(r"[A-Za-z0-9_./-]+", args.directory)
    ):
        parser.error("directory must be a relative pnpm project path without '..'")
    if valid_snapshot(directory) is None:
        parser.error(
            "directory must contain valid package files for the pinned pnpm deployment"
        )
    report = prepare(directory)
    args.report.write_text(report)
    print(report)


if __name__ == "__main__":
    main()

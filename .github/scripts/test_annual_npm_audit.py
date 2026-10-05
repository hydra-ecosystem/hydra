# SPDX-FileCopyrightText: Contributors to Hydra
# SPDX-License-Identifier: MIT

import json
import os
import runpy
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml

audit_module = runpy.run_path(str(Path(__file__).with_name("annual_npm_audit.py")))
format_remaining_audit = audit_module["format_remaining_audit"]
format_audit = audit_module["format_audit"]
audit = audit_module["audit"]
prepare = audit_module["prepare"]


def test_remaining_summary_deduplicates_propagated_advisories():
    advisory = {
        "title": "Nested pattern exhaustion",
        "url": "https://github.com/advisories/GHSA-example",
        "severity": "high",
        "range": "<=3.0.3",
    }
    data = {
        "metadata": {"vulnerabilities": {"high": 3, "total": 3}},
        "vulnerabilities": {
            "braces": {
                "nodes": ["node_modules/braces"],
                "via": [advisory, advisory],
            },
            "micromatch": {"via": ["braces"]},
            "docusaurus": {"via": ["micromatch"]},
        },
    }
    lock = {"packages": {"node_modules/braces": {"version": "3.0.3"}}}

    report = format_remaining_audit(data, lock)

    assert report.count("https://github.com/advisories/GHSA-example") == 1
    assert "braces@3.0.3" in report
    assert "high: 3, total: 3" in report
    assert "Registry advisory counts" in report
    assert "docusaurus" not in report


def test_remaining_summary_prioritizes_severity():
    data = {
        "metadata": {"vulnerabilities": {"low": 1, "critical": 1, "total": 2}},
        "vulnerabilities": {
            name: {
                "via": [
                    {
                        "title": name,
                        "url": f"https://github.com/advisories/{name}",
                        "severity": severity,
                        "range": "*",
                    }
                ]
            }
            for name, severity in (("low-issue", "low"), ("urgent", "critical"))
        },
    }

    report = format_remaining_audit(data, {})

    assert report.index("[urgent]") < report.index("[low-issue]")


@pytest.mark.parametrize(
    "data, expected",
    [
        ("Audit unavailable (exit 124).", "Audit unavailable"),
        (
            {"metadata": {"vulnerabilities": {"total": 0}}},
            "No known vulnerabilities reported by pnpm.",
        ),
        (
            {
                "metadata": {"vulnerabilities": {"high": 1, "total": 1}},
                "vulnerabilities": {"parent": {"via": ["child"]}},
            },
            "pnpm supplied no direct advisory details",
        ),
    ],
)
def test_remaining_summary_reports_unavailable_and_incomplete_evidence(data, expected):
    assert expected in format_remaining_audit(data, {})


def test_workflow_dispatch_uses_the_configured_project():
    workflow = (
        Path(__file__).parents[1] / "workflows/annual-npm-audit.yml"
    ).read_text()

    assert "cron: '0 2 30 1 *'" in workflow
    assert "  workflow_dispatch:\n" in workflow
    assert "inputs.directory" not in workflow
    assert "WEBSITE_PROJECT: website" in workflow


def test_publisher_uses_the_audited_revision():
    workflow = yaml.safe_load(
        (Path(__file__).parents[1] / "workflows/annual-npm-audit.yml").read_text()
    )
    for job in ("audit", "pull-request"):
        checkout = next(
            step
            for step in workflow["jobs"][job]["steps"]
            if step.get("uses", "").startswith("actions/checkout@")
        )
        assert checkout["with"]["ref"] == "${{ github.sha }}"


@pytest.mark.parametrize(
    "event, ref, expected",
    [
        ("schedule", "refs/heads/main", 0),
        ("workflow_dispatch", "refs/heads/main", 0),
        ("workflow_dispatch", "refs/heads/feature", 1),
        ("workflow_dispatch", "refs/tags/main", 1),
    ],
)
def test_manual_dispatch_ref_guard(event, ref, expected):
    workflow = yaml.safe_load(
        (Path(__file__).parents[1] / "workflows/annual-npm-audit.yml").read_text()
    )
    steps = workflow["jobs"]["audit"]["steps"]
    guard_index = next(
        index
        for index, step in enumerate(steps)
        if step.get("name") == "Validate manual dispatch ref"
    )
    checkout_index = next(
        index
        for index, step in enumerate(steps)
        if step.get("uses", "").startswith("actions/checkout@")
    )
    guard = steps[guard_index]

    assert guard_index < checkout_index
    assert (
        guard["env"]["DEFAULT_BRANCH"]
        == "${{ github.event.repository.default_branch }}"
    )
    result = subprocess.run(
        ["bash", "-c", guard["run"]],
        env={
            **os.environ,
            "DEFAULT_BRANCH": "main",
            "GITHUB_EVENT_NAME": event,
            "GITHUB_REF": ref,
        },
        capture_output=True,
        text=True,
    )

    assert result.returncode == (0 if expected == 0 else 1)
    if expected:
        assert "must target the repository default branch" in result.stderr


@pytest.fixture
def pnpm_project(tmp_path):
    (tmp_path / "package.json").write_text(
        json.dumps(
            {"packageManager": "pnpm@11.21.0", "dependencies": {"renderer": "^1.0.0"}}
        )
    )
    (tmp_path / "pnpm-lock.yaml").write_text(
        yaml.safe_dump(
            {
                "lockfileVersion": "9.0",
                "importers": {".": {}},
                "packages": {"renderer@1.0.0": {}},
            }
        )
    )
    (tmp_path / "pnpm-workspace.yaml").write_text(
        yaml.safe_dump(
            {
                "packages": ["."],
                "minimumReleaseAge": 14400,
                "minimumReleaseAgeExclude": ["other@3.0.0"],
                "blockExoticSubdeps": True,
                "strictDepBuilds": True,
                "allowBuilds": {"core-js": False},
                "overrides": {"other": "3.0.0"},
            }
        )
    )
    return tmp_path


def test_info_advisory_uses_pinned_level_and_is_rendered(pnpm_project, monkeypatch):
    commands = []
    response = {
        "metadata": {"vulnerabilities": {"info": 1, "total": 1}},
        "advisories": {
            "123": {
                "module_name": "renderer",
                "severity": "info",
                "title": "Informational renderer notice",
                "url": "https://github.com/advisories/GHSA-info",
                "vulnerable_versions": "<1.0.1",
                "patched_versions": ">=1.0.1",
                "findings": [{"version": "1.0.0"}],
            }
        },
    }

    def invoke(command, *, cwd, **kwargs):
        commands.append(tuple(command[5:]))
        return subprocess.CompletedProcess(command, 1, json.dumps(response), "")

    monkeypatch.setattr(subprocess, "run", invoke)
    data = audit(pnpm_project)
    lock = audit_module["valid_snapshot"](pnpm_project)[3]

    assert commands == [("audit", "--json", "--audit-level", "info")]
    for report in (format_remaining_audit(data, lock), format_audit(data, lock)):
        assert "https://github.com/advisories/GHSA-info" in report
        assert "Informational renderer notice" in report
        assert "info" in report
        assert "<1.0.1" in report
        assert "1.0.0" in report


@pytest.mark.parametrize("failure", [None, "stable", "policy", "frozen", "build"])
def test_pnpm_security_first_and_policy_restoration(pnpm_project, monkeypatch, failure):
    commands = []
    fixes = 0
    workspace = pnpm_project / "pnpm-workspace.yaml"
    lockfile = pnpm_project / "pnpm-lock.yaml"

    def invoke(command, *, cwd, **kwargs):
        nonlocal fixes
        assert command[3:5] == ["corepack", "pnpm"]
        args = command[5:]
        commands.append(args)
        stdout, code = "", 0
        if args[:2] == ["audit", "--json"]:
            stdout = json.dumps(
                {
                    "metadata": {"vulnerabilities": {"high": 1}},
                    "advisories": {
                        "123": {
                            "module_name": "renderer",
                            "severity": "high",
                            "title": "Render bug",
                            "url": "https://github.com/advisories/GHSA-render",
                            "vulnerable_versions": "<1.0.1",
                            "patched_versions": ">=1.0.1",
                            "findings": [
                                {"version": "1.0.0" if fixes == 0 else "1.0.1"}
                            ],
                        }
                    },
                }
            )
        elif args[:2] == ["audit", "--fix=update"]:
            fixes += 1
            policy = yaml.safe_load(workspace.read_text())
            exclusions = policy.setdefault("minimumReleaseAgeExclude", [])
            if "renderer@1.0.1" not in exclusions:
                exclusions.append("renderer@1.0.1")
            workspace.write_text(yaml.safe_dump(policy))
            locked = yaml.safe_load(lockfile.read_text())
            locked["packages"] = {"renderer@1.0.1": {}}
            lockfile.write_text(yaml.safe_dump(locked))
            if failure == "policy" and fixes == 1:
                workspace.write_text("[")
                code = 124
        elif args[0] == "view":
            stdout = (
                '{"2.0.0": "2020-01-01T00:00:00Z"}' if args[-2] == "time" else '"2.0.0"'
            )
        elif args[0] == "install" and "--lockfile-only" in args:
            if failure == "stable":
                workspace.write_text("[")
                lockfile.unlink()
                code = 1
        elif args == ["install", "--frozen-lockfile"] and failure == "frozen":
            (cwd / "package.json").write_text("{")
        elif args == ["run", "build"] and failure == "build":
            (cwd / "package.json").write_text("{")
        return subprocess.CompletedProcess(command, code, stdout, "")

    monkeypatch.setattr(subprocess, "run", invoke)
    report = prepare(pnpm_project)
    policy = yaml.safe_load(workspace.read_text())
    assert policy["minimumReleaseAge"] == 14400
    assert policy["blockExoticSubdeps"] and policy["strictDepBuilds"]
    assert policy["allowBuilds"] == {"core-js": False}
    assert policy["overrides"] == {"other": "3.0.0"}
    assert commands.index(["audit", "--fix=update", "--ignore-scripts"]) < next(
        i for i, args in enumerate(commands) if args[0] == "view"
    )
    assert "--force" not in str(commands)
    assert "pnpm" in report and "Render bug" in report
    assert "Registry advisory counts" in report
    assert "Full before/after pnpm audit" in report
    if failure == "stable":
        assert policy["minimumReleaseAgeExclude"] == [
            "other@3.0.0",
            "renderer@1.0.1",
        ]
        assert "renderer: `^1.0.0` → `2.0.0`" not in report
        assert "renderer: `1.0.0` → `1.0.1`" in report
    if failure == "policy":
        assert "restored" in report and "exit 124" in report
    if failure == "frozen":
        assert "Not run: pnpm frozen install failed" in report
        assert ["run", "build"] not in commands
    if failure == "build":
        assert "pnpm run build left invalid package files" in report


@pytest.mark.parametrize("scenario", ["initial-safe", "followup-safe"])
def test_security_exclusion_requires_complete_lock_delta(
    pnpm_project, monkeypatch, scenario
):
    workspace = pnpm_project / "pnpm-workspace.yaml"
    lockfile = pnpm_project / "pnpm-lock.yaml"
    original = yaml.safe_load(workspace.read_text())
    if scenario == "initial-safe":
        lock = yaml.safe_load(lockfile.read_text())
        lock["packages"]["renderer@2.0.0"] = {}
        lockfile.write_text(yaml.safe_dump(lock))
    fixes = 0

    def invoke(command, *, cwd, **kwargs):
        nonlocal fixes
        args = command[5:]
        stdout, code = "", 0
        if args[:2] == ["audit", "--json"]:
            stdout = json.dumps(
                {
                    "metadata": {"vulnerabilities": {"high": 1}},
                    "advisories": {
                        "123": {
                            "module_name": "renderer",
                            "severity": "high",
                            "title": "Render bug",
                            "url": "https://github.com/advisories/GHSA-render",
                            "vulnerable_versions": "<1.0.1",
                            "patched_versions": ">=1.0.1",
                            "findings": [{"version": "1.0.0"}],
                        }
                    },
                }
            )
        elif args[:2] == ["audit", "--fix=update"]:
            fixes += 1
            if scenario == "initial-safe" or fixes > 1:
                policy = yaml.safe_load(workspace.read_text())
                policy["minimumReleaseAgeExclude"].append("renderer@2.0.0")
                workspace.write_text(yaml.safe_dump(policy))
        elif args[0] == "view":
            stdout = (
                '{"2.0.0": "2020-01-01T00:00:00Z"}'
                if args[-2] == "time"
                else '"2.0.0"'
                if scenario == "followup-safe"
                else '"1.0.0"'
            )
        elif args[0] == "install" and "--lockfile-only" in args:
            if scenario == "followup-safe":
                lock = yaml.safe_load(lockfile.read_text())
                lock["packages"]["renderer@2.0.0"] = {}
                lockfile.write_text(yaml.safe_dump(lock))
        return subprocess.CompletedProcess(command, code, stdout, "")

    monkeypatch.setattr(subprocess, "run", invoke)

    report = prepare(pnpm_project)

    assert yaml.safe_load(workspace.read_text()) == original
    assert "did not claim its changes" in report
    if scenario == "followup-safe":
        lock = yaml.safe_load(lockfile.read_text())
        assert "renderer@2.0.0" in lock["packages"]


@pytest.mark.parametrize(
    "operation, field, value",
    [
        ("audit-fix", "minimumReleaseAge", 1),
        ("install", "overrides", {"other": "changed"}),
        ("frozen", "allowBuilds", {}),
        ("build", "strictDepBuilds", False),
    ],
)
def test_protected_policy_mutation_is_restored_and_reported(
    pnpm_project, monkeypatch, operation, field, value
):
    workspace = pnpm_project / "pnpm-workspace.yaml"
    original = yaml.safe_load(workspace.read_text())
    mutated = False

    def invoke(command, *, cwd, **kwargs):
        nonlocal mutated
        args = command[5:]
        stdout, code = "", 0
        if args[:2] == ["audit", "--json"]:
            stdout = json.dumps(
                {
                    "metadata": {"vulnerabilities": {"high": 1}},
                    "advisories": {
                        "123": {
                            "module_name": "renderer",
                            "severity": "high",
                            "title": "Render bug",
                            "url": "https://github.com/advisories/GHSA-render",
                            "vulnerable_versions": "<1.0.1",
                            "patched_versions": ">=1.0.1",
                            "findings": [{"version": "1.0.0"}],
                        }
                    },
                }
            )
        elif args[:2] == ["audit", "--fix=update"]:
            if operation == "audit-fix" and not mutated:
                policy = yaml.safe_load(workspace.read_text())
                policy[field] = value
                workspace.write_text(yaml.safe_dump(policy))
                mutated = True
        elif args[0] == "view":
            stdout = '"1.0.0"'
        elif args[0] == "install" and "--lockfile-only" in args:
            if operation == "install" and not mutated:
                policy = yaml.safe_load(workspace.read_text())
                policy[field] = value
                workspace.write_text(yaml.safe_dump(policy))
                mutated = True
        elif args == ["install", "--frozen-lockfile"]:
            if operation == "frozen" and not mutated:
                policy = yaml.safe_load(workspace.read_text())
                policy[field] = value
                workspace.write_text(yaml.safe_dump(policy))
                mutated = True
        elif args == ["run", "build"]:
            if operation == "build" and not mutated:
                policy = yaml.safe_load(workspace.read_text())
                policy[field] = value
                workspace.write_text(yaml.safe_dump(policy))
                mutated = True
        return subprocess.CompletedProcess(command, code, stdout, "")

    monkeypatch.setattr(subprocess, "run", invoke)

    report = prepare(pnpm_project)

    policy = yaml.safe_load(workspace.read_text())
    assert policy == original
    assert "changed protected pnpm policy" in report


def test_pnpm_shared_workspace_is_rejected(pnpm_project):
    workspace = pnpm_project / "pnpm-workspace.yaml"
    policy = yaml.safe_load(workspace.read_text())
    policy["packages"] = [".", "../other"]
    workspace.write_text(yaml.safe_dump(policy))
    with pytest.raises(ValueError, match="one deployment"):
        prepare(pnpm_project)


def test_pnpm_reference_policy_and_publisher_include_workspace():
    root = Path(__file__).parents[2]
    policy = yaml.safe_load((root / "website/pnpm-workspace.yaml").read_text())
    assert policy["minimumReleaseAge"] == 14400
    assert policy["blockExoticSubdeps"] and policy["strictDepBuilds"]
    assert policy["allowBuilds"] == {"core-js": False, "core-js-pure": False}
    workflow = (root / ".github/workflows/annual-npm-audit.yml").read_text()
    assert "${{ env.WEBSITE_PROJECT }}/pnpm-workspace.yaml" in workflow
    assert "package-lock.json" not in workflow
    assert "for file in pnpm-lock.yaml pnpm-workspace.yaml" in workflow
    publisher = yaml.safe_load(workflow)["jobs"]["pull-request"]
    assert all("corepack" not in step.get("run", "") for step in publisher["steps"])


def test_stable_upgrades_respect_release_age(pnpm_project, monkeypatch):
    manifest_path = pnpm_project / "package.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["dependencies"]["other"] = "1.0.0"
    manifest_path.write_text(json.dumps(manifest))
    now = datetime.now(timezone.utc)

    def invoke(command, *, cwd, **kwargs):
        args = command[5:]
        stdout = ""
        if args[:2] == ["audit", "--json"]:
            stdout = json.dumps({"metadata": {"vulnerabilities": {"total": 0}}})
        elif args[0] == "view":
            if args[-2] == "time":
                stdout = json.dumps(
                    {
                        "1.5.0": (now - timedelta(days=11)).isoformat(),
                        "2.0.0": (now - timedelta(days=1)).isoformat(),
                        "3.0.0-beta.1": (now - timedelta(days=20)).isoformat(),
                    }
                    if args[1] == "renderer"
                    else {"2.0.0": (now - timedelta(days=11)).isoformat()}
                )
            else:
                stdout = '"2.0.0"'
        return subprocess.CompletedProcess(command, 0, stdout, "")

    monkeypatch.setattr(subprocess, "run", invoke)
    report = prepare(pnpm_project)

    manifest = json.loads(manifest_path.read_text())
    assert manifest["dependencies"] == {"renderer": "1.5.0", "other": "2.0.0"}
    assert "renderer: `^1.0.0` → `1.5.0`" in report
    assert "other: `1.0.0` → `2.0.0`" in report


@pytest.mark.parametrize(
    "eligible, expected", [("1.0.5", "^1.0.0"), ("1.0.7", "1.0.7")]
)
def test_stable_selection_preserves_direct_locked_security_fix(
    pnpm_project, monkeypatch, eligible, expected
):
    lockfile = pnpm_project / "pnpm-lock.yaml"
    lock = yaml.safe_load(lockfile.read_text())
    lock["importers"]["."] = {
        "dependencies": {"renderer": {"specifier": "^1.0.0", "version": "1.0.0"}}
    }
    lockfile.write_text(yaml.safe_dump(lock))
    fixes = 0
    now = datetime.now(timezone.utc)

    def invoke(command, *, cwd, **kwargs):
        nonlocal fixes
        args = command[5:]
        stdout = ""
        if args[:2] == ["audit", "--json"]:
            stdout = json.dumps({"metadata": {"vulnerabilities": {"total": 0}}})
        elif args[:2] == ["audit", "--fix=update"]:
            fixes += 1
            if fixes == 1:
                lock = yaml.safe_load(lockfile.read_text())
                lock["importers"]["."]["dependencies"]["renderer"]["version"] = (
                    "1.0.6(peer@1.0.0)"
                )
                lock["packages"] = {"renderer@1.0.6": {}, "renderer@3.0.0": {}}
                lockfile.write_text(yaml.safe_dump(lock))
        elif args[0] == "view":
            stdout = (
                json.dumps(
                    {
                        eligible: (now - timedelta(days=11)).isoformat(),
                        "2.0.0": (now - timedelta(days=1)).isoformat(),
                        "3.0.0": (now - timedelta(days=11)).isoformat(),
                    }
                )
                if args[-2] == "time"
                else '"2.0.0"'
            )
        elif args[0] == "install" and "--lockfile-only" in args:
            manifest = json.loads((pnpm_project / "package.json").read_text())
            selected = manifest["dependencies"]["renderer"]
            if not selected.startswith("^"):
                lock = yaml.safe_load(lockfile.read_text())
                lock["importers"]["."]["dependencies"]["renderer"]["version"] = selected
                lockfile.write_text(yaml.safe_dump(lock))
        return subprocess.CompletedProcess(command, 0, stdout, "")

    monkeypatch.setattr(subprocess, "run", invoke)
    prepare(pnpm_project)

    manifest = json.loads((pnpm_project / "package.json").read_text())
    assert manifest["dependencies"]["renderer"] == expected
    version = yaml.safe_load(lockfile.read_text())["importers"]["."]["dependencies"][
        "renderer"
    ]["version"].split("(")[0]
    assert tuple(map(int, version.split("."))) >= (1, 0, 6)


@pytest.mark.parametrize(
    "operation", ["initial-audit", "view", "frozen", "build", "final-audit"]
)
@pytest.mark.parametrize("filename", ["package.json", "pnpm-lock.yaml"])
def test_read_only_commands_restore_valid_package_mutations(
    pnpm_project, monkeypatch, operation, filename
):
    path = pnpm_project / filename
    original = path.read_bytes()
    audits = 0
    mutated = False

    def invoke(command, *, cwd, **kwargs):
        nonlocal audits, mutated
        args = command[5:]
        stdout, stage = "", None
        if args[:2] == ["audit", "--json"]:
            audits += 1
            stage = "initial-audit" if audits == 1 else "final-audit"
            stdout = json.dumps({"metadata": {"vulnerabilities": {"total": 0}}})
        elif args[0] == "view":
            stage, stdout = "view", '"1.0.0"'
        elif args == ["install", "--frozen-lockfile"]:
            stage = "frozen"
        elif args == ["run", "build"]:
            stage = "build"
        if stage == operation and not mutated:
            if filename == "package.json":
                manifest = json.loads(path.read_text())
                manifest["scripts"] = {"unexpected": "unplanned"}
                path.write_text(json.dumps(manifest))
            else:
                lock = yaml.safe_load(path.read_text())
                lock["packages"]["unexpected@1.0.0"] = {}
                path.write_text(yaml.safe_dump(lock))
            mutated = True
        return subprocess.CompletedProcess(command, 0, stdout, "")

    monkeypatch.setattr(subprocess, "run", invoke)
    report = prepare(pnpm_project)

    assert mutated
    assert path.read_bytes() == original
    assert "did not claim its changes" in report


@pytest.mark.parametrize(
    "changed, existing", [(False, False), (False, True), (True, False), (True, True)]
)
def test_publisher_no_change_and_regular_pr_behavior(tmp_path, changed, existing):
    workflow = yaml.safe_load(
        (Path(__file__).parents[1] / "workflows/annual-npm-audit.yml").read_text()
    )
    publisher = workflow["jobs"]["pull-request"]["steps"][-1]["run"]
    stubs = tmp_path / "bin"
    stubs.mkdir()
    commands = tmp_path / "commands"
    for name, body in {
        "git": """#!/bin/sh
printf 'git %s\\n' "$*" >> "$COMMAND_LOG"
case "$1" in
  rev-parse) printf 'existing-head\\n';;
  diff) if [ "$CHANGED" = 1 ]; then exit 1; fi;;
esac
""",
        "gh": """#!/bin/sh
printf 'gh %s\\n' "$*" >> "$COMMAND_LOG"
if [ "$1 $2" = 'pr list' ] && [ "$EXISTING" = 1 ]; then printf '123\\n'; fi
""",
    }.items():
        stub = stubs / name
        stub.write_text(body)
        stub.chmod(0o755)
    project = tmp_path / "website"
    project.mkdir()
    for name in ("package.json", "pnpm-lock.yaml", "pnpm-workspace.yaml"):
        (project / name).write_text("candidate")
    (tmp_path / "annual-npm-audit-pr.md").write_text("Audit report\n")
    subprocess.run(
        ["bash", "-c", publisher],
        cwd=tmp_path,
        env={
            **os.environ,
            "PATH": f"{stubs}:{os.environ['PATH']}",
            "COMMAND_LOG": str(commands),
            "CHANGED": str(int(changed)),
            "EXISTING": str(int(existing)),
            "RUNNER_TEMP": str(tmp_path),
            "WEBSITE_PROJECT": "website",
            "PR_BRANCH": "maintenance/annual-website-dependencies",
            "BASE_BRANCH": "main",
            "PR_TITLE": "Annual website dependencies",
            "PR_FOOTER": "Run details",
        },
        check=True,
        capture_output=True,
        text=True,
    )
    log = commands.read_text()
    assert ("git commit" in log) == changed
    assert ("git push" in log) == changed
    assert ("gh pr edit" in log) == existing
    assert ("gh pr create" in log) == (changed and not existing)
    assert "--draft" not in log and "gh pr ready" not in log
    assert "git add -- website/package.json" in log
    assert "git add -- website/pnpm-lock.yaml" in log
    assert "git add -- website/pnpm-workspace.yaml" in log
    assert "git add -- website/package-lock.json" not in log
    assert "git add -- website/annual-npm-audit-pr.md" not in log
    if changed:
        assert (
            "--force-with-lease=refs/heads/maintenance/annual-website-dependencies:existing-head"
            in log
        )

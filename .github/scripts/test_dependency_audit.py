# SPDX-FileCopyrightText: Contributors to Hydra
# SPDX-License-Identifier: MIT
import json
import os
import runpy
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

audit_module = runpy.run_path(str(Path(__file__).with_name("dependency_audit.py")))
format_remaining_audit = audit_module["format_remaining_audit"]
format_audit = audit_module["format_audit"]
audit = audit_module["audit"]
prepare = audit_module["prepare"]


@pytest.mark.parametrize(
    ("first_versions", "second_versions"),
    [(["1.0.0"], ["2.0.0"]), (["1.0.0", "2.0.0"], ["2.0.0"]), ([], ["2.0.0"])],
)
def test_pnpm_remaining_versions_are_scoped_to_each_advisory(
    pnpm_project, monkeypatch, first_versions, second_versions
):
    lockfile = pnpm_project / "pnpm-lock.yaml"
    lock = yaml.safe_load(lockfile.read_bytes())
    lock["packages"]["renderer@2.0.0"] = {}
    lockfile.write_text(yaml.safe_dump(lock))
    advisories = {
        name: {
            "module_name": "renderer",
            "severity": "high",
            "title": name,
            "url": f"https://github.com/advisories/{name}",
            "vulnerable_versions": "*",
            "patched_versions": "<0.0.0",
            "findings": [{"version": version} for version in versions],
        }
        for name, versions in (("first", first_versions), ("second", second_versions))
    }

    def invoke(command, **kwargs):
        return subprocess.CompletedProcess(
            command,
            1,
            json.dumps(
                {
                    "metadata": {"vulnerabilities": {"high": 2, "total": 2}},
                    "advisories": advisories,
                }
            ),
            "",
        )

    monkeypatch.setattr(subprocess, "run", invoke)
    data = audit(pnpm_project)
    report = format_remaining_audit(
        data, audit_module["valid_snapshot"](pnpm_project)[3]
    )

    for name, versions in (("first", first_versions), ("second", second_versions)):
        line = next(line for line in report.splitlines() if f"[{name}]" in line)
        expected = ", ".join(sorted(versions)) or "not recorded in lockfile"
        assert f"locked `renderer@{expected}`;" in line
    assert set(data["vulnerabilities"]["renderer"]["nodes"]) == {
        f"renderer@{version}" for version in first_versions + second_versions
    }


def fake_npm(monkeypatch, *, install=0, build=0, audit_error=False):
    def invoke(command, *, cwd, **kwargs):
        args = command[4:]
        stdout, code = "", 0
        if args[0] == "view":
            stdout = '"2.0.0"'
        elif args[0] == "install":
            (cwd / "package-lock.json").write_text('{"candidate": true}')
        elif args[0] == "ci":
            code = install
        elif args[:2] == ["run", "build"]:
            code = build
        elif args[:2] == ["audit", "--json"]:
            code = 1
            stdout = json.dumps(
                {"error": {"code": "ENETUNREACH"}}
                if audit_error
                else {
                    "metadata": {"vulnerabilities": {"total": 0}},
                    "vulnerabilities": {},
                }
            )
        return subprocess.CompletedProcess(command, code, stdout, "")

    monkeypatch.setattr(subprocess, "run", invoke)


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
    assert "not distinct advisory counts" in report
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
            "No known vulnerabilities reported by npm.",
        ),
        (
            {
                "metadata": {"vulnerabilities": {"high": 1, "total": 1}},
                "vulnerabilities": {"parent": {"via": ["child"]}},
            },
            "npm supplied no direct advisory details",
        ),
    ],
)
def test_remaining_summary_reports_unavailable_and_incomplete_evidence(data, expected):
    assert expected in format_remaining_audit(data, {})


def test_workflow_dispatch_uses_the_configured_project():
    workflow = (
        Path(__file__).parents[1] / "workflows/dependency-audit.yml"
    ).read_text()

    assert "cron: '0 2 30 1 *'" in workflow
    assert "  workflow_dispatch:\n" in workflow
    assert "inputs.directory" not in workflow
    assert "NPM_PROJECT: website" in workflow


def test_publisher_uses_the_audited_revision_and_default_branch_base():
    workflow = yaml.safe_load(
        (Path(__file__).parents[1] / "workflows/dependency-audit.yml").read_text()
    )
    for job in ("audit", "pull-request"):
        checkout = next(
            step
            for step in workflow["jobs"][job]["steps"]
            if step.get("uses", "").startswith("actions/checkout@")
        )
        assert checkout["with"]["ref"] == "${{ github.sha }}"
    publisher = workflow["jobs"]["pull-request"]["steps"][-1]
    assert (
        publisher["env"]["BASE_BRANCH"]
        == "${{ github.event.repository.default_branch }}"
    )
    assert '--base "$BASE_BRANCH"' in publisher["run"]


@pytest.mark.parametrize("failure", [None, "fetch", "checkout", "changed", "compare"])
def test_publisher_refreshes_base_and_rejects_stale_or_unreadable_inputs(
    tmp_path, failure
):
    workflow = yaml.safe_load(
        (Path(__file__).parents[1] / "workflows/dependency-audit.yml").read_text()
    )
    steps = workflow["jobs"]["pull-request"]["steps"]
    guard = next(
        step for step in steps if step.get("name") == "Verify audit dependency state"
    )
    guard_index = steps.index(guard)
    assert all(
        "download-artifact@" not in step.get("uses", "") for step in steps[:guard_index]
    )
    executable = tmp_path / "git"
    executable.write_text(
        "#!/bin/sh\n"
        'printf "%s\\n" "$*" >> "$COMMAND_LOG"\n'
        'case "$1:$FAILURE" in\n'
        "  fetch:fetch|checkout:checkout) exit 2 ;;\n"
        "  diff:changed) exit 1 ;;\n"
        "  diff:compare) exit 2 ;;\n"
        "esac\n"
        "exit 0\n"
    )
    executable.chmod(0o755)
    command_log = tmp_path / "commands.log"
    result = subprocess.run(
        ["bash", "-c", guard["run"]],
        env=dict(
            os.environ,
            PATH=f"{tmp_path}{os.pathsep}{os.environ['PATH']}",
            COMMAND_LOG=str(command_log),
            FAILURE=failure or "",
            AUDIT_SHA="audited-revision",
            BASE_BRANCH="main",
            NPM_PROJECT="website",
        ),
        capture_output=True,
        text=True,
    )
    commands = command_log.read_text().splitlines()
    assert commands[0] == "fetch --no-tags origin main:refs/remotes/origin/main"
    assert (result.returncode == 0) == (failure is None)
    if failure != "fetch":
        assert commands[1] == "checkout --detach refs/remotes/origin/main"
    if failure in (None, "changed", "compare"):
        assert commands[-1] == (
            "diff --quiet audited-revision HEAD -- website/package.json "
            "website/package-lock.json website/pnpm-lock.yaml website/pnpm-workspace.yaml"
        )


@pytest.fixture
def npm_project(tmp_path):
    (tmp_path / "package.json").write_text(
        json.dumps({"dependencies": {"renderer": "1.0.0"}})
    )
    (tmp_path / "package-lock.json").write_text('{"lockfileVersion": 3}')
    return tmp_path


def test_summary_precedes_collapsed_full_audit(npm_project, monkeypatch):
    fake_npm(monkeypatch)

    report = prepare(npm_project)
    summary, details = report.split("<details>")

    assert "renderer: `1.0.0` → `2.0.0`" in summary
    assert "## Remaining advisories" in summary
    assert "## Production build\n\nPassed." in summary
    assert summary.index("Security findings") < summary.index("Other stable")
    assert "### Before" not in summary and "### After" not in summary
    assert "### Before" in details and "### After" in details
    assert details.endswith("</details>\n")
    assert not (npm_project / "dependency-audit.md").exists()


@pytest.mark.parametrize("install, build", [(1, 0), (0, 1)])
def test_summary_keeps_failed_validation_visible(
    npm_project, monkeypatch, install, build
):
    fake_npm(monkeypatch, install=install, build=build, audit_error=True)

    summary = prepare(npm_project).split("<details>")[0]

    assert "Audit unavailable" in summary
    assert "No known vulnerabilities" not in summary
    assert "Passed." not in summary
    assert "failed" in summary.lower()


def test_summary_marks_security_fix_unconfirmed_when_initial_audit_is_unavailable(
    pnpm_project, monkeypatch
):
    fixes = 0

    def invoke(command, *, cwd, **kwargs):
        nonlocal fixes
        args = command[5:]
        if args[:2] == ["audit", "--json"]:
            if fixes:
                return subprocess.CompletedProcess(
                    command,
                    0,
                    json.dumps(
                        {
                            "metadata": {"vulnerabilities": {"total": 0}},
                            "advisories": {},
                        }
                    ),
                    "",
                )
            return subprocess.CompletedProcess(
                command,
                1,
                json.dumps(
                    {"metadata": {"vulnerabilities": {"high": 1}}, "advisories": []}
                ),
                "",
            )
        if args[:2] == ["audit", "--fix=update"]:
            fixes += 1
            lockfile = cwd / "pnpm-lock.yaml"
            lock = yaml.safe_load(lockfile.read_bytes())
            lock["packages"] = {"renderer@1.0.1": {}}
            lockfile.write_text(yaml.safe_dump(lock))
        elif args[0] == "view":
            return subprocess.CompletedProcess(command, 0, '"1.0.0"', "")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(subprocess, "run", invoke)
    summary = prepare(pnpm_project).split("<details>")[0]

    assert "Initial audit evidence was unavailable" in summary
    assert "retained security-fix changes are unconfirmed" in summary
    assert "No upgrades to affected dependencies resolved." not in summary
    assert "No additional tool errors recorded." not in summary
    assert (
        "## Remaining advisories\n\nNo known vulnerabilities reported by pnpm."
        in summary
    )


@pytest.mark.parametrize("mutation", ["audit-fix", "install", "ci", "build", "missing"])
def test_failed_mutation_restores_valid_files_and_reports_partial_work(
    npm_project, monkeypatch, mutation
):
    calls = {"audit-fix": 0}

    def invoke(command, *, cwd, **kwargs):
        args = command[4:]
        stdout, code = "", 0
        if args[0] == "view":
            stdout = '"2.0.0"'
        elif args[:2] == ["audit", "fix"]:
            calls["audit-fix"] += 1
            if mutation in {"audit-fix", "missing"} and calls["audit-fix"] == 1:
                if mutation == "missing":
                    (cwd / "package-lock.json").unlink()
                else:
                    (cwd / "package-lock.json").write_text("{")
                code = 124
        elif args[0] == "install":
            (cwd / "package-lock.json").write_text(
                "{" if mutation == "install" else '{"candidate": true}'
            )
            code = 0
        elif args[0] == "ci":
            if mutation == "ci":
                (cwd / "package.json").write_text("{")
                code = 1
        elif args[:2] == ["run", "build"]:
            if mutation == "build":
                (cwd / "package.json").write_text("{")
                code = 1
        elif args[:2] == ["audit", "--json"]:
            code = 1
            stdout = json.dumps(
                {
                    "metadata": {"vulnerabilities": {"total": 0}},
                    "vulnerabilities": {},
                }
            )
        return subprocess.CompletedProcess(command, code, stdout, "")

    monkeypatch.setattr(subprocess, "run", invoke)

    report = prepare(npm_project)

    json.loads((npm_project / "package.json").read_text())
    json.loads((npm_project / "package-lock.json").read_text())
    assert "restored" in report
    assert "did not claim its changes" in report or "failed" in report.lower()
    if mutation == "install":
        assert "renderer: `1.0.0` → `2.0.0`" not in report


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
                "resolutionMode": "highest",
            }
        )
    )
    return tmp_path


@pytest.mark.parametrize("failure", [None, "stable", "policy", "frozen"])
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
            exclusions = policy["minimumReleaseAgeExclude"]
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
        return subprocess.CompletedProcess(command, code, stdout, "")

    monkeypatch.setattr(subprocess, "run", invoke)
    report = prepare(pnpm_project)
    policy = yaml.safe_load(workspace.read_text())
    assert policy["minimumReleaseAge"] == 14400
    assert policy["blockExoticSubdeps"] and policy["strictDepBuilds"]
    assert policy["allowBuilds"] == {"core-js": False}
    assert policy["overrides"] == {"other": "3.0.0"}
    assert commands.index(
        ["audit", "--fix=update", "--audit-level", "info", "--ignore-scripts"]
    ) < next(i for i, args in enumerate(commands) if args[0] == "view")
    assert "--force" not in str(commands)
    assert "pnpm" in report and "Render bug" in report
    assert "Registry advisory counts" in report
    assert "Full before/after pnpm audit" in report
    if failure == "stable":
        assert policy["minimumReleaseAgeExclude"] == ["other@3.0.0", "renderer@1.0.1"]
        assert "renderer: `^1.0.0` → `2.0.0`" not in report
        assert "renderer: `1.0.0` → `1.0.1`" in report
    if failure == "policy":
        assert "restored" in report and "exit 124" in report
    if failure == "frozen":
        assert "Not run: pnpm frozen install failed" in report
        assert ["run", "build"] not in commands


def test_info_advisory_is_reported_and_fix_attempt_includes_info(
    pnpm_project, monkeypatch
):
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
        commands.append(command[5:])
        return subprocess.CompletedProcess(command, 1, json.dumps(response), "")

    monkeypatch.setattr(subprocess, "run", invoke)
    data = audit(pnpm_project)
    audit_module["fix_security"](pnpm_project, float("inf"))
    assert commands[:2] == [
        ["audit", "--json", "--audit-level", "info"],
        ["audit", "--fix=update", "--audit-level", "info", "--ignore-scripts"],
    ]
    assert commands[2][:4] == [
        "install",
        "--lockfile-only",
        "--no-frozen-lockfile",
        "--ignore-scripts",
    ]
    lock = audit_module["valid_snapshot"](pnpm_project)[3]
    for report in (format_remaining_audit(data, lock), format_audit(data, lock)):
        for detail in (
            "info",
            "Informational renderer notice",
            "https://github.com/advisories/GHSA-info",
            "<1.0.1",
            "1.0.0",
        ):
            assert detail in report


@pytest.mark.parametrize("mutation", ["severity", "via", "nodes", "fixAvailable"])
def test_audit_rejects_malformed_npm_vulnerability_details(
    npm_project, monkeypatch, mutation
):
    detail: Any = {
        "severity": "high",
        "range": "<1.0.1",
        "nodes": ["node_modules/renderer"],
        "via": [
            {
                "title": "Render bug",
                "url": "https://github.com/advisories/GHSA-render",
                "severity": "high",
                "range": "<1.0.1",
            }
        ],
        "fixAvailable": False,
    }
    if mutation == "severity":
        del detail["severity"]
    elif mutation == "via":
        del detail["via"][0]["range"]
    elif mutation == "nodes":
        detail["nodes"] = [None]
    else:
        detail["fixAvailable"] = {"name": 7}

    response = {
        "metadata": {"vulnerabilities": {"high": 1, "total": 1}},
        "vulnerabilities": {"renderer": detail},
    }
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda command, **kwargs: subprocess.CompletedProcess(
            command, 1, json.dumps(response), ""
        ),
    )

    result = audit(npm_project)

    assert isinstance(result, str) and "unavailable" in result.lower()
    assert "unavailable" in format_audit(result, {}).lower()
    assert "unavailable" in format_remaining_audit(result, {}).lower()


@pytest.mark.parametrize(
    ("location", "severity"),
    [
        ("vulnerability", []),
        ("vulnerability", {}),
        ("via", []),
        ("via", {}),
    ],
)
def test_audit_rejects_non_scalar_npm_severity(
    npm_project, monkeypatch, location, severity
):
    detail: Any = {
        "severity": "high",
        "range": "<1.0.1",
        "nodes": ["node_modules/renderer"],
        "via": [
            {
                "title": "Render bug",
                "url": "https://github.com/advisories/GHSA-render",
                "severity": "high",
                "range": "<1.0.1",
            }
        ],
        "fixAvailable": False,
    }
    if location == "vulnerability":
        detail["severity"] = severity
    else:
        detail["via"][0]["severity"] = severity
    response = {
        "metadata": {"vulnerabilities": {"high": 1, "total": 1}},
        "vulnerabilities": {"renderer": detail},
    }
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda command, **kwargs: subprocess.CompletedProcess(
            command, 1, json.dumps(response), ""
        ),
    )

    result = audit(npm_project)

    assert isinstance(result, str) and "unavailable" in result.lower()


@pytest.mark.parametrize(
    "counts",
    [
        {"high": 2, "total": 2},
        {"low": 1, "total": 1},
    ],
)
def test_audit_rejects_npm_count_mismatches(npm_project, monkeypatch, counts):
    response = {
        "metadata": {"vulnerabilities": counts},
        "vulnerabilities": {
            "renderer": {
                "severity": "high",
                "range": "<1.0.1",
                "nodes": ["node_modules/renderer"],
                "via": [
                    {
                        "title": "Render bug",
                        "url": "https://github.com/advisories/GHSA-render",
                        "severity": "high",
                        "range": "<1.0.1",
                    }
                ],
                "fixAvailable": False,
            }
        },
    }
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda command, **kwargs: subprocess.CompletedProcess(
            command, 1, json.dumps(response), ""
        ),
    )

    result = audit(npm_project)

    assert isinstance(result, str) and "unavailable" in result.lower()


def test_audit_preserves_valid_npm_propagated_findings(npm_project, monkeypatch):
    response = {
        "metadata": {"vulnerabilities": {"high": 2, "total": 2}},
        "vulnerabilities": {
            "renderer": {
                "severity": "high",
                "range": "<1.0.1",
                "nodes": ["node_modules/renderer"],
                "via": [
                    {
                        "title": "Render bug",
                        "url": "https://github.com/advisories/GHSA-render",
                        "severity": "high",
                        "range": "<1.0.1",
                    }
                ],
                "fixAvailable": False,
            },
            "application": {
                "severity": "high",
                "range": "*",
                "nodes": ["node_modules/application"],
                "via": ["renderer"],
                "fixAvailable": False,
            },
        },
    }
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda command, **kwargs: subprocess.CompletedProcess(
            command, 1, json.dumps(response), ""
        ),
    )

    result = audit(npm_project)

    assert isinstance(result, dict)
    assert result["vulnerabilities"]["application"]["via"] == ["renderer"]
    assert "GHSA-render" in format_remaining_audit(result, {})


@pytest.mark.parametrize("reverse", [False, True])
def test_pnpm_group_summary_is_order_independent(pnpm_project, monkeypatch, reverse):
    advisories = {
        "low": {
            "module_name": "renderer",
            "severity": "low",
            "title": "Low issue",
            "url": "https://github.com/advisories/GHSA-low",
            "vulnerable_versions": "<1.0.1",
            "patched_versions": ">=1.0.1",
            "findings": [{"version": "1.0.0"}],
        },
        "critical": {
            "module_name": "renderer",
            "severity": "critical",
            "title": "Critical issue",
            "url": "https://github.com/advisories/GHSA-critical",
            "vulnerable_versions": ">=2 <2.0.1",
            "patched_versions": ">=2.0.1",
            "findings": [{"version": "1.0.0"}],
        },
    }
    if reverse:
        advisories = dict(reversed(tuple(advisories.items())))
    response = {
        "metadata": {"vulnerabilities": {"low": 1, "critical": 1, "total": 2}},
        "advisories": advisories,
    }
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda command, **kwargs: subprocess.CompletedProcess(
            command, 1, json.dumps(response), ""
        ),
    )

    result = audit(pnpm_project)

    assert isinstance(result, dict)
    summary = result["vulnerabilities"]["renderer"]
    assert summary["severity"] == "critical"
    assert summary["range"] == "<1.0.1 || >=2 <2.0.1"


@pytest.mark.parametrize("exit_code", [0, 1])
@pytest.mark.parametrize(
    "operation, field, value",
    [
        ("initial-audit", "minimumReleaseAge", 1),
        ("initial-fix", "overrides", {"other": "changed"}),
        ("view", "allowBuilds", {}),
        ("install", "blockExoticSubdeps", False),
        ("followup-fix", "strictDepBuilds", False),
        ("frozen", "minimumReleaseAgeExclude", ["unrelated@9.0.0"]),
        ("build", "resolutionMode", "lowest-direct"),
        ("final-audit", "audit", {"ignore": ["GHSA-hidden"]}),
    ],
)
def test_valid_policy_mutation_restores_all_package_files(
    pnpm_project, monkeypatch, operation, field, value, exit_code
):
    workspace = pnpm_project / "pnpm-workspace.yaml"
    files = {
        name: (pnpm_project / name).read_bytes()
        for name in ("package.json", "pnpm-lock.yaml", "pnpm-workspace.yaml")
    }
    audits = fixes = 0
    mutated = False

    def invoke(command, *, cwd, **kwargs):
        nonlocal audits, fixes, mutated
        args = command[5:]
        stdout, boundary = "", None
        if args[:2] == ["audit", "--json"]:
            audits += 1
            boundary = "initial-audit" if audits == 1 else "final-audit"
            stdout = json.dumps(
                {"metadata": {"vulnerabilities": {"total": 0}}, "advisories": {}}
            )
        elif args[:2] == ["audit", "--fix=update"]:
            fixes += 1
            boundary = "initial-fix" if fixes == 1 else "followup-fix"
        elif args[0] == "view":
            boundary, stdout = "view", '"1.0.0"'
        elif "--lockfile-only" in args:
            boundary = "install"
        elif args == ["install", "--frozen-lockfile"]:
            boundary = "frozen"
        elif args == ["run", "build"]:
            boundary = "build"
        if boundary == operation and not mutated:
            policy = yaml.safe_load(workspace.read_text())
            policy[field] = value
            workspace.write_text(yaml.safe_dump(policy))
            (cwd / "package.json").write_text(
                json.dumps({"packageManager": "pnpm@11.21.0", "dependencies": {}})
            )
            lockfile = cwd / "pnpm-lock.yaml"
            lock = yaml.safe_load(lockfile.read_text())
            lock["packages"] = {"unrelated@9.0.0": {}}
            lockfile.write_text(yaml.safe_dump(lock))
            mutated = True
            return subprocess.CompletedProcess(command, exit_code, stdout, "")
        return subprocess.CompletedProcess(command, 0, stdout, "")

    monkeypatch.setattr(subprocess, "run", invoke)
    report = prepare(pnpm_project)

    assert mutated
    for name, content in files.items():
        assert (pnpm_project / name).read_bytes() == content
    assert "changed protected pnpm policy" in report


@pytest.mark.parametrize("phase", ["initial", "followup"])
@pytest.mark.parametrize(
    "addition, accepted, retained",
    [
        ("renderer@1.0.1", True, True),
        ("renderer@2.0.0", True, False),
        ("@scope/safe@2.0.0", True, False),
        ("unrelated@3.0.0", True, False),
        ("renderer@*", False, False),
        ("renderer@1.0.1 || 2.0.0", True, True),
        (None, False, False),
    ],
)
def test_security_exclusions_require_each_fix_complete_normalized_lock_delta(
    pnpm_project, monkeypatch, phase, addition, accepted, retained
):
    workspace = pnpm_project / "pnpm-workspace.yaml"
    lockfile = pnpm_project / "pnpm-lock.yaml"
    original_policy = yaml.safe_load(workspace.read_text())
    baseline_packages = {
        "renderer@1.0.0": {},
        "renderer@2.0.0": {},
        "@scope/safe@2.0.0(peer@1.0.0)": {},
    }
    if phase == "initial":
        lock = yaml.safe_load(lockfile.read_text())
        lock["packages"] = baseline_packages
        lockfile.write_text(yaml.safe_dump(lock))
    fixes = 0

    def invoke(command, *, cwd, **kwargs):
        nonlocal fixes
        args = command[5:]
        stdout = ""
        if args[:2] == ["audit", "--json"]:
            stdout = json.dumps(
                {"metadata": {"vulnerabilities": {"total": 0}}, "advisories": {}}
            )
        elif args[0] == "view":
            stdout = '"1.0.0"'
        elif "--lockfile-only" in args and phase == "followup":
            lock = yaml.safe_load(lockfile.read_text())
            lock["packages"] = baseline_packages
            lockfile.write_text(yaml.safe_dump(lock))
        elif args[:2] == ["audit", "--fix=update"]:
            fixes += 1
            if fixes == (1 if phase == "initial" else 2):
                lock = yaml.safe_load(lockfile.read_text())
                lock["packages"].pop("renderer@1.0.0")
                lock["packages"]["renderer@1.0.1"] = {}
                lock["packages"].pop("@scope/safe@2.0.0(peer@1.0.0)")
                lock["packages"]["@scope/safe@2.0.0(peer@2.0.0)"] = {}
                lockfile.write_text(yaml.safe_dump(lock))
                policy = yaml.safe_load(workspace.read_text())
                if addition is None:
                    policy["minimumReleaseAgeExclude"] = []
                else:
                    policy["minimumReleaseAgeExclude"].append(addition)
                workspace.write_text(yaml.safe_dump(policy))
        return subprocess.CompletedProcess(command, 0, stdout, "")

    monkeypatch.setattr(subprocess, "run", invoke)
    report = prepare(pnpm_project)
    policy = yaml.safe_load(workspace.read_text())
    if retained:
        original_policy["minimumReleaseAgeExclude"].append("renderer@1.0.1")
    assert policy == original_policy
    packages = yaml.safe_load(lockfile.read_text())["packages"]
    assert ("renderer@1.0.1" in packages) == accepted
    assert ("changed protected pnpm policy" in report) == (not accepted)


@pytest.mark.parametrize("security_fix", [False, True])
@pytest.mark.parametrize(
    "union, permitted",
    [
        ("renderer@1.0.0 || 1.0.1", True),
        ("renderer@1.0.1", False),
        ("renderer@1.0.0 || *", False),
        ("renderer@1.0.0 || 2.0.0", True),
        ("renderer@1.0.0 || ^1.0.1", False),
    ],
)
def test_pnpm_merged_exclusions_preserve_existing_exact_versions(
    pnpm_project, security_fix, union, permitted
):
    workspace = pnpm_project / "pnpm-workspace.yaml"
    lockfile = pnpm_project / "pnpm-lock.yaml"
    policy = yaml.safe_load(workspace.read_text())
    policy["minimumReleaseAgeExclude"].append("renderer@1.0.0")
    workspace.write_text(yaml.safe_dump(policy))
    original_policy = workspace.read_text().replace(
        "minimumReleaseAgeExclude:\n- other@3.0.0\n- renderer@1.0.0\n",
        "# Preserve the release-age policy.\n"
        "minimumReleaseAgeExclude: # Existing policy.\n"
        "- 'other@3.0.0' # Existing rationale.\n"
        "- 'renderer@1.0.0' # Baseline pin.\n",
    )
    workspace.write_text(original_policy)
    lock = yaml.safe_load(lockfile.read_text())
    lock["packages"]["renderer@2.0.0"] = {}
    lockfile.write_text(yaml.safe_dump(lock))
    snapshot = audit_module["valid_snapshot"](pnpm_project)
    policy["minimumReleaseAgeExclude"] = ["other@3.0.0", union]
    workspace.write_text(yaml.safe_dump(policy))
    lock["packages"].pop("renderer@1.0.0")
    lock["packages"]["renderer@1.0.1"] = {}
    lockfile.write_text(yaml.safe_dump(lock))
    notes = []

    restored = audit_module["restore_invalid_state"](
        pnpm_project, snapshot, notes, "Test command", security_fix=security_fix
    )

    accepted = permitted and security_fix
    assert restored == (not accepted)
    if accepted:
        expected_policy_text = original_policy
        if union == "renderer@1.0.0 || 1.0.1":
            expected_policy_text = original_policy.replace(
                "- 'renderer@1.0.0' # Baseline pin.\n",
                "- 'renderer@1.0.0' # Baseline pin.\n- renderer@1.0.1\n",
            )
        assert workspace.read_text() == expected_policy_text
        expected_policy = yaml.safe_load(expected_policy_text)
        baseline_policy = yaml.safe_load(snapshot[1]["pnpm-workspace.yaml"])
        expected_exclusions = ["other@3.0.0", "renderer@1.0.0"]
        if union == "renderer@1.0.0 || 1.0.1":
            expected_exclusions.append("renderer@1.0.1")
        assert expected_policy["minimumReleaseAgeExclude"] == expected_exclusions
        expected_policy.pop("minimumReleaseAgeExclude")
        baseline_policy.pop("minimumReleaseAgeExclude")
        assert expected_policy == baseline_policy
        assert yaml.safe_load(lockfile.read_text()) == lock
        assert bool(notes) == (union == "renderer@1.0.0 || 2.0.0")
    else:
        assert (pnpm_project / "package.json").read_bytes() == snapshot[0]
        for name, content in snapshot[1].items():
            assert (pnpm_project / name).read_bytes() == content
        assert "changed protected pnpm policy" in notes[0]


def test_pnpm_shared_workspace_is_rejected(pnpm_project):
    workspace = pnpm_project / "pnpm-workspace.yaml"
    policy = yaml.safe_load(workspace.read_text())
    policy["packages"] = [".", "../other"]
    workspace.write_text(yaml.safe_dump(policy))
    with pytest.raises(ValueError, match="one deployment"):
        prepare(pnpm_project)


@pytest.mark.parametrize("fixture_name", ["npm_project", "pnpm_project"])
@pytest.mark.parametrize("exit_code", [0, 1])
@pytest.mark.parametrize(
    "operation", ["initial-audit", "view", "frozen", "build", "final-audit"]
)
@pytest.mark.parametrize("mutated_file", ["package.json", "lock"])
def test_nonmutating_commands_preserve_exact_package_files(
    request, monkeypatch, fixture_name, exit_code, operation, mutated_file
):
    project = request.getfixturevalue(fixture_name)
    pnpm = fixture_name == "pnpm_project"
    lock_name = "pnpm-lock.yaml" if pnpm else "package-lock.json"
    files = {
        name: (project / name).read_bytes()
        for name in (
            "package.json",
            lock_name,
            *(["pnpm-workspace.yaml"] if pnpm else []),
        )
    }
    audits = 0
    mutated = False

    def invoke(command, *, cwd, **kwargs):
        nonlocal audits, mutated
        args = command[5:] if pnpm else command[4:]
        stdout, boundary = "", None
        if args[:2] == ["audit", "--json"]:
            audits += 1
            boundary = "initial-audit" if audits == 1 else "final-audit"
            stdout = json.dumps(
                {
                    "metadata": {"vulnerabilities": {"total": 0}},
                    "advisories" if pnpm else "vulnerabilities": {},
                }
            )
        elif args[0] == "view":
            boundary, stdout = "view", '"1.0.0"'
        elif args[0] == "ci" or args == ["install", "--frozen-lockfile"]:
            boundary = "frozen"
        elif args == ["run", "build"]:
            boundary = "build"
        if boundary == operation and not mutated:
            if mutated_file == "package.json":
                manifest = json.loads((project / "package.json").read_bytes())
                manifest["dependencies"]["renderer"] = "9.9.9"
                (project / "package.json").write_text(json.dumps(manifest))
            elif pnpm:
                lock = yaml.safe_load((project / lock_name).read_bytes())
                lock["packages"] = {"renderer@9.9.9": {}}
                (project / lock_name).write_text(yaml.safe_dump(lock))
            else:
                (project / lock_name).write_text(
                    json.dumps(
                        {
                            "lockfileVersion": 3,
                            "packages": {"node_modules/renderer": {"version": "9.9.9"}},
                        }
                    )
                )
            mutated = True
            return subprocess.CompletedProcess(command, exit_code, stdout, "")
        return subprocess.CompletedProcess(command, 0, stdout, "")

    monkeypatch.setattr(subprocess, "run", invoke)
    report = prepare(project)

    assert mutated
    for name, content in files.items():
        assert (project / name).read_bytes() == content
    assert "restored" in report
    if operation in {"frozen", "build"}:
        assert "## Production build\n\nPassed." not in report
    if operation == "final-audit":
        assert "## Remaining advisories\n\nAudit unavailable" in report


@pytest.mark.parametrize("fixture_name", ["npm_project", "pnpm_project"])
@pytest.mark.parametrize("container", [None, [], {}])
def test_audit_missing_or_inconsistent_advisory_evidence_is_unavailable(
    request, monkeypatch, fixture_name, container
):
    project = request.getfixturevalue(fixture_name)
    key = "advisories" if fixture_name == "pnpm_project" else "vulnerabilities"
    response = {"metadata": {"vulnerabilities": {"high": 1}}}
    if container is not None:
        response[key] = container

    def invoke(command, *, cwd, **kwargs):
        return subprocess.CompletedProcess(command, 1, json.dumps(response), "")

    monkeypatch.setattr(subprocess, "run", invoke)
    data = audit(project)
    assert isinstance(data, str) and "Audit unavailable" in data
    for formatter in (format_remaining_audit, format_audit):
        assert "Audit unavailable" in formatter(data, {})
        assert "No known vulnerabilities" not in formatter(data, {})


def test_pnpm_reference_policy_and_publisher_include_workspace():
    templates = Path(__file__).parents[1] / "workflows"
    policy = yaml.safe_load(
        (Path(__file__).parents[2] / "website/pnpm-workspace.yaml").read_text()
    )
    assert policy["minimumReleaseAge"] == 14400
    assert policy["blockExoticSubdeps"] and policy["strictDepBuilds"]
    assert policy["allowBuilds"] == {
        "core-js": False,
        "core-js-pure": False,
        "fsevents": False,
    }
    workflow = (templates / "dependency-audit.yml").read_text()
    assert "${{ env.NPM_PROJECT }}/pnpm-workspace.yaml" in workflow
    assert (
        "for file in package-lock.json pnpm-lock.yaml pnpm-workspace.yaml" in workflow
    )
    publisher = yaml.safe_load(workflow)["jobs"]["pull-request"]
    assert all("corepack" not in step.get("run", "") for step in publisher["steps"])


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
        (Path(__file__).parents[1] / "workflows/dependency-audit.yml").read_text()
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

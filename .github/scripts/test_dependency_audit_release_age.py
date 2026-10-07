# SPDX-FileCopyrightText: Contributors to Hydra
# SPDX-License-Identifier: MIT
import json
import runpy
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml

module = runpy.run_path(str(Path(__file__).with_name("dependency_audit.py")))


@pytest.fixture
def project(tmp_path):
    (tmp_path / "package.json").write_text(
        json.dumps(
            {"packageManager": "pnpm@11.21.0", "dependencies": {"renderer": "^1.0.0"}}
        )
    )
    (tmp_path / "pnpm-workspace.yaml").write_text(
        "packages: ['.']\nminimumReleaseAge: 14400\n"
        "blockExoticSubdeps: true\nstrictDepBuilds: true\n"
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
    return tmp_path


@pytest.mark.parametrize(
    "eligible, fixed, expected",
    [
        ("1.5.0", None, "1.5.0"),
        ("1.0.5", "1.0.6", "^1.0.0"),
        ("1.0.7", "1.0.6", "1.0.7"),
    ],
)
def test_stable_selection_preserves_release_age_and_direct_security_fix(
    project, monkeypatch, eligible, fixed, expected
):
    now = datetime.now(timezone.utc)
    fixes = 0

    def invoke(command, *, cwd, **kwargs):
        nonlocal fixes
        args = command[5:]
        stdout = ""
        if args[:2] == ["audit", "--json"]:
            stdout = json.dumps(
                {"metadata": {"vulnerabilities": {"total": 0}}, "advisories": {}}
            )
        elif args[:2] == ["audit", "--fix=update"]:
            fixes += 1
            if fixed and fixes == 1:
                lock = yaml.safe_load((cwd / "pnpm-lock.yaml").read_bytes())
                lock["importers"]["."] = {
                    "dependencies": {"renderer": {"version": fixed + "(peer@1.0.0)"}}
                }
                lock["packages"] = {"renderer@" + fixed: {}}
                (cwd / "pnpm-lock.yaml").write_text(yaml.safe_dump(lock))
        elif args[0] == "view":
            stdout = (
                json.dumps(
                    {
                        eligible: (now - timedelta(days=11)).isoformat(),
                        "2.0.0": (now - timedelta(days=1)).isoformat(),
                        "3.0.0": (now - timedelta(days=20)).isoformat(),
                        "3.0.0-beta.1": (now - timedelta(days=20)).isoformat(),
                    }
                )
                if args[-2] == "time"
                else '"2.0.0"'
            )
        return subprocess.CompletedProcess(command, 0, stdout, "")

    monkeypatch.setattr(subprocess, "run", invoke)
    module["prepare"](project)
    manifest = json.loads((project / "package.json").read_bytes())
    assert manifest["dependencies"]["renderer"] == expected


@pytest.mark.parametrize("release_data", [{}, "invalid", {"1.5.0": "not a timestamp"}])
def test_unverifiable_release_age_retains_current_specifier(
    project, monkeypatch, release_data
):
    def invoke(command, **kwargs):
        args = command[5:]
        stdout = ""
        if args[:2] == ["audit", "--json"]:
            stdout = '{"metadata":{"vulnerabilities":{"total":0}},"advisories":{}}'
        elif args[0] == "view":
            stdout = json.dumps(release_data) if args[-2] == "time" else '"2.0.0"'
        return subprocess.CompletedProcess(command, 0, stdout, "")

    monkeypatch.setattr(subprocess, "run", invoke)
    report = module["prepare"](project)
    assert json.loads((project / "package.json").read_bytes())["dependencies"] == {
        "renderer": "^1.0.0"
    }
    assert "retained" in report.lower()


def add_direct_lock(project, version="1.0.0", specifier="^1.0.0"):
    lockfile = project / "pnpm-lock.yaml"
    lock = yaml.safe_load(lockfile.read_bytes())
    lock["importers"]["."] = {
        "dependencies": {"renderer": {"specifier": specifier, "version": version}}
    }
    lock["packages"] = {f"renderer@{version}": {}}
    lockfile.write_text(yaml.safe_dump(lock))


@pytest.mark.parametrize("phase", ["initial", "follow-up"])
def test_security_fix_restores_direct_downgrade_in_each_phase(
    project, monkeypatch, phase
):
    add_direct_lock(project)
    original = {
        name: (project / name).read_bytes()
        for name in ("package.json", "pnpm-lock.yaml", "pnpm-workspace.yaml")
    }
    target_fix = 1 if phase == "initial" else 2
    fixes = 0

    def invoke(command, *, cwd, **kwargs):
        nonlocal fixes
        args = command[5:]
        if args[:2] == ["audit", "--json"]:
            stdout = json.dumps(
                {"metadata": {"vulnerabilities": {"total": 0}}, "advisories": {}}
            )
        elif args[:2] == ["audit", "--fix=update"]:
            fixes += 1
            if fixes == target_fix:
                manifest = json.loads((cwd / "package.json").read_bytes())
                manifest["dependencies"]["renderer"] = "^0.9.0"
                (cwd / "package.json").write_text(json.dumps(manifest) + "\n")
                lock = yaml.safe_load((cwd / "pnpm-lock.yaml").read_bytes())
                lock["importers"]["."]["dependencies"]["renderer"]["version"] = "0.9.0"
                lock["packages"] = {"renderer@0.9.0": {}}
                (cwd / "pnpm-lock.yaml").write_text(yaml.safe_dump(lock))
            stdout = ""
        elif args[0] == "view":
            stdout = '"1.0.0"'
        else:
            stdout = ""
        return subprocess.CompletedProcess(command, 0, stdout, "")

    monkeypatch.setattr(subprocess, "run", invoke)
    report = module["prepare"](project)

    for name, content in original.items():
        assert (project / name).read_bytes() == content
    operation = "Initial" if phase == "initial" else "Follow-up"
    assert f"{operation} security fix" in report
    assert "lowered a known direct pnpm dependency" in report


@pytest.mark.parametrize("phase", ["initial", "follow-up"])
@pytest.mark.parametrize("specifier", ["^1.0.0", "~1.0.0"])
def test_security_fix_restores_manifest_only_downgrade_in_each_phase(
    project, monkeypatch, phase, specifier
):
    add_direct_lock(project, specifier=specifier)
    original = {
        name: (project / name).read_bytes()
        for name in ("package.json", "pnpm-lock.yaml", "pnpm-workspace.yaml")
    }
    target_fix = 1 if phase == "initial" else 2
    fixes = 0

    def invoke(command, *, cwd, **kwargs):
        nonlocal fixes
        args = command[5:]
        if args[:2] == ["audit", "--json"]:
            stdout = json.dumps(
                {"metadata": {"vulnerabilities": {"total": 0}}, "advisories": {}}
            )
        elif args[:2] == ["audit", "--fix=update"]:
            fixes += 1
            if fixes == target_fix:
                manifest = json.loads((cwd / "package.json").read_bytes())
                manifest["dependencies"]["renderer"] = f"{specifier[0]}0.9.0"
                (cwd / "package.json").write_text(json.dumps(manifest) + "\n")
            stdout = ""
        elif args[0] == "view":
            stdout = '"1.0.0"'
        else:
            stdout = ""
        return subprocess.CompletedProcess(command, 0, stdout, "")

    monkeypatch.setattr(subprocess, "run", invoke)
    report = module["prepare"](project)

    for name, content in original.items():
        assert (project / name).read_bytes() == content
    operation = "Initial" if phase == "initial" else "Follow-up"
    assert f"{operation} security fix" in report
    assert "lowered a known direct pnpm dependency" in report


def test_security_fix_restores_direct_lock_only_downgrade(project):
    add_direct_lock(project)
    snapshot = module["valid_snapshot"](project)
    lockfile = project / "pnpm-lock.yaml"
    lock = yaml.safe_load(lockfile.read_bytes())
    lock["importers"]["."]["dependencies"]["renderer"]["version"] = "0.9.0"
    lock["packages"] = {"renderer@0.9.0": {}}
    lockfile.write_text(yaml.safe_dump(lock))
    notes = []

    assert module["restore_invalid_state"](
        project, snapshot, notes, "Follow-up security fix", security_fix=True
    )
    assert (project / "package.json").read_bytes() == snapshot[0]
    for name, content in snapshot[1].items():
        assert (project / name).read_bytes() == content
    assert "lowered a known direct pnpm dependency" in notes[0]


def test_stable_install_restores_security_snapshot_after_direct_lock_downgrade(
    project, monkeypatch
):
    add_direct_lock(project)
    lockfile = project / "pnpm-lock.yaml"
    security_lock = yaml.safe_load(lockfile.read_bytes())
    security_lock["importers"]["."]["dependencies"]["renderer"]["version"] = "1.0.5"
    security_lock["packages"] = {"renderer@1.0.5": {}}
    security_files = {
        "package.json": (project / "package.json").read_bytes(),
        "pnpm-lock.yaml": yaml.safe_dump(security_lock).encode(),
        "pnpm-workspace.yaml": (project / "pnpm-workspace.yaml").read_bytes(),
    }
    fixes = 0
    installs = 0

    def set_lock(version):
        lock = yaml.safe_load(
            lockfile.read_bytes()
            if lockfile.exists()
            else security_files["pnpm-lock.yaml"]
        )
        lock["importers"]["."]["dependencies"]["renderer"]["version"] = version
        lock["packages"] = {f"renderer@{version}": {}}
        lockfile.write_text(yaml.safe_dump(lock))

    def invoke(command, *, cwd, **kwargs):
        nonlocal fixes, installs
        args = command[5:]
        stdout, code = "", 0
        if args[:2] == ["audit", "--json"]:
            stdout = json.dumps(
                {"metadata": {"vulnerabilities": {"total": 0}}, "advisories": {}}
            )
        elif args[:2] == ["audit", "--fix=update"]:
            fixes += 1
            if fixes == 1:
                set_lock("1.0.5")
                code = 1
            else:
                code = 1
        elif args[0] == "view":
            stdout = (
                json.dumps({"1.0.6": "2020-01-01T00:00:00Z"})
                if args[-2] == "time"
                else '"1.0.6"'
            )
        elif args[0] == "install" and "--lockfile-only" in args:
            installs += 1
            if installs == 1:
                set_lock("1.0.5")
            elif installs == 2:
                set_lock("1.0.4")
            else:
                code = 1
        return subprocess.CompletedProcess(command, code, stdout, "")

    monkeypatch.setattr(subprocess, "run", invoke)
    report = module["prepare"](project)

    for name, content in security_files.items():
        assert (project / name).read_bytes() == content
    assert fixes == 1
    assert "Stable upgrade resolution failed (exit 0)" in report
    assert (
        "restored the manifest and lockfile from the initial security fix attempt"
        in report
    )

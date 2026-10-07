# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved
import json
import runpy
import subprocess
from pathlib import Path

import pytest
import yaml

module = runpy.run_path(
    str(Path(__file__).parents[1] / "templates/dependency_audit.py")
)


@pytest.fixture
def project(tmp_path):
    (tmp_path / "package.json").write_text(
        json.dumps(
            {"packageManager": "pnpm@11.21.0", "dependencies": {"parent": "1.0.0"}}
        )
    )
    (tmp_path / "pnpm-workspace.yaml").write_text(
        "packages: ['.']\nminimumReleaseAge: 14400\nblockExoticSubdeps: true\n"
        "minimumReleaseAgeExclude: ['existing@1.0.0']\n"
    )
    lock = {
        "lockfileVersion": "9.0",
        "importers": {".": {}},
        "packages": {"parent@1.0.0": {}, "child@1.0.0": {}},
        "snapshots": {"parent@1.0.0": {"dependencies": {"child": "1.0.0"}}},
    }
    (tmp_path / "pnpm-lock.yaml").write_text(yaml.safe_dump(lock))
    return tmp_path


def upgrade(project):
    lock = yaml.safe_load((project / "pnpm-lock.yaml").read_bytes())
    lock["packages"].pop("child@1.0.0")
    lock["packages"]["child@1.0.1"] = {}
    lock["snapshots"]["parent@1.0.0"]["dependencies"]["child"] = "1.0.1"
    (project / "pnpm-lock.yaml").write_text(yaml.safe_dump(lock))


def test_unused_exceptions_do_not_discard_a_resolved_patch(project):
    snapshot = module["valid_snapshot"](project)
    upgrade(project)
    policy = yaml.safe_load((project / "pnpm-workspace.yaml").read_bytes())
    policy["minimumReleaseAgeExclude"] += ["child@1.0.1", "unpublished@3.0.4"]
    (project / "pnpm-workspace.yaml").write_text(yaml.safe_dump(policy))
    notes = []
    assert not module["restore_invalid_state"](
        project, snapshot, notes, "Security fix", security_fix=True
    )
    assert "child@1.0.1" in module["valid_snapshot"](project)[3]["packages"]
    assert yaml.safe_load((project / "pnpm-workspace.yaml").read_bytes())[
        "minimumReleaseAgeExclude"
    ] == ["existing@1.0.0", "child@1.0.1"]
    assert "unpublished@3.0.4" in notes[0]


def test_used_only_exception_preserves_original_policy_and_lock(project):
    workspace = project / "pnpm-workspace.yaml"
    original = (
        "# Workspace policy rationale.\npackages: ['.']\n"
        "minimumReleaseAge: 14400 # Ten days.\nblockExoticSubdeps: true\n"
        "minimumReleaseAgeExclude: ['existing@1.0.0'] # Keep this comment.\n"
    )
    workspace.write_text(original)
    snapshot = module["valid_snapshot"](project)
    upgrade(project)
    upgraded_lock = (project / "pnpm-lock.yaml").read_bytes()
    policy = yaml.safe_load(workspace.read_bytes())
    policy["minimumReleaseAgeExclude"].append("child@1.0.1")
    workspace.write_text(yaml.safe_dump(policy))
    notes = []

    assert not module["restore_invalid_state"](
        project, snapshot, notes, "Security fix", security_fix=True
    )
    assert workspace.read_bytes() == (
        original.replace(
            "['existing@1.0.0']", "['existing@1.0.0', \"child@1.0.1\"]"
        ).encode()
    )
    repaired = module["valid_snapshot"](project)
    assert repaired is not None
    assert repaired[0] == snapshot[0]
    assert repaired[1]["pnpm-lock.yaml"] == upgraded_lock
    assert repaired[3]["packages"]["child@1.0.1"] == {
        "name": "child",
        "version": "1.0.1",
    }
    assert not notes


def test_invalid_reconstructed_policy_restores_snapshot(project, monkeypatch):
    workspace = project / "pnpm-workspace.yaml"
    original_policy = workspace.read_bytes()
    snapshot = module["valid_snapshot"](project)
    upgrade(project)
    policy = yaml.safe_load(workspace.read_bytes())
    policy["minimumReleaseAgeExclude"].append("child@1.0.1")
    workspace.write_text(yaml.safe_dump(policy))
    original_valid_snapshot = module["valid_snapshot"]
    calls = 0

    def reject_reconstructed_policy(directory):
        nonlocal calls
        calls += 1
        candidate = original_valid_snapshot(directory)
        return None if calls > 1 else candidate

    monkeypatch.setitem(
        module["restore_invalid_state"].__globals__,
        "valid_snapshot",
        reject_reconstructed_policy,
    )
    notes = []

    assert module["restore_invalid_state"](
        project, snapshot, notes, "Security fix", security_fix=True
    )
    assert workspace.read_bytes() == original_policy
    assert (project / "pnpm-lock.yaml").read_bytes() == snapshot[1]["pnpm-lock.yaml"]
    assert "reconstructed an invalid pnpm policy" in notes[0]


def test_shared_exclusion_anchor_restores_the_full_snapshot(project):
    workspace = project / "pnpm-workspace.yaml"
    original_policy = (
        "# Keep policy rationale.\npackages: ['.']\n"
        "minimumReleaseAge: 14400\nblockExoticSubdeps: true\n"
        "minimumReleaseAgeExclude: &pins ['existing@1.0.0']\n"
        "protectedPins: *pins\n"
    )
    workspace.write_text(original_policy)
    snapshot = module["valid_snapshot"](project)
    upgrade(project)
    policy = yaml.safe_load(original_policy)
    policy["minimumReleaseAgeExclude"] = policy["minimumReleaseAgeExclude"] + [
        "child@1.0.1"
    ]
    assert policy["protectedPins"] == ["existing@1.0.0"]
    workspace.write_text(yaml.safe_dump(policy))
    notes = []

    assert module["restore_invalid_state"](
        project, snapshot, notes, "Security fix", security_fix=True
    )
    for name, content in snapshot[1].items():
        assert (project / name).read_bytes() == content
    assert "restored" in notes[0]


def test_absent_exclusions_without_new_exception_accepts_lock_update(project):
    workspace = project / "pnpm-workspace.yaml"
    original_policy = (
        "# Keep policy rationale.\npackages: ['.']\n"
        "minimumReleaseAge: 14400\nblockExoticSubdeps: true\n"
    )
    workspace.write_text(original_policy)
    snapshot = module["valid_snapshot"](project)
    upgrade(project)
    policy = yaml.safe_load(original_policy)
    workspace.write_text(yaml.safe_dump(policy))
    upgraded_lock = (project / "pnpm-lock.yaml").read_bytes()
    notes = []

    assert not module["restore_invalid_state"](
        project, snapshot, notes, "Security fix", security_fix=True
    )
    assert workspace.read_bytes() == original_policy.encode()
    assert (project / "pnpm-lock.yaml").read_bytes() == upgraded_lock
    assert module["valid_snapshot"](project) is not None
    assert not notes


@pytest.mark.parametrize(
    "exclusions, expected",
    [
        (
            "minimumReleaseAgeExclude:\n# Keep the migration exceptions.\n"
            "- 'existing@1.0.0' # Existing rationale.\n",
            "minimumReleaseAgeExclude:\n# Keep the migration exceptions.\n"
            "- 'existing@1.0.0' # Existing rationale.\n- child@1.0.1\n",
        ),
        (
            "minimumReleaseAgeExclude:\n  - 'existing@1.0.0'\n",
            "minimumReleaseAgeExclude:\n  - 'existing@1.0.0'\n  - child@1.0.1\n",
        ),
        (
            "minimumReleaseAgeExclude:\n- 'existing@1.0.0'",
            "minimumReleaseAgeExclude:\n- 'existing@1.0.0'\n- child@1.0.1\n",
        ),
        (
            "minimumReleaseAgeExclude: &exclusions\n- 'existing@1.0.0'\n",
            "minimumReleaseAgeExclude: &exclusions\n- 'existing@1.0.0'\n- child@1.0.1\n",
        ),
        (
            "shared: &exclusions ['existing@1.0.0']\n"
            "minimumReleaseAgeExclude: *exclusions # Keep shared settings unchanged.\n",
            "shared: &exclusions ['existing@1.0.0']\n"
            'minimumReleaseAgeExclude: ["existing@1.0.0", "child@1.0.1"] # Keep shared settings unchanged.\n',
        ),
        (
            "minimumReleaseAgeExclude: ['existing@1.0.0'] # Keep this comment.\n",
            "minimumReleaseAgeExclude: ['existing@1.0.0', \"child@1.0.1\"] # Keep this comment.\n",
        ),
        (
            "minimumReleaseAgeExclude: ['existing@1.0.0',] # Keep this comment.\n",
            "minimumReleaseAgeExclude: ['existing@1.0.0', \"child@1.0.1\"] # Keep this comment.\n",
        ),
        (
            "minimumReleaseAgeExclude: [\n"
            "  'existing@1.0.0', # Existing rationale.\n"
            "] # Keep this comment.\n",
            "minimumReleaseAgeExclude: [\n"
            "  'existing@1.0.0', # Existing rationale.\n"
            ' "child@1.0.1"] # Keep this comment.\n',
        ),
        (
            "minimumReleaseAgeExclude: []\n",
            'minimumReleaseAgeExclude: ["child@1.0.1"]\n',
        ),
        ("", "minimumReleaseAgeExclude:\n- child@1.0.1\n"),
    ],
)
def test_pruning_preserves_original_policy_comments_and_formatting(
    project, exclusions, expected
):
    workspace = project / "pnpm-workspace.yaml"
    prefix = (
        "# Workspace policy rationale.\npackages: ['.']\n"
        "minimumReleaseAge: 14400 # Ten days.\nblockExoticSubdeps: true\n"
    )
    workspace.write_text(prefix + exclusions)
    snapshot = module["valid_snapshot"](project)
    upgrade(project)
    policy = yaml.safe_load(workspace.read_text())
    policy["minimumReleaseAgeExclude"] = policy.get("minimumReleaseAgeExclude", []) + [
        "child@1.0.1",
        "unpublished@3.0.4",
    ]
    # Model pnpm rewriting the proposal before pruning its unused exclusion.
    workspace.write_text(yaml.safe_dump(policy))
    notes = []
    assert not module["restore_invalid_state"](
        project, snapshot, notes, "Security fix", security_fix=True
    )
    assert workspace.read_text() == prefix + expected
    assert "child@1.0.1" in module["valid_snapshot"](project)[3]["packages"]
    assert "unpublished@3.0.4" in notes[0]


@pytest.mark.parametrize("failure", [None, "exit", "invalid"])
def test_fresh_security_resolution_is_isolated_and_restores_failures(
    project, monkeypatch, failure
):
    snapshot = module["valid_snapshot"](project)
    commands = []

    def invoke(command, *, cwd, **kwargs):
        args = command[5:]
        commands.append(args)
        if args[0] == "audit":
            return subprocess.CompletedProcess(command, 1, "5 advisories remain", "")
        assert not (cwd / "pnpm-lock.yaml").exists()
        assert "--ignore-scripts" in args and "--force" not in args
        assert "--config.optimistic-repeat-install=false" in args
        modules = Path(args[args.index("--modules-dir") + 1])
        assert modules != cwd / "node_modules"
        assert Path(args[args.index("--virtual-store-dir") + 1]) == modules / ".pnpm"
        (cwd / "pnpm-lock.yaml").write_bytes(snapshot[1]["pnpm-lock.yaml"])
        if failure == "invalid":
            (cwd / "pnpm-lock.yaml").write_text("[")
        else:
            upgrade(project)
        return subprocess.CompletedProcess(command, int(failure == "exit"), "", "")

    monkeypatch.setattr(subprocess, "run", invoke)
    notes = []
    module["fix_security"](project, float("inf"), notes)
    assert len(commands) == 2
    if failure:
        assert (project / "pnpm-lock.yaml").read_bytes() == snapshot[1][
            "pnpm-lock.yaml"
        ]
        assert "regeneration failed" in notes[0]
    else:
        assert "child@1.0.1" in module["valid_snapshot"](project)[3]["packages"]
        assert "Regenerated" in notes[0]


def test_weakened_policy_prevents_fresh_resolution(project, monkeypatch):
    commands = []

    def invoke(command, *, cwd, **kwargs):
        commands.append(command)
        policy = yaml.safe_load((cwd / "pnpm-workspace.yaml").read_bytes())
        policy["blockExoticSubdeps"] = False
        (cwd / "pnpm-workspace.yaml").write_text(yaml.safe_dump(policy))
        return subprocess.CompletedProcess(command, 1, "", "")

    monkeypatch.setattr(subprocess, "run", invoke)
    module["fix_security"](project, float("inf"))
    assert len(commands) == 1


@pytest.mark.parametrize(
    "status",
    [
        "unpublished",
        "blocked",
        "compatible",
        "unavailable",
        "malformed",
        "invalid-json",
        "invalid-error",
        "mutated-policy",
        "no-patch",
        "unrelated",
        "missing-constraint",
        "unavailable-intersection",
    ],
)
def test_patch_publication_and_parent_constraints_are_reported(
    project, monkeypatch, status
):
    detail = {
        "patchedRange": None if status == "no-patch" else ">=2.0.0",
        "nodes": ["child@0.9.0" if status == "unrelated" else "child@1.0.0"],
        "title": "Example",
        "severity": "high",
        "url": "https://github.com/advisories/example",
        "range": "<2.0.0",
    }
    data = {
        "package_manager": "pnpm",
        "metadata": {"vulnerabilities": {"high": 1}},
        "vulnerabilities": {"child": {"via": [detail], "fixAvailable": True}},
    }
    commands = []

    def invoke(command, **kwargs):
        args = command[5:]
        commands.append(args)
        value, code = ["2.0.0"], 0
        if args[1] == "child@>=2.0.0":
            if status == "unpublished":
                value, code = {"error": {"code": "ERR_PNPM_PACKAGE_NOT_FOUND"}}, 1
            elif status == "unavailable":
                value, code = {"error": {"code": "ETIMEDOUT"}}, 1
            elif status == "invalid-json":
                return subprocess.CompletedProcess(command, 0, "{", "")
            elif status == "invalid-error":
                value, code = {"error": "invalid metadata"}, 1
            elif status == "mutated-policy":
                policy = yaml.safe_load((project / "pnpm-workspace.yaml").read_bytes())
                policy["blockExoticSubdeps"] = False
                (project / "pnpm-workspace.yaml").write_text(yaml.safe_dump(policy))
        elif args[1] == "parent@1.0.0":
            value = {
                "dependencies": None
                if status == "malformed"
                else {}
                if status == "missing-constraint"
                else {"child": "^1.0.0" if status == "blocked" else ">=1.0.0"}
            }
        elif args[1] == "child@^1.0.0 >=2.0.0":
            value, code = {"error": {"code": "ERR_PNPM_PACKAGE_NOT_FOUND"}}, 1
        elif args[1] == "child@>=1.0.0 >=2.0.0":
            if status == "unavailable-intersection":
                value, code = {"error": {"code": "ETIMEDOUT"}}, 1
            else:
                value = "2.0.0"
        return subprocess.CompletedProcess(command, code, json.dumps(value), "")

    monkeypatch.setattr(subprocess, "run", invoke)
    snapshot = module["valid_snapshot"](project)
    cache = {}
    notes = []
    for _ in range(2):
        module["describe_pnpm_fixes"](
            project, data, snapshot[1], notes, float("inf"), cache
        )
    expected = {
        "unpublished": "No published stable patch",
        "blocked": "`parent@1.0.0` requires `child ^1.0.0`",
        "compatible": "No checked parent constraint excludes",
        "unavailable": "Could not verify publication",
        "malformed": "Parent compatibility could not be fully verified",
        "invalid-json": "Could not verify publication",
        "invalid-error": "Could not verify publication",
        "mutated-policy": "Could not verify publication",
        "no-patch": "No patched version declared",
        "unrelated": "No checked parent constraint excludes",
        "missing-constraint": "Parent compatibility could not be fully verified",
        "unavailable-intersection": "Parent compatibility could not be fully verified",
    }
    assert isinstance(detail["fixStatus"], str)
    assert expected[status] in detail["fixStatus"]
    assert data["vulnerabilities"]["child"]["fixAvailable"] == (
        status
        not in (
            "unpublished",
            "unavailable",
            "invalid-json",
            "invalid-error",
            "mutated-policy",
            "no-patch",
        )
    )
    assert expected[status] in module["format_remaining_audit"](data, snapshot[3])
    assert (
        len(commands)
        == {
            "unpublished": 1,
            "blocked": 3,
            "compatible": 3,
            "unavailable": 1,
            "malformed": 2,
            "invalid-json": 1,
            "invalid-error": 1,
            "mutated-policy": 1,
            "no-patch": 0,
            "unrelated": 1,
            "missing-constraint": 2,
            "unavailable-intersection": 3,
        }[status]
    )
    assert module["valid_snapshot"](project)[:2] == snapshot[:2]
    if status == "mutated-policy":
        assert len(notes) == 1 and "restored" in notes[0]


def test_parent_can_use_an_older_patch_than_the_latest_registry_match(
    project, monkeypatch
):
    detail = {"patchedRange": ">=2.0.0", "nodes": ["child@1.0.0"]}
    data = {"package_manager": "pnpm", "vulnerabilities": {"child": {"via": [detail]}}}
    responses = {
        "child@>=2.0.0": "3.0.0",
        "parent@1.0.0": {"dependencies": {"child": "^1.0.0 || ^2.0.0"}},
        "child@^1.0.0 >=2.0.0": [],
        "child@^2.0.0 >=2.0.0": "2.1.0",
    }

    monkeypatch.setattr(
        subprocess,
        "run",
        lambda command, **kwargs: subprocess.CompletedProcess(
            command, 0, json.dumps(responses[command[6]]), ""
        ),
    )
    module["describe_pnpm_fixes"](
        project, data, module["valid_snapshot"](project)[1], [], float("inf"), {}
    )
    assert "Published patch: `child@2.1.0`" in detail["fixStatus"]
    assert "No checked parent constraint excludes" in detail["fixStatus"]


@pytest.mark.parametrize("shared_patch", [False, True])
def test_patch_candidate_must_satisfy_every_affected_parent(
    project, monkeypatch, shared_patch
):
    detail = {"patchedRange": ">=2.0.0", "nodes": ["child@1.0.0"]}
    data = {"package_manager": "pnpm", "vulnerabilities": {"child": {"via": [detail]}}}
    files = module["valid_snapshot"](project)[1]
    lock = yaml.safe_load(files["pnpm-lock.yaml"])
    lock["snapshots"]["other-parent@1.0.0"] = {"dependencies": {"child": "1.0.0"}}
    files["pnpm-lock.yaml"] = yaml.safe_dump(lock).encode()
    responses = {
        "child@>=2.0.0": ["2.1.0", "3.1.0"],
        "parent@1.0.0": {"dependencies": {"child": "^2.0.0 || ^3.0.0"}},
        "other-parent@1.0.0": {"dependencies": {"child": "^3.0.0"}},
        "child@^2.0.0 >=2.0.0": ["2.1.0"],
        "child@^3.0.0 >=2.0.0": ["3.1.0"],
    }
    if not shared_patch:
        responses["parent@1.0.0"] = {"dependencies": {"child": "^2.0.0"}}
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda command, **kwargs: subprocess.CompletedProcess(
            command, 0, json.dumps(responses[command[6]]), ""
        ),
    )
    module["describe_pnpm_fixes"](project, data, files, [], float("inf"), {})
    assert data["vulnerabilities"]["child"]["fixAvailable"] is True
    if shared_patch:
        assert "Published patch: `child@3.1.0`" in detail["fixStatus"]
        assert "No checked parent constraint excludes" in detail["fixStatus"]
    else:
        assert (
            "no single patch satisfies all checked parent constraints"
            in detail["fixStatus"]
        )
        assert "Published patch:" not in detail["fixStatus"]

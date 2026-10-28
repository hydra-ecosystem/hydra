# SPDX-FileCopyrightText: Contributors to Hydra
# SPDX-License-Identifier: MIT

import sys
from pathlib import Path
from typing import Any

import yaml
from pytest import MonkeyPatch, mark, param, raises, warns

from hydra._internal.instantiate._instantiate2 import _resolve_target
from hydra.errors import InstantiationException
from hydra.utils import UNSAFE_DISABLE_EXECUTION_CHECKS, instantiate


@mark.parametrize(
    "target",
    [
        "yaml.load",
        "yaml.load_all",
        "yaml.full_load",
        "yaml.full_load_all",
        "yaml.unsafe_load",
        "yaml.unsafe_load_all",
        "yaml.Loader",
        "yaml.FullLoader",
        "yaml.UnsafeLoader",
        "yaml.BaseLoader",
        "yaml.SafeLoader",
        "yaml.loader.Loader",
        "yaml.loader.FullLoader",
        "yaml.loader.UnsafeLoader",
        "yaml.loader.BaseLoader",
        "yaml.loader.SafeLoader",
        "yaml.constructor.Constructor",
        "yaml.constructor.FullConstructor",
        "yaml.constructor.UnsafeConstructor",
        "yaml.Loader.construct_python_object_apply",
        "yaml.FullLoader.make_python_instance",
        "yaml.UnsafeLoader.find_python_name",
        "yaml.loader.Constructor",
        "yaml.loader.FullConstructor.make_python_instance",
        "yaml.constructor.UnsafeConstructor.make_python_instance",
        *[
            param(
                target,
                marks=mark.skipif(not yaml.__with_libyaml__, reason="Requires LibYAML"),
            )
            for target in [
                "yaml.CLoader",
                "yaml.CFullLoader",
                "yaml.CUnsafeLoader",
                "yaml.CBaseLoader",
                "yaml.CSafeLoader",
                "yaml.cyaml.CLoader",
                "yaml.cyaml.CFullLoader",
                "yaml.cyaml.CUnsafeLoader",
                "yaml.cyaml.CBaseLoader",
                "yaml.cyaml.CSafeLoader",
                "yaml.CLoader.construct_python_object_apply",
                "yaml.cyaml.FullConstructor.make_python_instance",
            ]
        ],
    ],
)
@mark.parametrize("policy", [None, "exact", "yaml.*"])
@mark.parametrize("as_callable", [False, True])
def test_yaml_targets_are_restricted(
    target: str, policy: str | None, as_callable: bool
) -> None:
    configured_target: Any = target
    if as_callable:
        configured_target = _resolve_target(target, "", UNSAFE_DISABLE_EXECUTION_CHECKS)
    match = "blacklisted" if policy is None else "cannot be authorized"
    with raises(InstantiationException, match=match):
        _resolve_target(
            configured_target,
            "nested",
            (target,) if policy == "exact" else (policy,) if policy else None,
        )


@mark.parametrize("policy", [None, "exact"])
def test_yaml_alias_is_restricted(monkeypatch: MonkeyPatch, policy: str | None) -> None:
    monkeypatch.setattr(
        sys.modules[__name__], "yaml_alias", yaml.unsafe_load, raising=False
    )
    target = f"{__name__}.yaml_alias"
    with raises(
        InstantiationException,
        match="blacklisted" if policy is None else "cannot be authorized",
    ):
        _resolve_target(target, "nested", (target,) if policy else None)


@mark.parametrize(
    "target",
    ["yaml.future_loader", "yaml.dump", "yaml.SafeLoader.add_constructor"],
)
@mark.parametrize("policy", [None, "yaml.*"])
def test_yaml_namespace_is_restricted_by_default(
    target: str, policy: str | None
) -> None:
    with raises(
        InstantiationException,
        match="blacklisted" if policy is None else "cannot be authorized",
    ):
        _resolve_target(target, "nested", (policy,) if policy else None)


@mark.parametrize("target", ["yaml.unsafe_load", "yaml.unsafe_load_all"])
@mark.parametrize("as_partial", [False, True])
def test_yaml_payload_is_blocked_before_execution(
    target: str, tmp_path: Path, as_partial: bool
) -> None:
    marker = tmp_path / "executed"
    stream = f"!!python/object/apply:os.mkdir [{str(marker)!r}]"

    with raises(InstantiationException, match="blacklisted"):
        result = instantiate(
            {"_target_": target, "stream": stream, "_partial_": as_partial}
        )
        if as_partial:
            result = result()
        if target.endswith("_all"):
            list(result)

    assert not marker.exists()


@mark.parametrize("target", ["yaml.unsafe_load", "yaml.unsafe_load_all"])
def test_yaml_unsafe_opt_out_still_permits_execution(
    target: str, tmp_path: Path
) -> None:
    marker = tmp_path / "executed"
    stream = f"!!python/object/apply:os.mkdir [{str(marker)!r}]"
    result = instantiate(
        {"_target_": target, "stream": stream},
        _execution_whitelist_=UNSAFE_DISABLE_EXECUTION_CHECKS,
    )
    if target.endswith("_all"):
        list(result)

    assert marker.is_dir()


@mark.parametrize("target", ["yaml.safe_load", "yaml.safe_load_all"])
@mark.parametrize("policy", [None, "yaml.*"])
def test_yaml_safe_loading_remains_available(target: str, policy: Any) -> None:
    cfg = {"_target_": target, "stream": "answer: 42"}
    if policy is None:
        with warns(UserWarning, match="_execution_whitelist_"):
            result = instantiate(cfg)
    else:
        result = instantiate(cfg, _execution_whitelist_=policy)
    assert (list(result) if target.endswith("_all") else result) == (
        [{"answer": 42}] if target.endswith("_all") else {"answer": 42}
    )


@mark.parametrize("target", ["yaml.safe_load", "yaml.safe_load_all"])
def test_yaml_safe_loading_rejects_python_payloads(target: str, tmp_path: Path) -> None:
    marker = tmp_path / "executed"
    stream = f"!!python/object/apply:os.mkdir [{str(marker)!r}]"
    with raises(yaml.constructor.ConstructorError):
        result = instantiate(
            {"_target_": target, "stream": stream}, _execution_whitelist_=target
        )
        if target.endswith("_all"):
            list(result)
    assert not marker.exists()


@mark.parametrize("target", ["yaml.safe_dump", "yaml.safe_dump_all"])
@mark.parametrize("policy", [None, "yaml.*"])
def test_yaml_safe_dumping_remains_available(target: str, policy: str | None) -> None:
    data = {"answer": 42}
    cfg = {
        "_target_": target,
        "_args_": [[data] if target.endswith("_all") else data],
        "_convert_": "all",
    }
    if policy is None:
        with warns(UserWarning, match="_execution_whitelist_"):
            result = instantiate(cfg)
    else:
        result = instantiate(cfg, _execution_whitelist_=policy)
    assert yaml.safe_load(result) == data


@mark.parametrize("target", ["yaml.safe_dump", "yaml.safe_dump_all"])
def test_yaml_safe_dumping_rejects_python_objects(target: str) -> None:
    data = object()
    with raises(yaml.representer.RepresenterError):
        instantiate(
            {
                "_target_": target,
                "_convert_": "all",
            },
            [data] if target.endswith("_all") else data,
            _execution_whitelist_=target,
        )

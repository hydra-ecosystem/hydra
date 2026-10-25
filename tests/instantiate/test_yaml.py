# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved

import sys
from pathlib import Path
from typing import Any

import yaml
from pytest import mark, param, raises

from hydra._internal.instantiate._instantiate2 import _resolve_target
from hydra._internal.utils import _locate
from hydra.errors import InstantiationException
from hydra.utils import instantiate


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
        "yaml.SafeLoader",
        "yaml.BaseLoader",
        "yaml.loader.Loader",
        "yaml.loader.UnsafeLoader",
        "yaml.loader.SafeLoader",
        "yaml.loader.BaseLoader",
        "yaml.constructor.Constructor",
        "yaml.constructor.FullConstructor",
        "yaml.constructor.UnsafeConstructor.make_python_instance",
        "yaml.Loader.construct_python_object_apply",
        "yaml.SafeLoader.add_constructor",
        "yaml.dump",
        *[
            param(
                target,
                marks=mark.skipif(not yaml.__with_libyaml__, reason="Requires LibYAML"),
            )
            for target in [
                "yaml.CLoader",
                "yaml.CFullLoader",
                "yaml.CUnsafeLoader",
                "yaml.CSafeLoader",
                "yaml.CBaseLoader",
                "yaml.cyaml.CLoader",
                "yaml.cyaml.CFullLoader",
                "yaml.cyaml.CUnsafeLoader",
                "yaml.cyaml.CSafeLoader",
                "yaml.cyaml.CBaseLoader",
            ]
        ],
    ],
)
@mark.parametrize("override", [False, True])
@mark.parametrize("as_callable", [False, True])
def test_yaml_targets_are_restricted(
    target: str, override: bool, as_callable: bool, monkeypatch: Any
) -> None:
    if override:
        monkeypatch.setenv("HYDRA_INSTANTIATE_ALLOWLIST_OVERRIDE", target)
    configured_target = _locate(target) if as_callable else target
    with raises(InstantiationException, match="cannot be authorized"):
        _resolve_target(configured_target, "nested")


def test_yaml_alias_is_restricted(monkeypatch: Any) -> None:
    monkeypatch.setattr(
        sys.modules[__name__], "yaml_alias", yaml.unsafe_load, raising=False
    )
    with raises(InstantiationException, match="blocklisted"):
        _resolve_target(f"{__name__}.yaml_alias", "nested")


@mark.parametrize("target", ["yaml.unsafe_load", "yaml.unsafe_load_all"])
@mark.parametrize("as_partial", [False, True])
def test_yaml_payload_is_blocked_before_execution(
    target: str, tmp_path: Path, as_partial: bool
) -> None:
    marker = tmp_path / "executed"
    stream = f"!!python/object/apply:os.mkdir [{str(marker)!r}]"
    with raises(InstantiationException, match="blocklisted"):
        result = instantiate(
            {"_target_": target, "stream": stream, "_partial_": as_partial}
        )
        if as_partial:
            result = result()
        if target.endswith("_all"):
            list(result)
    assert not marker.exists()


@mark.parametrize("target", ["yaml.safe_load", "yaml.safe_load_all"])
def test_yaml_safe_loading_remains_available(target: str) -> None:
    result = instantiate({"_target_": target, "stream": "answer: 42"})
    assert (list(result) if target.endswith("_all") else result) == (
        [{"answer": 42}] if target.endswith("_all") else {"answer": 42}
    )


@mark.parametrize("target", ["yaml.safe_dump", "yaml.safe_dump_all"])
def test_yaml_safe_dumping_remains_available(target: str) -> None:
    data = {"answer": 42}
    result = instantiate(
        {
            "_target_": target,
            "_args_": [[data] if target.endswith("_all") else data],
            "_convert_": "all",
        }
    )
    assert yaml.safe_load(result) == data

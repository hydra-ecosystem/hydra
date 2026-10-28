# SPDX-FileCopyrightText: Contributors to Hydra
# SPDX-License-Identifier: MIT
import pickle
from dataclasses import dataclass, field
from typing import Any

from omegaconf import DictConfig, ListConfig, OmegaConf
from omegaconf.errors import (
    InterpolationResolutionError,
    UnsupportedValueType,
    ValidationError,
)
from pytest import mark, raises

from hydra.errors import InstantiationException
from hydra.utils import instantiate
from tests.instantiate import ArgsClass, TreeConf

WHITELIST = ["tests.instantiate.*", "builtins.dict"]


class Model:
    def __init__(self, sizes: ListConfig) -> None:
        self.sizes = sizes


@mark.parametrize("recursive", [True, False])
def test_isolation_local_schema_pickling(recursive: bool) -> None:
    @dataclass
    class ModelConf:
        _target_: str = f"{__name__}.Model"
        sizes: list[int] = field(default_factory=lambda: [1, 2, 3])

    shared = instantiate(
        ModelConf, _recursive_=recursive, _execution_whitelist_=WHITELIST
    )
    with raises((pickle.PicklingError, AttributeError)):
        pickle.dumps(shared)

    isolated = instantiate(
        ModelConf,
        isolate=True,
        _recursive_=recursive,
        _execution_whitelist_=WHITELIST,
    )
    assert isinstance(isolated.sizes, ListConfig)
    assert isolated.sizes._get_parent() is None
    # Round-trip only the object just serialized by this test.
    restored = pickle.loads(pickle.dumps(isolated))  # nosec B301
    assert list(restored.sizes) == [1, 2, 3]


@mark.parametrize("recursive", [True, False])
@mark.parametrize("with_override", [True, False])
def test_isolation_preserves_ancestor_resolution(
    recursive: bool, with_override: bool
) -> None:
    cfg = OmegaConf.create(
        {
            "width": 8,
            "node": {
                "_target_": "tests.instantiate.ArgsClass",
                "_recursive_": recursive,
                "payload": {"value": "${width}", "alias": "${.value}"},
            },
        }
    )
    OmegaConf.set_readonly(cfg, True)
    original = OmegaConf.to_container(cfg, resolve=False)
    result: ArgsClass = instantiate(
        cfg.node,
        isolate=True,
        _execution_whitelist_=WHITELIST,
        **({"extra": 10} if with_override else {}),
    )
    payload = result.kwargs["payload"]
    assert payload is not cfg.node.payload
    assert payload._get_parent() is None
    assert OmegaConf.to_container(payload, resolve=False) == {"value": 8, "alias": 8}
    payload.value = 32
    assert payload.alias == 8
    assert OmegaConf.to_container(cfg, resolve=False) == original
    assert OmegaConf.is_readonly(cfg)


def test_isolation_resolves_readonly_union_argument() -> None:
    @dataclass
    class Job:
        _target_: str = "tests.instantiate.ArgsClass"
        payload: TreeConf | int = field(
            default_factory=lambda: TreeConf(value="${width}")
        )

    cfg = OmegaConf.create({"width": 8, "job": Job()})
    OmegaConf.set_readonly(cfg.job.payload, True)
    result = instantiate(
        cfg.job, isolate=True, _recursive_=False, _execution_whitelist_=WHITELIST
    )
    payload = result.kwargs["payload"]
    assert payload.value == 8
    assert payload is not cfg.job.payload
    assert OmegaConf.is_interpolation(cfg.job.payload, "value")
    assert OmegaConf.is_readonly(cfg.job.payload)


def test_isolation_applies_to_nested_targets() -> None:
    cfg = OmegaConf.create(
        {
            "_target_": "tests.instantiate.ArgsClass",
            "child": {
                "_target_": "tests.instantiate.ArgsClass",
                "_recursive_": False,
                "payload": {"value": 8},
            },
        }
    )
    result: ArgsClass = instantiate(cfg, isolate=True, _execution_whitelist_=WHITELIST)
    payload = result.kwargs["child"].kwargs["payload"]
    assert payload._get_parent() is None
    payload.value = 32
    assert cfg.child.payload.value == 8


@mark.parametrize("recursive", [True, False])
@mark.parametrize("partial", [True, False])
@mark.parametrize("readonly_path", ["job.payload.nested", "template", "scalar"])
def test_isolation_resolves_explicit_readonly_nodes(
    recursive: bool, partial: bool, readonly_path: str
) -> None:
    cfg = OmegaConf.create(
        {
            "width": 8,
            "template": {"value": "${width}"},
            "job": {
                "_target_": "tests.instantiate.ArgsClass",
                "payload": {
                    "nested": {"value": "${width}"},
                    "alias": "${template}",
                },
            },
        }
    )
    readonly_node = (
        cfg.job.payload.nested._get_node("value")
        if readonly_path == "scalar"
        else OmegaConf.select(cfg, readonly_path)
    )
    OmegaConf.set_readonly(readonly_node, True)
    original = OmegaConf.to_container(cfg, resolve=False)
    result = instantiate(
        cfg.job,
        isolate=True,
        _recursive_=recursive,
        _partial_=partial,
        _execution_whitelist_=WHITELIST,
    )
    if partial:
        result = result()
    payload = result.kwargs["payload"]
    assert payload._get_parent() is None
    assert OmegaConf.to_container(payload, resolve=False) == {
        "nested": {"value": 8},
        "alias": {"value": 8},
    }
    assert OmegaConf.to_container(cfg, resolve=False) == original
    assert OmegaConf.is_readonly(readonly_node)
    if not recursive and readonly_path == "job.payload.nested":
        assert OmegaConf.is_readonly(payload.nested)


def register_poc_resolver() -> None:
    OmegaConf.register_resolver("isolation_poc", lambda: 42, replace=True)


def test_isolation_resolves_before_targets_run_and_restores_mode() -> None:
    cfg = {
        "_target_": "builtins.dict",
        "first": {"_target_": f"{__name__}.register_poc_resolver"},
        "second": "${isolation_poc:}",
    }
    OmegaConf.clear_resolver("isolation_poc")
    try:
        with raises(InterpolationResolutionError):
            instantiate(cfg, isolate=True, _execution_whitelist_=WHITELIST)
        assert instantiate(cfg, _execution_whitelist_=WHITELIST)["second"] == 42
    finally:
        OmegaConf.clear_resolver("isolation_poc")


@mark.parametrize("isolate", [True, False])
def test_isolation_keeps_current_override_semantics(isolate: bool) -> None:
    @dataclass
    class Conf:
        _target_: str = "builtins.dict"
        x: int = 1

    runtime = object()
    result = instantiate(
        Conf, isolate=isolate, x=2, runtime=runtime, _execution_whitelist_=WHITELIST
    )
    assert result == {"x": 2, "runtime": runtime}
    assert result["runtime"] is runtime


@mark.parametrize("isolate", [True, False])
@mark.parametrize("value", ["hi", "1"])
def test_isolation_preserves_strict_override_validation(
    isolate: bool, value: str
) -> None:
    @dataclass
    class Conf:
        _target_: str = "builtins.dict"
        x: int = 1

    with raises(ValidationError):
        instantiate(Conf, isolate=isolate, x=value, _execution_whitelist_=WHITELIST)


@mark.parametrize("isolate", [True, False])
def test_isolation_preserves_explicit_input_object_opt_in(isolate: bool) -> None:
    runtime = object()
    raw = {"_target_": "builtins.dict", "payload": runtime}
    with raises(UnsupportedValueType):
        instantiate(raw, isolate=isolate, _execution_whitelist_=WHITELIST)

    config = OmegaConf.create(raw, flags={"allow_objects": True})
    result = instantiate(config, isolate=isolate, _execution_whitelist_=WHITELIST)
    assert type(result["payload"]) is object
    assert config.payload is runtime


def test_isolation_is_a_callsite_option() -> None:
    result = instantiate(
        {"_target_": "builtins.dict", "isolate": "target argument"},
        isolate=True,
        _execution_whitelist_=WHITELIST,
    )
    assert result == {"isolate": "target argument"}


@mark.parametrize("isolate", [None, 1, "true"])
def test_isolation_requires_bool(isolate: Any) -> None:
    with raises(TypeError, match="isolate must be a bool"):
        instantiate({}, isolate=isolate, _execution_whitelist_=WHITELIST)


def test_isolation_prepares_partial_arguments() -> None:
    cfg = OmegaConf.create(
        {
            "_target_": "tests.instantiate.ArgsClass",
            "_recursive_": False,
            "_partial_": True,
            "payload": {"value": 8},
        }
    )
    factory = instantiate(cfg, isolate=True, _execution_whitelist_=WHITELIST)
    cfg.payload.value = 32
    assert factory().kwargs["payload"].value == 8
    assert factory.keywords["payload"]._get_parent() is None


@mark.parametrize("payload", [["${width}"], ("${width}",)])
def test_isolation_top_level_sequence(payload: Any) -> None:
    cfg = OmegaConf.create(
        {
            "width": 8,
            "nodes": [
                {
                    "_target_": "tests.instantiate.ArgsClass",
                    "_recursive_": False,
                    "payload": payload,
                }
            ],
        }
    )
    result = instantiate(cfg.nodes, isolate=True, _execution_whitelist_=WHITELIST)
    isolated = result[0].kwargs["payload"]
    assert list(isolated) == [8]
    assert isolated._get_parent() is None
    assert isolated is not cfg.nodes[0].payload


def reenter_default_instantiation() -> bool:
    cfg = OmegaConf.create(
        {"_target_": "builtins.dict", "_recursive_": False, "payload": {"value": 8}}
    )
    result = instantiate(cfg, _execution_whitelist_=WHITELIST)
    return result["payload"] is cfg.payload


def test_isolation_does_not_change_independent_reentrant_calls() -> None:
    assert instantiate(
        {"_target_": f"{__name__}.reenter_default_instantiation"},
        isolate=True,
        _execution_whitelist_=WHITELIST,
    )


def test_isolation_preserves_execution_checks() -> None:
    with raises(InstantiationException):
        instantiate(
            {"_target_": f"{__name__}.Model", "sizes": [1, 2, 3]},
            isolate=True,
            _execution_whitelist_="builtins.dict",
        )


def test_isolation_prepares_positional_runtime_config() -> None:
    cfg = OmegaConf.create({"width": 8, "payload": {"value": "${width}"}})
    result = instantiate(
        {"_target_": "tests.instantiate.ArgsClass", "_recursive_": False},
        cfg.payload,
        isolate=True,
        _execution_whitelist_=WHITELIST,
    )
    payload = result.args[0]
    assert payload is not cfg.payload
    assert payload._get_parent() is None
    assert OmegaConf.to_container(payload, resolve=False) == {"value": 8}
    assert OmegaConf.to_container(cfg.payload, resolve=False) == {"value": "${width}"}


@mark.parametrize("positional", [True, False])
@mark.parametrize("partial", [True, False])
def test_runtime_config_isolation_preserves_ancestor_containers(
    positional: bool, partial: bool
) -> None:
    cfg = OmegaConf.create(
        {
            "width": 8,
            "template": {"value": "${width}"},
            "payload": {"nested": "${template}"},
        }
    )
    original = OmegaConf.to_container(cfg, resolve=False)
    result = instantiate(
        {
            "_target_": "tests.instantiate.ArgsClass",
            "_recursive_": False,
            "_partial_": partial,
        },
        *((cfg.payload,) if positional else ()),
        isolate=True,
        _execution_whitelist_=WHITELIST,
        **({} if positional else {"payload": cfg.payload}),
    )
    if partial:
        result = result()
    payload = result.args[0] if positional else result.kwargs["payload"]
    assert payload._get_parent() is None
    assert OmegaConf.to_container(payload, resolve=False) == {"nested": {"value": 8}}
    assert OmegaConf.to_container(cfg, resolve=False) == original


@mark.parametrize("isolate", [True, False])
@mark.parametrize("with_override", [True, False])
def test_isolation_preserves_null_config_handling(
    isolate: bool, with_override: bool
) -> None:
    config = DictConfig(None)
    result = instantiate(
        config,
        isolate=isolate,
        _execution_whitelist_=WHITELIST,
        **({"value": 10} if with_override else {}),
    )
    assert result == ({"value": 10} if with_override else None)
    assert config._is_none()


@mark.parametrize("config_kind", ["dict", "omegaconf", "class", "instance"])
@mark.parametrize("config_default", [True, False])
@mark.parametrize("explicit", ["omitted", True, False])
def test_config_isolation_default_and_explicit_precedence(
    config_kind: str, config_default: bool, explicit: Any
) -> None:
    @dataclass
    class ModelConf:
        _target_: str = f"{__name__}.Model"
        _isolate_: bool = config_default
        sizes: list[int] = field(default_factory=lambda: [1, 2, 3])

    configs = {
        "dict": {
            "_target_": f"{__name__}.Model",
            "_isolate_": config_default,
            "sizes": [1, 2, 3],
        },
        "omegaconf": OmegaConf.structured(ModelConf),
        "class": ModelConf,
        "instance": ModelConf(),
    }
    options = {} if explicit == "omitted" else {"isolate": explicit}
    model = instantiate(
        configs[config_kind], _execution_whitelist_=WHITELIST, **options
    )
    expected = config_default if explicit == "omitted" else explicit
    assert (model.sizes._get_parent() is None) is expected
    if expected:
        # Round-trip only the object just serialized by this test.
        restored = pickle.loads(pickle.dumps(model))  # nosec B301
        assert list(restored.sizes) == [1, 2, 3]


@mark.parametrize("root_default", [True, False])
def test_nested_config_does_not_change_invocation_isolation(root_default: bool) -> None:
    cfg = OmegaConf.create(
        {
            "_target_": "tests.instantiate.ArgsClass",
            "_isolate_": root_default,
            "child": {
                "_target_": "tests.instantiate.ArgsClass",
                "_isolate_": not root_default,
                "_recursive_": False,
                "payload": {"value": 8},
            },
        }
    )
    result = instantiate(cfg, _execution_whitelist_=WHITELIST)
    assert "_isolate_" not in result.kwargs
    child = result.kwargs["child"]
    assert "_isolate_" not in child.kwargs
    assert (child.kwargs["payload"]._get_parent() is None) is root_default

    # The child can supply its own default when it is the input of another call.
    direct_child = instantiate(cfg.child, _execution_whitelist_=WHITELIST)
    assert (direct_child.kwargs["payload"]._get_parent() is None) is not root_default


@mark.parametrize("invalid", [None, 1, "true"])
def test_config_isolation_default_requires_bool(invalid: Any) -> None:
    with raises(TypeError, match="_isolate_ must be a bool"):
        instantiate(
            {"_target_": "builtins.dict", "_isolate_": invalid},
            _execution_whitelist_=WHITELIST,
        )


@mark.parametrize("explicit", [True, False])
def test_explicit_isolation_does_not_read_unused_config_default(explicit: bool) -> None:
    result = instantiate(
        {"_target_": "builtins.dict", "_isolate_": "unused"},
        isolate=explicit,
        _execution_whitelist_=WHITELIST,
    )
    assert result == {}


def test_config_isolation_default_on_non_target_root() -> None:
    cfg = OmegaConf.create(
        {
            "_isolate_": True,
            "width": 8,
            "model": {
                "_target_": f"{__name__}.Model",
                "sizes": ["${width}", 16],
            },
        }
    )
    result = instantiate(cfg, _execution_whitelist_=WHITELIST)
    assert "_isolate_" not in result
    assert list(result.model.sizes) == [8, 16]
    assert result.model.sizes._get_parent() is None
    assert OmegaConf.to_container(cfg.model.sizes, resolve=False) == ["${width}", 16]

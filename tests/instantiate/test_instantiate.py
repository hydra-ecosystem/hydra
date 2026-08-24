# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved
import copy
import inspect
import os
import pickle
import re
from dataclasses import InitVar, dataclass, field
from functools import partial
from textwrap import dedent
from typing import Any, Callable, Dict, List, Optional, Tuple, cast

import attr
from omegaconf import (
    MISSING,
    AnyNode,
    DictConfig,
    ListConfig,
    MissingMandatoryValue,
    OmegaConf,
    TupleConfig,
)
from omegaconf.errors import ValidationError
from pytest import fixture, mark, param, raises, warns

from hydra._internal.instantiate import _instantiate2
from hydra._internal.instantiate._instantiate2 import _resolve_target
from hydra.errors import InstantiationException
from hydra.test_utils.test_utils import assert_multiline_regex_search
from hydra.types import ConvertMode
from hydra.utils import UNSAFE_ALLOW_ALL_TARGETS, target_whitelist
from tests.instantiate import (
    AClass,
    Adam,
    AdamConf,
    AnotherClass,
    ArgsClass,
    ASubclass,
    BClass,
    CallableClass,
    CenterCrop,
    CenterCropConf,
    Compose,
    ComposeConf,
    IllegalType,
    KeywordsInParamsClass,
    Mapping,
    MappingConf,
    NestedConf,
    NestingClass,
    OuterClass,
    Parameters,
    Rotation,
    RotationConf,
    SimpleClass,
    SimpleClassDefaultPrimitiveConf,
    SimpleClassNonPrimitiveConf,
    SimpleClassPrimitiveConf,
    SimpleDataClass,
    TargetWithInstantiateInInit,
    Tree,
    TreeConf,
    UntypedPassthroughClass,
    UntypedPassthroughConf,
    User,
    add_values,
    module_function,
    module_function2,
    partial_equal,
    recisinstance,
)


@fixture(
    params=[
        _instantiate2.instantiate,
    ],
    ids=[
        "instantiate2",
    ],
)
def instantiate_func(request: Any) -> Any:
    def wrapper(config: Any, *args: Any, **kwargs: Any) -> Any:
        kwargs.setdefault("_target_whitelist_", UNSAFE_ALLOW_ALL_TARGETS)
        return request.param(config, *args, **kwargs)

    return wrapper


@fixture(
    params=[
        lambda cfg: copy.deepcopy(cfg),
        lambda cfg: OmegaConf.create(cfg),
    ],
    ids=[
        "dict",
        "dict_config",
    ],
)
def config(request: Any, src: Any) -> Any:
    config = request.param(src)
    cfg_copy = copy.deepcopy(config)
    yield config
    assert config == cfg_copy


def structured_config_object_node(value: Any) -> Any:
    return AnyNode(value, flags={"allow_objects": True})


def register_test_resolver(name: str, value: Any) -> Any:
    OmegaConf.register_resolver(name, lambda: value, replace=True)
    return value


@mark.parametrize(
    "recursive", [param(False, id="not_recursive"), param(True, id="recursive")]
)
@mark.parametrize(
    "src, passthrough, expected",
    [
        param(
            {
                "_target_": "tests.instantiate.AClass",
                "a": 10,
                "b": 20,
                "c": 30,
                "d": 40,
            },
            {},
            AClass(10, 20, 30, 40),
            id="class",
        ),
        param(
            {
                "_target_": "tests.instantiate.AClass",
                "_partial_": True,
                "a": 10,
                "b": 20,
                "c": 30,
            },
            {},
            partial(AClass, a=10, b=20, c=30),
            id="class+partial",
        ),
        param(
            {
                "_target_": "tests.instantiate.AClass",
                "_partial_": True,
                "a": "???",
                "b": 20,
                "c": 30,
            },
            {},
            partial(AClass, b=20, c=30),
            id="class+partial+missing",
        ),
        param(
            [
                {
                    "_target_": "tests.instantiate.AClass",
                    "_partial_": True,
                    "a": 10,
                    "b": 20,
                    "c": 30,
                },
                {
                    "_target_": "tests.instantiate.BClass",
                    "a": 50,
                    "b": 60,
                    "c": 70,
                },
            ],
            {},
            [partial(AClass, a=10, b=20, c=30), BClass(a=50, b=60, c=70)],
            id="list_of_partial_class",
        ),
        param(
            [
                {
                    "_target_": "tests.instantiate.AClass",
                    "_partial_": True,
                    "a": "???",
                    "b": 20,
                    "c": 30,
                },
                {
                    "_target_": "tests.instantiate.BClass",
                    "a": 50,
                    "b": 60,
                    "c": 70,
                },
            ],
            {},
            [partial(AClass, b=20, c=30), BClass(a=50, b=60, c=70)],
            id="list_of_partial_class+missing",
        ),
        param(
            {"_target_": "tests.instantiate.AClass", "b": 20, "c": 30},
            {"a": 10, "d": 40},
            AClass(10, 20, 30, 40),
            id="class+override",
        ),
        param(
            {"_target_": "tests.instantiate.AClass", "b": 20, "c": 30},
            {"a": 10, "_partial_": True},
            partial(AClass, a=10, b=20, c=30),
            id="class+override+partial1",
        ),
        param(
            {
                "_target_": "tests.instantiate.AClass",
                "_partial_": True,
                "c": 30,
            },
            {"a": 10, "d": 40},
            partial(AClass, a=10, c=30, d=40),
            id="class+override+partial2",
        ),
        param(
            {"_target_": "tests.instantiate.AClass", "b": 200, "c": "${b}"},
            {"a": 10, "b": 99, "d": 40},
            AClass(10, 99, 99, 40),
            id="class+override+interpolation",
        ),
        param(
            {"_target_": "tests.instantiate.AClass", "b": 200, "c": "${b}"},
            {"a": 10, "b": 99, "_partial_": True},
            partial(AClass, a=10, b=99, c=99),
            id="class+override+interpolation+partial1",
        ),
        param(
            {
                "_target_": "tests.instantiate.AClass",
                "b": 200,
                "_partial_": True,
                "c": "${b}",
            },
            {"a": 10, "b": 99},
            partial(AClass, a=10, b=99, c=99),
            id="class+override+interpolation+partial2",
        ),
        # Check class and static methods
        param(
            {"_target_": "tests.instantiate.ASubclass.class_method", "_partial_": True},
            {},
            partial(ASubclass.class_method),
            id="class_method+partial",
        ),
        param(
            {"_target_": "tests.instantiate.ASubclass.class_method", "y": 10},
            {},
            ASubclass(11),
            id="class_method",
        ),
        param(
            {"_target_": "tests.instantiate.AClass.static_method", "_partial_": True},
            {},
            partial(AClass.static_method),
            id="static_method+partial",
        ),
        param(
            {
                "_target_": "tests.instantiate.AClass.static_method",
                "_partial_": True,
                "y": "???",
            },
            {},
            partial(AClass.static_method),
            id="static_method+partial+missing",
        ),
        param(
            {"_target_": "tests.instantiate.AClass.static_method", "z": 43},
            {},
            43,
            id="static_method",
        ),
        # Check nested types and static methods
        param(
            {"_target_": "tests.instantiate.NestingClass"},
            {},
            NestingClass(ASubclass(10)),
            id="class_with_nested_class",
        ),
        param(
            {"_target_": "tests.instantiate.nesting.a.class_method", "_partial_": True},
            {},
            partial(ASubclass.class_method),
            id="class_method_on_an_object_nested_in_a_global+partial",
        ),
        param(
            {"_target_": "tests.instantiate.nesting.a.class_method", "y": 10},
            {},
            ASubclass(11),
            id="class_method_on_an_object_nested_in_a_global",
        ),
        param(
            {
                "_target_": "tests.instantiate.nesting.a.static_method",
                "_partial_": True,
            },
            {},
            partial(ASubclass.static_method),
            id="static_method_on_an_object_nested_in_a_global+partial",
        ),
        param(
            {"_target_": "tests.instantiate.nesting.a.static_method", "z": 43},
            {},
            43,
            id="static_method_on_an_object_nested_in_a_global",
        ),
        # Check that default value is respected
        param(
            {"_target_": "tests.instantiate.AClass"},
            {"a": 10, "b": 20, "_partial_": True, "d": "new_default"},
            partial(AClass, a=10, b=20, d="new_default"),
            id="instantiate_respects_default_value+partial",
        ),
        param(
            {"_target_": "tests.instantiate.AClass"},
            {"a": 10, "b": 20, "c": 30},
            AClass(10, 20, 30, "default_value"),
            id="instantiate_respects_default_value",
        ),
        # call a function from a module
        param(
            {
                "_target_": "tests.instantiate.module_function",
                "_partial_": True,
            },
            {},
            partial(module_function),
            id="call_function_in_module",
        ),
        param(
            {"_target_": "tests.instantiate.module_function", "x": 43},
            {},
            43,
            id="call_function_in_module",
        ),
        # Check builtins
        param(
            {"_target_": "builtins.int", "base": 2, "_partial_": True},
            {},
            partial(int, base=2),
            id="builtin_types+partial",
        ),
        param(
            {"_target_": "builtins.str", "object": 43},
            {},
            "43",
            id="builtin_types",
        ),
        # passthrough
        param(
            {"_target_": "tests.instantiate.AClass"},
            {"a": 10, "b": 20, "c": 30},
            AClass(a=10, b=20, c=30),
            id="passthrough",
        ),
        param(
            {"_target_": "tests.instantiate.AClass"},
            {"a": 10, "b": 20, "_partial_": True},
            partial(AClass, a=10, b=20),
            id="passthrough+partial",
        ),
        param(
            {"_target_": "tests.instantiate.AClass"},
            {"a": 10, "b": 20, "c": 30, "d": {"x": IllegalType()}},
            AClass(a=10, b=20, c=30, d={"x": IllegalType()}),
            id="oc_incompatible_passthrough",
        ),
        param(
            {"_target_": "tests.instantiate.AClass", "_partial_": True},
            {"a": 10, "b": 20, "d": {"x": IllegalType()}},
            partial(AClass, a=10, b=20, d={"x": IllegalType()}),
            id="oc_incompatible_passthrough+partial",
        ),
        param(
            {"_target_": "tests.instantiate.AClass", "_partial_": True},
            {
                "a": 10,
                "b": 20,
                "d": {"x": [10, IllegalType()]},
            },
            partial(AClass, a=10, b=20, d={"x": [10, IllegalType()]}),
            id="passthrough:list+partial",
        ),
        param(
            {"_target_": "tests.instantiate.AClass"},
            {
                "a": 10,
                "b": 20,
                "c": 30,
                "d": {"x": [10, IllegalType()]},
            },
            AClass(a=10, b=20, c=30, d={"x": [10, IllegalType()]}),
            id="passthrough:list",
        ),
        param(
            UntypedPassthroughConf,
            {"a": IllegalType()},
            UntypedPassthroughClass(a=IllegalType()),
            id="untyped_passthrough",
        ),
        param(
            KeywordsInParamsClass,
            {"target": "foo", "partial": "bar"},
            KeywordsInParamsClass(target="foo", partial="bar"),
            id="keywords_in_params",
        ),
        param([], {}, [], id="list_as_toplevel0"),
        param(
            [
                {
                    "_target_": "tests.instantiate.AClass",
                    "a": 10,
                    "b": 20,
                    "c": 30,
                    "d": 40,
                },
                {
                    "_target_": "tests.instantiate.BClass",
                    "a": 50,
                    "b": 60,
                    "c": 70,
                    "d": 80,
                },
            ],
            {},
            [AClass(10, 20, 30, 40), BClass(50, 60, 70, 80)],
            id="list_as_toplevel2",
        ),
    ],
)
def test_class_instantiate(
    instantiate_func: Any,
    config: Any,
    passthrough: Dict[str, Any],
    expected: Any,
    recursive: bool,
) -> Any:
    passthrough["_recursive_"] = recursive
    original_config_str = str(config)
    obj = instantiate_func(config, **passthrough)
    assert partial_equal(obj, expected)
    assert str(config) == original_config_str


def test_callsite_override_is_visible_to_configured_interpolation(
    instantiate_func: Any,
) -> None:
    config = {
        "_target_": "tests.instantiate.ArgsClass",
        "base": 10,
        "middle": "${base}",
        "derived": "${middle}",
    }

    result = instantiate_func(config, base=20)

    assert result.kwargs == {"base": 20, "middle": 20, "derived": 20}


def test_callsite_override_is_visible_through_absolute_interpolation(
    instantiate_func: Any,
) -> None:
    config = OmegaConf.create(
        {
            "node": {
                "_target_": "tests.instantiate.ArgsClass",
                "base": 10,
                "derived": "${node.base}",
            }
        }
    )

    result = instantiate_func(config.node, base=20)

    assert result.kwargs == {"base": 20, "derived": 20}
    assert config.node.base == 10


def test_callsite_runtime_object_is_visible_to_configured_interpolation(
    instantiate_func: Any,
) -> None:
    base = Parameters([1, 2, 3])

    result = instantiate_func(
        {
            "_target_": "tests.instantiate.ArgsClass",
            "base": "configured",
            "derived": "${base}",
        },
        base=base,
    )

    assert result.kwargs["base"] is base
    assert result.kwargs["derived"] is base


def test_callsite_override_storage_survives_nested_reinstantiation(
    instantiate_func: Any,
) -> None:
    config = OmegaConf.create(
        {
            "_target_": "builtins.dict",
            "_recursive_": False,
            "base": 10,
            "child": {
                "_target_": "builtins.dict",
                "value": "${..base}",
            },
        }
    )

    result = instantiate_func(config, base=20)
    child = result["child"]

    assert child.value == 20
    assert instantiate_func(child, extra=1) == {"value": 20, "extra": 1}
    assert config.base == 10


def test_callsite_override_resolver_token_uses_normalized_path() -> None:
    config = OmegaConf.create(
        {
            "_target_": "tests.instantiate.ArgsClass",
            "base": {"value": 10},
        }
    )

    copied = _instantiate2._copy_config_with_override_interpolations(
        config, {"base": {"value": 20}}
    )

    assert copied.base._get_node("value")._value() == (
        "${hydra.instantiate_override:base_value}"
    )


@mark.parametrize(
    ("key", "token"),
    [
        param("123", "value_123", id="integer"),
        param("true", "value_true", id="boolean"),
        param("nan", "value_nan", id="float"),
    ],
)
def test_callsite_override_resolver_token_is_not_parsed_as_primitive(
    key: str, token: str
) -> None:
    config = OmegaConf.create({key: 10})

    copied = _instantiate2._copy_config_with_override_interpolations(config, {key: 20})

    node = copied._get_node(key)
    assert node is not None
    assert node._value() == f"${{hydra.instantiate_override:{token}}}"
    assert copied[key] == 20


def test_callsite_override_restores_internal_resolver_after_clear() -> None:
    OmegaConf.clear_resolver(_instantiate2._INSTANTIATE_OVERRIDE_RESOLVER)

    result = _instantiate2.instantiate(
        {
            "_target_": "builtins.dict",
            "base": 10,
            "derived": "${base}",
        },
        base=20,
        _target_whitelist_=UNSAFE_ALLOW_ALL_TARGETS,
    )

    assert result == {"base": 20, "derived": 20}


def test_partial_with_missing(instantiate_func: Any) -> Any:
    config = {
        "_target_": "tests.instantiate.AClass",
        "_partial_": True,
        "a": "???",
        "b": 20,
        "c": 30,
    }
    original_config_str = str(config)
    partial_obj = instantiate_func(config)
    assert partial_equal(partial_obj, partial(AClass, b=20, c=30))
    obj = partial_obj(a=10)
    assert partial_equal(obj, AClass(a=10, b=20, c=30))
    assert str(config) == original_config_str


def test_instantiate_with_missing(instantiate_func: Any) -> Any:
    config = {
        "_target_": "tests.instantiate.AClass",
        "a": "???",
        "b": 20,
        "c": 30,
    }
    with raises(MissingMandatoryValue, match=re.escape("Missing mandatory value: a")):
        instantiate_func(config)


@mark.parametrize(
    "value",
    [
        param("???", id="missing"),
        param("${configured}", id="interpolation"),
        param({"nested": "???"}, id="nested_missing"),
        param({"nested": "${configured}"}, id="nested_interpolation"),
        param(["???"], id="list_missing"),
        param(("${configured}",), id="tuple_interpolation"),
    ],
)
def test_callsite_override_rejects_omegaconf_syntax(
    instantiate_func: Any, value: Any
) -> None:
    config = {
        "_target_": "tests.instantiate.ArgsClass",
        "configured": 10,
    }

    with raises(InstantiationException, match="Call-site override"):
        instantiate_func(config, value=value)


@mark.parametrize(
    "value", [param("???", id="missing"), param("${value}", id="interpolation")]
)
def test_callsite_positional_override_rejects_omegaconf_syntax(
    instantiate_func: Any, value: str
) -> None:
    config = {"_target_": "tests.instantiate.ArgsClass"}

    with raises(
        InstantiationException,
        match=re.escape("Call-site override '_args_.0'"),
    ):
        instantiate_func(config, value)


def test_callsite_override_does_not_inspect_structured_runtime_value(
    instantiate_func: Any,
) -> None:
    @dataclass
    class DictRuntimeValue(dict):  # type: ignore[type-arg]
        pass

    @attr.define(slots=False)
    class ListRuntimeValue(list):  # type: ignore[type-arg]
        pass

    mapping = DictRuntimeValue()
    mapping["value"] = "${literal}"
    sequence = ListRuntimeValue()
    sequence.append("???")

    for value in (mapping, sequence):
        result = instantiate_func(
            {"_target_": "tests.instantiate.ArgsClass"},
            value=value,
        )

        assert result.kwargs["value"] is value


def test_none_cases(
    instantiate_func: Any,
) -> Any:
    assert instantiate_func(None) is None

    cfg = {
        "_target_": "tests.instantiate.ArgsClass",
        "none_dict": DictConfig(None),
        "none_list": ListConfig(None),
        "dict": {
            "field": 10,
            "none_dict": DictConfig(None),
            "none_list": ListConfig(None),
        },
        "list": [
            10,
            DictConfig(None),
            ListConfig(None),
        ],
    }
    original_config_str = str(cfg)
    ret = instantiate_func(cfg)
    assert ret.kwargs["none_dict"] is None
    assert ret.kwargs["none_list"] is None
    assert ret.kwargs["dict"].field == 10
    assert ret.kwargs["dict"].none_dict is None
    assert ret.kwargs["dict"].none_list is None
    assert ret.kwargs["list"][0] == 10
    assert ret.kwargs["list"][1] is None
    assert ret.kwargs["list"][2] is None
    assert str(cfg) == original_config_str


def test_callsite_override_materializes_none_root(instantiate_func: Any) -> None:
    config = DictConfig(None)

    result = instantiate_func(config, value=10)

    assert result == {"value": 10}
    assert config._is_none()


@mark.parametrize("convert_to_list", [True, False])
@mark.parametrize(
    "input_conf, passthrough, expected",
    [
        param(
            {
                "node": {
                    "_target_": "tests.instantiate.AClass",
                    "a": "${value}",
                    "b": 20,
                    "c": 30,
                    "d": 40,
                },
                "value": 99,
            },
            {},
            AClass(99, 20, 30, 40),
            id="interpolation_into_parent",
        ),
        param(
            {
                "node": {
                    "_target_": "tests.instantiate.AClass",
                    "_partial_": True,
                    "a": "${value}",
                    "b": 20,
                },
                "value": 99,
            },
            {},
            partial(AClass, a=99, b=20),
            id="interpolation_into_parent_partial",
        ),
        param(
            {
                "A": {"_target_": "tests.instantiate.add_values", "a": 1, "b": 2},
                "node": {
                    "_target_": "tests.instantiate.add_values",
                    "_partial_": True,
                    "a": "${A}",
                },
            },
            {},
            partial(add_values, a=3),
            id="interpolation_from_recursive_partial",
        ),
        param(
            {
                "A": {"_target_": "tests.instantiate.add_values", "a": 1, "b": 2},
                "node": {
                    "_target_": "tests.instantiate.add_values",
                    "a": "${A}",
                    "b": 3,
                },
            },
            {},
            6,
            id="interpolation_from_recursive",
        ),
        param(
            {
                "my_id": 5,
                "node": {
                    "b": "${foo_b}",
                },
                "foo_b": {
                    "unique_id": "${my_id}",
                },
            },
            {},
            OmegaConf.create({"b": {"unique_id": 5}}),
            id="interpolation_from_parent_with_interpolation",
        ),
        param(
            {
                "my_id": 5,
                "node": "${foo_b}",
                "foo_b": {
                    "unique_id": "${my_id}",
                },
            },
            {},
            OmegaConf.create({"unique_id": 5}),
            id="interpolation_from_parent_with_interpolation",
        ),
        param(
            DictConfig(
                {
                    "username": "test_user",
                    "node": {
                        "_target_": "tests.instantiate.TargetWithInstantiateInInit",
                        "_recursive_": False,
                        "user_config": {
                            "_target_": "tests.instantiate.User",
                            "name": "${foo_b.username}",
                            "age": 40,
                        },
                    },
                    "foo_b": {
                        "username": "${username}",
                    },
                }
            ),
            {},
            TargetWithInstantiateInInit(
                user_config=None, user=User(name="test_user", age=40)
            ),
            id="target_with_instantiate_in_init",
        ),
    ],
)
def test_interpolation_accessing_parent(
    instantiate_func: Any,
    input_conf: Any,
    passthrough: Dict[str, Any],
    expected: Any,
    convert_to_list: bool,
) -> Any:
    if convert_to_list:
        input_conf = copy.deepcopy(input_conf)
        input_conf["node"] = [input_conf["node"]]
    cfg_copy = OmegaConf.create(input_conf)
    input_conf = OmegaConf.create(input_conf)
    original_config_str = str(input_conf)
    if convert_to_list:
        obj = instantiate_func(input_conf.node[0], **passthrough)
    else:
        obj = instantiate_func(input_conf.node, **passthrough)
    if isinstance(expected, partial):
        assert partial_equal(obj, expected)
    else:
        assert obj == expected
    assert input_conf == cfg_copy
    assert str(input_conf) == original_config_str


def test_instantiate_does_not_copy_unrelated_root_siblings(
    instantiate_func: Any,
) -> None:
    class Uncopyable:
        def __deepcopy__(self, memo: Any) -> Any:
            raise AssertionError("instantiate() copied an unrelated root sibling")

    cfg = OmegaConf.create(
        {
            "node": {
                "_target_": "tests.instantiate.AClass",
                "a": "${value}",
                "b": 20,
                "c": 30,
            },
            "value": 10,
            "unrelated": Uncopyable(),
        },
        flags={"allow_objects": True},
    )

    assert instantiate_func(cfg.node, b=99) == AClass(a=10, b=99, c=30)


def test_non_recursive_config_argument_is_passed_directly_without_resolving(
    instantiate_func: Any,
) -> None:
    cfg = OmegaConf.create(
        {
            "node": {
                "_target_": "tests.instantiate.ArgsClass",
                "_recursive_": False,
                "payload": {
                    "value": 10,
                    "alias": "${.value}",
                },
            },
        },
        flags={"allow_objects": True},
    )
    OmegaConf.set_readonly(cfg, True)
    OmegaConf.set_struct(cfg, True)
    original_config = str(cfg)
    source_payload = cfg.node.payload

    result = instantiate_func(cfg.node)
    payload = result.kwargs["payload"]

    assert OmegaConf.to_container(payload, resolve=False) == {
        "value": 10,
        "alias": "${.value}",
    }
    assert payload is source_payload
    assert payload._get_parent() is cfg.node
    assert source_payload._get_parent() is cfg.node
    assert OmegaConf.is_readonly(payload)
    assert OmegaConf.is_struct(payload)
    assert payload._get_flag("allow_objects")
    assert payload.alias == 10
    assert str(cfg) == original_config


def test_non_recursive_config_argument_uses_source_resolver_cache(
    instantiate_func: Any,
) -> None:
    resolver_name = "hydra_instantiate_cached_config_argument"
    calls = 0

    def resolver() -> int:
        nonlocal calls
        calls += 1
        return calls

    OmegaConf.register_resolver(
        resolver_name,
        resolver,
        replace=True,
        use_cache=True,
    )
    cfg = OmegaConf.create(
        {
            "first": f"${{{resolver_name}:}}",
            "node": {
                "_target_": "tests.instantiate.ArgsClass",
                "_recursive_": False,
                "payload": {"value": f"${{{resolver_name}:}}"},
            },
        }
    )

    try:
        assert cfg.first == 1
        result = instantiate_func(cfg.node)
        payload = result.kwargs["payload"]

        assert payload is cfg.node.payload
        assert payload.value == 1
        assert calls == 1
    finally:
        OmegaConf.clear_resolver(resolver_name)


def test_non_recursive_runtime_config_argument_is_passed_directly_and_remains_lazy(
    instantiate_func: Any,
) -> None:
    runtime_config = OmegaConf.create(
        {
            "num_classes": -1,
            "model": {"num_class": "${num_classes}"},
        }
    )

    result = instantiate_func(
        {
            "_target_": "tests.instantiate.ArgsClass",
            "_recursive_": False,
        },
        cfg=runtime_config,
    )
    cfg = result.kwargs["cfg"]
    cfg.num_classes = 10

    assert cfg is runtime_config
    assert cfg._get_parent() is None
    assert cfg.model.num_class == 10
    assert runtime_config.num_classes == 10
    assert runtime_config.model.num_class == 10


def test_non_recursive_runtime_config_supports_late_resolver_registration(
    instantiate_func: Any,
) -> None:
    resolver_name = "hydra_instantiate_late_runtime_config"
    OmegaConf.clear_resolver(resolver_name)
    runtime_config = OmegaConf.create({"value": f"${{{resolver_name}:}}"})

    try:
        result = instantiate_func(
            {
                "_target_": "tests.instantiate.ArgsClass",
                "_recursive_": False,
            },
            cfg=runtime_config,
        )
        cfg = result.kwargs["cfg"]
        assert cfg is runtime_config
        OmegaConf.register_resolver(resolver_name, lambda: 42)

        assert OmegaConf.to_container(cfg, resolve=False) == {
            "value": f"${{{resolver_name}:}}"
        }
        assert cfg.value == 42
    finally:
        OmegaConf.clear_resolver(resolver_name)


def test_top_level_instantiation_control_keys_are_not_in_result(
    instantiate_func: Any,
) -> None:
    result = instantiate_func({"_convert_": "none", "value": 10})

    assert result == {"value": 10}
    assert "_convert_" not in result


@mark.parametrize(
    "src",
    [
        {
            "_target_": "tests.instantiate.AClass",
            "b": 200,
            "c": {"x": 10, "y": "${b}"},
        }
    ],
)
def test_class_instantiate_omegaconf_node(instantiate_func: Any, config: Any) -> Any:
    obj = instantiate_func(config, a=10, d=AnotherClass(99))
    assert obj == AClass(a=10, b=200, c={"x": 10, "y": 200}, d=AnotherClass(99))
    assert OmegaConf.is_config(obj.c)


@mark.parametrize(
    "src",
    [
        param(
            ListConfig(
                [
                    {
                        "_target_": "tests.instantiate.AClass",
                        "b": 200,
                        "c": {"x": 10, "y": "${0.b}"},
                    }
                ]
            ),
            id="list",
        ),
        param(
            OmegaConf.create(
                (
                    {
                        "_target_": "tests.instantiate.AClass",
                        "b": 200,
                        "c": {"x": 10, "y": "${0.b}"},
                    },
                )
            ),
            id="tuple",
        ),
    ],
)
def test_class_instantiate_sequence_item(instantiate_func: Any, config: Any) -> Any:
    obj = instantiate_func(config[0], a=10, d=AnotherClass(99))
    assert obj == AClass(a=10, b=200, c={"x": 10, "y": 200}, d=AnotherClass(99))
    assert OmegaConf.is_config(obj.c)


@mark.parametrize("src", [{"_target_": "tests.instantiate.Adam"}])
def test_instantiate_adam(instantiate_func: Any, config: Any) -> None:
    with raises(
        InstantiationException,
        match=r"Error in call to target 'tests\.instantiate\.Adam':\nTypeError\(.*\)",
    ):
        # can't instantiate without passing params
        instantiate_func(config)

    adam_params = Parameters([1, 2, 3])
    res = instantiate_func(config, params=adam_params)
    assert res == Adam(params=adam_params)


@mark.parametrize("is_partial", [True, False])
def test_regression_1483(instantiate_func: Any, is_partial: bool) -> None:
    """
    In 1483, call-site arguments were merged into one OmegaConf tree, so the
    ListConfig argument retained an unpicklable generator through its parent.
    Keeping call-site arguments separate leaves the ListConfig independently
    picklable without eager resolution or detachment.
    """

    def gen() -> Any:
        yield 10

    res: ArgsClass = instantiate_func(
        {"_target_": "tests.instantiate.ArgsClass"},
        _partial_=is_partial,
        gen=gen(),
        lst=[1, 2],
    )
    if is_partial:
        # res is of type functools.partial
        lst = res.keywords["lst"]  # type: ignore
    else:
        lst = res.kwargs["lst"]
    assert lst._get_parent() is None
    pickle.dumps(lst)


def test_runtime_object_override_replaces_unresolvable_config_value(
    instantiate_func: Any,
) -> None:
    runtime_value = Parameters([1, 2, 3])

    result = instantiate_func(
        {
            "_target_": "tests.instantiate.ArgsClass",
            "value": "${missing}",
        },
        value=runtime_value,
    )

    assert result.kwargs["value"] is runtime_value


@mark.parametrize(
    ("runtime_value", "expected"),
    [
        param(
            OmegaConf.create({"_target_": "tests.instantiate.AnotherClass", "x": 10}),
            AnotherClass(10),
            id="dictconfig",
        ),
        param(
            [{"_target_": "tests.instantiate.AnotherClass", "x": 10}],
            [AnotherClass(10)],
            id="native-list-with-dict",
        ),
        param(
            OmegaConf.create([{"_target_": "tests.instantiate.AnotherClass", "x": 10}]),
            [AnotherClass(10)],
            id="listconfig",
        ),
    ],
)
def test_runtime_container_override_is_instantiated(
    instantiate_func: Any, runtime_value: Any, expected: Any
) -> None:
    result = instantiate_func(
        {"_target_": "tests.instantiate.ArgsClass"}, value=runtime_value
    )

    assert result.kwargs["value"] == expected


def test_nested_runtime_object_override_replaces_unresolvable_config_value(
    instantiate_func: Any,
) -> None:
    runtime_value = Parameters([1, 2, 3])

    result = instantiate_func(
        {
            "_target_": "tests.instantiate.Tree",
            "value": 0,
            "left": {
                "_target_": "tests.instantiate.Tree",
                "value": "${missing}",
            },
        },
        left={"value": runtime_value},
    )

    assert result.left.value is runtime_value


@mark.parametrize("convert", list(ConvertMode))
@mark.parametrize("recursive", [False, True])
def test_structured_runtime_override_is_passed_through(
    instantiate_func: Any,
    convert: ConvertMode,
    recursive: bool,
) -> None:
    user = User(name="Bond", age=7)

    result = instantiate_func(
        {"_target_": "tests.instantiate.ArgsClass"},
        user=user,
        _convert_=convert,
        _recursive_=recursive,
    )

    assert result.kwargs["user"] is user


def test_structured_runtime_override_with_target_is_passed_through(
    instantiate_func: Any,
) -> None:
    @dataclass
    class RuntimeValue:
        _target_: str
        value: int
        token: InitVar[str]
        runtime_token: str = field(init=False)

        def __post_init__(self, token: str) -> None:
            self.runtime_token = token

    runtime_value = RuntimeValue(
        _target_="tests.instantiate.AnotherClass",
        value=10,
        token="secret",
    )

    result = instantiate_func(
        {"_target_": "tests.instantiate.ArgsClass"},
        value=runtime_value,
        _convert_=ConvertMode.OBJECT,
    )

    assert result.kwargs["value"] is runtime_value
    assert result.kwargs["value"].runtime_token == "secret"


def test_attrs_runtime_override_is_passed_through(instantiate_func: Any) -> None:
    @attr.define
    class RuntimeValue:
        value: int

    runtime_value = RuntimeValue(value=10)

    result = instantiate_func(
        {"_target_": "tests.instantiate.ArgsClass"},
        value=runtime_value,
        _convert_=ConvertMode.OBJECT,
    )

    assert result.kwargs["value"] is runtime_value


def test_dataclass_dict_subclass_runtime_override_is_passed_through(
    instantiate_func: Any,
) -> None:
    @dataclass
    class RuntimeValue(dict):  # type: ignore[type-arg]
        pass

    runtime_value = RuntimeValue()
    runtime_value["value"] = 10

    result = instantiate_func(
        {"_target_": "tests.instantiate.ArgsClass"},
        value=runtime_value,
    )

    assert result.kwargs["value"] is runtime_value


def test_attrs_list_subclass_runtime_override_is_passed_through(
    instantiate_func: Any,
) -> None:
    @attr.define(slots=False)
    class RuntimeValue(list):  # type: ignore[type-arg]
        pass

    runtime_value = RuntimeValue()
    runtime_value.append(10)

    result = instantiate_func(
        {"_target_": "tests.instantiate.ArgsClass"},
        value=runtime_value,
    )

    assert result.kwargs["value"] is runtime_value


def test_omegaconf_structured_runtime_override_is_instantiated(
    instantiate_func: Any,
) -> None:
    runtime_config = OmegaConf.structured(TreeConf(value=10))

    result = instantiate_func(
        {"_target_": "tests.instantiate.ArgsClass"},
        value=runtime_config,
    )

    assert result.kwargs["value"] == Tree(value=10)


def test_omegaconf_structured_runtime_override_merges_with_configured_value(
    instantiate_func: Any,
) -> None:
    @dataclass
    class TreeValueOverride:
        value: int

    runtime_config = OmegaConf.structured(TreeValueOverride(value=20))

    result = instantiate_func(
        {
            "_target_": "tests.instantiate.ArgsClass",
            "value": {
                "_target_": "tests.instantiate.Tree",
                "value": 10,
                "left": {
                    "_target_": "tests.instantiate.Tree",
                    "value": 30,
                },
            },
        },
        value=runtime_config,
    )

    assert result.kwargs["value"] == Tree(value=20, left=Tree(value=30))


def test_regression_2350_dict_override_replaces_configured_dict(
    instantiate_func: Any,
) -> None:
    @dataclass
    class Config:
        _target_: str = "tests.instantiate.ArgsClass"
        value: Dict[str, int] = field(default_factory=lambda: {"configured": 10})

    result = instantiate_func(
        Config,
        value={"runtime": 20},
    )

    assert result.kwargs["value"] == {"runtime": 20}


def test_dict_override_for_unconfigured_target_parameter(
    instantiate_func: Any,
) -> None:
    @dataclass
    class Config:
        _target_: str = "tests.instantiate.ArgsClass"

    result = instantiate_func(Config, extra={"value": 10})

    assert result.kwargs["extra"] == {"value": 10}


@mark.parametrize(
    "recursive,expected",
    [
        param(
            False,
            {
                "_target_": "tests.instantiate.Tree",
                "value": 20,
                "left": {
                    "_target_": "tests.instantiate.Tree",
                    "value": 30,
                },
            },
            id="not_recursive",
        ),
        param(True, Tree(value=20, left=Tree(value=30)), id="recursive"),
    ],
)
def test_dict_override_merges_configured_target(
    instantiate_func: Any, recursive: bool, expected: Any
) -> None:
    """
    A configured target keeps merge behavior: the call-site dict overrides the
    arguments it names and leaves the rest of the target config in place.
    """
    result = instantiate_func(
        {
            "_target_": "tests.instantiate.ArgsClass",
            "value": {
                "_target_": "tests.instantiate.Tree",
                "value": 10,
                "left": {
                    "_target_": "tests.instantiate.Tree",
                    "value": 30,
                },
            },
        },
        value={"value": 20},
        _recursive_=recursive,
    )

    value = result.kwargs["value"]
    assert value == expected
    if not recursive:
        assert isinstance(value, DictConfig)


def test_dict_override_merges_interpolated_configured_target(
    instantiate_func: Any,
) -> None:
    result = instantiate_func(
        {
            "_target_": "tests.instantiate.ArgsClass",
            "template": {
                "_target_": "tests.instantiate.Tree",
                "value": 10,
                "left": {
                    "_target_": "tests.instantiate.Tree",
                    "value": 30,
                },
            },
            "value": "${template}",
        },
        value={"value": 20},
    )

    assert result.kwargs["value"] == Tree(value=20, left=Tree(value=30))


@mark.parametrize(
    "overrides",
    [
        param(
            {
                "value": {"runtime": 20},
                "template": {"configured": 10},
            },
            id="dependent-first",
        ),
        param(
            {
                "template": {"configured": 10},
                "value": {"runtime": 20},
            },
            id="dependency-first",
        ),
    ],
)
def test_dict_override_merge_is_independent_of_callsite_argument_order(
    instantiate_func: Any, overrides: Dict[str, Any]
) -> None:
    result = instantiate_func(
        {
            "_target_": "tests.instantiate.ArgsClass",
            "template": {"_target_": "builtins.dict", "original": 0},
            "value": "${template}",
        },
        **overrides,
    )

    assert result.kwargs == {
        "template": {"original": 0, "configured": 10},
        "value": {"original": 0, "configured": 10, "runtime": 20},
    }


def test_dict_override_merges_interpolated_structured_config(
    instantiate_func: Any,
) -> None:
    @dataclass
    class Value:
        count: int = 10
        label: str = "configured"

    result = instantiate_func(
        {
            "_target_": "tests.instantiate.ArgsClass",
            "template": OmegaConf.structured(Value),
            "value": "${template}",
        },
        value={"count": 20},
    )

    value = result.kwargs["value"]
    assert OmegaConf.get_type(value) is Value
    assert value == {"count": 20, "label": "configured"}


def test_dict_override_replaces_interpolated_configured_dict(
    instantiate_func: Any,
) -> None:
    result = instantiate_func(
        {
            "_target_": "tests.instantiate.ArgsClass",
            "template": {"configured": 10},
            "value": "${template}",
        },
        value={"runtime": 20},
    )

    assert result.kwargs["value"] == {"runtime": 20}


def test_dict_override_replaces_unresolvable_configured_interpolation(
    instantiate_func: Any,
) -> None:
    result = instantiate_func(
        {
            "_target_": "tests.instantiate.ArgsClass",
            "value": "${missing}",
        },
        value={"runtime": 20},
    )

    assert result.kwargs["value"] == {"runtime": 20}


def test_dict_override_merges_resolver_result_target(
    instantiate_func: Any,
) -> None:
    resolver_name = "hydra_instantiate_target_mapping"
    OmegaConf.register_resolver(
        resolver_name,
        lambda: {"_target_": "builtins.dict", "configured": 10},
    )
    try:
        result = instantiate_func(
            {
                "_target_": "tests.instantiate.ArgsClass",
                "value": f"${{{resolver_name}:}}",
            },
            value={"runtime": 20},
        )
    finally:
        OmegaConf.clear_resolver(resolver_name)

    assert result.kwargs["value"] == {"configured": 10, "runtime": 20}


def test_dict_override_merges_structured_config_fields(
    instantiate_func: Any,
) -> None:
    @dataclass
    class Child:
        count: int = 10
        label: str = "configured"

    @dataclass
    class Value:
        count: int = 10
        derived: int = "${.count}"  # type: ignore[assignment]
        label: str = "configured"
        child: Child = field(default_factory=Child)
        tags: Dict[str, str] = field(
            default_factory=lambda: {"env": "prod", "team": "ml"}
        )

    @dataclass
    class Config:
        _target_: str = "tests.instantiate.ArgsClass"
        value: Value = field(default_factory=Value)

    cfg = OmegaConf.structured(Config)
    OmegaConf.set_readonly(cfg, True)
    result = instantiate_func(
        cfg,
        value={
            "count": "20",
            "child": {"count": "30"},
            "tags": {"env": "dev"},
        },
    )

    value = result.kwargs["value"]
    assert OmegaConf.get_type(value) is Value
    assert value == {
        "count": 20,
        "derived": 20,
        "label": "configured",
        "child": {"count": 30, "label": "configured"},
        "tags": {"env": "dev", "team": "ml"},
    }
    assert OmegaConf.get_type(value.child) is Child
    assert cfg.value == {
        "count": 10,
        "derived": 10,
        "label": "configured",
        "child": {"count": 10, "label": "configured"},
        "tags": {"env": "prod", "team": "ml"},
    }
    assert OmegaConf.is_readonly(cfg)
    assert OmegaConf.is_interpolation(cfg.value, "derived")

    with raises(ValidationError):
        instantiate_func(Config, value={"count": "not an integer"})


@mark.parametrize("convert", list(ConvertMode))
@mark.parametrize("runtime_type", ["dataclass", "attrs"])
@mark.parametrize("container", ["direct", "mapping", "list", "tuple"])
def test_structured_config_dict_override_preserves_nested_runtime_object(
    instantiate_func: Any,
    container: str,
    runtime_type: str,
    convert: ConvertMode,
) -> None:
    @dataclass
    class RuntimeValue:
        _target_: str
        value: int
        token: InitVar[str]
        runtime_token: str = field(init=False)

        def __post_init__(self, token: str) -> None:
            self.runtime_token = token

    @attr.define
    class AttrsRuntimeValue:
        _target_: str
        value: int

    @dataclass
    class Value:
        payload: Any = None

    @dataclass
    class Config:
        _target_: str = "tests.instantiate.ArgsClass"
        value: Value = field(default_factory=Value)

    runtime_value = (
        RuntimeValue(
            _target_="tests.instantiate.AnotherClass",
            value=10,
            token="secret",
        )
        if runtime_type == "dataclass"
        else AttrsRuntimeValue("tests.instantiate.AnotherClass", 10)
    )
    payload = {
        "direct": runtime_value,
        "mapping": {"runtime": runtime_value},
        "list": [runtime_value],
        "tuple": (runtime_value,),
    }[container]

    result = instantiate_func(Config, value={"payload": payload}, _convert_=convert)
    value = result.kwargs["value"]
    actual = value.payload if hasattr(value, "payload") else value["payload"]
    if container == "mapping":
        actual = actual["runtime"]
    elif container in ("list", "tuple"):
        actual = actual[0]

    assert actual is runtime_value


@mark.parametrize("convert", list(ConvertMode))
def test_structured_config_dict_override_preserves_typed_runtime_object(
    instantiate_func: Any, convert: ConvertMode
) -> None:
    @dataclass
    class Child:
        value: int = 10

    @dataclass
    class Value:
        child: Child = field(default_factory=Child)

    @dataclass
    class Config:
        _target_: str = "tests.instantiate.ArgsClass"
        value: Value = field(default_factory=Value)

    child = Child(value=20)
    result = instantiate_func(Config, value={"child": child}, _convert_=convert)
    value = result.kwargs["value"]

    assert (value.child if hasattr(value, "child") else value["child"]) is child


@mark.parametrize("container", ["mapping", "sequence"])
def test_nested_target_result_preserves_runtime_object(
    instantiate_func: Any, container: str
) -> None:
    @dataclass
    class RuntimeValue:
        value: int

    runtime_value = RuntimeValue(value=10)
    target = OmegaConf.create({"_target_": "builtins.dict"})
    target["object"] = structured_config_object_node(runtime_value)
    config = {"result": target} if container == "mapping" else [target]

    result = instantiate_func(config)
    target_result = result["result"] if container == "mapping" else result[0]

    assert target_result["object"] is runtime_value


def test_dict_override_materializes_structured_config_with_allow_objects(
    instantiate_func: Any,
) -> None:
    class RuntimeObject: ...

    @dataclass
    class Value:
        payload: Any = RuntimeObject()

    @dataclass
    class Config:
        _target_: str = "tests.instantiate.ArgsClass"
        value: Optional[Value] = None

    result = instantiate_func(Config, value={})

    value = result.kwargs["value"]
    assert OmegaConf.get_type(value) is Value
    assert isinstance(value.payload, RuntimeObject)


@mark.parametrize(
    "configured_value",
    [param(None, id="none"), param(MISSING, id="missing")],
)
def test_dict_override_materialized_structured_config_resolves_outside_subtree(
    instantiate_func: Any, configured_value: Any
) -> None:
    @dataclass
    class Value:
        count: int = 10
        inherited: int = "${..template}"  # type: ignore[assignment]

    @dataclass
    class Config:
        _target_: str = "tests.instantiate.ArgsClass"
        template: int = 20
        value: Optional[Value] = configured_value

    result = instantiate_func(Config, value={"count": 30})

    assert result.kwargs["value"] == {"count": 30, "inherited": 20}


@mark.parametrize(
    "recursive,expected",
    [
        param(
            False,
            {
                "_target_": "tests.instantiate.Tree",
                "value": 20,
                "left": {
                    "_target_": "tests.instantiate.Tree",
                    "value": 30,
                },
            },
            id="not_recursive",
        ),
        param(True, Tree(value=20, left=Tree(value=30)), id="recursive"),
    ],
)
def test_dict_override_merges_target_nested_in_structured_config(
    instantiate_func: Any, recursive: bool, expected: Any
) -> None:
    @dataclass
    class Value:
        child: Dict[str, Any] = field(
            default_factory=lambda: {
                "_target_": "tests.instantiate.Tree",
                "value": 10,
                "left": {
                    "_target_": "tests.instantiate.Tree",
                    "value": 30,
                },
            }
        )

    @dataclass
    class Config:
        _target_: str = "tests.instantiate.ArgsClass"
        value: Value = field(default_factory=Value)

    result = instantiate_func(
        Config,
        value={"child": {"value": 20}},
        _recursive_=recursive,
    )

    assert result.kwargs["value"].child == expected


def test_dict_override_merges_non_target_config(instantiate_func: Any) -> None:
    result = instantiate_func(
        {"value": {"configured": 10, "overridden": 20}},
        value={"overridden": 30},
    )

    assert result == {"value": {"configured": 10, "overridden": 30}}


def test_runtime_override_is_not_coerced_by_structured_config(
    instantiate_func: Any,
) -> None:
    result = instantiate_func(
        AdamConf(),
        params=Parameters([]),
        lr="runtime value",
    )

    assert result.lr == "runtime value"


@mark.parametrize("with_override", [False, True])
def test_nested_target_can_register_resolver_for_later_argument(
    instantiate_func: Any, with_override: bool
) -> None:
    resolver_name = "hydra_instantiate_delayed_resolution"
    OmegaConf.clear_resolver(resolver_name)
    try:
        result = instantiate_func(
            {
                "_target_": "tests.instantiate.ArgsClass",
                "first": {
                    "_target_": (
                        "tests.instantiate.test_instantiate.register_test_resolver"
                    ),
                    "name": resolver_name,
                    "value": 10,
                },
                "second": f"${{{resolver_name}:}}",
            },
            **({"callsite": 20} if with_override else {}),
        )
    finally:
        OmegaConf.clear_resolver(resolver_name)

    expected = {"first": 10, "second": 10}
    if with_override:
        expected["callsite"] = 20
    assert result.kwargs == expected


@mark.parametrize(
    "is_partial,expected_params",
    [(True, Parameters([1, 2, 3])), (False, partial(Parameters))],
)
def test_instantiate_adam_conf(
    instantiate_func: Any, is_partial: bool, expected_params: Any
) -> None:
    with raises(
        InstantiationException,
        match=r"Error in call to target 'tests\.instantiate\.Adam':\nTypeError\(.*\)",
    ):
        # can't instantiate without passing params
        instantiate_func(AdamConf())

    adam_params = expected_params
    res = instantiate_func(AdamConf(lr=0.123), params=adam_params)
    expected = Adam(lr=0.123, params=adam_params)
    if is_partial:
        partial_equal(res.params, expected.params)
    else:
        assert res.params == expected.params
    assert res.lr == expected.lr
    assert isinstance(res.betas, TupleConfig)
    assert res.betas == expected.betas
    assert res.eps == expected.eps
    assert res.weight_decay == expected.weight_decay
    assert res.amsgrad == expected.amsgrad


def test_instantiate_adam_conf_with_convert(instantiate_func: Any) -> None:
    adam_params = Parameters([1, 2, 3])
    res = instantiate_func(AdamConf(lr=0.123), params=adam_params, _convert_="all")
    expected = Adam(lr=0.123, params=adam_params)
    assert res.params == expected.params
    assert res.lr == expected.lr
    assert isinstance(res.betas, tuple)
    assert res.betas == expected.betas
    assert res.eps == expected.eps
    assert res.weight_decay == expected.weight_decay
    assert res.amsgrad == expected.amsgrad


def test_instantiate_with_missing_module(instantiate_func: Any) -> None:
    _target_ = "tests.instantiate.ClassWithMissingModule"
    with raises(
        InstantiationException,
        match=dedent(
            rf"""
            Error in call to target '{re.escape(_target_)}':
            ModuleNotFoundError\("No module named 'some_missing_module'",?\)"""
        ).strip(),
    ):
        # can't instantiate when importing a missing module
        instantiate_func({"_target_": _target_})


def test_instantiate_target_raising_exception_taking_no_arguments(
    instantiate_func: Any,
) -> None:
    _target_ = "tests.instantiate.raise_exception_taking_no_argument"
    with raises(
        InstantiationException,
        match=(
            dedent(rf"""
                Error in call to target '{re.escape(_target_)}':
                ExceptionTakingNoArgument\('Err message',?\)""").strip()
        ),
    ):
        instantiate_func({}, _target_=_target_)


def test_instantiate_target_raising_exception_taking_no_arguments_nested(
    instantiate_func: Any,
) -> None:
    _target_ = "tests.instantiate.raise_exception_taking_no_argument"
    with raises(
        InstantiationException,
        match=(
            dedent(rf"""
                Error in call to target '{re.escape(_target_)}':
                ExceptionTakingNoArgument\('Err message',?\)
                full_key: foo
                """).strip()
        ),
    ):
        instantiate_func({"foo": {"_target_": _target_}})


@mark.parametrize(
    ("config", "sequence_type"),
    [
        param(
            [{"_target_": "tests.instantiate.AClass", "a": 10, "b": 20, "c": 30}],
            "list",
            id="list",
        ),
        param(
            ({"_target_": "tests.instantiate.AClass", "a": 10, "b": 20, "c": 30},),
            "tuple",
            id="tuple",
        ),
    ],
)
def test_toplevel_sequence_partial_not_allowed(
    instantiate_func: Any, config: Any, sequence_type: str
) -> None:
    with raises(
        InstantiationException,
        match=re.escape(
            "The _partial_ keyword is not compatible with "
            f"top-level {sequence_type} instantiation"
        ),
    ):
        instantiate_func(config, _partial_=True)


@mark.parametrize(
    "config",
    [
        param(
            ({"_target_": "tests.instantiate.AClass", "a": 10, "b": 20, "c": 30},),
            id="native",
        ),
        param(
            OmegaConf.create(
                (
                    {
                        "_target_": "tests.instantiate.AClass",
                        "a": 10,
                        "b": 20,
                        "c": 30,
                    },
                )
            ),
            id="tuple-config",
        ),
    ],
)
@mark.parametrize(
    ("convert", "expected_type"),
    [
        param(ConvertMode.NONE, TupleConfig, id="none"),
        param(ConvertMode.PARTIAL, tuple, id="partial"),
        param(ConvertMode.OBJECT, tuple, id="object"),
        param(ConvertMode.ALL, tuple, id="all"),
    ],
)
def test_instantiate_toplevel_tuple(
    instantiate_func: Any, config: Any, convert: ConvertMode, expected_type: Any
) -> None:
    result = instantiate_func(config, _convert_=convert)

    assert isinstance(result, expected_type)
    assert result[0] == AClass(a=10, b=20, c=30)


@mark.parametrize("is_partial", [True, False])
def test_pass_extra_variables(instantiate_func: Any, is_partial: bool) -> None:
    cfg = OmegaConf.create(
        {
            "_target_": "tests.instantiate.AClass",
            "a": 10,
            "b": 20,
            "_partial_": is_partial,
        }
    )
    if is_partial:
        assert partial_equal(
            instantiate_func(cfg, c=30), partial(AClass, a=10, b=20, c=30)
        )
    else:
        assert instantiate_func(cfg, c=30) == AClass(a=10, b=20, c=30)


@mark.parametrize(
    "target, expected",
    [
        param(module_function2, lambda x: x == "fn return", id="fn"),
        param(OuterClass, lambda x: isinstance(x, OuterClass), id="OuterClass"),
        param(
            OuterClass.method,
            lambda x: x == "OuterClass.method return",
            id="classmethod",
        ),
        param(
            OuterClass.Nested, lambda x: isinstance(x, OuterClass.Nested), id="nested"
        ),
        param(
            OuterClass.Nested.method,
            lambda x: x == "OuterClass.Nested.method return",
            id="nested_method",
        ),
    ],
)
def test_instantiate_with_callable_target_keyword(
    instantiate_func: Any, target: Callable[[], None], expected: Callable[[Any], bool]
) -> None:
    ret = instantiate_func({}, _target_=target)
    assert expected(ret)


@mark.parametrize(
    "src, passthrough, expected",
    [
        # direct
        param(
            {
                "_target_": "tests.instantiate.Tree",
                "value": 1,
                "left": {
                    "_target_": "tests.instantiate.Tree",
                    "value": 21,
                },
                "right": {
                    "_target_": "tests.instantiate.Tree",
                    "value": 22,
                },
            },
            {},
            Tree(value=1, left=Tree(value=21), right=Tree(value=22)),
            id="recursive:direct:dict",
        ),
        param(
            {"_target_": "tests.instantiate.Tree"},
            {"value": 1},
            Tree(value=1),
            id="recursive:direct:dict:passthrough",
        ),
        param(
            {"_target_": "tests.instantiate.Tree"},
            {"value": 1, "left": {"_target_": "tests.instantiate.Tree", "value": 2}},
            Tree(value=1, left=Tree(2)),
            id="recursive:direct:dict:passthrough",
        ),
        param(
            {"_target_": "tests.instantiate.Tree"},
            {
                "value": 1,
                "left": {"_target_": "tests.instantiate.Tree", "value": 2},
                "right": {"_target_": "tests.instantiate.Tree", "value": 3},
            },
            Tree(value=1, left=Tree(2), right=Tree(3)),
            id="recursive:direct:dict:passthrough",
        ),
        param(
            {"_target_": "tests.instantiate.Tree"},
            {"value": IllegalType()},
            Tree(value=IllegalType()),
            id="recursive:direct:dict:passthrough:incompatible_value",
        ),
        param(
            {"_target_": "tests.instantiate.Tree"},
            {
                "value": 1,
                "left": {"_target_": "tests.instantiate.Tree", "value": IllegalType()},
            },
            Tree(value=1, left=Tree(value=IllegalType())),
            id="recursive:direct:dict:passthrough:incompatible_value",
        ),
        param(
            TreeConf(
                value=1,
                left=TreeConf(value=21),
                right=TreeConf(value=22),
            ),
            {},
            Tree(value=1, left=Tree(value=21), right=Tree(value=22)),
            id="recursive:direct:dataclass",
        ),
        param(
            TreeConf(
                value=1,
                left=TreeConf(value=21),
            ),
            {"right": {"value": 22}},
            Tree(value=1, left=Tree(value=21), right=Tree(value=22)),
            id="recursive:direct:dataclass:passthrough",
        ),
        # list
        # note that passthrough to a list element is not currently supported
        param(
            ComposeConf(
                transforms=[
                    CenterCropConf(size=10),
                    RotationConf(degrees=45),
                ]
            ),
            {},
            Compose(
                transforms=[
                    CenterCrop(size=10),
                    Rotation(degrees=45),
                ]
            ),
            id="recursive:list:dataclass",
        ),
        param(
            {
                "_target_": "tests.instantiate.Compose",
                "transforms": [
                    {"_target_": "tests.instantiate.CenterCrop", "size": 10},
                    {"_target_": "tests.instantiate.Rotation", "degrees": 45},
                ],
            },
            {},
            Compose(
                transforms=[
                    CenterCrop(size=10),
                    Rotation(degrees=45),
                ]
            ),
            id="recursive:list:dict",
        ),
        # map
        param(
            MappingConf(
                dictionary={
                    "a": MappingConf(),
                    "b": MappingConf(),
                }
            ),
            {},
            Mapping(
                dictionary={
                    "a": Mapping(),
                    "b": Mapping(),
                }
            ),
            id="recursive:map:dataclass",
        ),
        param(
            {
                "_target_": "tests.instantiate.Mapping",
                "dictionary": {
                    "a": {"_target_": "tests.instantiate.Mapping"},
                    "b": {"_target_": "tests.instantiate.Mapping"},
                },
            },
            {},
            Mapping(
                dictionary={
                    "a": Mapping(),
                    "b": Mapping(),
                }
            ),
            id="recursive:map:dict",
        ),
        # the configured dictionary is not a target, so it is replaced
        param(
            {
                "_target_": "tests.instantiate.Mapping",
                "dictionary": {
                    "a": {"_target_": "tests.instantiate.Mapping"},
                },
            },
            {
                "dictionary": {
                    "b": {"_target_": "tests.instantiate.Mapping"},
                },
            },
            Mapping(
                dictionary={
                    "b": Mapping(),
                }
            ),
            id="recursive:map:dict:passthrough",
        ),
    ],
)
def test_recursive_instantiation(
    instantiate_func: Any,
    config: Any,
    passthrough: Dict[str, Any],
    expected: Any,
) -> None:
    obj = instantiate_func(config, **passthrough)
    assert obj == expected


@mark.parametrize(
    "src, passthrough, expected",
    [
        # direct
        param(
            {
                "_target_": "tests.instantiate.Tree",
                "_partial_": True,
                "left": {
                    "_target_": "tests.instantiate.Tree",
                    "value": 21,
                },
                "right": {
                    "_target_": "tests.instantiate.Tree",
                    "value": 22,
                },
            },
            {},
            partial(Tree, left=Tree(value=21), right=Tree(value=22)),
        ),
        param(
            {"_target_": "tests.instantiate.Tree", "_partial_": True},
            {"value": 1},
            partial(Tree, value=1),
        ),
        param(
            {"_target_": "tests.instantiate.Tree"},
            {
                "value": 1,
                "left": {"_target_": "tests.instantiate.Tree", "_partial_": True},
            },
            Tree(value=1, left=partial(Tree)),
        ),
        param(
            {"_target_": "tests.instantiate.Tree"},
            {
                "value": 1,
                "left": {"_target_": "tests.instantiate.Tree", "_partial_": True},
                "right": {"_target_": "tests.instantiate.Tree", "value": 3},
            },
            Tree(value=1, left=partial(Tree), right=Tree(3)),
        ),
        param(
            TreeConf(
                value=1,
                left=TreeConf(value=21, _partial_=True),
                right=TreeConf(value=22),
            ),
            {},
            Tree(
                value=1,
                left=partial(Tree, value=21, left=None, right=None),
                right=Tree(value=22),
            ),
        ),
        param(
            TreeConf(
                _partial_=True,
                value=1,
                left=TreeConf(value=21, _partial_=True),
                right=TreeConf(value=22, _partial_=True),
            ),
            {},
            partial(
                Tree,
                value=1,
                left=partial(Tree, value=21, left=None, right=None),
                right=partial(Tree, value=22, left=None, right=None),
            ),
        ),
        param(
            TreeConf(
                _partial_=True,
                value=1,
                left=TreeConf(
                    value=21,
                ),
                right=TreeConf(value=22, left=TreeConf(_partial_=True, value=42)),
            ),
            {},
            partial(
                Tree,
                value=1,
                left=Tree(value=21),
                right=Tree(
                    value=22, left=partial(Tree, value=42, left=None, right=None)
                ),
            ),
        ),
        # list
        # note that passthrough to a list element is not currently supported
        param(
            ComposeConf(
                _partial_=True,
                transforms=[
                    CenterCropConf(size=10),
                    RotationConf(degrees=45),
                ],
            ),
            {},
            partial(
                Compose,
                transforms=[
                    CenterCrop(size=10),
                    Rotation(degrees=45),
                ],
            ),
        ),
        param(
            ComposeConf(
                transforms=[
                    CenterCropConf(_partial_=True, size=10),
                    RotationConf(degrees=45),
                ],
            ),
            {},
            Compose(
                transforms=cast(
                    Any,
                    [
                        partial(CenterCrop, size=10),  # type: ignore
                        Rotation(degrees=45),
                    ],
                ),
            ),
        ),
        param(
            {
                "_target_": "tests.instantiate.Compose",
                "transforms": [
                    {"_target_": "tests.instantiate.CenterCrop", "_partial_": True},
                    {"_target_": "tests.instantiate.Rotation", "degrees": 45},
                ],
            },
            {},
            Compose(
                transforms=cast(
                    Any,
                    [
                        partial(CenterCrop),  # type: ignore
                        Rotation(degrees=45),
                    ],
                )
            ),
            id="recursive:list:dict",
        ),
        # map
        param(
            MappingConf(
                dictionary={
                    "a": MappingConf(_partial_=True),
                    "b": MappingConf(),
                }
            ),
            {},
            Mapping(
                dictionary=cast(
                    Any,
                    {
                        "a": partial(Mapping, dictionary=None),
                        "b": Mapping(),
                    },
                )
            ),
        ),
        param(
            {
                "_target_": "tests.instantiate.Mapping",
                "_partial_": True,
                "dictionary": {
                    "a": {"_target_": "tests.instantiate.Mapping", "_partial_": True},
                },
            },
            {
                "dictionary": {
                    "b": {"_target_": "tests.instantiate.Mapping", "_partial_": True},
                },
            },
            partial(
                Mapping,
                dictionary=cast(
                    Any,
                    {
                        # the configured dictionary is not a target, so it is
                        # replaced by the call-site argument
                        "b": partial(Mapping),
                    },
                ),
            ),
        ),
    ],
)
def test_partial_instantiate(
    instantiate_func: Any,
    config: Any,
    passthrough: Dict[str, Any],
    expected: Any,
) -> None:
    obj = instantiate_func(config, **passthrough)
    assert obj == expected or partial_equal(obj, expected)


@mark.parametrize(
    ("src", "passthrough", "expected"),
    [
        param(
            {
                "_target_": "tests.instantiate.Tree",
                "value": 1,
                "left": {
                    "_target_": "tests.instantiate.Tree",
                    "value": 21,
                },
            },
            {},
            Tree(value=1, left=Tree(value=21)),
            id="default",
        ),
        param(
            {
                "_target_": "tests.instantiate.Tree",
                "_recursive_": True,
                "value": 1,
                "left": {
                    "_target_": "tests.instantiate.Tree",
                    "value": 21,
                },
            },
            {"_recursive_": True},
            Tree(value=1, left=Tree(value=21)),
            id="cfg:true,override:true",
        ),
        param(
            {
                "_target_": "tests.instantiate.Tree",
                "_recursive_": True,
                "value": 1,
                "left": {
                    "_target_": "tests.instantiate.Tree",
                    "value": 21,
                },
            },
            {"_recursive_": False},
            Tree(value=1, left={"_target_": "tests.instantiate.Tree", "value": 21}),
            id="cfg:true,override:false",
        ),
        param(
            {
                "_target_": "tests.instantiate.Tree",
                "_recursive_": False,
                "value": 1,
                "left": {
                    "_target_": "tests.instantiate.Tree",
                    "value": 21,
                },
            },
            {"_recursive_": True},
            Tree(value=1, left=Tree(value=21)),
            id="cfg:false,override:true",
        ),
        param(
            {
                "_target_": "tests.instantiate.Tree",
                "_recursive_": False,
                "value": 1,
                "left": {
                    "_target_": "tests.instantiate.Tree",
                    "value": 21,
                },
            },
            {"_recursive_": False},
            Tree(value=1, left={"_target_": "tests.instantiate.Tree", "value": 21}),
            id="cfg:false,override:false",
        ),
        param(
            {
                "_target_": "tests.instantiate.Tree",
                "value": 1,
                "left": {
                    "_target_": "tests.instantiate.Tree",
                    "value": 2,
                    "left": {
                        "_target_": "tests.instantiate.Tree",
                        "value": 3,
                    },
                },
            },
            {},
            Tree(value=1, left=Tree(value=2, left=Tree(value=3))),
            id="3_levels:default",
        ),
        param(
            {
                "_target_": "tests.instantiate.Tree",
                "_recursive_": False,
                "value": 1,
                "left": {
                    "_target_": "tests.instantiate.Tree",
                    "value": 2,
                    "left": {
                        "_target_": "tests.instantiate.Tree",
                        "value": 3,
                    },
                },
            },
            {},
            Tree(
                value=1,
                left={
                    "_target_": "tests.instantiate.Tree",
                    "value": 2,
                    "left": {"_target_": "tests.instantiate.Tree", "value": 3},
                },
            ),
            id="3_levels:cfg1=false",
        ),
        param(
            {
                "_target_": "tests.instantiate.Tree",
                "value": 1,
                "left": {
                    "_target_": "tests.instantiate.Tree",
                    "_recursive_": False,
                    "value": 2,
                    "left": {
                        "_target_": "tests.instantiate.Tree",
                        "value": 3,
                    },
                },
            },
            {},
            Tree(
                value=1,
                left=Tree(
                    value=2, left={"_target_": "tests.instantiate.Tree", "value": 3}
                ),
            ),
            id="3_levels:cfg2=false",
        ),
    ],
)
def test_recursive_override(
    instantiate_func: Any,
    config: Any,
    passthrough: Any,
    expected: Any,
) -> None:
    obj = instantiate_func(config, **passthrough)
    assert obj == expected


def test_non_target_node_obeys_recursive_false(instantiate_func: Any) -> None:
    obj = instantiate_func(
        {
            "_target_": "tests.instantiate.ArgsClass",
            "child": {
                "_recursive_": False,
                "grandchild": {
                    "_target_": "tests.instantiate.SimpleClass",
                    "value": 10,
                },
            },
        }
    )

    child = obj.kwargs["child"]
    assert isinstance(child, DictConfig)
    assert isinstance(child.grandchild, DictConfig)


@mark.parametrize(
    ("src", "passthrough", "expected"),
    [
        param(
            {
                "_target_": "tests.instantiate.AClass",
                "a": 10,
                "b": 20,
                "c": 30,
                "d": 40,
            },
            {"_target_": "tests.instantiate.BClass"},
            BClass(10, 20, 30, 40),
            id="str:override_same_args",
        ),
        param(
            {
                "_target_": "tests.instantiate.AClass",
                "a": 10,
                "b": 20,
                "c": 30,
                "d": 40,
            },
            {"_target_": BClass},
            BClass(10, 20, 30, 40),
            id="type:override_same_args",
        ),
        param(
            {"_target_": "tests.instantiate.AClass", "a": 10, "b": 20},
            {"_target_": "tests.instantiate.BClass"},
            BClass(10, 20, "c", "d"),
            id="str:override_other_args",
        ),
        param(
            {"_target_": "tests.instantiate.AClass", "a": 10, "b": 20},
            {"_target_": BClass},
            BClass(10, 20, "c", "d"),
            id="type:override_other_args",
        ),
        param(
            {
                "_target_": "tests.instantiate.AClass",
                "a": 10,
                "b": 20,
                "c": {
                    "_target_": "tests.instantiate.AClass",
                    "a": "aa",
                    "b": "bb",
                    "c": "cc",
                },
            },
            {
                "_target_": "tests.instantiate.BClass",
                "c": {
                    "_target_": "tests.instantiate.BClass",
                },
            },
            BClass(10, 20, BClass(a="aa", b="bb", c="cc"), "d"),
            id="str:recursive_override",
        ),
        param(
            {
                "_target_": "tests.instantiate.AClass",
                "a": 10,
                "b": 20,
                "c": {
                    "_target_": "tests.instantiate.AClass",
                    "a": "aa",
                    "b": "bb",
                    "c": "cc",
                },
            },
            {"_target_": BClass, "c": {"_target_": BClass}},
            BClass(10, 20, BClass(a="aa", b="bb", c="cc"), "d"),
            id="type:recursive_override",
        ),
    ],
)
def test_override_target(
    instantiate_func: Any, config: Any, passthrough: Any, expected: Any
) -> None:
    obj = instantiate_func(config, **passthrough)
    assert obj == expected


@mark.parametrize(
    "config, passthrough, expected",
    [
        param(
            {"_target_": AnotherClass, "x": 10},
            {},
            AnotherClass(10),
            id="class_in_config_dict",
        ),
    ],
)
def test_instantiate_from_class_in_dict(
    instantiate_func: Any, config: Any, passthrough: Any, expected: Any
) -> None:
    config_copy = copy.deepcopy(config)
    assert instantiate_func(config, **passthrough) == expected
    assert config == config_copy


@mark.parametrize(
    "config, passthrough, err_msg",
    [
        param(
            OmegaConf.create({"_target_": AClass}),
            {},
            re.escape(
                "Expected a callable target, got"
                + " '{'a': '???', 'b': '???', 'c': '???', 'd': 'default_value'}' of type 'DictConfig'"
            ),
            id="instantiate-from-dataclass-in-dict-fails",
        ),
        param(
            OmegaConf.create({"foo": {"_target_": AClass}}),
            {},
            re.escape(
                "Expected a callable target, got"
                + " '{'a': '???', 'b': '???', 'c': '???', 'd': 'default_value'}' of type 'DictConfig'"
                + "\nfull_key: foo"
            ),
            id="instantiate-from-dataclass-in-dict-fails-nested",
        ),
    ],
)
def test_instantiate_from_dataclass_in_dict_fails(
    instantiate_func: Any, config: Any, passthrough: Any, err_msg: str
) -> None:
    with raises(
        InstantiationException,
        match=err_msg,
    ):
        instantiate_func(config, **passthrough)


def test_cannot_locate_target(instantiate_func: Any) -> None:
    cfg = OmegaConf.create({"foo": {"_target_": "not_found"}})
    with raises(
        InstantiationException,
        match=re.escape(
            dedent("""\
                Error locating target 'not_found'
                full_key: foo""")
        ),
    ) as exc_info:
        instantiate_func(cfg)
    err = exc_info.value
    assert hasattr(err, "__cause__")
    chained = err.__cause__
    assert isinstance(chained, ImportError)
    assert_multiline_regex_search(
        dedent("""\
            Error loading 'not_found':
            ModuleNotFoundError\\("No module named 'not_found'",?\\)
            Are you sure that module 'not_found' is installed\\?"""),
        chained.args[0],
    )


@mark.parametrize(
    "target",
    [
        "builtins.compile",
        "ctypes.CDLL",
        "ctypes.WinDLL",
        "ctypes.windll.LoadLibrary",
        "importlib.import_module",
        "os.execl",
        "os.getcwd",
        "os.popen",
        "os.posix_spawn",
        "posix.kill",
        "posix.remove",
        "posix.system",
        "nt.startfile",
        "nt.system",
        "pty.spawn",
        "runpy.run_path",
        "subprocess.Popen",
        "subprocess.check_output",
        "subprocess.run",
    ],
)
def test_blocklisted_target_fails(target: str) -> None:
    cfg = OmegaConf.create({"foo": {"_target_": target}})
    with raises(
        InstantiationException,
        match=re.escape(
            dedent(f"""\
                Target '{target}' is blocklisted and cannot be instantiated from config
                to prevent security vulnerabilities.
                Pass _target_whitelist_ from trusted code to allow expected targets.
                full_key: foo""")
        ),
    ) as exc_info:
        _instantiate2.instantiate(cfg)
    err = exc_info.value
    assert hasattr(err, "__cause__")
    chained = err.__cause__
    assert chained is None


def test_target_whitelist_warns_in_legacy_mode() -> None:
    cfg = {"_target_": "tests.instantiate.AClass", "a": 10, "b": 20, "c": 30}
    with warns(UserWarning, match=r"This\s+warning will become an error in Hydra 1\.5"):
        assert _instantiate2.instantiate(cfg) == AClass(a=10, b=20, c=30)


def test_target_whitelist_warning_points_to_user_callsite() -> None:
    def call_legacy_instantiate(config: Any) -> Any:
        nonlocal expected_lineno
        frame = inspect.currentframe()
        assert frame is not None
        expected_lineno = frame.f_lineno + 1
        return _instantiate2.instantiate(config)

    expected_lineno = -1
    cfg = {
        "nested": {
            "_target_": "tests.instantiate.AClass",
            "a": 10,
            "b": 20,
            "c": 30,
        }
    }
    with warns(UserWarning, match="_target_whitelist_") as records:
        assert call_legacy_instantiate(cfg) == {"nested": AClass(a=10, b=20, c=30)}

    assert os.path.samefile(records[0].filename, __file__)
    assert records[0].lineno == expected_lineno


def test_target_whitelist_applies_to_callable_targets() -> None:
    cfg = {"_target_": AClass, "a": 10, "b": 20, "c": 30}
    with warns(UserWarning, match="_target_whitelist_"):
        assert _instantiate2.instantiate(cfg) == AClass(a=10, b=20, c=30)

    assert _instantiate2.instantiate(
        cfg, _target_whitelist_="tests.instantiate.AClass"
    ) == AClass(a=10, b=20, c=30)

    cfg = OmegaConf.create(
        {"_target_": module_function, "x": 10},
        flags={"allow_objects": True},
    )
    with warns(UserWarning, match="_target_whitelist_"):
        assert _instantiate2.instantiate(cfg) == 10

    with raises(
        InstantiationException,
        match=(
            "Target 'tests.instantiate.module_function' is not in the "
            "instantiate target whitelist"
        ),
    ):
        _instantiate2.instantiate(cfg, _target_whitelist_=[])

    assert (
        _instantiate2.instantiate(
            cfg, _target_whitelist_="tests.instantiate.module_function"
        )
        == 10
    )

    cfg = OmegaConf.create(
        {"_target_": eval, "_args_": ["1+2"]},
        flags={"allow_objects": True},
    )
    with raises(
        InstantiationException,
        match="Target 'builtins.eval' is blocklisted",
    ):
        _instantiate2.instantiate(cfg)

    target = CallableClass()
    cfg = OmegaConf.create(
        {"_target_": target},
        flags={"allow_objects": True},
    )
    assert (
        _instantiate2.instantiate(
            cfg, _target_whitelist_="tests.instantiate.CallableClass"
        )
        == "callable class"
    )

    cfg = {"_target_": target}
    assert (
        _instantiate2.instantiate(
            cfg, _target_whitelist_="tests.instantiate.CallableClass"
        )
        == "callable class"
    )


def test_target_whitelist_preserves_bound_classmethod_identity() -> None:
    cfg = OmegaConf.create(
        {"_target_": ASubclass.class_method, "y": 10},
        flags={"allow_objects": True},
    )

    result = _instantiate2.instantiate(
        cfg, _target_whitelist_="tests.instantiate.ASubclass.class_method"
    )

    assert isinstance(result, ASubclass)
    assert result.x == 11


def test_non_recursive_plain_config_preserves_callable_target(
    instantiate_func: Any,
) -> None:
    target = CallableClass()

    result = instantiate_func(
        {
            "_target_": "tests.instantiate.ArgsClass",
            "_recursive_": False,
            "payload": {"_target_": target},
        }
    )

    payload = result.kwargs["payload"]
    assert OmegaConf.is_dict(payload)
    assert payload["_target_"] is target


def test_callable_target_does_not_alias_literal_target_string(
    instantiate_func: Any,
) -> None:
    target = CallableClass()
    cfg = {
        "_target_": "tests.instantiate.ArgsClass",
        "callable": {"_target_": target},
        "literal": {"_target_": "__hydra_callable_target_0__"},
    }

    with raises(
        InstantiationException,
        match="Error locating target '__hydra_callable_target_0__'",
    ):
        instantiate_func(cfg)


@mark.parametrize(
    "target_whitelist",
    [
        "tests.instantiate.*",
        ["tests.instantiate.AClass"],
    ],
)
def test_target_whitelist_allows_expected_targets(
    instantiate_func: Any, target_whitelist: Any
) -> None:
    cfg = {"_target_": "tests.instantiate.AClass", "a": 10, "b": 20, "c": 30}
    assert instantiate_func(cfg, _target_whitelist_=target_whitelist) == AClass(
        a=10, b=20, c=30
    )


def test_target_whitelist_context_allows_expected_targets() -> None:
    cfg = {"_target_": "tests.instantiate.AClass", "a": 10, "b": 20, "c": 30}
    with target_whitelist("tests.instantiate.*"):
        assert _instantiate2.instantiate(cfg) == AClass(a=10, b=20, c=30)


def test_target_whitelist_context_stacks_additively() -> None:
    class_cfg = {
        "_target_": "tests.instantiate.AClass",
        "a": 10,
        "b": 20,
        "c": 30,
    }
    function_cfg = {"_target_": "tests.instantiate.module_function", "x": 10}

    with target_whitelist("tests.instantiate.AClass"):
        assert _instantiate2.instantiate(class_cfg) == AClass(a=10, b=20, c=30)
        with target_whitelist("tests.instantiate.module_function"):
            assert _instantiate2.instantiate(class_cfg) == AClass(a=10, b=20, c=30)
            assert _instantiate2.instantiate(function_cfg) == 10

        with raises(
            InstantiationException,
            match="Target 'tests.instantiate.module_function' is not in the instantiate target whitelist",
        ):
            _instantiate2.instantiate(function_cfg)


def test_target_whitelist_context_reset_replaces_outer_context() -> None:
    cfg = {"_target_": "tests.instantiate.AClass", "a": 10, "b": 20, "c": 30}

    with target_whitelist("tests.instantiate.*"):
        with target_whitelist([], reset=True):
            with raises(
                InstantiationException,
                match="Target 'tests.instantiate.AClass' is not in the instantiate target whitelist",
            ):
                _instantiate2.instantiate(cfg)

        assert _instantiate2.instantiate(cfg) == AClass(a=10, b=20, c=30)


def test_target_whitelist_policy_can_be_passed_to_instantiate(
    instantiate_func: Any,
) -> None:
    cfg = {"_target_": "tests.instantiate.AClass", "a": 10, "b": 20, "c": 30}
    policy = target_whitelist("tests.instantiate.*", reset=True)
    assert instantiate_func(cfg, _target_whitelist_=policy) == AClass(a=10, b=20, c=30)


def test_target_whitelist_policy_reset_replaces_context_for_instantiate() -> None:
    cfg = {"_target_": "tests.instantiate.AClass", "a": 10, "b": 20, "c": 30}

    with target_whitelist("tests.instantiate.*"):
        with raises(
            InstantiationException,
            match="Target 'tests.instantiate.AClass' is not in the instantiate target whitelist",
        ):
            _instantiate2.instantiate(
                cfg, _target_whitelist_=target_whitelist([], reset=True)
            )


@mark.parametrize(
    "target_whitelist",
    [
        [],
        "tests.other.*",
        ["tests.instantiate.BClass"],
    ],
)
def test_target_whitelist_blocks_unlisted_targets(
    instantiate_func: Any, target_whitelist: Any
) -> None:
    cfg = {"_target_": "tests.instantiate.AClass", "a": 10}
    with raises(
        InstantiationException,
        match="Target 'tests.instantiate.AClass' is not in the instantiate target whitelist",
    ):
        instantiate_func(cfg, _target_whitelist_=target_whitelist)


@mark.parametrize("target_whitelist", ["*", "*.*", "tests.*.AClass"])
def test_target_whitelist_rejects_broad_wildcards(
    instantiate_func: Any, target_whitelist: str
) -> None:
    cfg = {"_target_": "tests.instantiate.AClass", "a": 10}
    with raises(
        InstantiationException,
        match="Invalid _target_whitelist_ entry",
    ):
        instantiate_func(cfg, _target_whitelist_=target_whitelist)


def test_target_whitelist_in_config_is_rejected(instantiate_func: Any) -> None:
    cfg = {
        "_target_": "tests.instantiate.AClass",
        "_target_whitelist_": "tests.instantiate.*",
        "a": 10,
    }
    with raises(
        InstantiationException,
        match="_target_whitelist_ must be passed to instantiate\\(\\)",
    ):
        instantiate_func(cfg)


def test_target_whitelist_can_explicitly_allow_blocklisted_targets(
    instantiate_func: Any,
) -> None:
    cfg = {"_target_": "builtins.eval", "_args_": ["1+2"]}
    assert instantiate_func(cfg, _target_whitelist_="builtins.eval") == 3


def test_target_whitelist_unsafe_allows_all_targets(instantiate_func: Any) -> None:
    cfg = {"_target_": "builtins.eval", "_args_": ["1+2"]}
    assert instantiate_func(cfg, _target_whitelist_=UNSAFE_ALLOW_ALL_TARGETS) == 3


@mark.parametrize(
    "primitive,expected_primitive",
    [
        param(None, False, id="unspecified"),
        param(ConvertMode.NONE, False, id="none"),
        param(ConvertMode.PARTIAL, True, id="partial"),
        param(ConvertMode.OBJECT, True, id="object"),
        param(ConvertMode.ALL, True, id="all"),
    ],
)
@mark.parametrize(
    "input_,expected",
    [
        param(
            {
                "obj": {
                    "_target_": "tests.instantiate.AClass",
                    "a": {"foo": "bar"},
                    "b": OmegaConf.create({"foo": "bar"}),
                    "c": [1, 2, 3],
                    "d": OmegaConf.create([1, 2, 3]),
                },
            },
            AClass(
                a={"foo": "bar"},
                b={"foo": "bar"},
                c=[1, 2, 3],
                d=[1, 2, 3],
            ),
            id="simple",
        ),
        param(
            {
                "value": 99,
                "obj": {
                    "_target_": "tests.instantiate.AClass",
                    "a": {"foo": "${value}"},
                    "b": OmegaConf.create({"foo": "${value}"}),
                    "c": [1, "${value}"],
                    "d": OmegaConf.create([1, "${value}"]),
                },
            },
            AClass(
                a={"foo": 99},
                b={"foo": 99},
                c=[1, 99],
                d=[1, 99],
            ),
            id="interpolation",
        ),
    ],
)
def test_convert_params_override(
    instantiate_func: Any,
    primitive: Optional[bool],
    expected_primitive: bool,
    input_: Any,
    expected: Any,
) -> None:
    input_cfg = OmegaConf.create(input_)
    if primitive is not None:
        ret = instantiate_func(input_cfg.obj, _convert_=primitive)
    else:
        ret = instantiate_func(input_cfg.obj)

    expected_list: Any
    expected_dict: Any
    if expected_primitive is True:
        expected_list = list
        expected_dict = dict
    else:
        expected_list = ListConfig
        expected_dict = DictConfig

    assert ret == expected
    assert isinstance(ret.a, expected_dict)
    assert isinstance(ret.b, expected_dict)
    assert isinstance(ret.c, expected_list)
    assert isinstance(ret.d, expected_list)


@mark.parametrize(
    "convert_mode",
    [
        param(None, id="none"),
        param(ConvertMode.NONE, id="none"),
        param("none", id="none"),
        param(ConvertMode.PARTIAL, id="partial"),
        param("partial", id="partial"),
        param(ConvertMode.OBJECT, id="object"),
        param("object", id="object"),
        param(ConvertMode.ALL, id="all"),
        param("all", id="all"),
    ],
)
@mark.parametrize(
    "input_,expected",
    [
        param(
            {
                "value": 99,
                "obj": {
                    "_target_": "tests.instantiate.SimpleClass",
                    "a": {
                        "_target_": "tests.instantiate.SimpleClass",
                        "a": {"foo": "${value}"},
                        "b": [1, "${value}"],
                    },
                    "b": None,
                },
            },
            SimpleClass(a={"foo": 99}, b=[1, 99]),
            id="simple",
        ),
    ],
)
def test_convert_params(
    instantiate_func: Any, input_: Any, expected: Any, convert_mode: Any
) -> None:
    cfg = OmegaConf.create(input_)
    kwargs = {"a": {"_convert_": convert_mode}}
    ret = instantiate_func(cfg.obj, **kwargs)

    if convert_mode in (ConvertMode.PARTIAL, ConvertMode.OBJECT, ConvertMode.ALL):
        assert isinstance(ret.a.a, dict)
        assert isinstance(ret.a.b, list)
    elif convert_mode in (None, ConvertMode.NONE):
        assert isinstance(ret.a.a, DictConfig)
        assert isinstance(ret.a.b, ListConfig)
    else:
        assert False

    assert ret.a == expected


@mark.parametrize("nested_recursive", [True, False])
def test_convert_and_recursive_node(
    instantiate_func: Any, nested_recursive: bool
) -> None:
    cfg = {
        "_target_": "tests.instantiate.SimpleClass",
        "a": {
            "_target_": "tests.instantiate.SimpleClass",
            "_convert_": "all",
            "_recursive_": nested_recursive,
            "a": {},
            "b": [],
        },
        "b": None,
    }

    obj = instantiate_func(cfg)
    assert isinstance(obj.a.a, dict)
    assert isinstance(obj.a.b, list)


@mark.parametrize(
    "src,expected",
    [
        param(
            {
                "value": 99,
                "obj": {
                    "_target_": "tests.instantiate.SimpleDataClass",
                    "a": {
                        "_target_": "tests.instantiate.SimpleDataClass",
                        "a": {"foo": "${value}"},
                        "b": [1, "${value}"],
                    },
                    "b": None,
                },
            },
            (
                SimpleDataClass(
                    a=SimpleDataClass(
                        a=OmegaConf.create({"foo": 99}), b=OmegaConf.create([1, 99])
                    ),
                    b=None,
                ),
                SimpleDataClass(a=SimpleDataClass(a={"foo": 99}, b=[1, 99]), b=None),
                SimpleDataClass(a=SimpleDataClass(a={"foo": 99}, b=[1, 99]), b=None),
                SimpleDataClass(a=SimpleDataClass(a={"foo": 99}, b=[1, 99]), b=None),
            ),
            id="dataclass+dataclass",
        ),
        param(
            {
                "value": 99,
                "obj": {
                    "_target_": "tests.instantiate.SimpleClass",
                    "a": {
                        "_target_": "tests.instantiate.SimpleDataClass",
                        "a": {"foo": "${value}"},
                        "b": [1, "${value}"],
                    },
                    "b": None,
                },
            },
            (
                SimpleClass(
                    a=SimpleDataClass(
                        a=OmegaConf.create({"foo": 99}), b=OmegaConf.create([1, 99])
                    ),
                    b=None,
                ),
                SimpleClass(a=SimpleDataClass(a={"foo": 99}, b=[1, 99]), b=None),
                SimpleClass(a=SimpleDataClass(a={"foo": 99}, b=[1, 99]), b=None),
                SimpleClass(a=SimpleDataClass(a={"foo": 99}, b=[1, 99]), b=None),
            ),
            id="class+dataclass",
        ),
        param(
            {
                "value": 99,
                "obj": {
                    "a": {
                        "_target_": "tests.instantiate.SimpleDataClass",
                        "a": {"foo": "${value}"},
                        "b": [1, "${value}"],
                    },
                    "b": None,
                },
            },
            (
                OmegaConf.create(
                    {
                        "a": structured_config_object_node(
                            SimpleDataClass(
                                a=OmegaConf.create({"foo": 99}),
                                b=OmegaConf.create([1, 99]),
                            )
                        ),
                        "b": None,
                    },
                    flags={"allow_objects": True},
                ),
                {"a": SimpleDataClass(a={"foo": 99}, b=[1, 99]), "b": None},
                {"a": SimpleDataClass(a={"foo": 99}, b=[1, 99]), "b": None},
                {"a": SimpleDataClass(a={"foo": 99}, b=[1, 99]), "b": None},
            ),
            id="dict+dataclass",
        ),
        param(
            {
                "obj": {
                    "_target_": "tests.instantiate.SimpleClass",
                    "a": SimpleDataClass(a="foo"),
                    "b": None,
                }
            },
            (
                SimpleClass(a=OmegaConf.create({"a": "foo", "b": None}), b=None),
                SimpleClass(a=OmegaConf.create({"a": "foo", "b": None}), b=None),
                SimpleClass(a=SimpleDataClass(a="foo", b=None), b=None),
                SimpleClass(a={"a": "foo", "b": None}, b=None),
            ),
            id="class+dataclass_instance",
        ),
        param(
            {
                "obj": SimpleDataClass(
                    a={
                        "_target_": "tests.instantiate.SimpleClass",
                        "a": "foo",
                        "b": None,
                    }
                )
            },
            (
                OmegaConf.create(
                    {"a": SimpleClass(a="foo", b=None), "b": None},
                    flags={"allow_objects": True},
                ),
                OmegaConf.create(
                    {"a": SimpleClass(a="foo", b=None), "b": None},
                    flags={"allow_objects": True},
                ),
                SimpleDataClass(a=SimpleClass(a="foo", b=None), b=None),
                {"a": SimpleClass(a="foo", b=None), "b": None},
            ),
            id="dataclass_instance+class",
        ),
        param(
            {"obj": SimpleClassDefaultPrimitiveConf(a=SimpleDataClass(a="foo"))},
            (
                SimpleClass(a=OmegaConf.create({"a": "foo", "b": None}), b=None),
                SimpleClass(a=OmegaConf.create({"a": "foo", "b": None}), b=None),
                SimpleClass(a=SimpleDataClass(a="foo", b=None), b=None),
                SimpleClass(a={"a": "foo", "b": None}, b=None),
            ),
            id="dataclass_instance_with_target+dataclass_instance",
        ),
    ],
)
def test_instantiate_convert_dataclasses(
    instantiate_func: Any, config: Any, expected: Tuple[Any, Any, Any, Any]
) -> None:
    """Instantiate on nested dataclass + dataclass."""
    modes = [ConvertMode.NONE, ConvertMode.PARTIAL, ConvertMode.OBJECT, ConvertMode.ALL]
    assert len(modes) == len(expected)
    for exp, mode in zip(expected, modes):
        # create DictConfig to ensure interpolations are working correctly when we pass a cfg.obj
        cfg = OmegaConf.create(config)
        instance = instantiate_func(cfg.obj, _convert_=mode)
        assert instance == exp
        assert recisinstance(instance, exp)


@mark.parametrize(
    ("mode", "expected_dict", "expected_list"),
    [
        param(ConvertMode.NONE, DictConfig, ListConfig, id="none"),
        param(ConvertMode.ALL, dict, list, id="all"),
        param(ConvertMode.PARTIAL, dict, list, id="partial"),
        param(ConvertMode.OBJECT, dict, list, id="object"),
    ],
)
def test_instantiated_regular_class_container_types(
    instantiate_func: Any, mode: Any, expected_dict: Any, expected_list: Any
) -> None:
    cfg = {"_target_": "tests.instantiate.SimpleClass", "a": {}, "b": []}
    ret = instantiate_func(cfg, _convert_=mode)
    assert isinstance(ret.a, expected_dict)
    assert isinstance(ret.b, expected_list)

    cfg2 = {
        "_target_": "tests.instantiate.SimpleClass",
        "a": {"_target_": "tests.instantiate.SimpleClass", "a": {}, "b": []},
        "b": [{"_target_": "tests.instantiate.SimpleClass", "a": {}, "b": []}],
    }
    ret = instantiate_func(cfg2, _convert_=mode)
    assert isinstance(ret.a.a, expected_dict)
    assert isinstance(ret.a.b, expected_list)
    assert isinstance(ret.b[0].a, expected_dict)
    assert isinstance(ret.b[0].b, expected_list)


@mark.parametrize(
    ("mode", "expected_tuple"),
    [
        param(ConvertMode.NONE, TupleConfig, id="none"),
        param(ConvertMode.ALL, tuple, id="all"),
        param(ConvertMode.PARTIAL, tuple, id="partial"),
        param(ConvertMode.OBJECT, tuple, id="object"),
    ],
)
def test_instantiated_regular_class_tuple_type(
    instantiate_func: Any, mode: Any, expected_tuple: Any
) -> None:
    cfg = {"_target_": "tests.instantiate.SimpleClass", "a": (1, 2), "b": None}

    ret = instantiate_func(cfg, _convert_=mode)

    assert isinstance(ret.a, expected_tuple)
    assert ret.a == (1, 2)


def test_instantiated_regular_class_container_types_partial(
    instantiate_func: Any,
) -> None:
    cfg = {
        "_target_": "tests.instantiate.SimpleClass",
        "a": {},
        "b": User(name="Bond", age=7),
    }
    ret = instantiate_func(cfg, _convert_=ConvertMode.PARTIAL)
    assert isinstance(ret.a, dict)
    assert isinstance(ret.b, DictConfig)
    assert OmegaConf.get_type(ret.b) is User


def test_instantiated_regular_class_container_types_object(
    instantiate_func: Any,
) -> None:
    cfg = {
        "_target_": "tests.instantiate.SimpleClass",
        "a": {},
        "b": User(name="Bond", age=7),
    }
    ret = instantiate_func(cfg, _convert_=ConvertMode.OBJECT)
    assert isinstance(ret.a, dict)
    assert isinstance(ret.b, User)


def test_instantiated_regular_class_container_types_partial2(
    instantiate_func: Any,
) -> None:
    cfg = {
        "_target_": "tests.instantiate.SimpleClass",
        "a": [{}, User(name="Bond", age=7)],
        "b": None,
    }
    ret = instantiate_func(cfg, _convert_=ConvertMode.PARTIAL)
    assert isinstance(ret.a, list)
    assert isinstance(ret.a[0], dict)
    assert isinstance(ret.a[1], DictConfig)
    assert OmegaConf.get_type(ret.a[1]) is User


def test_instantiated_regular_class_container_types_object2(
    instantiate_func: Any,
) -> None:
    cfg = {
        "_target_": "tests.instantiate.SimpleClass",
        "a": [{}, User(name="Bond", age=7)],
        "b": None,
    }
    ret = instantiate_func(cfg, _convert_=ConvertMode.OBJECT)
    assert isinstance(ret.a, list)
    assert isinstance(ret.a[0], dict)
    assert isinstance(ret.a[1], User)


def test_nested_dataclass_targets_remain_objects_with_convert_none(
    instantiate_func: Any,
) -> None:
    dataclass_target = {
        "_target_": "tests.instantiate.SimpleDataClass",
        "a": "foo",
        "b": 123,
    }

    top = instantiate_func(dataclass_target, _convert_=ConvertMode.NONE)
    assert isinstance(top, SimpleDataClass)

    ret_list = instantiate_func([dataclass_target], _convert_=ConvertMode.NONE)
    assert isinstance(ret_list, ListConfig)
    assert isinstance(ret_list[0], SimpleDataClass)
    assert ret_list[0] == top

    ret = instantiate_func(
        {
            "nested": dataclass_target,
            "items": [dataclass_target],
            "tuple_items": (dataclass_target,),
        },
        _convert_=ConvertMode.NONE,
    )
    assert isinstance(ret, DictConfig)
    assert isinstance(ret.nested, SimpleDataClass)
    assert ret.nested == top
    assert isinstance(ret["items"], ListConfig)
    assert isinstance(ret["items"][0], SimpleDataClass)
    assert ret["items"][0] == top
    assert isinstance(ret["tuple_items"], TupleConfig)
    assert isinstance(ret["tuple_items"][0], SimpleDataClass)
    assert ret["tuple_items"][0] == top


@mark.parametrize(
    "src",
    [
        {
            "_target_": "tests.instantiate.SimpleClass",
            "a": {
                "_target_": "tests.instantiate.SimpleClass",
                "a": {},
                "b": User(name="Bond", age=7),
            },
            "b": None,
        }
    ],
)
def test_instantiated_regular_class_container_types_partial__recursive(
    instantiate_func: Any, config: Any
) -> None:
    ret = instantiate_func(config, _convert_=ConvertMode.PARTIAL)
    assert isinstance(ret.a, SimpleClass)
    assert isinstance(ret.a.a, dict)
    assert isinstance(ret.a.b, DictConfig)
    assert OmegaConf.get_type(ret.a.b) is User


@mark.parametrize(
    "src",
    [
        {
            "_target_": "tests.instantiate.SimpleClass",
            "a": {
                "_target_": "tests.instantiate.SimpleClass",
                "a": {},
                "b": User(name="Bond", age=7),
            },
            "b": None,
        }
    ],
)
def test_instantiated_regular_class_container_types_object__recursive(
    instantiate_func: Any, config: Any
) -> None:
    ret = instantiate_func(config, _convert_=ConvertMode.OBJECT)
    assert isinstance(ret.a, SimpleClass)
    assert isinstance(ret.a.a, dict)
    assert isinstance(ret.a.b, User)


@mark.parametrize(
    "input_,is_primitive,expected",
    [
        param(
            {
                "value": 99,
                "obj": SimpleClassPrimitiveConf(
                    a={"foo": "${value}"}, b=[1, "${value}"]
                ),
            },
            True,
            SimpleClass(a={"foo": 99}, b=[1, 99]),
            id="primitive_specified_true",
        ),
        param(
            {
                "value": 99,
                "obj": SimpleClassNonPrimitiveConf(
                    a={"foo": "${value}"}, b=[1, "${value}"]
                ),
            },
            False,
            SimpleClass(a={"foo": 99}, b=[1, 99]),
            id="primitive_specified_false",
        ),
        param(
            {
                "value": 99,
                "obj": SimpleClassDefaultPrimitiveConf(
                    a={"foo": "${value}"}, b=[1, "${value}"]
                ),
            },
            False,
            SimpleClass(a={"foo": 99}, b=[1, 99]),
            id="default_behavior",
        ),
    ],
)
def test_convert_in_config(
    instantiate_func: Any, input_: Any, is_primitive: bool, expected: Any
) -> None:
    cfg = OmegaConf.create(input_)
    ret = instantiate_func(cfg.obj)
    assert ret == expected

    if is_primitive:
        assert isinstance(ret.a, dict)
        assert isinstance(ret.b, list)
    else:
        assert isinstance(ret.a, DictConfig)
        assert isinstance(ret.b, ListConfig)


@mark.parametrize(
    ("v1", "v2", "expected"),
    [
        (ConvertMode.ALL, ConvertMode.ALL, True),
        (ConvertMode.NONE, "none", True),
        (ConvertMode.PARTIAL, "Partial", True),
        (ConvertMode.OBJECT, "object", True),
        (ConvertMode.ALL, ConvertMode.NONE, False),
        (ConvertMode.NONE, "all", False),
    ],
)
def test_convert_mode_equality(v1: Any, v2: Any, expected: bool) -> None:
    assert (v1 == v2) == expected


def test_nested_dataclass_with_partial_convert(instantiate_func: Any) -> None:
    # dict
    cfg = OmegaConf.structured(NestedConf)
    ret = instantiate_func(cfg, _convert_="partial")
    assert isinstance(ret.a, DictConfig) and OmegaConf.get_type(ret.a) == User
    assert isinstance(ret.b, DictConfig) and OmegaConf.get_type(ret.b) == User
    expected = SimpleClass(a=User(name="a", age=1), b=User(name="b", age=2))
    assert ret == expected

    # list
    lst = [User(name="a", age=1)]
    cfg = OmegaConf.structured(NestedConf(a=lst))
    ret = instantiate_func(cfg, _convert_="partial")
    assert isinstance(ret.a, list) and OmegaConf.get_type(ret.a[0]) == User
    assert isinstance(ret.b, DictConfig) and OmegaConf.get_type(ret.b) == User
    expected = SimpleClass(a=lst, b=User(name="b", age=2))
    assert ret == expected


class DictValues:
    def __init__(self, d: Dict[str, User]):
        self.d = d


class ListValues:
    def __init__(self, d: List[User]):
        self.d = d


def test_dict_with_structured_config(instantiate_func: Any) -> None:
    @dataclass
    class DictValuesConf:
        _target_: str = "tests.instantiate.test_instantiate.DictValues"
        d: Dict[str, User] = MISSING

    schema = OmegaConf.structured(DictValuesConf)
    cfg = OmegaConf.merge(schema, {"d": {"007": {"name": "Bond", "age": 7}}})
    obj = instantiate_func(config=cfg, _convert_="none")
    assert OmegaConf.is_dict(obj.d)
    assert OmegaConf.get_type(obj.d["007"]) == User

    obj = instantiate_func(config=cfg, _convert_="partial")
    assert isinstance(obj.d, dict)
    assert OmegaConf.get_type(obj.d["007"]) == User

    obj = instantiate_func(config=cfg, _convert_="all")
    assert isinstance(obj.d, dict)
    assert isinstance(obj.d["007"], dict)


def test_list_with_structured_config(instantiate_func: Any) -> None:
    @dataclass
    class ListValuesConf:
        _target_: str = "tests.instantiate.test_instantiate.ListValues"
        d: List[User] = MISSING

    schema = OmegaConf.structured(ListValuesConf)
    cfg = OmegaConf.merge(schema, {"d": [{"name": "Bond", "age": 7}]})

    obj = instantiate_func(config=cfg, _convert_="none")
    assert isinstance(obj.d, ListConfig)
    assert OmegaConf.get_type(obj.d[0]) == User

    obj = instantiate_func(config=cfg, _convert_="partial")
    assert isinstance(obj.d, list)
    assert OmegaConf.get_type(obj.d[0]) == User

    obj = instantiate_func(config=cfg, _convert_="all")
    assert isinstance(obj.d, list)
    assert isinstance(obj.d[0], dict)


def test_list_as_none(instantiate_func: Any) -> None:
    @dataclass
    class ListValuesConf:
        _target_: str = "tests.instantiate.test_instantiate.ListValues"
        d: Optional[List[User]] = None

    cfg = OmegaConf.structured(ListValuesConf)
    obj = instantiate_func(config=cfg)
    assert obj.d is None


def test_dict_as_none(instantiate_func: Any) -> None:
    @dataclass
    class DictValuesConf:
        _target_: str = "tests.instantiate.test_instantiate.DictValues"
        d: Optional[Dict[str, User]] = None

    cfg = OmegaConf.structured(DictValuesConf)
    obj = instantiate_func(config=cfg)
    assert obj.d is None


@mark.parametrize(
    "alias",
    [
        "logging.os.system",  # os.system reached via logging's imported `os`
        "logging.os.execl",  # prefix-blocked callable reached via an alias
        "multiprocessing.sharedctypes.ctypes.cdll.LoadLibrary",
        "multiprocessing.sharedctypes.ctypes.pydll.LoadLibrary",
        "site.builtins.exit",
        "site.builtins.help",
        "site.builtins.exit.__call__",
        "site.builtins.help.__call__",
        "site.builtins.exit.__call__.__call__",
        "os.system.__call__",
        "logging.os.system.__call__",
        "builtins.eval.__call__",
    ],
)
def test_blocklist_blocks_module_attribute_aliases(alias: str) -> None:
    # The alias is not literally in the blocklist, but resolves to a blocklisted
    # callable. Authorization must be on the resolved identity, not the string.
    with raises(InstantiationException, match="blocklisted"):
        _resolve_target(alias, "")


@mark.parametrize("target", [os.system.__call__, eval.__call__])
def test_blocklist_blocks_callable_object_aliases(target: Callable[..., Any]) -> None:
    with raises(InstantiationException, match="blocklisted"):
        _resolve_target(target, "")


def test_whitelist_blocks_module_attribute_aliases() -> None:
    # A trailing-'.*' whitelist authorizes by string prefix; the alias
    # 'logging.os.system' matches 'logging.*' but resolves to os.system and must
    # be rejected on its resolved identity.
    cfg = OmegaConf.create({"_target_": "logging.os.system", "_args_": ["true"]})
    with raises(
        InstantiationException,
        match="not in the instantiate target whitelist",
    ):
        _instantiate2.instantiate(cfg, _target_whitelist_="logging.*")


def test_whitelist_allows_genuine_target_under_prefix() -> None:
    # A genuine target whose resolved identity lives under the whitelisted
    # prefix keeps working.
    cfg = {"_target_": "tests.instantiate.AClass", "a": 10, "b": 20, "c": 30}
    assert _instantiate2.instantiate(
        cfg, _target_whitelist_="tests.instantiate.*"
    ) == AClass(a=10, b=20, c=30)


@mark.parametrize("target", ["os.getcwd", "os.path.join"])
def test_whitelist_allows_os_implementation_aliases(target: str) -> None:
    assert callable(_resolve_target(target, "", ("os.*",)))


@mark.parametrize("target", [os.getcwd, os.path.join])
def test_whitelist_allows_os_callable_objects(target: Callable[..., Any]) -> None:
    assert _resolve_target(target, "", ("os.*",)) is target


@mark.parametrize("target", ["posix.system", "ntpath.join"])
def test_whitelist_does_not_alias_literal_target_strings(target: str) -> None:
    with raises(
        InstantiationException, match="not in the instantiate target whitelist"
    ):
        _resolve_target(target, "", ("os.*",))


def test_whitelist_allows_exact_reexported_target() -> None:
    # An exact (non-wildcard) whitelist entry is a deliberate per-target
    # authorization and must be honored even when the class is re-exported from
    # a submodule (json.JSONDecoder actually lives in json.decoder), whose
    # canonical module.qualname differs from the config string.
    import json

    cfg = OmegaConf.create({"_target_": "json.JSONDecoder"})
    obj = _instantiate2.instantiate(cfg, _target_whitelist_="json.JSONDecoder")
    assert isinstance(obj, json.JSONDecoder)


def test_whitelist_wildcard_still_blocks_alias_after_exact_reexport_rule() -> None:
    # The exact-match honoring must not reopen the aliasing bypass for wildcard
    # entries: 'logging.os.system' matches 'logging.*' only by wildcard, so the
    # resolved identity (os.system) is still rechecked and rejected.
    cfg = OmegaConf.create({"_target_": "logging.os.system", "_args_": ["true"]})
    with raises(
        InstantiationException,
        match="not in the instantiate target whitelist",
    ):
        _instantiate2.instantiate(cfg, _target_whitelist_="logging.*")


@mark.parametrize(
    "target",
    [
        "pickle.loads",
        "pickle.load",
        "pickle.Unpickler",
        "_pickle.loads",  # canonical C spelling must be blocked too
        "_pickle.load",
        "marshal.loads",
        "marshal.load",
        "shelve.open",
        "trace.CoverageResults",
        "tracemalloc.Snapshot.load",
    ],
)
def test_deserialization_sinks_are_blocklisted(target: str) -> None:
    # Direct-instantiate unpickle sinks are refused on the legacy path. This
    # removes the trivial inline RCE vector; the target whitelist remains the
    # boundary, and users who genuinely need to deserialize wrap it in their own
    # callable.
    cfg = OmegaConf.create({"foo": {"_target_": target}})
    with raises(InstantiationException, match="blocklisted"):
        _instantiate2.instantiate(cfg)


def test_pickle_base64_chain_is_blocklisted() -> None:
    # The reporter's inline vector: pickle.loads(base64.b64decode("...")). The
    # outer pickle.loads target is refused before the chain runs.
    cfg = OmegaConf.create(
        {
            "_target_": "pickle.loads",
            "_args_": [{"_target_": "base64.b64decode", "_args_": ["gA=="]}],
        }
    )
    with raises(InstantiationException, match="blocklisted"):
        _instantiate2.instantiate(cfg)


@mark.parametrize(
    "target",
    [
        "timeit.timeit",
        "timeit.repeat",
        "timeit.Timer.timeit",
        "timeit.Timer.repeat",
        "timeit.Timer.autorange",
        "cProfile.run",
        "cProfile.runctx",
        "cProfile.Profile.run",
        "cProfile.Profile.runctx",
        "profile.run",
        "profile.runctx",
        "profile.Profile.run",
        "profile.Profile.runctx",
        "bdb.Bdb.run",
        "bdb.Bdb.runeval",
        "bdb.Bdb.runctx",
        "pdb.run",
        "pdb.runeval",
        "pdb.Pdb.run",
        "pdb.Pdb.runeval",
        "pdb.Pdb.runctx",
        "trace.Trace.run",
        "trace.Trace.runctx",
        "code.interact",
        "code.InteractiveInterpreter.runsource",
        "code.InteractiveInterpreter.runcode",
        "code.InteractiveConsole.push",
        "doctest.DocTestRunner.run",
        "doctest.DebugRunner.run",
        "doctest.DocTestCase.runTest",
        "doctest.DocTestCase.debug",
        "doctest.debug_src",
        "doctest.debug_script",
        "doctest.testfile",
        "typing.ForwardRef._evaluate",
        "typing._eval_type",
        "typing.evaluate_forward_ref",
        "typing.get_type_hints",
        "annotationlib.ForwardRef._evaluate",
        "annotationlib.ForwardRef.evaluate",
        "annotationlib.get_annotations",
        "inspect.get_annotations",
        "inspect.signature",
        "inspect.Signature.from_callable",
        "logging.config.dictConfig",
        "logging.config.fileConfig",
        "optparse.Values.read_file",
    ],
)
def test_exec_wrapper_targets_are_blocklisted(target: str) -> None:
    # Standard-library functions that exec/eval a user-supplied string. They have
    # no legitimate instantiate() use, so they are blocked directly (this is what
    # closed the reporter's timeit.timeit vector). The whitelist stays the boundary.
    cfg = OmegaConf.create({"foo": {"_target_": target}})
    with raises(InstantiationException, match="blocklisted"):
        _instantiate2.instantiate(cfg)


@mark.parametrize(
    "cfg",
    [
        {
            "_target_": "bdb.Bdb.run",
            "_args_": [
                {"_target_": "bdb.Bdb"},
                "raise RuntimeError('must not execute')",
            ],
        },
        {
            "_target_": "timeit.Timer.timeit",
            "_args_": [
                {
                    "_target_": "timeit.Timer",
                    "stmt": "raise RuntimeError('must not execute')",
                },
                1,
            ],
        },
        {
            "_target_": "doctest.debug_script",
            "_args_": ["raise RuntimeError('must not execute')"],
        },
        {
            "_target_": "typing.ForwardRef._evaluate",
            "_args_": [
                {
                    "_target_": "typing.ForwardRef",
                    "_args_": [
                        "(_ for _ in ()).throw(RuntimeError('must not execute'))"
                    ],
                },
                {},
                {},
            ],
            "recursive_guard": {"_target_": "builtins.set"},
        },
        {
            "_target_": "inspect.get_annotations",
            "obj": {
                "_target_": "builtins.type",
                "_args_": [
                    "Probe",
                    {"_target_": "builtins.tuple"},
                    {
                        "__annotations__": {
                            "payload": "(_ for _ in ()).throw(RuntimeError('must not execute'))"
                        }
                    },
                ],
                "_convert_": "all",
            },
            "eval_str": True,
        },
    ],
)
def test_exec_wrapper_chains_are_blocklisted(cfg: Any) -> None:
    with raises(InstantiationException, match="blocklisted"):
        _instantiate2.instantiate(cfg)


@mark.parametrize(
    "target",
    [
        # pure-Python fallbacks — must not slip past the pickle block
        "pickle._load",
        "pickle._loads",
        "pickle._Unpickler",
        # exec-string siblings of cProfile.run / profile.run
        "cProfile.runctx",
        "profile.runctx",
    ],
)
def test_blocklist_covers_alternate_sink_spellings(target: str) -> None:
    cfg = OmegaConf.create({"foo": {"_target_": target}})
    with raises(InstantiationException, match="blocklisted"):
        _instantiate2.instantiate(cfg)

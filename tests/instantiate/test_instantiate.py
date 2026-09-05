# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved
import _threading_local
import asyncio
import builtins
import contextlib
import copy
import functools
import inspect
import operator
import os
import pickle
import re
import warnings
from dataclasses import InitVar, dataclass, field
from functools import partial
from textwrap import dedent
from typing import Any, Callable, Dict, List, Optional, Tuple, cast
from unittest.mock import NonCallableMock

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
from omegaconf.errors import ReadonlyConfigError, ValidationError
from pytest import fixture, mark, param, raises, warns

from hydra._internal import target_policy
from hydra._internal.instantiate import _instantiate2
from hydra._internal.instantiate._instantiate2 import _resolve_target
from hydra.errors import InstantiationException
from hydra.test_utils.test_utils import assert_multiline_regex_search
from hydra.types import ConvertMode
from hydra.utils import UNSAFE_DISABLE_EXECUTION_CHECKS, execution_whitelist
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
    make_attributed_partial,
    module_function,
    module_function2,
    partial_equal,
    recisinstance,
)

operator_attrgetter = operator.attrgetter
operator_itemgetter = operator.itemgetter
operator_methodcaller = operator.methodcaller
object_getattribute = object.__getattribute__
type_getattribute = type.__getattribute__
builtin_delattr = delattr
builtin_hasattr = hasattr
builtin_setattr = setattr


class GetattrDescriptorProbe:
    descriptor_accessed = False
    descriptor_deleted = False
    descriptor_set = False

    @property
    def payload(self) -> int:
        type(self).descriptor_accessed = True
        return 10

    @payload.setter
    def payload(self, value: int) -> None:
        type(self).descriptor_set = True

    @payload.deleter
    def payload(self) -> None:
        type(self).descriptor_deleted = True


class GetattributeMeta(type):
    descriptor_accessed = False

    @property
    def payload(cls) -> int:
        type(cls).descriptor_accessed = True
        return 10


class GetattributeTypeProbe(metaclass=GetattributeMeta):
    pass


class ItemOperationProbe:
    item_accessed = False
    item_deleted = False
    item_set = False
    membership_checked = False

    def __getitem__(self, key: str) -> int:
        type(self).item_accessed = True
        return 10

    def __setitem__(self, key: str, value: int) -> None:
        type(self).item_set = True

    def __delitem__(self, key: str) -> None:
        type(self).item_deleted = True

    def __contains__(self, item: object) -> bool:
        type(self).membership_checked = True
        return False


class ConfigMutationProbe:
    def __init__(self, payload: DictConfig, fail: bool = False) -> None:
        self.payload = payload
        self.readonly = OmegaConf.is_readonly(payload)
        try:
            payload.value = 20
        except ReadonlyConfigError:
            self.mutation_blocked = True
        else:
            self.mutation_blocked = False
        if fail:
            raise RuntimeError("expected failure")


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
        kwargs.setdefault("_execution_whitelist_", UNSAFE_DISABLE_EXECUTION_CHECKS)
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


def test_callsite_override_preserves_context_only_merged_ancestor(
    instantiate_func: Any,
) -> None:
    config = OmegaConf.create(
        {
            "factory": {
                "base": "???",
                "target": {
                    "_target_": "tests.instantiate.ArgsClass",
                    "value": "${..base}",
                },
            }
        }
    )
    merged = OmegaConf.merge(config.factory, {"base": 10})

    assert merged._get_parent() is config
    assert config.factory is not merged
    assert merged.target.value == 10

    result = instantiate_func(merged.target, extra=20)

    assert result.kwargs == {"value": 10, "extra": 20}
    assert OmegaConf.is_missing(config.factory, "base")


def test_callsite_override_preserves_readonly_context_only_merged_ancestor(
    instantiate_func: Any,
) -> None:
    config = OmegaConf.create(
        {
            "factory": {
                "base": "???",
                "target": {
                    "_target_": "tests.instantiate.ArgsClass",
                    "value": "${..base}",
                },
            }
        }
    )
    OmegaConf.set_readonly(config, True)
    merged = OmegaConf.merge(config.factory, {"base": 10})

    result = instantiate_func(merged.target, extra=20)

    assert result.kwargs == {"value": 10, "extra": 20}
    assert OmegaConf.is_missing(config.factory, "base")
    assert OmegaConf.is_readonly(config)


def test_callsite_override_preserves_nested_readonly_context_only_ancestors(
    instantiate_func: Any,
) -> None:
    config = OmegaConf.create(
        {
            "outer": {
                "base": "???",
                "inner": {
                    "offset": "???",
                    "target": {
                        "_target_": "tests.instantiate.ArgsClass",
                        "value": "${...base}",
                        "offset": "${..offset}",
                    },
                },
            }
        }
    )
    OmegaConf.set_readonly(config, True)
    merged_outer = OmegaConf.merge(config.outer, {"base": 10})
    merged_inner = OmegaConf.merge(merged_outer.inner, {"offset": 20})

    result = instantiate_func(merged_inner.target, extra=30)

    assert result.kwargs == {"value": 10, "offset": 20, "extra": 30}
    assert OmegaConf.is_missing(config.outer, "base")
    assert OmegaConf.is_readonly(config)


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
        _execution_whitelist_=UNSAFE_DISABLE_EXECUTION_CHECKS,
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


def test_no_override_config_is_readonly_during_instantiation_and_restored(
    instantiate_func: Any,
) -> None:
    cfg = OmegaConf.create(
        {
            "_target_": "tests.instantiate.test_instantiate.ConfigMutationProbe",
            "_recursive_": False,
            "payload": {"value": 10},
        }
    )
    OmegaConf.set_readonly(cfg.payload, False)
    original_readonly = cfg._get_node_flag("readonly")

    result = instantiate_func(cfg)

    assert result.readonly
    assert result.mutation_blocked
    assert result.payload.value == 10
    assert cfg.payload.value == 10
    assert cfg._get_node_flag("readonly") is original_readonly
    assert cfg.payload._get_node_flag("readonly") is False
    assert not OmegaConf.is_readonly(cfg.payload)


def test_private_config_copy_remains_writable(instantiate_func: Any) -> None:
    cfg = OmegaConf.create(
        {
            "_target_": "tests.instantiate.test_instantiate.ConfigMutationProbe",
            "_recursive_": False,
            "payload": {"value": 10},
        }
    )

    result = instantiate_func(cfg, _convert_="none")

    assert not result.readonly
    assert not result.mutation_blocked
    assert result.payload.value == 20
    assert cfg.payload.value == 10


def test_top_level_sequence_is_readonly_during_instantiation_and_restored(
    instantiate_func: Any,
) -> None:
    cfg = OmegaConf.create(
        [
            {
                "_target_": "tests.instantiate.test_instantiate.ConfigMutationProbe",
                "_recursive_": False,
                "payload": {"value": 10},
            }
        ]
    )
    OmegaConf.set_readonly(cfg[0].payload, False)
    original_readonly = cfg._get_node_flag("readonly")

    result = instantiate_func(cfg)

    assert result[0].readonly
    assert result[0].mutation_blocked
    assert cfg[0].payload.value == 10
    assert cfg._get_node_flag("readonly") is original_readonly
    assert cfg[0].payload._get_node_flag("readonly") is False


def test_no_override_config_readonly_is_restored_after_failure(
    instantiate_func: Any,
) -> None:
    cfg = OmegaConf.create(
        {
            "_target_": "tests.instantiate.test_instantiate.ConfigMutationProbe",
            "_recursive_": False,
            "payload": {"value": 10},
            "fail": True,
        }
    )
    original_readonly = cfg._get_node_flag("readonly")

    with raises(InstantiationException, match="expected failure"):
        instantiate_func(cfg)

    assert cfg.payload.value == 10
    assert cfg._get_node_flag("readonly") is original_readonly
    assert not OmegaConf.is_readonly(cfg.payload)


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
def test_blacklisted_target_fails(target: str) -> None:
    cfg = OmegaConf.create({"foo": {"_target_": target}})
    with raises(
        InstantiationException,
        match=rf"Target '{re.escape(target)}'.*blacklisted",
    ) as exc_info:
        _instantiate2.instantiate(cfg)
    err = exc_info.value
    assert hasattr(err, "__cause__")
    chained = err.__cause__
    assert chained is None


@mark.parametrize(
    "target",
    [
        "importlib.machinery.ExtensionFileLoader.create_module",
        "importlib.machinery.ExtensionFileLoader.exec_module",
        "importlib.machinery.ExtensionFileLoader.load_module",
        "importlib.machinery.SourceFileLoader.exec_module",
        "importlib.machinery.SourceFileLoader.load_module",
        "importlib.machinery.SourcelessFileLoader.exec_module",
        "importlib.machinery.SourcelessFileLoader.load_module",
        "_frozen_importlib_external.ExtensionFileLoader.create_module",
        "_frozen_importlib_external.ExtensionFileLoader.exec_module",
        "_frozen_importlib_external.FileLoader.load_module",
        "_frozen_importlib_external._LoaderBasics.exec_module",
    ],
)
def test_importlib_loader_execution_targets_are_blacklisted(target: str) -> None:
    with (
        warnings.catch_warnings(),
        raises(InstantiationException, match="blacklisted"),
    ):
        warnings.simplefilter("ignore")
        _instantiate2.instantiate({"_target_": target})


@mark.parametrize(
    "target",
    [
        "importlib.machinery.SourceFileLoader.load_module",
        "_frozen_importlib_external.FileLoader.load_module",
    ],
)
def test_importlib_source_loader_is_blocked_before_execution(
    target: str, tmp_path: Any
) -> None:
    source = tmp_path / "payload.py"
    marker = tmp_path / "executed"
    source.write_text(
        f"from pathlib import Path\nPath({str(marker)!r}).write_text('executed')\n"
    )
    cfg = {
        "_target_": target,
        "_args_": [
            {
                "_target_": "importlib.machinery.SourceFileLoader",
                "_args_": ["hydra_loader_payload", str(source)],
            }
        ],
    }

    with (
        warnings.catch_warnings(),
        raises(InstantiationException, match="blacklisted"),
    ):
        warnings.simplefilter("ignore")
        _instantiate2.instantiate(cfg)

    assert not marker.exists()


def test_execution_whitelist_warns_in_legacy_mode() -> None:
    cfg = {"_target_": "tests.instantiate.AClass", "a": 10, "b": 20, "c": 30}
    with warns(UserWarning, match=r"This\s+warning will become an error in Hydra 1\.5"):
        assert _instantiate2.instantiate(cfg) == AClass(a=10, b=20, c=30)


def test_direct_functools_partial_target_warns_in_legacy_mode() -> None:
    cfg = {"_target_": "functools.partial", "_args_": [pow], "exp": 2}

    with warns(UserWarning) as records:
        factory = _instantiate2.instantiate(cfg)

    assert factory(3) == 9
    assert any(
        "Using '_target_: functools.partial' is deprecated" in str(record.message)
        and "use '_partial_: true' instead" in str(record.message)
        for record in records
    )


def test_direct_partial_warns_with_unsafe_disable_execution_checks() -> None:
    cfg = {"_target_": "functools.partial", "_args_": [pow], "exp": 2}

    with warns(UserWarning, match=r"Using '_target_: functools\.partial'"):
        factory = _instantiate2.instantiate(
            cfg, _execution_whitelist_=UNSAFE_DISABLE_EXECUTION_CHECKS
        )

    assert factory(3) == 9


def test_execution_whitelist_warning_points_to_user_callsite() -> None:
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
    with warns(UserWarning, match="_execution_whitelist_") as records:
        assert call_legacy_instantiate(cfg) == {"nested": AClass(a=10, b=20, c=30)}

    assert os.path.samefile(records[0].filename, __file__)
    assert records[0].lineno == expected_lineno


def test_execution_whitelist_applies_to_callable_targets() -> None:
    cfg = {"_target_": AClass, "a": 10, "b": 20, "c": 30}
    with warns(UserWarning, match="_execution_whitelist_"):
        assert _instantiate2.instantiate(cfg) == AClass(a=10, b=20, c=30)

    assert _instantiate2.instantiate(
        cfg, _execution_whitelist_="tests.instantiate.AClass"
    ) == AClass(a=10, b=20, c=30)

    cfg = OmegaConf.create(
        {"_target_": module_function, "x": 10},
        flags={"allow_objects": True},
    )
    with warns(UserWarning, match="_execution_whitelist_"):
        assert _instantiate2.instantiate(cfg) == 10

    with raises(
        InstantiationException,
        match=(
            "Target 'tests.instantiate.module_function' is not in the "
            "Hydra execution whitelist"
        ),
    ):
        _instantiate2.instantiate(cfg, _execution_whitelist_=[])

    assert (
        _instantiate2.instantiate(
            cfg, _execution_whitelist_="tests.instantiate.module_function"
        )
        == 10
    )

    cfg = OmegaConf.create(
        {"_target_": eval, "_args_": ["1+2"]},
        flags={"allow_objects": True},
    )
    with raises(
        InstantiationException,
        match="Target 'builtins.eval' is blacklisted",
    ):
        _instantiate2.instantiate(cfg)

    target = CallableClass()
    cfg = OmegaConf.create(
        {"_target_": target},
        flags={"allow_objects": True},
    )
    assert (
        _instantiate2.instantiate(
            cfg, _execution_whitelist_="tests.instantiate.CallableClass"
        )
        == "callable class"
    )

    cfg = {"_target_": target}
    assert (
        _instantiate2.instantiate(
            cfg, _execution_whitelist_="tests.instantiate.CallableClass"
        )
        == "callable class"
    )


def test_execution_whitelist_preserves_bound_classmethod_identity() -> None:
    cfg = OmegaConf.create(
        {"_target_": ASubclass.class_method, "y": 10},
        flags={"allow_objects": True},
    )

    result = _instantiate2.instantiate(
        cfg, _execution_whitelist_="tests.instantiate.ASubclass.class_method"
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
    "execution_whitelist",
    [
        "tests.instantiate.*",
        ["tests.instantiate.AClass"],
    ],
)
def test_execution_whitelist_allows_expected_targets(
    instantiate_func: Any, execution_whitelist: Any
) -> None:
    cfg = {"_target_": "tests.instantiate.AClass", "a": 10, "b": 20, "c": 30}
    assert instantiate_func(cfg, _execution_whitelist_=execution_whitelist) == AClass(
        a=10, b=20, c=30
    )


def test_execution_whitelist_context_allows_expected_targets() -> None:
    cfg = {"_target_": "tests.instantiate.AClass", "a": 10, "b": 20, "c": 30}
    with execution_whitelist("tests.instantiate.*"):
        assert _instantiate2.instantiate(cfg) == AClass(a=10, b=20, c=30)


def test_execution_whitelist_context_stacks_additively() -> None:
    class_cfg = {
        "_target_": "tests.instantiate.AClass",
        "a": 10,
        "b": 20,
        "c": 30,
    }
    function_cfg = {"_target_": "tests.instantiate.module_function", "x": 10}

    with execution_whitelist("tests.instantiate.AClass"):
        assert _instantiate2.instantiate(class_cfg) == AClass(a=10, b=20, c=30)
        with execution_whitelist("tests.instantiate.module_function"):
            assert _instantiate2.instantiate(class_cfg) == AClass(a=10, b=20, c=30)
            assert _instantiate2.instantiate(function_cfg) == 10

        with raises(
            InstantiationException,
            match="Target 'tests.instantiate.module_function' is not in the Hydra execution whitelist",
        ):
            _instantiate2.instantiate(function_cfg)


def test_execution_whitelist_context_reset_replaces_outer_context() -> None:
    cfg = {"_target_": "tests.instantiate.AClass", "a": 10, "b": 20, "c": 30}

    with execution_whitelist("tests.instantiate.*"):
        with execution_whitelist([], reset=True):
            with raises(
                InstantiationException,
                match="Target 'tests.instantiate.AClass' is not in the Hydra execution whitelist",
            ):
                _instantiate2.instantiate(cfg)

        assert _instantiate2.instantiate(cfg) == AClass(a=10, b=20, c=30)


def test_execution_whitelist_policy_isolates_overlapping_async_contexts() -> None:
    policy = execution_whitelist("tests.instantiate.AClass")
    first_entered = asyncio.Event()
    second_entered = asyncio.Event()
    first_exited = asyncio.Event()

    async def first() -> None:
        try:
            with policy:
                first_entered.set()
                await second_entered.wait()
        finally:
            first_exited.set()

    async def second() -> None:
        await first_entered.wait()
        with policy:
            second_entered.set()
            await first_exited.wait()

    async def run() -> None:
        await asyncio.gather(first(), second())

    asyncio.run(run())


def test_execution_whitelist_policy_can_be_passed_to_instantiate(
    instantiate_func: Any,
) -> None:
    cfg = {"_target_": "tests.instantiate.AClass", "a": 10, "b": 20, "c": 30}
    policy = execution_whitelist("tests.instantiate.*", reset=True)
    assert instantiate_func(cfg, _execution_whitelist_=policy) == AClass(
        a=10, b=20, c=30
    )


def test_execution_whitelist_policy_reset_replaces_context_for_instantiate() -> None:
    cfg = {"_target_": "tests.instantiate.AClass", "a": 10, "b": 20, "c": 30}

    with execution_whitelist("tests.instantiate.*"):
        with raises(
            InstantiationException,
            match="Target 'tests.instantiate.AClass' is not in the Hydra execution whitelist",
        ):
            _instantiate2.instantiate(
                cfg, _execution_whitelist_=execution_whitelist([], reset=True)
            )


@mark.parametrize(
    "execution_whitelist",
    [
        [],
        "tests.other.*",
        ["tests.instantiate.BClass"],
    ],
)
def test_execution_whitelist_blocks_unlisted_targets(
    instantiate_func: Any, execution_whitelist: Any
) -> None:
    cfg = {"_target_": "tests.instantiate.AClass", "a": 10}
    with raises(
        InstantiationException,
        match="Target 'tests.instantiate.AClass' is not in the Hydra execution whitelist",
    ):
        instantiate_func(cfg, _execution_whitelist_=execution_whitelist)


@mark.parametrize("execution_whitelist", ["*", "*.*", "tests.*.AClass"])
def test_execution_whitelist_rejects_broad_wildcards(
    instantiate_func: Any, execution_whitelist: str
) -> None:
    cfg = {"_target_": "tests.instantiate.AClass", "a": 10}
    with raises(
        InstantiationException,
        match="Invalid _execution_whitelist_ entry",
    ):
        instantiate_func(cfg, _execution_whitelist_=execution_whitelist)


def test_execution_whitelist_in_config_is_rejected(instantiate_func: Any) -> None:
    cfg = {
        "_target_": "tests.instantiate.AClass",
        "_execution_whitelist_": "tests.instantiate.*",
        "a": 10,
    }
    with raises(
        InstantiationException,
        match="_execution_whitelist_ must be passed to instantiate\\(\\)",
    ):
        instantiate_func(cfg)


def test_execution_whitelist_can_explicitly_allow_blacklisted_targets(
    instantiate_func: Any,
) -> None:
    assert target_policy._is_blacklisted_target("_sitebuiltins.Quitter")
    assert not target_policy._is_non_whitelistable_target("_sitebuiltins.Quitter")
    cfg = {
        "_target_": "_sitebuiltins.Quitter",
        "_args_": ["probe", None],
    }
    result = instantiate_func(cfg, _execution_whitelist_="_sitebuiltins.Quitter")
    assert type(result).__module__ == "_sitebuiltins"
    assert type(result).__qualname__ == "Quitter"


@mark.parametrize("target", sorted(target_policy.UNCONTROLLED_EXECUTION_TARGETS))
def test_uncontrolled_execution_targets_cannot_be_whitelisted(target: str) -> None:
    assert target_policy._is_blacklisted_target(target)
    assert target_policy._is_non_whitelistable_target(target)
    cfg = {"_target_": target}

    with raises(InstantiationException, match="cannot be authorized"):
        _instantiate2.instantiate(cfg, _execution_whitelist_=target)


@mark.parametrize(
    "target",
    [
        "os.execl",
        "os.spawnl",
        "logging.config.valid_ident",
        "doctest.OutputChecker",
        "shelve.open",
        "trace.main",
        "pydoc.cram",
        "pdb.help",
        "bdb.Bdb",
    ],
)
def test_uncontrolled_execution_families_cannot_be_whitelisted(target: str) -> None:
    assert target_policy._is_blacklisted_target(target)
    assert target_policy._is_non_whitelistable_target(target)
    with raises(InstantiationException, match="cannot be authorized"):
        _instantiate2.instantiate({"_target_": target}, _execution_whitelist_=target)


def test_getcwd_is_not_blacklisted() -> None:
    with warns(UserWarning, match="with no\n_execution_whitelist_"):
        assert _instantiate2.instantiate({"_target_": "os.getcwd"}) == os.getcwd()

    assert (
        _instantiate2.instantiate(
            {"_target_": "os.getcwd"}, _execution_whitelist_="os.getcwd"
        )
        == os.getcwd()
    )


def test_ineffective_sys_modules_entries_are_not_in_policy() -> None:
    for target in (
        "sys.modules.ipdb",
        "sys.modules.joblib",
        "sys.modules.resource",
        "sys.modules.psutil",
        "sys.modules.tkinter",
    ):
        assert target not in target_policy.DEFAULT_BLACKLISTED_MODULES
        assert target not in target_policy.UNCONTROLLED_EXECUTION_TARGETS


def test_blacklist_policy_sections_are_disjoint() -> None:
    assert target_policy.DEFAULT_BLACKLISTED_MODULES.isdisjoint(
        target_policy.UNCONTROLLED_EXECUTION_TARGETS
    )


@mark.parametrize(
    "target",
    [
        "builtins.filter",
        "itertools.dropwhile",
        "itertools.filterfalse",
        "itertools.takewhile",
    ],
)
def test_non_result_lazy_callback_targets_are_not_blacklisted(target: str) -> None:
    assert not target_policy._is_blacklisted_target(target)


def test_one_argument_iter_target_is_allowed() -> None:
    result = _instantiate2.instantiate(
        {"_target_": "builtins.iter", "_args_": [[1, 2]]},
        _execution_whitelist_="builtins.iter",
    )

    assert list(result) == [1, 2]


def test_two_argument_iter_callback_is_blocked_in_legacy_mode() -> None:
    calls: List[str] = []

    def callback() -> int:
        calls.append("called")
        return 1

    cfg = {"_target_": "builtins.iter", "_args_": [callback, 2]}
    with (
        warns(UserWarning, match="_execution_whitelist_"),
        raises(InstantiationException, match="two-argument callback form"),
    ):
        _instantiate2.instantiate(cfg)

    assert calls == []


def test_two_argument_iter_callback_cannot_be_whitelisted() -> None:
    calls: List[str] = []

    def callback() -> int:
        calls.append("called")
        return 1

    cfg = {"_target_": "builtins.iter", "_args_": [callback, 2]}
    with raises(InstantiationException, match="two-argument callback form"):
        _instantiate2.instantiate(cfg, _execution_whitelist_="builtins.iter")

    assert calls == []


def test_partial_call_target_cannot_be_whitelisted() -> None:
    calls: List[str] = []

    def callback() -> None:
        calls.append("called")

    cfg = {
        "_target_": "functools.partial.__call__",
        "_args_": [partial(callback)],
    }
    with raises(
        InstantiationException,
        match=r"Target 'functools\.partial\.__call__'.*cannot be authorized",
    ):
        _instantiate2.instantiate(
            cfg, _execution_whitelist_="functools.partial.__call__"
        )

    assert calls == []


def test_property_get_target_cannot_be_whitelisted() -> None:
    calls: List[str] = []

    class Receiver:
        pass

    def getter(_: Receiver) -> int:
        calls.append("called")
        return 42

    cfg = {
        "_target_": "builtins.property.__get__",
        "_args_": [property(getter), Receiver(), Receiver],
    }
    with raises(
        InstantiationException,
        match=r"Target 'builtins\.property\.__get__'.*cannot be authorized",
    ):
        _instantiate2.instantiate(
            cfg, _execution_whitelist_="builtins.property.__get__"
        )

    assert calls == []


@mark.parametrize(
    ("target", "canonical_target"),
    [
        ("builtins.map.__new__", "builtins.map"),
        ("builtins.map.__call__", "builtins.map"),
        ("builtins.classmethod.__new__", "builtins.classmethod"),
        ("builtins.classmethod.__get__", "builtins.classmethod"),
        ("builtins.staticmethod.__new__", "builtins.staticmethod"),
        ("builtins.type.__new__.__call__", "builtins.type.__new__"),
        ("builtins.type.__call__.__call__", "builtins.type.__call__"),
        (
            "concurrent.futures.Executor.map",
            "concurrent.futures._base.Executor.map",
        ),
        (
            "concurrent.futures.ThreadPoolExecutor.submit",
            "concurrent.futures.thread.ThreadPoolExecutor.submit",
        ),
        (
            "concurrent.futures.ProcessPoolExecutor.submit",
            "concurrent.futures.process.ProcessPoolExecutor.submit",
        ),
        (
            "contextlib._GeneratorContextManager.__call__",
            "contextlib.ContextDecorator.__call__",
        ),
        (
            "contextlib._AsyncGeneratorContextManager.__call__",
            "contextlib.AsyncContextDecorator.__call__",
        ),
        ("functools.reduce.__call__", "_functools.reduce"),
        ("functools.partialmethod.__call__", "functools.partialmethod"),
        (
            "functools.singledispatchmethod.__get__.__call__",
            "functools.singledispatchmethod.__get__",
        ),
        ("types.MethodType.__new__", "types.MethodType"),
        ("types.FunctionType.__new__", "types.FunctionType"),
        ("types.LambdaType", "types.FunctionType"),
        (
            "builtins.dict.get.__get__",
            "types.MethodDescriptorType.__get__",
        ),
        (
            "builtins.object.__getattribute__.__get__",
            "types.WrapperDescriptorType.__get__",
        ),
        (
            "multiprocessing.pool.ThreadPool.apply_async",
            "multiprocessing.pool.Pool.apply_async",
        ),
        (
            "multiprocessing.pool.ThreadPool.starmap_async",
            "multiprocessing.pool.Pool.starmap_async",
        ),
        ("itertools.accumulate.__new__", "itertools.accumulate"),
        ("itertools.groupby.__new__", "itertools.groupby"),
        ("itertools.starmap.__new__", "itertools.starmap"),
    ],
)
def test_callable_dispatch_aliases_are_non_whitelistable(
    target: str, canonical_target: str
) -> None:
    with raises(
        InstantiationException,
        match=rf"Target '{re.escape(canonical_target)}'.*cannot be authorized",
    ):
        _instantiate2.instantiate({"_target_": target}, _execution_whitelist_=target)


@mark.parametrize(
    "target",
    [
        "operator.call",
        "operator.contains",
        "operator.delitem",
        "operator.attrgetter",
        "operator.getitem",
        "operator.itemgetter",
        "operator.methodcaller",
        "operator.setitem",
        "_operator.call",
        "_operator.contains",
        "_operator.delitem",
        "_operator.attrgetter",
        "_operator.getitem",
        "_operator.itemgetter",
        "_operator.methodcaller",
        "_operator.setitem",
    ],
)
def test_operator_dispatch_targets_are_blacklisted(target: str) -> None:
    with raises(InstantiationException, match="blacklisted"):
        _instantiate2.instantiate({"_target_": target})


@mark.parametrize(
    "target",
    [
        "operator.call",
        "operator.contains",
        "operator.delitem",
        "operator.attrgetter",
        "operator.getitem",
        "operator.itemgetter",
        "operator.methodcaller",
        "operator.setitem",
        "_operator.call",
        "_operator.contains",
        "_operator.delitem",
        "_operator.attrgetter",
        "_operator.getitem",
        "_operator.itemgetter",
        "_operator.methodcaller",
        "_operator.setitem",
    ],
)
def test_execution_whitelist_cannot_authorize_operator_dispatch(target: str) -> None:
    with raises(
        InstantiationException,
        match=r"generic selection or dispatch using\s+config data",
    ):
        _instantiate2.instantiate({"_target_": target}, _execution_whitelist_=target)


@mark.parametrize(
    ("target", "execution_whitelist"),
    [
        (
            "operator.methodcaller.__new__",
            "operator.methodcaller.__new__",
        ),
        ("operator.methodcaller.__new__", "operator.*"),
        (
            "operator.methodcaller.__new__.__call__",
            "operator.methodcaller.__new__.__call__",
        ),
        (
            "tests.instantiate.test_instantiate.operator_methodcaller.__new__",
            "tests.instantiate.test_instantiate.operator_methodcaller.__new__",
        ),
    ],
)
def test_execution_whitelist_cannot_authorize_methodcaller_constructor(
    target: str, execution_whitelist: str
) -> None:
    with raises(
        InstantiationException,
        match=r"Target 'operator\.methodcaller'.*cannot be authorized",
    ):
        _instantiate2.instantiate(
            {"_target_": target}, _execution_whitelist_=execution_whitelist
        )


def test_execution_whitelist_rejects_methodcaller_constructor_callable() -> None:
    with raises(
        InstantiationException,
        match=r"Target 'operator\.methodcaller'.*cannot be authorized",
    ):
        _resolve_target(
            operator.methodcaller.__new__,
            full_key="",
            execution_whitelist=("operator.methodcaller",),
        )


def test_methodcaller_constructor_alias_is_blacklisted() -> None:
    with raises(
        InstantiationException,
        match=r"Target 'operator\.methodcaller'.*resolved from.*blacklisted",
    ):
        _instantiate2.instantiate({"_target_": "operator.methodcaller.__new__"})


@mark.parametrize(
    ("target", "execution_whitelist"),
    [
        ("operator.attrgetter.__new__", "operator.attrgetter.__new__"),
        ("operator.attrgetter.__new__", "operator.*"),
        (
            "operator.attrgetter.__new__.__call__",
            "operator.attrgetter.__new__.__call__",
        ),
        (
            "tests.instantiate.test_instantiate.operator_attrgetter.__new__",
            "tests.instantiate.test_instantiate.operator_attrgetter.__new__",
        ),
    ],
)
def test_execution_whitelist_cannot_authorize_attrgetter_constructor(
    target: str, execution_whitelist: str
) -> None:
    with raises(
        InstantiationException,
        match=r"Target 'operator\.attrgetter'.*cannot be authorized",
    ):
        _instantiate2.instantiate(
            {"_target_": target}, _execution_whitelist_=execution_whitelist
        )


def test_execution_whitelist_rejects_attrgetter_constructor_callable() -> None:
    with raises(
        InstantiationException,
        match=r"Target 'operator\.attrgetter'.*cannot be authorized",
    ):
        _resolve_target(
            operator.attrgetter.__new__,
            full_key="",
            execution_whitelist=("operator.attrgetter",),
        )


def test_attrgetter_constructor_alias_is_blacklisted() -> None:
    with raises(
        InstantiationException,
        match=r"Target 'operator\.attrgetter'.*resolved from.*blacklisted",
    ):
        _instantiate2.instantiate({"_target_": "operator.attrgetter.__new__"})


@mark.parametrize(
    "target",
    [
        "operator.itemgetter.__new__",
        "tests.instantiate.test_instantiate.operator_itemgetter.__new__",
    ],
)
def test_execution_whitelist_cannot_authorize_itemgetter_constructor(
    target: str,
) -> None:
    with raises(
        InstantiationException,
        match=r"Target 'operator\.itemgetter'.*cannot be authorized",
    ):
        _instantiate2.instantiate({"_target_": target}, _execution_whitelist_=target)


def test_itemgetter_constructor_alias_is_blacklisted() -> None:
    with raises(
        InstantiationException,
        match=r"Target 'operator\.itemgetter'.*resolved from.*blacklisted",
    ):
        _instantiate2.instantiate({"_target_": "operator.itemgetter.__new__"})


@mark.parametrize(
    ("target", "descriptor", "canonical_target"),
    [
        (
            "operator.attrgetter.__call__",
            operator.attrgetter.__call__,
            "operator.attrgetter",
        ),
        (
            "operator.attrgetter.__reduce__",
            operator.attrgetter.__reduce__,
            "operator.attrgetter",
        ),
        (
            "operator.itemgetter.__call__",
            operator.itemgetter.__call__,
            "operator.itemgetter",
        ),
        (
            "operator.itemgetter.__reduce__",
            operator.itemgetter.__reduce__,
            "operator.itemgetter",
        ),
        (
            "operator.methodcaller.__call__",
            operator.methodcaller.__call__,
            "operator.methodcaller",
        ),
        (
            "operator.methodcaller.__reduce__",
            operator.methodcaller.__reduce__,
            "operator.methodcaller",
        ),
    ],
)
def test_execution_whitelist_cannot_authorize_operator_dispatch_descriptors(
    target: str, descriptor: Any, canonical_target: str
) -> None:
    match = rf"Target '{canonical_target}'.*cannot be authorized"
    with raises(InstantiationException, match=match):
        _instantiate2.instantiate({"_target_": target}, _execution_whitelist_=target)

    with raises(InstantiationException, match=match):
        _resolve_target(descriptor, full_key="", execution_whitelist=(target,))


@mark.parametrize(
    ("target", "canonical_target"),
    [
        ("operator.attrgetter.__call__", "operator.attrgetter"),
        ("operator.itemgetter.__call__", "operator.itemgetter"),
        ("operator.methodcaller.__call__", "operator.methodcaller"),
    ],
)
def test_operator_dispatch_descriptors_are_blacklisted(
    target: str, canonical_target: str
) -> None:
    with raises(
        InstantiationException,
        match=rf"Target '{canonical_target}'.*resolved from.*blacklisted",
    ):
        _instantiate2.instantiate({"_target_": target})


def test_legacy_operator_error_does_not_recommend_execution_whitelist() -> None:
    with raises(InstantiationException) as exc_info:
        _instantiate2.instantiate({"_target_": "operator.methodcaller"})

    message = str(exc_info.value)
    assert "_execution_whitelist_" not in message
    assert "UNSAFE_DISABLE_EXECUTION_CHECKS" in message
    assert "Set '_target_' to the intended callable instead" in message


@mark.parametrize(
    ("target", "receiver", "marker_owner", "execution_whitelist"),
    [
        (
            "builtins.object.__getattribute__",
            {"_target_": "tests.instantiate.test_instantiate.GetattrDescriptorProbe"},
            GetattrDescriptorProbe,
            [
                "builtins.object.__getattribute__",
                "tests.instantiate.test_instantiate.GetattrDescriptorProbe",
            ],
        ),
        (
            "tests.instantiate.test_instantiate.object_getattribute",
            {"_target_": "tests.instantiate.test_instantiate.GetattrDescriptorProbe"},
            GetattrDescriptorProbe,
            [
                "tests.instantiate.test_instantiate.object_getattribute",
                "tests.instantiate.test_instantiate.GetattrDescriptorProbe",
            ],
        ),
        (
            "builtins.type.__getattribute__",
            {
                "_target_": "hydra.utils.get_class",
                "path": "tests.instantiate.test_instantiate.GetattributeTypeProbe",
            },
            GetattributeMeta,
            [
                "builtins.type.__getattribute__",
                "hydra.utils.get_class",
                "tests.instantiate.test_instantiate.GetattributeTypeProbe",
            ],
        ),
        (
            "tests.instantiate.test_instantiate.type_getattribute",
            {
                "_target_": "hydra.utils.get_class",
                "path": "tests.instantiate.test_instantiate.GetattributeTypeProbe",
            },
            GetattributeMeta,
            [
                "tests.instantiate.test_instantiate.type_getattribute",
                "hydra.utils.get_class",
                "tests.instantiate.test_instantiate.GetattributeTypeProbe",
            ],
        ),
    ],
)
def test_execution_whitelist_rejects_getattribute_before_descriptor_access(
    target: str,
    receiver: Dict[str, Any],
    marker_owner: Any,
    execution_whitelist: List[str],
) -> None:
    marker_owner.descriptor_accessed = False
    cfg = {"_target_": target, "_args_": [receiver, "payload"]}

    with raises(
        InstantiationException,
        match=r"Target 'builtins\.(?:object|type)\.__getattribute__'.*cannot be authorized",
    ):
        _instantiate2.instantiate(cfg, _execution_whitelist_=execution_whitelist)

    assert not marker_owner.descriptor_accessed


def test_execution_whitelist_rejects_getattr_before_descriptor_access() -> None:
    GetattrDescriptorProbe.descriptor_accessed = False
    probe_target = "tests.instantiate.test_instantiate.GetattrDescriptorProbe"
    cfg = {
        "_target_": "builtins.getattr",
        "_args_": [
            {"_target_": probe_target},
            "payload",
        ],
    }

    with raises(
        InstantiationException,
        match=r"Target 'builtins\.getattr'.*cannot be authorized",
    ):
        _instantiate2.instantiate(
            cfg,
            _execution_whitelist_=[
                "builtins.getattr",
                probe_target,
            ],
        )

    assert not GetattrDescriptorProbe.descriptor_accessed


@mark.parametrize(
    ("target", "canonical_target", "args", "marker"),
    [
        ("builtins.hasattr", "builtins.hasattr", ["payload"], "descriptor_accessed"),
        (
            "tests.instantiate.test_instantiate.builtin_hasattr",
            "builtins.hasattr",
            ["payload"],
            "descriptor_accessed",
        ),
        ("builtins.setattr", "builtins.setattr", ["payload", 20], "descriptor_set"),
        (
            "tests.instantiate.test_instantiate.builtin_setattr",
            "builtins.setattr",
            ["payload", 20],
            "descriptor_set",
        ),
        ("builtins.delattr", "builtins.delattr", ["payload"], "descriptor_deleted"),
        (
            "tests.instantiate.test_instantiate.builtin_delattr",
            "builtins.delattr",
            ["payload"],
            "descriptor_deleted",
        ),
    ],
)
def test_execution_whitelist_rejects_attribute_dispatch_before_descriptor_access(
    target: str, canonical_target: str, args: List[Any], marker: str
) -> None:
    probe_target = "tests.instantiate.test_instantiate.GetattrDescriptorProbe"
    setattr(GetattrDescriptorProbe, marker, False)
    cfg = {
        "_target_": target,
        "_args_": [{"_target_": probe_target}, *args],
    }

    with raises(
        InstantiationException,
        match=rf"Target '{re.escape(canonical_target)}'.*cannot be authorized",
    ):
        _instantiate2.instantiate(
            cfg,
            _execution_whitelist_=[target, probe_target],
        )

    assert not getattr(GetattrDescriptorProbe, marker)


@mark.parametrize(
    ("target", "args", "marker"),
    [
        ("operator.getitem", ["payload"], "item_accessed"),
        ("_operator.getitem", ["payload"], "item_accessed"),
        ("operator.setitem", ["payload", 20], "item_set"),
        ("_operator.setitem", ["payload", 20], "item_set"),
        ("operator.delitem", ["payload"], "item_deleted"),
        ("_operator.delitem", ["payload"], "item_deleted"),
        ("operator.contains", ["payload"], "membership_checked"),
        ("_operator.contains", ["payload"], "membership_checked"),
    ],
)
def test_execution_whitelist_rejects_item_dispatch_before_receiver_access(
    target: str, args: List[Any], marker: str
) -> None:
    probe_target = "tests.instantiate.test_instantiate.ItemOperationProbe"
    setattr(ItemOperationProbe, marker, False)
    cfg = {
        "_target_": target,
        "_args_": [{"_target_": probe_target}, *args],
    }

    with raises(
        InstantiationException,
        match=r"Target '_?operator\.(?:contains|delitem|getitem|setitem)'.*cannot be authorized",
    ):
        _instantiate2.instantiate(
            cfg,
            _execution_whitelist_=[target, probe_target],
        )

    assert not getattr(ItemOperationProbe, marker)


def test_getattr_allows_non_callable_result_in_legacy_mode() -> None:
    cfg = {
        "_target_": "builtins.getattr",
        "_args_": [
            {"_target_": "types.SimpleNamespace", "value": 10},
            "value",
        ],
    }

    with warns(UserWarning, match="_execution_whitelist_"):
        assert _instantiate2.instantiate(cfg) == 10


def test_getattr_callable_result_applies_legacy_blacklist() -> None:
    cfg = {
        "_target_": "builtins.getattr",
        "_args_": [
            {"_target_": "timeit.Timer", "stmt": "40 + 2"},
            "timeit",
        ],
    }

    with (
        warns(UserWarning, match="_execution_whitelist_"),
        raises(
            InstantiationException,
            match=r"Target 'timeit\.Timer\.timeit'.*blacklisted",
        ),
    ):
        _instantiate2.instantiate(cfg)


def test_getattr_unwraps_partial_callable_result() -> None:
    cfg = {
        "_target_": "builtins.getattr",
        "_args_": [partial(eval), "__call__"],
    }

    with (
        warns(UserWarning, match="_execution_whitelist_"),
        raises(
            InstantiationException,
            match=r"Target 'builtins\.eval'.*blacklisted",
        ),
    ):
        _instantiate2.instantiate(cfg)


def test_execution_whitelist_cannot_authorize_getattr_callable_result() -> None:
    cfg = {
        "_target_": "builtins.getattr",
        "_args_": [
            {"_target_": "timeit.Timer", "stmt": "40 + 2"},
            "timeit",
        ],
    }
    with raises(
        InstantiationException,
        match=r"Target 'builtins\.getattr'.*cannot be authorized",
    ):
        _instantiate2.instantiate(
            cfg,
            _execution_whitelist_=[
                "builtins.getattr",
                "timeit.Timer",
                "timeit.Timer.timeit",
            ],
        )


def test_getattr_map_dispatch_chain_is_rejected() -> None:
    cfg = {
        "_target_": "builtins.list",
        "_args_": [
            {
                "_target_": "builtins.map",
                "_args_": [
                    {
                        "_target_": "builtins.getattr",
                        "_args_": [
                            {"_target_": "timeit.Timer", "stmt": "40 + 2"},
                            "timeit",
                        ],
                    },
                    [1],
                ],
            }
        ],
    }

    with raises(
        InstantiationException,
        match=r"Target 'builtins\.map'.*cannot be authorized",
    ):
        _instantiate2.instantiate(
            cfg,
            _execution_whitelist_=[
                "builtins.getattr",
                "builtins.list",
                "builtins.map",
                "timeit.Timer",
            ],
        )


def test_getattr_cannot_be_partial_with_execution_whitelist() -> None:
    cfg = {"_target_": "builtins.getattr", "_partial_": True}

    with raises(
        InstantiationException,
        match=r"Target 'builtins\.getattr'.*cannot be authorized",
    ):
        _instantiate2.instantiate(cfg, _execution_whitelist_="builtins.getattr")


def test_unsafe_disable_execution_checks_permits_partial_getattr() -> None:
    cfg = {"_target_": "builtins.getattr", "_partial_": True}

    factory = _instantiate2.instantiate(
        cfg, _execution_whitelist_=UNSAFE_DISABLE_EXECUTION_CHECKS
    )
    assert factory(str, "upper") is str.upper


@mark.parametrize(
    ("target", "execution_whitelist"),
    [
        ("functools.partial", "functools.partial"),
        ("functools.partial", "functools.*"),
        (
            "tests.instantiate.test_instantiate.partial",
            "tests.instantiate.test_instantiate.partial",
        ),
    ],
)
def test_execution_whitelist_authorizes_functools_partial_and_effective_callable(
    target: str, execution_whitelist: str
) -> None:
    cfg = {"_target_": target, "_args_": [pow], "exp": 2}

    with warns(UserWarning, match=r"Using '_target_: functools\.partial'"):
        factory = _instantiate2.instantiate(
            cfg,
            _execution_whitelist_=[execution_whitelist, "builtins.pow"],
        )

    assert factory(3) == 9


def test_execution_whitelist_checks_functools_partial_effective_callable() -> None:
    cfg = {"_target_": "functools.partial", "_args_": [pow], "exp": 2}

    with (
        warns(UserWarning, match=r"Using '_target_: functools\.partial'"),
        raises(
            InstantiationException,
            match=r"Target 'builtins\.pow'.*not in the Hydra execution whitelist",
        ),
    ):
        _instantiate2.instantiate(cfg, _execution_whitelist_="functools.partial")


@mark.parametrize(
    ("target", "execution_whitelist"),
    [
        ("functools.partial.__new__", "functools.partial.__new__"),
        ("functools.partial.__new__", "functools.*"),
        (
            "tests.instantiate.test_instantiate.partial.__new__",
            "tests.instantiate.test_instantiate.partial.__new__",
        ),
    ],
)
def test_execution_whitelist_authorizes_functools_partial_constructor(
    target: str, execution_whitelist: str
) -> None:
    cfg = {"_target_": target, "_args_": [partial, pow], "exp": 2}

    with warns(UserWarning, match=r"Using '_target_: functools\.partial'"):
        factory = _instantiate2.instantiate(
            cfg,
            _execution_whitelist_=[execution_whitelist, "builtins.pow"],
        )

    assert factory(3) == 9


@mark.parametrize(
    "execution_whitelist", [None, ["functools.partial.__new__", "builtins.len"]]
)
def test_functools_partial_constructor_rejects_subclass_with_spoofed_func(
    execution_whitelist: Any,
) -> None:
    spoofed_partial = type(
        "SpoofedPartial",
        (partial,),
        {"func": property(lambda _: len)},
    )
    cfg = {
        "_target_": "functools.partial.__new__",
        "_args_": [spoofed_partial, eval],
    }

    with (
        warns(UserWarning),
        raises(InstantiationException, match="cannot return partial subclasses"),
    ):
        _instantiate2.instantiate(cfg, _execution_whitelist_=execution_whitelist)


def test_unsafe_disable_execution_checks_permits_partial_subclass() -> None:
    spoofed_partial = type(
        "SpoofedPartial",
        (partial,),
        {"func": property(lambda _: len)},
    )
    cfg = {
        "_target_": "functools.partial.__new__",
        "_args_": [spoofed_partial, eval],
    }

    with warns(UserWarning, match=r"Using '_target_: functools\.partial'"):
        factory = _instantiate2.instantiate(
            cfg, _execution_whitelist_=UNSAFE_DISABLE_EXECUTION_CHECKS
        )

    assert factory("1 + 2") == 3


def test_direct_functools_partial_applies_legacy_blacklist_to_callable() -> None:
    cfg = {"_target_": "functools.partial", "_args_": [eval]}

    with (
        warns(UserWarning),
        raises(
            InstantiationException,
            match=r"Target 'builtins\.eval'.*blacklisted",
        ),
    ):
        _instantiate2.instantiate(cfg)


def test_unsafe_disable_checks_permit_blacklisted_partial_callable() -> None:
    cfg = {"_target_": "functools.partial", "_args_": [eval]}

    with warns(UserWarning, match=r"Using '_target_: functools\.partial'"):
        factory = _instantiate2.instantiate(
            cfg, _execution_whitelist_=UNSAFE_DISABLE_EXECUTION_CHECKS
        )

    assert factory("1 + 2") == 3


def test_direct_functools_partial_can_be_deferred_with_runtime_authorization() -> None:
    cfg = {"_target_": "functools.partial", "_partial_": True}

    with warns(UserWarning, match=r"Using '_target_: functools\.partial'"):
        deferred = _instantiate2.instantiate(
            cfg,
            _execution_whitelist_=["functools.partial", "builtins.pow"],
        )

    factory = deferred(pow, exp=2)
    assert factory(3) == 9


def test_native_partial_remains_whitelistable() -> None:
    cfg = {
        "_target_": "tests.instantiate.module_function",
        "_partial_": True,
        "x": 10,
    }

    factory = _instantiate2.instantiate(
        cfg, _execution_whitelist_="tests.instantiate.module_function"
    )

    assert factory() == 10


def test_callable_result_from_any_target_requires_authorization() -> None:
    cfg = {
        "_target_": "builtins.dict.get",
        "_args_": [{"eval": eval}, "eval"],
        "_convert_": "all",
    }

    with raises(
        InstantiationException,
        match=r"Target 'builtins\.eval'.*cannot be authorized",
    ):
        _instantiate2.instantiate(cfg, _execution_whitelist_="builtins.dict.get")


def test_callable_result_from_any_target_allows_authorized_callable() -> None:
    cfg = {
        "_target_": "builtins.dict.get",
        "_args_": [{"pow": pow}, "pow"],
        "_convert_": "all",
    }

    assert (
        _instantiate2.instantiate(
            cfg, _execution_whitelist_=["builtins.dict.get", "builtins.pow"]
        )
        is pow
    )


def test_callable_result_producer_whitelist_does_not_authorize_result() -> None:
    cfg = {
        "_target_": "builtins.dict.get",
        "_args_": [{"remove": os.remove}, "remove"],
        "_convert_": "all",
    }

    with raises(
        InstantiationException,
        match=r"Target 'os\.remove'.*not in the Hydra execution whitelist",
    ):
        _instantiate2.instantiate(cfg, _execution_whitelist_="builtins.dict.get")


def test_native_partial_authorizes_callable_result_when_invoked() -> None:
    deferred = _instantiate2.instantiate(
        {
            "_target_": "builtins.dict.get",
            "_partial_": True,
            "_args_": [{"pow": pow, "eval": eval}],
            "_convert_": "all",
        },
        _execution_whitelist_=["builtins.dict.get", "builtins.pow"],
    )

    assert isinstance(deferred, partial)
    assert deferred("pow") is pow
    with raises(
        InstantiationException,
        match=r"Target 'builtins\.eval'.*cannot be authorized",
    ):
        deferred("eval")


def test_native_partial_with_runtime_authorization_is_pickleable() -> None:
    deferred = _instantiate2.instantiate(
        {"_target_": "builtins.pow", "_partial_": True, "exp": 2},
        _execution_whitelist_="builtins.pow",
    )
    restored = pickle.loads(pickle.dumps(deferred))  # nosec B301

    assert isinstance(restored, partial)
    assert restored.func is pow
    assert restored(3) == 9


def test_native_partial_preserves_unsafe_policy_when_pickled() -> None:
    deferred = _instantiate2.instantiate(
        {"_target_": "builtins.dict.get", "_partial_": True},
        _execution_whitelist_=UNSAFE_DISABLE_EXECUTION_CHECKS,
    )
    restored = pickle.loads(pickle.dumps(deferred))  # nosec B301

    assert restored({"eval": eval}, "eval") is eval


def test_direct_functools_partial_authorizes_result_when_invoked() -> None:
    cfg = {
        "_target_": "functools.partial",
        "_args_": [dict.get, {"pow": pow, "eval": eval}],
        "_convert_": "all",
    }
    with warns(UserWarning, match=r"Using '_target_: functools\.partial'"):
        factory = _instantiate2.instantiate(
            cfg,
            _execution_whitelist_=[
                "functools.partial",
                "builtins.dict.get",
                "builtins.pow",
            ],
        )

    assert factory("pow") is pow
    with raises(
        InstantiationException,
        match=r"Target 'builtins\.eval'.*cannot be authorized",
    ):
        factory("eval")


def test_native_partial_mediates_partial_result_when_invoked() -> None:
    cfg = {
        "_target_": "functools.partial",
        "_partial_": True,
        "_args_": [dict.get, {"pow": pow, "eval": eval}],
        "_convert_": "all",
    }
    with warns(UserWarning, match=r"Using '_target_: functools\.partial'"):
        outer = _instantiate2.instantiate(
            cfg,
            _execution_whitelist_=[
                "functools.partial",
                "builtins.dict.get",
                "builtins.pow",
            ],
        )

    inner = outer()
    assert isinstance(inner, partial)
    assert inner("pow") is pow
    with raises(
        InstantiationException,
        match=r"Target 'builtins\.eval'.*cannot be authorized",
    ):
        inner("eval")


def test_mediated_partial_result_preserves_attributes() -> None:
    factory = _instantiate2.instantiate(
        {"_target_": make_attributed_partial},
        _execution_whitelist_=[
            "tests.instantiate.make_attributed_partial",
            "builtins.pow",
        ],
    )

    assert factory.__name__ == "square"
    assert factory.metadata == {"source": "application"}
    assert factory(3) == 9


def test_partial_discovery_target_reauthorizes_runtime_override() -> None:
    deferred = _instantiate2.instantiate(
        {
            "_target_": "hydra.utils.get_object",
            "_partial_": True,
            "path": "builtins.pow",
        },
        _execution_whitelist_=["hydra.utils.get_object", "builtins.pow"],
    )

    assert deferred() is pow
    with raises(
        InstantiationException,
        match=r"Target 'builtins\.eval'.*cannot be authorized",
    ):
        deferred(path="builtins.eval")


def test_type_introspection_is_allowed() -> None:
    assert (
        _instantiate2.instantiate(
            {"_target_": "builtins.type", "_args_": [10]},
            _execution_whitelist_=["builtins.type", "builtins.int"],
        )
        is int
    )


@mark.parametrize("target", ["builtins.type", "abc.ABCMeta"])
def test_dynamic_type_construction_is_not_allowed(target: str) -> None:
    cfg = {
        "_target_": target,
        "_args_": ["Selector", [], {"__call__": dict.get}],
        "_convert_": "all",
    }

    with raises(
        InstantiationException,
        match="cannot be used for dynamic class construction",
    ):
        _instantiate2.instantiate(cfg, _execution_whitelist_=target)


def test_partial_type_reauthorizes_runtime_arguments() -> None:
    deferred = _instantiate2.instantiate(
        {"_target_": "builtins.type", "_partial_": True},
        _execution_whitelist_=["builtins.type", "builtins.int"],
    )

    assert deferred(10) is int
    with raises(
        InstantiationException,
        match="cannot be used for dynamic class construction",
    ):
        deferred("Selector", (), {"__call__": dict.get})


def test_resolved_partial_target_cannot_bypass_dynamic_type_guard() -> None:
    initialized_subclasses: List[type] = []

    class Base:
        def __init_subclass__(cls) -> None:
            initialized_subclasses.append(cls)

    target = partial(type, "Selector", (Base,), {})
    with raises(
        InstantiationException,
        match="cannot be used for dynamic class construction",
    ):
        _instantiate2.instantiate(
            {"_target_": target},
            _execution_whitelist_="builtins.type",
        )

    assert initialized_subclasses == []


def test_resolved_partial_target_cannot_bypass_mock_parameter_guard() -> None:
    target = partial(NonCallableMock, wraps={})
    with raises(
        InstantiationException,
        match="cannot configure callable attributes",
    ):
        _instantiate2.instantiate(
            {"_target_": target},
            _execution_whitelist_="unittest.mock.NonCallableMock",
        )


@mark.skipif(
    not hasattr(functools, "Placeholder"),
    reason="functools.Placeholder requires Python 3.14",
)
def test_resolved_partial_target_substitutes_placeholder_before_guard() -> None:
    initialized_subclasses: List[type] = []

    class Base:
        def __init_subclass__(cls) -> None:
            initialized_subclasses.append(cls)

    placeholder = getattr(functools, "Placeholder")
    target = partial(type, placeholder, (Base,), {})
    with raises(
        InstantiationException,
        match="cannot be used for dynamic class construction",
    ):
        _instantiate2.instantiate(
            {"_target_": target, "_args_": ["Selector"]},
            _execution_whitelist_="builtins.type",
        )

    assert initialized_subclasses == []


@mark.skipif(
    not hasattr(functools, "Placeholder"),
    reason="functools.Placeholder requires Python 3.14",
)
def test_resolved_partial_target_preserves_unfilled_placeholder_error() -> None:
    placeholder = getattr(functools, "Placeholder")
    target = partial(pow, placeholder, 2)

    with raises(InstantiationException, match="Error in call to target"):
        _instantiate2.instantiate(
            {"_target_": target},
            _execution_whitelist_="builtins.pow",
        )


def test_metaclass_constructor_method_is_not_allowed() -> None:
    with raises(
        InstantiationException,
        match="cannot be used for dynamic class construction",
    ):
        _instantiate2.instantiate(
            {"_target_": "abc.ABCMeta.__new__"},
            _execution_whitelist_="abc.ABCMeta.__new__",
        )


@mark.parametrize(
    "target",
    ["unittest.mock.NonCallableMock", "unittest.mock.NonCallableMagicMock"],
)
def test_non_callable_mock_is_allowed(target: str) -> None:
    mock = _instantiate2.instantiate(
        {"_target_": target, "name": "inert"}, _execution_whitelist_=target
    )
    assert not callable(mock)
    assert mock._extract_mock_name() == "inert"


def test_non_callable_mock_allows_one_positional_spec() -> None:
    target = "unittest.mock.NonCallableMock"
    mock = _instantiate2.instantiate(
        {"_target_": target, "_args_": [[]]}, _execution_whitelist_=target
    )
    assert not callable(mock)


@mark.parametrize(
    "unsafe_kwargs",
    [
        {"child": dict.get},
        {"child.side_effect": dict.get},
        {"wraps": {}},
    ],
)
def test_non_callable_mock_cannot_configure_callable_children(
    unsafe_kwargs: Dict[str, Any],
) -> None:
    target = "unittest.mock.NonCallableMock"
    cfg = {"_target_": target, **unsafe_kwargs}
    with raises(
        InstantiationException,
        match="cannot configure callable attributes",
    ):
        _instantiate2.instantiate(cfg, _execution_whitelist_=target)


def test_non_callable_mock_rejects_positional_wraps() -> None:
    target = "unittest.mock.NonCallableMock"
    cfg = {"_target_": target, "_args_": [None, {}]}
    with raises(
        InstantiationException,
        match="cannot configure callable attributes",
    ):
        _instantiate2.instantiate(cfg, _execution_whitelist_=target)


def test_partial_non_callable_mock_reauthorizes_runtime_configuration() -> None:
    target = "unittest.mock.NonCallableMock"
    deferred = _instantiate2.instantiate(
        {"_target_": target, "_partial_": True}, _execution_whitelist_=target
    )

    assert not callable(deferred(name="inert"))
    with raises(
        InstantiationException,
        match="cannot configure callable attributes",
    ):
        deferred(**{"child.side_effect": dict.get})
    with raises(
        InstantiationException,
        match="cannot configure callable attributes",
    ):
        deferred(None, {})


def test_context_decorator_cannot_hide_deferred_callable_selection() -> None:
    context_manager = getattr(_threading_local, "_patch")(_threading_local.local())
    wrapper = contextlib.ContextDecorator.__call__(context_manager, dict.get)
    assert wrapper(vars(builtins), "eval") is eval

    target = "contextlib.ContextDecorator.__call__"
    cfg = {
        "_target_": target,
        "_args_": [context_manager, dict.get],
        "_convert_": "all",
    }
    with raises(
        InstantiationException,
        match=r"Target 'contextlib\.ContextDecorator\.__call__'.*cannot be authorized",
    ):
        _instantiate2.instantiate(cfg, _execution_whitelist_=target)


@mark.parametrize(
    ("target", "execution_whitelist"),
    [
        ("hydra.utils.instantiate", "hydra.utils.instantiate"),
        ("hydra.utils.call", "hydra.utils.*"),
        (
            "hydra._internal.instantiate._instantiate2.instantiate",
            "hydra._internal.instantiate._instantiate2.instantiate",
        ),
    ],
)
def test_execution_whitelist_cannot_authorize_instantiate_reentry(
    target: str, execution_whitelist: str
) -> None:
    cfg = {"_target_": target, "_recursive_": False, "config": {}}

    with raises(
        InstantiationException,
        match=r"reentrant instantiate calls do not safely inherit",
    ):
        _instantiate2.instantiate(cfg, _execution_whitelist_=execution_whitelist)


@mark.parametrize(
    ("target", "path", "expected"),
    [
        (
            "hydra._internal.utils._locate",
            "tests.instantiate.module_function",
            module_function,
        ),
        ("hydra.utils.get_class", "tests.instantiate.AClass", AClass),
        (
            "hydra.utils.get_method",
            "tests.instantiate.module_function",
            module_function,
        ),
        (
            "hydra.utils.get_static_method",
            "tests.instantiate.module_function",
            module_function,
        ),
        (
            "hydra.utils.get_object",
            "tests.instantiate.module_function",
            module_function,
        ),
    ],
)
def test_discovery_targets_require_selected_path_authorization(
    target: str, path: str, expected: Any
) -> None:
    cfg = {"_target_": target, "path": path}

    with raises(
        InstantiationException,
        match=rf"Target '{re.escape(path)}' is not in the Hydra execution whitelist",
    ):
        _instantiate2.instantiate(cfg, _execution_whitelist_=target)

    assert (
        _instantiate2.instantiate(cfg, _execution_whitelist_=[target, path]) is expected
    )


def test_internal_locate_requires_selected_path_authorization() -> None:
    cfg = {
        "_target_": "hydra._internal.utils._locate",
        "path": "tests.instantiate.module_function",
    }

    with raises(
        InstantiationException,
        match="Target 'tests.instantiate.module_function' is not in the Hydra execution whitelist",
    ):
        _instantiate2.instantiate(cfg, _execution_whitelist_="hydra.*")


def test_discovery_target_applies_legacy_blacklist_to_selected_path() -> None:
    cfg = {"_target_": "hydra.utils.get_method", "path": "builtins.eval"}

    with (
        warns(UserWarning, match="_execution_whitelist_"),
        raises(
            InstantiationException,
            match="Target 'builtins.eval' is blacklisted",
        ),
    ):
        _instantiate2.instantiate(cfg)


@mark.parametrize(
    "target",
    [
        "hydra._internal.utils._locate",
        "hydra.utils.get_class",
        "hydra.utils.get_method",
        "hydra.utils.get_static_method",
        "hydra.utils.get_object",
    ],
)
def test_partial_discovery_target_rechecks_runtime_path(target: str) -> None:
    cfg = {"_target_": target, "_partial_": True, "path": "builtins.int"}
    deferred = _instantiate2.instantiate(
        cfg, _execution_whitelist_=[target, "builtins.int"]
    )

    assert deferred() is int
    with raises(InstantiationException, match="cannot be authorized"):
        deferred(path="builtins.eval")


def test_partial_discovery_target_applies_legacy_blacklist() -> None:
    cfg = {
        "_target_": "hydra.utils.get_method",
        "_partial_": True,
        "path": "logging.os.system",
    }

    with warns(UserWarning, match="_execution_whitelist_"):
        deferred = _instantiate2.instantiate(cfg)

    with raises(
        InstantiationException,
        match=r"Target 'os\.system'.*blacklisted",
    ):
        deferred()


def test_unsafe_disable_checks_permit_partial_discovery_target() -> None:
    cfg = {"_target_": "hydra.utils.get_method", "_partial_": True}

    factory = _instantiate2.instantiate(
        cfg, _execution_whitelist_=UNSAFE_DISABLE_EXECUTION_CHECKS
    )

    assert factory("builtins.str") is str


def test_unsafe_disable_execution_checks_allows_all_targets(
    instantiate_func: Any,
) -> None:
    cfg = {"_target_": "builtins.eval", "_args_": ["1+2"]}
    assert (
        instantiate_func(cfg, _execution_whitelist_=UNSAFE_DISABLE_EXECUTION_CHECKS)
        == 3
    )


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
def test_blacklist_blocks_module_attribute_aliases(alias: str) -> None:
    # The alias is not literally in the blacklist, but resolves to a blacklisted
    # callable. Authorization must be on the resolved identity, not the string.
    with raises(InstantiationException, match="blacklisted"):
        _resolve_target(alias, "")


@mark.parametrize("target", [os.system.__call__, eval.__call__])
def test_blacklist_blocks_callable_object_aliases(target: Callable[..., Any]) -> None:
    with raises(InstantiationException, match="blacklisted"):
        _resolve_target(target, "")


def test_whitelist_blocks_module_attribute_aliases() -> None:
    # A trailing-'.*' whitelist authorizes by string prefix; the alias
    # 'logging.os.system' matches 'logging.*' but resolves to os.system and must
    # be rejected on its resolved identity.
    cfg = OmegaConf.create({"_target_": "logging.os.system", "_args_": ["true"]})
    with raises(
        InstantiationException,
        match="cannot be authorized by the",
    ):
        _instantiate2.instantiate(cfg, _execution_whitelist_="logging.*")


def test_whitelist_allows_genuine_target_under_prefix() -> None:
    # A genuine target whose resolved identity lives under the whitelisted
    # prefix keeps working.
    cfg = {"_target_": "tests.instantiate.AClass", "a": 10, "b": 20, "c": 30}
    assert _instantiate2.instantiate(
        cfg, _execution_whitelist_="tests.instantiate.*"
    ) == AClass(a=10, b=20, c=30)


@mark.parametrize("target", ["os.getcwd", "os.path.join"])
def test_whitelist_allows_os_implementation_aliases(target: str) -> None:
    assert callable(_resolve_target(target, "", ("os.*",)))


@mark.parametrize("target", [os.getcwd, os.path.join])
def test_whitelist_allows_os_callable_objects(target: Callable[..., Any]) -> None:
    assert _resolve_target(target, "", ("os.*",)) is target


@mark.parametrize(
    ("target", "message"),
    [
        ("posix.system", "cannot be authorized by the"),
        ("ntpath.join", "not in the Hydra execution whitelist"),
    ],
)
def test_whitelist_does_not_alias_literal_target_strings(
    target: str, message: str
) -> None:
    with raises(InstantiationException, match=message):
        _resolve_target(target, "", ("os.*",))


def test_whitelist_allows_exact_reexported_target() -> None:
    # An exact (non-wildcard) whitelist entry is a deliberate per-target
    # authorization and must be honored even when the class is re-exported from
    # a submodule (json.JSONDecoder actually lives in json.decoder), whose
    # canonical module.qualname differs from the config string.
    import json

    cfg = OmegaConf.create({"_target_": "json.JSONDecoder"})
    obj = _instantiate2.instantiate(cfg, _execution_whitelist_="json.JSONDecoder")
    assert isinstance(obj, json.JSONDecoder)


def test_whitelist_wildcard_still_blocks_alias_after_exact_reexport_rule() -> None:
    # The exact-match honoring must not reopen the aliasing bypass for wildcard
    # entries: 'logging.os.system' matches 'logging.*' only by wildcard, so the
    # resolved identity (os.system) is still rechecked and rejected.
    cfg = OmegaConf.create({"_target_": "logging.os.system", "_args_": ["true"]})
    with raises(
        InstantiationException,
        match="cannot be authorized by the",
    ):
        _instantiate2.instantiate(cfg, _execution_whitelist_="logging.*")


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
        "dill.load",
        "dill.loads",
        "cloudpickle.load",
        "cloudpickle.loads",
    ],
)
def test_deserialization_sinks_are_blacklisted(target: str) -> None:
    # Direct-instantiate unpickle sinks are refused on the legacy path. This
    # removes the trivial inline RCE vector; the execution whitelist remains the
    # boundary, and users who genuinely need to deserialize wrap it in their own
    # callable.
    cfg = OmegaConf.create({"foo": {"_target_": target}})
    with raises(InstantiationException, match="blacklisted"):
        _instantiate2.instantiate(cfg)


def test_pickle_base64_chain_is_blacklisted() -> None:
    # The reporter's inline vector: pickle.loads(base64.b64decode("...")). The
    # outer pickle.loads target is refused before the chain runs.
    cfg = OmegaConf.create(
        {
            "_target_": "pickle.loads",
            "_args_": [{"_target_": "base64.b64decode", "_args_": ["gA=="]}],
        }
    )
    with raises(InstantiationException, match="blacklisted"):
        _instantiate2.instantiate(cfg)


@mark.parametrize(
    "target",
    [
        "timeit.timeit",
        "timeit.repeat",
        "timeit.main",
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
        "typing.ForwardRef._evaluate",
        "typing._eval_type",
        "typing.evaluate_forward_ref",
        "typing.get_type_hints",
        "annotationlib.ForwardRef._evaluate",
        "annotationlib.ForwardRef.evaluate",
        "annotationlib.get_annotations",
        "optparse.Values.read_file",
    ],
)
def test_exec_wrapper_targets_are_blacklisted(target: str) -> None:
    # Standard-library functions that exec/eval a user-supplied string. They have
    # no legitimate instantiate() use, so they are blocked directly (this is what
    # closed the reporter's timeit.timeit vector). The whitelist stays the boundary.
    cfg = OmegaConf.create({"foo": {"_target_": target}})
    with raises(InstantiationException, match="blacklisted"):
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
            "_target_": "typing.get_type_hints",
            "_args_": [
                {
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
                }
            ],
        },
    ],
)
def test_exec_wrapper_chains_are_blacklisted(cfg: Any) -> None:
    with raises(InstantiationException, match="blacklisted"):
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
def test_blacklist_covers_alternate_sink_spellings(target: str) -> None:
    cfg = OmegaConf.create({"foo": {"_target_": target}})
    with raises(InstantiationException, match="blacklisted"):
        _instantiate2.instantiate(cfg)


@mark.parametrize(
    "target",
    [
        "logging.config.dictConfig",
        "logging.config.fileConfig",
        "logging.config.BaseConfigurator.configure_custom",
        "logging.config.DictConfigurator.configure",
        "logging.config.DictConfigurator.configure_handler",
        "logging.config.DictConfigurator.configure_formatter",
        "logging.config.DictConfigurator.configure_filter",
    ],
)
def test_logging_config_family_is_blacklisted(target: str) -> None:
    # The whole logging.config namespace resolves/calls config-named factories
    # (arbitrary code) on the legacy path. Covered by one prefix rather than
    # enumerating configurator methods. Permanent control is the whitelist
    # (GHSA-c3wx); this is the stopgap for 1.3 and the 1.4 legacy path.
    cfg = OmegaConf.create({"foo": {"_target_": target}})
    with raises(InstantiationException, match="blacklisted"):
        _instantiate2.instantiate(cfg)


@mark.parametrize(
    "target",
    [
        "doctest.run_docstring_examples",
        "doctest.testmod",
        "doctest.testfile",
        "doctest.Example.__init__",
        "doctest.DocTestRunner.run",
        "doctest.DebugRunner.run",
        "doctest.debug_script",
    ],
)
def test_doctest_family_is_blacklisted(target: str) -> None:
    # doctest executes example code from docstrings/files; the whole family is
    # covered by one prefix (no legitimate instantiate() use).
    cfg = OmegaConf.create({"foo": {"_target_": target}})
    with raises(InstantiationException, match="blacklisted"):
        _instantiate2.instantiate(cfg)


@mark.parametrize(
    "target",
    [
        "shelve.open",
        "shelve.DbfilenameShelf",
        "shelve.Shelf",
        "trace.CoverageResults",
        "trace.Trace.results",
        "trace.Trace.run",
    ],
)
def test_shelve_and_trace_families_are_blacklisted(target: str) -> None:
    # shelve shelf classes unpickle on access; trace delegates to CoverageResults
    # which unpickles. Whole families covered by prefixes rather than one entry.
    cfg = OmegaConf.create({"foo": {"_target_": target}})
    with raises(InstantiationException, match="blacklisted"):
        _instantiate2.instantiate(cfg)


@mark.parametrize(
    "target",
    ["pydoc.importfile", "pydoc.safeimport", "pydoc.render_doc"],
)
def test_pydoc_family_is_blacklisted(target: str) -> None:
    # pydoc imports/executes modules and files; covered by a prefix.
    cfg = OmegaConf.create({"foo": {"_target_": target}})
    with raises(InstantiationException, match="blacklisted"):
        _instantiate2.instantiate(cfg)


@mark.parametrize(
    "cfg",
    [
        {
            "_target_": "doctest.Example",
            "source": "pass\n",
            "want": "",
        },
        {
            "_target_": "doctest.DocTest",
            "_args_": [[], {}, "probe", "probe.py", 0, ""],
            "_convert_": "all",
        },
        {"_target_": "doctest.DocTestParser"},
        {"_target_": "pydoc.HTMLDoc"},
        {"_target_": "pydoc.TextDoc"},
        {"_target_": "trace.Trace"},
    ],
)
def test_blacklist_prefix_exceptions_are_allowed(cfg: Dict[str, Any]) -> None:
    with warns(UserWarning, match="with no\n_execution_whitelist_"):
        result = _instantiate2.instantiate(cfg)
    assert result is not None

    target = cfg["_target_"]
    assert _instantiate2.instantiate(cfg, _execution_whitelist_=target) is not None


def test_exact_blacklist_takes_precedence_over_prefix_exception(
    monkeypatch: Any,
) -> None:
    monkeypatch.setattr(
        target_policy,
        "DEFAULT_BLACKLISTED_MODULES",
        {*target_policy.DEFAULT_BLACKLISTED_MODULES, "trace.CoverageResults"},
    )
    monkeypatch.setattr(
        target_policy,
        "UNCONTROLLED_EXECUTION_TARGET_PREFIX_EXCEPTIONS",
        {
            *target_policy.UNCONTROLLED_EXECUTION_TARGET_PREFIX_EXCEPTIONS,
            "trace.CoverageResults",
        },
    )
    assert target_policy._is_blacklisted_target("trace.CoverageResults")


@mark.parametrize(
    "target",
    [
        "pdb.run",
        "pdb.runeval",
        "pdb.Pdb._getval",
        "pdb.Pdb._getval_except",
        "pdb.Pdb.default",
        "pdb.Pdb.run",
        "bdb.Bdb.run",
        "bdb.Bdb.runeval",
        "bdb.Bdb.runctx",
    ],
)
def test_debugger_families_are_blacklisted(target: str) -> None:
    # pdb/bdb evaluate/execute user strings; whole families covered by prefix.
    cfg = OmegaConf.create({"foo": {"_target_": target}})
    with raises(InstantiationException, match="blacklisted"):
        _instantiate2.instantiate(cfg)

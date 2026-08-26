# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved
import builtins
import contextlib
import copy
import os
import pickle
import re
import types
import _threading_local
from dataclasses import dataclass
from functools import partial
from textwrap import dedent
from typing import Any, Callable, Dict, List, Optional, Tuple

from omegaconf import MISSING, DictConfig, ListConfig, MissingMandatoryValue, OmegaConf
from pytest import fixture, mark, param, raises, warns

import hydra
from hydra import version
from hydra._internal.instantiate import _instantiate2
from hydra._internal.instantiate._instantiate2 import _resolve_target
from hydra.errors import Hydra14MigrationWarning, InstantiationException
from hydra.test_utils.test_utils import assert_multiline_regex_search
from hydra.types import ConvertMode, TargetConf
from tests.instantiate import (
    AClass,
    Adam,
    AdamConf,
    AnotherClass,
    ArgsClass,
    ASubclass,
    BadAdamConf,
    BClass,
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
        hydra._internal.instantiate._instantiate2.instantiate,
    ],
    ids=[
        "instantiate2",
    ],
)
def instantiate_func(request: Any) -> Any:
    return request.param


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
            {"_target_": "tests.instantiate.AClass", "b": 20, "c": 30},
            {"a": "???", "_partial_": True},
            partial(AClass, b=20, c=30),
            id="class+override+partial1+missing",
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
    obj = instantiate_func(config, **passthrough)
    assert partial_equal(obj, expected)


def test_partial_with_missing(instantiate_func: Any) -> Any:
    config = {
        "_target_": "tests.instantiate.AClass",
        "_partial_": True,
        "a": "???",
        "b": 20,
        "c": 30,
    }
    partial_obj = instantiate_func(config)
    assert partial_equal(partial_obj, partial(AClass, b=20, c=30))
    obj = partial_obj(a=10)
    assert partial_equal(obj, AClass(a=10, b=20, c=30))


def test_instantiate_with_missing(instantiate_func: Any) -> Any:
    config = {
        "_target_": "tests.instantiate.AClass",
        "a": "???",
        "b": 20,
        "c": 30,
    }
    with raises(MissingMandatoryValue, match=re.escape("Missing mandatory value: a")):
        instantiate_func(config)


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
    ret = instantiate_func(cfg)
    assert ret.kwargs["none_dict"] is None
    assert ret.kwargs["none_list"] is None
    assert ret.kwargs["dict"].field == 10
    assert ret.kwargs["dict"].none_dict is None
    assert ret.kwargs["dict"].none_list is None
    assert ret.kwargs["list"][0] == 10
    assert ret.kwargs["list"][1] is None
    assert ret.kwargs["list"][2] is None


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
    ],
)
def test_interpolation_accessing_parent(
    instantiate_func: Any,
    input_conf: Any,
    passthrough: Dict[str, Any],
    expected: Any,
) -> Any:
    cfg_copy = OmegaConf.create(input_conf)
    input_conf = OmegaConf.create(input_conf)
    obj = instantiate_func(input_conf.node, **passthrough)
    if isinstance(expected, partial):
        assert partial_equal(obj, expected)
    else:
        assert obj == expected
    assert input_conf == cfg_copy


@mark.parametrize(
    "src",
    [
        (
            {
                "_target_": "tests.instantiate.AClass",
                "b": 200,
                "c": {"x": 10, "y": "${b}"},
            }
        )
    ],
)
def test_class_instantiate_omegaconf_node(instantiate_func: Any, config: Any) -> Any:
    obj = instantiate_func(config, a=10, d=AnotherClass(99))
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
    In 1483, pickle is failing because the parent node of lst node contains
    a generator, which is not picklable.
    The solution is to resolve and retach from the parent before calling the function.
    This tests verifies the expected behavior.
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
        pickle.dumps(res.keywords["lst"])  # type: ignore
    else:
        pickle.dumps(res.kwargs["lst"])


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
    assert list(res.betas) == list(expected.betas)  # OmegaConf converts tuples to lists
    assert res.eps == expected.eps
    assert res.weight_decay == expected.weight_decay
    assert res.amsgrad == expected.amsgrad


def test_instantiate_adam_conf_with_convert(instantiate_func: Any) -> None:
    adam_params = Parameters([1, 2, 3])
    res = instantiate_func(AdamConf(lr=0.123), params=adam_params, _convert_="all")
    expected = Adam(lr=0.123, params=adam_params)
    assert res.params == expected.params
    assert res.lr == expected.lr
    assert isinstance(res.betas, list)
    assert list(res.betas) == list(expected.betas)  # OmegaConf converts tuples to lists
    assert res.eps == expected.eps
    assert res.weight_decay == expected.weight_decay
    assert res.amsgrad == expected.amsgrad


def test_targetconf_deprecated(hydra_restore_singletons: Any) -> None:
    with warns(Hydra14MigrationWarning):
        version.setbase("1.1")
    with warns(
        expected_warning=UserWarning,
        match=re.escape(
            "TargetConf is deprecated since Hydra 1.1 and will be removed in Hydra 1.2."
        ),
    ):
        TargetConf()


def test_targetconf_disabled(hydra_restore_singletons: Any) -> None:
    version.setbase("1.2")
    with raises(
        TypeError,
        match=re.escape("TargetConf is unsupported since Hydra 1.2"),
    ):
        TargetConf()


def test_instantiate_bad_adam_conf(instantiate_func: Any, recwarn: Any) -> None:
    msg = re.escape(
        dedent(
            """\
            Config has missing value for key `_target_`, cannot instantiate.
            Config type: BadAdamConf
            Check that the `_target_` key in your dataclass is properly annotated and overridden.
            A common problem is forgetting to annotate _target_ as a string : '_target_: str = ...'"""
        )
    )
    with raises(
        InstantiationException,
        match=msg,
    ):
        instantiate_func(BadAdamConf())


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
            dedent(
                rf"""
                Error in call to target '{re.escape(_target_)}':
                ExceptionTakingNoArgument\('Err message',?\)"""
            ).strip()
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
            dedent(
                rf"""
                Error in call to target '{re.escape(_target_)}':
                ExceptionTakingNoArgument\('Err message',?\)
                full_key: foo
                """
            ).strip()
        ),
    ):
        instantiate_func({"foo": {"_target_": _target_}})


def test_toplevel_list_partial_not_allowed(instantiate_func: Any) -> None:
    config = [{"_target_": "tests.instantiate.ClassA", "a": 10, "b": 20, "c": 30}]
    with raises(
        InstantiationException,
        match=re.escape(
            "The _partial_ keyword is not compatible with top-level list instantiation"
        ),
    ):
        instantiate_func(config, _partial_=True)


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
        param(
            TreeConf(
                value=1,
                left=TreeConf(value=21),
            ),
            {"right": TreeConf(value=22)},
            Tree(value=1, left=Tree(value=21), right=Tree(value=22)),
            id="recursive:direct:dataclass:passthrough",
        ),
        param(
            TreeConf(
                value=1,
                left=TreeConf(value=21),
            ),
            {
                "right": TreeConf(value=IllegalType()),
            },
            Tree(value=1, left=Tree(value=21), right=Tree(value=IllegalType())),
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
                    "a": Mapping(),
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
                transforms=[
                    partial(CenterCrop, size=10),  # type: ignore
                    Rotation(degrees=45),
                ],
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
                transforms=[
                    partial(CenterCrop),  # type: ignore
                    Rotation(degrees=45),
                ]
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
                dictionary={
                    "a": partial(Mapping, dictionary=None),  # type: ignore
                    "b": Mapping(),
                }
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
                dictionary={
                    "a": partial(Mapping),
                    "b": partial(Mapping),
                },
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
            dedent(
                """\
                Error locating target 'not_found', set env var HYDRA_FULL_ERROR=1 to see chained exception.
                full_key: foo"""
            )
        ),
    ) as exc_info:
        instantiate_func(cfg)
    err = exc_info.value
    assert hasattr(err, "__cause__")
    chained = err.__cause__
    assert isinstance(chained, ImportError)
    assert_multiline_regex_search(
        dedent(
            """\
            Error loading 'not_found':
            ModuleNotFoundError\\("No module named 'not_found'",?\\)
            Are you sure that module 'not_found' is installed\\?"""
        ),
        chained.args[0],
    )


@mark.parametrize(
    "target",
    [
        "os.kill",
        "builtins.compile",
        "builtins.__build_class__",
        "builtins.classmethod",
        "builtins.map",
        "builtins.staticmethod",
        "builtins.type.__call__",
        "builtins.type.__new__",
        "concurrent.futures.Executor.map",
        "concurrent.futures.Executor.submit",
        "concurrent.futures.ThreadPoolExecutor.map",
        "concurrent.futures.ThreadPoolExecutor.submit",
        "concurrent.futures.ProcessPoolExecutor.map",
        "concurrent.futures.ProcessPoolExecutor.submit",
        "contextlib.AsyncContextDecorator.__call__",
        "contextlib.ContextDecorator.__call__",
        "functools.cache",
        "functools.lru_cache",
        "functools.partialmethod",
        "functools.partialmethod.__get__",
        "functools.reduce",
        "functools.singledispatch",
        "functools.singledispatchmethod",
        "functools.singledispatchmethod.__get__",
        "functools.update_wrapper",
        "functools.wraps",
        "types.ClassMethodDescriptorType.__get__",
        "types.FunctionType.__get__",
        "types.MethodDescriptorType.__get__",
        "types.FunctionType",
        "types.MethodType",
        "types.WrapperDescriptorType.__get__",
        "types.new_class",
        "unittest.mock.AsyncMock",
        "unittest.mock.MagicMock",
        "unittest.mock.Mock",
        "unittest.mock.PropertyMock",
        "unittest.mock.create_autospec",
        "unittest.mock.mock_open",
        "unittest.mock.patch",
        "unittest.mock.patch.dict",
        "unittest.mock.patch.multiple",
        "unittest.mock.patch.object",
        "itertools.accumulate",
        "itertools.groupby",
        "itertools.starmap",
        "multiprocessing.pool.ThreadPool.apply",
        "multiprocessing.pool.ThreadPool.apply_async",
        "multiprocessing.pool.ThreadPool.starmap",
        "ctypes.CDLL",
        "ctypes.WinDLL",
        "ctypes.windll.LoadLibrary",
        "dataclasses.make_dataclass",
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
def test_blocklisted_target_fails(instantiate_func: Any, target: str) -> None:
    cfg = OmegaConf.create({"foo": {"_target_": target}})
    with raises(
        InstantiationException,
        match="blocklisted",
    ) as exc_info:
        instantiate_func(cfg)
    err = exc_info.value
    assert "full_key: foo" in str(err)
    assert hasattr(err, "__cause__")
    chained = err.__cause__
    assert chained is None


def test_allowlist_override_works_for_general_target(monkeypatch: Any) -> None:
    monkeypatch.setenv("HYDRA_INSTANTIATE_ALLOWLIST_OVERRIDE", "os.kill")
    assert _resolve_target("os.kill", "") is os.kill


def test_allowlist_override_cannot_authorize_uncontrolled_prefix(
    monkeypatch: Any,
) -> None:
    monkeypatch.setenv("HYDRA_INSTANTIATE_ALLOWLIST_OVERRIDE", "os.execl")
    with raises(InstantiationException, match="cannot be authorized"):
        _resolve_target("os.execl", "")


def test_allowlist_works_for_canonical_os_alias(monkeypatch: Any) -> None:
    monkeypatch.setenv("HYDRA_INSTANTIATE_ALLOWLIST_OVERRIDE", "os.kill")
    assert _resolve_target("posix.kill", "") is os.kill


@mark.parametrize("target", sorted(_instantiate2.UNCONTROLLED_EXECUTION_TARGETS))
def test_uncontrolled_execution_target_ignores_allowlist_override(
    target: str, monkeypatch: Any
) -> None:
    monkeypatch.setenv("HYDRA_INSTANTIATE_ALLOWLIST_OVERRIDE", target)
    with raises(InstantiationException, match="cannot be authorized"):
        _resolve_target(target, "")


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
def test_uncontrolled_execution_family_ignores_allowlist_override(
    target: str, monkeypatch: Any
) -> None:
    monkeypatch.setenv("HYDRA_INSTANTIATE_ALLOWLIST_OVERRIDE", target)
    with raises(InstantiationException, match="cannot be authorized"):
        _resolve_target(target, "")


@mark.parametrize(
    "target",
    [
        "doctest.DocTest",
        "doctest.DocTestParser",
        "doctest.Example",
        "pydoc.HTMLDoc",
        "pydoc.TextDoc",
        "trace.Trace",
    ],
)
def test_uncontrolled_execution_prefix_exceptions_are_not_blocklisted(
    target: str,
) -> None:
    assert not _instantiate2._is_blocklisted_target(target)


def test_blocklist_policy_sections_are_disjoint() -> None:
    assert _instantiate2.DEFAULT_BLOCKLISTED_MODULES.isdisjoint(
        _instantiate2.UNCONTROLLED_EXECUTION_TARGETS
    )


def test_getcwd_is_not_blocklisted() -> None:
    assert _instantiate2.instantiate({"_target_": "os.getcwd"}) == os.getcwd()


def test_ineffective_sys_modules_entries_are_not_in_policy() -> None:
    for target in (
        "sys.modules.ipdb",
        "sys.modules.joblib",
        "sys.modules.resource",
        "sys.modules.psutil",
        "sys.modules.tkinter",
    ):
        assert target not in _instantiate2.DEFAULT_BLOCKLISTED_MODULES
        assert target not in _instantiate2.UNCONTROLLED_EXECUTION_TARGETS


@mark.parametrize(
    "alias",
    [
        "logging.os.system",
        "logging.os.execl",
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
    with raises(InstantiationException, match="blocklisted"):
        _resolve_target(alias, "")


@mark.parametrize(
    "target",
    [
        os.system.__call__,
        eval.__call__,
        classmethod(getattr).__get__,
        types.FunctionType,
        types.MethodType,
    ],
)
def test_blocklist_blocks_callable_object_aliases(target: Callable[..., Any]) -> None:
    with raises(InstantiationException, match="blocklisted"):
        _resolve_target(target, "")


@mark.parametrize(
    ("target", "canonical_target"),
    [
        ("operator.attrgetter.__new__", "operator.attrgetter"),
        ("operator.itemgetter.__new__", "operator.itemgetter"),
        ("operator.methodcaller.__new__", "operator.methodcaller"),
        ("operator.attrgetter.__call__", "operator.attrgetter"),
        ("operator.itemgetter.__call__", "operator.itemgetter"),
        ("operator.methodcaller.__call__", "operator.methodcaller"),
        ("builtins.map.__new__", "builtins.map"),
        ("builtins.map.__call__", "builtins.map"),
        ("builtins.map.__new__.__call__", "builtins.map"),
        ("builtins.classmethod.__new__", "builtins.classmethod"),
        ("builtins.classmethod.__new__.__call__", "builtins.classmethod"),
        ("builtins.classmethod.__get__", "builtins.classmethod"),
        ("builtins.classmethod.__get__.__call__", "builtins.classmethod"),
        *(
            [("builtins.classmethod.__call__", "builtins.classmethod")]
            if hasattr(classmethod, "__call__")
            else []
        ),
        ("builtins.staticmethod.__new__", "builtins.staticmethod"),
        ("builtins.staticmethod.__new__.__call__", "builtins.staticmethod"),
        *(
            [("builtins.staticmethod.__call__", "builtins.staticmethod")]
            if hasattr(staticmethod, "__call__")
            else []
        ),
        ("builtins.type.__new__.__call__", "builtins.type.__new__"),
        ("builtins.type.__call__.__call__", "builtins.type.__call__"),
        (
            "concurrent.futures.Executor.map",
            "concurrent.futures._base.Executor.map",
        ),
        (
            "concurrent.futures.Executor.submit",
            "concurrent.futures._base.Executor.submit",
        ),
        (
            "concurrent.futures.ThreadPoolExecutor.map",
            "concurrent.futures._base.Executor.map",
        ),
        (
            "concurrent.futures.ThreadPoolExecutor.submit",
            "concurrent.futures.thread.ThreadPoolExecutor.submit",
        ),
        (
            "concurrent.futures.ProcessPoolExecutor.map",
            "concurrent.futures.process.ProcessPoolExecutor.map",
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
            "contextlib._GeneratorContextManager.__call__.__call__",
            "contextlib.ContextDecorator.__call__",
        ),
        (
            "contextlib._AsyncGeneratorContextManager.__call__",
            "contextlib.AsyncContextDecorator.__call__",
        ),
        (
            "contextlib._AsyncGeneratorContextManager.__call__.__call__",
            "contextlib.AsyncContextDecorator.__call__",
        ),
        ("functools.reduce.__call__", "_functools.reduce"),
        ("functools.partialmethod.__call__", "functools.partialmethod"),
        (
            "functools.partialmethod.__get__.__call__",
            "functools.partialmethod.__get__",
        ),
        (
            "functools.singledispatchmethod.__call__",
            "functools.singledispatchmethod",
        ),
        (
            "functools.singledispatchmethod.__get__.__call__",
            "functools.singledispatchmethod.__get__",
        ),
        ("types.MethodType.__new__", "types.MethodType"),
        ("types.MethodType.__call__", "types.MethodType"),
        ("types.MethodType.__new__.__call__", "types.MethodType"),
        ("types.FunctionType.__new__", "types.FunctionType"),
        ("types.FunctionType.__call__", "types.FunctionType"),
        ("types.FunctionType.__new__.__call__", "types.FunctionType"),
        ("types.LambdaType", "types.FunctionType"),
        (
            "builtins.dict.get.__get__",
            "types.MethodDescriptorType.__get__",
        ),
        (
            "builtins.dict.get.__get__.__call__",
            "types.MethodDescriptorType.__get__",
        ),
        (
            "builtins.object.__getattribute__.__get__",
            "types.WrapperDescriptorType.__get__",
        ),
        (
            "multiprocessing.pool.ThreadPool._map_async",
            "multiprocessing.pool.Pool._map_async",
        ),
        (
            "multiprocessing.pool.ThreadPool.apply",
            "multiprocessing.pool.Pool.apply",
        ),
        (
            "multiprocessing.pool.ThreadPool.apply_async",
            "multiprocessing.pool.Pool.apply_async",
        ),
        (
            "multiprocessing.pool.ThreadPool.imap",
            "multiprocessing.pool.Pool.imap",
        ),
        (
            "multiprocessing.pool.ThreadPool.imap_unordered",
            "multiprocessing.pool.Pool.imap_unordered",
        ),
        (
            "multiprocessing.pool.ThreadPool.map",
            "multiprocessing.pool.Pool.map",
        ),
        (
            "multiprocessing.pool.ThreadPool.map_async",
            "multiprocessing.pool.Pool.map_async",
        ),
        (
            "multiprocessing.pool.ThreadPool.starmap",
            "multiprocessing.pool.Pool.starmap",
        ),
        (
            "multiprocessing.pool.ThreadPool.starmap_async",
            "multiprocessing.pool.Pool.starmap_async",
        ),
        ("itertools.accumulate.__new__", "itertools.accumulate"),
        ("itertools.accumulate.__call__", "itertools.accumulate"),
        ("itertools.accumulate.__new__.__call__", "itertools.accumulate"),
        ("itertools.groupby.__new__", "itertools.groupby"),
        ("itertools.groupby.__call__", "itertools.groupby"),
        ("itertools.groupby.__new__.__call__", "itertools.groupby"),
        ("itertools.starmap.__new__", "itertools.starmap"),
        ("itertools.starmap.__call__", "itertools.starmap"),
        ("itertools.starmap.__new__.__call__", "itertools.starmap"),
    ],
)
def test_resolved_target_aliases_are_blocklisted(
    target: str, canonical_target: str
) -> None:
    with raises(
        InstantiationException,
        match=rf"Target '{canonical_target}'.*resolved from.*blocklisted",
    ):
        _resolve_target(target, "")


@mark.parametrize(
    "target",
    [
        "builtins.filter",
        "builtins.iter",
        "itertools.dropwhile",
        "itertools.filterfalse",
        "itertools.takewhile",
    ],
)
def test_non_result_lazy_callback_targets_are_not_blocklisted(target: str) -> None:
    assert not _instantiate2._is_blocklisted_target(target)


def test_discovery_target_applies_blocklist_to_selected_path() -> None:
    cfg = {"_target_": "hydra.utils.get_method", "path": "builtins.eval"}
    with raises(InstantiationException, match="Target 'builtins.eval'.*blocklisted"):
        _instantiate2.instantiate(cfg)


def test_partial_discovery_target_applies_resolved_blocklist_when_invoked() -> None:
    cfg = {
        "_target_": "hydra.utils.get_method",
        "_partial_": True,
        "path": "logging.os.system",
    }
    deferred = _instantiate2.instantiate(cfg)

    with raises(InstantiationException, match=r"Target 'os\.system'.*blocklisted"):
        deferred()


def test_partial_discovery_target_defers_resolution_and_allows_override() -> None:
    cfg = {
        "_target_": "hydra.utils.get_object",
        "_partial_": True,
        "path": "does.not.exist",
    }
    deferred = _instantiate2.instantiate(cfg)

    assert deferred(path="builtins.pow") is pow
    with raises(
        InstantiationException,
        match=r"Target 'builtins\.eval'.*blocklisted",
    ):
        deferred(path="builtins.eval")


def test_partial_discovery_target_reauthorizes_runtime_override(
    monkeypatch: Any,
) -> None:
    monkeypatch.setenv("HYDRA_INSTANTIATE_ALLOWLIST_OVERRIDE", "os.remove")
    deferred = _instantiate2.instantiate(
        {
            "_target_": "hydra.utils.get_object",
            "_partial_": True,
            "path": "os.remove",
        }
    )

    assert deferred() is os.remove
    with raises(InstantiationException, match=r"Target 'os\.kill'.*blocklisted"):
        deferred(path="os.kill")


def test_getattr_allows_non_callable_result() -> None:
    cfg = {
        "_target_": "builtins.getattr",
        "_args_": [
            {"_target_": "types.SimpleNamespace", "value": 10},
            "value",
        ],
    }
    assert _instantiate2.instantiate(cfg) == 10


def test_getattr_callable_result_applies_blocklist() -> None:
    cfg = {
        "_target_": "builtins.getattr",
        "_args_": [
            {"_target_": "timeit.Timer", "stmt": "40 + 2"},
            "timeit",
        ],
    }
    with raises(
        InstantiationException,
        match=r"Target 'timeit\.Timer\.timeit'.*blocklisted",
    ):
        _instantiate2.instantiate(cfg)


def test_callable_descriptor_binding_cannot_return_unmediated_selector() -> None:
    cfg = {
        "_target_": "builtins.dict.get.__get__",
        "_args_": [{"eval": eval}],
        "_convert_": "all",
    }

    with raises(
        InstantiationException,
        match=r"Target 'types\.MethodDescriptorType\.__get__'.*blocklisted",
    ):
        _instantiate2.instantiate(cfg)


def test_classmethod_wrapper_cannot_defer_callable_selection() -> None:
    cfg = {
        "_target_": "builtins.classmethod",
        "_args_": [getattr],
    }

    with raises(
        InstantiationException,
        match=r"Target 'builtins\.classmethod'.*blocklisted",
    ):
        _instantiate2.instantiate(cfg)


def test_context_decorator_cannot_hide_deferred_callable_selection() -> None:
    context_manager = _threading_local._patch(_threading_local.local())
    wrapper = contextlib.ContextDecorator.__call__(context_manager, dict.get)
    assert wrapper(vars(builtins), "eval") is eval

    cfg = {
        "_target_": "contextlib.ContextDecorator.__call__",
        "_args_": [context_manager, dict.get],
        "_convert_": "all",
    }
    with raises(
        InstantiationException,
        match=r"Target 'contextlib\.ContextDecorator\.__call__'.*blocklisted",
    ):
        _instantiate2.instantiate(cfg)


def test_type_introspection_is_allowed() -> None:
    assert _instantiate2.instantiate(
        {"_target_": "builtins.type", "_args_": [10]}
    ) is type(10)


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
        _instantiate2.instantiate(cfg)


def test_partial_type_reauthorizes_runtime_arguments() -> None:
    deferred = _instantiate2.instantiate(
        {"_target_": "builtins.type", "_partial_": True}
    )

    assert deferred(10) is int
    with raises(
        InstantiationException,
        match="cannot be used for dynamic class construction",
    ):
        deferred("Selector", (), {"__call__": dict.get})

    deferred_metaclass = _instantiate2.instantiate(
        {"_target_": "abc.ABCMeta", "_partial_": True}
    )
    with raises(
        InstantiationException,
        match="cannot be used for dynamic class construction",
    ):
        deferred_metaclass("Selector", (), {"__call__": dict.get})


def test_metaclass_constructor_method_is_not_allowed() -> None:
    with raises(
        InstantiationException,
        match="cannot be used for dynamic class construction",
    ):
        _instantiate2.instantiate({"_target_": "abc.ABCMeta.__new__"})

    with raises(
        InstantiationException,
        match="cannot be used for dynamic class construction",
    ):
        _instantiate2.instantiate(
            {"_target_": "abc.ABCMeta.__new__", "_partial_": True}
        )


def test_callable_mock_wrapper_is_not_allowed() -> None:
    cfg = {
        "_target_": "unittest.mock.Mock",
        "side_effect": dict.get,
    }

    with raises(
        InstantiationException,
        match=r"Target 'unittest\.mock\.Mock'.*blocklisted",
    ):
        _instantiate2.instantiate(cfg)


@mark.parametrize(
    "target",
    ["unittest.mock.NonCallableMock", "unittest.mock.NonCallableMagicMock"],
)
def test_non_callable_mock_is_allowed(target: str) -> None:
    mock = _instantiate2.instantiate({"_target_": target, "name": "inert"})
    assert not callable(mock)
    assert mock._extract_mock_name() == "inert"


def test_non_callable_mock_allows_one_positional_spec() -> None:
    mock = _instantiate2.instantiate(
        {
            "_target_": "unittest.mock.NonCallableMock",
            "_args_": [[]],
        }
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
    cfg = {"_target_": "unittest.mock.NonCallableMock", **unsafe_kwargs}
    with raises(
        InstantiationException,
        match="cannot configure callable attributes",
    ):
        _instantiate2.instantiate(cfg)


def test_partial_non_callable_mock_reauthorizes_runtime_configuration() -> None:
    deferred = _instantiate2.instantiate(
        {"_target_": "unittest.mock.NonCallableMock", "_partial_": True}
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


def test_non_callable_mock_rejects_positional_wraps() -> None:
    cfg = {
        "_target_": "unittest.mock.NonCallableMock",
        "_args_": [None, {}],
    }
    with raises(
        InstantiationException,
        match="cannot configure callable attributes",
    ):
        _instantiate2.instantiate(cfg)


def test_callable_result_from_any_target_applies_blocklist() -> None:
    cfg = {
        "_target_": "builtins.dict.get",
        "_args_": [{"eval": eval}, "eval"],
        "_convert_": "all",
    }
    with raises(
        InstantiationException,
        match=r"Target 'builtins\.eval'.*blocklisted",
    ):
        _instantiate2.instantiate(cfg)


def test_callable_result_from_any_target_allows_safe_callable() -> None:
    cfg = {
        "_target_": "builtins.dict.get",
        "_args_": [{"pow": pow}, "pow"],
        "_convert_": "all",
    }
    assert _instantiate2.instantiate(cfg) is pow


def test_callable_result_producer_allowlist_does_not_authorize_result(
    monkeypatch: Any,
) -> None:
    monkeypatch.setenv(
        "HYDRA_INSTANTIATE_ALLOWLIST_OVERRIDE",
        "builtins.dict.get",
    )
    cfg = {
        "_target_": "builtins.dict.get",
        "_args_": [{"remove": os.remove}, "remove"],
        "_convert_": "all",
    }

    with raises(InstantiationException, match=r"Target 'os\.remove'.*blocklisted"):
        _instantiate2.instantiate(cfg)


def test_discovery_result_accepts_allowlisted_alias(monkeypatch: Any) -> None:
    monkeypatch.setenv(
        "HYDRA_INSTANTIATE_ALLOWLIST_OVERRIDE",
        "logging.os.kill",
    )
    cfg = {
        "_target_": "hydra.utils.get_method",
        "path": "logging.os.kill",
    }

    assert _instantiate2.instantiate(cfg) is os.kill


def test_hydra_partial_authorizes_callable_result_when_invoked() -> None:
    cfg = {
        "_target_": "builtins.getattr",
        "_partial_": True,
        "_args_": [
            {"_target_": "hydra.utils.get_object", "path": "builtins"},
        ],
    }
    deferred = _instantiate2.instantiate(cfg)

    assert isinstance(deferred, partial)
    assert deferred.func is getattr
    assert deferred("pow") is pow
    with raises(
        InstantiationException,
        match=r"Target 'builtins\.eval'.*blocklisted",
    ):
        deferred("eval")


def test_hydra_partial_with_runtime_authorization_is_pickleable() -> None:
    deferred = _instantiate2.instantiate(
        {"_target_": "builtins.pow", "_partial_": True, "exp": 2}
    )
    restored = pickle.loads(pickle.dumps(deferred))

    assert isinstance(restored, partial)
    assert restored.func is pow
    assert restored(3) == 9


def test_direct_functools_partial_warns() -> None:
    cfg = {"_target_": "functools.partial", "_args_": [pow], "exp": 2}
    with warns(UserWarning, match=r"Using '_target_: functools\.partial'"):
        factory = _instantiate2.instantiate(cfg)
    assert factory(3) == 9


def test_direct_functools_partial_applies_blocklist_to_callable() -> None:
    cfg = {"_target_": "functools.partial", "_args_": [eval]}
    with warns(UserWarning, match=r"Using '_target_: functools\.partial'"):
        with raises(
            InstantiationException, match=r"Target 'builtins\.eval'.*blocklisted"
        ):
            _instantiate2.instantiate(cfg)


def test_direct_functools_partial_authorizes_callable_result_when_invoked() -> None:
    cfg = {
        "_target_": "functools.partial",
        "_args_": [
            getattr,
            {"_target_": "hydra.utils.get_object", "path": "builtins"},
        ],
    }
    with warns(UserWarning, match=r"Using '_target_: functools\.partial'"):
        factory = _instantiate2.instantiate(cfg)

    assert isinstance(factory, partial)
    assert factory("pow") is pow
    with raises(
        InstantiationException,
        match=r"Target 'builtins\.eval'.*blocklisted",
    ):
        factory("eval")


def test_hydra_partial_mediates_partial_result_when_invoked() -> None:
    cfg = {
        "_target_": "functools.partial",
        "_partial_": True,
        "_args_": [
            getattr,
            {"_target_": "hydra.utils.get_object", "path": "builtins"},
        ],
    }
    with warns(UserWarning, match=r"Using '_target_: functools\.partial'"):
        outer = _instantiate2.instantiate(cfg)

    inner = outer()
    assert isinstance(inner, partial)
    assert inner("pow") is pow
    with raises(
        InstantiationException,
        match=r"Target 'builtins\.eval'.*blocklisted",
    ):
        inner("eval")


def test_mediated_partial_result_preserves_attributes() -> None:
    factory = _instantiate2.instantiate(
        {"_target_": "tests.instantiate.make_attributed_partial"}
    )

    assert factory.__name__ == "square"
    assert factory.metadata == {"source": "application"}
    assert factory(3) == 9


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
                # a is a DictConfig because of top level DictConfig
                OmegaConf.create(
                    {
                        "a": SimpleDataClass(
                            a=OmegaConf.create({"foo": 99}), b=OmegaConf.create([1, 99])
                        ),
                        "b": None,
                    }
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

# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved
from textwrap import dedent
from typing import Any

from pytest import mark, param, raises

from hydra.errors import InstantiationException
from hydra.utils import UNSAFE_DISABLE_EXECUTION_CHECKS, instantiate
from tests.instantiate import ArgsClass


def unsafe_instantiate(config: Any, *args: Any, **kwargs: Any) -> Any:
    kwargs.setdefault("_execution_whitelist_", UNSAFE_DISABLE_EXECUTION_CHECKS)
    return instantiate(config, *args, **kwargs)


#######################
# non-recursive tests #
#######################


@mark.parametrize(
    ("cfg", "expected"),
    [
        param(
            {"_target_": "tests.instantiate.ArgsClass"},
            ArgsClass(),
            id="config:no_params",
        ),
        param(
            {"_target_": "tests.instantiate.ArgsClass", "_args_": [1]},
            ArgsClass(1),
            id="config:args_only",
        ),
        param(
            {
                "_target_": "tests.instantiate.ArgsClass",
                "_args_": [1],
                "foo": 10,
            },
            ArgsClass(1, foo=10),
            id="config:args+kwargs",
        ),
        param(
            {
                "_target_": "tests.instantiate.ArgsClass",
                "foo": 10,
            },
            ArgsClass(foo=10),
            id="config:kwargs_only",
        ),
    ],
)
def test_instantiate_args_kwargs(cfg: Any, expected: Any) -> None:
    assert unsafe_instantiate(cfg) == expected


@mark.parametrize(
    "cfg, msg",
    [
        param(
            {"_target_": "tests.instantiate.ArgsClass", "_args_": {"foo": "bar"}},
            dedent(
                """\
                Error in collecting args and kwargs for 'tests\\.instantiate\\.ArgsClass':
                InstantiationException\\("Unsupported _args_ type: 'DictConfig'\\. value: '{'foo': 'bar'}'",?\\)"""
            ),
            id="unsupported-args-type",
        ),
        param(
            {
                "foo": {
                    "_target_": "tests.instantiate.ArgsClass",
                    "_args_": {"foo": "bar"},
                }
            },
            dedent("""\
                Error in collecting args and kwargs for 'tests\\.instantiate\\.ArgsClass':
                InstantiationException\\("Unsupported _args_ type: 'DictConfig'\\. value: '{'foo': 'bar'}'",?\\)
                full_key: foo"""),
            id="unsupported-args-type-nested",
        ),
    ],
)
def test_instantiate_unsupported_args_type(cfg: Any, msg: str) -> None:
    with raises(
        InstantiationException,
        match=msg,
    ):
        unsafe_instantiate(cfg)


@mark.parametrize(
    ("cfg", "expected"),
    [
        param(
            {"_target_": "tests.instantiate.ArgsClass", "_args_": ["${.1}", 2]},
            ArgsClass(2, 2),
            id="config:args_only",
        ),
        param(
            {
                "_target_": "tests.instantiate.ArgsClass",
                "_args_": [1],
                "foo": "${._args_}",
            },
            ArgsClass(1, foo=[1]),
            id="config:args+kwargs",
        ),
        param(
            {
                "_target_": "tests.instantiate.ArgsClass",
                "foo": "${._target_}",
            },
            ArgsClass(foo="tests.instantiate.ArgsClass"),
            id="config:kwargs_only)",
        ),
    ],
)
def test_instantiate_args_kwargs_with_interpolation(cfg: Any, expected: Any) -> None:
    assert unsafe_instantiate(cfg) == expected


@mark.parametrize(
    ("cfg", "args_override", "kwargs_override", "expected"),
    [
        param(
            {"_target_": "tests.instantiate.ArgsClass", "_args_": [1]},
            [2],
            {},
            ArgsClass(2),
            id="direct_args",
        ),
        param(
            {
                "_target_": "tests.instantiate.ArgsClass",
                "_args_": [1],
                "derived": "${._args_.0}",
            },
            [2],
            {},
            ArgsClass(2, derived=2),
            id="direct_args+interpolation",
        ),
        param(
            {"_target_": "tests.instantiate.ArgsClass", "_args_": [1]},
            [],
            {"_args_": [2]},
            ArgsClass(2),
            id="indirect_args",
        ),
        param(
            {"_target_": "tests.instantiate.ArgsClass", "_args_": [1]},
            [],
            {"foo": 10},
            ArgsClass(1, foo=10),
            id="kwargs",
        ),
        param(
            {"_target_": "tests.instantiate.ArgsClass", "_args_": [1]},
            [],
            {"foo": 10, "_args_": [2]},
            ArgsClass(2, foo=10),
            id="kwargs+indirect_args",
        ),
    ],
)
def test_instantiate_args_kwargs_with_override(
    cfg: Any, args_override: Any, expected: Any, kwargs_override: Any
) -> None:
    assert unsafe_instantiate(cfg, *args_override, **kwargs_override) == expected


###################
# recursive tests #
###################
@mark.parametrize(
    ("cfg", "expected"),
    [
        param(
            {
                "_target_": "tests.instantiate.ArgsClass",
                "child": {"_target_": "tests.instantiate.ArgsClass"},
            },
            ArgsClass(child=ArgsClass()),
            id="config:no_params",
        ),
        param(
            {
                "_target_": "tests.instantiate.ArgsClass",
                "_args_": [1],
                "child": {
                    "_target_": "tests.instantiate.ArgsClass",
                    "_args_": [2],
                },
            },
            ArgsClass(1, child=ArgsClass(2)),
            id="config:args_only",
        ),
        param(
            {
                "_target_": "tests.instantiate.ArgsClass",
                "_args_": [1],
                "foo": 10,
                "child": {
                    "_target_": "tests.instantiate.ArgsClass",
                    "_args_": [2],
                },
            },
            ArgsClass(1, foo=10, child=ArgsClass(2)),
            id="config:args+kwargs",
        ),
        param(
            {
                "_target_": "tests.instantiate.ArgsClass",
                "child": {
                    "_target_": "tests.instantiate.ArgsClass",
                    "_args_": [2],
                },
                "foo": 10,
            },
            ArgsClass(foo=10, child=ArgsClass(2)),
            id="config:kwargs_only",
        ),
    ],
)
def test_recursive_instantiate_args_kwargs(cfg: Any, expected: Any) -> None:
    assert unsafe_instantiate(cfg) == expected


@mark.parametrize(
    ("cfg", "args_override", "kwargs_override", "expected"),
    [
        param(
            {
                "_target_": "tests.instantiate.ArgsClass",
                "child": {"_target_": "tests.instantiate.ArgsClass"},
            },
            [1],
            {},
            ArgsClass(1, child=ArgsClass()),
            id="direct_args_not_in_nested",
        ),
        param(
            {
                "_target_": "tests.instantiate.ArgsClass",
                "_args_": [1],
                "child": {
                    "_target_": "tests.instantiate.ArgsClass",
                    "_args_": [2],
                },
            },
            [],
            {"_args_": [3], "child": {"_args_": [4]}},
            ArgsClass(3, child=ArgsClass(4)),
            id="indirect_args",
        ),
        param(
            {
                "_target_": "tests.instantiate.ArgsClass",
                "_args_": [1],
                "child": {
                    "_target_": "tests.instantiate.ArgsClass",
                    "_args_": [2],
                },
            },
            [],
            {"foo": 10},
            ArgsClass(1, foo=10, child=ArgsClass(2)),
            id="kwargs",
        ),
        param(
            {
                "_target_": "tests.instantiate.ArgsClass",
                "_args_": [1],
                "child": {
                    "_target_": "tests.instantiate.ArgsClass",
                    "_args_": [2],
                },
            },
            [],
            {"foo": 10, "_args_": [3], "child": {"_args_": [4]}},
            ArgsClass(3, foo=10, child=ArgsClass(4)),
            id="kwargs+indirect_args",
        ),
    ],
)
def test_recursive_instantiate_args_kwargs_with_override(
    cfg: Any, args_override: Any, expected: Any, kwargs_override: Any
) -> None:
    assert unsafe_instantiate(cfg, *args_override, **kwargs_override) == expected

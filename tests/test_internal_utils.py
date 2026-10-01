# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved
from typing import Any, Callable

from omegaconf import DictConfig, OmegaConf
from pytest import mark, param, raises

from hydra._internal import utils
from hydra._internal.utils import get_args
from tests import data


@mark.parametrize(
    "matrix,expected",
    [
        ([["a"]], [1]),
        ([["a", "bb"]], [1, 2]),
        ([["a", "bb"], ["aa", "b"]], [2, 2]),
        ([["a"], ["aa", "b"]], [2, 1]),
        ([["a", "aa"], ["bb"]], [2, 2]),
        ([["a"]], [1]),
        ([["a"]], [1]),
        ([["a"]], [1]),
    ],
)
def test_get_column_widths(matrix: Any, expected: Any) -> None:
    assert utils.get_column_widths(matrix) == expected


@mark.parametrize(
    "config, expected",
    [
        param(OmegaConf.create({"_target_": "foo"}), "foo", id="ObjectConf:target"),
    ],
)
def test_get_class_name(config: DictConfig, expected: Any) -> None:
    assert utils._get_cls_name(config) == expected


@mark.parametrize(
    "task_function, expected_file, expected_module",
    [
        param(data.foo, None, "tests.data", id="function"),
        param(data.foo_main_module, data.__file__, None, id="function-main-module"),
        param(data.Bar, None, "tests.data", id="class"),
        param(data.bar_instance, None, "tests.data", id="class_inst"),
        param(data.bar_instance_main_module, None, None, id="class_inst-main-module"),
    ],
)
def test_detect_calling_file_or_module_from_task_function(
    task_function: Callable[..., None],
    expected_file: str | None,
    expected_module: str | None,
) -> None:
    file, module = utils.detect_calling_file_or_module_from_task_function(task_function)
    assert file == expected_file
    assert module == expected_module


@mark.parametrize(
    "args, expected_overrides, expected_multirun",
    [
        param(
            ["--multirun", "task=1", "db=mysql"],
            ["task=1", "db=mysql"],
            True,
            id="multirun-first",
        ),
        param(
            ["task=1", "db=mysql", "--multirun"],
            ["task=1", "db=mysql"],
            True,
            id="multirun-last",
        ),
        param(
            ["task=1", "--multirun", "db=mysql"],
            ["task=1", "db=mysql"],
            True,
            id="multirun-between-overrides",
        ),
        param(
            ["task=1", "-m", "db=mysql"],
            ["task=1", "db=mysql"],
            True,
            id="short-flag-between-overrides",
        ),
        param(
            ["task=1", "db=mysql"],
            ["task=1", "db=mysql"],
            False,
            id="no-multirun",
        ),
    ],
)
def test_get_args_override_ordering(
    args: Any, expected_overrides: Any, expected_multirun: bool
) -> None:
    parsed = get_args(args)
    assert parsed.overrides == expected_overrides
    assert parsed.multirun == expected_multirun


def test_get_args_rejects_unknown_option() -> None:
    with raises(SystemExit):
        get_args(["task=1", "--bad-flag", "db=mysql"])

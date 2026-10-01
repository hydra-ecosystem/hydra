# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved
import sys
import warnings
from pathlib import Path
from typing import Any

import nevergrad as ng
from hydra.core.override_parser.overrides_parser import OverridesParser
from hydra.core.plugins import Plugins
from hydra.plugins.sweeper import Sweeper
from hydra.test_utils.test_utils import (
    TSweepRunner,
    chdir_plugin_root,
    run_process,
    run_python_script,
)
from omegaconf import DictConfig, OmegaConf
from pytest import mark, raises, warns

from hydra_plugins.hydra_nevergrad_sweeper import _impl
from hydra_plugins.hydra_nevergrad_sweeper._impl import NevergradSweeperImpl
from hydra_plugins.hydra_nevergrad_sweeper.config import OptimConf
from hydra_plugins.hydra_nevergrad_sweeper.nevergrad_sweeper import NevergradSweeper

chdir_plugin_root()


def test_discovery() -> None:
    assert NevergradSweeper.__name__ in [
        x.__name__ for x in Plugins.instance().discover(Sweeper)
    ]


def assert_ng_param_equals(expected: Any, actual: Any) -> None:
    assert type(expected) is type(actual)
    if isinstance(actual, ng.p.Choice) or isinstance(actual, ng.p.TransitionChoice):
        assert sorted(expected.choices.value) == sorted(actual.choices.value)
    elif isinstance(actual, ng.p.Log) or isinstance(actual, ng.p.Scalar):
        assert expected.bounds == actual.bounds
        assert expected.integer == actual.integer
    elif isinstance(actual, str):
        assert expected == actual
    else:
        assert False, f"Unexpected type: {type(actual)}"


def get_scalar_with_integer_bounds(lower: int, upper: int, type: Any) -> ng.p.Scalar:
    scalar = type(lower=lower, upper=upper)
    scalar.set_integer_casting()
    assert isinstance(scalar, ng.p.Scalar)
    return scalar


@mark.parametrize(
    "input, expected",
    [
        ([1, 2, 3], ng.p.Choice([1, 2, 3])),
        (["1", "2", "3"], ng.p.Choice(["1", "2", "3"])),
        ({"lower": 1, "upper": 12, "log": True}, ng.p.Log(lower=1, upper=12)),
        ({"lower": 1, "upper": 12}, ng.p.Scalar(lower=1, upper=12)),
        (
            {"lower": 1, "upper": 12, "integer": True},
            get_scalar_with_integer_bounds(1, 12, ng.p.Scalar),
        ),
        (
            {"lower": 1, "upper": 12, "log": True, "integer": True},
            get_scalar_with_integer_bounds(1, 12, ng.p.Log),
        ),
        (
            {"init": 0.02, "step": 2.0, "log": True},
            ng.p.Log(init=0.02, lower=None, upper=None, exponent=2.0),
        ),
    ],
)
def test_create_nevergrad_parameter_from_config(
    input: Any,
    expected: Any,
) -> None:
    actual = _impl.create_nevergrad_param_from_config(input)
    assert_ng_param_equals(expected, actual)


@mark.parametrize(
    "input, expected",
    [
        ("key=choice(1,2)", ng.p.Choice([1, 2])),
        ("key=choice('hello','world')", ng.p.Choice(["hello", "world"])),
        ("key=tag(ordered, choice(1,2,3))", ng.p.TransitionChoice([1, 2, 3])),
        (
            "key=tag(ordered, choice('hello','world', 'nevergrad'))",
            ng.p.TransitionChoice(["hello", "world", "nevergrad"]),
        ),
        ("key=range(1,3)", ng.p.Choice([1, 2])),
        ("key=shuffle(range(1,3))", ng.p.Choice([1, 2])),
        ("key=range(1,5)", ng.p.Choice([1, 2, 3, 4])),
        ("key=float(range(1,5))", ng.p.Choice([1.0, 2.0, 3.0, 4.0])),
        (
            "key=int(interval(1,12))",
            get_scalar_with_integer_bounds(lower=1, upper=12, type=ng.p.Scalar),
        ),
        ("key=tag(log, interval(1,12))", ng.p.Log(lower=1, upper=12)),
        (
            "key=tag(log, int(interval(1,12)))",
            get_scalar_with_integer_bounds(lower=1, upper=12, type=ng.p.Log),
        ),
        ("key=abc", "abc"),
        ("key='a&c'", "'a&c'"),
        ("key='${f:${x}}'", "'${f:${x}}'"),
        (r"key=$\{f\:$\{x\}\}", r"$\{f\:$\{x\}\}"),
        ("key=0", "0"),
        ("key=true", "True"),
        ("key=null", "null"),
        (
            "key={init: 0.02, step: 2.0, log: true}",
            ng.p.Log(init=0.02, lower=None, upper=None, exponent=2.0),
        ),
    ],
)
def test_create_nevergrad_parameter_from_override(
    input: Any,
    expected: Any,
) -> None:
    parser = OverridesParser.create()
    parsed = parser.parse_overrides([input])[0]
    param = _impl.create_nevergrad_parameter_from_override(parsed)
    assert_ng_param_equals(param, expected)


def test_launched_jobs(hydra_sweep_runner: TSweepRunner) -> None:
    budget = 8
    sweep = hydra_sweep_runner(
        calling_file=None,
        calling_module="hydra.test_utils.a_module",
        config_path="configs",
        config_name="compose.yaml",
        task_function=None,
        overrides=[
            "hydra/sweeper=nevergrad",
            "hydra/launcher=basic",
            f"hydra.sweeper.optim.budget={budget}",  # small budget to test fast
            "hydra.sweeper.optim.num_workers=3",
            "foo=1,2",
            "bar=4:8",
        ],
    )
    with warnings.catch_warnings():  # ignore specific warnings raised by sweep:
        warnings.filterwarnings(
            "ignore", category=ng.common.errors.InefficientSettingsWarning
        )
        warnings.filterwarnings(
            "ignore",
            category=UserWarning,
            message=r"Could not import matplotlib\.pyplot",
        )
        with sweep:
            assert sweep.returns is None


@mark.parametrize("with_commandline", (True, False))
def test_nevergrad_example(with_commandline: bool, tmpdir: Path) -> None:
    budget = 32 if with_commandline else 1  # make a full test only once (faster)
    cmd = [
        "example/my_app.py",
        "-m",
        "hydra.sweep.dir=" + str(tmpdir),
        "hydra.job.chdir=True",
        f"hydra.sweeper.optim.budget={budget}",  # small budget to test fast
        f"hydra.sweeper.optim.num_workers={min(8, budget)}",
        "hydra.sweeper.optim.seed=12",  # avoid random failures
    ]
    if with_commandline:
        cmd += [
            "db=mnist,cifar",
            "batch_size=4,8,12,16",
            "lr=tag(log, interval(0.001, 1.0))",
            "dropout=interval(0,1)",
        ]
    run_python_script(cmd)
    returns = OmegaConf.load(f"{tmpdir}/optimization_results.yaml")
    assert isinstance(returns, DictConfig)
    assert returns.name == "nevergrad"
    assert len(returns) == 3
    best_parameters = returns.best_evaluated_params
    assert not best_parameters.dropout.is_integer()
    if budget > 1:
        assert best_parameters.batch_size == 4  # this argument should be easy to find
    # check that all job folders are created
    last_job = max(int(fp.name) for fp in Path(tmpdir).iterdir() if fp.name.isdigit())
    assert last_job == budget - 1


@mark.parametrize("max_failure_rate", (0.5, 1.0))
def test_failure_rate(max_failure_rate: float, tmpdir: Path) -> None:
    cmd = [
        sys.executable,
        "example/my_app.py",
        "-m",
        f"hydra.sweep.dir={tmpdir}",
        "hydra.sweeper.optim.budget=2",  # small budget to test fast
        "hydra.sweeper.optim.num_workers=2",
        f"hydra.sweeper.optim.max_failure_rate={max_failure_rate}",
        "error=true",
    ]
    out, err = run_process(cmd, print_error=False, raise_exception=False)
    assert "Returning infinity for failed experiment" in out
    error_string = "RuntimeError: cfg.error is True"
    if max_failure_rate < 1.0:
        assert error_string in err
    else:
        assert error_string not in err


def create_sweeper(
    *,
    parametrization: DictConfig | None = None,
    params: DictConfig | None = None,
) -> NevergradSweeperImpl:
    return NevergradSweeperImpl(
        optim=OptimConf(),
        parametrization=parametrization,
        params=params,
    )


def test_empty_parameter_config() -> None:
    sweeper = create_sweeper()
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        parametrization, overrides = sweeper._process_parameter_config()
    assert parametrization == {}
    assert overrides == []


def test_parametrization_is_deprecated_but_supported() -> None:
    sweeper = create_sweeper(
        parametrization=OmegaConf.create({"key": [1, 2, 3]}),
    )
    with warns(
        UserWarning,
        match=(
            r"`hydra\.sweeper\.parametrization` is deprecated in Hydra 1\.4 "
            r"and will be removed in Hydra 1\.5\."
        ),
    ):
        parametrization, overrides = sweeper._process_parameter_config()
    assert_ng_param_equals(ng.p.Choice([1, 2, 3]), parametrization["key"])
    assert overrides == []


def test_params_and_parametrization_are_mutually_exclusive() -> None:
    sweeper = create_sweeper(
        parametrization=OmegaConf.create({"key": [1, 2, 3]}),
        params=OmegaConf.create({"key": "choice(1,2,3)"}),
    )
    with raises(
        ValueError,
        match=(
            r"hydra\.sweeper\.params and hydra\.sweeper\.parametrization "
            r"cannot both be configured"
        ),
    ):
        sweeper._process_parameter_config()


@mark.parametrize("value", ["'a&c'", "'a,b'"])
def test_process_parameter_config_preserves_override_quotes(value: str) -> None:
    sweeper = create_sweeper(params=OmegaConf.create({"key": value}))
    parametrization, overrides = sweeper._process_parameter_config()
    assert parametrization == {}
    assert overrides == [f"key={value}"]

    override = OverridesParser.create().parse_overrides(overrides)[0]
    assert not override.is_sweep_override()
    assert_ng_param_equals(
        _impl.create_nevergrad_parameter_from_override(override),
        value,
    )


def test_process_parameter_config_supports_scalar_dict() -> None:
    sweeper = create_sweeper(
        params=OmegaConf.create({"key": {"init": 0.02, "step": 2.0, "log": True}})
    )
    parametrization, overrides = sweeper._process_parameter_config()
    assert_ng_param_equals(
        ng.p.Log(init=0.02, lower=None, upper=None, exponent=2.0),
        parametrization["key"],
    )
    assert overrides == []

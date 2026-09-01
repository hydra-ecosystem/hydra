# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved
import os
import sys
import warnings
from pathlib import Path
from typing import Any, List

import optuna
from hydra import compose, initialize
from hydra.core.override_parser.overrides_parser import OverridesParser
from hydra.core.plugins import Plugins
from hydra.errors import InstantiationException
from hydra.plugins.sweeper import Sweeper
from hydra.test_utils.test_utils import (
    TSweepRunner,
    chdir_plugin_root,
    run_process,
    run_python_script,
)
from hydra.utils import instantiate
from omegaconf import DictConfig, OmegaConf
from optuna.distributions import (
    BaseDistribution,
    CategoricalDistribution,
    FloatDistribution,
    IntDistribution,
)
from pytest import mark, raises

from hydra_plugins.hydra_optuna_sweeper import _impl
from hydra_plugins.hydra_optuna_sweeper.config import (
    CmaEsSamplerConfig,
    GridSamplerConfig,
    MOTPESamplerConfig,
    NSGAIISamplerConfig,
    TPESamplerConfig,
)
from hydra_plugins.hydra_optuna_sweeper.optuna_sweeper import OptunaSweeper

chdir_plugin_root()

SQLALCHEMY_UTC_WARNING_FILTER = (
    r"-W ignore:datetime.datetime.utcfromtimestamp() is deprecated:"
    r"DeprecationWarning:sqlalchemy.sql.sqltypes"
)


def run_optuna_script(cmd: List[str]) -> None:
    run_python_script([SQLALCHEMY_UTC_WARNING_FILTER, *cmd])


def test_discovery() -> None:
    assert OptunaSweeper.__name__ in [
        x.__name__ for x in Plugins.instance().discover(Sweeper)
    ]


@mark.parametrize(
    "config_type, field_name, expected",
    [
        (GridSamplerConfig, "seed", None),
        (TPESamplerConfig, "group", False),
        (TPESamplerConfig, "constant_liar", False),
        (TPESamplerConfig, "constraints_func", None),
        (CmaEsSamplerConfig, "n_startup_trials", 1),
        (CmaEsSamplerConfig, "popsize", None),
        (CmaEsSamplerConfig, "with_margin", False),
        (CmaEsSamplerConfig, "lr_adapt", False),
        (CmaEsSamplerConfig, "inc_popsize", -1),
        (NSGAIISamplerConfig, "crossover", None),
    ],
)
def test_sampler_config_defaults(
    config_type: Any, field_name: str, expected: Any
) -> None:
    assert getattr(config_type(), field_name) == expected


@mark.parametrize(
    "sampler_name, field_override, expected",
    [
        ("grid", "seed=123", 123),
        ("tpe", "group=true", True),
        ("tpe", "constant_liar=true", True),
        (
            "tpe",
            "constraints_func=test_constraints",
            "test_constraints",
        ),
        ("cmaes", "n_startup_trials=7", 7),
        ("cmaes", "popsize=12", 12),
        ("cmaes", "with_margin=true", True),
        ("cmaes", "lr_adapt=true", True),
        (
            "nsgaii",
            "crossover=test_crossover",
            "test_crossover",
        ),
    ],
)
def test_sampler_normal_override(
    sampler_name: str,
    field_override: str,
    expected: Any,
) -> None:
    field_name = field_override.split("=", maxsplit=1)[0]
    with initialize(config_path="conf"):
        cfg = compose(
            config_name="test_grid",
            return_hydra_config=True,
            overrides=[
                f"hydra/sweeper/sampler={sampler_name}",
                f"hydra.sweeper.sampler.{field_override}",
            ],
        )

    assert cfg.hydra.sweeper.sampler[field_name] == expected


def test_default_cmaes_config_has_no_restart_deprecation_warning() -> None:
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        instantiate(
            OmegaConf.structured(CmaEsSamplerConfig),
            _execution_whitelist_="optuna.samplers.*",
        )

    messages = [str(warning.message).lower() for warning in caught]
    assert not any(
        "inc_popsize" in message
        or ("restart_strategy" in message and "deprecat" in message)
        for message in messages
    )


def check_distribution(expected: BaseDistribution, actual: BaseDistribution) -> None:
    if not isinstance(expected, CategoricalDistribution):
        assert expected == actual
        return

    assert isinstance(actual, CategoricalDistribution)
    # shuffle() will randomize the order of items in choices.
    assert set(expected.choices) == set(actual.choices)


@mark.parametrize(
    "input, expected",
    [
        ("key=choice(1,2)", CategoricalDistribution([1, 2])),
        ("key=choice(true, false)", CategoricalDistribution([True, False])),
        ("key=choice('hello', 'world')", CategoricalDistribution(["hello", "world"])),
        ("key=shuffle(range(1,3))", CategoricalDistribution((1, 2))),
        ("key=range(1,3)", IntDistribution(1, 3)),
        ("key=interval(1, 5)", FloatDistribution(1, 5)),
        ("key=int(interval(1, 5))", IntDistribution(1, 5)),
        ("key=tag(log, interval(1, 5))", FloatDistribution(1, 5, log=True)),
        ("key=tag(log, int(interval(1, 5)))", IntDistribution(1, 5, log=True)),
        ("key=range(0.5, 5.5, step=1)", FloatDistribution(0.5, 5.5, step=1)),
    ],
)
def test_create_optuna_distribution_from_override(input: Any, expected: Any) -> None:
    parser = OverridesParser.create()
    parsed = parser.parse_overrides([input])[0]
    actual = _impl.create_optuna_distribution_from_override(parsed)
    check_distribution(expected, actual)


@mark.parametrize(
    "input, expected",
    [
        (["key=choice(1,2)"], ({"key": CategoricalDistribution([1, 2])}, {}, [])),
        (["key=5"], ({}, {"key": "5"}, [])),
        (
            ["key1=choice(1,2)", "key2=5"],
            ({"key1": CategoricalDistribution([1, 2])}, {"key2": "5"}, []),
        ),
        (
            ["key1=choice(1,2)", "key2=5", "key3=range(1,3)"],
            (
                {
                    "key1": CategoricalDistribution([1, 2]),
                    "key3": IntDistribution(1, 3),
                },
                {"key2": "5"},
                [],
            ),
        ),
        (["~z"], ({}, {}, ["~z"])),
        (["~z=10"], ({}, {}, ["~z=10"])),
    ],
)
def test_create_params_from_overrides(input: Any, expected: Any) -> None:
    actual = _impl.create_params_from_overrides(input)
    assert actual == expected


def test_launch_jobs(hydra_sweep_runner: TSweepRunner) -> None:
    sweep = hydra_sweep_runner(
        calling_file=None,
        calling_module="hydra.test_utils.a_module",
        config_path="configs",
        config_name="compose.yaml",
        task_function=None,
        overrides=[
            "hydra/sweeper=optuna",
            "hydra/launcher=basic",
            "hydra.sweeper.n_trials=8",
            "hydra.sweeper.n_jobs=3",
        ],
    )
    with sweep:
        assert sweep.returns is None


@mark.parametrize("with_commandline", (True, False))
def test_optuna_example(with_commandline: bool, tmpdir: Path) -> None:
    storage = "sqlite:///" + os.path.join(str(tmpdir), "test.db")
    study_name = "test-optuna-example"
    cmd = [
        "example/sphere.py",
        "--multirun",
        "hydra.sweep.dir=" + str(tmpdir),
        "hydra.job.chdir=True",
        "hydra.sweeper.n_trials=20",
        "hydra.sweeper.n_jobs=1",
        f"hydra.sweeper.storage={storage}",
        f"hydra.sweeper.study_name={study_name}",
        "hydra/sweeper/sampler=tpe",
        "hydra.sweeper.sampler.seed=123",
        "~z",
    ]
    if with_commandline:
        cmd += [
            "x=choice(0, 1, 2)",
            "y=0",  # Fixed parameter
        ]
    run_optuna_script(cmd)
    returns = OmegaConf.load(f"{tmpdir}/optimization_results.yaml")
    study = optuna.load_study(storage=storage, study_name=study_name)
    best_trial = study.best_trial
    assert isinstance(returns, DictConfig)
    assert returns.name == "optuna"
    assert returns["best_params"]["x"] == best_trial.params["x"]
    if with_commandline:
        assert "y" not in returns["best_params"]
        assert "y" not in best_trial.params
    else:
        assert returns["best_params"]["y"] == best_trial.params["y"]
    assert returns["best_value"] == best_trial.value
    # Check the search performance of the TPE sampler.
    # The threshold is the 95th percentile calculated with 1000 different seed values
    # to make the test robust against the detailed implementation of the sampler.
    # See https://github.com/facebookresearch/hydra/pull/1746#discussion_r681549830.
    assert returns["best_value"] <= 2.27


@mark.parametrize("num_trials", (10, 1))
def test_example_with_grid_sampler(
    tmpdir: Path,
    num_trials: int,
) -> None:
    storage = "sqlite:///" + os.path.join(str(tmpdir), "test.db")
    study_name = "test-grid-sampler"
    cmd = [
        "example/sphere.py",
        "--multirun",
        "--config-dir=tests/conf",
        "--config-name=test_grid",
        "hydra.sweep.dir=" + str(tmpdir),
        "hydra.job.chdir=False",
        f"hydra.sweeper.n_trials={num_trials}",
        "hydra.sweeper.n_jobs=1",
        f"hydra.sweeper.storage={storage}",
        f"hydra.sweeper.study_name={study_name}",
        "hydra.sweeper.sampler.seed=123",
    ]
    run_optuna_script(cmd)
    returns = OmegaConf.load(f"{tmpdir}/optimization_results.yaml")
    assert isinstance(returns, DictConfig)
    bv, bx, by, bz = (
        returns["best_value"],
        returns["best_params"]["x"],
        returns["best_params"]["y"],
        returns["best_params"]["z"],
    )
    if num_trials >= 12:
        assert bv == 1 and abs(bx) == 1 and by == 0
    else:
        assert bx in [-1, 1] and by in [-1, 0]
    assert bz in ["foo", "bar"]


@mark.parametrize("with_commandline", (True, False))
def test_optuna_multi_objective_example(with_commandline: bool, tmpdir: Path) -> None:
    cmd = [
        "example/multi-objective.py",
        "--multirun",
        "hydra.sweep.dir=" + str(tmpdir),
        "hydra.job.chdir=True",
        "hydra.sweeper.n_trials=20",
        "hydra.sweeper.n_jobs=1",
        "hydra/sweeper/sampler=random",
        "hydra.sweeper.sampler.seed=123",
    ]
    if with_commandline:
        cmd += [
            "x=range(0, 5)",
            "y=range(0, 3)",
        ]
    run_optuna_script(cmd)
    returns = OmegaConf.load(f"{tmpdir}/optimization_results.yaml")
    assert isinstance(returns, DictConfig)
    assert returns.name == "optuna"
    if with_commandline:
        for trial_x in returns["solutions"]:
            assert trial_x["params"]["x"] % 1 == 0
            assert trial_x["params"]["y"] % 1 == 0
            # The trials must not dominate each other.
            for trial_y in returns["solutions"]:
                assert not _dominates(trial_x, trial_y)
    else:
        for trial_x in returns["solutions"]:
            assert trial_x["params"]["x"] % 1 in {0, 0.5}
            assert trial_x["params"]["y"] % 1 in {0, 0.5}
            # The trials must not dominate each other.
            for trial_y in returns["solutions"]:
                assert not _dominates(trial_x, trial_y)


def _dominates(values_x: List[float], values_y: List[float]) -> bool:
    return all(x <= y for x, y in zip(values_x, values_y)) and any(
        x < y for x, y in zip(values_x, values_y)
    )


def test_optuna_custom_search_space_example(tmpdir: Path) -> None:
    max_z_difference_from_x = 0.3
    cmd = [
        "example/custom-search-space-objective.py",
        "--multirun",
        "hydra.sweep.dir=" + str(tmpdir),
        "hydra.job.chdir=True",
        "hydra.sweeper.n_trials=20",
        "hydra.sweeper.n_jobs=1",
        "hydra/sweeper/sampler=random",
        "hydra.sweeper.sampler.seed=123",
        f"max_z_difference_from_x={max_z_difference_from_x}",
    ]
    run_optuna_script(cmd)
    returns = OmegaConf.load(f"{tmpdir}/optimization_results.yaml")
    assert isinstance(returns, DictConfig)
    assert returns.name == "optuna"
    assert (
        abs(returns["best_params"]["x"] - returns["best_params"]["z"])
        <= max_z_difference_from_x
    )
    w = returns["best_params"]["+w"]
    assert 0 <= w <= 1


@mark.parametrize("max_failure_rate", (0.5, 1.0))
def test_failure_rate(max_failure_rate: float, tmpdir: Path) -> None:
    cmd = [
        sys.executable,
        "example/sphere.py",
        "--multirun",
        "hydra.sweep.dir=" + str(tmpdir),
        "hydra.job.chdir=True",
        "hydra.sweeper.n_trials=20",
        "hydra.sweeper.n_jobs=2",
        "hydra/sweeper/sampler=random",
        "hydra.sweeper.sampler.seed=123",
        f"hydra.sweeper.max_failure_rate={max_failure_rate}",
        "error=true",
    ]
    out, err = run_process(cmd, print_error=False, raise_exception=False)
    error_string = "RuntimeError: cfg.error is True"
    if max_failure_rate < 1.0:
        assert error_string in err
    else:
        assert error_string not in err


def test_motpe_sampler_removed() -> None:
    with raises(
        InstantiationException,
        match="The 'motpe' sampler was removed in Optuna 4.0",
    ):
        instantiate(
            OmegaConf.structured(MOTPESamplerConfig),
            _execution_whitelist_="hydra_plugins.hydra_optuna_sweeper.config.raise_motpe_removed",
        )


def test_example_with_removed_motpe(
    tmpdir: Path,
) -> None:
    cmd = [
        sys.executable,
        "example/multi-objective.py",
        "--multirun",
        "--config-dir=tests/conf",
        "--config-name=test_motpe",
        "hydra.sweep.dir=" + str(tmpdir),
        "hydra.job.chdir=True",
        "hydra.sweeper.n_trials=20",
        "hydra.sweeper.n_jobs=1",
    ]

    out, err = run_process(cmd, print_error=False, raise_exception=False)
    assert "motpe" in err
    assert "sampler was removed in Optuna 4.0" in err

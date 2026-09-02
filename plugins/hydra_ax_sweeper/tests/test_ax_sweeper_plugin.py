# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved
import math
import os
from pathlib import Path
from typing import Any, List, Tuple

from hydra.core.plugins import Plugins
from hydra.plugins.sweeper import Sweeper
from hydra.test_utils.test_utils import (
    TSweepRunner,
    chdir_plugin_root,
    run_python_script,
)
from omegaconf import DictConfig, OmegaConf
from pytest import mark, raises

from hydra_plugins.hydra_ax_sweeper.ax_sweeper import AxSweeper

chdir_plugin_root()

WARNING_FILTERS = [
    # 2026-05-15: linear_operator 0.6.1 imports torch.jit.script via
    # Ax -> Botorch -> GPyTorch on Python 3.14 with Torch 2.12.
    # Remove when the current Ax stack no longer emits it under -Werror.
    "ignore:`torch.jit.script` is deprecated:FutureWarning",
    # 2026-05-15: same linear_operator import path as above, but Torch emits this
    # alternate wording in some import paths. Remove with the filter above.
    "ignore:`torch.jit.script` is not supported:FutureWarning",
    # 2026-05-15: Ax 1.2.4 uses asyncio.iscoroutinefunction in retry helpers.
    # Remove when Ax no longer emits it on Python 3.14 under -Werror.
    "ignore:'asyncio.iscoroutinefunction' is deprecated:DeprecationWarning",
    # 2026-05-15: Ax 1.2.4's JSON storage registry imports this moved shim.
    # Remove when importing ax.api.Client no longer touches the shim.
    "ignore:ax.service.utils.orchestrator_options has been moved:DeprecationWarning",
    # 2026-05-15: Ax 1.2.4's overview analysis imports this moved shim.
    # Remove when importing ax.api.Client no longer touches the shim.
    "ignore:ax.service.orchestrator has been moved:DeprecationWarning",
    # 2026-05-15: Botorch/linear_operator can add Cholesky jitter while fitting
    # the Ax surrogate for log-scale tests. Remove when the current Ax stack no
    # longer emits it under -Werror for the plugin's log-scale sweep.
    "ignore:A not p.d., added jitter:Warning",
]

pytestmark = [mark.filterwarnings(warning_filter) for warning_filter in WARNING_FILTERS]
PYTHON_WARNING_FILTERS = [f"-W{warning_filter}" for warning_filter in WARNING_FILTERS]


def run_ax_python_script(cmd: List[str]) -> Tuple[str, str]:
    return run_python_script(PYTHON_WARNING_FILTERS + cmd)


def test_discovery() -> None:
    """
    Tests that this plugin can be discovered via the plugins subsystem when looking for Sweeper
    :return:
    """
    assert AxSweeper.__name__ in [
        x.__name__ for x in Plugins.instance().discover(Sweeper)
    ]


def quadratic(cfg: DictConfig) -> Any:
    return 100 * (cfg.quadratic.x**2) + 1 * cfg.quadratic.y


@mark.parametrize(
    "n,expected",
    [
        (None, [[1, 2, 3, 4, 5]]),
        (1, [[1], [2], [3], [4], [5]]),
        (2, [[1, 2], [3, 4], [5]]),
        (5, [[1, 2, 3, 4, 5]]),
        (6, [[1, 2, 3, 4, 5]]),
    ],
)
def test_chunk_method_for_valid_inputs(n: int, expected: List[List[int]]) -> None:
    from hydra_plugins.hydra_ax_sweeper._core import CoreAxSweeper

    chunk_func = CoreAxSweeper.chunks
    batch = [1, 2, 3, 4, 5]
    out = list(chunk_func(batch, n))
    assert out == expected


@mark.parametrize("n", [-1, -11, 0])
def test_chunk_method_for_invalid_inputs(n: int) -> None:
    from hydra_plugins.hydra_ax_sweeper._core import CoreAxSweeper

    chunk_func = CoreAxSweeper.chunks
    batch = [1, 2, 3, 4, 5]
    with raises(ValueError):
        list(chunk_func(batch, n))


def test_jobs_dirs(hydra_sweep_runner: TSweepRunner) -> None:
    # Verify that the spawned jobs are not overstepping the directories of one another.
    sweep = hydra_sweep_runner(
        calling_file="tests/test_ax_sweeper_plugin.py",
        calling_module=None,
        task_function=quadratic,
        config_path="config",
        config_name="config.yaml",
        overrides=[
            "hydra/launcher=basic",
            "hydra.sweeper.ax_config.max_trials=6",
            "hydra.sweeper.ax_config.early_stop.max_epochs_without_improvement=100",
            "hydra.sweeper.max_batch_size=2",
            "params=basic",
        ],
    )
    with sweep:
        assert isinstance(sweep.temp_dir, str)
        dirs = [
            x
            for x in os.listdir(sweep.temp_dir)
            if os.path.isdir(os.path.join(sweep.temp_dir, x))
        ]
        assert len(dirs) == 6  # and a total of 6 unique output directories


@mark.parametrize("test_conf", ["basic", "logscale"])
def test_jobs_configured_via_config(
    hydra_sweep_runner: TSweepRunner, test_conf: str
) -> None:
    sweep = hydra_sweep_runner(
        calling_file="tests/test_ax_sweeper_plugin.py",
        calling_module=None,
        task_function=quadratic,
        config_path="config",
        config_name="config.yaml",
        overrides=["hydra/launcher=basic", f"params={test_conf}"],
    )
    with sweep:
        assert sweep.returns is None
        returns = OmegaConf.load(f"{sweep.temp_dir}/optimization_results.yaml")
        assert isinstance(returns, DictConfig)
        assert returns["optimizer"] == "ax"
        assert len(returns) == 2
        best_parameters = returns.ax
        assert math.isclose(best_parameters["quadratic.x"], 0.0, abs_tol=1e-4)
        expected_y = 0.0 if test_conf == "basic" else -1.0
        assert math.isclose(best_parameters["quadratic.y"], expected_y, abs_tol=1e-4)


@mark.parametrize(
    "test_conf, override, expected_x",
    [
        ("basic", "int(interval(1, 5))", 1.0),
    ],
)
def test_jobs_configured_via_cmd(
    hydra_sweep_runner: TSweepRunner, test_conf: str, override: str, expected_x: float
) -> None:
    sweep = hydra_sweep_runner(
        calling_file="tests/test_ax_sweeper_plugin.py",
        calling_module=None,
        task_function=quadratic,
        config_path="config",
        config_name="config.yaml",
        overrides=[
            "hydra/launcher=basic",
            "hydra.sweeper.ax_config.max_trials=5",
            f"quadratic.x={override}",
            "quadratic.y=-2",
            f"params={test_conf}",
        ],
    )
    with sweep:
        assert sweep.returns is None
        returns = OmegaConf.load(f"{sweep.temp_dir}/optimization_results.yaml")
        assert isinstance(returns, DictConfig)
        assert returns["optimizer"] == "ax"
        assert len(returns) == 2
        best_parameters = returns.ax
        assert math.isclose(best_parameters["quadratic.x"], expected_x, abs_tol=1e-4)
        assert math.isclose(best_parameters["quadratic.y"], -2.0, abs_tol=1e-4)


def test_jobs_configured_via_cmd_and_config(hydra_sweep_runner: TSweepRunner) -> None:
    sweep = hydra_sweep_runner(
        calling_file="tests/test_ax_sweeper_plugin.py",
        calling_module=None,
        task_function=quadratic,
        config_path="config",
        config_name="config.yaml",
        overrides=[
            "hydra/launcher=basic",
            "hydra.sweeper.ax_config.max_trials=2",
            "quadratic.x=int(interval(-5, -2))",
            "params=basic",
        ],
    )
    with sweep:
        assert sweep.returns is None
        returns = OmegaConf.load(f"{sweep.temp_dir}/optimization_results.yaml")
        assert isinstance(returns, DictConfig)
        assert returns["optimizer"] == "ax"
        assert len(returns) == 2
        best_parameters = returns.ax
        assert math.isclose(best_parameters["quadratic.x"], -3.0, abs_tol=1e-4)
        assert math.isclose(best_parameters["quadratic.y"], 0.0, abs_tol=1e-4)


def test_command_line_int_interval_optimizes_integer_parabola(
    hydra_sweep_runner: TSweepRunner,
) -> None:
    sweep = hydra_sweep_runner(
        calling_file="tests/test_ax_sweeper_plugin.py",
        calling_module=None,
        task_function=quadratic,
        config_path="config",
        config_name="config.yaml",
        overrides=[
            "hydra/launcher=basic",
            "hydra.sweeper.ax_config.max_trials=12",
            "quadratic.x=int(interval(-5, 5))",
            "quadratic.y=0",
        ],
    )
    with sweep:
        assert sweep.returns is None
        returns = OmegaConf.load(f"{sweep.temp_dir}/optimization_results.yaml")
        assert isinstance(returns, DictConfig)
        best_parameters = returns.ax
        assert isinstance(best_parameters["quadratic.x"], int)
        assert best_parameters["quadratic.x"] == 0
        assert best_parameters["quadratic.y"] == 0


def test_configuration_set_via_cmd_and_default_config(
    hydra_sweep_runner: TSweepRunner,
) -> None:
    sweep = hydra_sweep_runner(
        calling_file="tests/test_ax_sweeper_plugin.py",
        calling_module=None,
        task_function=quadratic,
        config_path="config",
        config_name="config.yaml",
        overrides=[
            "hydra/launcher=basic",
            "hydra.sweeper.ax_config.max_trials=2",
            "hydra.sweeper.ax_config.early_stop.max_epochs_without_improvement=2",
            "quadratic=basic",
            "quadratic.x=interval(-5, -2)",
            "quadratic.y=interval(-1, 1)",
        ],
    )
    with sweep:
        assert sweep.returns is None
        returns = OmegaConf.load(f"{sweep.temp_dir}/optimization_results.yaml")
        assert isinstance(returns, DictConfig)
        best_parameters = returns.ax
        assert "quadratic.x" in best_parameters
        assert "quadratic.y" in best_parameters


@mark.parametrize(
    "cmd_arg, expected_str",
    [
        ("polynomial.y=choice(-1, 0, 1)", "polynomial.y: choice=[-1, 0, 1]"),
        ("polynomial.y=range(-1, 2)", "polynomial.y: choice=[-1, 0, 1]"),
        ("polynomial.y=range(-1, 3, 1)", "polynomial.y: choice=[-1, 0, 1, 2]"),
        (
            "polynomial.y=range(-1, 2, 0.5)",
            "polynomial.y: choice=[-1.0, -0.5, 0.0, 0.5, 1.0, 1.5]",
        ),
        ("polynomial.y=int(interval(-1, 2))", "polynomial.y: range=[-1, 2]"),
        ("polynomial.y=interval(-1, 2)", "polynomial.y: range=[-1.0, 2.0]"),
        (
            "polynomial.y=tag(log, interval(0.00001, 1))",
            "polynomial.y: range=[1e-05, 1.0], log_scale = True",
        ),
        ("polynomial.y=2", "polynomial.y: fixed=2"),
        ("polynomial.y=2.0", "polynomial.y: fixed=2.0"),
    ],
)
def test_ax_logging(cmd_arg: str, expected_str: str) -> None:
    from hydra_plugins.hydra_ax_sweeper._core import (
        CoreAxSweeper,
        encoder_parameters_into_string,
    )
    from hydra_plugins.hydra_ax_sweeper.config import AxConfig

    sweeper = CoreAxSweeper(AxConfig(), max_batch_size=None)
    parameters = sweeper.parse_commandline_args(
        [
            "polynomial.x=interval(-5, -2)",
            "polynomial.z=10",
            cmd_arg,
        ]
    )
    result = encoder_parameters_into_string(parameters)
    assert "polynomial.x: range=[-5.0, -2.0]" in result
    assert expected_str in result
    assert "polynomial.z: fixed=10" in result


def test_command_line_log_interval_configures_ax_log_range() -> None:
    from ax.api.configs import RangeParameterConfig  # type: ignore

    from hydra_plugins.hydra_ax_sweeper._core import (
        CoreAxSweeper,
        create_ax_parameter_config,
    )
    from hydra_plugins.hydra_ax_sweeper.config import AxConfig

    sweeper = CoreAxSweeper(AxConfig(), max_batch_size=None)
    (parameter,) = sweeper.parse_commandline_args(
        ["polynomial.y=tag(log, interval(0.00001, 1))"]
    )
    ax_parameter = create_ax_parameter_config(parameter)
    assert isinstance(ax_parameter, RangeParameterConfig)
    assert ax_parameter.name == "polynomial.y"
    assert ax_parameter.parameter_type == "float"
    assert ax_parameter.bounds == (1e-05, 1.0)
    assert ax_parameter.scaling == "log"


def test_create_ax_raw_data() -> None:
    from hydra_plugins.hydra_ax_sweeper._core import create_ax_raw_data

    assert create_ax_raw_data(1, "loss", is_noisy=True) == {"loss": 1.0}
    assert create_ax_raw_data(1, "loss", is_noisy=False) == {"loss": (1.0, 0.0)}
    assert create_ax_raw_data({"loss": 1, "accuracy": (0.5, 0.1)}, "loss", True) == {
        "loss": 1.0,
        "accuracy": (0.5, 0.1),
    }

    raw_data = create_ax_raw_data((1, None), "loss", is_noisy=True)
    loss = raw_data["loss"]
    assert isinstance(loss, tuple)
    sem = loss[1]
    assert math.isnan(sem)


def test_ax_logging_from_hydra_app(tmpdir: Path) -> None:
    cmd = [
        "tests/apps/polynomial.py",
        "-m",
        f'hydra.run.dir="{str(tmpdir)}"',
        "hydra.job.chdir=True",
        "polynomial.x=interval(-5, -2)",
        "polynomial.z=10",
        "hydra.sweeper.ax_config.max_trials=2",
        "polynomial.y=int(interval(-1, 2))",
    ]
    result, _ = run_ax_python_script(cmd)
    assert "polynomial.x: range=[-5.0, -2.0]" in result
    assert "polynomial.y: range=[-1, 2]" in result
    assert "polynomial.z: fixed=10" in result


@mark.parametrize(
    "cmd_args",
    [
        ["polynomial.y=choice(-1, 0, 1)", "polynomial.x=range(2,4)"],
        ["polynomial.y=1", "polynomial.x=range(2,4)"],
    ],
)
def test_search_space_exhausted_exception(tmpdir: Path, cmd_args: List[str]) -> None:
    cmd = [
        "tests/apps/polynomial.py",
        "-m",
        f'hydra.run.dir="{str(tmpdir)}"',
        "hydra.job.chdir=True",
        "hydra.sweeper.ax_config.max_trials=2",
    ] + cmd_args
    run_ax_python_script(cmd)


@mark.parametrize(
    "cmd_args",
    [
        ["polynomial.y=choice(-1, 0, 1)", "polynomial.x=range(2,4)"],
        ["polynomial.y=1", "polynomial.x=range(2,4)"],
    ],
)
def test_search_space_with_constraint_metric(tmpdir: Path, cmd_args: List[str]) -> None:
    # test that outcome_constraints experiment parameter `outcome_constraints`
    # works correctly, and that the ax_sweeper supports outputting a dictionary
    # from the evaluation function so that multiple metrics can be supported.
    cmd = [
        "tests/apps/polynomial_with_constraint.py",
        "-m",
        f'hydra.run.dir="{str(tmpdir)}"',
        "hydra.job.chdir=True",
        "hydra.sweeper.ax_config.max_trials=2",
    ] + cmd_args
    results, _ = run_ax_python_script(cmd)


@mark.parametrize(
    "cmd_arg, serialized_encoding, best_coefficients, best_value",
    [
        (
            "polynomial.coefficients=[-1, 0, 1],[2, 3, 4],[5, 6, 7]",
            "choice=['[-1,0,1]', '[2,3,4]', '[5,6,7]']",
            "'[-1,0,1]'",
            101.0,
        ),
        (
            "polynomial.coefficients=choice([8, 12, 11],[-1, -1, 1000], [-2, 4, 7])",
            "choice=['[8,12,11]', '[-1,-1,1000]', '[-2,4,7]']",
            "'[-2,4,7]'",
            447,
        ),
    ],
)
def test_jobs_using_choice_between_lists(
    tmpdir: Path,
    cmd_arg: str,
    serialized_encoding: str,
    best_coefficients: str,
    best_value: float,
) -> None:
    cmd = [
        "tests/apps/polynomial_with_list_coefficients.py",
        "-m",
        f'hydra.run.dir="{str(tmpdir)}"',
        "hydra.job.chdir=True",
        "hydra.sweeper.ax_config.max_trials=3",
    ] + [cmd_arg]
    result, _ = run_ax_python_script(cmd)
    assert f"polynomial.coefficients: {serialized_encoding}" in result
    assert f"'polynomial.coefficients': {best_coefficients}" in result
    assert f"New best value: {best_value}" in result


@mark.parametrize(
    "cmd_arg, serialized_encoding, best_coefficients, best_value",
    [
        (
            "+polynomial.coefficients=choice({x:-1, y:0, z:1},{x:2, y:3, z:4},{x:5, y:6, z:7})",
            "choice=['{x:-1,y:0,z:1}', '{x:2,y:3,z:4}', '{x:5,y:6,z:7}']",
            "'{x:-1,y:0,z:1}'",
            101.0,
        ),
        (
            "+polynomial.coefficients=choice({x:8, y:12, z:11},{x:-1, y:-1, z:1000}, {x:-2, y:4, z:7})",
            "choice=['{x:8,y:12,z:11}', '{x:-1,y:-1,z:1000}', '{x:-2,y:4,z:7}']",
            "'{x:-2,y:4,z:7}'}",
            447,
        ),
    ],
)
def test_jobs_using_choice_between_dicts(
    tmpdir: Path,
    cmd_arg: str,
    serialized_encoding: str,
    best_coefficients: str,
    best_value: float,
) -> None:
    cmd = [
        "tests/apps/polynomial_with_dict_coefficients.py",
        "-m",
        f'hydra.run.dir="{str(tmpdir)}"',
        "hydra.job.chdir=True",
        "hydra.sweeper.ax_config.max_trials=3",
    ] + [cmd_arg]
    result, _ = run_ax_python_script(cmd)
    assert f"polynomial.coefficients: {serialized_encoding}" in result
    assert f"'+polynomial.coefficients': {best_coefficients}" in result
    assert f"New best value: {best_value}" in result


def test_example_app(tmpdir: Path) -> None:
    cmd = [
        "example/banana.py",
        "-m",
        f'hydra.run.dir="{str(tmpdir)}"',
        "hydra.job.chdir=True",
        "banana.x=int(interval(-5, 5))",
        "banana.y=interval(-5, 10.1)",
        "hydra.sweeper.ax_config.max_trials=2",
    ]
    result, _ = run_ax_python_script(cmd)
    assert "banana.x: range=[-5, 5]" in result
    assert "banana.y: range=[-5.0, 10.1]" in result

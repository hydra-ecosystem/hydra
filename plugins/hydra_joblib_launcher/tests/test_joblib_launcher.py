# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, cast

from hydra.core.plugins import Plugins
from hydra.core.utils import JobReturn
from hydra.plugins.launcher import Launcher
from hydra.test_utils.launcher_common_tests import (
    IntegrationTestSuite,
    LauncherTestSuite,
)
from hydra.test_utils.test_utils import (
    TSweepRunner,
    chdir_plugin_root,
    run_python_script,
)
from omegaconf import OmegaConf
from pytest import mark, raises

from hydra_plugins.hydra_joblib_launcher import _core
from hydra_plugins.hydra_joblib_launcher.joblib_launcher import JoblibLauncher

chdir_plugin_root()


class CallableTask:
    def __call__(self, cfg: Any) -> None:
        pass


def test_discovery() -> None:
    # Tests that this plugin can be discovered via the plugins subsystem when looking for Launchers
    assert JoblibLauncher.__name__ in [
        x.__name__ for x in Plugins.instance().discover(Launcher)
    ]


@mark.parametrize("launcher_name, overrides", [("joblib", [])])
class TestJoblibLauncher(LauncherTestSuite):
    """
    Run the Launcher test suite on this launcher.
    """

    pass


@mark.parametrize(
    "task_launcher_cfg, extra_flags",
    [
        # joblib with process-based backend (default)
        (
            {},
            [
                "-m",
                "hydra/job_logging=hydra_debug",
                "hydra/job_logging=disabled",
                "hydra/launcher=joblib",
            ],
        )
    ],
)
class TestJoblibLauncherIntegration(IntegrationTestSuite):
    """
    Run this launcher through the integration test suite.
    """

    pass


def test_example_app(hydra_sweep_runner: TSweepRunner, tmpdir: Any) -> None:
    with hydra_sweep_runner(
        calling_file="example/my_app.py",
        calling_module=None,
        task_function=None,
        config_path=".",
        config_name="config",
        overrides=["task=1,2,3,4", f"hydra.sweep.dir={tmpdir}"],
    ) as sweep:
        overrides = {("task=1",), ("task=2",), ("task=3",), ("task=4",)}

        assert sweep.returns is not None and len(sweep.returns[0]) == 4
        for ret in sweep.returns[0]:
            assert tuple(ret.overrides) in overrides


def test_example_app_loads_its_config(tmp_path: Path) -> None:
    stdout, _stderr = run_python_script(
        [
            "example/my_app.py",
            "--multirun",
            "task=1,2",
            f'hydra.sweep.dir="{tmp_path}"',
            "hydra.launcher.n_jobs=1",
        ],
    )

    assert "Joblib.Parallel" in stdout
    assert (tmp_path / "0" / "my_app.log").exists()
    assert (tmp_path / "1" / "my_app.log").exists()


@mark.parametrize("n_jobs", [1, 2])
def test_multiprocessing_backend_isolates_jobs_and_preserves_state(
    tmp_path: Path, n_jobs: int
) -> None:
    run_python_script(
        [
            "tests/apps/multiprocessing_app.py",
            "--multirun",
            "hydra/launcher=joblib",
            "hydra.launcher.backend=multiprocessing",
            f"hydra.launcher.n_jobs={n_jobs}",
            "+job=0,1,2,3",
            "+runtime_value=${runtime_test:ok}",
            f'hydra.sweep.dir="{tmp_path}"',
        ],
    )

    results = [
        (tmp_path / str(job_num) / "result.txt").read_text(encoding="utf-8")
        for job_num in range(4)
    ]
    pids = {result.split()[0] for result in results}

    assert len(pids) == 4
    assert {result.split()[1] for result in results} == {"resolved-ok"}


def test_multiprocessing_backend_runs_callable_task(tmp_path: Path) -> None:
    run_python_script(
        [
            "tests/apps/multiprocessing_callable_app.py",
            "--multirun",
            "hydra/launcher=joblib",
            "hydra.launcher.backend=multiprocessing",
            "hydra.launcher.n_jobs=2",
            "+job=0,1",
            f'hydra.sweep.dir="{tmp_path}"',
        ],
    )

    assert {
        (tmp_path / str(job_num) / "result.txt").read_text(encoding="utf-8")
        for job_num in range(2)
    } == {"callable-0", "callable-1"}


def test_multiprocessing_backend_transports_non_picklable_return_value(
    tmp_path: Path,
) -> None:
    run_python_script(
        [
            "tests/apps/multiprocessing_app.py",
            "--multirun",
            "hydra/launcher=joblib",
            "hydra.launcher.backend=multiprocessing",
            "hydra.launcher.n_jobs=2",
            "+job=0",
            "+runtime_value=${runtime_test:ok}",
            "+return_lambda=true",
            f'hydra.sweep.dir="{tmp_path}"',
        ],
    )

    assert (tmp_path / "0" / "result.txt").exists()


@mark.parametrize("backend", ["threading", "sequential", "dask"])
def test_rejects_unsupported_backend(backend: str) -> None:
    with raises(ValueError, match="Unsupported Joblib backend"):
        _core.process_joblib_cfg({"backend": backend})


def test_null_backend_defaults_to_loky() -> None:
    config = {"backend": None}

    _core.process_joblib_cfg(config)

    assert config["backend"] == "loky"


def test_failure_preserves_source_in_worker_log(tmp_path: Path) -> None:
    _stdout, stderr = run_python_script(
        [
            "tests/apps/failing_app.py",
            "--multirun",
            "hydra/launcher=joblib",
            "hydra.launcher.n_jobs=2",
            f'hydra.sweep.dir="{tmp_path}"',
        ],
        print_error=False,
        raise_exception=False,
    )

    for output in (stderr, (tmp_path / "0" / "failing_app.log").read_text()):
        assert 'raise ValueError("joblib remote cause")' in output
        assert 'raise RuntimeError("joblib remote failure") from cause' in output
        assert "<dynamic-code>" not in output


def test_multiprocessing_enforces_process_isolation() -> None:
    config = {"backend": "multiprocessing", "batch_size": "auto"}

    _core.process_joblib_cfg(config)

    assert config["batch_size"] == 1
    assert config["maxtasksperchild"] == 1


def test_multiprocessing_accepts_callable_task() -> None:
    task = CallableTask()

    resolved_task, unwrap_depth = _core._get_multiprocessing_task_function(task)

    assert resolved_task is task
    assert unwrap_depth == 0


def test_multiprocessing_rejects_undiscoverable_function() -> None:
    def task(cfg: Any) -> None:
        pass

    with raises(TypeError, match="requires function tasks to be defined"):
        _core._get_multiprocessing_task_function(task)


@mark.parametrize(
    "config, message",
    [
        (
            {"backend": "multiprocessing", "inner_max_num_threads": 1},
            "inner_max_num_threads is supported only by the loky backend",
        ),
        (
            {"backend": "loky", "maxtasksperchild": 1},
            "maxtasksperchild is supported only by the multiprocessing backend",
        ),
        (
            {"backend": "multiprocessing", "batch_size": 2},
            "requires batch_size=1",
        ),
        (
            {"backend": "multiprocessing", "maxtasksperchild": 2},
            "fixes maxtasksperchild at 1",
        ),
    ],
)
def test_rejects_backend_specific_option(config: dict[str, Any], message: str) -> None:
    with raises(ValueError, match=message):
        _core.process_joblib_cfg(config)


def test_inner_max_num_threads_configures_loky_backend(
    hydra_sweep_runner: TSweepRunner, monkeypatch: Any
) -> None:
    calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []
    real_parallel_backend = _core.parallel_backend

    @contextmanager
    def spy_parallel_backend(*args: Any, **kwargs: Any) -> Iterator[None]:
        calls.append((args, kwargs))
        with real_parallel_backend(*args, **kwargs):
            yield

    monkeypatch.setattr(_core, "parallel_backend", spy_parallel_backend)

    with hydra_sweep_runner(
        calling_file="example/my_app.py",
        calling_module=None,
        task_function=None,
        config_path=".",
        config_name="config",
        overrides=[
            "hydra.launcher.n_jobs=1",
            "hydra.launcher.inner_max_num_threads=2",
        ],
    ) as sweep:
        assert sweep.returns is not None and len(sweep.returns[0]) == 1

    assert calls == [(("loky",), {"n_jobs": 1, "inner_max_num_threads": 2})]


def test_inner_max_num_threads_does_not_require_n_jobs(
    monkeypatch: Any, tmp_path: Path
) -> None:
    backend_calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []
    parallel_calls: list[dict[str, Any]] = []

    @contextmanager
    def spy_parallel_backend(*args: Any, **kwargs: Any) -> Iterator[None]:
        backend_calls.append((args, kwargs))
        yield

    class FakeParallel:
        def __init__(self, **kwargs: Any) -> None:
            parallel_calls.append(kwargs)

        def __call__(self, calls: Any) -> list[JobReturn]:
            return [JobReturn()]

    monkeypatch.setattr(_core, "parallel_backend", spy_parallel_backend)
    monkeypatch.setattr(_core, "Parallel", FakeParallel)

    launcher = JoblibLauncher(inner_max_num_threads=2)
    launcher.config = OmegaConf.create(
        {
            "hydra": {
                "hydra_logging": None,
                "verbose": False,
                "sweep": {"dir": str(tmp_path)},
            }
        }
    )
    launcher.task_function = cast(Any, lambda cfg: None)
    launcher.hydra_context = cast(Any, object())

    _core.launch(launcher=launcher, job_overrides=[[]], initial_job_idx=0)

    assert backend_calls == [(("loky",), {"inner_max_num_threads": 2})]
    assert len(parallel_calls) == 1
    assert "n_jobs" not in parallel_calls[0]


@mark.parametrize(
    "overrides",
    [
        "hydra.launcher.batch_size=1",
        "hydra.launcher.max_nbytes=10000",
        "hydra.launcher.max_nbytes=1M",
        "hydra.launcher.pre_dispatch=all",
        "hydra.launcher.pre_dispatch=10",
        "hydra.launcher.pre_dispatch=3*n_jobs",
    ],
)
def test_example_app_launcher_overrides(
    hydra_sweep_runner: TSweepRunner, overrides: str
) -> None:
    with hydra_sweep_runner(
        calling_file="example/my_app.py",
        calling_module=None,
        task_function=None,
        config_path=".",
        config_name="config",
        overrides=[overrides],
    ) as sweep:
        assert sweep.returns is not None and len(sweep.returns[0]) == 1

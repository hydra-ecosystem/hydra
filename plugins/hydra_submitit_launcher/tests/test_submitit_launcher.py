# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved
from pathlib import Path
from typing import Any, cast
from unittest.mock import MagicMock, patch

import submitit
from hydra.core.plugins import Plugins
from hydra.plugins.launcher import Launcher
from hydra.test_utils.launcher_common_tests import (
    IntegrationTestSuite,
    LauncherTestSuite,
)
from hydra.test_utils.test_utils import chdir_plugin_root, run_python_script
from hydra.utils import instantiate
from omegaconf import OmegaConf
from pytest import mark

from hydra_plugins.hydra_submitit_launcher import submitit_launcher
from hydra_plugins.hydra_submitit_launcher._serialization import (
    SourceExecutor,
    SourceSubmission,
)
from hydra_plugins.hydra_submitit_launcher.config import SlurmQueueConf

chdir_plugin_root()

pytestmark = mark.filterwarnings("ignore:pkg_resources is deprecated as an API:Warning")


@mark.parametrize(
    "cls", [submitit_launcher.LocalLauncher, submitit_launcher.SlurmLauncher]
)
def test_discovery(cls: type[Launcher]) -> None:
    # Tests that this plugin can be discovered via the plugins subsystem when looking for Launchers
    assert cls.__name__ in [x.__name__ for x in Plugins.instance().discover(Launcher)]


@mark.parametrize(
    "launcher_name, overrides", [("submitit_local", ["hydra.launcher.timeout_min=2"])]
)
class TestSubmititLauncher(LauncherTestSuite):
    pass


@mark.parametrize(
    "task_launcher_cfg, extra_flags",
    [
        (
            {},
            [
                "-m",
                "hydra/hydra_logging=disabled",
                "hydra/job_logging=disabled",
                "hydra/launcher=submitit_local",
                "hydra.launcher.gpus_per_node=0",
                "hydra.launcher.timeout_min=1",
            ],
        ),
    ],
)
class TestSubmititLauncherIntegration(IntegrationTestSuite):
    pass


@mark.parametrize("python", [None, "/opt/venv/bin/python"])
def test_slurm_python_parameter(tmp_path: Path, python: str | None) -> None:
    executor = MagicMock()
    executor.map_array.return_value = []
    auto_executor = MagicMock(return_value=executor)

    config = OmegaConf.create(
        {
            "hydra": {
                "job": {"name": "test"},
                "sweep": {"dir": str(tmp_path / "sweep")},
                "launcher": OmegaConf.structured(SlurmQueueConf),
            }
        }
    )
    config.hydra.launcher.python = python
    launcher = instantiate(
        config.hydra.launcher,
        _execution_whitelist_=(
            "hydra_plugins.hydra_submitit_launcher.submitit_launcher.SlurmLauncher"
        ),
    )
    launcher.config = config

    with patch(
        "hydra_plugins.hydra_submitit_launcher._serialization.SourceExecutor",
        auto_executor,
    ):
        assert launcher.launch([[]], initial_job_idx=0) == []

    auto_executor.assert_called_once_with(
        cluster="slurm",
        folder=str(tmp_path / "sweep" / ".submitit" / "%j"),
        slurm_max_num_timeout=0,
        slurm_python=python,
    )
    assert "slurm_python" not in executor.update_parameters.call_args.kwargs


@mark.parametrize("tasks_per_node", [1, None])
def test_slurm_tasks_per_node_is_optional_with_compatible_default(
    tmp_path: Path, tasks_per_node: int | None
) -> None:
    assert SlurmQueueConf().tasks_per_node == 1

    executor = MagicMock()
    executor.map_array.return_value = []
    config = OmegaConf.create(
        {
            "hydra": {
                "job": {"name": "test"},
                "sweep": {"dir": str(tmp_path / "sweep")},
                "launcher": OmegaConf.structured(SlurmQueueConf),
            }
        }
    )
    config.hydra.launcher.tasks_per_node = tasks_per_node
    launcher = instantiate(
        config.hydra.launcher,
        _execution_whitelist_=(
            "hydra_plugins.hydra_submitit_launcher.submitit_launcher.SlurmLauncher"
        ),
    )
    launcher.config = config

    with patch(
        "hydra_plugins.hydra_submitit_launcher._serialization.SourceExecutor",
        return_value=executor,
    ):
        assert launcher.launch([[]], initial_job_idx=0) == []

    assert (
        executor.update_parameters.call_args.kwargs["tasks_per_node"] == tasks_per_node
    )


@mark.parametrize("use_srun", [True, False])
def test_slurm_use_srun_parameter(tmp_path: Path, use_srun: bool) -> None:
    assert SlurmQueueConf().use_srun is True

    executor = MagicMock()
    executor.map_array.return_value = []
    config = OmegaConf.create(
        {
            "hydra": {
                "job": {"name": "test"},
                "sweep": {"dir": str(tmp_path / "sweep")},
                "launcher": OmegaConf.structured(SlurmQueueConf),
            }
        }
    )
    config.hydra.launcher.use_srun = use_srun
    launcher = instantiate(
        config.hydra.launcher,
        _execution_whitelist_=(
            "hydra_plugins.hydra_submitit_launcher.submitit_launcher.SlurmLauncher"
        ),
    )
    launcher.config = config

    with patch(
        "hydra_plugins.hydra_submitit_launcher._serialization.SourceExecutor",
        return_value=executor,
    ):
        assert launcher.launch([[]], initial_job_idx=0) == []

    assert executor.update_parameters.call_args.kwargs["slurm_use_srun"] is use_srun
    assert "use_srun" not in executor.update_parameters.call_args.kwargs


def test_example(tmpdir: Path) -> None:
    run_python_script(
        [
            "example/my_app.py",
            "-m",
            f"hydra.sweep.dir={tmpdir}",
            "hydra/launcher=submitit_local",
        ],
        allow_warnings=True,
    )


def test_failure_preserves_remote_traceback(tmp_path: Path) -> None:
    _stdout, stderr = run_python_script(
        [
            "tests/apps/failing_app.py",
            "--multirun",
            "hydra/launcher=submitit_local",
            "hydra.launcher.gpus_per_node=0",
            "hydra.launcher.timeout_min=1",
            "+job=0",
            f'hydra.sweep.dir="{tmp_path}"',
        ],
        allow_warnings=True,
        print_error=False,
        raise_exception=False,
    )

    assert "ValueError: submitit remote cause 0" in stderr
    assert "The above exception was the direct cause" in stderr
    assert "in main" in stderr
    assert 'raise RuntimeError(f"submitit remote failure {cfg.job}")' in stderr
    assert "RuntimeError: submitit remote failure 0" in stderr
    worker_log = (tmp_path / "0" / "failing_app.log").read_text()
    assert 'raise RuntimeError(f"submitit remote failure {cfg.job}")' in worker_log
    assert 'raise ValueError(f"submitit remote cause {cfg.job}")' in worker_log
    assert "<dynamic-code>" not in worker_log


def test_submission_preserves_source_and_shared_state_once(tmp_path: Path) -> None:
    class Once:
        calls = 0

        def __reduce__(self) -> Any:
            self.calls += 1
            assert self.calls == 1
            return list, ()

    shared = Once()

    def task(other: Any) -> tuple[bool, str]:
        return shared is other, task.__code__.co_filename

    submission = SourceSubmission(task, other=shared)
    submission.set_timeout(13, 2)
    path = tmp_path / "submission.pkl"
    submission.dump(path)
    restored = submitit.helpers.DelayedSubmission.load(path)

    assert restored.__class__.__name__ == "DelayedSubmission"
    assert restored._timeout_min == 13
    assert restored._timeout_countdown == 2
    assert restored.result() == (True, __file__)
    assert shared.calls == 1


def test_checkpoint_preserves_task_source(tmp_path: Path) -> None:
    launcher = submitit_launcher.LocalLauncher()

    def task(cfg: Any) -> None:
        pass

    launcher.task_function = task
    submission = launcher.checkpoint([], "hydra.sweep.dir", 0, "job", {})
    assert isinstance(submission, SourceSubmission)
    path = tmp_path / "checkpoint.pkl"
    submission.dump(path)
    restored = submitit.helpers.DelayedSubmission.load(path)

    restored_launcher = cast(submitit_launcher.LocalLauncher, restored.function)
    assert restored_launcher.task_function is not None
    assert getattr(restored_launcher.task_function, "__code__").co_filename == __file__


@mark.parametrize("count", [1, 2])
def test_slurm_submissions_preserve_source(tmp_path: Path, count: int) -> None:
    def task(value: int) -> tuple[int, str]:
        return value, task.__code__.co_filename

    with patch.object(submitit.SlurmExecutor, "affinity", return_value=2):
        executor = SourceExecutor(folder=tmp_path, cluster="slurm")
        executor.update_parameters(timeout_min=1)
        with patch.object(
            submitit.SlurmExecutor,
            "_submit_command",
            return_value=submitit.SlurmJob(folder=tmp_path, job_id="123", tasks=[0]),
        ):
            jobs = executor.map_array(task, range(count))

    assert len(jobs) == count
    for index, job in enumerate(jobs):
        restored = submitit.helpers.DelayedSubmission.load(job.paths.submitted_pickle)
        assert restored.result() == (index, __file__)

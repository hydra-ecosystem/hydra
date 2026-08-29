# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved
from pathlib import Path
from typing import Optional, Type
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
from hydra_plugins.hydra_submitit_launcher.config import SlurmQueueConf

chdir_plugin_root()

pytestmark = mark.filterwarnings("ignore:pkg_resources is deprecated as an API:Warning")


@mark.parametrize(
    "cls", [submitit_launcher.LocalLauncher, submitit_launcher.SlurmLauncher]
)
def test_discovery(cls: Type[Launcher]) -> None:
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
def test_slurm_python_parameter(tmp_path: Path, python: Optional[str]) -> None:
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

    with patch.object(submitit, "AutoExecutor", auto_executor):
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
    tmp_path: Path, tasks_per_node: Optional[int]
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

    with patch.object(submitit, "AutoExecutor", return_value=executor):
        assert launcher.launch([[]], initial_job_idx=0) == []

    assert (
        executor.update_parameters.call_args.kwargs["tasks_per_node"] == tasks_per_node
    )


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

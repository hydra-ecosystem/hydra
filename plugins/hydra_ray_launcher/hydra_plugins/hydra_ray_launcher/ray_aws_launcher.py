# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved
import logging
from typing import Any, Sequence, cast

from hydra.core.utils import JobReturn
from hydra.plugins.launcher import Launcher
from hydra.types import HydraContext, TaskFunction
from omegaconf import DictConfig

from ._config import (
    RayAWSConf,
    RayCreateOrUpdateClusterConf,
    RayLoggingConf,
    RayTeardownClusterConf,
    RsyncConf,
)

log = logging.getLogger(__name__)


class RayAWSLauncher(Launcher):
    def __init__(
        self,
        env_setup: DictConfig,
        ray: RayAWSConf,
        stop_cluster: bool,
        sync_up: RsyncConf,
        sync_down: RsyncConf,
        logging: RayLoggingConf,
        create_update_cluster: RayCreateOrUpdateClusterConf,
        teardown_cluster: RayTeardownClusterConf,
    ) -> None:
        self.ray_cfg = ray
        self.stop_cluster = stop_cluster
        self.sync_up = sync_up
        self.sync_down = sync_down
        self.logging = logging
        self.create_update_cluster = create_update_cluster
        self.teardown_cluster = teardown_cluster
        self.config: DictConfig | None = None
        self.hydra_context: HydraContext | None = None
        self.task_function: TaskFunction | None = None
        self.ray_yaml_path: str | None = None
        self.env_setup = env_setup

    def setup(
        self,
        *,
        hydra_context: HydraContext,
        task_function: TaskFunction,
        config: DictConfig,
    ) -> None:
        self.config = config
        self.hydra_context = hydra_context
        self.task_function = task_function

    def launch(
        self, job_overrides: Sequence[Sequence[str]], initial_job_idx: int
    ) -> Sequence[JobReturn]:
        from . import _core_aws

        return _core_aws.launch(
            launcher=cast(Any, self),
            job_overrides=job_overrides,
            initial_job_idx=initial_job_idx,
        )

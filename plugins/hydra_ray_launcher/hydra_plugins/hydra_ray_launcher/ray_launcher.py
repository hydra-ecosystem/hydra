# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved
from typing import Any, Sequence, cast

from hydra.core.utils import JobReturn
from hydra.plugins.launcher import Launcher
from hydra.types import HydraContext, TaskFunction
from omegaconf import DictConfig

from . import _config as _config


class RayLauncher(Launcher):
    def __init__(self, ray: DictConfig) -> None:
        self.ray_cfg = ray
        self.hydra_context: HydraContext | None = None
        self.task_function: TaskFunction | None = None
        self.config: DictConfig | None = None

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
        from . import _core

        return _core.launch(
            launcher=cast(Any, self),
            job_overrides=job_overrides,
            initial_job_idx=initial_job_idx,
        )

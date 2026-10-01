# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved

from hydra.plugins.sweeper import Sweeper
from hydra.types import HydraContext, TaskFunction
from omegaconf import DictConfig

from .config import AxConfig


class AxSweeper(Sweeper):
    """Class to interface with the Ax Platform"""

    def __init__(self, ax_config: AxConfig, max_batch_size: int | None):
        from ._core import CoreAxSweeper

        self.sweeper = CoreAxSweeper(ax_config, max_batch_size)

    def setup(
        self,
        *,
        hydra_context: HydraContext,
        task_function: TaskFunction,
        config: DictConfig,
    ) -> None:
        return self.sweeper.setup(
            hydra_context=hydra_context, task_function=task_function, config=config
        )

    def sweep(self, arguments: list[str]) -> None:
        return self.sweeper.sweep(arguments)

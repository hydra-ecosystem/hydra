# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved
"""
Sweeper plugin interface
"""

from abc import abstractmethod
from typing import Any, Sequence

from omegaconf import DictConfig

from hydra.types import HydraContext, TaskFunction

from .launcher import Launcher
from .plugin import Plugin


class Sweeper(Plugin):
    """
    An abstract sweeper interface
    Sweeper takes the command line arguments, generates a and launches jobs
    (where each job typically takes a different command line arguments)
    """

    hydra_context: HydraContext | None
    config: DictConfig | None
    launcher: Launcher | None

    @abstractmethod
    def setup(
        self,
        *,
        hydra_context: HydraContext,
        task_function: TaskFunction,
        config: DictConfig,
    ) -> None:
        raise NotImplementedError()

    @abstractmethod
    def sweep(self, arguments: list[str]) -> Any:
        """
        Execute a sweep
        :param arguments: list of strings describing what this sweeper should do.
        exact structure is determine by the concrete Sweeper class.
        :return: the return objects of all thy launched jobs. structure depends on the Sweeper
        implementation.
        """
        ...

    def validate_batch_is_legal(self, batch: Sequence[Sequence[str]]) -> None:
        """
        Ensures that the given batch can be composed.
        This repeat work the launcher will do, but as the launcher may be performing this in a different
        process/machine it's important to do it here as well to detect failures early.
        """
        assert self.config is not None
        assert self.hydra_context is not None
        for overrides in batch:
            self.hydra_context.config_loader.load_sweep_config(
                master_config=self.config, sweep_overrides=list(overrides)
            )

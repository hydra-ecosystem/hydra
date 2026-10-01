# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved
from dataclasses import dataclass, field
from typing import Any

from hydra.core.config_store import ConfigStore


@dataclass
class EarlyStopConfig:
    minimize: bool = True

    max_epochs_without_improvement: int = 10

    # An improvement larger than epsilon is considered significant
    epsilon: float = 0.00001


@dataclass
class ExperimentConfig:
    # Experiment name
    name: str | None = None

    # Name of metric to optimize or null if you only return one metric
    objective_name: str = "objective"

    # Defaults to minimize, set to false to maximize
    minimize: bool = True

    # For the remaining parameters, refer the Ax documentation: https://ax.dev/api/core.html#experiment
    parameter_constraints: list[str] | None = None
    outcome_constraints: list[str] | None = None
    status_quo: dict[str, Any] | None = None


@dataclass
class ClientConfig:
    verbose_logging: bool = False

    # set random seed here to make Ax results reproducible
    random_seed: int | None = None


@dataclass
class AxConfig:
    # max_trials is application-specific. Tune it for your use case
    max_trials: int = 10
    early_stop: EarlyStopConfig = field(default_factory=EarlyStopConfig)
    experiment: ExperimentConfig = field(default_factory=ExperimentConfig)
    client: ClientConfig = field(default_factory=ClientConfig)
    params: dict[str, Any] = field(default_factory=dict)
    # is_noisy = True indicates measurements have unknown uncertainty
    # is_noisy = False indicates measurements have an uncertainty of zero
    is_noisy: bool = True


@dataclass
class AxSweeperConf:
    _target_: str = "hydra_plugins.hydra_ax_sweeper.ax_sweeper.AxSweeper"
    # Maximum number of trials to run in parallel
    max_batch_size: int | None = None
    ax_config: AxConfig = field(default_factory=AxConfig)


ConfigStore.instance().store(
    group="hydra/sweeper", name="ax", node=AxSweeperConf, provider="ax_sweeper"
)

# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, NoReturn

from hydra.core.config_store import ConfigStore
from omegaconf import MISSING


def raise_motpe_removed(*args: Any, **kwargs: Any) -> NoReturn:
    raise ValueError(
        "The 'motpe' sampler was removed in Optuna 4.0. "
        "Use 'hydra/sweeper/sampler=tpe' instead. "
        "TPESampler now handles multi-objective optimization."
    )


class Direction(Enum):
    minimize = 1
    maximize = 2


@dataclass
class SamplerConfig:
    _target_: str = MISSING


@dataclass
class GridSamplerConfig(SamplerConfig):
    """
    https://optuna.readthedocs.io/en/stable/reference/generated/optuna.samplers.GridSampler.html
    """

    _target_: str = "optuna.samplers.GridSampler"
    # search_space will be populated at run time based on hydra.sweeper.params
    _partial_: bool = True
    seed: int | None = None


@dataclass
class TPESamplerConfig(SamplerConfig):
    """
    https://optuna.readthedocs.io/en/stable/reference/generated/optuna.samplers.TPESampler.html
    """

    _target_: str = "optuna.samplers.TPESampler"
    seed: int | None = None

    consider_prior: bool | None = None
    prior_weight: float | None = None
    consider_magic_clip: bool | None = None
    consider_endpoints: bool | None = None
    n_startup_trials: int = 10
    n_ei_candidates: int = 24
    multivariate: bool = False
    group: bool = False
    warn_independent_sampling: bool | None = None
    constant_liar: bool = False
    constraints_func: Any | None = None


@dataclass
class RandomSamplerConfig(SamplerConfig):
    """
    https://optuna.readthedocs.io/en/stable/reference/generated/optuna.samplers.RandomSampler.html
    """

    _target_: str = "optuna.samplers.RandomSampler"
    seed: int | None = None


@dataclass
class CmaEsSamplerConfig(SamplerConfig):
    """
    https://optuna.readthedocs.io/en/stable/reference/generated/optuna.samplers.CmaEsSampler.html
    """

    _target_: str = "optuna.samplers.CmaEsSampler"
    seed: int | None = None

    x0: dict[str, Any] | None = None
    sigma0: float | None = None
    n_startup_trials: int = 1
    independent_sampler: Any | None = None
    warn_independent_sampling: bool = True
    consider_pruned_trials: bool = False
    restart_strategy: Any | None = None
    popsize: int | None = None
    inc_popsize: int = -1
    use_separable_cma: bool = False
    with_margin: bool = False
    lr_adapt: bool = False
    source_trials: Any | None = None


@dataclass
class NSGAIISamplerConfig(SamplerConfig):
    """
    https://optuna.readthedocs.io/en/stable/reference/generated/optuna.samplers.NSGAIISampler.html
    """

    _target_: str = "hydra_plugins.hydra_optuna_sweeper._impl.create_nsgaii_sampler"
    seed: int | None = None

    population_size: int = 50
    mutation_prob: float | None = None
    mutation: Any | None = None
    crossover: Any | None = None
    crossover_prob: float = 0.9
    swapping_prob: float = 0.5
    constraints_func: Any | None = None


@dataclass
class NSGAIIISamplerConfig(SamplerConfig):
    """
    https://optuna.readthedocs.io/en/v4.9.0/reference/samplers/generated/optuna.samplers.NSGAIIISampler.html
    """

    _target_: str = "hydra_plugins.hydra_optuna_sweeper._impl.create_nsgaiii_sampler"
    seed: int | None = None

    population_size: int = 50
    mutation_prob: float | None = None
    mutation: Any | None = None
    crossover: Any | None = None
    crossover_prob: float = 0.9
    swapping_prob: float = 0.5
    constraints_func: Any | None = None
    reference_points: list[list[float]] | None = None
    dividing_parameter: int = 3


@dataclass
class MOTPESamplerConfig(SamplerConfig):
    _target_: str = "hydra_plugins.hydra_optuna_sweeper.config.raise_motpe_removed"


@dataclass
class GPSamplerConfig(SamplerConfig):
    """
    https://optuna.readthedocs.io/en/stable/reference/samplers/generated/optuna.samplers.GPSampler.html
    """

    _target_: str = "optuna.samplers.GPSampler"
    seed: int | None = None

    independent_sampler: Any | None = None
    n_startup_trials: int = 10
    deterministic_objective: bool = False
    constraints_func: Any | None = None
    warn_independent_sampling: bool = True


@dataclass
class QMCSamplerConfig(SamplerConfig):
    """
    https://optuna.readthedocs.io/en/stable/reference/samplers/generated/optuna.samplers.QMCSampler.html
    """

    _target_: str = "optuna.samplers.QMCSampler"
    seed: int | None = None

    qmc_type: str = "sobol"
    scramble: bool = False
    independent_sampler: Any | None = None
    warn_asynchronous_seeding: bool = True
    warn_independent_sampling: bool = True


defaults = [{"sampler": "tpe"}]


@dataclass
class OptunaSweeperConf:
    _target_: str = "hydra_plugins.hydra_optuna_sweeper.optuna_sweeper.OptunaSweeper"
    defaults: list[Any] = field(default_factory=lambda: defaults)

    # Sampling algorithm
    # Please refer to the reference for further details
    # https://optuna.readthedocs.io/en/stable/reference/samplers.html
    sampler: SamplerConfig = MISSING

    # Direction of optimization
    # Union[Direction, List[Direction]]
    direction: Any = Direction.minimize

    # Storage URL to persist optimization results
    # For example, you can use SQLite if you set 'sqlite:///example.db'
    # Please refer to the reference for further details
    # https://optuna.readthedocs.io/en/stable/reference/storages.html
    storage: Any | None = None

    # Name of study to persist optimization results
    study_name: str | None = None

    # Total number of function evaluations
    n_trials: int = 20

    # Number of parallel workers
    n_jobs: int = 2

    # Maximum authorized failure rate for a batch of parameters
    max_failure_rate: float = 0.0

    params: dict[str, str] | None = None

    # Allow custom trial configuration via Python methods.
    # If given, `custom_search_space` should be a an instantiate-style dotpath targeting
    # a callable with signature Callable[[DictConfig, optuna.trial.Trial], None].
    # https://optuna.readthedocs.io/en/stable/tutorial/10_key_features/002_configurations.html
    custom_search_space: str | None = None


ConfigStore.instance().store(
    group="hydra/sweeper",
    name="optuna",
    node=OptunaSweeperConf,
    provider="optuna_sweeper",
)

ConfigStore.instance().store(
    group="hydra/sweeper/sampler",
    name="tpe",
    node=TPESamplerConfig,
    provider="optuna_sweeper",
)

ConfigStore.instance().store(
    group="hydra/sweeper/sampler",
    name="random",
    node=RandomSamplerConfig,
    provider="optuna_sweeper",
)

ConfigStore.instance().store(
    group="hydra/sweeper/sampler",
    name="cmaes",
    node=CmaEsSamplerConfig,
    provider="optuna_sweeper",
)

ConfigStore.instance().store(
    group="hydra/sweeper/sampler",
    name="nsgaii",
    node=NSGAIISamplerConfig,
    provider="optuna_sweeper",
)

ConfigStore.instance().store(
    group="hydra/sweeper/sampler",
    name="nsgaiii",
    node=NSGAIIISamplerConfig,
    provider="optuna_sweeper",
)

ConfigStore.instance().store(
    group="hydra/sweeper/sampler",
    name="motpe",
    node=MOTPESamplerConfig,
    provider="optuna_sweeper",
)

ConfigStore.instance().store(
    group="hydra/sweeper/sampler",
    name="grid",
    node=GridSamplerConfig,
    provider="optuna_sweeper",
)

ConfigStore.instance().store(
    group="hydra/sweeper/sampler",
    name="gp",
    node=GPSamplerConfig,
    provider="optuna_sweeper",
)

ConfigStore.instance().store(
    group="hydra/sweeper/sampler",
    name="qmc",
    node=QMCSamplerConfig,
    provider="optuna_sweeper",
)

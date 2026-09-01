# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, NoReturn, Optional

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


@dataclass
class TPESamplerConfig(SamplerConfig):
    """
    https://optuna.readthedocs.io/en/stable/reference/generated/optuna.samplers.TPESampler.html
    """

    _target_: str = "optuna.samplers.TPESampler"
    seed: Optional[int] = None

    consider_prior: Optional[bool] = None
    prior_weight: Optional[float] = None
    consider_magic_clip: Optional[bool] = None
    consider_endpoints: Optional[bool] = None
    n_startup_trials: int = 10
    n_ei_candidates: int = 24
    multivariate: bool = False
    warn_independent_sampling: Optional[bool] = None


@dataclass
class RandomSamplerConfig(SamplerConfig):
    """
    https://optuna.readthedocs.io/en/stable/reference/generated/optuna.samplers.RandomSampler.html
    """

    _target_: str = "optuna.samplers.RandomSampler"
    seed: Optional[int] = None


@dataclass
class CmaEsSamplerConfig(SamplerConfig):
    """
    https://optuna.readthedocs.io/en/stable/reference/generated/optuna.samplers.CmaEsSampler.html
    """

    _target_: str = "optuna.samplers.CmaEsSampler"
    seed: Optional[int] = None

    x0: Optional[Dict[str, Any]] = None
    sigma0: Optional[float] = None
    independent_sampler: Optional[Any] = None
    warn_independent_sampling: bool = True
    consider_pruned_trials: bool = False
    restart_strategy: Optional[Any] = None
    inc_popsize: int = 2
    use_separable_cma: bool = False
    source_trials: Optional[Any] = None


@dataclass
class NSGAIISamplerConfig(SamplerConfig):
    """
    https://optuna.readthedocs.io/en/stable/reference/generated/optuna.samplers.NSGAIISampler.html
    """

    _target_: str = "optuna.samplers.NSGAIISampler"
    seed: Optional[int] = None

    population_size: int = 50
    mutation_prob: Optional[float] = None
    crossover_prob: float = 0.9
    swapping_prob: float = 0.5
    constraints_func: Optional[Any] = None


@dataclass
class NSGAIIISamplerConfig(SamplerConfig):
    """
    https://optuna.readthedocs.io/en/v4.9.0/reference/samplers/generated/optuna.samplers.NSGAIIISampler.html
    """

    _target_: str = "optuna.samplers.NSGAIIISampler"
    seed: Optional[int] = None

    population_size: int = 50
    mutation_prob: Optional[float] = None
    crossover: Optional[Any] = None
    crossover_prob: float = 0.9
    swapping_prob: float = 0.5
    constraints_func: Optional[Any] = None
    reference_points: Optional[List[List[float]]] = None
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
    seed: Optional[int] = None

    independent_sampler: Optional[Any] = None
    n_startup_trials: int = 10
    deterministic_objective: bool = False
    constraints_func: Optional[Any] = None
    warn_independent_sampling: bool = True


@dataclass
class QMCSamplerConfig(SamplerConfig):
    """
    https://optuna.readthedocs.io/en/stable/reference/samplers/generated/optuna.samplers.QMCSampler.html
    """

    _target_: str = "optuna.samplers.QMCSampler"
    seed: Optional[int] = None

    qmc_type: str = "sobol"
    scramble: bool = False
    independent_sampler: Optional[Any] = None
    warn_asynchronous_seeding: bool = True
    warn_independent_sampling: bool = True


defaults = [{"sampler": "tpe"}]


@dataclass
class OptunaSweeperConf:
    _target_: str = "hydra_plugins.hydra_optuna_sweeper.optuna_sweeper.OptunaSweeper"
    defaults: List[Any] = field(default_factory=lambda: defaults)

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
    storage: Optional[Any] = None

    # Name of study to persist optimization results
    study_name: Optional[str] = None

    # Total number of function evaluations
    n_trials: int = 20

    # Number of parallel workers
    n_jobs: int = 2

    # Maximum authorized failure rate for a batch of parameters
    max_failure_rate: float = 0.0

    params: Optional[Dict[str, str]] = None

    # Allow custom trial configuration via Python methods.
    # If given, `custom_search_space` should be a an instantiate-style dotpath targeting
    # a callable with signature Callable[[DictConfig, optuna.trial.Trial], None].
    # https://optuna.readthedocs.io/en/stable/tutorial/10_key_features/002_configurations.html
    custom_search_space: Optional[str] = None


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

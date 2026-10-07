# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved
from dataclasses import dataclass, field
from typing import Any

from hydra.core.config_store import ConfigStore


@dataclass
class ScalarConfigSpec:
    """Representation of all the options to define
    a scalar.
    """

    # lower bound if any
    lower: float | None = None

    # upper bound if any
    upper: float | None = None

    # initial value
    # default to the middle point if completely bounded
    init: float | None = None

    # step size for an update
    # defaults to 1 if unbounded
    # or 1/6 of the range if completely bounded
    step: float | None = None

    # cast to integer
    integer: bool = False

    # logarithmically distributed
    log: bool = False


@dataclass
class OptimConf:
    # name of the Nevergrad optimizer to use. Here is a sample:
    #   - "OnePlusOne" extremely simple and robust, especially at low budget, but
    #     tends to converge early.
    #   - "CMA" very good algorithm, but may require a significant budget (> 120)
    #   - "TwoPointsDE": an algorithm good in a wide range of settings, for significant
    #     budgets (> 120).
    #   - "NGOpt" an algorithm aiming at identifying the best optimizer given your input
    #     definition (updated regularly)
    # find out more within nevergrad's documentation:
    # https://github.com/facebookresearch/nevergrad/
    optimizer: str = "NGOpt"

    # total number of function evaluations to perform
    budget: int = 80

    # number of parallel workers for performing function evaluations
    num_workers: int = 10

    # set to true if the function evaluations are noisy
    noisy: bool = False

    # set to true for performing maximization instead of minimization
    maximize: bool = False

    # optimization seed, for reproducibility
    seed: int | None = None

    # maximum authorized failure rate for a batch of parameters
    max_failure_rate: float = 0.0


@dataclass
class NevergradSweeperConf:
    _target_: str = (
        "hydra_plugins.hydra_nevergrad_sweeper.nevergrad_sweeper.NevergradSweeper"
    )

    # configuration of the optimizer
    optim: OptimConf = field(default_factory=OptimConf)

    # Deprecated search-space configuration.
    parametrization: dict[str, Any] | None = None

    # Search-space configuration using Hydra's override grammar.
    params: dict[str, Any] | None = None


ConfigStore.instance().store(
    group="hydra/sweeper",
    name="nevergrad",
    node=NevergradSweeperConf,
    provider="nevergrad",
    replace=True,
)

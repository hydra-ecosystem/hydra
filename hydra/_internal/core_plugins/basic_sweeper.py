# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved

"""
Basic sweeper can generate cartesian products of multiple input commands, each with a
comma separated list of values.
for example, for:
python foo.py a=1,2,3 b=10,20
Basic Sweeper would generate 6 jobs:
1,10
1,20
2,10
2,20
3,10
3,20

The Basic Sweeper also support, the following is equivalent to the above.
python foo.py a=range(1,4) b=10,20
"""

import itertools
import logging
import time
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

from omegaconf import DictConfig, OmegaConf

from hydra.core.config_store import ConfigStore
from hydra.core.override_parser.overrides_parser import OverridesParser
from hydra.core.override_parser.types import Override
from hydra.core.utils import JobReturn
from hydra.errors import HydraException
from hydra.plugins.launcher import Launcher
from hydra.plugins.sweeper import Sweeper
from hydra.types import HydraContext, TaskFunction


@dataclass
class BasicSweeperConf:
    _target_: str = "hydra._internal.core_plugins.basic_sweeper.BasicSweeper"
    max_batch_size: int | None = None
    params: dict[str, str] | None = None


ConfigStore.instance().store(
    group="hydra/sweeper",
    name="basic",
    node=BasicSweeperConf,
    provider="hydra",
    replace=True,
)


log = logging.getLogger(__name__)


class BasicSweeper(Sweeper):
    """
    Basic sweeper
    """

    def __init__(
        self, max_batch_size: int | None, params: dict[str, str] | None = None
    ) -> None:
        """
        Instantiates
        """
        super().__init__()

        if params is None:
            params = {}
        self.overrides: Sequence[Sequence[Sequence[str]]] | None = None
        self.batch_index = 0
        self.max_batch_size = max_batch_size
        self.params = params

        self.hydra_context: HydraContext | None = None
        self.config: DictConfig | None = None
        self.launcher: Launcher | None = None

    def setup(
        self,
        *,
        hydra_context: HydraContext,
        task_function: TaskFunction,
        config: DictConfig,
    ) -> None:
        from hydra.core.plugins import Plugins

        self.hydra_context = hydra_context
        self.config = config

        self.launcher = Plugins.instance().instantiate_launcher(
            hydra_context=hydra_context,
            task_function=task_function,
            config=config,
        )

    @staticmethod
    def split_overrides_to_chunks(
        lst: list[list[str]], n: int | None
    ) -> Iterable[list[list[str]]]:
        if n is None or n == -1:
            n = len(lst)
        assert n > 0
        for i in range(0, len(lst), n):
            yield lst[i : i + n]

    @staticmethod
    def split_arguments(
        overrides: list[Override], max_batch_size: int | None
    ) -> list[list[list[str]]]:
        lists = []
        final_overrides = OrderedDict()
        for override in overrides:
            if override.is_sweep_override():
                if override.is_discrete_sweep():
                    key = override.get_key_element()
                    sweep = [f"{key}={val}" for val in override.sweep_string_iterator()]
                    final_overrides[key] = sweep
                else:
                    assert override.value_type is not None
                    raise HydraException(
                        f"{BasicSweeper.__name__} does not support sweep type : {override.value_type.name}"
                    )
            else:
                key = override.get_key_element()
                value = override.get_value_element_as_str()
                final_overrides[key] = [f"{key}={value}"]

        for _, v in final_overrides.items():
            lists.append(v)

        all_batches = [list(x) for x in itertools.product(*lists)]
        assert max_batch_size is None or max_batch_size > 0
        if max_batch_size is None:
            return [all_batches]
        else:
            chunks_iter = BasicSweeper.split_overrides_to_chunks(
                all_batches, max_batch_size
            )
            return [x for x in chunks_iter]

    def _parse_config(self) -> list[str]:
        params_conf = []
        for k, v in self.params.items():
            params_conf.append(f"{k}={v}")
        return params_conf

    def sweep(self, arguments: list[str]) -> Any:
        assert self.config is not None
        assert self.launcher is not None
        assert self.hydra_context is not None

        params_conf = self._parse_config()
        params_conf.extend(arguments)

        parser = OverridesParser.create(config_loader=self.hydra_context.config_loader)
        overrides = parser.parse_overrides(params_conf)

        self.overrides = self.split_arguments(overrides, self.max_batch_size)
        returns: list[Sequence[JobReturn]] = []

        # Save sweep run config in top level sweep working directory
        sweep_dir = Path(self.config.hydra.sweep.dir)
        sweep_dir.mkdir(parents=True, exist_ok=True)
        OmegaConf.save(self.config, sweep_dir / "multirun.yaml")

        initial_job_idx = 0
        while not self.is_done():
            batch = self.get_job_batch()
            tic = time.perf_counter()
            # Validate that jobs can be safely composed. This catches composition errors early.
            # This can be a bit slow for large jobs. can potentially allow disabling from the config.
            self.validate_batch_is_legal(batch)
            elapsed = time.perf_counter() - tic
            log.debug(
                f"Validated configs of {len(batch)} jobs in {elapsed:0.2f} seconds, "
                f"{len(batch) / elapsed:.2f} / second)"
            )
            results = self.launcher.launch(batch, initial_job_idx=initial_job_idx)

            for r in results:
                # access the result to trigger an exception in case the job failed.
                _ = r.return_value

            initial_job_idx += len(batch)
            returns.append(results)

        return returns

    def get_job_batch(self) -> Sequence[Sequence[str]]:
        """
        :return: A list of lists of strings, each inner list is the overrides for a single job
        that should be executed.
        """
        assert self.overrides is not None
        self.batch_index += 1
        return self.overrides[self.batch_index - 1]

    def is_done(self) -> bool:
        assert self.overrides is not None
        return self.batch_index >= len(self.overrides)

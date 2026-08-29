# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved

import logging
from typing import Any

from omegaconf import DictConfig, OmegaConf

import hydra
from hydra.core.utils import JobReturn
from hydra.experimental.callback import Callback
from hydra.utils import execution_whitelist

log = logging.getLogger(__name__)


class CustomCallback(Callback):
    def __init__(self, callback_name: str) -> None:
        self.name = callback_name
        log.info(f"Init {self.name}")

    def on_job_start(self, config: DictConfig, **kwargs: Any) -> None:
        log.info(f"{self.name} on_job_start")

    def on_job_end(
        self, config: DictConfig, job_return: JobReturn, **kwargs: Any
    ) -> None:
        log.info(f"{self.name} on_job_end")

    def on_run_start(self, config: DictConfig, **kwargs: Any) -> None:
        log.info(f"{self.name} on_run_start")

    def on_run_end(self, config: DictConfig, **kwargs: Any) -> None:
        log.info(f"{self.name} on_run_end")

    def on_multirun_start(self, config: DictConfig, **kwargs: Any) -> None:
        log.info(f"{self.name} on_multirun_start")

    def on_multirun_end(self, config: DictConfig, **kwargs: Any) -> None:
        log.info(f"{self.name} on_multirun_end")


@hydra.main(config_path=".", config_name="config")
def my_app(cfg: DictConfig) -> None:
    log.info(OmegaConf.to_yaml(cfg))


if __name__ == "__main__":
    with execution_whitelist("my_app.*"):
        my_app()

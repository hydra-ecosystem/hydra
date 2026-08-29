# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved

import logging
from typing import Any

from omegaconf import DictConfig

import hydra
from hydra.experimental.callback import Callback
from hydra.types import TaskFunction
from hydra.utils import execution_whitelist

log = logging.getLogger(__name__)


class OnJobStartCallback(Callback):
    def on_job_start(
        self, config: DictConfig, *, task_function: TaskFunction, **kwargs: Any
    ) -> None:
        assert task_function(...) == "called my_app"
        log.info(f"on_job_start task_function: {task_function}")


@hydra.main(config_path=".", config_name="config")
def my_app(cfg: DictConfig) -> Any:
    return "called my_app"


if __name__ == "__main__":
    with execution_whitelist("my_app.*"):
        my_app()

# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved

import logging

from omegaconf import DictConfig

import hydra
from hydra.core.hydra_config import HydraConfig

log = logging.getLogger(__name__)


@hydra.main(config_path=".", config_name="config")
def my_app(cfg: DictConfig) -> None:
    log.info(f"Output_dir={HydraConfig.get().runtime.output_dir}")
    log.info(f"cfg.foo={cfg.foo}")


if __name__ == "__main__":
    my_app()

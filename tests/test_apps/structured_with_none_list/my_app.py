# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved
import builtins
from dataclasses import dataclass

from omegaconf import DictConfig

import hydra
from hydra.core.config_store import ConfigStore


@dataclass
class Config:
    list: builtins.list[int] | None = None


cs = ConfigStore.instance()
cs.store(name="config", node=Config)


@hydra.main(config_name="config")
def main(cfg: DictConfig) -> None:
    print(cfg)


if __name__ == "__main__":
    main()

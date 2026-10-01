# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved
from dataclasses import dataclass

from omegaconf import MISSING

import hydra
from hydra.core.config_store import ConfigStore
from hydra.core.hydra_config import HydraConfig


@dataclass
class Config:
    age: int = MISSING
    name: str = MISSING
    group: dict[str, str] = MISSING


ConfigStore.instance().store(name="config_schema", node=Config)


@hydra.main(config_path=".", config_name="config")
def my_app(cfg: Config) -> None:
    print(
        f"job_name: {HydraConfig().get().job.name}, "
        f"name: {cfg.name}, age: {cfg.age}, group: {cfg.group['name']}"
    )


if __name__ == "__main__":
    my_app()

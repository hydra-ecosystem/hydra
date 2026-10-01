# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved
from dataclasses import dataclass
from typing import Any

from omegaconf import MISSING, DictConfig, OmegaConf

import hydra
from hydra.core.config_store import ConfigStore


@dataclass
class DBConfig:
    driver: str = MISSING
    host: str = "localhost"
    port: int = MISSING


@dataclass
class MySQLConfig(DBConfig):
    driver: str = "mysql"
    port: int = 3306
    user: str = MISSING
    password: str = MISSING


@dataclass
class Config:
    defaults: list[Any] = MISSING
    db: DBConfig = MISSING


cs = ConfigStore.instance()
cs.store(group="db", name="mysql", node=MySQLConfig, provider="main")
cs.store(name="config", node=Config, provider="main")


@hydra.main(config_path="conf", config_name="config")
def my_app(cfg: DictConfig) -> None:
    print(OmegaConf.to_yaml(cfg))


if __name__ == "__main__":
    my_app()

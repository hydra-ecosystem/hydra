# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved
from dataclasses import dataclass, field
from typing import Any

from omegaconf import MISSING, OmegaConf  # Do not confuse with dataclass.MISSING

import hydra
from hydra.core.config_store import ConfigStore


@dataclass
class MySQLConfig:
    driver: str = "mysql"
    host: str = "localhost"
    port: int = 3306
    user: str = "omry"
    password: str = "secret"


@dataclass
class PostGreSQLConfig:
    driver: str = "postgresql"
    host: str = "localhost"
    port: int = 5432
    timeout: int = 10
    user: str = "postgres_user"
    password: str = "drowssap"


defaults = [
    # config group name db will load config named mysql
    {"db": "mysql"}
]


@dataclass
class Config:
    # this is unfortunately verbose due to @dataclass limitations
    defaults: list[Any] = field(default_factory=lambda: defaults)

    # Hydra will populate this field based on the defaults list
    db: Any = MISSING


cs = ConfigStore.instance()
cs.store(group="db", name="mysql", node=MySQLConfig)
cs.store(group="db", name="postgresql", node=PostGreSQLConfig)
cs.store(name="config", node=Config)


@hydra.main(config_name="config")
def my_app(cfg: Config) -> None:
    print(OmegaConf.to_yaml(cfg))


if __name__ == "__main__":
    my_app()

# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved
from omegaconf import DictConfig

import hydra
from hydra.utils import execution_whitelist, instantiate


class DBConnection:
    def connect(self) -> None: ...


class MySQLConnection(DBConnection):
    def __init__(self, host: str, user: str, password: str) -> None:
        self.host = host
        self.user = user
        self.password = password

    def connect(self) -> None:
        print(f"MySQL connecting to {self.host}")


class PostgreSQLConnection(DBConnection):
    def __init__(self, host: str, user: str, password: str, database: str) -> None:
        self.host = host
        self.user = user
        self.password = password
        self.database = database

    def connect(self) -> None:
        print(f"PostgreSQL connecting to {self.host}")


@hydra.main(config_path="conf", config_name="config")
def my_app(cfg: DictConfig) -> None:
    with execution_whitelist("my_app.*"):
        connection = instantiate(cfg.db)
    connection.connect()


if __name__ == "__main__":
    my_app()

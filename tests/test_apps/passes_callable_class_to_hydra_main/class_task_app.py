# SPDX-FileCopyrightText: Contributors to Hydra
# SPDX-License-Identifier: MIT
from omegaconf import DictConfig

import hydra


class TaskClass:
    def __init__(self, cfg: DictConfig) -> None:
        raise ValueError("class task failed")


my_app = hydra.main()(TaskClass)

if __name__ == "__main__":
    my_app()

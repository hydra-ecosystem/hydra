# SPDX-FileCopyrightText: Contributors to Hydra
# SPDX-License-Identifier: MIT
import json
import os

from omegaconf import DictConfig, OmegaConf

import hydra


@hydra.main(config_path=".", config_name="config")
def my_app(cfg: DictConfig) -> None:
    print(
        json.dumps(
            {"config": OmegaConf.to_container(cfg, resolve=True), "cwd": os.getcwd()}
        )
    )


if __name__ == "__main__":
    my_app()

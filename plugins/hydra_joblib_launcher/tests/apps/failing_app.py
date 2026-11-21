# SPDX-FileCopyrightText: Contributors to Hydra
# SPDX-License-Identifier: MIT
import hydra
from omegaconf import DictConfig


@hydra.main(config_path=None)
def main(cfg: DictConfig) -> None:
    try:
        raise ValueError("joblib remote cause")
    except ValueError as cause:
        raise RuntimeError("joblib remote failure") from cause


if __name__ == "__main__":
    main()

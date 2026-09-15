# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved
import hydra
from omegaconf import DictConfig


@hydra.main(version_base=None)
def main(cfg: DictConfig) -> None:
    raise RuntimeError(f"submitit remote failure {cfg.job}")


if __name__ == "__main__":
    main()

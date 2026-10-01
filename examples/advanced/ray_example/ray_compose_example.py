# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved
import time

import ray
from omegaconf import DictConfig, OmegaConf

import hydra


@ray.remote  # type: ignore
def train(overrides: list[str], cfg: DictConfig) -> tuple[list[str], float]:
    print(OmegaConf.to_yaml(cfg))
    time.sleep(5)
    return overrides, 0.9


@hydra.main(config_path="conf", config_name="config")
def main(cfg: DictConfig) -> None:
    ray.init(**cfg.ray.init)

    results = []
    for model in ["alexnet", "resnet"]:
        for dataset in ["cifar10", "imagenet"]:
            overrides = [f"dataset={dataset}", f"model={model}"]
            run_cfg = hydra.compose(overrides=overrides)
            ret = train.remote(overrides, run_cfg)
            results.append(ret)

    for overrides, score in ray.get(results):
        print(f"Result from {overrides} : {score}")


if __name__ == "__main__":
    main()

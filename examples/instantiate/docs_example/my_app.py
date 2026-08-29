# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved

from omegaconf import DictConfig

import hydra
from hydra.utils import execution_whitelist, instantiate


class Optimizer:
    algo: str
    lr: float

    def __init__(self, algo: str, lr: float) -> None:
        self.algo = algo
        self.lr = lr

    def __repr__(self) -> str:
        return f"Optimizer(algo={self.algo},lr={self.lr})"


class Dataset:
    name: str
    path: str

    def __init__(self, name: str, path: str) -> None:
        self.name = name
        self.path = path

    def __repr__(self) -> str:
        return f"Dataset(name={self.name}, path={self.path})"


class Trainer:
    def __init__(self, optimizer: Optimizer, dataset: Dataset) -> None:
        self.optimizer = optimizer
        self.dataset = dataset

    def __repr__(self) -> str:
        return f"Trainer(\n  optimizer={self.optimizer},\n  dataset={self.dataset}\n)"


@hydra.main(config_path=".", config_name="config")
def my_app(cfg: DictConfig) -> None:
    with execution_whitelist("my_app.*"):
        optimizer = instantiate(cfg.trainer.optimizer)
        print(optimizer)
        # Optimizer(algo=SGD,lr=0.01)

        # override parameters on the call-site
        optimizer = instantiate(cfg.trainer.optimizer, lr=0.2)
        print(optimizer)
        # Optimizer(algo=SGD,lr=0.2)

        # recursive instantiation
        trainer = instantiate(cfg.trainer)
        print(trainer)
        # Trainer(
        #   optimizer=Optimizer(algo=SGD,lr=0.01),
        #   dataset=Dataset(name=Imagenet, path=/datasets/imagenet)
        # )

        # override nested parameters from the call-site
        trainer = instantiate(
            cfg.trainer,
            optimizer={"lr": 0.3},
            dataset={"name": "cifar10", "path": "/datasets/cifar10"},
        )
        print(trainer)
        # Trainer(
        #   optimizer=Optimizer(algo=SGD,lr=0.3),
        #   dataset=Dataset(name=cifar10, path=/datasets/cifar10)
        # )

        # non recursive instantiation
        trainer = instantiate(cfg.trainer, _recursive_=False)
        print(trainer)
        # Trainer(
        #     optimizer={'_target_': 'my_app.Optimizer', 'algo': 'SGD', 'lr': 0.01},
        #     dataset={'_target_': 'my_app.Dataset', 'name': 'Imagenet', 'path': '/datasets/imagenet'}
        # )


if __name__ == "__main__":
    my_app()

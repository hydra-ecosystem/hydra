# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved
from functools import partial

from omegaconf import DictConfig

import hydra


def task(self: object, cfg: DictConfig, value: int) -> None:
    print(value)


class PartialCallable:
    __call__ = partial(task, value=123)


my_app = hydra.main()(PartialCallable())

if __name__ == "__main__":
    my_app()

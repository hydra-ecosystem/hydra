# SPDX-FileCopyrightText: Contributors to Hydra
# SPDX-License-Identifier: MIT
from functools import partialmethod

from omegaconf import DictConfig

import hydra


class Inner:
    def __call__(self, outer: object, cfg: DictConfig) -> None:
        raise ValueError("nested partial failed")


class App:
    __call__ = partialmethod(Inner())


my_app = hydra.main()(App())

if __name__ == "__main__":
    my_app()

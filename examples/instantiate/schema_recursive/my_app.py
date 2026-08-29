# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved
from dataclasses import dataclass
from typing import Optional

from omegaconf import MISSING

import hydra
from hydra.core.config_store import ConfigStore
from hydra.utils import execution_whitelist, instantiate


class Tree:
    def __init__(
        self, value: int, left: Optional["Tree"] = None, right: Optional["Tree"] = None
    ) -> None:
        self.value = value
        self.left = left
        self.right = right


@dataclass
class TreeConf:
    _target_: str = "my_app.Tree"
    value: int = MISSING
    left: Optional["TreeConf"] = None
    right: Optional["TreeConf"] = None


# we will populate the tree from the config file with the matching name
@dataclass
class Config:
    tree: TreeConf = MISSING


cs = ConfigStore.instance()
cs.store(name="config_schema", node=Config)


# pretty print utility
def pretty_print(tree: Tree, name: str = "root", depth: int = 0) -> None:
    pad = " " * depth * 2
    print(f"{pad}{name}({tree.value})")
    if tree.left is not None:
        pretty_print(tree.left, name="left", depth=depth + 1)
    if tree.right is not None:
        pretty_print(tree.right, name="right", depth=depth + 1)


@hydra.main(config_path=".", config_name="config")
def my_app(cfg: Config) -> None:
    with execution_whitelist("my_app.*"):
        tree: Tree = instantiate(cfg.tree)
    pretty_print(tree)


if __name__ == "__main__":
    my_app()

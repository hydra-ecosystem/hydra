# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved
from typing import Any

from hydra._internal.hydra import Hydra
from hydra.core.config_loader import ConfigLoader
from hydra.core.singleton import Singleton


class GlobalHydra(metaclass=Singleton):
    def __init__(self) -> None:
        self.hydra: Hydra | None = None

    def initialize(self, hydra: "Hydra") -> None:
        assert isinstance(hydra, Hydra), f"Unexpected Hydra type : {type(hydra)}"
        if self.is_initialized():
            raise ValueError(
                "GlobalHydra is already initialized, call GlobalHydra.instance().clear() if you want to re-initialize"
            )
        self.hydra = hydra

    def config_loader(self) -> "ConfigLoader":
        assert self.hydra is not None
        return self.hydra.config_loader

    def is_initialized(self) -> bool:
        return self.hydra is not None

    def clear(self) -> None:
        self.hydra = None

    @staticmethod
    def instance(*args: Any, **kwargs: Any) -> "GlobalHydra":
        return Singleton.instance(GlobalHydra, *args, **kwargs)  # type: ignore

    @staticmethod
    def set_instance(instance: "GlobalHydra") -> None:
        assert isinstance(instance, GlobalHydra)
        Singleton._instances[GlobalHydra] = instance  # type: ignore

# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved
from typing import TYPE_CHECKING, Any

from hydra._internal.hydra import Hydra
from hydra.core.config_loader import ConfigLoader
from hydra.core.singleton import Singleton

if TYPE_CHECKING:
    from hydra._internal.authorization import _InitializationFrame


class GlobalHydra(metaclass=Singleton):
    def __init__(self) -> None:
        self.hydra: Hydra | None = None
        self._initialization_frame: _InitializationFrame | None = None

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
        frame = self._initialization_frame
        self._initialization_frame = None
        if frame is not None:
            frame.close()

    @staticmethod
    def instance(*args: Any, **kwargs: Any) -> "GlobalHydra":
        return Singleton.instance(GlobalHydra, *args, **kwargs)  # type: ignore

    @staticmethod
    def set_instance(instance: "GlobalHydra") -> None:
        assert isinstance(instance, GlobalHydra)
        Singleton._instances[GlobalHydra] = instance  # type: ignore

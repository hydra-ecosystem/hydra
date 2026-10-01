# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved
from typing import Any

from omegaconf import DictConfig, OmegaConf

from hydra.conf import HydraConf
from hydra.core.singleton import Singleton


class HydraConfig(metaclass=Singleton):
    def __init__(self) -> None:
        self.cfg: HydraConf | None = None

    def set_config(self, cfg: DictConfig) -> None:
        assert cfg is not None
        OmegaConf.set_readonly(cfg.hydra, True)
        hydra_node_type = OmegaConf.get_type(cfg, "hydra")
        assert hydra_node_type is not None and issubclass(hydra_node_type, HydraConf)
        # THis is emulating a node that is hidden.
        # It's quiet a hack but it will be much better once
        # https://github.com/omry/omegaconf/issues/280 is done
        # The motivation is that this allows for interpolations from the hydra node
        # into the user's config.
        self.cfg = OmegaConf.masked_copy(cfg, "hydra")  # type: ignore
        self.cfg.hydra._set_parent(cfg)  # type: ignore

    @staticmethod
    def get() -> HydraConf:
        instance = HydraConfig.instance()
        if instance.cfg is None:
            raise ValueError("HydraConfig was not set")
        return instance.cfg.hydra  # type: ignore

    @staticmethod
    def initialized() -> bool:
        instance = HydraConfig.instance()
        return instance.cfg is not None

    @staticmethod
    def instance(*args: Any, **kwargs: Any) -> "HydraConfig":
        return Singleton.instance(HydraConfig, *args, **kwargs)  # type: ignore

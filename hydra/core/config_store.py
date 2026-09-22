# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved
import copy
import warnings
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from omegaconf import DictConfig, OmegaConf

from hydra.core.object_type import ObjectType
from hydra.core.singleton import Singleton
from hydra.plugins.config_source import ConfigLoadError


class ConfigStoreWithProvider:
    def __init__(self, provider: str) -> None:
        self.provider = provider

    def __enter__(self) -> "ConfigStoreWithProvider":
        return self

    def store(
        self,
        name: str,
        node: Any,
        group: Optional[str] = None,
        package: Optional[str] = None,
        replace: Optional[bool] = None,
    ) -> None:
        ConfigStore.instance().store(
            group=group,
            name=name,
            node=node,
            package=package,
            provider=self.provider,
            replace=replace,
        )

    def __exit__(self, exc_type: Any, exc_value: Any, exc_traceback: Any) -> Any: ...


@dataclass
class ConfigNode:
    name: str
    node: DictConfig
    group: Optional[str]
    package: Optional[str]
    provider: Optional[str]


class ConfigStore(metaclass=Singleton):
    @staticmethod
    def instance(*args: Any, **kwargs: Any) -> "ConfigStore":
        return Singleton.instance(ConfigStore, *args, **kwargs)  # type: ignore

    repo: Dict[str, Any]

    def __init__(self) -> None:
        self.repo = {}

    def store(
        self,
        name: str,
        node: Any,
        group: Optional[str] = None,
        package: Optional[str] = None,
        provider: Optional[str] = None,
        replace: Optional[bool] = None,
    ) -> None:
        """
        Stores a config node into the repository
        :param name: config name
        :param node: config node, can be DictConfig, ListConfig,
            Structured configs and even dict and list
        :param group: config group, subgroup separator is '/',
            for example hydra/launcher
        :param package: Config node parent hierarchy.
            Child separator is '.', for example foo.bar.baz
        :param provider: the name of the module/app providing this config.
            Helps debugging.
        :param replace: what to do when a *different* config is already stored
            under the same group and name. True replaces it, False raises a
            ValueError. The default, None, replaces it and issues a UserWarning.
            Storing a config that equals the stored one is never a clobber:
            Hydra re-executes plugin modules on every plugin discovery pass, so
            their module level store() calls repeat by design.
        """
        # An empty string group is treated as a config without a config group.
        if group == "":
            group = None

        cur = self.repo
        if group is not None:
            for d in group.split("/"):
                if d not in cur:
                    cur[d] = {}
                cur = cur[d]

        if not name.endswith(".yaml"):
            name = f"{name}.yaml"
        assert isinstance(cur, dict)
        cfg = OmegaConf.structured(node)
        new = ConfigNode(
            name=name, node=cfg, group=group, package=package, provider=provider
        )

        if replace is not True and name in cur and cur[name] != new:
            full_name = name if group is None else f"{group}/{name}"
            msg = f"A different config is already stored at '{full_name}'"
            if replace is False:
                raise ValueError(msg)
            warnings.warn(
                f"{msg} and is being replaced. Pass replace=True to store() to"
                " silence this warning, or replace=False to raise a ValueError"
                " instead.",
                UserWarning,
                stacklevel=2,
            )

        cur[name] = new

    def load(self, config_path: str) -> ConfigNode:
        ret = self._load(config_path)

        # shallow copy to avoid changing the original stored ConfigNode
        ret = copy.copy(ret)
        assert isinstance(ret, ConfigNode)
        # copy to avoid mutations to config effecting subsequent calls
        ret.node = copy.deepcopy(ret.node)
        return ret

    def _load(self, config_path: str) -> ConfigNode:
        idx = config_path.rfind("/")
        if idx == -1:
            ret = self._open(config_path)
            if ret is None:
                raise ConfigLoadError(f"Structured config not found {config_path}")
            assert isinstance(ret, ConfigNode)
            return ret
        else:
            path = config_path[0:idx]
            name = config_path[idx + 1 :]
            d = self._open(path)
            if d is None or not isinstance(d, dict):
                raise ConfigLoadError(f"Structured config not found {config_path}")

            if name not in d:
                raise ConfigLoadError(
                    f"Structured config {name} not found in {config_path}"
                )

            ret = d[name]
            assert isinstance(ret, ConfigNode)
            return ret

    def get_type(self, path: str) -> ObjectType:
        d = self._open(path)
        if d is None:
            return ObjectType.NOT_FOUND
        if isinstance(d, dict):
            return ObjectType.GROUP
        else:
            return ObjectType.CONFIG

    def list(self, path: str) -> List[str]:
        d = self._open(path)
        if d is None:
            raise OSError(f"Path not found {path}")

        if not isinstance(d, dict):
            raise OSError(f"Path points to a file : {path}")

        return sorted(d.keys())

    def _open(self, path: str) -> Any:
        d: Any = self.repo
        for frag in path.split("/"):
            if frag == "":
                continue
            if frag in d:
                d = d[frag]
            else:
                return None
        return d

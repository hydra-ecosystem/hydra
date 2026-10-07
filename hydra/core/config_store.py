# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved
import builtins
import copy
from dataclasses import dataclass
from typing import Any

from omegaconf import DictConfig, OmegaConf

from hydra._internal.deprecation_warning import deprecation_warning
from hydra.core.object_type import ObjectType
from hydra.core.singleton import Singleton
from hydra.errors import Hydra15MigrationWarning
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
        group: str | None = None,
        package: str | None = None,
        replace: bool | None = None,
    ) -> None:
        ConfigStore.instance()._store(
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
    group: str | None
    package: str | None
    provider: str | None


class ConfigStore(metaclass=Singleton):
    @staticmethod
    def instance(*args: Any, **kwargs: Any) -> "ConfigStore":
        return Singleton.instance(ConfigStore, *args, **kwargs)  # type: ignore

    repo: dict[str, Any]

    def __init__(self) -> None:
        self.repo = {}

    def store(
        self,
        name: str,
        node: Any,
        group: str | None = None,
        package: str | None = None,
        provider: str | None = None,
        replace: bool | None = None,
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
        :param replace: On a collision, True replaces silently, False raises
            ValueError, and None warns and replaces (an error in Hydra 1.5).
        """
        self._store(
            name=name,
            node=node,
            group=group,
            package=package,
            provider=provider,
            replace=replace,
        )

    def _store(
        self,
        name: str,
        node: Any,
        group: str | None,
        package: str | None,
        provider: str | None,
        replace: bool | None,
    ) -> None:
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
        if name in cur and replace is not True:
            previous = cur[name]
            path = f"{group}/{name}" if group else name
            previous_provider = (
                previous.provider if isinstance(previous, ConfigNode) else None
            )
            message = (
                f"ConfigStore config '{path}' is already registered "
                f"(provider={previous_provider!r}); attempted registration has "
                f"provider={provider!r}. "
                "Use replace=True to replace it or replace=False to reject collisions."
            )
            if replace is False:
                raise ValueError(message)
            deprecation_warning(
                message + " Omitting replace warns and replaces in Hydra 1.4, "
                "but will raise an error in Hydra 1.5. "
                "See https://hydra.cc/docs/next/upgrades/1.3_to_1.4/config_store_collisions",
                stacklevel=3,
                category=Hydra15MigrationWarning,
            )
        cfg = OmegaConf.structured(node)
        cur[name] = ConfigNode(
            name=name, node=cfg, group=group, package=package, provider=provider
        )

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

    def list(self, path: str) -> builtins.list[str]:
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

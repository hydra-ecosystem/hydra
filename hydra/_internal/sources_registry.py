# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved
from typing import Any

from hydra.core.singleton import Singleton
from hydra.plugins.config_source import ConfigSource


class SourcesRegistry(metaclass=Singleton):
    types: dict[str, type[ConfigSource]]

    def __init__(self) -> None:
        self.types = {}

    def register(self, type_: type[ConfigSource]) -> None:
        scheme = type_.scheme()
        if scheme in self.types:
            if self.types[scheme].__name__ != type_.__name__:
                raise ValueError(
                    f"{scheme} is already registered with a different class"
                )
            else:
                # Do not replace existing ConfigSource
                return
        self.types[scheme] = type_

    def resolve(self, scheme: str) -> type[ConfigSource]:
        if scheme not in self.types:
            supported = ", ".join(sorted(self.types.keys()))
            raise ValueError(
                f"No config source registered for schema {scheme}, supported types : [{supported}]"
            )
        return self.types[scheme]

    @staticmethod
    def instance(*args: Any, **kwargs: Any) -> "SourcesRegistry":
        return Singleton.instance(SourcesRegistry, *args, **kwargs)  # type: ignore

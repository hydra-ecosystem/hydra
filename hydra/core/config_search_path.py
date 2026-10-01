# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import MutableSequence


class SearchPathElement:
    def __init__(self, provider: str, search_path: str):
        self.provider = provider
        self.path = search_path

    def __str__(self) -> str:
        return repr(self)

    def __repr__(self) -> str:
        return f"provider={self.provider}, path={self.path}"


@dataclass
class SearchPathQuery:
    """
    Used in append and prepend API
    """

    provider: str | None = None
    path: str | None = None


class ConfigSearchPath(ABC):
    @abstractmethod
    def get_path(self) -> MutableSequence[SearchPathElement]: ...

    @abstractmethod
    def append(
        self, provider: str, path: str, anchor: SearchPathQuery | None = None
    ) -> None:
        """
        Appends to the search path.
        Note, this currently only takes effect if called before the ConfigRepository is instantiated.

        :param provider: who is providing this search path, can be Hydra,
               the @hydra.main() function, or individual plugins or libraries.
        :param path: path element, can be a file system path or a package path (For example pkg://hydra.conf)
        :param anchor: Optional anchor query to append after
        """

    ...

    @abstractmethod
    def prepend(
        self,
        provider: str,
        path: str,
        anchor: SearchPathQuery | str | None = None,
    ) -> None:
        """
        Prepends to the search path.
        Note, this currently only takes effect if called before the ConfigRepository is instantiated.

        :param provider: who is providing this search path, can be Hydra,
               the @hydra.main() function, or individual plugins or libraries.
        :param path: path element, can be a file system path or a package path (For example pkg://hydra.conf)
        :param anchor: Optional anchor query to prepend before
        """

    ...

# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved
from typing import MutableSequence

from hydra.core.config_search_path import (
    ConfigSearchPath,
    SearchPathElement,
    SearchPathQuery,
)


class ConfigSearchPathImpl(ConfigSearchPath):
    config_search_path: list[SearchPathElement]

    def __init__(self) -> None:
        self.config_search_path = []

    def get_path(self) -> MutableSequence[SearchPathElement]:
        return self.config_search_path

    def find_last_match(self, reference: SearchPathQuery) -> int:
        return self.find_match(reference, reverse=True)

    def find_first_match(self, reference: SearchPathQuery) -> int:
        return self.find_match(reference, reverse=False)

    def find_match(self, reference: SearchPathQuery, reverse: bool) -> int:
        p = self.config_search_path
        if reverse:
            iterator = zip(reversed(range(len(p))), reversed(p))
        else:
            iterator = zip(range(len(p)), p)
        for idx, sp in iterator:
            has_prov = reference.provider is not None
            has_path = reference.path is not None
            if has_prov and has_path:
                if reference.provider == sp.provider and reference.path == sp.path:
                    return idx
            elif has_prov:
                if reference.provider == sp.provider:
                    return idx
            elif has_path:
                if reference.path == sp.path:
                    return idx
            else:
                assert False
        return -1

    def append(
        self, provider: str, path: str, anchor: SearchPathQuery | None = None
    ) -> None:
        if anchor is None:
            self.config_search_path.append(SearchPathElement(provider, path))
        else:
            if isinstance(anchor, str):
                anchor = SearchPathQuery(anchor, None)

            idx = self.find_last_match(anchor)
            if idx != -1:
                self.config_search_path.insert(
                    idx + 1, SearchPathElement(provider, path)
                )
            else:
                self.append(provider, path, anchor=None)

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
        :param anchor: if string, acts as provider. if SearchPath can be used to match against provider and / or path
        """
        if anchor is None:
            self.config_search_path.insert(0, SearchPathElement(provider, path))
        else:
            if isinstance(anchor, str):
                anchor = SearchPathQuery(anchor, None)

            idx = self.find_first_match(anchor)
            if idx != -1:
                if idx > 0:
                    self.config_search_path.insert(
                        idx, SearchPathElement(provider, path)
                    )
                else:
                    self.prepend(provider, path, None)
            else:
                self.prepend(provider, path, None)

    def __str__(self) -> str:
        return str(self.config_search_path)

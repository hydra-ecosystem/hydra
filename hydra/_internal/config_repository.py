# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved
import copy
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from omegaconf import (
    Container,
    DictConfig,
    ListConfig,
    Node,
    OmegaConf,
    open_dict,
    read_write,
)

from hydra.core.config_search_path import ConfigSearchPath
from hydra.core.object_type import ObjectType
from hydra.plugins.config_source import ConfigResult, ConfigSource

from ..core.default_element import ConfigDefault, GroupDefault, InputDefault
from .sources_registry import SourcesRegistry


class IConfigRepository(ABC):
    @abstractmethod
    def get_schema_source(self) -> ConfigSource: ...

    @abstractmethod
    def load_config(self, config_path: str) -> Optional[ConfigResult]: ...

    @abstractmethod
    def group_exists(self, config_path: str) -> bool: ...

    @abstractmethod
    def config_exists(self, config_path: str) -> bool: ...

    @abstractmethod
    def get_group_options(
        self, group_name: str, results_filter: Optional[ObjectType] = ObjectType.CONFIG
    ) -> List[str]: ...

    @abstractmethod
    def get_sources(self) -> List[ConfigSource]: ...

    @abstractmethod
    def initialize_sources(self, config_search_path: ConfigSearchPath) -> None: ...


class ConfigRepository(IConfigRepository):
    _KNOWN_DEFAULTS_LIST_KEYWORDS = ("optional", "override")

    config_search_path: ConfigSearchPath
    sources: List[ConfigSource]

    def __init__(self, config_search_path: ConfigSearchPath) -> None:
        self.initialize_sources(config_search_path)

    def initialize_sources(self, config_search_path: ConfigSearchPath) -> None:
        self.sources = []
        for search_path in config_search_path.get_path():
            assert search_path.path is not None
            assert search_path.provider is not None
            scheme = self._get_scheme(search_path.path)
            source_type = SourcesRegistry.instance().resolve(scheme)
            source = source_type(search_path.provider, search_path.path)
            self.sources.append(source)

    def get_schema_source(self) -> ConfigSource:
        source = self.sources[-1]  # should always be last
        assert (
            source.__class__.__name__ == "StructuredConfigSource"
            and source.provider == "schema"
        ), "schema config source must be last"
        return source

    def load_config(self, config_path: str) -> Optional[ConfigResult]:
        source = self._find_object_source(
            config_path=config_path, object_type=ObjectType.CONFIG
        )
        ret = None
        if source is not None:
            ret = source.load_config(config_path=config_path)
            # if this source is THE schema source, flag the result as coming from it.
            ret.is_schema_source = (
                source.__class__.__name__ == "StructuredConfigSource"
                and source.provider == "schema"
            )

        if ret is not None:
            raw_defaults = self._extract_defaults_list(config_path, ret.config)
            ret.defaults_list = self._create_defaults_list(config_path, raw_defaults)

        return ret

    def group_exists(self, config_path: str) -> bool:
        return self._find_object_source(config_path, ObjectType.GROUP) is not None

    def config_exists(self, config_path: str) -> bool:
        return self._find_object_source(config_path, ObjectType.CONFIG) is not None

    def get_group_options(
        self, group_name: str, results_filter: Optional[ObjectType] = ObjectType.CONFIG
    ) -> List[str]:
        options: List[str] = []
        for source in self.sources:
            if source.is_group(config_path=group_name):
                options.extend(
                    source.list(config_path=group_name, results_filter=results_filter)
                )
        return sorted(list(set(options)))

    def get_sources(self) -> List[ConfigSource]:
        return self.sources

    def _find_object_source(
        self, config_path: str, object_type: Optional[ObjectType]
    ) -> Optional[ConfigSource]:
        found_source = None
        for source in self.sources:
            if object_type == ObjectType.CONFIG:
                if source.is_config(config_path):
                    found_source = source
                    break
            elif object_type == ObjectType.GROUP:
                if source.is_group(config_path):
                    found_source = source
                    break
            else:
                raise ValueError("Unexpected object_type")
        return found_source

    @staticmethod
    def _get_scheme(path: str) -> str:
        idx = path.find("://")
        if idx == -1:
            return "file"
        else:
            return path[0:idx]

    def _split_group(
        self,
        group_with_package: str,
    ) -> Tuple[str, Optional[str], Optional[str]]:
        idx = group_with_package.find("@")
        if idx == -1:
            # group
            group = group_with_package
            package = None
        else:
            # group@package
            group = group_with_package[0:idx]
            package = group_with_package[idx + 1 :]

        package2 = None
        if package is not None:
            # if we have a package, break it down if it's a rename
            idx = package.find(":")
            if idx != -1:
                package2 = package[idx + 1 :]
                package = package[0:idx]

        return group, package, package2

    def _create_defaults_list(
        self,
        config_path: str,
        defaults: ListConfig,
    ) -> List[InputDefault]:
        res: List[InputDefault] = []
        for item in defaults._iter_ex(resolve=False):
            default: InputDefault
            if isinstance(item, DictConfig):
                keys = list(item.keys())

                if len(keys) > 1:
                    raise ValueError(
                        f"In {config_path}: Too many keys in default item {item}"
                    )
                if len(keys) == 0:
                    raise ValueError(f"In {config_path}: Missing group name in {item}")

                key = keys[0]
                assert isinstance(key, str)
                config_group, package, _package2 = self._split_group(key)
                keywords = ConfigRepository.Keywords()
                self._extract_keywords_from_config_group(
                    config_path, config_group, keywords
                )

                node = item._get_node(key)
                assert node is not None and isinstance(node, Node)
                config_value = node._value()

                if config_value is not None and not isinstance(
                    config_value, (str, list)
                ):
                    raise ValueError(
                        f"Unsupported item value in defaults : {type(config_value).__name__}."
                        " Supported: string or list"
                    )

                if isinstance(config_value, list):
                    options = []
                    for v in config_value:
                        vv = v._value()
                        if not isinstance(vv, str):
                            raise ValueError(
                                f"Unsupported item value in defaults : {type(vv).__name__},"
                                " nested list items must be strings"
                            )
                        options.append(vv)
                    config_value = options

                normalized_shorthand = False
                original_group = None
                if (
                    isinstance(config_value, str)
                    and "/" in config_value
                    and ".." not in config_value.split("/")
                    and "${" not in config_value
                    and config_value != "???"
                ):
                    original_group = keywords.group
                    group_suffix, option_name = config_value.rsplit("/", 1)
                    keywords.group = f"{keywords.group}/{group_suffix}"
                    config_value = option_name
                    normalized_shorthand = True

                default = GroupDefault(
                    group=keywords.group,
                    value=config_value,
                    package=package,
                    optional=keywords.optional,
                    override=keywords.override,
                )
                default.normalized_shorthand = normalized_shorthand
                default.original_group = original_group

            elif isinstance(item, str):
                path, package, _package2 = self._split_group(item)
                default = ConfigDefault(path=path, package=package)
            else:
                raise ValueError(
                    f"Unsupported type in defaults : {type(item).__name__}"
                )
            res.append(default)
        return res

    def _extract_defaults_list(self, config_path: str, cfg: Container) -> ListConfig:
        empty = OmegaConf.create([])
        if not OmegaConf.is_dict(cfg):
            return empty
        assert isinstance(cfg, DictConfig)
        with read_write(cfg):
            with open_dict(cfg):
                if not cfg._is_typed():
                    defaults = cfg.pop("defaults", empty)
                else:
                    # If node is a backed by Structured Config, flag it and temporarily keep the defaults list in.
                    # It will be removed later.
                    # This is addressing an edge case where the defaults list re-appears once the dataclass is used
                    # as a prototype during OmegaConf merge.
                    cfg._set_flag("HYDRA_REMOVE_TOP_LEVEL_DEFAULTS", True)
                    defaults = cfg.get("defaults", empty)
        if not isinstance(defaults, ListConfig):
            if isinstance(defaults, DictConfig):
                type_str = "mapping"
            else:
                type_str = type(defaults).__name__
            raise ValueError(
                f"Invalid defaults list in '{config_path}', defaults must be a list (got {type_str})"
            )

        return defaults

    @dataclass
    class Keywords:
        optional: bool = False
        override: bool = False
        group: str = ""

    @staticmethod
    def _extract_keywords_from_config_group(
        config_path: str, group: str, keywords: "ConfigRepository.Keywords"
    ) -> None:
        elements = group.split()
        if not elements:
            raise ValueError(f"In {config_path}: Missing group name in defaults list")
        group = elements[-1]
        elements = elements[0:-1]
        for keyword in elements:
            if keyword not in ConfigRepository._KNOWN_DEFAULTS_LIST_KEYWORDS:
                raise ValueError(
                    f"In {config_path}: Unsupported keyword '{keyword}' in defaults list"
                )
            if keyword == "optional":
                keywords.optional = True
            elif keyword == "override":
                keywords.override = True
        if keywords.optional and keywords.override:
            raise ValueError(
                f"In {config_path}: 'optional' and 'override' keywords "
                "cannot be combined in defaults list"
            )
        keywords.group = group


class CachingConfigRepository(IConfigRepository):
    def __init__(self, delegate: IConfigRepository):
        # copy the underlying repository to avoid mutating it with initialize_sources()
        self.delegate = copy.deepcopy(delegate)
        self.cache: Dict[str, Optional[ConfigResult]] = {}

    def get_schema_source(self) -> ConfigSource:
        return self.delegate.get_schema_source()

    def initialize_sources(self, config_search_path: ConfigSearchPath) -> None:
        self.delegate.initialize_sources(config_search_path)
        # not clearing the cache.
        # For the use case this is used, the only thing in the cache is the primary config
        # and we want to keep it even though we re-initialized the sources.

    def load_config(self, config_path: str) -> Optional[ConfigResult]:
        cache_key = f"config_path={config_path}"
        if cache_key in self.cache:
            return self.cache[cache_key]
        else:
            ret = self.delegate.load_config(config_path=config_path)
            self.cache[cache_key] = ret
            return ret

    def group_exists(self, config_path: str) -> bool:
        return self.delegate.group_exists(config_path=config_path)

    def config_exists(self, config_path: str) -> bool:
        return self.delegate.config_exists(config_path=config_path)

    def get_group_options(
        self, group_name: str, results_filter: Optional[ObjectType] = ObjectType.CONFIG
    ) -> List[str]:
        return self.delegate.get_group_options(
            group_name=group_name, results_filter=results_filter
        )

    def get_sources(self) -> List[ConfigSource]:
        return self.delegate.get_sources()

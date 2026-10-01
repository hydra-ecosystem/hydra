# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved
import builtins
import re
from abc import abstractmethod
from dataclasses import dataclass

from omegaconf import Container

from hydra.core.default_element import InputDefault
from hydra.core.object_type import ObjectType
from hydra.errors import HydraException
from hydra.plugins.plugin import Plugin


@dataclass
class ConfigResult:
    provider: str
    path: str
    config: Container
    header: dict[str, str | None]
    defaults_list: list[InputDefault] | None = None
    is_schema_source: bool = False


class ConfigLoadError(HydraException, IOError):
    pass


class ConfigSource(Plugin):
    provider: str
    path: str

    def __init__(self, provider: str, path: str) -> None:
        if not path.startswith(self.scheme()):
            raise ValueError("Invalid path")
        self.provider = provider
        self.path = path[len(self.scheme() + "://") :]

    @staticmethod
    @abstractmethod
    def scheme() -> str:
        """
        :return: the scheme for this config source, for example file:// or pkg://
        """
        ...

    @abstractmethod
    def load_config(self, config_path: str) -> ConfigResult: ...

    # subclasses may override to improve performance
    def exists(self, config_path: str) -> bool:
        return self.is_group(config_path) or self.is_config(config_path)

    @abstractmethod
    def is_group(self, config_path: str) -> bool: ...

    @abstractmethod
    def is_config(self, config_path: str) -> bool: ...

    @abstractmethod
    def available(self) -> bool:
        """
        :return: True is this config source is pointing to a valid location
        """
        ...

    @abstractmethod
    def list(self, config_path: str, results_filter: ObjectType | None) -> builtins.list[str]:
        """
        List items under the specified config path
        :param config_path: config path to list items in, examples: "", "foo", "foo/bar"
        :param results_filter: None for all, GROUP for groups only and CONFIG for configs only
        :return: a list of config or group identifiers (sorted and unique)
        """
        ...

    def __str__(self) -> str:
        return repr(self)

    def __repr__(self) -> str:
        return f"provider={self.provider}, path={self.scheme()}://{self.path}"

    def _list_add_result(
        self,
        files: builtins.list[str],
        file_path: str,
        file_name: str,
        results_filter: ObjectType | None,
    ) -> None:
        filtered = ["__pycache__", "__init__.py"]
        is_group = self.is_group(file_path)
        is_config = self.is_config(file_path)
        if (
            is_group
            and (results_filter is None or results_filter == ObjectType.GROUP)
            and file_name not in filtered
        ):
            files.append(file_name)
        if (
            is_config
            and file_name not in filtered
            and (results_filter is None or results_filter == ObjectType.CONFIG)
        ):
            # strip extension
            last_dot = file_name.rfind(".")
            if last_dot != -1:
                file_name = file_name[0:last_dot]

            files.append(file_name)

    def full_path(self) -> str:
        return f"{self.scheme()}://{self.path}"

    @staticmethod
    def _normalize_file_name(filename: str) -> str:
        supported_extensions = [".yaml"]
        if filename.endswith(".yml"):
            raise ConfigLoadError(
                "Unsupported config file extension '.yml'. "
                "Hydra config files must use the '.yaml' extension."
            )
        if not any(filename.endswith(ext) for ext in supported_extensions):
            filename += ".yaml"
        return filename

    @staticmethod
    def _get_header_dict(config_text: str) -> dict[str, str | None]:
        res: dict[str, str | None] = {}
        for line in config_text.splitlines():
            line = line.strip()
            if len(line) == 0:
                # skip empty lines in header
                continue
            if re.match("^\\s*#\\s*@", line):
                line = line.lstrip("#").strip()
                splits = re.split(" ", line)
                splits = list(filter(lambda x: len(x) > 0, splits))
                if len(splits) < 2:
                    raise ValueError(f"Expected header format: KEY VALUE, got '{line}'")
                if len(splits) > 2:
                    raise ValueError(f"Too many components in '{line}'")
                key, val = splits[0], splits[1]
                key = key.strip()
                val = val.strip()
                if key.startswith("@"):
                    res[key[1:]] = val
            else:
                # stop parsing header on first non-header line
                break

        if "package" not in res:
            res["package"] = None
        return res

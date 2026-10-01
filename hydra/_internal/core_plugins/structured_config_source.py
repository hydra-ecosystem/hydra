# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved
import builtins
import importlib
import warnings

from hydra.core.config_store import ConfigStore
from hydra.core.object_type import ObjectType
from hydra.plugins.config_source import ConfigResult, ConfigSource


class StructuredConfigSource(ConfigSource):
    def __init__(self, provider: str, path: str) -> None:
        super().__init__(provider=provider, path=path)
        # Import the module, the __init__ there is expected to register the configs.
        if self.path != "":
            try:
                importlib.import_module(self.path)
            except Exception as e:
                warnings.warn(
                    f"Error importing {self.path} : some configs may not be available\n\n\tRoot cause: {e}\n"
                )
                raise e

    @staticmethod
    def scheme() -> str:
        return "structured"

    def load_config(self, config_path: str) -> ConfigResult:
        normalized_config_path = self._normalize_file_name(config_path)
        ret = ConfigStore.instance().load(config_path=normalized_config_path)
        provider = ret.provider if ret.provider is not None else self.provider
        header = {"package": ret.package}
        return ConfigResult(
            config=ret.node,
            path=f"{self.scheme()}://{self.path}",
            provider=provider,
            header=header,
        )

    def available(self) -> bool:
        return True

    def is_group(self, config_path: str) -> bool:
        type_ = ConfigStore.instance().get_type(config_path.rstrip("/"))
        return type_ == ObjectType.GROUP

    def is_config(self, config_path: str) -> bool:
        filename = self._normalize_file_name(config_path.rstrip("/"))
        type_ = ConfigStore.instance().get_type(filename)
        return type_ == ObjectType.CONFIG

    def list(
        self, config_path: str, results_filter: ObjectType | None
    ) -> builtins.list[str]:
        ret: list[str] = []
        files = ConfigStore.instance().list(config_path)

        for file in files:
            self._list_add_result(
                files=ret,
                file_path=f"{config_path}/{file}",
                file_name=file,
                results_filter=results_filter,
            )
        return sorted(list(set(ret)))

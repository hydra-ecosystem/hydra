# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved
import builtins
import os
import zipfile
from importlib import resources
from typing import Any

from omegaconf import OmegaConf

from hydra.core.object_type import ObjectType
from hydra.plugins.config_source import ConfigLoadError, ConfigResult, ConfigSource


class ImportlibResourcesConfigSource(ConfigSource):
    def __init__(self, provider: str, path: str) -> None:
        super().__init__(provider=provider, path=path)
        # normalize to pkg format
        self.path = self.path.replace("/", ".").rstrip(".")

    @staticmethod
    def scheme() -> str:
        return "pkg"

    def _read_config(self, res: Any) -> ConfigResult:
        try:
            if isinstance(res, zipfile.Path):
                # zipfile does not support encoding, read() calls returns bytes.
                f = res.open()
            else:
                f = res.open(encoding="utf-8")
            header_text = f.read(512)
            if isinstance(header_text, bytes):
                # if header is bytes, utf-8 decode (zipfile path)
                header_text_str = header_text.decode("utf-8")
            else:
                header_text_str = header_text
            header = ConfigSource._get_header_dict(header_text_str)
            f.seek(0)
            cfg = OmegaConf.load(f)
            return ConfigResult(
                config=cfg,
                path=f"{self.scheme()}://{self.path}",
                provider=self.provider,
                header=header,
            )
        finally:
            f.close()

    def load_config(self, config_path: str) -> ConfigResult:
        normalized_config_path = self._normalize_file_name(config_path)
        res = resources.files(self.path).joinpath(normalized_config_path)
        if not (res.is_file() or res.is_dir()):
            raise ConfigLoadError(f"Config not found : {normalized_config_path}")

        return self._read_config(res)

    def available(self) -> bool:
        try:
            files = resources.files(self.path)
        except (ValueError, ModuleNotFoundError, TypeError):
            return False
        return any(f.name == "__init__.py" and f.is_file() for f in files.iterdir())

    def is_group(self, config_path: str) -> bool:
        try:
            files = resources.files(self.path)
        except (ValueError, ModuleNotFoundError, TypeError):
            return False

        res = files.joinpath(config_path)
        ret = res.is_dir()
        assert isinstance(ret, bool)
        return ret

    def is_config(self, config_path: str) -> bool:
        config_path = self._normalize_file_name(config_path)
        try:
            files = resources.files(self.path)
        except (ValueError, ModuleNotFoundError, TypeError):
            return False
        res = files.joinpath(config_path)
        ret = res.is_file()
        assert isinstance(ret, bool)
        return ret

    def list(
        self, config_path: str, results_filter: ObjectType | None
    ) -> builtins.list[str]:
        files: list[str] = []
        for file in resources.files(self.path).joinpath(config_path).iterdir():
            fname = file.name
            fpath = os.path.join(config_path, fname)
            self._list_add_result(
                files=files,
                file_path=fpath,
                file_name=fname,
                results_filter=results_filter,
            )

        return sorted(list(set(files)))

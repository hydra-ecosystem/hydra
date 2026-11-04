# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved
import builtins
import posixpath
import sys
import zipfile
from importlib import import_module, resources
from pathlib import Path
from typing import Any

from omegaconf import OmegaConf

from hydra._internal.config_source_path import (
    ConfigPathOutsideRootError,
    package_resource_name,
    package_resource_root,
    require_package_reader,
    resolve_package_path,
)
from hydra.core.object_type import ObjectType
from hydra.plugins.config_source import ConfigLoadError, ConfigResult, ConfigSource

if sys.version_info >= (3, 12):
    from importlib.resources.abc import TraversalError
else:
    TraversalError = FileNotFoundError


class ImportlibResourcesConfigSource(ConfigSource):
    def __init__(self, provider: str, path: str) -> None:
        super().__init__(provider=provider, path=path)
        # normalize to pkg format
        self.path = self.path.replace("/", ".").rstrip(".")
        self._resources: Any = None

    def __getstate__(self) -> dict[str, Any]:
        # Each copied source establishes its own root; readers need not be copyable.
        state = self.__dict__.copy()
        state["_resources"] = None
        return state

    @staticmethod
    def scheme() -> str:
        return "pkg"

    def _get_resources(self) -> Any:
        if self._resources is not None:
            return self._resources
        package = import_module(self.path)
        spec = package.__spec__
        if (
            spec is None
            or spec.submodule_search_locations is None
            or spec.origin is None
        ):
            raise ValueError(f"'{self.path}' is not a regular Python package")
        self._resources = package_resource_root(resources.files(package))
        return self._resources

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
        try:
            res = resolve_package_path(self._get_resources(), normalized_config_path)
        except (FileNotFoundError, TraversalError):
            raise ConfigLoadError(f"Config not found : {normalized_config_path}")
        if not (res.is_file() or res.is_dir()):
            raise ConfigLoadError(f"Config not found : {normalized_config_path}")

        require_package_reader(self._get_resources(), res)
        return self._read_config(res)

    def available(self) -> bool:
        try:
            self._get_resources()
        except (ValueError, ModuleNotFoundError, TypeError):
            return False
        return True

    def is_group(self, config_path: str) -> bool:
        try:
            files = self._get_resources()
        except (ValueError, ModuleNotFoundError, TypeError):
            return False

        try:
            res = resolve_package_path(files, config_path)
        except (FileNotFoundError, TraversalError):
            return False
        ret = res.is_dir()
        assert isinstance(ret, bool)
        return ret

    def is_config(self, config_path: str) -> bool:
        config_path = self._normalize_file_name(config_path)
        try:
            files = self._get_resources()
        except (ValueError, ModuleNotFoundError, TypeError):
            return False
        try:
            res = resolve_package_path(files, config_path)
        except (FileNotFoundError, TraversalError):
            return False
        ret = res.is_file()
        assert isinstance(ret, bool)
        return ret

    def list(
        self, config_path: str, results_filter: ObjectType | None
    ) -> builtins.list[str]:
        files: list[str] = []
        root = self._get_resources()
        directory = resolve_package_path(root, config_path)
        require_package_reader(root, directory)
        for file in directory.iterdir():
            fname = file.name if isinstance(root, Path) else package_resource_name(file)
            if fname in ("__pycache__", "__init__.py"):
                continue
            fpath = posixpath.join(config_path, fname)
            for object_type, check in (
                (ObjectType.GROUP, self.is_group),
                (ObjectType.CONFIG, self.is_config),
            ):
                try:
                    matches = check(fpath)
                except ConfigPathOutsideRootError:
                    continue
                if matches and (
                    results_filter is None or results_filter == object_type
                ):
                    files.append(
                        fname.rsplit(".", 1)[0]
                        if object_type == ObjectType.CONFIG
                        else fname
                    )

        return sorted(list(set(files)))

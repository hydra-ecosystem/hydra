# SPDX-FileCopyrightText: Contributors to Hydra
# SPDX-License-Identifier: MIT
import ntpath
import os
import zipfile
from pathlib import Path
from typing import Any

from hydra.plugins.config_source import ConfigLoadError


class ConfigPathOutsideRootError(ConfigLoadError):
    """A config path resolves outside its selected source root."""


def resolve_file_path(root: str, config_path: str) -> str:
    """Resolve a config path within a fixed filesystem source root."""
    try:
        candidate = os.path.realpath(os.path.join(root, config_path))
    except (OSError, ValueError) as error:
        raise ConfigLoadError(
            f"Cannot resolve config path '{config_path}' within source root '{root}'"
        ) from error
    try:
        if os.path.normcase(os.path.commonpath([root, candidate])) == os.path.normcase(
            root
        ):
            return candidate
    except ValueError:
        pass
    raise ConfigPathOutsideRootError(
        f"Config path '{config_path}' resolves outside source root '{root}'"
    )


def package_resource_root(root: Any) -> Any:
    """Establish a supported public resource representation once per source."""
    if isinstance(root, Path):
        return Path(os.path.realpath(root))
    _require_traversable(root)
    return root


def _require_traversable(resource: Any, *, reading: bool = False) -> None:
    operations = ("joinpath", "is_file", "is_dir")
    if reading:
        operations += ("open", "iterdir")
    if not isinstance(getattr(resource, "name", None), str) or not all(
        callable(getattr(resource, operation, None)) for operation in operations
    ):
        raise ConfigLoadError("Unsupported package resource containment")


def resolve_package_path(root: Any, config_path: str) -> Any:
    """Resolve beneath the established native, archive or trusted virtual root."""
    if isinstance(root, Path):
        return Path(resolve_file_path(str(root), config_path))
    if (
        "\\" in config_path
        or config_path.startswith("/")
        or ntpath.splitdrive(config_path)[0]
    ):
        raise ConfigPathOutsideRootError(
            f"Config path '{config_path}' is outside the package resource root"
        )
    parts: list[str] = []
    for part in config_path.split("/"):
        if part == "..":
            if not parts:
                raise ConfigPathOutsideRootError(
                    f"Config path '{config_path}' is outside the package resource root"
                )
            parts.pop()
        elif part and part != ".":
            parts.append(part)
    resource = root.joinpath("/".join(parts)) if parts else root
    if not isinstance(root, zipfile.Path) and isinstance(
        resource, (Path, zipfile.Path)
    ):
        raise ConfigLoadError("Unsupported concrete package resource containment")
    _require_traversable(resource)
    return resource


def require_package_reader(root: Any, resource: Any) -> None:
    """Require the complete reader protocol before reading or listing content."""
    _require_traversable(root, reading=True)
    _require_traversable(resource, reading=True)


def package_resource_name(resource: Any) -> str:
    """Check an enumerated component before using it in any resource traversal."""
    name = getattr(resource, "name", None)
    if (
        not isinstance(name, str)
        or not name
        or name in (".", "..")
        or "/" in name
        or "\\" in name
        or ntpath.splitdrive(name)[0]
    ):
        raise ConfigLoadError(f"Invalid package resource name: {name!r}")
    return name

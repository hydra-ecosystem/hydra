# SPDX-FileCopyrightText: Contributors to Hydra
# SPDX-License-Identifier: MIT
import os

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

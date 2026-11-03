# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved
import os

from hydra.plugins.config_source import ConfigLoadError


def resolve_file_path(root: str, config_path: str) -> str:
    """Resolve a config path within a fixed filesystem source root."""
    try:
        candidate = os.path.realpath(os.path.join(root, config_path))
        if os.path.normcase(os.path.commonpath([root, candidate])) == os.path.normcase(
            root
        ):
            return candidate
    except (OSError, ValueError) as error:
        raise ConfigLoadError(
            f"Cannot resolve config path '{config_path}' within source root '{root}'"
        ) from error
    raise ConfigLoadError(
        f"Config path '{config_path}' resolves outside source root '{root}'"
    )

# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved

# Source of truth for Hydra's version
__version__ = "1.4.0rc1"
from hydra import utils
from hydra.errors import MissingConfigException
from hydra.main import main
from hydra.types import TaskFunction

from .compose import compose
from .initialize import (
    initialize,
    initialize_config_dir,
    initialize_config_module,
    initialize_config_search_path,
)

__all__ = [
    "__version__",
    "MissingConfigException",
    "main",
    "utils",
    "TaskFunction",
    "compose",
    "initialize",
    "initialize_config_module",
    "initialize_config_dir",
    "initialize_config_search_path",
]

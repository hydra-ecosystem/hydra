# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved
import functools
from typing import Any, Callable

from omegaconf import DictConfig

from . import version
from ._internal.execution_policy import ExecutionWhitelist
from ._internal.execution_policy import (
    execution_whitelist as execution_whitelist_context,
)
from ._internal.utils import _run_hydra, get_args_parser
from .types import TaskFunction


def main(
    config_path: str | None = None,
    config_name: str | None = None,
    version_base: str | None = version._UNSPECIFIED_,
    execution_whitelist: ExecutionWhitelist = None,
) -> Callable[[TaskFunction], Any]:
    """
    :param config_path: The config path, a directory where Hydra will search for
                        config files. This path is added to Hydra's searchpath.
                        Relative paths are interpreted relative to the declaring python
                        file. Alternatively, you can use the prefix `pkg://` to specify
                        a python package to add to the searchpath.
                        If config_path is None no directory is added to the Config search path.
    :param config_name: The name of the config (usually the file name without the .yaml extension)
    :param execution_whitelist: Trusted targets allowed for calls to instantiate()
                            and for Python logging configured by Hydra.
    """

    version.setbase(version_base)

    def main_decorator(task_function: TaskFunction) -> Callable[[], None]:
        @functools.wraps(task_function)
        def decorated_main(cfg_passthrough: DictConfig | None = None) -> Any:
            with execution_whitelist_context(execution_whitelist):
                if cfg_passthrough is not None:
                    return task_function(cfg_passthrough)
                else:
                    args_parser = get_args_parser()
                    args = args_parser.parse_intermixed_args()
                    # no return value from run_hydra() as it may sometime actually run the task_function
                    # multiple times (--multirun)
                    _run_hydra(
                        args=args,
                        args_parser=args_parser,
                        task_function=task_function,
                        config_path=config_path,
                        config_name=config_name,
                    )

        return decorated_main

    return main_decorator

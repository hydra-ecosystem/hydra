# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved
import copy
import functools
import pickle
import warnings
from pathlib import Path
from typing import Any, Callable, List, Optional

from omegaconf import DictConfig, open_dict, read_write

from . import version
from ._internal.target_policy import TargetWhitelist
from ._internal.target_policy import (
    target_whitelist as target_whitelist_context,
)
from ._internal.utils import _run_hydra, get_args_parser
from .core.hydra_config import HydraConfig
from .core.utils import _flush_loggers, configure_log
from .types import TaskFunction


def _get_rerun_conf(file_path: str, overrides: List[str]) -> DictConfig:
    msg = "Experimental rerun CLI option, other command line args are ignored."
    warnings.warn(msg, UserWarning)
    file = Path(file_path)
    if not file.exists():
        raise ValueError(f"File {file} does not exist!")

    if len(overrides) > 0:
        msg = "Config overrides are not supported as of now."
        warnings.warn(msg, UserWarning)

    with open(str(file), "rb") as input:
        config = pickle.load(input)  # nosec
    configure_log(config.hydra.job_logging, config.hydra.verbose)
    HydraConfig.instance().set_config(config)
    task_cfg = copy.deepcopy(config)
    with read_write(task_cfg):
        with open_dict(task_cfg):
            del task_cfg["hydra"]
    assert isinstance(task_cfg, DictConfig)
    return task_cfg


def main(
    config_path: Optional[str] = None,
    config_name: Optional[str] = None,
    version_base: Optional[str] = version._UNSPECIFIED_,
    target_whitelist: TargetWhitelist = None,
) -> Callable[[TaskFunction], Any]:
    """
    :param config_path: The config path, a directory where Hydra will search for
                        config files. This path is added to Hydra's searchpath.
                        Relative paths are interpreted relative to the declaring python
                        file. Alternatively, you can use the prefix `pkg://` to specify
                        a python package to add to the searchpath.
                        If config_path is None no directory is added to the Config search path.
    :param config_name: The name of the config (usually the file name without the .yaml extension)
    :param target_whitelist: Trusted Python targets allowed for Hydra operations,
                            including instantiate() and logging configuration.
    """

    version.setbase(version_base)

    def main_decorator(task_function: TaskFunction) -> Callable[[], None]:
        @functools.wraps(task_function)
        def decorated_main(cfg_passthrough: Optional[DictConfig] = None) -> Any:
            with target_whitelist_context(target_whitelist):
                if cfg_passthrough is not None:
                    return task_function(cfg_passthrough)
                else:
                    args_parser = get_args_parser()
                    args = args_parser.parse_intermixed_args()
                    if args.experimental_rerun is not None:
                        cfg = _get_rerun_conf(args.experimental_rerun, args.overrides)
                        task_function(cfg)
                        _flush_loggers()
                    else:
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

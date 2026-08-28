# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved
import copy
import logging
import os
import re
import sys
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from os.path import splitext
from pathlib import Path
from textwrap import dedent
from typing import Any, Dict, List, Optional, Sequence, Union, cast

from omegaconf import DictConfig, OmegaConf, open_dict, read_write

from hydra._internal.deprecation_warning import deprecation_warning
from hydra.core.hydra_config import HydraConfig
from hydra.core.singleton import Singleton
from hydra.types import HydraContext, TaskFunction

log = logging.getLogger(__name__)


def simple_stdout_log_config(level: int = logging.INFO) -> None:
    root = logging.getLogger()
    root.setLevel(level)
    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter("%(message)s")
    handler.setFormatter(formatter)
    root.addHandler(handler)


def configure_log(
    log_config: DictConfig,
    verbose_config: Union[bool, str, Sequence[str]] = False,
    target_whitelist: Any = None,
) -> None:
    assert isinstance(verbose_config, (bool, str)) or OmegaConf.is_list(verbose_config)
    if log_config is not None:
        conf: Dict[str, Any] = OmegaConf.to_container(  # type: ignore
            log_config, resolve=True
        )
        if conf["root"] is not None:
            # Imported lazily because instantiate's resolver imports core.utils.
            from hydra._internal.logging_config import configure_logging

            configure_logging(conf, target_whitelist)
    else:
        # default logging to stdout
        root = logging.getLogger()
        root.setLevel(logging.INFO)
        handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter(
            "[%(asctime)s][%(name)s][%(levelname)s] - %(message)s"
        )
        handler.setFormatter(formatter)
        root.addHandler(handler)
    if isinstance(verbose_config, bool):
        if verbose_config:
            logging.getLogger().setLevel(logging.DEBUG)
    else:
        if isinstance(verbose_config, str):
            verbose_list = OmegaConf.create([verbose_config])
        elif OmegaConf.is_list(verbose_config):
            verbose_list = verbose_config  # type: ignore
        else:
            assert False

        for logger in verbose_list:
            logging.getLogger(logger).setLevel(logging.DEBUG)


def _save_config(cfg: DictConfig, filename: str, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    with open(str(output_dir / filename), "w", encoding="utf-8") as file:
        file.write(OmegaConf.to_yaml(cfg))


def _log_job_error_to_file() -> None:
    record = log.makeRecord(
        name=log.name,
        level=logging.ERROR,
        fn=__file__,
        lno=0,
        msg="Job failed",
        args=(),
        exc_info=sys.exc_info(),
    )
    for handler in logging.getLogger().handlers:
        if isinstance(handler, logging.FileHandler) and record.levelno >= handler.level:
            handler.handle(record)


def filter_overrides(overrides: Sequence[str]) -> Sequence[str]:
    """
    :param overrides: overrides list
    :return: returning a new overrides list with all the keys starting with hydra. filtered.
    """
    return [x for x in overrides if not x.startswith("hydra.")]


def run_job(
    task_function: TaskFunction,
    config: DictConfig,
    job_dir_key: str,
    job_subdir_key: Optional[str],
    hydra_context: HydraContext,
    configure_logging: bool = True,
) -> "JobReturn":
    callbacks = hydra_context.callbacks

    old_cwd = os.getcwd()
    orig_hydra_cfg = HydraConfig.instance().cfg

    # init Hydra config for config evaluation
    HydraConfig.instance().set_config(config)

    output_dir = str(OmegaConf.select(config, job_dir_key))
    if job_subdir_key is not None:
        # evaluate job_subdir_key lazily.
        # this is running on the client side in sweep and contains things such as job:id which
        # are only available there.
        subdir = str(OmegaConf.select(config, job_subdir_key))
        output_dir = os.path.join(output_dir, subdir)

    with read_write(config.hydra.runtime):
        with open_dict(config.hydra.runtime):
            config.hydra.runtime.output_dir = os.path.abspath(output_dir)

    # update Hydra config
    HydraConfig.instance().set_config(config)
    _chdir = None
    try:
        ret = JobReturn()
        task_cfg = copy.deepcopy(config)
        with read_write(task_cfg):
            with open_dict(task_cfg):
                del task_cfg["hydra"]

        ret.cfg = task_cfg
        hydra_cfg = HydraConfig.instance().cfg
        assert isinstance(hydra_cfg, DictConfig)
        env_set = hydra_cfg.hydra.job.env_set
        with read_write(env_set):
            OmegaConf.resolve(env_set)
        hydra_cfg = copy.deepcopy(hydra_cfg)
        assert isinstance(hydra_cfg, DictConfig)
        ret.hydra_cfg = hydra_cfg
        overrides = OmegaConf.to_container(config.hydra.overrides.task)
        assert isinstance(overrides, list)
        ret.overrides = overrides
        # handle output directories here
        Path(str(output_dir)).mkdir(parents=True, exist_ok=True)

        _chdir = hydra_cfg.hydra.job.chdir

        if _chdir:
            os.chdir(output_dir)
            ret.working_dir = output_dir
        else:
            ret.working_dir = os.getcwd()

        if configure_logging:
            configure_log(
                config.hydra.job_logging,
                config.hydra.verbose,
                target_whitelist=hydra_context.target_whitelist,
            )

        if config.hydra.output_subdir is not None:
            hydra_output = Path(config.hydra.runtime.output_dir) / Path(
                config.hydra.output_subdir
            )
            _save_config(task_cfg, "config.yaml", hydra_output)
            _save_config(hydra_cfg, "hydra.yaml", hydra_output)
            _save_config(config.hydra.overrides.task, "overrides.yaml", hydra_output)

        interrupt: Optional[KeyboardInterrupt] = None
        with env_override(hydra_cfg.hydra.job.env_set):
            callbacks.on_job_start(config=config, task_function=task_function)
            try:
                ret.return_value = task_function(task_cfg)
                ret.status = JobStatus.COMPLETED
            except Exception as e:
                _log_job_error_to_file()
                ret.return_value = e
                ret.status = JobStatus.FAILED
            except KeyboardInterrupt as e:
                # record the interrupt like any other failure so callbacks see
                # it, but re-raise after finalization so it still propagates
                # (multirun relies on it to stop the remaining jobs)
                ret.return_value = e
                ret.status = JobStatus.FAILED
                interrupt = e

        ret.task_name = JobRuntime.instance().get("name")

        _flush_loggers()

        callbacks.on_job_end(config=config, job_return=ret)

        if interrupt is not None:
            # expose the populated JobReturn to callers (Hydra.run) so
            # on_run_end can receive the real job metadata after the re-raise
            setattr(interrupt, "job_return", ret)
            raise interrupt

        return ret
    finally:
        HydraConfig.instance().cfg = orig_hydra_cfg
        if _chdir:
            os.chdir(old_cwd)


def get_valid_filename(s: str) -> str:
    s = str(s).strip().replace(" ", "_")
    return re.sub(r"(?u)[^-\w.]", "", s)


@dataclass
class OverrideDirnameOptions:
    kv_sep: str = "="
    item_sep: str = ","
    exclude_keys: List[str] = field(default_factory=list)
    element_resolver: Optional[str] = None


def _get_override_dirname_options(
    options: Optional[Union[Dict[str, Any], DictConfig]], hydra_conf: DictConfig
) -> OverrideDirnameOptions:
    if options is None:
        old = hydra_conf.job.config.override_dirname
        if not isinstance(old.kv_sep, str):
            raise TypeError("hydra_override_dirname kv_sep must be a string")
        if not isinstance(old.item_sep, str):
            raise TypeError("hydra_override_dirname item_sep must be a string")
        if not OmegaConf.is_list(old.exclude_keys):
            raise TypeError("hydra_override_dirname exclude_keys must be a list")
        if not all(isinstance(key, str) for key in old.exclude_keys):
            raise TypeError("hydra_override_dirname exclude_keys must contain strings")
        return OverrideDirnameOptions(
            kv_sep=old.kv_sep,
            item_sep=old.item_sep,
            exclude_keys=list(old.exclude_keys),
        )

    if isinstance(options, DictConfig):
        options = cast(Dict[str, Any], OmegaConf.to_container(options, resolve=True))

    if not isinstance(options, dict):
        raise TypeError("hydra_override_dirname options must be a dictionary")

    kv_sep = options.get("kv_sep", "=")
    if not isinstance(kv_sep, str):
        raise TypeError("hydra_override_dirname kv_sep must be a string")

    item_sep = options.get("item_sep", ",")
    if not isinstance(item_sep, str):
        raise TypeError("hydra_override_dirname item_sep must be a string")

    exclude_keys = options.get("exclude_keys", [])
    if not isinstance(exclude_keys, (list, tuple)) and not OmegaConf.is_list(
        exclude_keys
    ):
        raise TypeError("hydra_override_dirname exclude_keys must be a list")
    if not all(isinstance(key, str) for key in exclude_keys):
        raise TypeError("hydra_override_dirname exclude_keys must contain strings")

    element_resolver = options.get("element_resolver")
    if element_resolver is not None and not isinstance(element_resolver, str):
        raise TypeError("hydra_override_dirname element_resolver must be a string")

    return OverrideDirnameOptions(
        kv_sep=kv_sep,
        item_sep=item_sep,
        exclude_keys=list(exclude_keys),
        element_resolver=element_resolver,
    )


def _resolve_override_dirname_item(item: str, root: DictConfig) -> str:
    if "${" not in item:
        return item

    key = "_hydra_override_dirname_item"
    cfg = copy.deepcopy(root)
    with open_dict(cfg):
        cfg[key] = item
    resolved = OmegaConf.select(cfg, key)
    assert resolved is not None
    return str(resolved)


def hydra_override_dirname(
    options: Optional[Union[Dict[str, Any], DictConfig]] = None,
    *,
    _root_: DictConfig,
    _parent_: DictConfig,
    _node_: Any,
) -> str:
    hydra_root = _root_
    hydra_conf = OmegaConf.select(hydra_root, "hydra", default=None)
    if hydra_conf is None:
        hydra_conf = cast(DictConfig, HydraConfig.get())
    assert isinstance(hydra_conf, DictConfig)

    opts = _get_override_dirname_options(options, hydra_conf)

    element_resolver = None
    if opts.element_resolver is not None:
        if not OmegaConf.has_resolver(opts.element_resolver):
            raise ValueError(f"Unknown OmegaConf resolver '{opts.element_resolver}'")
        element_resolver = OmegaConf._get_resolver(opts.element_resolver)
        assert element_resolver is not None

    task_overrides = OmegaConf.to_container(
        hydra_conf.overrides.task,
        resolve=False,
    )
    assert isinstance(task_overrides, list)

    from hydra.core.override_parser.overrides_parser import OverridesParser

    parsed_overrides = OverridesParser.create().parse_overrides(task_overrides)
    exclude_keys = set(opts.exclude_keys)
    items = []
    for override in parsed_overrides:
        if override.key_or_group in exclude_keys:
            continue

        assert override.input_line is not None
        items.append(override.input_line)

    items.sort()
    for idx, item in enumerate(items):
        item = re.sub(pattern="[=]", repl=opts.kv_sep, string=item)
        item = _resolve_override_dirname_item(item, _root_)
        if element_resolver is not None:
            item = str(element_resolver(_root_, _parent_, _node_, (item,), (item,)))
        items[idx] = item

    return opts.item_sep.join(items)


def hydra_deprecated_override_dirname(
    *,
    _root_: DictConfig,
    _parent_: DictConfig,
    _node_: Any,
) -> str:
    deprecation_warning(
        "hydra.job.override_dirname is deprecated. "
        "Use ${hydra_override_dirname:} instead.",
        stacklevel=3,
    )
    return hydra_override_dirname(_root_=_root_, _parent_=_parent_, _node_=_node_)


def setup_globals() -> None:
    # please add documentation when you add a new resolver
    OmegaConf.register_resolver(
        "hydra_override_dirname",
        hydra_override_dirname,
        replace=True,
    )
    OmegaConf.register_resolver(
        "hydra_deprecated_override_dirname",
        hydra_deprecated_override_dirname,
        replace=True,
    )
    OmegaConf.register_resolver(
        "now",
        lambda pattern: datetime.now().strftime(pattern),
        use_cache=True,
        replace=True,
    )
    OmegaConf.register_resolver(
        "hydra",
        lambda path: OmegaConf.select(cast(DictConfig, HydraConfig.get()), path),
        replace=True,
    )

    vi = sys.version_info
    version_dict = {
        "major": f"{vi[0]}",
        "minor": f"{vi[0]}.{vi[1]}",
        "micro": f"{vi[0]}.{vi[1]}.{vi[2]}",
    }
    OmegaConf.register_resolver(
        "python_version", lambda level="minor": version_dict.get(level), replace=True
    )


class JobStatus(Enum):
    UNKNOWN = 0
    COMPLETED = 1
    FAILED = 2


@dataclass
class JobReturn:
    overrides: Optional[Sequence[str]] = None
    cfg: Optional[DictConfig] = None
    hydra_cfg: Optional[DictConfig] = None
    working_dir: Optional[str] = None
    task_name: Optional[str] = None
    status: JobStatus = JobStatus.UNKNOWN
    _return_value: Any = None

    @property
    def return_value(self) -> Any:
        assert self.status != JobStatus.UNKNOWN, "return_value not yet available"
        if self.status == JobStatus.COMPLETED:
            return self._return_value
        else:
            sys.stderr.write(
                f"Error executing job with overrides: {self.overrides}" + os.linesep
            )
            raise self._return_value

    @return_value.setter
    def return_value(self, value: Any) -> None:
        self._return_value = value


class JobRuntime(metaclass=Singleton):
    def __init__(self) -> None:
        self.conf: DictConfig = OmegaConf.create()
        self.set("name", "UNKNOWN_NAME")

    def get(self, key: str) -> Any:
        ret = OmegaConf.select(self.conf, key)
        if ret is None:
            raise KeyError(f"Key not found in {type(self).__name__}: {key}")
        return ret

    def set(self, key: str, value: Any) -> None:
        log.debug(f"Setting {type(self).__name__}:{key}={value}")
        self.conf[key] = value


def validate_config_path(config_path: Optional[str]) -> None:
    if config_path is not None:
        split_file = splitext(config_path)
        if split_file[1] in (".yaml", ".yml"):
            msg = dedent("""\
            Using config_path to specify the config name is not supported, specify the config name via config_name.
            See https://hydra.cc/docs/1.2/upgrades/0.11_to_1.0/config_path_changes
            """)
            raise ValueError(msg)


@contextmanager
def env_override(env: Dict[str, str]) -> Any:
    """Temporarily set environment variables inside the context manager and
    fully restore previous environment afterwards
    """
    original_env = {key: os.getenv(key) for key in env}
    os.environ.update(env)
    try:
        yield
    finally:
        for key, value in original_env.items():
            if value is None:
                del os.environ[key]
            else:
                os.environ[key] = value


def _flush_loggers() -> None:
    # Python logging does not have an official API to flush all loggers.
    # This will have to do.
    for h_weak_ref in logging._handlerList:  # type: ignore
        try:
            h_weak_ref().flush()
        except Exception:
            # ignore exceptions thrown during flushing
            pass

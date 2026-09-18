# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved
import builtins
import copy
import logging
import os
import pickle
import re
import sys
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from os.path import splitext
from pathlib import Path
from textwrap import dedent
from types import FrameType, FunctionType, TracebackType
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple, Union, cast

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
    execution_whitelist: Any = None,
) -> None:
    assert isinstance(verbose_config, (bool, str)) or OmegaConf.is_list(verbose_config)
    if log_config is not None:
        conf: Dict[str, Any] = OmegaConf.to_container(  # type: ignore
            log_config, resolve=True
        )
        if conf["root"] is not None:
            # Imported lazily because instantiate's resolver imports core.utils.
            from hydra._internal.logging_config import configure_logging

            configure_logging(conf, execution_whitelist)
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
    # Imported lazily because execution_policy's resolver imports core.utils.
    from hydra._internal.execution_policy import execution_whitelist

    with execution_whitelist(hydra_context.execution_whitelist, reset=True):
        return _run_job(
            task_function=task_function,
            config=config,
            job_dir_key=job_dir_key,
            job_subdir_key=job_subdir_key,
            hydra_context=hydra_context,
            configure_logging=configure_logging,
        )


def _run_job(
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
                execution_whitelist=hydra_context.execution_whitelist,
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
                ret._remote_traceback = _serialize_traceback(e.__traceback__)
                ret._remote_exception_chain = _serialize_exception_chain(e)
                ret._remote_exception_group = _serialize_exception_group(e)
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


class _SyntheticTraceback(Exception):
    pass


_TRACEBACK_STUB = compile("raise _SyntheticTraceback", "<remote traceback>", "exec")
_SerializedTraceback = List[Tuple[str, str, int]]
_SerializedExceptionChain = List[Tuple[str, "_SerializedExceptionNode"]]
_SerializedExceptionNode = Tuple[
    str,
    str,
    str,
    bool,
    _SerializedTraceback,
    _SerializedExceptionChain,
    List["_SerializedExceptionNode"],
]
_SerializedExceptionGroup = List[_SerializedExceptionNode]


def _serialize_traceback(tb: Optional[TracebackType]) -> _SerializedTraceback:
    result = []
    while tb is not None:
        code = tb.tb_frame.f_code
        result.append((code.co_filename, code.co_name, tb.tb_lineno))
        tb = tb.tb_next
    return result


def _safe_exception_message(error: BaseException) -> str:
    try:
        return str(error)
    except BaseException:
        return "<exception message unavailable>"


def _serialize_exception_chain(
    error: BaseException, ancestors: Optional[Set[int]] = None
) -> _SerializedExceptionChain:
    seen = set() if ancestors is None else set(ancestors)
    seen.add(id(error))
    if error.__cause__ is not None:
        relation = "cause"
        chained = error.__cause__
    elif error.__context__ is not None and not error.__suppress_context__:
        relation = "context"
        chained = error.__context__
    else:
        return []
    if id(chained) in seen:
        return []
    return [(relation, _serialize_exception_node(chained, seen))]


def _exception_group_members(error: BaseException) -> Sequence[BaseException]:
    group_type = getattr(builtins, "BaseExceptionGroup", None)
    if group_type is None or not isinstance(error, group_type):
        return ()
    return cast(Sequence[BaseException], error.exceptions)


def _serialize_exception_node(
    error: BaseException, ancestors: Optional[Set[int]] = None
) -> _SerializedExceptionNode:
    seen = set() if ancestors is None else set(ancestors)
    seen.add(id(error))
    error_type = type(error)
    members = _exception_group_members(error)
    message = (
        cast(str, error.message)
        if members and hasattr(error, "message")
        else _safe_exception_message(error)
    )
    return (
        error_type.__module__,
        error_type.__qualname__,
        message,
        isinstance(error, Exception),
        _serialize_traceback(error.__traceback__),
        _serialize_exception_chain(error, seen),
        [_serialize_exception_node(child, seen) for child in members],
    )


def _serialize_exception_group(
    error: BaseException,
) -> Optional[_SerializedExceptionGroup]:
    members = _exception_group_members(error)
    if not members:
        return None
    return [_serialize_exception_node(member, {id(error)}) for member in members]


def _create_synthetic_frame(filename: str, name: str, lineno: int) -> FrameType:
    code = _TRACEBACK_STUB.replace(
        co_filename=filename,
        co_name=name,
        co_firstlineno=lineno,
    )
    if hasattr(code, "co_qualname"):
        code = code.replace(co_qualname=name)
    function = FunctionType(code, {"_SyntheticTraceback": _SyntheticTraceback})
    try:
        function()
    except _SyntheticTraceback as error:
        tb = error.__traceback__
        assert tb is not None and tb.tb_next is not None
        return tb.tb_next.tb_frame
    raise AssertionError("Synthetic traceback frame was not created")


def _deserialize_traceback(
    serialized: Sequence[Tuple[str, str, int]],
) -> Optional[TracebackType]:
    result: Optional[TracebackType] = None
    for filename, name, lineno in reversed(serialized):
        frame = _create_synthetic_frame(filename, name, lineno)
        result = TracebackType(result, frame, -1, lineno)
    return result


def _deserialize_exception_chain(
    serialized: _SerializedExceptionChain,
) -> Optional[Tuple[str, BaseException]]:
    if not serialized:
        return None
    relation, node = serialized[0]
    return relation, _deserialize_exception_node(node)


def _deserialize_exception_node(serialized: _SerializedExceptionNode) -> BaseException:
    module, qualname, message, is_exception, tb, chain, group = serialized
    children = [_deserialize_exception_node(child) for child in group]
    name = qualname.rsplit(".", maxsplit=1)[-1]
    if children:
        group_name = "ExceptionGroup" if is_exception else "BaseExceptionGroup"
        group_base = cast(Any, getattr(builtins, group_name))
        error_type = type(
            name,
            (group_base,),
            {"__module__": module, "__qualname__": qualname},
        )
        error = error_type(message, children)
    else:
        base = Exception if is_exception else BaseException
        error_type = type(
            name,
            (base,),
            {"__module__": module, "__qualname__": qualname},
        )
        error = error_type(message)
    error.__traceback__ = _deserialize_traceback(tb)
    if chain:
        relation, chained = cast(
            Tuple[str, BaseException], _deserialize_exception_chain(chain)
        )
        if relation == "cause":
            error.__cause__ = chained
        else:
            error.__context__ = chained
    return error


def _restore_exception_node(
    error: BaseException, serialized: _SerializedExceptionNode
) -> None:
    _, _, _, _, remote_traceback, remote_chain, remote_group = serialized
    error.__traceback__ = _deserialize_traceback(remote_traceback)
    if remote_chain:
        relation, chained = cast(
            Tuple[str, BaseException], _deserialize_exception_chain(remote_chain)
        )
        if relation == "cause":
            error.__cause__ = chained
        else:
            error.__context__ = chained

    members = _exception_group_members(error)
    if len(members) == len(remote_group):
        for member, child in zip(members, remote_group):
            _restore_exception_node(member, child)


@dataclass
class JobReturn:
    overrides: Optional[Sequence[str]] = None
    cfg: Optional[DictConfig] = None
    hydra_cfg: Optional[DictConfig] = None
    working_dir: Optional[str] = None
    task_name: Optional[str] = None
    status: JobStatus = JobStatus.UNKNOWN
    _return_value: Any = None
    _remote_traceback: Optional[_SerializedTraceback] = field(
        default=None, repr=False, compare=False
    )
    _remote_exception_chain: Optional[_SerializedExceptionChain] = field(
        default=None, repr=False, compare=False
    )
    _remote_exception_group: Optional[_SerializedExceptionGroup] = field(
        default=None, repr=False, compare=False
    )

    def __getstate__(self) -> Dict[str, Any]:
        state = self.__dict__.copy()
        error = self._return_value
        if self.status is JobStatus.FAILED and isinstance(error, BaseException):
            try:
                # The exception was raised by the local task, not read from a peer.
                restored = pickle.loads(  # nosec B301
                    pickle.dumps(error, protocol=pickle.HIGHEST_PROTOCOL)
                )
                if type(restored) is not type(error):
                    raise TypeError("exception type changed after pickle")
            except Exception:
                error_type = type(error)
                state["_return_value"] = RuntimeError(
                    f"Remote {error_type.__module__}.{error_type.__qualname__}: "
                    f"{_safe_exception_message(error)}"
                )
        return state

    @property
    def return_value(self) -> Any:
        assert self.status != JobStatus.UNKNOWN, "return_value not yet available"
        if self.status == JobStatus.COMPLETED:
            return self._return_value
        else:
            sys.stderr.write(
                f"Error executing job with overrides: {self.overrides}" + os.linesep
            )
            if (
                self._remote_traceback is not None
                and isinstance(self._return_value, BaseException)
                and self._return_value.__traceback__ is None
            ):
                if self._remote_exception_chain:
                    relation, chained = cast(
                        Tuple[str, BaseException],
                        _deserialize_exception_chain(self._remote_exception_chain),
                    )
                    if relation == "cause":
                        self._return_value.__cause__ = chained
                    else:
                        self._return_value.__context__ = chained
                if self._remote_exception_group:
                    members = _exception_group_members(self._return_value)
                    if len(members) == len(self._remote_exception_group):
                        for member, child in zip(members, self._remote_exception_group):
                            _restore_exception_node(member, child)
                raise self._return_value.with_traceback(
                    _deserialize_traceback(self._remote_traceback)
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

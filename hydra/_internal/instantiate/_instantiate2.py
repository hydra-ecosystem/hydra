# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved

import copy
import functools
import inspect
import itertools
import operator
import os
import types
from enum import Enum
from textwrap import dedent
from typing import Any, Callable, Dict, List, Sequence, Set, Tuple, Union

from omegaconf import OmegaConf, SCMode
from omegaconf._utils import is_structured_config

from hydra._internal.deprecation_warning import deprecation_warning
from hydra._internal.utils import _locate
from hydra.errors import InstantiationException
from hydra.types import ConvertMode, TargetConf

# This blocklist is a best-effort, defense-in-depth stopgap. It is not a
# complete security boundary because application callables can indirectly
# dispatch operations that never appear as _target_ values.
#
# These operations are fully named by the target itself. Trusted users may
# authorize them with HYDRA_INSTANTIATE_ALLOWLIST_OVERRIDE.
DEFAULT_BLOCKLISTED_MODULES = {
    "_sitebuiltins.Quitter",
    "builtins.exit",
    "builtins.quit",
    "os.kill",
    "os.putenv",
    "os.remove",
    "os.removedirs",
    "os.rmdir",
    "os.fchdir",
    "os.setuid",
    "os.fork",
    "os.forkpty",
    "os.killpg",
    "os.rename",
    "os.renames",
    "os.truncate",
    "os.replace",
    "os.unlink",
    "os.fchmod",
    "os.fchown",
    "os.chmod",
    "os.chown",
    "os.chroot",
    "os.lchflags",
    "os.lchmod",
    "os.lchown",
    "os.chdir",
    "shutil.rmtree",
    "shutil.move",
    "shutil.chown",
}

# These dispatchers execute caller-supplied callables and return their results
# directly or through a container, iterator, or deferred result. That allows
# selection, wrapping, and invocation to happen outside instantiate's immediate
# callable-result authorization.
CALLBACK_DISPATCH_TARGETS = {
    "builtins.map",
    "concurrent.futures._base.Executor.map",
    "concurrent.futures._base.Executor.submit",
    "concurrent.futures.process.ProcessPoolExecutor.map",
    "concurrent.futures.process.ProcessPoolExecutor.submit",
    "concurrent.futures.thread.ThreadPoolExecutor.submit",
    "functools.reduce",
    "itertools.accumulate",
    "itertools.groupby",
    "itertools.starmap",
    "multiprocessing.pool.Pool._map_async",
    "multiprocessing.pool.Pool.apply",
    "multiprocessing.pool.Pool.apply_async",
    "multiprocessing.pool.Pool.imap",
    "multiprocessing.pool.Pool.imap_unordered",
    "multiprocessing.pool.Pool.map",
    "multiprocessing.pool.Pool.map_async",
    "multiprocessing.pool.Pool.starmap",
    "multiprocessing.pool.Pool.starmap_async",
    "_functools.reduce",
}

_CALLABLE_DESCRIPTOR_BINDING_TARGETS: Dict[type, str] = {
    types.ClassMethodDescriptorType: "types.ClassMethodDescriptorType.__get__",
    types.FunctionType: "types.FunctionType.__get__",
    types.MethodDescriptorType: "types.MethodDescriptorType.__get__",
    types.WrapperDescriptorType: "types.WrapperDescriptorType.__get__",
}

# These helpers construct, bind, or relabel callable wrappers whose later
# invocation can return an unauthorized callable outside instantiate's result
# mediation.
CALLABLE_WRAPPER_TARGETS = {
    "builtins.classmethod",
    "builtins.staticmethod",
    "contextlib.AsyncContextDecorator.__call__",
    "contextlib.ContextDecorator.__call__",
    "functools.cache",
    "functools.lru_cache",
    "functools.partialmethod",
    "functools.partialmethod.__get__",
    "functools.singledispatch",
    "functools.singledispatchmethod",
    "functools.singledispatchmethod.__get__",
    "functools.update_wrapper",
    "functools.wraps",
    "types.FunctionType",
    "types.MethodType",
    "unittest.mock.AsyncMock",
    "unittest.mock.MagicMock",
    "unittest.mock.Mock",
    "unittest.mock.PropertyMock",
    "unittest.mock.create_autospec",
    "unittest.mock.mock_open",
} | set(_CALLABLE_DESCRIPTOR_BINDING_TARGETS.values())

_NON_CALLABLE_MOCK_TARGETS = {
    "unittest.mock.NonCallableMagicMock",
    "unittest.mock.NonCallableMock",
}
_NON_CALLABLE_MOCK_SAFE_PARAMETERS = {"name", "spec", "spec_set"}

# These targets allow config data to select or supply executable behavior.
# They cannot be authorized with HYDRA_INSTANTIATE_ALLOWLIST_OVERRIDE.
UNCONTROLLED_EXECUTION_TARGETS = {
    "_sitebuiltins._Helper",
    "builtins.__build_class__",
    "builtins.__import__",
    "builtins.compile",
    "builtins.eval",
    "builtins.exec",
    "builtins.help",
    "builtins.type.__call__",
    "builtins.type.__new__",
    "operator.attrgetter",
    "operator.call",
    "operator.contains",
    "operator.delitem",
    "operator.getitem",
    "operator.itemgetter",
    "operator.methodcaller",
    "operator.setitem",
    "_operator.attrgetter",
    "_operator.call",
    "_operator.contains",
    "_operator.delitem",
    "_operator.getitem",
    "_operator.itemgetter",
    "_operator.methodcaller",
    "_operator.setitem",
    "ctypes.CDLL",
    "ctypes.LibraryLoader.LoadLibrary",
    "ctypes.OleDLL",
    "ctypes.PyDLL",
    "ctypes.WinDLL",
    "ctypes.cdll.LoadLibrary",
    "ctypes.oledll.LoadLibrary",
    "ctypes.pydll.LoadLibrary",
    "ctypes.windll.LoadLibrary",
    "dataclasses.make_dataclass",
    "importlib.import_module",
    "importlib.machinery.ExtensionFileLoader.create_module",
    "importlib.machinery.ExtensionFileLoader.exec_module",
    "importlib.machinery.ExtensionFileLoader.load_module",
    "importlib.machinery.SourceFileLoader.exec_module",
    "importlib.machinery.SourceFileLoader.load_module",
    "importlib.machinery.SourcelessFileLoader.exec_module",
    "importlib.machinery.SourcelessFileLoader.load_module",
    "_frozen_importlib_external.ExtensionFileLoader.create_module",
    "_frozen_importlib_external.ExtensionFileLoader.exec_module",
    "_frozen_importlib_external.FileLoader.load_module",
    "_frozen_importlib_external._LoaderBasics.exec_module",
    "os.popen",
    "os.posix_spawn",
    "os.posix_spawnp",
    "os.startfile",
    "os.system",
    "pty.spawn",
    "runpy.run_module",
    "runpy.run_path",
    "subprocess.Popen",
    "subprocess.call",
    "subprocess.check_call",
    "subprocess.check_output",
    "subprocess.getoutput",
    "subprocess.getstatusoutput",
    "subprocess.run",
    "pickle.load",
    "pickle.loads",
    "pickle.Unpickler",
    "pickle._load",
    "pickle._loads",
    "pickle._Unpickler",
    "_pickle.load",
    "_pickle.loads",
    "_pickle.Unpickler",
    "marshal.load",
    "marshal.loads",
    "tracemalloc.Snapshot.load",
    "dill.load",
    "dill.loads",
    "cloudpickle.load",
    "cloudpickle.loads",
    "timeit.timeit",
    "timeit.repeat",
    "timeit.main",
    "timeit.Timer.timeit",
    "timeit.Timer.repeat",
    "timeit.Timer.autorange",
    "cProfile.run",
    "cProfile.runctx",
    "cProfile.Profile.run",
    "cProfile.Profile.runctx",
    "profile.run",
    "profile.runctx",
    "profile.Profile.run",
    "profile.Profile.runctx",
    "code.interact",
    "code.InteractiveInterpreter.runsource",
    "code.InteractiveInterpreter.runcode",
    "code.InteractiveConsole.push",
    "typing.ForwardRef._evaluate",
    "typing._eval_type",
    "typing.evaluate_forward_ref",
    "typing.get_type_hints",
    "types.new_class",
    "unittest.mock.patch",
    "unittest.mock.patch.dict",
    "unittest.mock.patch.multiple",
    "unittest.mock.patch.object",
    "annotationlib.ForwardRef._evaluate",
    "annotationlib.ForwardRef.evaluate",
    "annotationlib.get_annotations",
    "optparse.Values.read_file",
    "optparse.Values.read_module",
} | CALLBACK_DISPATCH_TARGETS | CALLABLE_WRAPPER_TARGETS

UNCONTROLLED_EXECUTION_TARGET_PREFIXES = (
    "os.exec",
    "os.spawn",
    "logging.config.",
    "doctest.",
    "shelve.",
    "trace.",
    "pydoc.",
    "pdb.",
    "bdb.",
)

UNCONTROLLED_EXECUTION_TARGET_PREFIX_EXCEPTIONS = {
    "doctest.DocTest",
    "doctest.DocTestParser",
    "doctest.Example",
    "pydoc.HTMLDoc",
    "pydoc.TextDoc",
    "trace.Trace",
}

DISCOVERY_TARGETS = {
    "hydra._internal.utils._locate",
    "hydra.utils.get_class",
    "hydra.utils.get_method",
    "hydra.utils.get_static_method",
    "hydra.utils.get_object",
}


def _get_os_alias_target(target: str) -> str:
    for module, public_module in (
        ("posix", "os"),
        ("nt", "os"),
        ("posixpath", "os.path"),
        ("ntpath", "os.path"),
    ):
        module_prefix = f"{module}."
        if target.startswith(module_prefix):
            return f"{public_module}.{target[len(module_prefix):]}"
    return target


class _Keys(str, Enum):
    """Special keys in configs used by instantiate."""

    TARGET = "_target_"
    CONVERT = "_convert_"
    RECURSIVE = "_recursive_"
    ARGS = "_args_"
    PARTIAL = "_partial_"


def _is_target(x: Any) -> bool:
    if isinstance(x, dict):
        return "_target_" in x
    if OmegaConf.is_dict(x):
        return "_target_" in x
    return False


def _is_blocklisted_target(target: str) -> bool:
    canonical_target = _get_os_alias_target(target)
    if (
        canonical_target in DEFAULT_BLOCKLISTED_MODULES
        or canonical_target in UNCONTROLLED_EXECUTION_TARGETS
    ):
        return True
    if canonical_target in UNCONTROLLED_EXECUTION_TARGET_PREFIX_EXCEPTIONS:
        return False
    return canonical_target.startswith(UNCONTROLLED_EXECUTION_TARGET_PREFIXES)


def _is_uncontrolled_execution_target(target: str) -> bool:
    canonical_target = _get_os_alias_target(target)
    if canonical_target in UNCONTROLLED_EXECUTION_TARGETS:
        return True
    if canonical_target in UNCONTROLLED_EXECUTION_TARGET_PREFIX_EXCEPTIONS:
        return False
    return canonical_target.startswith(UNCONTROLLED_EXECUTION_TARGET_PREFIXES)


def _get_target_name_for_check(target: Union[str, type, Callable[..., Any]]) -> str:
    if isinstance(target, str):
        return target
    module = getattr(target, "__module__", None)
    qualname = getattr(target, "__qualname__", None)
    if module is not None and qualname is not None:
        return f"{module}.{qualname}"
    target_type = type(target)
    return f"{target_type.__module__}.{target_type.__qualname__}"


def _get_resolved_target_name_for_check(target: Callable[..., Any]) -> str:
    """Return the security identity of a resolved callable."""
    seen: Set[int] = set()
    while id(target) not in seen:
        seen.add(id(target))
        if getattr(target, "__name__", None) == "__call__":
            owner = getattr(target, "__self__", None)
            if owner is not None and callable(owner):
                target = owner
                continue
        if isinstance(target, functools.partial):
            target = target.func
            continue
        break
    descriptor_owner = getattr(target, "__objclass__", None)
    if getattr(target, "__name__", None) == "__get__":
        descriptor_binding_target = _CALLABLE_DESCRIPTOR_BINDING_TARGETS.get(
            descriptor_owner
        )
        if descriptor_binding_target is not None:
            return descriptor_binding_target
    if descriptor_owner is operator.attrgetter:
        return "operator.attrgetter"
    if descriptor_owner is operator.itemgetter:
        return "operator.itemgetter"
    if descriptor_owner is operator.methodcaller:
        return "operator.methodcaller"
    if descriptor_owner is type and getattr(target, "__name__", None) == "__call__":
        return "builtins.type.__call__"
    if descriptor_owner is types.FunctionType:
        return "types.FunctionType"
    if descriptor_owner is types.MethodType:
        return "types.MethodType"
    if descriptor_owner is classmethod:
        return "builtins.classmethod"
    if descriptor_owner is staticmethod:
        return "builtins.staticmethod"
    if target is functools.partial.__new__:
        return "functools.partial"
    if target is type.__new__:
        return "builtins.type.__new__"
    if target is classmethod or target is classmethod.__new__:
        return "builtins.classmethod"
    if target is staticmethod or target is staticmethod.__new__:
        return "builtins.staticmethod"
    if target is types.FunctionType or target is types.FunctionType.__new__:
        return "types.FunctionType"
    if target is types.MethodType or target is types.MethodType.__new__:
        return "types.MethodType"
    if target is map.__new__:
        return "builtins.map"
    if target is itertools.accumulate.__new__:
        return "itertools.accumulate"
    if target is itertools.groupby.__new__:
        return "itertools.groupby"
    if target is itertools.starmap.__new__:
        return "itertools.starmap"
    if target is operator.attrgetter.__new__:
        return "operator.attrgetter"
    if target is operator.itemgetter.__new__:
        return "operator.itemgetter"
    if target is operator.methodcaller.__new__:
        return "operator.methodcaller"
    return _get_target_name_for_check(target)


def _with_full_key(message: str, full_key: str) -> str:
    return f"{message}\nfull_key: {full_key}" if full_key else message


def _resolved_from_note(target_name: str, resolved_from: str) -> str:
    return "" if resolved_from == target_name else f" (resolved from '{resolved_from}')"


def _authorize_target_name(
    target_name: str,
    resolved_from: str,
    full_key: str,
    *,
    resolved_from_is_alias: bool = False,
) -> None:
    canonical_target = _get_os_alias_target(target_name)
    resolved_note = _resolved_from_note(canonical_target, resolved_from)
    if _is_uncontrolled_execution_target(canonical_target):
        msg = dedent(f"""\
            Target '{canonical_target}'{resolved_note} is blocklisted because it allows
            config data to control executable behavior or belongs to an
            execution-capable target family. It cannot be authorized with
            HYDRA_INSTANTIATE_ALLOWLIST_OVERRIDE.""")
        raise InstantiationException(_with_full_key(msg, full_key))
    if canonical_target not in DEFAULT_BLOCKLISTED_MODULES:
        return

    allowlist = os.environ.get("HYDRA_INSTANTIATE_ALLOWLIST_OVERRIDE", "")
    allowlist_entries = allowlist.split(":")
    if (
        target_name in allowlist_entries
        or canonical_target in allowlist_entries
        or (resolved_from_is_alias and resolved_from in allowlist_entries)
    ):
        return
    msg = dedent(
        f"""\
        Target '{canonical_target}'{resolved_note} is blocklisted and cannot be instantiated from config
        to prevent security vulnerabilities, set env var
        HYDRA_INSTANTIATE_ALLOWLIST_OVERRIDE={canonical_target}:<other allowlisted targets> to bypass"""
    )
    raise InstantiationException(_with_full_key(msg, full_key))


def _authorize_discovery_path(
    target: Callable[..., Any],
    args: Tuple[Any, ...],
    kwargs: Dict[str, Any],
    full_key: str,
) -> Union[str, None]:
    target_name = _get_resolved_target_name_for_check(target)
    if target_name not in DISCOVERY_TARGETS:
        return None
    path = args[0] if args else kwargs.get("path")
    if not isinstance(path, str):
        return None
    _authorize_target_name(path, path, full_key)
    return path


def _authorize_callable_result(
    result: Callable[..., Any],
    resolved_from: str,
    full_key: str,
    *,
    resolved_from_is_alias: bool = False,
) -> None:
    resolved_name = _get_os_alias_target(_get_resolved_target_name_for_check(result))
    _authorize_target_name(
        resolved_name,
        resolved_from,
        full_key,
        resolved_from_is_alias=resolved_from_is_alias,
    )


def _authorize_target_invocation(
    target: Callable[..., Any],
    args: Tuple[Any, ...],
    kwargs: Dict[str, Any],
    full_key: str,
    *,
    allow_incomplete_partial: bool = False,
) -> None:
    target_name = _get_resolved_target_name_for_check(target)
    if target_name in _NON_CALLABLE_MOCK_TARGETS:
        unsafe_parameters = sorted(
            set(kwargs).difference(_NON_CALLABLE_MOCK_SAFE_PARAMETERS)
        )
        if len(args) > 1 or unsafe_parameters:
            unsafe_details = list(unsafe_parameters)
            if len(args) > 1:
                unsafe_details.append(f"{len(args)} positional arguments")
            joined = ", ".join(unsafe_details)
            msg = dedent(f"""\
                Target '{target_name}' cannot configure callable attributes,
                children, or wrappers from config (unsafe parameters: {joined}).
                Only one positional spec and the name, spec, and spec_set keyword
                parameters are allowed. This restriction cannot be bypassed with
                HYDRA_INSTANTIATE_ALLOWLIST_OVERRIDE.""")
            raise InstantiationException(_with_full_key(msg, full_key))

    if getattr(target, "__name__", None) in {"__call__", "__new__"}:
        module = getattr(target, "__module__", None)
        qualname = getattr(target, "__qualname__", "")
        owner_qualname, separator, _ = qualname.rpartition(".")
        if module is not None and separator and "<locals>" not in owner_qualname:
            try:
                owner = _locate(f"{module}.{owner_qualname}")
            except Exception:
                owner = None
            if isinstance(owner, type) and issubclass(owner, type):
                msg = dedent(f"""\
                    Target '{target_name}' cannot be used for dynamic class construction
                    from config. Metaclass constructor methods cannot be authorized with
                    HYDRA_INSTANTIATE_ALLOWLIST_OVERRIDE.""")
                raise InstantiationException(_with_full_key(msg, full_key))

    if not isinstance(target, type) or not issubclass(target, type):
        return
    if allow_incomplete_partial and len(args) <= 1 and not kwargs:
        return
    if len(args) == 1 and not kwargs:
        return
    msg = dedent(f"""\
        Target '{target_name}' cannot be used for dynamic class construction
        from config. Only one-argument type(obj) introspection is allowed, and
        this restriction cannot be bypassed with HYDRA_INSTANTIATE_ALLOWLIST_OVERRIDE.""")
    raise InstantiationException(_with_full_key(msg, full_key))


class _DeferredTarget(functools.partial):  # type: ignore[type-arg]
    """Authorize callable results when a Hydra partial is invoked."""

    _hydra_resolved_from: str
    _hydra_full_key: str

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        effective_args = self.args + args
        effective_kwargs = {**(self.keywords or {}), **kwargs}
        _authorize_target_invocation(
            self.func,
            effective_args,
            effective_kwargs,
            self._hydra_full_key,
        )
        discovery_path = _authorize_discovery_path(
            self.func,
            effective_args,
            effective_kwargs,
            self._hydra_full_key,
        )
        result = super().__call__(*args, **kwargs)
        return _mediate_target_result(
            result,
            discovery_path or self._hydra_resolved_from,
            self._hydra_full_key,
            resolved_from_is_alias=discovery_path is not None,
        )


def _mediate_target_result(
    result: Any,
    resolved_from: str,
    full_key: str,
    *,
    resolved_from_is_alias: bool = False,
) -> Any:
    if isinstance(result, functools.partial) and type(result) is not _DeferredTarget:
        if type(result) is not functools.partial:
            msg = dedent("""\
                Callable targets cannot return partial subclasses because overrides
                can hide their invocation behavior. Return an exact functools.partial
                or use Hydra's '_partial_: true' support instead.""")
            raise InstantiationException(_with_full_key(msg, full_key))
        deferred = _DeferredTarget(
            result.func,
            *result.args,
            **(result.keywords or {}),
        )
        deferred.__dict__.update(result.__dict__)
        deferred._hydra_resolved_from = resolved_from
        deferred._hydra_full_key = full_key
        result = deferred
    if callable(result):
        _authorize_callable_result(
            result,
            resolved_from,
            full_key,
            resolved_from_is_alias=resolved_from_is_alias,
        )
    return result


def _warn_direct_functools_partial_target() -> None:
    stacklevel = 1
    frame = inspect.currentframe()
    while frame is not None:
        if frame.f_code.co_filename != __file__:
            break
        stacklevel += 1
        frame = frame.f_back
    deprecation_warning(
        dedent("""\
            Using '_target_: functools.partial' is deprecated. Set '_target_' to
            the effective callable and use '_partial_: true' instead. Direct
            functools.partial targets will become an error in Hydra 1.5."""),
        stacklevel=stacklevel,
    )


def _extract_pos_args(input_args: Any, kwargs: Any) -> Tuple[Any, Any]:
    config_args = kwargs.pop(_Keys.ARGS, ())
    output_args = config_args

    if isinstance(config_args, Sequence):
        if len(input_args) > 0:
            output_args = input_args
    else:
        raise InstantiationException(
            f"Unsupported _args_ type: '{type(config_args).__name__}'. value: '{config_args}'"
        )

    return output_args, kwargs


def _call_target(
    _target_: Callable[..., Any],
    _partial_: bool,
    args: Tuple[Any, ...],
    kwargs: Dict[str, Any],
    full_key: str,
) -> Any:
    """Call target (type) with args and kwargs."""
    try:
        args, kwargs = _extract_pos_args(args, kwargs)
        # detaching configs from parent.
        # At this time, everything is resolved and the parent link can cause
        # issues when serializing objects in some scenarios.
        for arg in args:
            if OmegaConf.is_config(arg):
                arg._set_parent(None)
        for v in kwargs.values():
            if OmegaConf.is_config(v):
                v._set_parent(None)
    except Exception as e:
        msg = (
            f"Error in collecting args and kwargs for '{_convert_target_to_string(_target_)}':"
            + f"\n{repr(e)}"
        )
        if full_key:
            msg += f"\nfull_key: {full_key}"

        raise InstantiationException(msg) from e

    resolved_target_name = _get_resolved_target_name_for_check(_target_)
    _authorize_target_invocation(
        _target_,
        args,
        kwargs,
        full_key,
        allow_incomplete_partial=_partial_,
    )
    discovery_path = _authorize_discovery_path(_target_, args, kwargs, full_key)

    try:
        if _partial_:
            deferred = _DeferredTarget(_target_, *args, **kwargs)
            deferred._hydra_resolved_from = discovery_path or resolved_target_name
            deferred._hydra_full_key = full_key
            return deferred
        result = _target_(*args, **kwargs)
    except Exception as e:
        if _partial_:
            msg = (
                f"Error in creating partial({_convert_target_to_string(_target_)}, ...) object:"
                + f"\n{repr(e)}"
            )
        else:
            msg = f"Error in call to target '{_convert_target_to_string(_target_)}':\n{repr(e)}"
        raise InstantiationException(_with_full_key(msg, full_key)) from e

    return _mediate_target_result(
        result,
        discovery_path or resolved_target_name,
        full_key,
        resolved_from_is_alias=discovery_path is not None,
    )


def _convert_target_to_string(t: Any) -> Any:
    if callable(t) and hasattr(t, "__qualname__"):
        return f"{t.__module__}.{t.__qualname__}"
    else:
        return t


def _prepare_input_dict_or_list(d: Union[Dict[Any, Any], List[Any]]) -> Any:
    res: Any
    if isinstance(d, dict):
        res = {}
        for k, v in d.items():
            if k == "_target_":
                v = _convert_target_to_string(d["_target_"])
            elif isinstance(v, (dict, list)):
                v = _prepare_input_dict_or_list(v)
            res[k] = v
    elif isinstance(d, list):
        res = []
        for v in d:
            if isinstance(v, (list, dict)):
                v = _prepare_input_dict_or_list(v)
            res.append(v)
    else:
        assert False
    return res


def _resolve_target(
    target: Union[str, type, Callable[..., Any]], full_key: str
) -> Union[type, Callable[..., Any]]:
    """Resolve target string, type or callable into type or callable."""
    if isinstance(target, str) or callable(target):
        target_name = (
            target
            if isinstance(target, str)
            else _get_os_alias_target(_get_resolved_target_name_for_check(target))
        )
        _authorize_target_name(target_name, target_name, full_key)

        resolved_name = target_name
        if isinstance(target, str):
            resolved_from = target
            try:
                target = _locate(target)
            except Exception as e:
                msg = f"Error locating target '{target}', set env var HYDRA_FULL_ERROR=1 to see chained exception."
                if full_key:
                    msg += f"\nfull_key: {full_key}"
                raise InstantiationException(msg) from e

            resolved_name = _get_os_alias_target(
                _get_resolved_target_name_for_check(target)
            )
            if resolved_name != target_name:
                _authorize_target_name(
                    resolved_name,
                    resolved_from,
                    full_key,
                    resolved_from_is_alias=True,
                )

        if resolved_name == "functools.partial":
            _warn_direct_functools_partial_target()
    if not callable(target):
        msg = f"Expected a callable target, got '{target}' of type '{type(target).__name__}'"
        if full_key:
            msg += f"\nfull_key: {full_key}"
        raise InstantiationException(msg)
    return target


def instantiate(config: Any, *args: Any, **kwargs: Any) -> Any:
    """
    :param config: An config object describing what to call and what params to use.
                   In addition to the parameters, the config must contain:
                   _target_ : target class or callable name (str)
                   And may contain:
                   _args_: List-like of positional arguments to pass to the target
                   _recursive_: Construct nested objects as well (bool).
                                True by default.
                                may be overridden via a _recursive_ key in
                                the kwargs
                   _convert_: Conversion strategy
                        none    : Passed objects are DictConfig and ListConfig, default
                        partial : Passed objects are converted to dict and list, with
                                  the exception of Structured Configs (and their fields).
                        object  : Passed objects are converted to dict and list.
                                  Structured Configs are converted to instances of the
                                  backing dataclass / attr class.
                        all     : Passed objects are dicts, lists and primitives without
                                  a trace of OmegaConf containers. Structured configs
                                  are converted to dicts / lists too.
                   _partial_: If True, return functools.partial wrapped method or object
                              False by default. Configure per target.
    :param args: Optional positional parameters pass-through
    :param kwargs: Optional named parameters to override
                   parameters in the config object. Parameters not present
                   in the config objects are being passed as is to the target.
                   IMPORTANT: dataclasses instances in kwargs are interpreted as config
                              and cannot be used as passthrough
    :return: if _target_ is a class name: the instantiated object
             if _target_ is a callable: the return value of the call
    """

    # Return None if config is None
    if config is None:
        return None

    # TargetConf edge case
    if isinstance(config, TargetConf) and config._target_ == "???":
        # Specific check to give a good warning about failure to annotate _target_ as a string.
        raise InstantiationException(
            dedent(
                f"""\
                Config has missing value for key `_target_`, cannot instantiate.
                Config type: {type(config).__name__}
                Check that the `_target_` key in your dataclass is properly annotated and overridden.
                A common problem is forgetting to annotate _target_ as a string : '_target_: str = ...'"""
            )
        )
        # TODO: print full key

    if isinstance(config, (dict, list)):
        config = _prepare_input_dict_or_list(config)

    kwargs = _prepare_input_dict_or_list(kwargs)

    # Structured Config always converted first to OmegaConf
    if is_structured_config(config) or isinstance(config, (dict, list)):
        config = OmegaConf.structured(config, flags={"allow_objects": True})

    if OmegaConf.is_dict(config):
        # Finalize config (convert targets to strings, merge with kwargs)
        config_copy = copy.deepcopy(config)
        config_copy._set_flag(
            flags=["allow_objects", "struct", "readonly"], values=[True, False, False]
        )
        config_copy._set_parent(config._get_parent())
        config = config_copy

        if kwargs:
            config = OmegaConf.merge(config, kwargs)

        OmegaConf.resolve(config)

        _recursive_ = config.pop(_Keys.RECURSIVE, True)
        _convert_ = config.pop(_Keys.CONVERT, ConvertMode.NONE)
        _partial_ = config.pop(_Keys.PARTIAL, False)

        return instantiate_node(
            config, *args, recursive=_recursive_, convert=_convert_, partial=_partial_
        )
    elif OmegaConf.is_list(config):
        # Finalize config (convert targets to strings, merge with kwargs)
        config_copy = copy.deepcopy(config)
        config_copy._set_flag(
            flags=["allow_objects", "struct", "readonly"], values=[True, False, False]
        )
        config_copy._set_parent(config._get_parent())
        config = config_copy

        OmegaConf.resolve(config)

        _recursive_ = kwargs.pop(_Keys.RECURSIVE, True)
        _convert_ = kwargs.pop(_Keys.CONVERT, ConvertMode.NONE)
        _partial_ = kwargs.pop(_Keys.PARTIAL, False)

        if _partial_:
            raise InstantiationException(
                "The _partial_ keyword is not compatible with top-level list instantiation"
            )

        return instantiate_node(
            config, *args, recursive=_recursive_, convert=_convert_, partial=_partial_
        )
    else:
        raise InstantiationException(
            dedent(
                f"""\
                Cannot instantiate config of type {type(config).__name__}.
                Top level config must be an OmegaConf DictConfig/ListConfig object,
                a plain dict/list, or a Structured Config class or instance."""
            )
        )


def _convert_node(node: Any, convert: Union[ConvertMode, str]) -> Any:
    if OmegaConf.is_config(node):
        if convert == ConvertMode.ALL:
            node = OmegaConf.to_container(node, resolve=True)
        elif convert == ConvertMode.PARTIAL:
            node = OmegaConf.to_container(
                node, resolve=True, structured_config_mode=SCMode.DICT_CONFIG
            )
        elif convert == ConvertMode.OBJECT:
            node = OmegaConf.to_container(
                node, resolve=True, structured_config_mode=SCMode.INSTANTIATE
            )
    return node


def instantiate_node(
    node: Any,
    *args: Any,
    convert: Union[str, ConvertMode] = ConvertMode.NONE,
    recursive: bool = True,
    partial: bool = False,
) -> Any:
    # Return None if config is None
    if node is None or (OmegaConf.is_config(node) and node._is_none()):
        return None

    if not OmegaConf.is_config(node):
        return node

    # Override parent modes from config if specified
    if OmegaConf.is_dict(node):
        # using getitem instead of get(key, default) because OmegaConf will raise an exception
        # if the key type is incompatible on get.
        convert = node[_Keys.CONVERT] if _Keys.CONVERT in node else convert
        recursive = node[_Keys.RECURSIVE] if _Keys.RECURSIVE in node else recursive
        partial = node[_Keys.PARTIAL] if _Keys.PARTIAL in node else partial

    full_key = node._get_full_key(None)

    if not isinstance(recursive, bool):
        msg = f"Instantiation: _recursive_ flag must be a bool, got {type(recursive)}"
        if full_key:
            msg += f"\nfull_key: {full_key}"
        raise TypeError(msg)

    if not isinstance(partial, bool):
        msg = f"Instantiation: _partial_ flag must be a bool, got {type( partial )}"
        if node and full_key:
            msg += f"\nfull_key: {full_key}"
        raise TypeError(msg)

    # If OmegaConf list, create new list of instances if recursive
    if OmegaConf.is_list(node):
        items = [
            instantiate_node(item, convert=convert, recursive=recursive)
            for item in node._iter_ex(resolve=True)
        ]

        if convert in (ConvertMode.ALL, ConvertMode.PARTIAL, ConvertMode.OBJECT):
            # If ALL or PARTIAL or OBJECT, use plain list as container
            return items
        else:
            # Otherwise, use ListConfig as container
            lst = OmegaConf.create(items, flags={"allow_objects": True})
            lst._set_parent(node)
            return lst

    elif OmegaConf.is_dict(node):
        exclude_keys = set({"_target_", "_convert_", "_recursive_", "_partial_"})
        if _is_target(node):
            _target_ = _resolve_target(node.get(_Keys.TARGET), full_key)
            kwargs = {}
            is_partial = node.get("_partial_", False) or partial
            for key in node.keys():
                if key not in exclude_keys:
                    if OmegaConf.is_missing(node, key) and is_partial:
                        continue
                    value = node[key]
                    if recursive:
                        value = instantiate_node(
                            value, convert=convert, recursive=recursive
                        )
                    kwargs[key] = _convert_node(value, convert)

            return _call_target(_target_, partial, args, kwargs, full_key)
        else:
            # If ALL or PARTIAL non structured or OBJECT non structured,
            # instantiate in dict and resolve interpolations eagerly.
            if convert == ConvertMode.ALL or (
                convert in (ConvertMode.PARTIAL, ConvertMode.OBJECT)
                and node._metadata.object_type in (None, dict)
            ):
                dict_items = {}
                for key, value in node.items():
                    # list items inherits recursive flag from the containing dict.
                    dict_items[key] = instantiate_node(
                        value, convert=convert, recursive=recursive
                    )
                return dict_items
            else:
                # Otherwise use DictConfig and resolve interpolations lazily.
                cfg = OmegaConf.create({}, flags={"allow_objects": True})
                for key, value in node.items():
                    cfg[key] = instantiate_node(
                        value, convert=convert, recursive=recursive
                    )
                cfg._set_parent(node)
                cfg._metadata.object_type = node._metadata.object_type
                if convert == ConvertMode.OBJECT:
                    return OmegaConf.to_object(cfg)
                return cfg

    else:
        assert False, f"Unexpected config type : {type(node).__name__}"

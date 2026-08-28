# SPDX-FileCopyrightText: Contributors to Hydra
# SPDX-License-Identifier: MIT

import functools
import itertools
import operator
import os
import types
from textwrap import dedent
from typing import Any, Callable, Dict, Set, Tuple, Union

from hydra._internal.utils import _locate
from hydra.errors import InstantiationException

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
    "functools.partial.__call__",
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
    property: "builtins.property.__get__",
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
UNCONTROLLED_EXECUTION_TARGETS = (
    {
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
    }
    | CALLBACK_DISPATCH_TARGETS
    | CALLABLE_WRAPPER_TARGETS
)

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
            return f"{public_module}.{target[len(module_prefix) :]}"
    return target


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
        descriptor_binding_target = (
            _CALLABLE_DESCRIPTOR_BINDING_TARGETS.get(descriptor_owner)
            if isinstance(descriptor_owner, type)
            else None
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


def _authorize_resolved_target_identity(
    target: Callable[..., Any],
    resolved_from: str,
    full_key: str,
) -> str:
    """Authorize the canonical identity of a callable resolved from a dotpath."""
    resolved_name = _get_os_alias_target(_get_resolved_target_name_for_check(target))
    if resolved_name != resolved_from:
        _authorize_target_name(
            resolved_name,
            resolved_from,
            full_key,
            resolved_from_is_alias=True,
        )
    return resolved_name


def _authorize_target_invocation(
    target: Callable[..., Any],
    args: Tuple[Any, ...],
    kwargs: Dict[str, Any],
    full_key: str,
    *,
    allow_incomplete_partial: bool = False,
) -> None:
    target_name = _get_resolved_target_name_for_check(target)
    if target_name == "builtins.iter" and len(args) == 2:
        msg = dedent(
            """\
            Target 'builtins.iter' cannot use its two-argument callback form from
            config because callback execution is deferred beyond instantiate's
            target authorization. Use one-argument iter(iterable), or perform the
            callback iteration in trusted Python code. This restriction cannot be
            bypassed with HYDRA_INSTANTIATE_ALLOWLIST_OVERRIDE."""
        )
        raise InstantiationException(_with_full_key(msg, full_key))

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

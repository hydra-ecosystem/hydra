# SPDX-FileCopyrightText: Contributors to Hydra
# SPDX-License-Identifier: MIT

import functools
import hashlib
import itertools
import json
import operator
import os
import sys
import types
from contextlib import contextmanager, nullcontext
from contextvars import Context, ContextVar
from textwrap import dedent
from typing import (
    Any,
    Callable,
    Dict,
    FrozenSet,
    Iterator,
    Mapping,
    NamedTuple,
    Optional,
    Set,
    Tuple,
    Union,
    cast,
)

from hydra._internal.utils import _locate
from hydra.errors import InstantiationException

# Threat model: declarative instantiation and logging configuration may be
# untrusted. This module provides best-effort defense in depth for Hydra 1.3;
# it is not a complete security boundary because trusted installed callables
# can indirectly dispatch operations that never appear as _target_ values.
# The policy prevents configuration from changing Hydra's authorization state
# or existing Python code.
#
# These operations are fully named by the target itself. Trusted users may
# authorize them with HYDRA_INSTANTIATE_ALLOWLIST_OVERRIDE.
DEFAULT_BLOCKLISTED_MODULES = frozenset(
    {
        "_sitebuiltins.Quitter",
        "builtins.exit",
        "builtins.quit",
        "os.kill",
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
)

# These dispatchers execute caller-supplied callables and return their results
# directly or through a container, iterator, or deferred result. That allows
# selection, wrapping, and invocation to happen outside instantiate's immediate
# callable-result authorization.
CALLBACK_DISPATCH_TARGETS = frozenset(
    {
        "builtins.filter",
        "builtins.map",
        "concurrent.futures._base.Executor.map",
        "concurrent.futures._base.Executor.submit",
        "concurrent.futures.process.ProcessPoolExecutor.map",
        "concurrent.futures.process.ProcessPoolExecutor.submit",
        "concurrent.futures.thread.ThreadPoolExecutor.submit",
        "functools.partial.__call__",
        "functools.reduce",
        "itertools.accumulate",
        "itertools.dropwhile",
        "itertools.filterfalse",
        "itertools.groupby",
        "itertools.starmap",
        "itertools.takewhile",
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
)

_CALLABLE_DESCRIPTOR_BINDING_TARGETS: Mapping[type, str] = types.MappingProxyType(
    {
        property: "builtins.property.__get__",
        types.ClassMethodDescriptorType: "types.ClassMethodDescriptorType.__get__",
        types.FunctionType: "types.FunctionType.__get__",
        types.MethodDescriptorType: "types.MethodDescriptorType.__get__",
        types.WrapperDescriptorType: "types.WrapperDescriptorType.__get__",
    }
)

# These helpers construct, bind, or relabel callable wrappers whose later
# invocation can return an unauthorized callable outside instantiate's result
# mediation.
CALLABLE_WRAPPER_TARGETS = frozenset(
    {
        "abc.abstractmethod",
        "builtins.classmethod",
        "builtins.property",
        "builtins.staticmethod",
        "contextlib.AsyncContextDecorator.__call__",
        "contextlib.ContextDecorator.__call__",
        "contextlib.asynccontextmanager",
        "contextlib.contextmanager",
        "functools.cache",
        "functools.cached_property",
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
        "types.coroutine",
        "unittest.mock.AsyncMock",
        "unittest.mock.MagicMock",
        "unittest.mock.Mock",
        "unittest.mock.PropertyMock",
        "unittest.mock.create_autospec",
        "unittest.mock.mock_open",
    }
) | frozenset(_CALLABLE_DESCRIPTOR_BINDING_TARGETS.values())

_NON_CALLABLE_MOCK_TARGETS = frozenset(
    {
        "unittest.mock.NonCallableMagicMock",
        "unittest.mock.NonCallableMock",
    }
)
_NON_CALLABLE_MOCK_SAFE_PARAMETERS = frozenset({"name", "spec", "spec_set"})

# These targets allow config data to select or supply executable behavior.
# They cannot be authorized with HYDRA_INSTANTIATE_ALLOWLIST_OVERRIDE.
UNCONTROLLED_EXECUTION_TARGETS = frozenset(
    {
        "_sitebuiltins._Helper",
        "builtins.__build_class__",
        "builtins.__import__",
        "builtins.compile",
        "builtins.eval",
        "builtins.exec",
        "builtins.frame.clear",
        "builtins.getset_descriptor.__get__",
        "builtins.help",
        "builtins.locals",
        "builtins.member_descriptor.__get__",
        "inspect",
        "builtins.type.__call__",
        "builtins.type.__new__",
        # vars() exposes the caller's locals, while vars(obj) exposes an object
        # namespace selected by config. Block both forms intentionally rather
        # than maintain an argument-sensitive exception for vars(obj).
        "builtins.vars",
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
        "os.putenv",
        "os.startfile",
        "os.system",
        "os.unsetenv",
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
        "sys.exc_info",
        "sys.exception",
        "sys._current_exceptions",
        "sys._current_frames",
        "sys._getframe",
        "sys.getobjects",
        "builtins.str.format",
        "builtins.str.format_map",
        "logging.Formatter",
        "logging.StrFormatStyle",
        "string.Formatter._vformat",
        "string.Formatter.format",
        "string.Formatter.get_field",
        "string.Formatter.vformat",
        "_asyncio.Task.get_stack",
        "asyncio.base_tasks._task_get_stack",
        "asyncio.tasks.Task.get_stack",
        "traceback.clear_frames",
        "traceback._walk_tb_with_full_positions",
        "traceback.walk_stack",
        "traceback.walk_tb",
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
    "gc.",
    "inspect.",
    "os.exec",
    "os.spawn",
    "logging.config.",
    "doctest.",
    "shelve.",
    "trace.",
    # PyYAML exposes Python-object loading and constructor dispatch. Keep only
    # exact safe load/dump functions available.
    "yaml.",
    "pydoc.",
    "pdb.",
    "bdb.",
)

UNCONTROLLED_EXECUTION_TARGET_PREFIX_EXCEPTIONS = frozenset(
    {
        "doctest.DocTest",
        "doctest.DocTestParser",
        "doctest.Example",
        "pydoc.HTMLDoc",
        "pydoc.TextDoc",
        "trace.Trace",
        "yaml.safe_load",
        "yaml.safe_load_all",
        "yaml.safe_dump",
        "yaml.safe_dump_all",
    }
)

DISCOVERY_TARGETS = frozenset(
    {
        "hydra._internal.utils._locate",
        "hydra.utils.get_class",
        "hydra.utils.get_method",
        "hydra.utils.get_static_method",
        "hydra.utils.get_object",
    }
)

_PROTECTED_FUNCTION_ATTRIBUTES = frozenset(
    {
        "__annotations__",
        "__annotate__",
        "__builtins__",
        "__closure__",
        "__code__",
        "__defaults__",
        "__dict__",
        "__globals__",
        "__kwdefaults__",
    }
)


class _TargetPolicySnapshot(NamedTuple):
    default_blocklisted_modules: FrozenSet[str]
    callable_descriptor_binding_targets: Tuple[Tuple[type, str], ...]
    non_callable_mock_targets: FrozenSet[str]
    non_callable_mock_safe_parameters: FrozenSet[str]
    uncontrolled_execution_targets: FrozenSet[str]
    uncontrolled_execution_target_prefixes: Tuple[str, ...]
    uncontrolled_execution_target_prefix_exceptions: FrozenSet[str]
    discovery_targets: FrozenSet[str]
    protected_function_attributes: FrozenSet[str]
    protected_objects: Tuple[Any, ...]


_TARGET_POLICY_CONTEXT: ContextVar[Optional[_TargetPolicySnapshot]] = ContextVar(
    "hydra_target_policy", default=None
)
_TRUSTED_INTERNAL_TARGET_CONTEXT: ContextVar[Optional[str]] = ContextVar(
    "hydra_trusted_internal_target", default=None
)


def _checked_frozenset(name: str, value: Any) -> FrozenSet[str]:
    if type(value) is not frozenset or any(type(item) is not str for item in value):
        raise InstantiationException(
            f"Hydra target policy integrity check failed for {name}"
        )
    return value


def _capture_target_policy() -> _TargetPolicySnapshot:
    if type(UNCONTROLLED_EXECUTION_TARGET_PREFIXES) is not tuple or any(
        type(item) is not str for item in UNCONTROLLED_EXECUTION_TARGET_PREFIXES
    ):
        raise InstantiationException(
            "Hydra target policy integrity check failed for "
            "UNCONTROLLED_EXECUTION_TARGET_PREFIXES"
        )
    if type(_CALLABLE_DESCRIPTOR_BINDING_TARGETS) is not types.MappingProxyType:
        raise InstantiationException(
            "Hydra target policy integrity check failed for "
            "_CALLABLE_DESCRIPTOR_BINDING_TARGETS"
        )
    descriptor_items = tuple(_CALLABLE_DESCRIPTOR_BINDING_TARGETS.items())
    if any(
        not isinstance(key, type) or type(value) is not str
        for key, value in descriptor_items
    ):
        raise InstantiationException(
            "Hydra target policy integrity check failed for "
            "_CALLABLE_DESCRIPTOR_BINDING_TARGETS"
        )

    protected_objects = (
        DEFAULT_BLOCKLISTED_MODULES,
        CALLBACK_DISPATCH_TARGETS,
        _CALLABLE_DESCRIPTOR_BINDING_TARGETS,
        CALLABLE_WRAPPER_TARGETS,
        _NON_CALLABLE_MOCK_TARGETS,
        _NON_CALLABLE_MOCK_SAFE_PARAMETERS,
        UNCONTROLLED_EXECUTION_TARGETS,
        UNCONTROLLED_EXECUTION_TARGET_PREFIXES,
        UNCONTROLLED_EXECUTION_TARGET_PREFIX_EXCEPTIONS,
        DISCOVERY_TARGETS,
        _PROTECTED_FUNCTION_ATTRIBUTES,
        _TARGET_POLICY_CONTEXT,
        _TRUSTED_INTERNAL_TARGET_CONTEXT,
    )
    return _TargetPolicySnapshot(
        default_blocklisted_modules=_checked_frozenset(
            "DEFAULT_BLOCKLISTED_MODULES", DEFAULT_BLOCKLISTED_MODULES
        ),
        callable_descriptor_binding_targets=descriptor_items,
        non_callable_mock_targets=_checked_frozenset(
            "_NON_CALLABLE_MOCK_TARGETS", _NON_CALLABLE_MOCK_TARGETS
        ),
        non_callable_mock_safe_parameters=_checked_frozenset(
            "_NON_CALLABLE_MOCK_SAFE_PARAMETERS", _NON_CALLABLE_MOCK_SAFE_PARAMETERS
        ),
        uncontrolled_execution_targets=_checked_frozenset(
            "UNCONTROLLED_EXECUTION_TARGETS", UNCONTROLLED_EXECUTION_TARGETS
        ),
        uncontrolled_execution_target_prefixes=UNCONTROLLED_EXECUTION_TARGET_PREFIXES,
        uncontrolled_execution_target_prefix_exceptions=_checked_frozenset(
            "UNCONTROLLED_EXECUTION_TARGET_PREFIX_EXCEPTIONS",
            UNCONTROLLED_EXECUTION_TARGET_PREFIX_EXCEPTIONS,
        ),
        discovery_targets=_checked_frozenset("DISCOVERY_TARGETS", DISCOVERY_TARGETS),
        protected_function_attributes=_checked_frozenset(
            "_PROTECTED_FUNCTION_ATTRIBUTES", _PROTECTED_FUNCTION_ATTRIBUTES
        ),
        protected_objects=protected_objects,
    )


def _target_policy_digest(policy: _TargetPolicySnapshot) -> str:
    payload = {
        "schema": "hydra-target-policy-v1",
        "default_blocklisted_modules": sorted(policy.default_blocklisted_modules),
        "callable_descriptor_binding_targets": sorted(
            (f"{key.__module__}.{key.__qualname__}", value)
            for key, value in policy.callable_descriptor_binding_targets
        ),
        "non_callable_mock_targets": sorted(policy.non_callable_mock_targets),
        "non_callable_mock_safe_parameters": sorted(
            policy.non_callable_mock_safe_parameters
        ),
        "uncontrolled_execution_targets": sorted(policy.uncontrolled_execution_targets),
        "uncontrolled_execution_target_prefixes": list(
            policy.uncontrolled_execution_target_prefixes
        ),
        "uncontrolled_execution_target_prefix_exceptions": sorted(
            policy.uncontrolled_execution_target_prefix_exceptions
        ),
        "discovery_targets": sorted(policy.discovery_targets),
        "protected_function_attributes": sorted(policy.protected_function_attributes),
    }
    canonical = json.dumps(
        payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True
    ).encode()
    return hashlib.sha256(canonical).hexdigest()


_EXPECTED_TARGET_POLICY_DIGEST = (
    "73bf7f617a627fa54bc01889ed4d923471c4b5e39fbd40e119d7f0d485c8a36b"
)


def _validated_target_policy(expected_digest: str) -> _TargetPolicySnapshot:
    policy = _capture_target_policy()
    if _target_policy_digest(policy) != expected_digest:
        raise InstantiationException(
            "Hydra target policy integrity check failed; refusing to resolve "
            "config-selected targets"
        )
    return policy


@contextmanager
def _target_policy_context(policy: _TargetPolicySnapshot) -> Iterator[None]:
    token = _TARGET_POLICY_CONTEXT.set(policy)
    try:
        yield
    finally:
        _TARGET_POLICY_CONTEXT.reset(token)


def _current_target_policy() -> _TargetPolicySnapshot:
    policy = _TARGET_POLICY_CONTEXT.get()
    return _capture_target_policy() if policy is None else policy


@contextmanager
def _trusted_internal_target(target: str) -> Iterator[None]:
    token = _TRUSTED_INTERNAL_TARGET_CONTEXT.set(target)
    try:
        yield
    finally:
        _TRUSTED_INTERNAL_TARGET_CONTEXT.reset(token)


def _is_hydra_module_name(name: Any) -> bool:
    return type(name) is str and (name == "hydra" or name.startswith("hydra."))


def _is_hydra_internal_path(path: str) -> bool:
    return path == "hydra._internal" or path.startswith("hydra._internal.")


def _reject_protected_reference(reference: str, full_key: str) -> None:
    if reference == _TRUSTED_INTERNAL_TARGET_CONTEXT.get():
        return
    policy = _current_target_policy()
    protected_runtime_reference = (
        # Before Python 3.13, frame locals are plain dictionaries and cannot be
        # identified as frame state after a longer dotpath has traversed them.
        "f_locals" in reference.split(".")
        or any(
            reference == prefix or reference.startswith(f"{prefix}.")
            for prefix in ("sys.last_exc", "sys.last_traceback", "sys.last_value")
        )
    )
    if (
        not _is_hydra_internal_path(reference)
        and not protected_runtime_reference
        and not any(
            component in policy.protected_function_attributes
            for component in reference.split(".")
        )
    ):
        return
    raise InstantiationException(
        _with_full_key(
            dedent(
                f"""\
                Reference '{reference}' cannot be selected by declarative
                configuration because it exposes implementation state. Access it
                from trusted Python code instead."""
            ),
            full_key,
        )
    )


def _is_loaded_module_namespace(value: Any) -> bool:
    if type(value) is not dict:
        return False
    return any(
        isinstance(module, types.ModuleType) and vars(module) is value
        for module in tuple(sys.modules.values())
    )


def _is_frame_locals_proxy(value: Any) -> bool:
    value_type = type(value)
    return (
        value_type.__module__ == "builtins"
        and value_type.__name__ == "FrameLocalsProxy"
    )


def _is_protected_implementation_object(
    value: Any, policy: _TargetPolicySnapshot
) -> bool:
    if value is sys.modules or isinstance(value, _TargetPolicySnapshot):
        return True
    if type(value) in {types.CodeType, types.FrameType, types.TracebackType}:
        return True
    if _is_frame_locals_proxy(value):
        return True
    if any(value is protected for protected in policy.protected_objects):
        return True
    if _is_loaded_module_namespace(value):
        return True
    if isinstance(value, types.ModuleType):
        return _is_hydra_internal_path(value.__name__)
    if type(value) is types.FunctionType:
        return _is_hydra_internal_path(value.__module__)
    if type(value) is types.MethodType:
        return _is_hydra_internal_path(getattr(value.__func__, "__module__", ""))
    if isinstance(value, type):
        return _is_hydra_internal_path(value.__module__)
    return value is not None and _is_hydra_internal_path(type(value).__module__)


def _unwrap_method_wrapper_call(target: Any) -> Any:
    while type(target) is types.MethodWrapperType and target.__name__ == "__call__":
        target = target.__self__
    return target


def _get_bound_receiver(target: Any) -> Any:
    target = _unwrap_method_wrapper_call(target)
    if type(target) in {
        types.BuiltinMethodType,
        types.MethodType,
        types.MethodWrapperType,
    }:
        return target.__self__
    return None


def _reject_protected_callable_capability(
    target: Any,
    args: Tuple[Any, ...],
    resolved_from: str,
    full_key: str,
) -> None:
    receiver = _get_bound_receiver(target)
    unwrapped = _unwrap_method_wrapper_call(target)
    if (
        receiver is None
        and args
        and type(unwrapped)
        in {
            types.MethodDescriptorType,
            types.WrapperDescriptorType,
        }
    ):
        receiver = args[0]
    if not _is_protected_implementation_object(receiver, _current_target_policy()):
        return
    raise InstantiationException(
        _with_full_key(
            dedent(
                f"""\
                Target '{resolved_from}' operates on protected Hydra implementation
                state. Access it from trusted Python code instead."""
            ),
            full_key,
        )
    )


def _reject_code_metadata_access(
    target: Callable[..., Any], args: Tuple[Any, ...], full_key: str
) -> None:
    target_name = _get_resolved_target_name_for_check(target)
    bound_receiver = _get_bound_receiver(target)
    receiver: Any = None
    attribute: Any = None

    if target_name == "builtins.getattr":
        if len(args) >= 2:
            receiver, attribute = args[:2]
    elif target_name == "builtins.object.__getstate__" or (
        getattr(target, "__name__", None) == "__getstate__"
        and type(target) in {types.BuiltinMethodType, types.MethodDescriptorType}
    ):
        receiver = bound_receiver if bound_receiver is not None else args[0] if args else None
        attribute = "__dict__"
    elif (
        target_name
        in {
            "builtins.object.__getattribute__",
            "builtins.type.__getattribute__",
        }
        or getattr(target, "__name__", None) == "__getattribute__"
    ):
        if bound_receiver is not None:
            receiver = bound_receiver
            attribute = args[0] if args else None
        elif len(args) >= 2:
            receiver, attribute = args[:2]
    else:
        return

    policy = _current_target_policy()
    accesses_code_metadata = (
        type(receiver) is types.FunctionType
        or isinstance(receiver, (type, types.ModuleType))
    ) and attribute in policy.protected_function_attributes
    accesses_frame_locals = (
        type(receiver) is types.FrameType and attribute == "f_locals"
    )
    if not accesses_code_metadata and not accesses_frame_locals:
        return

    raise InstantiationException(
        _with_full_key(
            dedent(
                """\
                Declarative configuration cannot access Python function, class,
                module, or frame implementation metadata. Access it from trusted
                Python code instead."""
            ),
            full_key,
        )
    )


def _reject_protected_result(result: Any, resolved_from: str, full_key: str) -> None:
    if type(result) is _DeferredTarget:
        return
    trusted_target = _TRUSTED_INTERNAL_TARGET_CONTEXT.get()
    if trusted_target is not None and any(
        f"{cls.__module__}.{cls.__qualname__}" == trusted_target
        for cls in type(result).__mro__
    ):
        return
    policy = _current_target_policy()
    protected = _is_protected_implementation_object(result, policy)
    if callable(result):
        protected = protected or _is_protected_implementation_object(
            _get_bound_receiver(result), policy
        )
    if isinstance(result, Context):
        protected = protected or any(
            _is_protected_implementation_object(value, policy)
            for item in result.items()
            for value in item
        )
    if protected:
        raise InstantiationException(
            _with_full_key(
                dedent(
                    f"""\
                    Target '{resolved_from}' cannot return Hydra implementation
                    state, live Python frames or tracebacks, frame locals, code
                    objects, or loaded module state to declarative configuration.
                    Access it from trusted Python code instead."""
                ),
                full_key,
            )
        )


def _reject_code_or_policy_mutation(
    target: Callable[..., Any], args: Tuple[Any, ...], full_key: str
) -> None:
    target_name = _get_resolved_target_name_for_check(target)
    bound_receiver = _get_bound_receiver(target)
    attribute_mutators = {
        "builtins.delattr",
        "builtins.object.__delattr__",
        "builtins.object.__setattr__",
        "builtins.setattr",
        "builtins.type.__delattr__",
        "builtins.type.__setattr__",
    }
    mapping_mutators = {
        "builtins.dict.__delitem__",
        "builtins.dict.__ior__",
        "builtins.dict.__setitem__",
        "builtins.dict.clear",
        "builtins.dict.pop",
        "builtins.dict.popitem",
        "builtins.dict.setdefault",
        "builtins.dict.update",
        "operator.delitem",
        "operator.ior",
        "operator.setitem",
        "_operator.delitem",
        "_operator.ior",
        "_operator.setitem",
    }
    receiver: Any = None
    if target_name in {"builtins.delattr", "builtins.setattr"}:
        receiver = (
            args[0]
            if target is setattr or target is delattr
            else bound_receiver if bound_receiver is not None else args[0] if args else None
        )
    elif target_name in attribute_mutators:
        receiver = (
            bound_receiver if bound_receiver is not None else args[0] if args else None
        )
    elif target_name in mapping_mutators:
        receiver = (
            bound_receiver if bound_receiver is not None else args[0] if args else None
        )
    elif getattr(target, "__name__", None) in {"__delattr__", "__setattr__"}:
        receiver = (
            bound_receiver if bound_receiver is not None else args[0] if args else None
        )

    descriptor_types = (types.GetSetDescriptorType, types.MemberDescriptorType)
    if getattr(target, "__name__", None) in {"__delete__", "__set__"}:
        descriptor = _get_bound_receiver(target)
        if isinstance(descriptor, descriptor_types):
            receiver = args[0] if args else None
        elif args and isinstance(args[0], descriptor_types):
            receiver = args[1] if len(args) > 1 else None

    policy = _current_target_policy()
    if (
        type(receiver) is not types.FunctionType
        and not isinstance(receiver, type)
        and not isinstance(receiver, types.ModuleType)
        and type(receiver) is not types.CellType
        and not _is_protected_implementation_object(receiver, policy)
    ):
        return
    raise InstantiationException(
        _with_full_key(
            dedent(
                """\
                Declarative configuration cannot modify Python functions, classes,
                modules, or Hydra implementation state. Perform this mutation from
                trusted Python code instead."""
            ),
            full_key,
        )
    )


def _reject_process_environment_mutation(
    target: Callable[..., Any],
    args: Tuple[Any, ...],
    kwargs: Dict[str, Any],
    full_key: str,
) -> None:
    target_name = _get_os_alias_target(_get_resolved_target_name_for_check(target))
    if target_name in {"os.putenv", "os.unsetenv"}:
        mutates_environment = True
    else:
        method_name = getattr(target, "__name__", None)
        if target_name in {"builtins.delattr", "builtins.setattr"}:
            bound_receiver = _get_bound_receiver(target)
            receiver = (
                args[0]
                if target is setattr or target is delattr
                else bound_receiver
                if bound_receiver is not None
                else args[0] if args else None
            )
        elif target_name in {
            "builtins.object.__delattr__",
            "builtins.object.__setattr__",
            "builtins.type.__delattr__",
            "builtins.type.__setattr__",
        }:
            bound_receiver = _get_bound_receiver(target)
            receiver = (
                bound_receiver
                if bound_receiver is not None
                else args[0] if args else None
            )
        else:
            receiver = _get_bound_receiver(target)
            if receiver is None and args:
                receiver = args[0]
            if receiver is None:
                receiver = kwargs.get("self")
        environments = (os.environ, getattr(os, "environb", None))
        environment_state = tuple(
            state
            for environ in environments
            if environ is not None
            for state in (environ, getattr(environ, "_data", None), vars(environ))
        )
        mutates_environment = method_name in {
            "__delattr__",
            "__delitem__",
            "__init__",
            "__ior__",
            "__setattr__",
            "__setitem__",
            "clear",
            "delattr",
            "pop",
            "popitem",
            "setattr",
            "setdefault",
            "update",
        } and (
            isinstance(receiver, type(os.environ))
            or any(receiver is state for state in environment_state)
        )

    if mutates_environment:
        raise InstantiationException(
            _with_full_key(
                dedent(
                    f"""\
                    Target '{target_name}' cannot modify the process environment from
                    declarative configuration. Perform this mutation from trusted Python
                    code instead."""
                ),
                full_key,
            )
        )


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


def _get_policy_alias_target(target: str) -> str:
    """Return the canonical security identity for a configured target name."""
    for prefix, canonical_target in (
        ("abc.abstractclassmethod", "builtins.classmethod"),
        ("abc.abstractproperty", "builtins.property"),
        ("abc.abstractstaticmethod", "builtins.staticmethod"),
        ("builtins.property", "builtins.property"),
        ("collections.UserString.format", "builtins.str.format"),
        ("collections.UserString.format_map", "builtins.str.format_map"),
        ("enum.DynamicClassAttribute", "builtins.property"),
        ("enum.property", "builtins.property"),
        ("functools.cached_property", "functools.cached_property"),
        ("logging.Formatter", "logging.Formatter"),
        ("types.DynamicClassAttribute", "builtins.property"),
    ):
        if target == prefix or target.startswith(f"{prefix}."):
            return canonical_target
    return target


def _is_blocklisted_target(target: str) -> bool:
    policy = _current_target_policy()
    canonical_target = _get_os_alias_target(target)
    if (
        canonical_target in policy.default_blocklisted_modules
        or canonical_target in policy.uncontrolled_execution_targets
    ):
        return True
    if canonical_target in policy.uncontrolled_execution_target_prefix_exceptions:
        return False
    return canonical_target.startswith(policy.uncontrolled_execution_target_prefixes)


def _is_uncontrolled_execution_target(target: str) -> bool:
    policy = _current_target_policy()
    canonical_target = _get_os_alias_target(target)
    if canonical_target in policy.uncontrolled_execution_targets:
        return True
    if canonical_target in policy.uncontrolled_execution_target_prefix_exceptions:
        return False
    return canonical_target.startswith(policy.uncontrolled_execution_target_prefixes)


def _get_target_name_for_check(target: Union[str, type, Callable[..., Any]]) -> str:
    if isinstance(target, str):
        return target
    module = getattr(target, "__module__", None)
    qualname = getattr(target, "__qualname__", None)
    if module is not None and qualname is not None:
        return f"{module}.{qualname}"
    target_type = type(target)
    return f"{target_type.__module__}.{target_type.__qualname__}"


def _get_resolved_target_name_for_check(target: Any) -> str:
    """Return the security identity of a resolved target or discovery result."""
    if isinstance(target, types.ModuleType):
        return target.__name__

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
            dict(_current_target_policy().callable_descriptor_binding_targets).get(
                descriptor_owner
            )
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
    descriptor_name = getattr(target, "__name__", None)
    owner_module = getattr(descriptor_owner, "__module__", None)
    owner_qualname = getattr(descriptor_owner, "__qualname__", None)
    if (
        descriptor_name is not None
        and owner_module is not None
        and owner_qualname is not None
    ):
        return f"{owner_module}.{owner_qualname}.{descriptor_name}"
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
    _reject_protected_reference(target_name, full_key)
    canonical_target = _get_policy_alias_target(_get_os_alias_target(target_name))
    resolved_note = _resolved_from_note(canonical_target, resolved_from)
    if _is_uncontrolled_execution_target(canonical_target):
        msg = dedent(f"""\
            Target '{canonical_target}'{resolved_note} is blocklisted because it allows
            config data to control executable behavior or belongs to an
            execution-capable target family. It cannot be authorized with
            HYDRA_INSTANTIATE_ALLOWLIST_OVERRIDE.""")
        raise InstantiationException(_with_full_key(msg, full_key))
    if canonical_target not in _current_target_policy().default_blocklisted_modules:
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
    if target_name not in _current_target_policy().discovery_targets:
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
    target: Any,
    resolved_from: str,
    full_key: str,
) -> str:
    """Authorize the canonical identity of an object resolved from a dotpath."""
    resolved_name = _get_policy_alias_target(
        _get_os_alias_target(_get_resolved_target_name_for_check(target))
    )
    if resolved_name != resolved_from:
        public_hydra_alias = (
            resolved_from in {"hydra.utils.call", "hydra.utils.instantiate"}
            and resolved_name == "hydra._internal.instantiate._instantiate2.instantiate"
        )
        context = (
            _trusted_internal_target(resolved_name)
            if public_hydra_alias
            else nullcontext()
        )
        with context:
            _authorize_target_name(
                resolved_name,
                resolved_from,
                full_key,
                resolved_from_is_alias=True,
            )
    return resolved_name


def _get_effective_target_invocation(
    target: Callable[..., Any],
    args: Tuple[Any, ...],
    kwargs: Dict[str, Any],
) -> Tuple[Callable[..., Any], Tuple[Any, ...], Dict[str, Any]]:
    """Return the callable and arguments an indirect invocation will use."""
    args = tuple(args)
    seen: Set[int] = set()
    while id(target) not in seen:
        seen.add(id(target))
        if isinstance(target, functools.partial):
            partial_args = target.args
            placeholder = getattr(functools, "Placeholder", None)
            if placeholder is not None and any(
                arg is placeholder for arg in partial_args
            ):
                placeholder_count = sum(arg is placeholder for arg in partial_args)
                if len(args) < placeholder_count:
                    return target, args, kwargs
                supplied_args = iter(args)
                partial_args = tuple(
                    next(supplied_args) if arg is placeholder else arg
                    for arg in partial_args
                )
                args = partial_args + tuple(supplied_args)
            else:
                args = partial_args + args
            kwargs = {**(target.keywords or {}), **kwargs}
            target = target.func
            continue

        if getattr(target, "__name__", None) == "__call__":
            receiver = getattr(target, "__self__", None)
            if receiver is not None and callable(receiver):
                target = receiver
                continue
            if (
                type(target) is types.WrapperDescriptorType
                and args
                and callable(args[0])
            ):
                target = cast(Callable[..., Any], args[0])
                args = args[1:]
                continue
        break
    return target, args, kwargs


def _authorize_target_invocation(
    target: Callable[..., Any],
    args: Tuple[Any, ...],
    kwargs: Dict[str, Any],
    full_key: str,
    *,
    allow_incomplete_partial: bool = False,
) -> Tuple[Callable[..., Any], Tuple[Any, ...], Dict[str, Any]]:
    original_target = target
    target, args, kwargs = _get_effective_target_invocation(target, args, kwargs)
    resolved_from = _get_resolved_target_name_for_check(original_target)
    if _get_resolved_target_name_for_check(target) != resolved_from:
        _authorize_callable_result(target, resolved_from, full_key)
        _reject_protected_result(target, resolved_from, full_key)

    target_name = _get_resolved_target_name_for_check(target)
    _reject_protected_callable_capability(target, args, target_name, full_key)
    _reject_code_metadata_access(target, args, full_key)
    _reject_code_or_policy_mutation(target, args, full_key)
    _reject_process_environment_mutation(target, args, kwargs, full_key)
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

    policy = _current_target_policy()
    if target_name in policy.non_callable_mock_targets:
        unsafe_parameters = sorted(
            set(kwargs).difference(policy.non_callable_mock_safe_parameters)
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
        return target, args, kwargs
    if allow_incomplete_partial and len(args) <= 1 and not kwargs:
        return target, args, kwargs
    if len(args) == 1 and not kwargs:
        return target, args, kwargs
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
        policy = _validated_target_policy(_EXPECTED_TARGET_POLICY_DIGEST)
        with _target_policy_context(policy):
            return self._call_with_target_policy(*args, **kwargs)

    def _call_with_target_policy(self, *args: Any, **kwargs: Any) -> Any:
        effective_target, effective_args, effective_kwargs = (
            _authorize_target_invocation(
                self,
                args,
                kwargs,
                self._hydra_full_key,
            )
        )
        discovery_path = _authorize_discovery_path(
            effective_target,
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
    _reject_protected_result(result, resolved_from, full_key)
    if callable(result):
        target, args, kwargs = _get_effective_target_invocation(result, (), {})
        _reject_code_metadata_access(target, args, full_key)
        _reject_code_or_policy_mutation(target, args, full_key)
        _reject_process_environment_mutation(target, args, kwargs, full_key)
    if resolved_from_is_alias and (
        callable(result) or isinstance(result, types.ModuleType)
    ):
        _authorize_resolved_target_identity(result, resolved_from, full_key)
    elif callable(result):
        _authorize_callable_result(
            result,
            resolved_from,
            full_key,
            resolved_from_is_alias=resolved_from_is_alias,
        )
    return result

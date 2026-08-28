# SPDX-FileCopyrightText: Contributors to Hydra
# SPDX-License-Identifier: MIT

import functools
import itertools
import operator
import types
from contextvars import ContextVar
from textwrap import dedent
from typing import Any, Callable, Dict, Optional, Sequence, Tuple, Union, cast

from hydra._internal.utils import _locate
from hydra.errors import InstantiationException

# This blocklist is a best-effort, defense-in-depth stopgap that refuses the
# most obvious dangerous _target_ values on the legacy (no _target_whitelist_)
# path. It is NOT a security boundary and is intentionally not exhaustive.
#
# Known limitation - indirect dispatch: user-defined targets can invoke a
# blocked method without ever naming it as a _target_. The method name is data,
# not a target, so name-based blocking cannot see it. Hydra blocks the generic
# standard-library dispatch primitives identified here, but cannot exhaustively
# identify equivalent application wrappers. A target whitelist supplied from
# trusted Python code is the real security boundary.
# Generally problematic targets are refused on the legacy path, but trusted
# Python code may authorize them with a target whitelist. Keep this set
# for operations whose effect is fully named and bounded by the target itself.
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
# They are refused both on the legacy path and by a real target whitelist.
# UNSAFE_ALLOW_ALL_TARGETS remains the explicit opt-out from all checks.
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
        # Generic dispatch primitives delegate the effective callable, selected
        # member, or operation to config data instead of naming it as _target_.
        # Include public and canonical C-module spellings.
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
        # Unsafe deserialization sinks. Include friendly and canonical C spellings
        # so resolved identities such as pickle.loads -> _pickle.loads are caught.
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
        # Exec/eval wrappers that run config-supplied strings or code objects.
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
        # Annotation evaluators: these execute string annotations as expressions.
        # Include compatibility and canonical spellings across Python versions.
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

# These package families contain version-specific execution, import, debugger,
# or unsafe loading surfaces. Prefixes make coverage version-resilient; narrow
# inert constructors with plausible instantiate() use are excepted below.
UNCONTROLLED_EXECUTION_TARGET_PREFIXES = (
    "os.exec",
    "os.spawn",
    # Whole logging.config namespace: dictConfig/fileConfig and every
    # BaseConfigurator/DictConfigurator method resolve and call config-named
    # factories (arbitrary code) on the legacy/no-whitelist path. Block the
    # family with one prefix instead of enumerating methods. Stopgap only; the
    # permanent control for logging config is the target whitelist (GHSA-c3wx).
    # Hydra's own logging calls logging.config.dictConfig directly (not via
    # instantiate), so this does not affect it.
    "logging.config.",
    # doctest executes example code from docstrings/files (run_docstring_examples,
    # testmod, testfile, DocTestRunner.run, ...). Block the family by default;
    # inert constructors used to assemble tests are excepted below.
    "doctest.",
    # Whole-module deserialization/tracing machinery. shelve.* shelf classes
    # unpickle values on access; trace.* delegates to CoverageResults which
    # unpickles a counts file. The inert Trace constructor is excepted below.
    "shelve.",
    "trace.",
    # pydoc imports/executes modules and files (importfile runs a file,
    # safeimport imports by name). Inert documentation formatters are excepted
    # below.
    "pydoc.",
    # Debugger machinery: pdb/bdb run/eval user strings (pdb.run/runeval,
    # Pdb._getval/_getval_except/default, Bdb.run/runeval/runctx). Whole
    # families; no legitimate instantiate() use.
    "pdb.",
    "bdb.",
)

# Exact legitimate constructors within otherwise denied module families. Exact
# entries in UNCONTROLLED_EXECUTION_TARGETS still take precedence over exceptions.
# An exception permits only the named target, not its methods or descendants.
UNCONTROLLED_EXECUTION_TARGET_PREFIX_EXCEPTIONS = {
    "doctest.DocTest",
    "doctest.DocTestParser",
    "doctest.Example",
    "pydoc.HTMLDoc",
    "pydoc.TextDoc",
    "trace.Trace",
}

# These additional callables cannot be safely authorized by the target-name
# whitelist, but retain temporary legacy compatibility while users migrate.
# Uncontrolled-execution targets above are independently non-whitelistable and
# blocked on the legacy path.
LEGACY_COMPATIBLE_NON_WHITELISTABLE_TARGETS = {
    "builtins.delattr",
    "builtins.getattr",
    "builtins.hasattr",
    "builtins.object.__getattribute__",
    "builtins.setattr",
    "builtins.type.__getattribute__",
    "hydra._internal.instantiate._instantiate2.instantiate",
}

# These targets resolve another object from a config-controlled dotpath. The
# selected path is itself an authorization boundary, independent of whether the
# helper is called immediately or returned through Hydra-native partial support.
DISCOVERY_TARGETS = {
    # Underlying resolver used by the public helpers. Gate it independently so
    # a broad hydra.* whitelist cannot authorize an arbitrary import path.
    "hydra._internal.utils._locate",
    "hydra.utils.get_class",
    "hydra.utils.get_method",
    # get_static_method is currently an alias of get_method; list it explicitly
    # so gating does not depend on that aliasing implementation detail.
    "hydra.utils.get_static_method",
    "hydra.utils.get_object",
}


class _UnsafeAllowAllTargets:
    def __repr__(self) -> str:
        return "UNSAFE_ALLOW_ALL_TARGETS"

    def __reduce__(self) -> Any:
        return (_get_unsafe_allow_all_targets, ())


def _get_unsafe_allow_all_targets() -> "_UnsafeAllowAllTargets":
    return UNSAFE_ALLOW_ALL_TARGETS


UNSAFE_ALLOW_ALL_TARGETS = _UnsafeAllowAllTargets()
NormalizedTargetWhitelist = Union[Tuple[str, ...], _UnsafeAllowAllTargets, None]
_TARGET_WHITELIST_CONTEXT: ContextVar[NormalizedTargetWhitelist] = ContextVar(
    "hydra_target_whitelist", default=None
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


def _is_non_whitelistable_target(target: str) -> bool:
    canonical_target = _get_os_alias_target(target)
    if (
        canonical_target in UNCONTROLLED_EXECUTION_TARGETS
        or canonical_target in LEGACY_COMPATIBLE_NON_WHITELISTABLE_TARGETS
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


def _validate_target_whitelist_pattern(pattern: Any) -> str:
    if not isinstance(pattern, str):
        raise InstantiationException(
            f"Invalid _target_whitelist_ entry '{pattern}': expected a string"
        )
    if pattern == "":
        raise InstantiationException("Invalid _target_whitelist_ entry: empty string")
    if "*" not in pattern:
        return pattern
    if pattern == "*" or not pattern.endswith(".*") or pattern.count("*") > 1:
        raise InstantiationException(
            dedent(f"""\
                Invalid _target_whitelist_ entry '{pattern}'. Only trailing '.*'
                package wildcards are supported. The wildcard '*' is not allowed
                as a target whitelist pattern. To preserve legacy all-target
                behavior, pass UNSAFE_ALLOW_ALL_TARGETS explicitly.""")
        )
    prefix = pattern[:-2]
    if prefix == "" or prefix.endswith("."):
        raise InstantiationException(
            f"Invalid _target_whitelist_ entry '{pattern}': missing package prefix"
        )
    return pattern


def _normalize_target_whitelist(
    target_whitelist: Any,
) -> NormalizedTargetWhitelist:
    if target_whitelist is None:
        return None
    if target_whitelist is UNSAFE_ALLOW_ALL_TARGETS:
        return UNSAFE_ALLOW_ALL_TARGETS
    if isinstance(target_whitelist, _TargetWhitelistPolicy):
        return target_whitelist.whitelist
    if isinstance(target_whitelist, str):
        return (_validate_target_whitelist_pattern(target_whitelist),)
    try:
        return tuple(
            _validate_target_whitelist_pattern(pattern) for pattern in target_whitelist
        )
    except TypeError as e:
        raise InstantiationException(
            "Invalid _target_whitelist_: expected a string, a sequence of strings, "
            "or UNSAFE_ALLOW_ALL_TARGETS"
        ) from e


def _combine_target_whitelists(
    base: NormalizedTargetWhitelist, extra: NormalizedTargetWhitelist
) -> NormalizedTargetWhitelist:
    if base is UNSAFE_ALLOW_ALL_TARGETS or extra is UNSAFE_ALLOW_ALL_TARGETS:
        return UNSAFE_ALLOW_ALL_TARGETS
    if base is None:
        return extra
    if extra is None:
        return base
    return tuple(
        dict.fromkeys(cast(Tuple[str, ...], base) + cast(Tuple[str, ...], extra))
    )


class _TargetWhitelistPolicy:
    def __init__(
        self, whitelist: NormalizedTargetWhitelist, reset: bool = False
    ) -> None:
        self.whitelist = whitelist
        self.reset = reset
        self._tokens: ContextVar[Tuple[Any, ...]] = ContextVar(
            "hydra_target_whitelist_tokens", default=()
        )

    def resolve(
        self, inherited: NormalizedTargetWhitelist
    ) -> NormalizedTargetWhitelist:
        if self.reset:
            return self.whitelist
        return _combine_target_whitelists(inherited, self.whitelist)

    def __enter__(self) -> "_TargetWhitelistPolicy":
        token = _TARGET_WHITELIST_CONTEXT.set(
            self.resolve(_TARGET_WHITELIST_CONTEXT.get())
        )
        self._tokens.set((*self._tokens.get(), token))
        return self

    def __exit__(self, *args: Any) -> None:
        tokens = self._tokens.get()
        _TARGET_WHITELIST_CONTEXT.reset(tokens[-1])
        self._tokens.set(tokens[:-1])


TargetWhitelist = Union[
    str, Sequence[str], _UnsafeAllowAllTargets, _TargetWhitelistPolicy, None
]


def target_whitelist(target_whitelist: TargetWhitelist, reset: bool = False) -> Any:
    """
    Create a target whitelist object for config-selected Python targets.

    The returned object can be used as a context manager to apply a whitelist to
    Hydra operations in the current context, or passed to instantiate() as
    _target_whitelist_. This includes targets selected by Hydra logging
    configuration.

    :param target_whitelist: A target string, list of target strings, or
        UNSAFE_ALLOW_ALL_TARGETS. A trailing .* allows targets under a package
        prefix.
    :param reset: If True, ignore any outer target_whitelist() context.
        If False, add these targets to the current context.
    """
    return _TargetWhitelistPolicy(
        whitelist=_normalize_target_whitelist(target_whitelist),
        reset=reset,
    )


def _resolve_target_whitelist(
    target_whitelist: TargetWhitelist,
) -> NormalizedTargetWhitelist:
    inherited = _TARGET_WHITELIST_CONTEXT.get()
    if isinstance(target_whitelist, _TargetWhitelistPolicy):
        return target_whitelist.resolve(inherited)
    return _combine_target_whitelists(
        inherited, _normalize_target_whitelist(target_whitelist)
    )


def _get_active_target_whitelist() -> NormalizedTargetWhitelist:
    """Return the normalized target whitelist active in this context."""
    return _TARGET_WHITELIST_CONTEXT.get()


def _is_target_whitelisted(target: str, target_whitelist: Tuple[str, ...]) -> bool:
    for pattern in target_whitelist:
        if pattern.endswith(".*"):
            prefix = pattern[:-2]
            if target.startswith(f"{prefix}."):
                return True
        elif target == pattern:
            return True
    return False


def _with_full_key(message: str, full_key: str) -> str:
    return f"{message}\nfull_key: {full_key}" if full_key else message


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
    """Return the security identity of a resolved callable.

    Callable wrappers, constructors, and descriptors must be authorized as the
    operation they expose, not as generic callable containers. Unwrap recursively
    because wrapper forms can wrap one another.
    """
    seen: set[int] = set()
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
    if target is object.__getattribute__:
        return "builtins.object.__getattribute__"
    if target is type.__getattribute__:
        return "builtins.type.__getattribute__"
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


def _resolved_from_note(target_name: str, resolved_from: str) -> str:
    return "" if resolved_from == target_name else f" (resolved from '{resolved_from}')"


_TARGET_WHITELIST_DOC_URL = (
    "https://hydra.cc/docs/upgrades/1.3_to_1.4/instantiate_target_whitelist/"
)


def _logging_target_help(full_key: str) -> str:
    if full_key != "hydra.logging":
        return ""
    return f"\nSee {_TARGET_WHITELIST_DOC_URL}"


def _blocklisted_target_message(
    target_name: str, resolved_from: str, full_key: str
) -> str:
    resolved_note = _resolved_from_note(target_name, resolved_from)
    if target_name in {
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
    }:
        message = dedent(
            f"""\
            Target '{target_name}'{resolved_note} is blocklisted because it performs
            generic selection or dispatch using config data.
            Set '_target_' to the intended callable instead. Pass
            UNSAFE_ALLOW_ALL_TARGETS only to explicitly disable target safety checks."""
        )
    elif _is_uncontrolled_execution_target(target_name):
        message = dedent(
            f"""\
            Target '{target_name}'{resolved_note} is blocklisted because it allows
            config data to control executable behavior or belongs to an
            execution-capable target family. It cannot be authorized with a target
            whitelist. Pass UNSAFE_ALLOW_ALL_TARGETS only to explicitly disable
            target safety checks."""
        )
    else:
        message = dedent(
            f"""\
            Target '{target_name}'{resolved_note} is blocklisted and cannot be instantiated from config
            to prevent security vulnerabilities.
            Pass _target_whitelist_ from trusted code to allow expected targets."""
        )
    return message + _logging_target_help(full_key)


def _not_whitelisted_message(
    target_name: str, resolved_from: str, full_key: str
) -> str:
    resolved_note = _resolved_from_note(target_name, resolved_from)
    if full_key == "hydra.logging":
        return dedent(
            f"""\
            Logging target '{target_name}'{resolved_note} is not in the Hydra target whitelist.
            Add it to target_whitelist= on @hydra.main(), or use
            hydra.utils.target_whitelist() around logging setup from trusted Python
            code.
            See {_TARGET_WHITELIST_DOC_URL}"""
        )
    return dedent(
        f"""\
        Target '{target_name}'{resolved_note} is not in the instantiate target whitelist.
        Pass _target_whitelist_ from trusted code to allow expected targets."""
    )


def _non_whitelistable_target_message(
    target_name: str, resolved_from: str, full_key: str
) -> str:
    resolved_note = _resolved_from_note(target_name, resolved_from)
    if target_name in {
        "builtins.delattr",
        "builtins.getattr",
        "builtins.hasattr",
        "builtins.object.__getattribute__",
        "builtins.setattr",
        "builtins.type.__getattribute__",
    }:
        message = dedent(
            f"""\
            Target '{target_name}'{resolved_note} cannot be authorized by the instantiate
            target whitelist because attribute operations can execute descriptor code before
            the operation can be authorized. Access or mutate the attribute from trusted
            Python code instead."""
        )
    elif target_name == "hydra._internal.instantiate._instantiate2.instantiate":
        message = dedent(
            f"""\
            Target '{target_name}'{resolved_note} cannot be authorized by the instantiate
            target whitelist because reentrant instantiate calls do not safely inherit
            the effective whitelist. Call instantiate() from trusted Python code instead."""
        )
    elif target_name in {
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
    }:
        message = dedent(
            f"""\
            Target '{target_name}'{resolved_note} cannot be authorized by the instantiate
            target whitelist because it performs generic selection or dispatch using
            config data.
            Set '_target_' to the intended callable instead."""
        )
    elif _is_uncontrolled_execution_target(target_name):
        message = dedent(
            f"""\
            Target '{target_name}'{resolved_note} cannot be authorized by the
            instantiate target whitelist because it allows config data to control
            executable behavior or belongs to an execution-capable target family.
            Call a narrow trusted wrapper from config instead."""
        )
    else:
        message = dedent(
            f"""\
            Target '{target_name}'{resolved_note} cannot be authorized by the instantiate
            target whitelist because it delegates the effective operation to config data.
            Set '_target_' to the intended callable instead."""
        )
    return message + _logging_target_help(full_key)


def _reject_non_whitelistable_target(
    target_name: str,
    resolved_from: str,
    full_key: str,
    target_whitelist: NormalizedTargetWhitelist,
) -> None:
    if (
        target_whitelist is not None
        and target_whitelist is not UNSAFE_ALLOW_ALL_TARGETS
        and _is_non_whitelistable_target(target_name)
    ):
        raise InstantiationException(
            _with_full_key(
                _non_whitelistable_target_message(target_name, resolved_from, full_key),
                full_key,
            )
        )


def _is_exactly_whitelisted(target: str, target_whitelist: Tuple[str, ...]) -> bool:
    """True if target matches a non-wildcard (exact) whitelist entry."""
    return any(
        not pattern.endswith(".*") and target == pattern for pattern in target_whitelist
    )


def _requires_resolved_authorization(
    target_name: str, target_whitelist: NormalizedTargetWhitelist
) -> bool:
    """Whether the resolved identity must be re-authorized after _locate().

    The resolved-identity recheck is what closes aliasing bypasses, but it must
    not punish a deliberate exact whitelist entry for a re-exported target
    (e.g. 'json.JSONDecoder' whose canonical name is 'json.decoder.JSONDecoder').
    An exact whitelist match on the config string is authoritative; only a
    wildcard match still needs the recheck. The blocklist path always rechecks.
    """
    if target_whitelist is UNSAFE_ALLOW_ALL_TARGETS:
        return False
    if target_whitelist is None:
        return True
    return not _is_exactly_whitelisted(
        target_name, cast(Tuple[str, ...], target_whitelist)
    )


def _authorize_target_name(
    target_name: str,
    resolved_from: str,
    full_key: str,
    target_whitelist: NormalizedTargetWhitelist,
) -> None:
    """Authorize a single target name against the active policy.

    Called on the literal pre-resolution string and on resolved callable
    identities. Checking the resolved identity is what closes module-attribute
    aliasing bypasses (e.g. ``logging.os.system`` resolving to the blocklisted
    ``os.system``), since a dotted string can name a callable that lives in a
    different module than the string's prefix suggests.
    """
    if target_whitelist is UNSAFE_ALLOW_ALL_TARGETS:
        return
    _reject_non_whitelistable_target(
        target_name, resolved_from, full_key, target_whitelist
    )
    if target_whitelist is None:
        if _is_blocklisted_target(target_name):
            raise InstantiationException(
                _with_full_key(
                    _blocklisted_target_message(target_name, resolved_from, full_key),
                    full_key,
                )
            )
    elif not _is_target_whitelisted(
        target_name, cast(Tuple[str, ...], target_whitelist)
    ):
        raise InstantiationException(
            _with_full_key(
                _not_whitelisted_message(target_name, resolved_from, full_key),
                full_key,
            )
        )


def _authorize_discovery_path(
    target: Callable[..., Any],
    args: Tuple[Any, ...],
    kwargs: Dict[str, Any],
    full_key: str,
    target_whitelist: NormalizedTargetWhitelist,
) -> Optional[str]:
    """Authorize the dotpath consumed by a Hydra discovery helper."""
    target_name = _get_resolved_target_name_for_check(target)
    if target_name not in DISCOVERY_TARGETS:
        return None

    path = args[0] if args else kwargs.get("path")
    if not isinstance(path, str):
        return None
    _authorize_target_name(path, path, full_key, target_whitelist)
    return path


def _authorize_discovery_result(
    path: str,
    result: Callable[..., Any],
    full_key: str,
    target_whitelist: NormalizedTargetWhitelist,
) -> None:
    """Recheck a discovered callable by its canonical security identity."""
    _authorize_resolved_target_identity(result, path, full_key, target_whitelist)


def _authorize_resolved_target_identity(
    target: Callable[..., Any],
    resolved_from: str,
    full_key: str,
    target_whitelist: NormalizedTargetWhitelist,
) -> str:
    """Authorize the canonical identity of a callable resolved from a dotpath."""
    resolved_name = _get_os_alias_target(_get_resolved_target_name_for_check(target))
    _reject_non_whitelistable_target(
        resolved_name, resolved_from, full_key, target_whitelist
    )
    if resolved_name != resolved_from and _requires_resolved_authorization(
        resolved_from, target_whitelist
    ):
        _authorize_target_name(resolved_name, resolved_from, full_key, target_whitelist)
    return resolved_name


def _authorize_callable_result(
    result: Callable[..., Any],
    resolved_from: str,
    full_key: str,
    target_whitelist: NormalizedTargetWhitelist,
) -> None:
    """Authorize a callable selected as another target's runtime result."""
    resolved_name = _get_os_alias_target(_get_resolved_target_name_for_check(result))
    _authorize_target_name(resolved_name, resolved_from, full_key, target_whitelist)


def _get_effective_target_invocation(
    target: Callable[..., Any],
    args: Tuple[Any, ...],
    kwargs: Dict[str, Any],
) -> Tuple[Callable[..., Any], Tuple[Any, ...], Dict[str, Any]]:
    """Return the callable and arguments an exact partial will invoke."""
    while isinstance(target, functools.partial):
        partial_args = target.args
        placeholder = getattr(functools, "Placeholder", None)
        if placeholder is not None and any(arg is placeholder for arg in partial_args):
            placeholder_count = sum(arg is placeholder for arg in partial_args)
            if len(args) < placeholder_count:
                # The partial call will fail before invoking its target.
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
    return target, args, kwargs


def _authorize_target_invocation(
    target: Callable[..., Any],
    args: Tuple[Any, ...],
    kwargs: Dict[str, Any],
    full_key: str,
    target_whitelist: NormalizedTargetWhitelist,
    *,
    allow_incomplete_partial: bool = False,
) -> None:
    """Reject argument-sensitive construction surfaces before invoking them."""
    if target_whitelist is UNSAFE_ALLOW_ALL_TARGETS:
        return

    target_name = _get_resolved_target_name_for_check(target)
    if target_name == "builtins.iter" and len(args) == 2:
        msg = dedent(
            """\
            Target 'builtins.iter' cannot use its two-argument callback form from
            config because callback execution is deferred beyond instantiate's
            target authorization. Use one-argument iter(iterable), or perform the
            callback iteration in trusted Python code. Pass UNSAFE_ALLOW_ALL_TARGETS
            only to explicitly disable target safety checks."""
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
            msg = dedent(
                f"""\
                Target '{target_name}' cannot configure callable attributes,
                children, or wrappers from config (unsafe parameters: {joined}).
                Only one positional spec and the name, spec, and spec_set keyword
                parameters are allowed. Pass UNSAFE_ALLOW_ALL_TARGETS only to
                explicitly disable target safety checks."""
            )
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
                msg = dedent(
                    f"""\
                    Target '{target_name}' cannot be used for dynamic class construction
                    from config. Metaclass constructor methods cannot be authorized with
                    a target whitelist. Pass UNSAFE_ALLOW_ALL_TARGETS only to explicitly
                    disable target safety checks."""
                )
                raise InstantiationException(_with_full_key(msg, full_key))

    if not isinstance(target, type) or not issubclass(target, type):
        return
    if allow_incomplete_partial and len(args) <= 1 and not kwargs:
        return
    if len(args) == 1 and not kwargs:
        return
    msg = dedent(
        f"""\
        Target '{target_name}' cannot be used for dynamic class construction from
        config. Only one-argument type(obj) introspection is allowed. Pass
        UNSAFE_ALLOW_ALL_TARGETS only to explicitly disable target safety checks."""
    )
    raise InstantiationException(_with_full_key(msg, full_key))


class _DeferredTarget(functools.partial):  # type: ignore[type-arg]
    """Authorize arguments and callable results when a Hydra partial is invoked."""

    _hydra_resolved_from: str
    _hydra_full_key: str
    _hydra_target_whitelist: NormalizedTargetWhitelist

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        effective_target, effective_args, effective_kwargs = (
            _get_effective_target_invocation(self, args, kwargs)
        )
        _authorize_target_invocation(
            effective_target,
            effective_args,
            effective_kwargs,
            self._hydra_full_key,
            self._hydra_target_whitelist,
        )
        discovery_path = _authorize_discovery_path(
            effective_target,
            effective_args,
            effective_kwargs,
            self._hydra_full_key,
            self._hydra_target_whitelist,
        )
        result = super().__call__(*args, **kwargs)
        return _mediate_target_result(
            result,
            discovery_path or self._hydra_resolved_from,
            self._hydra_full_key,
            self._hydra_target_whitelist,
            discovery_path=discovery_path,
        )


def _mediate_target_result(
    result: Any,
    resolved_from: str,
    full_key: str,
    target_whitelist: NormalizedTargetWhitelist,
    *,
    discovery_path: Optional[str] = None,
) -> Any:
    """Authorize callable results and keep deferred partial results mediated."""
    if target_whitelist is UNSAFE_ALLOW_ALL_TARGETS:
        return result

    if isinstance(result, functools.partial) and type(result) is not _DeferredTarget:
        if type(result) is not functools.partial:
            msg = dedent(
                """\
                Callable targets cannot return partial subclasses because overrides
                can hide their invocation behavior. Return an exact functools.partial
                or use Hydra's '_partial_: true' support instead."""
            )
            raise InstantiationException(_with_full_key(msg, full_key))
        deferred = _DeferredTarget(
            result.func,
            *result.args,
            **(result.keywords or {}),
        )
        deferred.__dict__.update(result.__dict__)
        deferred._hydra_resolved_from = resolved_from
        deferred._hydra_full_key = full_key
        deferred._hydra_target_whitelist = target_whitelist
        result = deferred

    if callable(result):
        if discovery_path is not None:
            _authorize_discovery_result(
                discovery_path, result, full_key, target_whitelist
            )
        else:
            _authorize_callable_result(
                result, resolved_from, full_key, target_whitelist
            )
    return result

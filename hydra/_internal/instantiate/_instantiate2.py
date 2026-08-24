# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved

import copy
import functools
import inspect
import operator
import re
from contextvars import ContextVar
from enum import Enum
from textwrap import dedent
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple, Union, cast

from omegaconf import AnyNode, DictConfig, Node, OmegaConf, SCMode
from omegaconf._utils import is_structured_config
from omegaconf.errors import InterpolationResolutionError

from hydra._internal.deprecation_warning import deprecation_warning
from hydra._internal.utils import _locate
from hydra.errors import InstantiationException
from hydra.types import ConvertMode

# This blocklist is a best-effort, defense-in-depth stopgap that refuses the
# most obvious dangerous _target_ values on the legacy (no _target_whitelist_)
# path. It is NOT a security boundary and is intentionally not exhaustive.
#
# Known limitation - indirect dispatch: user-defined targets can invoke a
# blocked method without ever naming it as a _target_. The method name is data,
# not a target, so name-based blocking cannot see it. Hydra blocks the generic
# standard-library dispatch primitives identified here, but cannot exhaustively
# identify equivalent application wrappers. The target whitelist
# (_target_whitelist_) is the real security boundary.
DEFAULT_BLOCKLISTED_MODULES = {
    "_sitebuiltins._Helper",
    "_sitebuiltins.Quitter",
    "builtins.exec",
    "builtins.eval",
    "builtins.__import__",
    "builtins.compile",
    "builtins.exit",
    "builtins.quit",
    # Generic dispatch primitives delegate the effective callable or method
    # name to config data instead of naming it as _target_. Include public and
    # canonical C-module spellings.
    "operator.call",
    "operator.attrgetter",
    "operator.methodcaller",
    "_operator.call",
    "_operator.attrgetter",
    "_operator.methodcaller",
    "ctypes.CDLL",
    "ctypes.LibraryLoader.LoadLibrary",
    "ctypes.OleDLL",
    "ctypes.PyDLL",
    "ctypes.WinDLL",
    "ctypes.cdll.LoadLibrary",
    "ctypes.oledll.LoadLibrary",
    "ctypes.pydll.LoadLibrary",
    "ctypes.windll.LoadLibrary",
    "importlib.import_module",
    "os.kill",
    "os.system",
    "os.popen",
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
    "os.startfile",
    "os.posix_spawn",
    "os.posix_spawnp",
    "os.truncate",
    "os.replace",
    "os.unlink",
    "os.fchmod",
    "os.fchown",
    "os.chmod",
    "os.chown",
    "os.chroot",
    "os.fchdir",
    "os.lchflags",
    "os.lchmod",
    "os.lchown",
    "os.getcwd",
    "os.chdir",
    "pty.spawn",
    "runpy.run_module",
    "runpy.run_path",
    "shutil.rmtree",
    "shutil.move",
    "shutil.chown",
    "subprocess.Popen",
    "subprocess.run",
    "subprocess.call",
    "subprocess.check_call",
    "subprocess.check_output",
    "subprocess.getoutput",
    "subprocess.getstatusoutput",
    "builtins.help",
    "sys.modules.ipdb",
    "sys.modules.joblib",
    "sys.modules.resource",
    "sys.modules.psutil",
    "sys.modules.tkinter",
    # Unsafe deserialization sinks: unpickling untrusted data is arbitrary code
    # execution. This blocks only the direct instantiate() vector (e.g. the
    # inline pickle.loads(base64.b64decode(...)) chain); it is not a claim that
    # deserialization is safe. The target whitelist remains the real boundary,
    # and whitelisted loaders (e.g. torch.load) or user wrappers are unaffected.
    # Both the friendly and canonical C spellings are listed so the resolved
    # identity (pickle.loads -> _pickle.loads) is caught either way.
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
    # Exec/eval wrappers: standard-library functions that run a user-supplied
    # string as code. They have no legitimate instantiate() use (like the already
    # blocked builtins.exec), so the direct vector is blocked; the whitelist
    # remains the boundary.
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
    "annotationlib.ForwardRef._evaluate",
    "annotationlib.ForwardRef.evaluate",
    "annotationlib.get_annotations",
    "optparse.Values.read_file",
    "optparse.Values.read_module",
}

DEFAULT_BLOCKLISTED_MODULE_PREFIXES = (
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

# Exact legitimate constructors within otherwise blocked module families. Exact
# entries in DEFAULT_BLOCKLISTED_MODULES still take precedence over exceptions.
# An exception permits only the named target, not its methods or descendants.
DEFAULT_BLOCKLISTED_MODULE_PREFIX_EXCEPTIONS = {
    "doctest.DocTest",
    "doctest.DocTestParser",
    "doctest.Example",
    "pydoc.HTMLDoc",
    "pydoc.TextDoc",
    "trace.Trace",
}

# These callables cannot be safely authorized by the target-name whitelist.
# Some retain temporary legacy compatibility while users migrate; generic
# dispatch primitives are also blocked on the legacy path.
NON_WHITELISTABLE_TARGETS = {
    "operator.call",
    "operator.attrgetter",
    "operator.methodcaller",
    "_operator.call",
    "_operator.attrgetter",
    "_operator.methodcaller",
    "hydra._internal.instantiate._instantiate2.instantiate",
}

# These targets resolve another object from a config-controlled dotpath. The
# selected path is itself an authorization boundary, independent of whether the
# helper is called immediately or returned through Hydra-native partial support.
DISCOVERY_TARGETS = {
    "hydra.utils.get_class",
    "hydra.utils.get_method",
    # get_static_method is currently an alias of get_method; list it explicitly
    # so gating does not depend on that aliasing implementation detail.
    "hydra.utils.get_static_method",
    "hydra.utils.get_object",
}

# These targets may return a callable selected by config data. Non-callable
# results remain ordinary values; callable results must independently satisfy
# the active target policy before they can flow into another config target.
CALLABLE_RESULT_TARGETS = {
    "builtins.getattr",
    "functools.partial",
}
DEFERRED_CALLABLE_SELECTION_TARGETS = DISCOVERY_TARGETS | CALLABLE_RESULT_TARGETS


class _UnsafeAllowAllTargets:
    def __repr__(self) -> str:
        return "UNSAFE_ALLOW_ALL_TARGETS"


UNSAFE_ALLOW_ALL_TARGETS = _UnsafeAllowAllTargets()
NormalizedTargetWhitelist = Union[Tuple[str, ...], _UnsafeAllowAllTargets, None]
ConfigOverlay = Union[Dict[str, Any], DictConfig]
_TARGET_WHITELIST_CONTEXT: ContextVar[NormalizedTargetWhitelist] = ContextVar(
    "hydra_instantiate_target_whitelist", default=None
)
_INSTANTIATE_OVERRIDE_RESOLVER = "hydra.instantiate_override"
_INSTANTIATE_OVERRIDE_STORAGE = "_hydra_instantiate_overrides"


def _resolve_instantiate_override(token: str, *, _root_: Any) -> Any:
    source, key = _root_.__dict__[_INSTANTIATE_OVERRIDE_STORAGE][token]
    return source[key]


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


class _Keys(str, Enum):
    """Special keys in configs used by instantiate."""

    TARGET = "_target_"
    CONVERT = "_convert_"
    RECURSIVE = "_recursive_"
    ARGS = "_args_"
    PARTIAL = "_partial_"
    TARGET_WHITELIST = "_target_whitelist_"


def _is_target(x: Any) -> bool:
    if isinstance(x, dict):
        return "_target_" in x
    if OmegaConf.is_dict(x):
        return "_target_" in x
    return False


def _is_blocklisted_target(target: str) -> bool:
    canonical_target = _get_os_alias_target(target)
    if canonical_target in DEFAULT_BLOCKLISTED_MODULES:
        return True
    if canonical_target in DEFAULT_BLOCKLISTED_MODULE_PREFIX_EXCEPTIONS:
        return False
    return canonical_target.startswith(DEFAULT_BLOCKLISTED_MODULE_PREFIXES)


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
        self._tokens: List[Any] = []

    def resolve(
        self, inherited: NormalizedTargetWhitelist
    ) -> NormalizedTargetWhitelist:
        if self.reset:
            return self.whitelist
        return _combine_target_whitelists(inherited, self.whitelist)

    def __enter__(self) -> "_TargetWhitelistPolicy":
        self._tokens.append(
            _TARGET_WHITELIST_CONTEXT.set(self.resolve(_TARGET_WHITELIST_CONTEXT.get()))
        )
        return self

    def __exit__(self, *args: Any) -> None:
        _TARGET_WHITELIST_CONTEXT.reset(self._tokens.pop())


TargetWhitelist = Union[
    str, Sequence[str], _UnsafeAllowAllTargets, _TargetWhitelistPolicy, None
]


def target_whitelist(target_whitelist: TargetWhitelist, reset: bool = False) -> Any:
    """
    Create a target whitelist object for hydra.utils.instantiate().

    The returned object can be used as a context manager to apply a whitelist to
    instantiate() calls in the current context, or passed to instantiate() as
    _target_whitelist_.

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


def _is_target_whitelisted(target: str, target_whitelist: Tuple[str, ...]) -> bool:
    for pattern in target_whitelist:
        if pattern.endswith(".*"):
            prefix = pattern[:-2]
            if target.startswith(f"{prefix}."):
                return True
        elif target == pattern:
            return True
    return False


def _warn_legacy_target_whitelist(target: str) -> None:
    stacklevel = 1
    frame = inspect.currentframe()
    while frame is not None:
        if frame.f_code.co_filename != __file__:
            break
        stacklevel += 1
        frame = frame.f_back
    deprecation_warning(
        dedent(
            f"""\
            hydra.utils.instantiate() resolved _target_='{target}' with no
            _target_whitelist_. This preserves legacy behavior but is deprecated
            because config-controlled targets can execute arbitrary code. This
            warning will become an error in Hydra 1.5. Pass a callsite target
            whitelist, or pass UNSAFE_ALLOW_ALL_TARGETS to explicitly keep legacy
            behavior.
            See https://hydra.cc/docs/upgrades/1.3_to_1.4/instantiate_target_whitelist/"""
        ),
        stacklevel=stacklevel,
    )


def _warn_direct_functools_partial_target() -> None:
    stacklevel = 1
    frame = inspect.currentframe()
    while frame is not None:
        if frame.f_code.co_filename != __file__:
            break
        stacklevel += 1
        frame = frame.f_back
    deprecation_warning(
        dedent(
            """\
            Using '_target_: functools.partial' is deprecated. Set '_target_' to
            the effective callable and use '_partial_: true' instead. Direct
            functools.partial targets will become an error in Hydra 1.5."""
        ),
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


def _with_full_key(message: str, full_key: str) -> str:
    return f"{message}\nfull_key: {full_key}" if full_key else message


def _call_target(
    _target_: Callable[..., Any],
    _partial_: bool,
    args: Tuple[Any, ...],
    kwargs: Dict[str, Any],
    full_key: str,
    target_whitelist: NormalizedTargetWhitelist,
) -> Any:
    """Call target (type) with args and kwargs."""
    try:
        args, kwargs = _extract_pos_args(args, kwargs)
    except Exception as e:
        msg = (
            f"Error in collecting args and kwargs for '{_convert_target_to_string(_target_)}':"
            + f"\n{repr(e)}"
        )
        raise InstantiationException(_with_full_key(msg, full_key)) from e

    resolved_target_name = _get_resolved_target_name_for_check(_target_)
    if (
        _partial_
        and resolved_target_name in DEFERRED_CALLABLE_SELECTION_TARGETS
        and target_whitelist is not None
        and target_whitelist is not UNSAFE_ALLOW_ALL_TARGETS
    ):
        msg = dedent(
            f"""\
            Target '{resolved_target_name}' cannot use '_partial_: true' with the
            instantiate target whitelist because its effective callable could be
            selected after authorization. Resolve the callable immediately or use a
            trusted Python wrapper."""
        )
        raise InstantiationException(_with_full_key(msg, full_key))

    discovery_path = _authorize_discovery_path(
        _target_, args, kwargs, full_key, target_whitelist
    )
    # For a deferred discovery partial on the legacy path, eagerly resolve and
    # blocklist-check the selected target so a partial cannot smuggle a blocked
    # callable past the stopgap. UNSAFE_ALLOW_ALL_TARGETS opts out of all checks
    # and keeps discovery fully deferred.
    if (
        discovery_path is not None
        and _partial_
        and target_whitelist is not UNSAFE_ALLOW_ALL_TARGETS
    ):
        try:
            discovered = _locate(discovery_path)
        except Exception as e:
            msg = f"Error locating discovered target '{discovery_path}'"
            raise InstantiationException(_with_full_key(msg, full_key)) from e
        if callable(discovered):
            _authorize_discovery_result(
                discovery_path, discovered, full_key, target_whitelist
            )
    try:
        if _partial_:
            return functools.partial(_target_, *args, **kwargs)
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

    if discovery_path is not None and callable(result):
        _authorize_discovery_result(discovery_path, result, full_key, target_whitelist)
    if resolved_target_name == "builtins.getattr" and callable(result):
        _authorize_callable_result(
            result, resolved_target_name, full_key, target_whitelist
        )
    if resolved_target_name == "functools.partial" and isinstance(
        result, functools.partial
    ):
        if (
            target_whitelist is not UNSAFE_ALLOW_ALL_TARGETS
            and type(result) is not functools.partial
        ):
            msg = dedent(
                """\
                Direct functools.partial targets cannot construct partial subclasses
                because overrides can hide their invocation behavior. Set '_target_'
                to the effective callable and use '_partial_: true' instead."""
            )
            raise InstantiationException(_with_full_key(msg, full_key))
        _authorize_callable_result(
            functools.partial.func.__get__(result),
            resolved_target_name,
            full_key,
            target_whitelist,
        )
    return result


def _convert_target_to_string(t: Any) -> Any:
    if callable(t) and hasattr(t, "__qualname__"):
        return f"{t.__module__}.{t.__qualname__}"
    else:
        return t


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

    Bound ``__call__`` attributes, ``functools.partial`` objects, and unbound
    descriptors owned by denied operator types must be authorized as the
    callable they wrap or expose, not as generic callable containers. Unwrap
    recursively because either wrapper form can wrap the other.
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
    descriptor_owner = getattr(target, "__objclass__", None)
    if descriptor_owner is operator.attrgetter:
        return "operator.attrgetter"
    if descriptor_owner is operator.methodcaller:
        return "operator.methodcaller"
    if target is functools.partial.__new__:
        return "functools.partial"
    if target is operator.attrgetter.__new__:
        return "operator.attrgetter"
    if target is operator.methodcaller.__new__:
        return "operator.methodcaller"
    return _get_target_name_for_check(target)


def _prepare_input_container(
    d: Union[Dict[Any, Any], List[Any], Tuple[Any, ...]],
) -> Any:
    if isinstance(d, dict):
        result = {}
        for k, v in d.items():
            if k == "_target_":
                v = _convert_target_to_string(d["_target_"])
            else:
                v = _prepare_input_value(v)
            result[k] = v
        return result

    if isinstance(d, list) or type(d) is tuple:
        values = [_prepare_input_value(v) for v in d]
        return values if isinstance(d, list) else tuple(values)

    assert False


def _prepare_input_value(
    value: Any,
) -> Any:
    if not is_structured_config(value) and (
        isinstance(value, (dict, list)) or type(value) is tuple
    ):
        return _prepare_input_container(value)
    return value


def _validate_callsite_override(value: Any, path: Tuple[Any, ...]) -> None:
    if is_structured_config(value):
        return

    raw_value = value._value() if isinstance(value, Node) else value
    full_key = ".".join(
        str(component.value if isinstance(component, Enum) else component)
        for component in path
    )
    if isinstance(raw_value, str) and raw_value == "???":
        raise InstantiationException(
            f"Call-site override '{full_key}' cannot be an OmegaConf missing value. "
            "Pass a concrete runtime value instead."
        )
    if isinstance(raw_value, str) and "${" in raw_value:
        raise InstantiationException(
            f"Call-site override '{full_key}' cannot be an OmegaConf interpolation. "
            "Pass a concrete runtime value instead."
        )

    if isinstance(value, dict):
        for key, child in value.items():
            _validate_callsite_override(child, (*path, key))
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            _validate_callsite_override(child, (*path, index))


def _resolved_from_note(target_name: str, resolved_from: str) -> str:
    return "" if resolved_from == target_name else f" (resolved from '{resolved_from}')"


def _blocklisted_target_message(target_name: str, resolved_from: str) -> str:
    resolved_note = _resolved_from_note(target_name, resolved_from)
    if target_name in {
        "operator.call",
        "operator.attrgetter",
        "operator.methodcaller",
        "_operator.call",
        "_operator.attrgetter",
        "_operator.methodcaller",
    }:
        return dedent(
            f"""\
            Target '{target_name}'{resolved_note} is blocklisted because it performs
            generic selection or dispatch using config data.
            Set '_target_' to the intended callable instead. Pass
            UNSAFE_ALLOW_ALL_TARGETS only to explicitly disable target safety checks."""
        )
    return dedent(
        f"""\
        Target '{target_name}'{resolved_note} is blocklisted and cannot be instantiated from config
        to prevent security vulnerabilities.
        Pass _target_whitelist_ from trusted code to allow expected targets."""
    )


def _not_whitelisted_message(target_name: str, resolved_from: str) -> str:
    resolved_note = _resolved_from_note(target_name, resolved_from)
    return dedent(
        f"""\
        Target '{target_name}'{resolved_note} is not in the instantiate target whitelist.
        Pass _target_whitelist_ from trusted code to allow expected targets."""
    )


def _non_whitelistable_target_message(target_name: str, resolved_from: str) -> str:
    resolved_note = _resolved_from_note(target_name, resolved_from)
    if target_name == "hydra._internal.instantiate._instantiate2.instantiate":
        return dedent(
            f"""\
            Target '{target_name}'{resolved_note} cannot be authorized by the instantiate
            target whitelist because reentrant instantiate calls do not safely inherit
            the effective whitelist. Call instantiate() from trusted Python code instead."""
        )
    if target_name in {
        "operator.call",
        "operator.attrgetter",
        "operator.methodcaller",
        "_operator.call",
        "_operator.attrgetter",
        "_operator.methodcaller",
    }:
        return dedent(
            f"""\
            Target '{target_name}'{resolved_note} cannot be authorized by the instantiate
            target whitelist because it performs generic selection or dispatch using
            config data.
            Set '_target_' to the intended callable instead."""
        )
    return dedent(
        f"""\
        Target '{target_name}'{resolved_note} cannot be authorized by the instantiate
        target whitelist because it delegates the effective operation to config data.
        Set '_target_' to the intended callable instead."""
    )


def _reject_non_whitelistable_target(
    target_name: str,
    resolved_from: str,
    full_key: str,
    target_whitelist: NormalizedTargetWhitelist,
) -> None:
    if (
        target_whitelist is not None
        and target_whitelist is not UNSAFE_ALLOW_ALL_TARGETS
        and target_name in NON_WHITELISTABLE_TARGETS
    ):
        raise InstantiationException(
            _with_full_key(
                _non_whitelistable_target_message(target_name, resolved_from),
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
                    _blocklisted_target_message(target_name, resolved_from), full_key
                )
            )
    elif not _is_target_whitelisted(
        target_name, cast(Tuple[str, ...], target_whitelist)
    ):
        raise InstantiationException(
            _with_full_key(
                _not_whitelisted_message(target_name, resolved_from), full_key
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
    resolved_name = _get_os_alias_target(_get_resolved_target_name_for_check(result))
    _reject_non_whitelistable_target(resolved_name, path, full_key, target_whitelist)
    if resolved_name != path and _requires_resolved_authorization(
        path, target_whitelist
    ):
        _authorize_target_name(resolved_name, path, full_key, target_whitelist)


def _authorize_callable_result(
    result: Callable[..., Any],
    resolved_from: str,
    full_key: str,
    target_whitelist: NormalizedTargetWhitelist,
) -> None:
    """Authorize a callable selected as another target's runtime result."""
    resolved_name = _get_os_alias_target(_get_resolved_target_name_for_check(result))
    _authorize_target_name(resolved_name, resolved_from, full_key, target_whitelist)


def _resolve_target(
    target: Union[str, type, Callable[..., Any]],
    full_key: str,
    target_whitelist: NormalizedTargetWhitelist = None,
) -> Union[type, Callable[..., Any]]:
    """Resolve target string, type or callable into type or callable."""
    if isinstance(target, str) or callable(target):
        target_name = (
            target
            if isinstance(target, str)
            else _get_os_alias_target(_get_resolved_target_name_for_check(target))
        )

        # Stage 1: authorize a string literally before import, or authorize an
        # already-resolved callable by its canonical identity.
        _authorize_target_name(target_name, target_name, full_key, target_whitelist)

        resolved_name = target_name
        if isinstance(target, str):
            try:
                target = _locate(target)
            except Exception as e:
                msg = f"Error locating target '{target}'"
                raise InstantiationException(_with_full_key(msg, full_key)) from e

            # Stage 2: authorize the resolved object's canonical identity. This
            # closes aliasing bypasses where the string passes stage 1 but the
            # resolved callable lives elsewhere (e.g. logging.os.system -> os.system).
            # Skipped for an exact whitelist entry, which authoritatively allows a
            # re-exported target whose canonical module differs from the string.
            resolved_name = _get_os_alias_target(
                _get_resolved_target_name_for_check(target)
            )
            _reject_non_whitelistable_target(
                resolved_name, target_name, full_key, target_whitelist
            )
            if resolved_name != target_name and _requires_resolved_authorization(
                target_name, target_whitelist
            ):
                _authorize_target_name(
                    resolved_name, target_name, full_key, target_whitelist
                )

        if resolved_name == "functools.partial":
            _warn_direct_functools_partial_target()
        if target_whitelist is None:
            _warn_legacy_target_whitelist(target_name)
    if not callable(target):
        msg = f"Expected a callable target, got '{target}' of type '{type(target).__name__}'"
        raise InstantiationException(_with_full_key(msg, full_key))
    return target


def instantiate(
    config: Any,
    *args: Any,
    _target_whitelist_: TargetWhitelist = None,
    **kwargs: Any,
) -> Any:
    """
    :param config: An config object describing what to call and what params to use.
                   In addition to the parameters, the config must contain:
                   _target_ : target class or callable name (str)
                              IMPORTANT: This may pose a security risk since the config
                              can be used to execute arbitrary code. Make sure to use this only
                              with trusted configs or configure the target whitelist.
                   And may contain:
                   _args_: List-like of positional arguments to pass to the target
                   _recursive_: Construct nested objects as well (bool).
                                True by default.
                                may be overridden via a _recursive_ key in
                                the kwargs
                   _convert_: Conversion strategy
                        none    : Passed objects are DictConfig, ListConfig and
                                  TupleConfig, default
                        partial : Passed objects are converted to dict, list and
                                  tuple, with the exception of Structured Configs
                                  (and their fields).
                        object  : Passed objects are converted to dict, list and tuple.
                                  Structured Configs are converted to instances of the
                                  backing dataclass / attr class.
                        all     : Passed objects are dicts, lists, tuples and
                                  primitives without a trace of OmegaConf containers.
                                  Structured configs are converted to primitive
                                  containers too.
                   _partial_: If True, return functools.partial wrapped method or object
                              False by default. Configure per target.
    :param _target_whitelist_: A target string, list of target strings,
                    target_whitelist() policy, or UNSAFE_ALLOW_ALL_TARGETS. A trailing
                    .* allows targets under a package prefix. Passing None preserves
                    legacy behavior unless a target_whitelist() context is active.
    :param args: Optional positional parameters pass-through
    :param kwargs: Optional named parameters to override
                   parameters in the config object. Parameters not present
                   in the config objects are being passed as is to the target.
                   Plain Python missing values and interpolation syntax are not
                   supported in call-site overrides; pass concrete runtime
                   values or an explicit OmegaConf container instead.
                   A dict replaces a configured plain mapping, but merges into
                   a configured Structured Config or target config.
                   Dataclass and attrs instances are passed through without
                   conversion or recursive instantiation.
    :return: if _target_ is a class name: the instantiated object
             if _target_ is a callable: the return value of the call
    """

    # Return None if config is None
    if config is None:
        return None

    target_whitelist = _resolve_target_whitelist(_target_whitelist_)

    for index, value in enumerate(args):
        _validate_callsite_override(value, (_Keys.ARGS, index))
    for key, value in kwargs.items():
        _validate_callsite_override(value, (key,))

    if isinstance(config, (dict, list)) or type(config) is tuple:
        config = _prepare_input_container(config)

    kwargs = _prepare_input_container(kwargs)

    # Structured Config always converted first to OmegaConf
    if (
        is_structured_config(config)
        or isinstance(config, (dict, list))
        or type(config) is tuple
    ):
        config = OmegaConf.structured(config, flags={"allow_objects": True})

    if OmegaConf.is_dict(config):
        resolution_overrides = dict(kwargs)
        if args:
            resolution_overrides[_Keys.ARGS] = args
        if resolution_overrides:
            config = _copy_config_with_override_interpolations(
                config, resolution_overrides
            )
        return instantiate_node(
            config,
            *args,
            overrides=kwargs,
            is_root=True,
            target_whitelist=target_whitelist,
        )
    elif OmegaConf.is_sequence(config):
        _recursive_ = kwargs.pop(_Keys.RECURSIVE, True)
        _convert_ = kwargs.pop(_Keys.CONVERT, ConvertMode.NONE)
        _partial_ = kwargs.pop(_Keys.PARTIAL, False)

        if _partial_:
            sequence_type = "tuple" if OmegaConf.is_tuple(config) else "list"
            raise InstantiationException(
                "The _partial_ keyword is not compatible with "
                f"top-level {sequence_type} instantiation"
            )

        return instantiate_node(
            config,
            *args,
            recursive=_recursive_,
            convert=_convert_,
            partial=_partial_,
            target_whitelist=target_whitelist,
        )
    else:
        raise InstantiationException(
            dedent(f"""\
                Cannot instantiate config of type {type(config).__name__}.
                Top level config must be an OmegaConf DictConfig/ListConfig/TupleConfig object,
                a plain dict/list/tuple, or a Structured Config class or instance.""")
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


def _wrap_structured_config_as_object(value: Any) -> Any:
    if is_structured_config(value):
        return AnyNode(value, flags={"allow_objects": True})
    if isinstance(value, dict):
        return {
            key: _wrap_structured_config_as_object(item) for key, item in value.items()
        }
    if isinstance(value, list):
        return [_wrap_structured_config_as_object(item) for item in value]
    if type(value) is tuple:
        return tuple(_wrap_structured_config_as_object(item) for item in value)
    return value


def _restore_nested_structured_config_objects(node: Any, value: Any) -> Any:
    if is_structured_config(value):
        return AnyNode(value, flags={"allow_objects": True})
    if isinstance(value, dict) and isinstance(node, DictConfig):
        content = node.__dict__["_content"]
        for key, item in value.items():
            child = node._get_node(key, validate_access=False)
            restored = _restore_nested_structured_config_objects(child, item)
            if restored is not child:
                restored._set_parent(node)
                restored._set_key(key)
                content[key] = restored
    elif isinstance(value, (list, tuple)) and OmegaConf.is_sequence(node):
        content = node.__dict__["_content"]
        for index, item in enumerate(value):
            child = node._get_node(index)
            restored = _restore_nested_structured_config_objects(child, item)
            if restored is not child:
                restored._set_parent(node)
                restored._set_key(index)
                content[index] = restored
    return node


def _create_sequence_result(
    items: List[Any],
    *,
    is_tuple: bool,
    convert: Union[str, ConvertMode],
    parent: Any = None,
) -> Any:
    if convert in (ConvertMode.ALL, ConvertMode.PARTIAL, ConvertMode.OBJECT):
        return tuple(items) if is_tuple else items

    if is_tuple:
        result = OmegaConf.create(
            tuple(_wrap_structured_config_as_object(item) for item in items),
            flags={"allow_objects": True},
        )
    else:
        result = OmegaConf.create([], flags={"allow_objects": True})
        for item in items:
            result.append(_wrap_structured_config_as_object(item))
    if parent is not None:
        result._set_parent(parent)
    return result


def _get_dict_override(value: Any) -> Optional[ConfigOverlay]:
    if is_structured_config(value):
        return None
    if isinstance(value, dict):
        return value
    if OmegaConf.is_dict(value):
        return cast(DictConfig, value)
    return None


def _iter_effective_keys(node: Any, overrides: Optional[ConfigOverlay]) -> List[str]:
    keys = list(node.keys())
    if overrides:
        keys.extend(key for key in overrides if key not in keys)
    return keys


def _get_effective_control(
    node: Any,
    overrides: Optional[ConfigOverlay],
    key: _Keys,
    default: Any,
) -> Any:
    if overrides is not None and key in overrides:
        return overrides[key]
    return node[key] if key in node else default


def _is_missing_parameter(
    node: Any, overrides: Optional[ConfigOverlay], key: str
) -> bool:
    if overrides is not None and key in overrides:
        return isinstance(overrides[key], str) and overrides[key] == "???"
    return OmegaConf.is_missing(node, key)


def _instantiate_override(
    value: Any,
    *,
    convert: Union[str, ConvertMode],
    recursive: bool,
    target_whitelist: NormalizedTargetWhitelist,
) -> Any:
    if is_structured_config(value):
        return value

    dict_override = _get_dict_override(value)
    if not recursive:
        if isinstance(dict_override, DictConfig) and (
            dict_override._metadata.object_type not in (None, dict)
        ):
            return dict_override
        return value

    if dict_override is not None:
        return instantiate_node(
            OmegaConf.create({}),
            overrides=dict_override,
            convert=convert,
            recursive=recursive,
            target_whitelist=target_whitelist,
        )

    if isinstance(value, (list, tuple)):
        items = [
            _instantiate_override(
                item,
                convert=convert,
                recursive=recursive,
                target_whitelist=target_whitelist,
            )
            for item in value
        ]
        return _create_sequence_result(
            items, is_tuple=isinstance(value, tuple), convert=convert
        )

    if OmegaConf.is_config(value):
        return instantiate_node(
            value,
            convert=convert,
            recursive=recursive,
            target_whitelist=target_whitelist,
        )
    return value


def _get_dict_override_merge_base(
    node: Any, key: str, *, is_target_parameter: bool
) -> Optional[ConfigOverlay]:
    """Return the configured mapping to merge with a dict override, if any."""
    configured_value = node._get_node(key, validate_access=False)
    if (
        is_target_parameter
        and configured_value is not None
        and configured_value._is_interpolation()
    ):
        try:
            configured_value = node[key]
        except InterpolationResolutionError:
            return None
    if isinstance(configured_value, dict):
        return configured_value if _is_target(configured_value) else None
    if not isinstance(configured_value, DictConfig):
        return None
    if (
        not is_target_parameter
        or is_structured_config(configured_value._metadata.ref_type)
        or is_structured_config(configured_value._metadata.object_type)
        or (
            not configured_value._is_none()
            and not configured_value._is_missing()
            and _is_target(configured_value)
        )
    ):
        return configured_value
    return None


def _get_override_child(source: Any, key: Any) -> Any:
    if isinstance(source, DictConfig):
        return source._get_node(key, validate_access=False)
    if OmegaConf.is_sequence(source):
        return source._get_node(key)
    return source[key]


def _replace_child(parent: Any, key: Any, child: Any) -> None:
    child._set_parent(parent)
    child._set_key(key)
    parent.__dict__["_content"][key] = child


def _override_mapping(value: Any) -> Optional[ConfigOverlay]:
    if OmegaConf.is_config(value) and (
        value._is_none() or value._is_missing() or value._is_interpolation()
    ):
        return None
    return _get_dict_override(value)


def _create_override_node(
    value: Any,
    *,
    source: Any,
    key: Any,
    path: Tuple[Any, ...],
    storage: Dict[str, Tuple[Any, Any]],
) -> Any:
    mapping = _override_mapping(value)
    if mapping is not None:
        result = OmegaConf.create({}, flags={"allow_objects": True})
        for child_key in mapping:
            child = _create_override_node(
                _get_override_child(mapping, child_key),
                source=mapping,
                key=child_key,
                path=(*path, child_key),
                storage=storage,
            )
            _replace_child(result, child_key, child)
        return result

    if not is_structured_config(value) and (
        isinstance(value, (list, tuple)) or OmegaConf.is_sequence(value)
    ):
        is_tuple = type(value) is tuple or OmegaConf.is_tuple(value)
        result = OmegaConf.create(() if is_tuple else [])
        content = []
        for index in range(len(value)):
            child = _create_override_node(
                _get_override_child(value, index),
                source=value,
                key=index,
                path=(*path, index),
                storage=storage,
            )
            child._set_parent(result)
            child._set_key(index)
            content.append(child)
        result.__dict__["_content"] = content
        return result

    name = re.sub(r"[^A-Za-z0-9_]+", "_", ".".join(map(str, path))).strip("_")
    name = name or "value"
    if name[0].isdigit() or name.lower() in {"false", "inf", "nan", "null", "true"}:
        name = f"value_{name}"
    token = name
    index = 2
    while token in storage:
        token = f"{name}_{index}"
        index += 1
    storage[token] = (source, key)
    return AnyNode(
        f"${{{_INSTANTIATE_OVERRIDE_RESOLVER}:{token}}}",
        flags={"allow_objects": True},
    )


def _apply_override_interpolations(
    node: DictConfig,
    overrides: ConfigOverlay,
    storage: Dict[str, Tuple[Any, Any]],
    *,
    is_target_parameter: bool,
) -> None:
    configured_values = {}
    override_nodes = {}
    for key in overrides:
        configured_values[key] = node._get_node(key, validate_access=False)
        override = _get_override_child(overrides, key)
        override_nodes[key] = _create_override_node(
            override,
            source=overrides,
            key=key,
            path=(key,),
            storage=storage,
        )
        _replace_child(node, key, override_nodes[key])

    mapping_keys = [
        key
        for key in overrides
        if configured_values[key] is not None
        and _override_mapping(_get_override_child(overrides, key)) is not None
    ]
    # Each pass lets another interpolation level observe effective overrides.
    for _ in mapping_keys:
        for key in mapping_keys:
            current_value = node._get_node(key, validate_access=False)
            _replace_child(node, key, configured_values[key])
            try:
                merge_base = _get_dict_override_merge_base(
                    node, key, is_target_parameter=is_target_parameter
                )
            finally:
                _replace_child(node, key, current_value)

            if merge_base is not None:
                merged = OmegaConf.merge(merge_base, override_nodes[key])
                _replace_child(node, key, merged)


def _copy_config_with_override_interpolations(
    config: DictConfig, overrides: ConfigOverlay
) -> DictConfig:
    OmegaConf.register_resolver(
        _INSTANTIATE_OVERRIDE_RESOLVER,
        _resolve_instantiate_override,
        replace=True,
        annotation_validation="off",
    )

    path = []
    current: Any = config
    while current._get_parent() is not None:
        path.append(current._key())
        current = current._get_parent()

    copied_root = copy.deepcopy(current)
    copied_config = copied_root
    for key in reversed(path):
        copied_config = _get_override_child(copied_config, key)

    if copied_config._is_none():
        ref_type = copied_config._metadata.ref_type
        parent = copied_config._get_parent()
        key = copied_config._key()
        copied_config = (
            OmegaConf.structured(ref_type)
            if is_structured_config(ref_type)
            else OmegaConf.create({})
        )
        if parent is None:
            copied_root = copied_config
        else:
            _replace_child(parent, key, copied_config)

    storage: Dict[str, Tuple[Any, Any]] = dict(
        current.__dict__.get(_INSTANTIATE_OVERRIDE_STORAGE, {})
    )
    copied_root.__dict__[_INSTANTIATE_OVERRIDE_STORAGE] = storage
    _apply_override_interpolations(
        copied_config,
        overrides,
        storage,
        is_target_parameter=_Keys.TARGET in overrides or _is_target(copied_config),
    )
    return copied_config


def _instantiate_effective_value(
    node: Any,
    key: str,
    overrides: Optional[ConfigOverlay],
    *,
    is_target_parameter: bool,
    convert: Union[str, ConvertMode],
    recursive: bool,
    target_whitelist: NormalizedTargetWhitelist,
) -> Any:
    if overrides is not None and key in overrides:
        override = overrides[key]
        dict_override = _get_dict_override(override)
        if dict_override is not None:
            configured_value = _get_dict_override_merge_base(
                node, key, is_target_parameter=is_target_parameter
            )
            if configured_value is not None:
                value = OmegaConf.merge(configured_value, dict_override)
                if isinstance(dict_override, dict):
                    _restore_nested_structured_config_objects(value, dict_override)
                if recursive:
                    value = instantiate_node(
                        value,
                        convert=convert,
                        recursive=recursive,
                        target_whitelist=target_whitelist,
                    )
                return value
        return _instantiate_override(
            override,
            convert=convert,
            recursive=recursive,
            target_whitelist=target_whitelist,
        )

    value = node[key]
    if recursive:
        value = instantiate_node(
            value,
            convert=convert,
            recursive=recursive,
            target_whitelist=target_whitelist,
        )
    return value


def instantiate_node(
    node: Any,
    *args: Any,
    overrides: Optional[ConfigOverlay] = None,
    convert: Union[str, ConvertMode] = ConvertMode.NONE,
    recursive: bool = True,
    partial: bool = False,
    is_root: bool = False,
    target_whitelist: NormalizedTargetWhitelist = None,
) -> Any:
    # Return None if config is None
    if node is None or (
        OmegaConf.is_config(node) and node._is_none() and not overrides
    ):
        return None

    if OmegaConf.is_config(node) and node._is_none() and overrides:
        ref_type = node._metadata.ref_type
        parent = node._get_parent()
        key = node._key()
        node = (
            OmegaConf.structured(ref_type)
            if is_structured_config(ref_type)
            else OmegaConf.create({})
        )
        node._set_parent(parent)
        node._set_key(key)

    if not OmegaConf.is_config(node):
        return node

    # Override parent modes from config if specified
    if OmegaConf.is_dict(node):
        # using getitem instead of get(key, default) because OmegaConf will raise an exception
        # if the key type is incompatible on get.
        convert = _get_effective_control(node, overrides, _Keys.CONVERT, convert)
        recursive = _get_effective_control(node, overrides, _Keys.RECURSIVE, recursive)
        partial = _get_effective_control(node, overrides, _Keys.PARTIAL, partial)

    full_key = node._get_full_key(None)

    if not isinstance(recursive, bool):
        msg = f"Instantiation: _recursive_ flag must be a bool, got {type(recursive)}"
        raise TypeError(_with_full_key(msg, full_key))

    if not isinstance(partial, bool):
        msg = f"Instantiation: _partial_ flag must be a bool, got {type(partial)}"
        if node and full_key:
            msg += f"\nfull_key: {full_key}"
        raise TypeError(msg)

    # If OmegaConf sequence, create a new sequence of instances if recursive
    if OmegaConf.is_sequence(node):
        is_tuple = OmegaConf.is_tuple(node)
        items = [
            instantiate_node(
                item,
                convert=convert,
                recursive=recursive,
                target_whitelist=target_whitelist,
            )
            for item in node._iter_ex(resolve=True)
        ]

        return _create_sequence_result(
            items, is_tuple=is_tuple, convert=convert, parent=node
        )

    elif OmegaConf.is_dict(node):
        if _Keys.TARGET_WHITELIST in node:
            msg = (
                "_target_whitelist_ must be passed to instantiate() from trusted "
                "code, not configured inside the config being instantiated."
            )
            raise InstantiationException(_with_full_key(msg, full_key))

        exclude_keys = set({"_target_", "_convert_", "_recursive_", "_partial_"})
        if (overrides is not None and _Keys.TARGET in overrides) or _is_target(node):
            target = (
                overrides[_Keys.TARGET]
                if overrides is not None and _Keys.TARGET in overrides
                else node.get(_Keys.TARGET)
            )
            _target_ = _resolve_target(target, full_key, target_whitelist)
            kwargs = {}
            is_partial = partial
            for key in _iter_effective_keys(node, overrides):
                if key not in exclude_keys:
                    if is_partial and _is_missing_parameter(node, overrides, key):
                        continue
                    value = _instantiate_effective_value(
                        node,
                        key,
                        overrides,
                        is_target_parameter=True,
                        convert=convert,
                        recursive=recursive,
                        target_whitelist=target_whitelist,
                    )
                    kwargs[key] = _convert_node(value, convert)

            return _call_target(
                _target_, partial, args, kwargs, full_key, target_whitelist
            )
        else:
            object_type = node._metadata.object_type
            if isinstance(overrides, DictConfig):
                override_type = overrides._metadata.object_type
                if override_type not in (None, dict):
                    object_type = override_type

            # If ALL or PARTIAL non structured or OBJECT non structured,
            # instantiate in dict and resolve interpolations eagerly.
            if convert == ConvertMode.ALL or (
                convert in (ConvertMode.PARTIAL, ConvertMode.OBJECT)
                and object_type in (None, dict)
            ):
                dict_items = {}
                for key in _iter_effective_keys(node, overrides):
                    if is_root and key in exclude_keys:
                        continue
                    # list items inherits recursive flag from the containing dict.
                    dict_items[key] = _instantiate_effective_value(
                        node,
                        key,
                        overrides,
                        is_target_parameter=False,
                        convert=convert,
                        recursive=recursive,
                        target_whitelist=target_whitelist,
                    )
                return dict_items
            else:
                # Otherwise use DictConfig and resolve interpolations lazily.
                cfg = OmegaConf.create({}, flags={"allow_objects": True})
                for key in _iter_effective_keys(node, overrides):
                    if is_root and key in exclude_keys:
                        continue
                    cfg[key] = _wrap_structured_config_as_object(
                        _instantiate_effective_value(
                            node,
                            key,
                            overrides,
                            is_target_parameter=False,
                            convert=convert,
                            recursive=recursive,
                            target_whitelist=target_whitelist,
                        )
                    )
                cfg._set_parent(node)
                cfg._metadata.object_type = object_type
                if convert == ConvertMode.OBJECT:
                    return OmegaConf.to_object(cfg)
                return cfg

    else:
        assert False, f"Unexpected config type : {type(node).__name__}"

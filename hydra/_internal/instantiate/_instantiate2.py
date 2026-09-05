# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved

import copy
import inspect
import re
import weakref
from contextlib import ExitStack, contextmanager, nullcontext
from enum import Enum
from textwrap import dedent
from typing import (
    Any,
    Callable,
    ContextManager,
    Dict,
    Iterator,
    List,
    Optional,
    Sequence,
    Tuple,
    Union,
    cast,
)

from omegaconf import (
    AnyNode,
    Container,
    DictConfig,
    Node,
    OmegaConf,
    SCMode,
    UnionNode,
    flag_override,
)
from omegaconf._utils import is_structured_config
from omegaconf.errors import InterpolationResolutionError

from hydra._internal.deprecation_warning import deprecation_warning
from hydra._internal.target_policy import (
    ExecutionWhitelist,
    NormalizedExecutionWhitelist,
    _authorize_discovery_path,
    _authorize_resolved_target_identity,
    _authorize_target_invocation,
    _authorize_target_name,
    _DeferredTarget,
    _get_effective_target_invocation,
    _get_os_alias_target,
    _get_resolved_target_name_for_check,
    _mediate_target_result,
    _resolve_execution_whitelist,
    _with_full_key,
)
from hydra._internal.utils import _locate
from hydra.errors import InstantiationException
from hydra.types import ConvertMode

ConfigOverlay = Union[Dict[str, Any], DictConfig]
DeferredCallContext = Optional[
    Callable[[_DeferredTarget, Tuple[Any, ...], Dict[str, Any]], ContextManager[None]]
]
_INSTANTIATE_OVERRIDE_RESOLVER = "hydra.instantiate_override"
_INSTANTIATE_OVERRIDE_STORAGE = "_hydra_instantiate_overrides"


def _resolve_instantiate_override(token: str, *, _root_: Any) -> Any:
    source, key = _root_.__dict__[_INSTANTIATE_OVERRIDE_STORAGE][token]
    return source[key]


class _Keys(str, Enum):
    """Special keys in configs used by instantiate."""

    TARGET = "_target_"
    CONVERT = "_convert_"
    RECURSIVE = "_recursive_"
    ARGS = "_args_"
    PARTIAL = "_partial_"
    EXECUTION_WHITELIST = "_execution_whitelist_"


def _is_target(x: Any) -> bool:
    if isinstance(x, dict):
        return "_target_" in x
    if OmegaConf.is_dict(x):
        return "_target_" in x
    return False


@contextmanager
def _read_only_config_tree(*configs: Node) -> Iterator[None]:
    context_roots = {id(config._get_root()) for config in configs}
    nodes = []
    pending: List[Node] = []
    for config in configs:
        ancestor: Optional[Node] = config
        while ancestor is not None:
            # Merged nodes can retain a parent only as interpolation context and
            # may therefore not be owned by the next ancestor.
            pending.append(ancestor)
            ancestor = ancestor._get_parent()
    seen = set()
    while pending:
        node = pending.pop()
        if id(node) in seen:
            continue
        seen.add(id(node))

        if isinstance(node, Container):
            nodes.append(node)
            keys: Sequence[Any]
            if isinstance(node, DictConfig):
                keys = list(node.keys())
            else:
                keys = range(len(cast(Sequence[Any], node)))
            for key in keys:
                child = node._get_node(key)
                if isinstance(child, Node):
                    pending.append(child)
        elif isinstance(node, UnionNode):
            child = node._value()
            if isinstance(child, Node):
                pending.append(child)

    root_overrides = ExitStack()
    descendant_overrides = ExitStack()
    try:
        for node in nodes:
            if id(node) in context_roots or node._is_flags_root():
                root_overrides.enter_context(flag_override(node, "readonly", True))
            elif node._get_node_flag("readonly") is not True:
                # Remove local False overrides so the node inherits the guard.
                # Leaving descendants without local True flags also preserves
                # read_write(parent)'s normal subtree behavior.
                descendant_overrides.enter_context(
                    flag_override(node, "readonly", None)
                )
        yield
    finally:
        # Restore roots before descendants so context-parented nodes invalidate
        # their inherited flag cache against the restored root state.
        root_overrides.close()
        descendant_overrides.close()


class _ReadOnlyDeferredTargetContext:
    def __init__(self, config: Optional[Node]) -> None:
        self._config_refs: List[weakref.ReferenceType[Node]] = []
        while config is not None:
            self._config_refs.append(weakref.ref(config))
            config = config._get_parent()

    def __call__(
        self,
        _deferred: _DeferredTarget,
        _args: Tuple[Any, ...],
        _kwargs: Dict[str, Any],
    ) -> ContextManager[None]:
        configs = [config for ref in self._config_refs if (config := ref()) is not None]
        return _read_only_config_tree(*configs) if configs else nullcontext()

    def __deepcopy__(self, memo: Dict[int, Any]) -> "_ReadOnlyDeferredTargetContext":
        # A deep-copied deferred target remains in this process and can retain
        # callable closures that reach the source tree, so preserve its guard.
        copied = type(self)(None)
        memo[id(self)] = copied
        copied._config_refs = self._config_refs.copy()
        return copied


def _warn_legacy_execution_whitelist(target: str) -> None:
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
            _execution_whitelist_. This preserves legacy behavior but is deprecated
            because config-controlled targets can execute arbitrary code. This
            warning will become an error in Hydra 1.5. Pass an execution whitelist
            from trusted call-site code, or pass UNSAFE_DISABLE_EXECUTION_CHECKS to
            explicitly keep legacy behavior.
            See https://hydra.cc/docs/advanced/execution_whitelist/"""
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


def _call_target(
    _target_: Callable[..., Any],
    _partial_: bool,
    args: Tuple[Any, ...],
    kwargs: Dict[str, Any],
    full_key: str,
    execution_whitelist: NormalizedExecutionWhitelist,
    deferred_call_context: DeferredCallContext,
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
    effective_target, effective_args, effective_kwargs = (
        _get_effective_target_invocation(_target_, args, kwargs)
    )
    _authorize_target_invocation(
        effective_target,
        effective_args,
        effective_kwargs,
        full_key,
        execution_whitelist,
        allow_incomplete_partial=_partial_,
    )
    discovery_path = _authorize_discovery_path(
        effective_target,
        effective_args,
        effective_kwargs,
        full_key,
        execution_whitelist,
    )
    try:
        if _partial_:
            deferred = _DeferredTarget(_target_, *args, **kwargs)
            deferred._hydra_resolved_from = discovery_path or resolved_target_name
            deferred._hydra_full_key = full_key
            deferred._hydra_execution_whitelist = execution_whitelist
            deferred._hydra_call_context = deferred_call_context
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
        execution_whitelist,
        discovery_path=discovery_path,
        call_context=deferred_call_context,
    )


def _convert_target_to_string(t: Any) -> Any:
    if callable(t) and hasattr(t, "__qualname__"):
        return f"{t.__module__}.{t.__qualname__}"
    else:
        return t


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


def _resolve_target(
    target: Union[str, type, Callable[..., Any]],
    full_key: str,
    execution_whitelist: NormalizedExecutionWhitelist = None,
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
        _authorize_target_name(target_name, target_name, full_key, execution_whitelist)

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
            resolved_name = _authorize_resolved_target_identity(
                target, target_name, full_key, execution_whitelist
            )

        if resolved_name == "functools.partial":
            _warn_direct_functools_partial_target()
        if execution_whitelist is None:
            _warn_legacy_execution_whitelist(target_name)
    if not callable(target):
        msg = f"Expected a callable target, got '{target}' of type '{type(target).__name__}'"
        raise InstantiationException(_with_full_key(msg, full_key))
    return target


def instantiate(
    config: Any,
    *args: Any,
    _execution_whitelist_: ExecutionWhitelist = None,
    **kwargs: Any,
) -> Any:
    """
    :param config: An config object describing what to call and what params to use.
                   In addition to the parameters, the config must contain:
                   _target_ : target class or callable name (str)
                              IMPORTANT: This may pose a security risk since the config
                              can be used to execute arbitrary code. Make sure to use this only
                              with trusted configs or configure the execution whitelist.
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
    :param _execution_whitelist_: A target string, list of target strings,
                    execution_whitelist() policy, or UNSAFE_DISABLE_EXECUTION_CHECKS. A trailing
                    .* allows targets under a package prefix. Passing None preserves
                    legacy behavior unless a execution_whitelist() context is active.
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

    execution_whitelist = _resolve_execution_whitelist(_execution_whitelist_)
    source_config_is_omegaconf = OmegaConf.is_config(config)

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
                execution_whitelist=execution_whitelist,
            )
        guard = (
            _read_only_config_tree(config)
            if source_config_is_omegaconf
            else nullcontext()
        )
        deferred_call_context = (
            _ReadOnlyDeferredTargetContext(config)
            if source_config_is_omegaconf
            else None
        )
        # No private copy was made for OmegaConf input. Keep the entire
        # instantiation read-only, including target constructors.
        with guard:
            return instantiate_node(
                config,
                *args,
                overrides=kwargs,
                is_root=True,
                execution_whitelist=execution_whitelist,
                deferred_call_context=deferred_call_context,
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

        guard = (
            _read_only_config_tree(config)
            if source_config_is_omegaconf
            else nullcontext()
        )
        deferred_call_context = (
            _ReadOnlyDeferredTargetContext(config)
            if source_config_is_omegaconf
            else None
        )
        with guard:
            return instantiate_node(
                config,
                *args,
                recursive=_recursive_,
                convert=_convert_,
                partial=_partial_,
                execution_whitelist=execution_whitelist,
                deferred_call_context=deferred_call_context,
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
    execution_whitelist: NormalizedExecutionWhitelist,
    deferred_call_context: DeferredCallContext,
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
            execution_whitelist=execution_whitelist,
            deferred_call_context=deferred_call_context,
        )

    if isinstance(value, (list, tuple)):
        items = [
            _instantiate_override(
                item,
                convert=convert,
                recursive=recursive,
                execution_whitelist=execution_whitelist,
                deferred_call_context=deferred_call_context,
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
            execution_whitelist=execution_whitelist,
            deferred_call_context=deferred_call_context,
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
        parent = current._get_parent()
        key = current._key()
        path.append((key, current, _get_override_child(parent, key) is current))
        current = parent

    copied_root = copy.deepcopy(current)
    copied_config = copied_root
    for key, source_config, parent_owns_source in reversed(path):
        copied_config = _get_override_child(copied_config, key)
        # Merged nodes can retain a parent only as interpolation context.
        if not parent_owns_source:
            # This tree is a private copy, so it is safe to mutate even when it
            # retains read-only flags from the source configuration.
            merge_source = copy.deepcopy(source_config)
            # Isolate the private source from flags inherited through its
            # original parent while preserving that parent for interpolation.
            merge_source._set_flags_root(True)
            copied_config._merge_with(merge_source, _allow_readonly_target=True)

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
    execution_whitelist: NormalizedExecutionWhitelist,
    deferred_call_context: DeferredCallContext,
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
                        execution_whitelist=execution_whitelist,
                        deferred_call_context=deferred_call_context,
                    )
                return value
        return _instantiate_override(
            override,
            convert=convert,
            recursive=recursive,
            execution_whitelist=execution_whitelist,
            deferred_call_context=deferred_call_context,
        )

    value = node[key]
    if recursive:
        value = instantiate_node(
            value,
            convert=convert,
            recursive=recursive,
            execution_whitelist=execution_whitelist,
            deferred_call_context=deferred_call_context,
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
    execution_whitelist: NormalizedExecutionWhitelist = None,
    deferred_call_context: DeferredCallContext = None,
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
                execution_whitelist=execution_whitelist,
                deferred_call_context=deferred_call_context,
            )
            for item in node._iter_ex(resolve=True)
        ]

        return _create_sequence_result(
            items, is_tuple=is_tuple, convert=convert, parent=node
        )

    elif OmegaConf.is_dict(node):
        if _Keys.EXECUTION_WHITELIST in node:
            msg = (
                "_execution_whitelist_ must be passed to instantiate() from trusted "
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
            _target_ = _resolve_target(target, full_key, execution_whitelist)
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
                        execution_whitelist=execution_whitelist,
                        deferred_call_context=deferred_call_context,
                    )
                    kwargs[key] = _convert_node(value, convert)

            return _call_target(
                _target_,
                partial,
                args,
                kwargs,
                full_key,
                execution_whitelist,
                deferred_call_context,
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
                        execution_whitelist=execution_whitelist,
                        deferred_call_context=deferred_call_context,
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
                            execution_whitelist=execution_whitelist,
                            deferred_call_context=deferred_call_context,
                        )
                    )
                cfg._set_parent(node)
                cfg._metadata.object_type = object_type
                if convert == ConvertMode.OBJECT:
                    return OmegaConf.to_object(cfg)
                return cfg

    else:
        assert False, f"Unexpected config type : {type(node).__name__}"

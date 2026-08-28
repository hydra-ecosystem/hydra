# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved

import json
import logging.config
import os
from pathlib import Path
from typing import Any, Callable

import hydra._internal.instantiate._instantiate2
import hydra.types
from hydra._internal.deprecation_warning import deprecation_warning
from hydra._internal.target_policy import (
    UNSAFE_ALLOW_ALL_TARGETS as UNSAFE_ALLOW_ALL_TARGETS,
)
from hydra._internal.target_policy import (
    target_whitelist as target_whitelist,
)
from hydra._internal.utils import _locate
from hydra.core.hydra_config import HydraConfig

log = logging.getLogger(__name__)

# Instantiation related symbols
instantiate = hydra._internal.instantiate._instantiate2.instantiate
call = instantiate
ConvertMode = hydra.types.ConvertMode


def get_class(path: str) -> type:
    """
    Look up a class based on a dotpath.
    Fails if the path does not point to a class.

    >>> import my_module
    >>> from hydra.utils import get_class
    >>> assert get_class("my_module.MyClass") is my_module.MyClass
    """
    try:
        cls = _locate(path)
        if not isinstance(cls, type):
            raise ValueError(
                f"Located non-class of type '{type(cls).__name__}'"
                + f" while loading '{path}'"
            )
        return cls
    except Exception as e:
        log.error(f"Error getting class at {path}: {e}")
        raise e


def get_method(path: str) -> Callable[..., Any]:
    """
    Look up a callable based on a dotpath.
    Fails if the path does not point to a callable object.

    >>> import my_module
    >>> from hydra.utils import get_method
    >>> assert get_method("my_module.my_function") is my_module.my_function
    """
    try:
        obj = _locate(path)
        if not callable(obj):
            raise ValueError(
                f"Located non-callable of type '{type(obj).__name__}'"
                + f" while loading '{path}'"
            )
        cl: Callable[..., Any] = obj
        return cl
    except Exception as e:
        log.error(f"Error getting callable at {path} : {e}")
        raise e


# Alias for get_method
get_static_method = get_method


def get_object(path: str) -> Any:
    """
    Look up an entity based on the dotpath.
    Does not perform any type checks on the entity.

    >>> import my_module
    >>> from hydra.utils import get_object
    >>> assert get_object("my_module.my_object") is my_module.my_object
    """
    try:
        obj = _locate(path)
        return obj
    except Exception as e:
        log.error(f"Error getting object at {path} : {e}")
        raise e


def get_original_cwd() -> str:
    """
    :return: the original working directory the Hydra application was launched from
    """
    if not HydraConfig.initialized():
        raise ValueError(
            "get_original_cwd() must only be used after HydraConfig is initialized"
        )
    ret = HydraConfig.get().runtime.cwd
    assert ret is not None and isinstance(ret, str)
    return ret


def to_absolute_path(path: str) -> str:
    """
    converts the specified path to be absolute path.
    if the input path is relative, it's interpreted as relative to the original working directory
    if it's absolute, it's returned as is
    :param path: path to convert
    :return:
    """
    p = Path(path)
    if not HydraConfig.initialized():
        base = Path(os.getcwd())
    else:
        base = Path(get_original_cwd())
    if p.is_absolute():
        ret = p
    else:
        ret = base / p
    return str(ret)


def _to_hydra_override_value_str(obj: Any) -> str:
    if isinstance(obj, dict):
        return (
            "{"
            + ", ".join(
                f"{key}: {_to_hydra_override_value_str(value)}"
                for key, value in obj.items()
            )
            + "}"
        )
    elif isinstance(obj, list):
        return (
            "["
            + ", ".join([_to_hydra_override_value_str(value) for value in obj])
            + "]"
        )
    elif isinstance(obj, str):
        new_str = obj.replace('\\"', '\\\\"').replace('"', '\\"')
        return f'"{new_str}"'
    return json.dumps(obj)


def to_hydra_override_value_str(obj: Any) -> str:
    """Deprecated basic conversion of an object to a Hydra override value string."""
    deprecation_warning(
        "to_hydra_override_value_str() is deprecated and will be removed in "
        "Hydra 1.5. See "
        "https://github.com/hydra-ecosystem/hydra/pull/2930#issuecomment-5018616929",
        stacklevel=2,
    )
    return _to_hydra_override_value_str(obj)

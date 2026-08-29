# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any, Callable

TaskFunction = Callable[[Any], Any]


if TYPE_CHECKING:
    from hydra._internal.callbacks import Callbacks
    from hydra.core.config_loader import ConfigLoader


@dataclass
class HydraContext:
    config_loader: "ConfigLoader"
    callbacks: "Callbacks"
    execution_whitelist: Any = None


class RunMode(Enum):
    RUN = 1
    MULTIRUN = 2


class ConvertMode(Enum):
    """ConvertMode for instantiate, controls return type.

    A config is either config or instance-like (`_target_` field).

    If instance-like, instantiate resolves the callable (class or
    function) and returns the result of the call on the rest of the
    parameters.

    If "none", config-like configs will be kept as is.

    If "partial", config-like configs will be converted to native python
    containers (list and dict), unless they are structured configs (
    dataclasses or attr instances). Structured configs remain as DictConfig objects.

    If "object", config-like configs will be converted to native python
    containers (list and dict), unless they are structured configs (
    dataclasses or attr instances). Structured configs are converted to instances
    of the backing dataclass or attr class using OmegaConf.to_object.

    If "all", config-like configs will all be converted to native python
    containers (list and dict).
    """

    # Use DictConfig/ListConfig
    NONE = "none"
    # Convert the OmegaConf config to primitive container, Structured Configs are preserved
    PARTIAL = "partial"
    # Convert the OmegaConf config to primitive container, Structured Configs are converted to
    # dataclass / attr class instances.
    OBJECT = "object"
    # Fully convert the OmegaConf config to primitive containers (dict, list and primitives).
    ALL = "all"

    def __eq__(self, other: Any) -> Any:
        if isinstance(other, ConvertMode):
            return other.value == self.value
        elif isinstance(other, str):
            return other.upper() == self.name.upper()
        else:
            return NotImplemented

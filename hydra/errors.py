# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved
from typing import Optional, Sequence


class HydraException(Exception): ...


class CompactHydraException(HydraException): ...


class OverrideParseException(CompactHydraException):
    def __init__(self, override: str, message: str) -> None:
        super().__init__(message)
        self.override = override
        self.message = message


class InstantiationException(HydraException):
    """An error raised by Hydra during instantiation."""


class ConfigCompositionException(CompactHydraException): ...


class SearchPathException(CompactHydraException): ...


class MissingConfigException(IOError, ConfigCompositionException):
    def __init__(
        self,
        message: str,
        missing_cfg_file: Optional[str] = None,
        options: Optional[Sequence[str]] = None,
    ) -> None:
        super().__init__(message)
        self.missing_cfg_file = missing_cfg_file
        self.options = options


class HydraDeprecationError(HydraException): ...


class Hydra14MigrationWarning(UserWarning):
    """Warn about changes required before upgrading to Hydra 1.4."""


class Hydra15MigrationWarning(UserWarning):
    """Warn about changes required before upgrading to Hydra 1.5."""

# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved

# Source of truth for Hydra's version

import re
from textwrap import dedent
from typing import Any

from . import __version__
from ._internal.deprecation_warning import deprecation_warning
from .core.singleton import Singleton
from .errors import Hydra15MigrationWarning, HydraException

_UNSPECIFIED_: Any = object()

_MIN_SUPPORTED_VERSION_BASE = "1.3"

_VERSION_PATTERN = re.compile(
    r"(?P<major>[0-9]+)\.(?P<minor>[0-9]+)"
    r"(?:\.[0-9]+(?:rc[0-9]+|\.dev[0-9]+)?)?"
)


class VersionBase(metaclass=Singleton):
    def __init__(self) -> None:
        self.version_base = _get_version(__version__)

    def setbase(self, version: str) -> None:
        assert isinstance(version, str), f"Unexpected Version type : {type(version)}"
        self.version_base = version

    def getbase(self) -> str:
        return self.version_base

    @staticmethod
    def instance(*args: Any, **kwargs: Any) -> "VersionBase":
        return Singleton.instance(VersionBase, *args, **kwargs)  # type: ignore


def _parse_version(ver: str) -> tuple[int, int]:
    if not isinstance(ver, str):
        raise TypeError(f"Expected version string, got {type(ver).__name__}")

    match = _VERSION_PATTERN.fullmatch(ver)
    if match is None:
        raise ValueError(f"Invalid version: {ver!r}")

    return int(match.group("major")), int(match.group("minor"))


def _get_version(ver: str) -> str:
    major, minor = _parse_version(ver)
    return f"{major}.{minor}"


def getbase() -> str:
    return VersionBase.instance().getbase()


def setbase(ver: Any) -> None:
    """
    Record the deprecated `version_base` parameter for runtime reporting.
    """
    if ver is _UNSPECIFIED_:
        _version_base = _get_version(__version__)
    else:
        if ver is None:
            _version_base = _get_version(__version__)
        else:
            _version_base = _get_version(ver)
            if _parse_version(_version_base) < _parse_version(
                _MIN_SUPPORTED_VERSION_BASE
            ):
                raise HydraException(
                    f"version_base={ver!r} is not supported in Hydra 1.4; "
                    "omit version_base to use the current behavior"
                )
        deprecation_warning(
            message=dedent("""\
            The version_base parameter is deprecated and will be removed in Hydra 1.5.
            Omit the version_base parameter to use the current Hydra defaults."""),
            stacklevel=3,
            category=Hydra15MigrationWarning,
        )
    VersionBase.instance().setbase(_version_base)

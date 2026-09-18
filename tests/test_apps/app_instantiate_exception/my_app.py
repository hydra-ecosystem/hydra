# SPDX-FileCopyrightText: Contributors to Hydra
# SPDX-License-Identifier: MIT
import sys
from dataclasses import dataclass
from enum import Enum
from types import TracebackType
from typing import Any, Optional

from omegaconf import MISSING

import hydra
from hydra.core.config_store import ConfigStore
from hydra.errors import InstantiationException
from hydra.utils import UNSAFE_DISABLE_EXECUTION_CHECKS, instantiate


class InstantiationCase(str, Enum):
    TARGET = "target"
    HOOK = "hook"
    DIRECT = "direct"
    INVALID = "invalid"
    NESTED = "nested"
    EMBEDDED = "embedded"
    EMBEDDED_INSTANTIATION = "embedded-instantiation"
    MISSING = "missing"


@dataclass
class AppConfig:
    case: InstantiationCase = MISSING


ConfigStore.instance().store(name="instantiate_exception", node=AppConfig)


class FailingTarget:
    def __init__(self) -> None:
        self._prepare()

    def _prepare(self) -> None:
        self._validate()

    def _validate(self) -> None:
        raise ValueError("target failed")


def fail() -> None:
    raise ValueError("direct call failed")


def fail_nested() -> None:
    instantiate(
        {"_target_": "my_app.FailingTarget"},
        _execution_whitelist_=UNSAFE_DISABLE_EXECUTION_CHECKS,
    )


def fail_with_embedded_cause() -> None:
    try:
        raise ValueError("root cause")
    except ValueError as cause:
        raise RuntimeError(f"request failed:\n{cause!r}") from cause


def fail_with_embedded_instantiation_cause() -> None:
    try:
        raise ValueError("root cause")
    except ValueError as cause:
        raise InstantiationException(f"request failed:\n{cause!r}") from cause


@hydra.main(config_path=None, config_name="instantiate_exception")
def my_app(cfg: AppConfig) -> Any:
    case = cfg.case
    if case is InstantiationCase.HOOK:

        def hook(
            error_type: type[BaseException],
            error: BaseException,
            tb: Optional[TracebackType],
        ) -> None:
            print(f"hook: {error_type.__name__}", file=sys.stderr)
            while tb is not None:
                print(f"frame: {tb.tb_frame.f_code.co_name}", file=sys.stderr)
                tb = tb.tb_next
            cause = error.__cause__
            if cause is not None:
                print(f"cause: {type(cause).__name__}: {cause}", file=sys.stderr)
                cause_tb = cause.__traceback__
                while cause_tb is not None:
                    print(
                        f"cause frame: {cause_tb.tb_frame.f_code.co_name}",
                        file=sys.stderr,
                    )
                    cause_tb = cause_tb.tb_next

        sys.excepthook = hook

    if case in {InstantiationCase.TARGET, InstantiationCase.HOOK}:
        return instantiate(
            {"_target_": "my_app.FailingTarget"},
            _execution_whitelist_=UNSAFE_DISABLE_EXECUTION_CHECKS,
        )
    if case is InstantiationCase.DIRECT:
        return fail()
    if case is InstantiationCase.INVALID:
        return instantiate({"_target_": 123})
    if case is InstantiationCase.NESTED:
        return instantiate(
            {"_target_": "my_app.fail_nested"},
            _execution_whitelist_=UNSAFE_DISABLE_EXECUTION_CHECKS,
        )
    if case is InstantiationCase.EMBEDDED:
        return instantiate(
            {"_target_": "my_app.fail_with_embedded_cause"},
            _execution_whitelist_=UNSAFE_DISABLE_EXECUTION_CHECKS,
        )
    if case is InstantiationCase.EMBEDDED_INSTANTIATION:
        return instantiate(
            {"_target_": "my_app.fail_with_embedded_instantiation_cause"},
            _execution_whitelist_=UNSAFE_DISABLE_EXECUTION_CHECKS,
        )
    assert case is InstantiationCase.MISSING
    return instantiate({"child": {"_target_": "__main__.missing"}})


if __name__ == "__main__":
    my_app()

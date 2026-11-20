# SPDX-FileCopyrightText: Contributors to Hydra
# SPDX-License-Identifier: MIT
from collections import ChainMap
from types import CodeType
from typing import Any, Callable, cast

# This optional dependency is installed by the launchers, not hydra-core.
import cloudpickle  # pyrefly: ignore[missing-import]


def _restore_code(
    constructor: Callable[..., CodeType], args: tuple[Any, ...], filename: str
) -> CodeType:
    return constructor(*args).replace(co_filename=filename)


def reduce_code(code: CodeType) -> tuple[Any, tuple[Any, ...]]:
    # Let cloudpickle handle Python-version-specific code fields, but retain
    # source locations for tracebacks instead of normalizing them for hashing.
    constructor, args = cast(
        tuple[Callable[..., CodeType], tuple[Any, ...]],
        cloudpickle.CloudPickler.dispatch_table[CodeType](code),
    )
    return _restore_code, (constructor, args, code.co_filename)


class SourcePickler(cloudpickle.CloudPickler):
    dispatch_table = ChainMap(
        {CodeType: reduce_code}, cloudpickle.CloudPickler.dispatch_table
    )

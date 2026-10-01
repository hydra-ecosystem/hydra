# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved

from functools import wraps
from typing import Callable, ParamSpec, TypeVar

P = ParamSpec("P")
R = TypeVar("R")

data: list[str] = []


def outer_decorator(arg1: str) -> Callable[[Callable[P, R]], Callable[P, R]]:
    def wrapper(func: Callable[P, R]) -> Callable[P, R]:
        @wraps(func)
        def inner_wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            data.append(arg1)
            return func(*args, **kwargs)

        return inner_wrapper

    return wrapper

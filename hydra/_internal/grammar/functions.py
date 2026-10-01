# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved
import inspect
from dataclasses import dataclass, field
from typing import Any, Callable

from omegaconf._utils import type_str

from hydra._internal.grammar.utils import is_type_matching
from hydra.core.override_parser.types import QuotedString
from hydra.errors import HydraException


@dataclass
class FunctionCall:
    name: str
    args: list[Any]
    kwargs: dict[str, Any]


@dataclass
class Functions:
    definitions: dict[str, inspect.Signature] = field(default_factory=dict)
    functions: dict[str, Callable[..., Any]] = field(default_factory=dict)

    def register(self, name: str, func: Callable[..., Any]) -> None:
        if name in self.definitions:
            raise HydraException(f"Function named '{name}' is already registered")

        self.definitions[name] = inspect.signature(func)
        self.functions[name] = func

    def eval(self, func: FunctionCall) -> Any:
        if func.name not in self.definitions:
            raise HydraException(
                f"Unknown function '{func.name}'"
                f"\nAvailable: {','.join(sorted(self.definitions.keys()))}\n"
            )
        sig = self.definitions[func.name]

        # unquote strings in args
        args = []
        for arg in func.args:
            if isinstance(arg, QuotedString):
                arg = arg.text
            args.append(arg)

        # Unquote strings in kwargs values
        kwargs = {}
        for key, val in func.kwargs.items():
            if isinstance(val, QuotedString):
                val = val.text
            kwargs[key] = val

        bound = sig.bind(*args, **kwargs)

        for idx, arg in enumerate(bound.arguments.items()):
            name = arg[0]
            value = arg[1]
            expected_type = sig.parameters[name].annotation
            if sig.parameters[name].kind == inspect.Parameter.VAR_POSITIONAL:
                for iidx, v in enumerate(value):
                    if not is_type_matching(v, expected_type):
                        raise TypeError(
                            f"mismatch type argument {name}[{iidx}]:"
                            f" {type_str(type(v))} is incompatible with {type_str(expected_type)}"
                        )

            else:
                if not is_type_matching(value, expected_type):
                    raise TypeError(
                        f"mismatch type argument {name}:"
                        f" {type_str(type(value))} is incompatible with {type_str(expected_type)}"
                    )

        return self.functions[func.name](*bound.args, **bound.kwargs)

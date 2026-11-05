# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved
import inspect
from dataclasses import dataclass, field, replace
from typing import Any, Callable

from omegaconf._utils import type_str

from hydra._internal.grammar.utils import is_type_matching
from hydra.core.override_parser.types import (
    ChoiceSweep,
    ListExtensionOverrideValue,
    Quote,
    QuotedString,
)
from hydra.errors import HydraException


@dataclass
class FunctionCall:
    name: str
    args: list[Any]
    kwargs: dict[str, Any]


@dataclass
class _ArgumentSpellings:
    """
    How the strings in the arguments of one function call were written.
    Each string in the result takes the spelling of the next argument string with
    the same text, in written order, and the last of them once none are left.
    A string that no argument had is single-quoted.
    """

    by_text: dict[str, list[str | QuotedString]] = field(default_factory=dict)

    def unwrap(self, value: Any) -> Any:
        """
        Returns value with each QuotedString replaced by its text, in list items,
        dict values and ChoiceSweep choices, and records how each string was written.
        """
        if isinstance(value, QuotedString):
            self.by_text.setdefault(value.text, []).append(value)
            return value.text
        if isinstance(value, str):
            self.by_text.setdefault(value, []).append(value)
            return value
        if isinstance(value, list):
            return [self.unwrap(item) for item in value]
        if isinstance(value, dict):
            return {key: self.unwrap(item) for key, item in value.items()}
        if isinstance(value, ChoiceSweep):
            return replace(value, list=self.unwrap(value.list))
        return value

    def rewrap(self, value: Any) -> Any:
        """
        Returns value with each string, in list items, dict values, ChoiceSweep
        choices and extend_list() values, replaced by its spelling.
        """
        if isinstance(value, str):
            spellings = self.by_text.get(value)
            if not spellings:
                return QuotedString(text=value, quote=Quote.single)
            return spellings.pop(0) if len(spellings) > 1 else spellings[0]
        if isinstance(value, list):
            return [self.rewrap(item) for item in value]
        if isinstance(value, dict):
            return {key: self.rewrap(item) for key, item in value.items()}
        if isinstance(value, ChoiceSweep):
            return replace(value, list=self.rewrap(value.list))
        if isinstance(value, ListExtensionOverrideValue):
            return ListExtensionOverrideValue(values=self.rewrap(value.values))
        return value


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
        """
        Calls the function with plain Python values: each QuotedString in the
        arguments is replaced by its text, at any depth. The strings in the result
        are returned as parsed elements, spelled as _ArgumentSpellings describes.
        """
        if func.name not in self.definitions:
            raise HydraException(
                f"Unknown function '{func.name}'"
                f"\nAvailable: {','.join(sorted(self.definitions.keys()))}\n"
            )
        sig = self.definitions[func.name]

        spellings = _ArgumentSpellings()
        args = [spellings.unwrap(arg) for arg in func.args]
        kwargs = {key: spellings.unwrap(val) for key, val in func.kwargs.items()}

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

        result = self.functions[func.name](*bound.args, **bound.kwargs)
        return spellings.rewrap(result)

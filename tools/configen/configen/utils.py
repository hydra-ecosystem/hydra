# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved
from enum import Enum
from typing import Any, Dict, Iterable, List, Optional

from omegaconf._utils import (
    _resolve_optional,
    get_dict_key_value_types,
    get_list_element_type,
    is_dict_annotation,
    is_list_annotation,
    is_primitive_type_annotation,
)


def is_tuple_annotation(type_: Any) -> bool:
    origin = getattr(type_, "__origin__", None)
    return origin is tuple


def convert_imports(imports: set[Any], string_imports: Iterable[str]) -> list[str]:
    tmp = set()
    for imp in string_imports:
        tmp.add(imp)
    for t in imports:
        s = None
        origin = getattr(t, "__origin__", None)
        if t is Any:
            classname = "Any"
        elif t is Optional:
            classname = "Optional"
        else:
            if origin is list:
                classname = "List"
            elif origin is tuple:
                classname = "Tuple"
            elif origin is dict:
                classname = "Dict"
            else:
                classname = t.__name__

        if not is_primitive_type_annotation(t) or issubclass(t, Enum):
            s = f"from {t.__module__} import {classname}"

        if s is not None:
            tmp.add(s)
    return sorted(list(tmp))


def collect_imports(imports: set[Any], type_: Any) -> None:
    if is_list_annotation(type_):
        collect_imports(imports, get_list_element_type(type_))
        type_ = List
    elif is_dict_annotation(type_):
        kvt = get_dict_key_value_types(type_)
        collect_imports(imports, kvt[0])
        collect_imports(imports, kvt[1])
        type_ = Dict
    else:
        is_optional = _resolve_optional(type_)[0]
        if is_optional and type_ is not Any:
            type_ = Optional
    imports.add(type_)

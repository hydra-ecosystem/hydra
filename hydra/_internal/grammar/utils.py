# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved
import inspect
import re
from types import UnionType
from typing import Any, Union, get_args, get_origin

from omegaconf._utils import is_dict_annotation, is_list_annotation

# All characters that must be escaped (must match the ESC grammar lexer token).
_ESC = "\\()[]{}:=, \t"

# Regular expression that matches any sequence of characters in `_ESC`.
_ESC_REGEX = re.compile(f"[{re.escape(_ESC)}]+")

# Regular expression that matches \ that must be escaped in a quoted string, i.e.,
# any number of \ followed by a quote.
_ESC_QUOTED_STR = {
    "'": re.compile(r"(\\)+'"),  # single quote
    '"': re.compile(r'(\\)+"'),  # double quote
}


def escape_special_characters(s: str) -> str:
    """Escape special characters in `s`"""
    matches = _ESC_REGEX.findall(s)
    if not matches:
        return s
    # Replace all special characters found in `s`. Performance should not be critical
    # so we do one pass per special character.
    all_special = set("".join(matches))
    # '\' is even more special: it needs to be replaced first, otherwise we will
    # mess up the other escaped characters.
    try:
        all_special.remove("\\")
    except KeyError:
        pass  # no '\' in the string
    else:
        s = s.replace("\\", "\\\\")
    for special_char in all_special:
        s = s.replace(special_char, f"\\{special_char}")
    return s


def is_type_matching(value: Any, type_: Any) -> bool:
    # Union
    if get_origin(type_) in (Union, UnionType):
        types = list(get_args(type_))
        for idx, t in enumerate(types):
            # for now treat any Dict[X,Y] as dict and any List[X] as list, ignoring element types
            if is_dict_annotation(t):
                t = dict
            elif is_list_annotation(t):
                t = list
            types[idx] = t
        return isinstance(value, tuple(types))
    else:
        primitives = (int, float, bool, str)
        if type_ in primitives:
            return type(value) is type_
        if type_ in (Any, inspect.Signature.empty):
            return True
        return isinstance(value, type_)

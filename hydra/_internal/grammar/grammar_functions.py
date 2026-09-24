# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved
import builtins
import decimal
import json
import random
from copy import copy
from typing import Any, Callable, Dict, List, Optional, Union

from hydra._internal.deprecation_warning import deprecation_warning
from hydra._internal.grammar.utils import is_type_matching
from hydra.core.override_parser.types import (
    ChoiceSweep,
    Glob,
    IntervalSweep,
    ListExtensionOverrideValue,
    ParsedElementType,
    QuotedString,
    RangeSweep,
    Sweep,
)

ElementType = Union[str, int, bool, float, List[Any], Dict[str, Any]]


def apply_to_dict_values(
    # val
    value: Dict[Any, Any],
    # func
    function: Callable[..., Any],
) -> Dict[Any, Any]:
    ret_dict: Dict[str, Any] = {}
    for key, value in value.items():
        ret_dict[key] = function(value)
    return ret_dict


def cast_choice(value: ChoiceSweep, function: Callable[..., Any]) -> ChoiceSweep:
    choices = []
    for item in value.list:
        choice = function(item)
        assert is_type_matching(choice, ElementType)
        choices.append(choice)
    return ChoiceSweep(
        simple_form=value.simple_form,
        list=choices,
        tags=copy(value.tags),
        shuffle=value.shuffle,
    )


def cast_interval(value: IntervalSweep, function: Callable[..., Any]) -> IntervalSweep:
    return IntervalSweep(
        start=function(value.start), end=function(value.end), tags=copy(value.tags)
    )


def cast_range(value: RangeSweep, function: Callable[..., Any]) -> RangeSweep:
    if function not in (cast_float, cast_int):
        raise ValueError("Range can only be cast to int or float")
    return RangeSweep(
        start=function(value.start),
        stop=function(value.stop),
        step=function(value.step),
        tags=copy(value.tags),
        shuffle=value.shuffle,
    )


CastType = Union[ParsedElementType, Sweep]


def _list_to_simple_choice(*args: Any) -> ChoiceSweep:
    choices: List[ParsedElementType] = []
    for arg in args:
        assert is_type_matching(arg, ParsedElementType)
        choices.append(arg)
    return ChoiceSweep(list=builtins.list(choices), simple_form=True)


def _normalize_cast_value(*args: CastType, value: Optional[CastType]) -> CastType:
    if len(args) > 0 and value is not None:
        raise TypeError("cannot use both position and named arguments")
    if value is not None:
        return value
    if len(args) == 0:
        raise TypeError("No positional args or value specified")
    if len(args) == 1:
        return args[0]
    if len(args) > 1:
        return _list_to_simple_choice(*args)
    assert False


def cast_int(*args: CastType, value: Optional[CastType] = None) -> Any:
    value = _normalize_cast_value(*args, value=value)
    if isinstance(value, QuotedString):
        return cast_int(value.text)
    if isinstance(value, dict):
        return apply_to_dict_values(value, cast_int)
    if isinstance(value, list):
        return list(map(cast_int, value))
    elif isinstance(value, ChoiceSweep):
        return cast_choice(value, cast_int)
    elif isinstance(value, RangeSweep):
        return cast_range(value, cast_int)
    elif isinstance(value, IntervalSweep):
        return cast_interval(value, cast_int)
    assert isinstance(value, (int, float, bool, str))
    return int(value)


def cast_float(*args: CastType, value: Optional[CastType] = None) -> Any:
    value = _normalize_cast_value(*args, value=value)
    if isinstance(value, QuotedString):
        return cast_float(value.text)
    if isinstance(value, dict):
        return apply_to_dict_values(value, cast_float)
    if isinstance(value, list):
        return list(map(cast_float, value))
    elif isinstance(value, ChoiceSweep):
        return cast_choice(value, cast_float)
    elif isinstance(value, RangeSweep):
        return cast_range(value, cast_float)
    elif isinstance(value, IntervalSweep):
        return cast_interval(value, cast_float)
    assert isinstance(value, (int, float, bool, str))
    return float(value)


def cast_str(*args: CastType, value: Optional[CastType] = None) -> Any:
    value = _normalize_cast_value(*args, value=value)
    if isinstance(value, QuotedString):
        return cast_str(value.text)
    if isinstance(value, dict):
        return apply_to_dict_values(value, cast_str)
    if isinstance(value, list):
        return list(map(cast_str, value))
    elif isinstance(value, ChoiceSweep):
        return cast_choice(value, cast_str)
    elif isinstance(value, RangeSweep):
        return cast_range(value, cast_str)
    elif isinstance(value, IntervalSweep):
        raise ValueError("Intervals cannot be cast to str")

    assert isinstance(value, (int, float, bool, str))
    if isinstance(value, bool):
        return str(value).lower()
    else:
        return str(value)


def extract_text(*args: Any, value: Optional[Any] = None) -> Any:
    value = _normalize_cast_value(*args, value=value)
    if isinstance(value, QuotedString):
        return value.text
    if isinstance(value, dict):
        return apply_to_dict_values(value, extract_text)
    elif isinstance(value, list):
        return list(map(extract_text, value))
    elif isinstance(value, ChoiceSweep):
        return cast_choice(value, extract_text)
    elif isinstance(value, RangeSweep):
        return cast_range(value, extract_text)
    else:
        return value


def cast_json_str(*args: Any, value: Optional[Any] = None) -> Any:
    deprecation_warning(
        "json_str(...) is deprecated and will be removed in Hydra 1.5. "
        "See https://github.com/hydra-ecosystem/hydra/pull/2930#issuecomment-5018616929",
        stacklevel=2,
    )
    value = _normalize_cast_value(*args, value=value)
    json_val = value
    if isinstance(value, QuotedString):
        json_val = value.text
    if isinstance(value, dict):
        json_val = apply_to_dict_values(value, extract_text)
    elif isinstance(value, list):
        json_val = list(map(extract_text, value))
    elif isinstance(value, ChoiceSweep):
        json_choices = cast_choice(value, extract_text)
        return cast_choice(json_choices, json.dumps)
    elif isinstance(value, RangeSweep):
        json_range = cast_range(value, extract_text)
        return cast_range(json_range, json.dumps)
    elif isinstance(value, IntervalSweep):
        raise ValueError("Intervals cannot be cast to json_str")

    return json.dumps(json_val)


def cast_bool(*args: CastType, value: Optional[CastType] = None) -> Any:
    value = _normalize_cast_value(*args, value=value)
    if isinstance(value, QuotedString):
        return cast_bool(value.text)
    if isinstance(value, dict):
        return apply_to_dict_values(value, cast_bool)
    if isinstance(value, list):
        return list(map(cast_bool, value))
    elif isinstance(value, ChoiceSweep):
        return cast_choice(value, cast_bool)
    elif isinstance(value, RangeSweep):
        return cast_range(value, cast_bool)
    elif isinstance(value, IntervalSweep):
        raise ValueError("Intervals cannot be cast to bool")

    if isinstance(value, str):
        if value.lower() == "false":
            return False
        elif value.lower() == "true":
            return True
        else:
            raise ValueError(f"Cannot cast '{value}' to bool")
    return bool(value)


def choice(
    *args: Union[str, int, float, bool, Dict[Any, Any], List[Any], ChoiceSweep],
) -> ChoiceSweep:
    """
    A choice sweep over the specified values
    """
    if len(args) == 0:
        raise ValueError("empty choice is not legal")
    if len(args) == 1:
        first = args[0]
        if isinstance(first, ChoiceSweep):
            if first.simple_form:
                first.simple_form = False
                return first
            else:
                raise ValueError("nesting choices is not supported")

    return ChoiceSweep(list=list(args))  # type: ignore


def range(
    start: Union[int, float],
    stop: Optional[Union[int, float]] = None,
    step: Union[int, float] = 1,
) -> RangeSweep:
    """
    Range defines a sweep over a range of integer or floating-point values.
    When only start is defined, it is set as the stop value, and start is set at
    zero.
    For a positive step, the contents of a range r are determined by the formula
     r[i] = start + step*i where i >= 0 and r[i] < stop.
    For a negative step, the contents of the range are still determined by the formula
     r[i] = start + step*i, but the constraints are i >= 0 and r[i] > stop.
    """
    if stop is None:
        stop = start
        start = 0
    return RangeSweep(start=start, stop=stop, step=step)


def interval(start: Union[int, float], end: Union[int, float]) -> IntervalSweep:
    """
    A continuous interval between two floating point values.
    value=interval(x,y) is interpreted as x <= value < y
    """
    return IntervalSweep(start=float(start), end=float(end))


def tag(*args: Union[str, Union[Sweep]], sweep: Optional[Sweep] = None) -> Sweep:
    """
    Tags the sweep with a list of string tags.
    """
    if len(args) < 1:
        raise ValueError("Not enough arguments to tag, must take at least a sweep")

    if sweep is not None:
        return tag(*(list(args) + [sweep]))

    last = args[-1]
    if isinstance(last, Sweep):
        sweep = last
        tags = set()
        for tag_ in args[0:-1]:
            if not isinstance(tag_, str):
                raise ValueError(
                    f"tag arguments type must be string, got {type(tag_).__name__}"
                )
            tags.add(tag_)
        sweep.tags = tags
        return sweep
    else:
        raise ValueError(
            f"Last argument to tag() must be a choice(), range() or interval(), got {type(sweep).__name__}"
        )


def shuffle(
    *args: Union[ElementType, ChoiceSweep, RangeSweep],
    sweep: Optional[Union[ChoiceSweep, RangeSweep]] = None,
    list: Optional[List[Any]] = None,
) -> Union[List[Any], ChoiceSweep, RangeSweep]:
    """
    Shuffle input list or sweep (does not support interval)
    """
    if list is not None:
        return shuffle(list)
    if sweep is not None:
        return shuffle(sweep)

    if len(args) == 1:
        arg = args[0]
        if isinstance(arg, (ChoiceSweep, RangeSweep)):
            sweep = copy(arg)
            sweep.shuffle = True
            return sweep
        if isinstance(arg, builtins.list):
            lst = copy(arg)
            random.shuffle(lst)
            return lst
        else:
            return [arg]
    else:
        simple_choice = _list_to_simple_choice(*args)
        simple_choice.shuffle = True
        return simple_choice


def sort(
    *args: Union[ElementType, ChoiceSweep, RangeSweep],
    sweep: Optional[Union[ChoiceSweep, RangeSweep]] = None,
    list: Optional[List[Any]] = None,
    reverse: bool = False,
) -> Any:
    """
    Sort an input list or sweep.
    reverse=True reverses the order
    """

    if list is not None:
        return sort(list, reverse=reverse)
    if sweep is not None:
        return _sort_sweep(sweep, reverse)

    if len(args) == 1:
        arg = args[0]
        if isinstance(arg, (ChoiceSweep, RangeSweep)):
            # choice: sort(choice(a,b,c))
            # range: sort(range(1,10))
            return _sort_sweep(arg, reverse)
        elif isinstance(arg, builtins.list):
            return sorted(arg, reverse=reverse)
        elif is_type_matching(arg, ParsedElementType):
            return arg
        else:
            raise TypeError(f"Invalid arguments: {args}")
    else:
        primitives = (int, float, bool, str)
        for arg in args:
            if not isinstance(arg, primitives):
                raise TypeError(f"Invalid arguments: {args}")
        if len(args) == 0:
            raise ValueError("empty sort input")
        elif len(args) > 1:
            cw = _list_to_simple_choice(*args)
            return _sort_sweep(cw, reverse)


def _sort_sweep(
    sweep: Union[ChoiceSweep, RangeSweep], reverse: bool
) -> Union[ChoiceSweep, RangeSweep]:
    sweep = copy(sweep)

    if isinstance(sweep, ChoiceSweep):
        # sorted will raise an error if types cannot be compared
        sweep.list = sorted(sweep.list, reverse=reverse)  # type: ignore
        return sweep
    elif isinstance(sweep, RangeSweep):
        assert sweep.start is not None
        assert sweep.stop is not None
        if (sweep.step > 0) == reverse:
            _reverse_range_sweep(sweep)
        return sweep
    else:
        assert False


def _reverse_range_sweep(sweep: RangeSweep) -> None:
    r = sweep.range()
    if isinstance(r, builtins.range):
        count = len(r)
        if count > 1:
            first = r[0]
            last = r[-1]
            sweep.start = last
            sweep.step = -sweep.step
            sweep.stop = first + sweep.step
    else:
        start = decimal.Decimal(str(sweep.start))
        stop = decimal.Decimal(str(sweep.stop))
        step = decimal.Decimal(str(sweep.step))
        count = _float_range_count(start=start, stop=stop, step=step)
        if count > 1:
            first = start
            last = start + (count - 1) * step
            sweep.start = last
            sweep.step = -step
            sweep.stop = first + sweep.step / 2


def _float_range_count(
    start: decimal.Decimal, stop: decimal.Decimal, step: decimal.Decimal
) -> int:
    if step == 0:
        return 0
    if step > 0:
        if start >= stop:
            return 0
        distance = stop - start
    else:
        if start <= stop:
            return 0
        distance = start - stop
    step = abs(step)
    quotient, remainder = divmod(distance, step)
    count = int(quotient)
    if remainder != 0:
        count += 1
    return count


def glob(
    include: Union[List[str], str], exclude: Optional[Union[List[str], str]] = None
) -> Glob:
    """
    A glob selects from all options in the config group.
    inputs are in glob format. e.g: *, foo*, *foo.
    :param include: a string or a list of strings to use as include globs
    :param exclude: a string or a list of strings to use as exclude globs
    """

    if isinstance(include, str):
        include = [include]
    if exclude is None:
        exclude = []
    elif isinstance(exclude, str):
        exclude = [exclude]

    return Glob(include=include, exclude=exclude)


def extend_list(*args: Any) -> ListExtensionOverrideValue:
    """
    Deprecated in Hydra 1.4 and scheduled for removal in Hydra 1.5.
    See https://github.com/hydra-ecosystem/hydra/issues/3200.
    """
    return ListExtensionOverrideValue(values=list(args))

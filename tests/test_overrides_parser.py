# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved
import builtins
import math
import re
from contextlib import nullcontext
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Union

try:
    from _pytest.raises import RaisesExc as RaisesContext
except ImportError:
    from _pytest.python_api import RaisesContext  # type: ignore[attr-defined,no-redef]
from pytest import mark, param, raises, warns

from hydra._internal.grammar import grammar_functions
from hydra._internal.grammar.functions import Functions
from hydra._internal.grammar.utils import escape_special_characters
from hydra.core.override_parser.overrides_parser import (
    OverridesParser,
    create_functions,
)
from hydra.core.override_parser.types import (
    ChoiceSweep,
    FloatRange,
    Glob,
    IntervalSweep,
    Key,
    ListExtensionOverrideValue,
    Override,
    OverrideType,
    Quote,
    QuotedString,
    RangeSweep,
    Sweep,
    Transformer,
    ValueType,
)
from hydra.errors import HydraException

UNQUOTED_SPECIAL = r"/-\+.$%*@?|"  # special characters allowed in unquoted strings

parser = OverridesParser(create_functions())

JSON_STR_DEPRECATION_WARNING = (
    "json_str(...) is deprecated and will be removed in Hydra 1.5. "
    "See https://github.com/hydra-ecosystem/hydra/pull/2930#issuecomment-5018616929"
)

EXTEND_LIST_DEPRECATION_WARNING = (
    "extend_list(...) is deprecated and will be removed in Hydra 1.5. "
    "See https://github.com/hydra-ecosystem/hydra/issues/3200"
)


def parse_rule(value: str, rule_name: str) -> Any:
    return parser.parse_rule(value, rule_name)


def eq(item1: Any, item2: Any) -> bool:
    if isinstance(item1, float) and isinstance(item2, float):
        return item1 == item2 or math.isnan(item1) and math.isnan(item2)
    else:
        return item1 == item2  # type: ignore


@mark.parametrize(
    "value,expected",
    [
        param("abc", "abc", id="value:id"),
        param("abc123", "abc123", id="value:idint"),
        param("abc-123", "abc-123", id="value:id-int"),
        param("a b c\t-\t1 2 3", "a b c\t-\t1 2 3", id="value:str-ws-in"),
        param(" abc-123 ", "abc-123", id="value:str-ws-out"),
        param("123abc", "123abc", id="value:str-int-id"),
        param(r"a\,b", "a,b", id="value:str-esc-comma"),
        param(r"a\:b", "a:b", id="value:str-esc-colon"),
        param(r"a\=b", "a=b", id="value:str-esc-equal"),
        param(r"\ ab", " ab", id="value:str-esc-space"),
        param("ab\\\t", "ab\t", id="value:str-esc-tab"),
        param("ab\\\\", "ab\\", id="value:str-esc-backslash"),
        param(r"\,", ",", id="value:str-esc-comma-alone"),
        param(r"f\(a\, b\)", "f(a, b)", id="value:str-esc-parentheses"),
        param(r"\[a\, b\]", "[a, b]", id="value:str-esc-brackets"),
        param(r"\{a\: b\}", "{a: b}", id="value:str-esc-braces"),
        param(r"$\{foo.bar\}", "${foo.bar}", id="value:str-esc-braces"),
        param("xyz_${a.b.c}", "xyz_${a.b.c}", id="value:str_interpolation"),
        param("${f:USER,root}", "${f:USER,root}", id="value:custom_interpolation"),
        param("${f.g:USER,root}", "${f.g:USER,root}", id="value:custom_interpolation"),
        param("c:\\foo\\a-b.txt", "c:\\foo\\a-b.txt", id="value:windows_path"),
        # null
        param("null", None, id="value:null"),
        # int
        param("1", 1, id="value:int:pos"),
        param("+1", 1, id="value:int:explicit_pos"),
        param("1___0___", "1___0___", id="value:int:not_an_int"),
        # float
        param("0.51", 0.51, id="value:float:positive"),
        param("10e0", 10.0, id="value:float:exp"),
        param("+inf", math.inf, id="value:float:plus_inf"),
        # bool
        param("true", True, id="value:bool"),
        param(".", ".", id="value:dot"),
    ],
)
def test_element(value: str, expected: Any) -> None:
    ret = parse_rule(value, "element")
    assert eq(ret, expected)


@mark.parametrize(
    "value,expected",
    [
        param("abc", "abc", id="value:simple"),
        param("abc ", "abc", id="value:simple_ws"),
        param(" abc", "abc", id="ws_value:simple"),
        param("[1,2,3]", [1, 2, 3], id="value:list"),
        param("[1 ]", [1], id="value:list1_ws"),
        param("[1, 2, 3]", [1, 2, 3], id="value:list_ws"),
        param("1,2,3", ChoiceSweep(list=[1, 2, 3], simple_form=True), id="sweep:int"),
        param(
            "1, 2, 3", ChoiceSweep(list=[1, 2, 3], simple_form=True), id="sweep:int_ws"
        ),
        param(
            "${a}, ${b}, ${c}",
            ChoiceSweep(list=["${a}", "${b}", "${c}"], simple_form=True),
            id="sweep:interpolations",
        ),
        param(
            "[a,b],[c,d]",
            ChoiceSweep(list=[["a", "b"], ["c", "d"]], simple_form=True),
            id="sweep:lists",
        ),
        # bool
        param("true", True, id="value:bool"),
        param("True", True, id="value:bool"),
        param("TRUE", True, id="value:bool"),
        param("trUe", True, id="value:bool"),
        param("false", False, id="value:bool"),
        param("False", False, id="value:bool"),
        param("FALSE", False, id="value:bool"),
        param("faLse", False, id="value:bool"),
        # casts
        param("int(10.0)", 10, id="int(10.0)"),
        param("str(10.0)", "10.0", id="str(10.0)"),
        param("bool(10.0)", True, id="bool(10.0)"),
        param("float(10)", 10.0, id="float(10)"),
        param("float(float(10))", 10.0, id="float(float(10))"),
        # ordering
        param("sort([2,3,1])", [1, 2, 3], id="sort([2,3,1])"),
        param("sort([2,3,1],reverse=true)", [3, 2, 1], id="sort([2,3,1],reverse=true)"),
        param(
            "sort(3,2,1)",
            ChoiceSweep(simple_form=True, list=[1, 2, 3], tags=set()),
            id="sort(3,2,1)",
        ),
        param(
            "sort(a,c,b,reverse=true)",
            ChoiceSweep(simple_form=True, list=["c", "b", "a"], tags=set()),
            id="sort(a,c,b,reverse=true)",
        ),
        param(
            "float(sort(3,2,1))",
            ChoiceSweep(simple_form=True, list=[1.0, 2.0, 3.0], tags=set()),
            id="float(sort(3,2,1))",
        ),
        param(
            "sort(float(3,2,1))",
            ChoiceSweep(simple_form=True, list=[1.0, 2.0, 3.0], tags=set()),
            id="sort(float(3,2,1))",
        ),
        param(
            "sort(3,2,str(1))",
            raises(
                HydraException,
                match=re.escape(
                    "TypeError while evaluating 'sort(3,2,str(1))':"
                    " '<' not supported between instances of 'str' and 'int'"
                ),
            ),
            id="sort(3,2,str(1))",
        ),
        param(
            "shuffle(1,2,3)",
            ChoiceSweep(list=[1, 2, 3], shuffle=True, simple_form=True),
            id="shuffle(1,2,3)",
        ),
        param(
            "shuffle(choice(1,2,3))",
            ChoiceSweep(list=[1, 2, 3], shuffle=True),
            id="shuffle(choice(1,2,3))",
        ),
        param(
            "extend_list(1,2,three)",
            ListExtensionOverrideValue(values=[1, 2, "three"]),
            id="extend_list(1,2,three)",
        ),
        param(
            "extend_list('5')",
            ListExtensionOverrideValue(values=["5"]),
            id="extend_list('5')",
        ),
        param(
            "extend_list([1,2,3], {a:1, b:2})",
            ListExtensionOverrideValue(values=[[1, 2, 3], {"a": 1, "b": 2}]),
            id="extend_list([1,2,3], {a:1, b:2})",
        ),
    ],
)
def test_value(value: str, expected: Any) -> None:
    if isinstance(expected, RaisesContext):
        with expected:
            parse_rule(value, "value")
    else:
        ret = parse_rule(value, "value")
        assert ret == expected


@mark.parametrize(
    "value,expected",
    [
        param("[]", [], id="list:empty"),
        param("[1]", [1], id="list:item"),
        param(
            "['a b']",
            [QuotedString(text="a b", quote=Quote.single)],
            id="list:quoted_item",
        ),
        param(
            "['[a,b]']",
            [QuotedString(text="[a,b]", quote=Quote.single)],
            id="list:quoted_item",
        ),
        param("[[a]]", [["a"]], id="list:nested_list"),
        param("[[[a]]]", [[["a"]]], id="list:double_nested_list"),
        param("[1,[a]]", [1, ["a"]], id="list:simple_and_list_elements"),
        param(
            r"['a\\', 'b\\']",
            [
                QuotedString(text="a\\", quote=Quote.single),
                QuotedString(text="b\\", quote=Quote.single),
            ],
            id="list:str_trailing_backslash_single",
        ),
        param(
            r'["a\\", "b\\"]',
            [
                QuotedString(text="a\\", quote=Quote.double),
                QuotedString(text="b\\", quote=Quote.double),
            ],
            id="list:str_trailing_backslash_double",
        ),
    ],
)
def test_list_container(value: str, expected: Any) -> None:
    ret = parse_rule(value, "listContainer")
    assert ret == expected


@mark.parametrize(
    "value,expected",
    [
        # list
        param("x=shuffle([1,2,3])", [1, 2, 3], id="shuffle:list"),
        param("x=shuffle(list=[1,2,3])", [1, 2, 3], id="shuffle:list"),
        # choice
        param(
            "x=shuffle(1,2,3)",
            ChoiceSweep(list=[1, 2, 3], simple_form=True, shuffle=True),
            id="x=shuffle:choice:simple",
        ),
        param(
            "x=shuffle(choice(1,2,3))",
            ChoiceSweep(list=[1, 2, 3], shuffle=True),
            id="shuffle:choice",
        ),
        # range
        param(
            "x=shuffle(range(1,10))",
            ChoiceSweep(list=[1, 2, 3, 4, 5, 6, 7, 8, 9], shuffle=True),
            id="shuffle:range",
        ),
    ],
)
def test_shuffle_sequence(value: str, expected: Any) -> None:
    ret = parser.parse_override(value)
    if isinstance(expected, Sweep):
        actual = list(ret.sweep_string_iterator())
        if isinstance(expected, ChoiceSweep):
            expected_str_list = list(map(str, expected.list))
        elif isinstance(expected, RangeSweep):
            expected_str_list = list(map(str, expected.range()))
        else:
            assert False

        assert sorted(expected_str_list) == sorted(actual)

        for i in range(1, 10):
            actual = list(ret.sweep_string_iterator())
            if actual != expected_str_list:
                return
        assert False
    else:
        val = ret.value()
        assert isinstance(val, list)
        assert sorted(val) == expected

        for i in range(1, 10):
            ret1 = parser.parse_override(value).value()
            if ret1 != expected:
                return
        assert False


@mark.parametrize(
    "value,expected",
    [
        param("{}", {}, id="dict"),
        param("{a:b}", {"a": "b"}, id="dict"),
        param("{a:10}", {"a": 10}, id="dict"),
        param("{a:[a,10]}", {"a": ["a", 10]}, id="dict"),
        param("{a:[true,10]}", {"a": [True, 10]}, id="dict"),
        param("{a:10,b:20}", {"a": 10, "b": 20}, id="dict"),
        param("{a:10,b:{}}", {"a": 10, "b": {}}, id="dict"),
        param("{a:10,b:{c:[1,2]}}", {"a": 10, "b": {"c": [1, 2]}}, id="dict"),
        param("{null: 1}", {None: 1}, id="dict_null_key"),
        param("{123: 1, 0: 2, -1: 3}", {123: 1, 0: 2, -1: 3}, id="dict_int_key"),
        param("{3.14: 0, 1e3: 1}", {3.14: 0, 1000.0: 1}, id="dict_float_key"),
        param("{true: 1, fAlSe: 0}", {True: 1, False: 0}, id="dict_bool_key"),
        param(
            "{%s: 1}" % UNQUOTED_SPECIAL,
            {UNQUOTED_SPECIAL: 1},
            id="dict_unquoted_char_key",
        ),
        param(
            "{\\\\\\(\\)\\[\\]\\{\\}\\:\\=\\ \\\t\\,: 1}",
            {"\\()[]{}:= \t,": 1},
            id="dict_esc_key",
        ),
        param("{white spaces: 1}", {"white spaces": 1}, id="dict_ws_key"),
        param(
            "{a_b: 1, ab 123.5 True: 2, null false: 3, 1: 4, null: 5}",
            {
                "a_b": 1,
                "ab 123.5 True": 2,
                "null false": 3,
                1: 4,
                None: 5,
            },
            id="dict_mixed_keys",
        ),
        param(
            r"{a: 'a\\', b: 'b\\'}",
            {
                "a": QuotedString(text="a\\", quote=Quote.single),
                "b": QuotedString(text="b\\", quote=Quote.single),
            },
            id="dict_str_trailing_backslash_single",
        ),
        param(
            r'{a: "a\\", b: "b\\"}',
            {
                "a": QuotedString(text="a\\", quote=Quote.double),
                "b": QuotedString(text="b\\", quote=Quote.double),
            },
            id="dict_str_trailing_backslash_double",
        ),
    ],
)
def test_dict_container(value: str, expected: Any) -> None:
    ret = parse_rule(value, "dictContainer")
    assert ret == expected


@mark.parametrize(
    "value,expected",
    [
        param("choice(a)", ChoiceSweep(list=["a"]), id="sweep:choice(a)"),
        param("choice(a,b)", ChoiceSweep(list=["a", "b"]), id="sweep:choice(a,b)"),
        param("choice (a,b)", ChoiceSweep(list=["a", "b"]), id="sweep:choice (a,b)"),
        param(
            "choice( 10 , 20 )",
            ChoiceSweep(list=[10, 20]),
            id="sweep:choice( 10 , 20 )",
        ),
        param("choice(str(10))", ChoiceSweep(list=["10"]), id="choice(str(10))"),
    ],
)
def test_choice_sweep(value: str, expected: Any) -> None:
    ret = parse_rule(value, "function")
    assert ret == expected


@mark.parametrize(
    "value,expected",
    [
        param("a,b", ChoiceSweep(list=["a", "b"], simple_form=True), id="a,b"),
        param(
            "a,10,3.14",
            ChoiceSweep(list=["a", 10, 3.14], simple_form=True),
            id="a,10,3.14",
        ),
        param("a , b", ChoiceSweep(list=["a", "b"], simple_form=True), id="a , b"),
        param(
            "${a},${b}",
            ChoiceSweep(list=["${a}", "${b}"], simple_form=True),
            id="${a},${a}",
        ),
    ],
)
def test_simple_choice_sweep(value: str, expected: Any) -> None:
    ret = parse_rule(value, "simpleChoiceSweep")
    assert ret == expected


@mark.parametrize(
    "value,expected",
    [
        param("range(10,11)", RangeSweep(start=10, stop=11, step=1), id="ints"),
        param("range (10,11)", RangeSweep(start=10, stop=11, step=1), id="ints"),
        param(
            "range(1,10,2)", RangeSweep(start=1, stop=10, step=2), id="ints_with_step"
        ),
        param(
            "range(start=1,stop=10,step=2)",
            RangeSweep(start=1, stop=10, step=2),
            id="ints_with_step",
        ),
        param(
            "range(1.0, 3.14)", RangeSweep(start=1.0, stop=3.14, step=1), id="floats"
        ),
        param(
            "range(1.0, 3.14, 0.1)",
            RangeSweep(start=1.0, stop=3.14, step=0.1),
            id="floats_with_step",
        ),
        param("range(10)", RangeSweep(start=0, stop=10, step=1), id="no_start"),
        param("range(-10)", RangeSweep(start=0, stop=-10, step=1), id="no_start_empty"),
        param(
            "range(-10, step=-1)",
            RangeSweep(start=0, stop=-10, step=-1),
            id="no_start_negative",
        ),
        param("range(5.5)", RangeSweep(start=0, stop=5.5, step=1), id="no_start_float"),
        param(
            "range(5.5, step=0.5)",
            RangeSweep(start=0, stop=5.5, step=0.5),
            id="no_start_step_float",
        ),
    ],
)
def test_range_sweep(value: str, expected: Any) -> None:
    ret = parse_rule(value, "function")
    assert ret == expected


@mark.parametrize(
    "value,expected",
    [
        param(
            "interval(10,11)", IntervalSweep(start=10.0, end=11.0), id="interval(10,11)"
        ),
        param(
            "interval(2.72,3.14)", IntervalSweep(start=2.72, end=3.14), id="interval"
        ),
        param(
            "interval(start=2.72,end=3.14)",
            IntervalSweep(start=2.72, end=3.14),
            id="interval:named",
        ),
    ],
)
def test_interval_sweep(value: str, expected: Any) -> None:
    ret: IntervalSweep = parse_rule(value, "function")
    assert type(ret.start) is float
    assert type(ret.end) is float
    assert ret == expected


@mark.parametrize(
    "rule,value,expected",
    [
        # errors
        param(
            "primitive",
            " ",
            raises(
                HydraException,
                match=re.escape("Trying to parse a primitive that is all whitespaces"),
            ),
            id="error:value:whitespace",
        ),
        param(
            "value",
            "[",
            raises(
                HydraException, match=re.escape("no viable alternative at input '['")
            ),
            id="error:partial_list",
        ),
        param(
            "override",
            "key=[]aa",
            raises(
                HydraException, match=re.escape("extraneous input 'aa' expecting <EOF>")
            ),
            id="error:left_overs",
        ),
        param(
            "listContainer",
            r"['a\', 'b']",
            raises(HydraException, match=re.escape("token recognition error at: '']'")),
            id="error:list_bad_escaping",
        ),
        param(
            "override",
            "key=[1,2,3]'",
            raises(HydraException, match=re.escape("token recognition error at: '''")),
            id="error:left_overs",
        ),
        param(
            "dictContainer",
            "{'0a': 0, \"1b\": 1}",
            raises(HydraException, match=re.escape("mismatched input ''0a''")),
            id="error:dict_quoted_key_dictContainer",
        ),
        param(
            "dictContainer",
            r"{a: 'a\', b: 'b'}",
            raises(HydraException, match=re.escape("token recognition error at: ''}'")),
            id="error:dict_bad_escaping",
        ),
        param(
            "override",
            "key={' abc ': 0}",
            raises(
                HydraException,
                match=re.escape("no viable alternative at input '{' abc ''"),
            ),
            id="error:dict_quoted_key_override_single",
        ),
        param(
            "override",
            'key={" abc ": 0}',
            raises(
                HydraException,
                match=re.escape("""no viable alternative at input '{" abc "'"""),
            ),
            id="error:dict_quoted_key_override_double",
        ),
        param(
            "override",
            "$foo/bar=foobar",
            raises(HydraException, match=re.escape("mismatched input '/'")),
            id="error:dollar_in_group",
        ),
        param(
            "override",
            "+key=extend_list(foobar)",
            raises(
                HydraException,
                match=re.escape("Trying to use override symbols when extending a list"),
            ),
            id="error:plus_in_extend_list_key",
        ),
    ],
)
def test_parse_errors(rule: str, value: str, expected: Any) -> None:
    with expected:
        parse_rule(value, rule)


@mark.parametrize(
    "value,expected",
    [
        param("abc", "abc", id="package"),
        param("abc.cde", "abc.cde", id="package"),
        param("$foo", "$foo", id="package_dollar"),
        param("$foo.bar$.x$z", "$foo.bar$.x$z", id="package_dollar_dotpath"),
        param("ab-c", "ab-c", id="package"),
    ],
)
def test_package(value: str, expected: Any) -> None:
    ret = parse_rule(value, "package")
    assert ret == expected


@mark.parametrize(
    "value,expected",
    [
        param("abc", "abc", id="package"),
        param("abc.cde", "abc.cde", id="package"),
        param("$foo", "$foo", id="package_dollar"),
        param("$foo.bar$.x$z", "$foo.bar$.x$z", id="package_dollar_dotpath"),
        param("a/b/c", "a/b/c", id="group"),
        param("a-b/c", "a-b/c", id="group_with_dash"),
        param("a-b", "a-b", id="package_with_dash"),
    ],
)
def test_package_or_group(value: str, expected: Any) -> None:
    ret = parse_rule(value, "packageOrGroup")
    assert ret == expected


@mark.parametrize(
    "value,expected",
    [
        param("abc", Key(key_or_group="abc"), id="abc"),
        param("abc/cde", Key(key_or_group="abc/cde"), id="abc/cde"),
        param("abc.cde", Key(key_or_group="abc.cde"), id="abc.cde"),
        param("ab-c/d-ef", Key(key_or_group="ab-c/d-ef"), id="ab-c/d-ef"),
        param("ab-c.d-ef", Key(key_or_group="ab-c.d-ef"), id="ab-c.d-ef"),
        param("$foo", Key(key_or_group="$foo"), id="dollar"),
        param("$foo.bar$.x$z", Key(key_or_group="$foo.bar$.x$z"), id="dollar_dotpath"),
        param("list.0", Key(key_or_group="list.0"), id="list.0"),
        param(
            "package_or_group@pkg1",
            Key(key_or_group="package_or_group", package="pkg1"),
            id="package_or_group@pkg1",
        ),
        param(
            "package_or_group@",
            Key(key_or_group="package_or_group", package=""),
            id="package_or_group@",
        ),
        param(
            "package_or_group@$pkg1",
            Key(key_or_group="package_or_group", package="$pkg1"),
            id="package_dollar",
        ),
    ],
)
def test_key(value: str, expected: Any) -> None:
    ret = parse_rule(value, "key")
    assert ret == expected


@mark.parametrize(
    "value,expected",
    [
        param("a", "a", id="a"),
        param(UNQUOTED_SPECIAL, UNQUOTED_SPECIAL, id="accepted_specials"),
        param("abc10", "abc10", id="abc10"),
        param("a.b.c", "a.b.c", id="a.b.c"),
        param("list.0.bar", "list.0.bar", id="list.0.bar"),
        param("0.foo", "0.foo", id="0.foo"),
        param("10", 10, id="10"),
        param("10abc", "10abc", id="10abc"),
        param("abc-cde", "abc-cde", id="abc-cde"),
        param("true", True, id="primitive:bool"),
        param("True", True, id="primitive:bool"),
        param("TRUE", True, id="primitive:bool"),
        param("trUe", True, id="primitive:bool"),
        param("false", False, id="primitive:bool"),
        param("False", False, id="primitive:bool"),
        param("FALSE", False, id="primitive:bool"),
        param("faLse", False, id="primitive:bool"),
        param("abc", "abc", id="primitive:id"),
        param("abc123", "abc123", id="primitive:idint"),
        param("abc-123", "abc-123", id="primitive:id-int"),
        param("xyz_${a.b.c}", "xyz_${a.b.c}", id="primitive:str_interpolation"),
        param("${f:USER,root}", "${f:USER,root}", id="primitive:custom_inter"),
        param("${f.g:USER,root}", "${f.g:USER,root}", id="primitive:custom_inter"),
        param("c:\\foo\\a-b.txt", "c:\\foo\\a-b.txt", id="primitive:windows_path"),
        # null
        param("null", None, id="primitive:null"),
        # int
        param("0", 0, id="primitive:int:zero"),
        param("-1", -1, id="primitive:int:neg"),
        param("1", 1, id="primitive:int:pos"),
        param("10_0", 100, id="primitive:int:underscore"),
        # float
        param("0.0", 0.0, id="primitive:float:zero"),
        param("0.51", 0.51, id="primitive:float:positive"),
        param("1e-05", 1e-05, id="primitive:float:small"),
        param("-3.14", -3.14, id="primitive:float:negative"),
        param("3.1_4", 3.14, id="primitive:float:underscore"),
        param("10e0", 10.0, id="primitive:float:exp"),
        param("-10e1", -100.0, id="primitive:float:exp:neg"),
        param("inf", math.inf, id="primitive:float:inf"),
        param("INF", math.inf, id="primitive:float:inf"),
        param("-inf", -math.inf, id="primitive:float:inf:neg"),
        param("nan", math.nan, id="primitive:float:nan"),
        param("NaN", math.nan, id="primitive:float:nan"),
        # bool
        param("true", True, id="primitive:bool"),
        param("false", False, id="primitive:bool"),
        # interpolations:
        param("${a}", "${a}", id="primitive:interpolation"),
        param("${a.b.c}", "${a.b.c}", id="primitive:interpolation"),
        param("${foo:a}", "${foo:a}", id="primitive:interpolation"),
        param("${foo:1,2,3}", "${foo:1,2,3}", id="primitive:interpolation"),
        param("${foo:[1,2,3]}", "${foo:[1,2,3]}", id="primitive:interpolation"),
    ],
)
def test_primitive(value: str, expected: Any) -> None:
    ret = parse_rule(value, "primitive")
    assert eq(ret, expected)


@mark.parametrize(
    ("value", "expected"),
    [
        param(
            r"'foo \'bar'",
            QuotedString(text="foo 'bar", quote=Quote.single),
            id="escape_single_quote",
        ),
        param(
            r'"foo \"bar"',
            QuotedString(text='foo "bar', quote=Quote.double),
            id="escape_double_quote",
        ),
        param(
            r"'foo \\\'bar'",
            QuotedString(text=r"foo \'bar", quote=Quote.single),
            id="escape_single_quote_x3",
        ),
        param(
            r'"foo \\\"bar"',
            QuotedString(text=r"foo \"bar", quote=Quote.double),
            id="escape_double_quote_x3",
        ),
        param(
            r"'foo\bar'",
            QuotedString(text=r"foo\bar", quote=Quote.single),
            id="one_backslash_single",
        ),
        param(
            r'"foo\bar"',
            QuotedString(text=r"foo\bar", quote=Quote.double),
            id="one_backslash_double",
        ),
        param(
            r"'foo\\bar'",
            QuotedString(text=r"foo\\bar", quote=Quote.single),
            id="noesc_backslash",
        ),
        param(
            r"'foo\\\\bar'",
            QuotedString(text=r"foo\\\\bar", quote=Quote.single),
            id="noesc_backslash_x4",
        ),
        param(
            r"'foo bar\\'",
            # Note: raw strings do not allow trailing \, adding a space and stripping it.
            QuotedString(text=r" foo bar\ ".strip(), quote=Quote.single),
            id="escape_backslash_trailing",
        ),
        param(
            r"'foo \\\\\'bar\' \\\\\\'",
            QuotedString(text=r" foo \\'bar' \\\ ".strip(), quote=Quote.single),
            id="escape_mixed",
        ),
        param(
            "'\t []{},=+~'",
            QuotedString(text="\t []{},=+~", quote=Quote.single),
            id="quoted_specials",
        ),
        param(
            '"\t []{},=+~"',
            QuotedString(text="\t []{},=+~", quote=Quote.double),
            id="quoted_specials",
        ),
        param(
            "'a b c'",
            QuotedString(text="a b c", quote=Quote.single),
            id="quoted_with_whitespace",
        ),
        param(
            "'a,b'",
            QuotedString(text="a,b", quote=Quote.single),
            id="quoted_with_comma",
        ),
        param(
            "'[1,2,3]'",
            QuotedString(text="[1,2,3]", quote=Quote.single),
            id="quoted_list",
        ),
        param(
            '"[1,2,3]"',
            QuotedString(text="[1,2,3]", quote=Quote.double),
            id="quoted_list",
        ),
        param(
            "\"[1,'2',3]\"",
            QuotedString(text="[1,'2',3]", quote=Quote.double),
            id="quoted_list_with_quoted_element",
        ),
        param(
            "'null'",
            QuotedString(text="null", quote=Quote.single),
            id="null",
        ),
        param("'100'", QuotedString(text="100", quote=Quote.single), id="int"),
        param(
            "'3.14'",
            QuotedString(text="3.14", quote=Quote.single),
            id="float",
        ),
        param(
            "'nan'",
            QuotedString(text="nan", quote=Quote.single),
            id="float:constant",
        ),
        param(
            "'inf'",
            QuotedString(text="inf", quote=Quote.single),
            id="float:constant",
        ),
        param(
            "'nan'",
            QuotedString(text="nan", quote=Quote.single),
            id="float:constant",
        ),
        param(
            "'true'",
            QuotedString(text="true", quote=Quote.single),
            id="bool",
        ),
        param(
            "'false'",
            QuotedString(text="false", quote=Quote.single),
            id="bool",
        ),
        param(
            "'a ${b}'",
            QuotedString(text="a ${b}", quote=Quote.single),
            id="interpolation",
        ),
        param(
            r"'a \${b}'",
            QuotedString(text=r"a \${b}", quote=Quote.single),
            id="esc_interpolation",
        ),
        param(
            r"'a \'\${b}\''",
            QuotedString(text=r"a '\${b}'", quote=Quote.single),
            id="quotes_and_esc_interpolation",
        ),
        param(
            r"'a \\${b}'",
            QuotedString(text=r"a \\${b}", quote=Quote.single),
            id="backslash_and_interpolation",
        ),
        param(
            r"'a \'${b}\''",
            QuotedString(text=r"a '${b}'", quote=Quote.single),
            id="quotes_and_interpolation",
        ),
        param(
            r"'a \'\\${b}\''",
            QuotedString(text=r"a '\\${b}'", quote=Quote.single),
            id="quotes_backslash_and_interpolation",
        ),
        param(
            r"'a \\\'${b}\\\''",
            QuotedString(text=r"a \'${b}\'", quote=Quote.single),
            id="backslash_quotes_and_interpolation",
        ),
        param(
            r"'${foo:\'b,a,r\'}'",
            QuotedString(text="${foo:'b,a,r'}", quote=Quote.single),
            id="interpolation_with_quoted_string",
        ),
        param(
            r"""'${foo:${a}, \'\${bar}\\\'\', {x: "${y}"}}'""",
            QuotedString(
                text=r"""${foo:${a}, '\${bar}\'', {x: "${y}"}}""", quote=Quote.single
            ),
            id="nested_interpolation",
        ),
        param(
            r"""'${foo:"\' }"}'""",
            QuotedString(text=r"""${foo:"' }"}""", quote=Quote.single),
            id="interpolation_apparent_brace_mismatch",
        ),
    ],
)
def test_primitive_quoted_string(value: str, expected: Any) -> None:
    ret = parse_rule(value, "primitive")
    assert isinstance(ret, QuotedString)
    assert eq(ret, expected)
    assert value == ret.with_quotes()  # round-trip


@mark.parametrize(
    "prefix,override_type",
    [
        param("", OverrideType.CHANGE, id="change"),
        param("+", OverrideType.ADD, id="add"),
        param("++", OverrideType.FORCE_ADD, id="force_add"),
        param("~", OverrideType.DEL, id="del"),
    ],
)
@mark.parametrize(
    "value,expected_key,expected_value,expected_value_type",
    [
        param("key=value", "key", "value", ValueType.ELEMENT, id="simple_value"),
        param(
            "key='1,2,3'",
            "key",
            QuotedString(text="1,2,3", quote=Quote.single),
            ValueType.ELEMENT,
            id="simple_value",
        ),
        param(
            "key='שלום'",
            "key",
            QuotedString(text="שלום", quote=Quote.single),
            ValueType.ELEMENT,
            id="unicode",
        ),
        param("key=value-123", "key", "value-123", ValueType.ELEMENT, id="id-int"),
        param("key=value-1.0", "key", "value-1.0", ValueType.ELEMENT, id="id-float"),
        param("key=value-true", "key", "value-true", ValueType.ELEMENT, id="id-bool"),
        param("key=", "key", "", ValueType.ELEMENT, id="empty_value"),
        param(
            "key='foo,bar'",
            "key",
            QuotedString(text="foo,bar", quote=Quote.single),
            ValueType.ELEMENT,
            id="quoted_value",
        ),
        param(
            "key='foo , bar'",
            "key",
            QuotedString(text="foo , bar", quote=Quote.single),
            ValueType.ELEMENT,
            id="quoted_value",
        ),
        param(
            "key=1,2,3",
            "key",
            ChoiceSweep(list=[1, 2, 3], simple_form=True),
            ValueType.SIMPLE_CHOICE_SWEEP,
            id="choice",
        ),
        param(
            "key=choice(1)",
            "key",
            ChoiceSweep(list=[1]),
            ValueType.CHOICE_SWEEP,
            id="choice_1_element",
        ),
        param(
            "key=choice(1,2,3)",
            "key",
            ChoiceSweep(list=[1, 2, 3]),
            ValueType.CHOICE_SWEEP,
            id="choice_sweep",
        ),
        param(
            "key=[1,2],[3,4]",
            "key",
            ChoiceSweep(list=[[1, 2], [3, 4]], simple_form=True),
            ValueType.SIMPLE_CHOICE_SWEEP,
            id="choice",
        ),
        param(
            "key=choice([1,2],[3,4])",
            "key",
            ChoiceSweep(list=[[1, 2], [3, 4]]),
            ValueType.CHOICE_SWEEP,
            id="choice",
        ),
        param(
            "key=range(0,2)",
            "key",
            RangeSweep(start=0, stop=2),
            ValueType.RANGE_SWEEP,
            id="range",
        ),
        param(
            "key=range(1,5,2)",
            "key",
            RangeSweep(start=1, stop=5, step=2),
            ValueType.RANGE_SWEEP,
            id="range",
        ),
        param(
            "key=range(10.0, 11.0)",
            "key",
            RangeSweep(start=10.0, stop=11.0, step=1.0),
            ValueType.RANGE_SWEEP,
            id="range",
        ),
        param(
            "key=interval(0,1)",
            "key",
            IntervalSweep(start=0.0, end=1.0),
            ValueType.INTERVAL_SWEEP,
            id="interval",
        ),
        # tags
        param(
            "key=tag(a,b,choice([1,2],[3,4]))",
            "key",
            ChoiceSweep(list=[[1, 2], [3, 4]], tags={"a", "b"}),
            ValueType.CHOICE_SWEEP,
            id="choice:tags",
        ),
        param(
            "key=tag(a,b,interval(0,1))",
            "key",
            IntervalSweep(tags={"a", "b"}, start=0.0, end=1.0),
            ValueType.INTERVAL_SWEEP,
            id="interval:tags",
        ),
        param("key=str([1,2])", "key", ["1", "2"], ValueType.ELEMENT, id="cast_list"),
        param(
            "choice=reverse",
            "choice",
            "reverse",
            ValueType.ELEMENT,
            id="using_function_name_in_key",
        ),
    ],
)
def test_override(
    prefix: str,
    value: str,
    override_type: OverrideType,
    expected_key: str,
    expected_value: Any,
    expected_value_type: ValueType,
) -> None:
    line = prefix + value
    ret = parse_rule(line, "override")
    expected = Override(
        input_line=line,
        type=override_type,
        key_or_group=expected_key,
        _value=expected_value,
        value_type=expected_value_type,
    )
    assert ret == expected


@mark.parametrize(
    "value,expected_key,expected_value",
    [
        param(
            "key=extend_list([1,2])",
            "key",
            [[1, 2]],
            id="extend_list_of_list",
        ),
        param(
            "key=extend_list(1,2,3)",
            "key",
            [1, 2, 3],
            id="extend_list_with_multiple_vals",
        ),
    ],
)
def test_list_extend_override(
    value: str,
    expected_key: str,
    expected_value: Any,
) -> None:
    with warns(UserWarning, match=re.escape(EXTEND_LIST_DEPRECATION_WARNING)):
        test_override(
            "",
            value,
            OverrideType.EXTEND_LIST,
            expected_key,
            expected_value,
            ValueType.ELEMENT,
        )


def test_name_package_is_literal() -> None:
    assert parse_rule("key@_name_=value", "override") == Override(
        type=OverrideType.CHANGE,
        key_or_group="key",
        value_type=ValueType.ELEMENT,
        _value="value",
        package="_name_",
        input_line="key@_name_=value",
        config_loader=None,
    )


@mark.parametrize(
    "value,expected",
    [
        param(
            "~x",
            Override(
                type=OverrideType.DEL, key_or_group="x", value_type=None, _value=None
            ),
            id="bare_del",
        ),
        param(
            "~x=10",
            Override(
                type=OverrideType.DEL,
                key_or_group="x",
                value_type=ValueType.ELEMENT,
                _value=10,
            ),
            id="specific_del",
        ),
        param(
            "~x=",
            Override(
                type=OverrideType.DEL,
                key_or_group="x",
                value_type=ValueType.ELEMENT,
                _value="",
            ),
            id="specific_del_empty_string",
        ),
    ],
)
def test_override_del(value: str, expected: Any) -> None:
    expected.input_line = value
    ret = parse_rule(value, "override")
    assert ret == expected


def test_parse_overrides() -> None:
    overrides = ["x=10", "y=[1,2]", "z=a,b,c", "z=choice(a,b,c)"]
    expected = [
        Override(
            type=OverrideType.CHANGE,
            key_or_group="x",
            value_type=ValueType.ELEMENT,
            _value=10,
            input_line=overrides[0],
        ),
        Override(
            type=OverrideType.CHANGE,
            key_or_group="y",
            value_type=ValueType.ELEMENT,
            _value=[1, 2],
            input_line=overrides[1],
        ),
        Override(
            type=OverrideType.CHANGE,
            key_or_group="z",
            value_type=ValueType.SIMPLE_CHOICE_SWEEP,
            _value=ChoiceSweep(list=["a", "b", "c"], simple_form=True),
            input_line=overrides[2],
        ),
        Override(
            type=OverrideType.CHANGE,
            key_or_group="z",
            value_type=ValueType.CHOICE_SWEEP,
            _value=ChoiceSweep(list=["a", "b", "c"]),
            input_line=overrides[3],
        ),
    ]
    ret = parser.parse_overrides(overrides)
    assert ret == expected


@mark.parametrize(
    "override,expected",
    [
        # change
        param("key=value", "key", id="key"),
        param("key@pkg1=value", "key@pkg1", id="key@pkg1"),
        # add
        param("+key=value", "+key", id="+key"),
        param("+key@pkg1=value", "+key@pkg1", id="+key@pkg1"),
        # force-add
        param("++key=value", "++key", id="++key"),
        param("++key@pkg1=value", "++key@pkg1", id="++key@pkg1"),
        # del
        param("~key=value", "~key", id="~key"),
        param("~key@pkg1=value", "~key@pkg1", id="~key@pkg1"),
    ],
)
def test_get_key_element(override: str, expected: str) -> None:
    ret = parse_rule(override, "override")
    assert ret.get_key_element() == expected


@mark.parametrize(
    "override,expected,space_after_sep",
    [
        param("key=value", "value", False, id="str"),
        param("key='value'", "'value'", False, id="single_quoted"),
        param('key="value"', '"value"', False, id="double_quoted"),
        param("key='שלום'", "'שלום'", False, id="quoted_unicode"),
        param(
            "key=\\\\\\(\\)\\[\\]\\{\\}\\:\\=\\ \\\t\\,",
            "\\\\\\(\\)\\[\\]\\{\\}\\:\\=\\ \\\t\\,",
            False,
            id="escaped_chars",
        ),
        param("key=10", "10", False, id="int"),
        param("key=3.1415", "3.1415", False, id="float"),
        param("key=[]", "[]", False, id="list"),
        param("key=[1,2,3]", "[1,2,3]", False, id="list"),
        param("key=[1,2,3]", "[1, 2, 3]", True, id="list"),
        param("key=['a b', 2, 3]", "['a b',2,3]", False, id="list"),
        param("key=['a b', 2, 3]", "['a b', 2, 3]", True, id="list"),
        param("key={}", "{}", False, id="dict"),
        param("key={a:10}", "{a:10}", False, id="dict"),
        param("key={a:10}", "{a: 10}", True, id="dict"),
        param("key={a:10,b:20}", "{a:10,b:20}", False, id="dict"),
        param("key={a:10,b:20}", "{a: 10, b: 20}", True, id="dict"),
        param("key={a:10,b:[1,2,3]}", "{a: 10, b: [1, 2, 3]}", True, id="dict"),
        param(
            "key={%s: 1}" % UNQUOTED_SPECIAL,
            # Note that \ gets escaped.
            "{%s: 1}" % UNQUOTED_SPECIAL.replace("\\", "\\\\"),
            True,
            id="dict_unquoted_key_special",
        ),
        param(
            "key={ white  space\t: 2}",
            "{white\\ \\ space: 2}",
            True,
            id="dict_ws_in_key",
        ),
        param(
            "key={\\\\\\(\\)\\[\\]\\{\\}\\:\\=\\ \\\t\\,: 2}",
            "{\\\\\\(\\)\\[\\]\\{\\}\\:\\=\\ \\\t\\,: 2}",
            True,
            id="dict_esc_key",
        ),
    ],
)
def test_override_get_value_element_method(
    override: str, expected: str, space_after_sep: bool
) -> None:
    ret = parse_rule(override, "override")
    assert ret.get_value_element_as_str(space_after_sep=space_after_sep) == expected


@mark.parametrize(
    "override,expected",
    [
        param("key=value", "value", id="str"),
        param("key='value'", "value", id="quoted_str"),
        param('key="value"', "value", id="quoted_str"),
        param("key=10", 10, id="int"),
        param("key=3.1415", 3.1415, id="float"),
        param("key=[]", [], id="list"),
        param("key=[1,2,3]", [1, 2, 3], id="list"),
        param("key=[1,2,3]", [1, 2, 3], id="list"),
        param("key=['a b', 2, 3]", ["a b", 2, 3], id="list"),
        param("key=['a b', 2, 3]", ["a b", 2, 3], id="list"),
        param("key={}", {}, id="dict"),
        param("key={a:10}", {"a": 10}, id="dict"),
        param("key={a:10}", {"a": 10}, id="dict"),
        param("key={a:10,b:20}", {"a": 10, "b": 20}, id="dict"),
        param("key={a:10,b:20}", {"a": 10, "b": 20}, id="dict"),
        param("key={a:10,b:[1,2,3]}", {"a": 10, "b": [1, 2, 3]}, id="dict"),
        param("key={123id: 0}", {"123id": 0}, id="dict_key_int_plus_id"),
        param(
            "key={%s: 0}" % UNQUOTED_SPECIAL,
            {UNQUOTED_SPECIAL: 0},
            id="dict_key_noquote",
        ),
        param("key={w s: 0}", {"w s": 0}, id="dict_key_ws"),
        param(
            "key={\\\\\\(\\)\\[\\]\\{\\}\\:\\=\\ \\\t\\,: 0}",
            {"\\()[]{}:= \t,": 0},
            id="dict_key_esc",
        ),
    ],
)
def test_override_value_method(override: str, expected: str) -> None:
    ret = parse_rule(override, "override")
    assert ret.value() == expected


@mark.parametrize(
    "start,stop,step,expected",
    [
        # empty
        param(0, 0, 1, [], id="FloatRange:empty"),
        param(0, 0, -1, [], id="FloatRange:empty"),
        param(10, 0, 1, [], id="FloatRange:empty"),
        param(0, 10, -1, [], id="FloatRange:empty"),
        # up
        param(0, 2, 1, [0.0, 1.0], id="FloatRange:up"),
        param(0, 2, 0.5, [0.0, 0.5, 1.0, 1.5], id="FloatRange:up"),
        param(0, 2, 1, [0.0, 1.0], id="FloatRange:up"),
        # down
        param(2, 0, -1, [2.0, 1.0], id="FloatRange:down"),
        param(10.0, 5.0, -2, [10.0, 8.0, 6.0], id="FloatRange:down"),
    ],
)
def test_float_range(
    start: float, stop: float, step: float, expected: List[float]
) -> None:
    res = list(FloatRange(start, stop, step))
    assert len(res) == len(expected)
    for i in range(len(res)):
        assert math.fabs(res[i] - expected[i]) < 10e-6


@mark.parametrize(
    "value, expected",
    [
        # choice
        param("tag(choice(a,b))", ChoiceSweep(list=["a", "b"]), id="tag(choice(a,b))"),
        param(
            "tag(tag1,tag2,choice(a,b))",
            ChoiceSweep(list=["a", "b"], tags={"tag1", "tag2"}),
            id="tag(tag1,tag2,choice(a,b))",
        ),
        # interval
        param(
            "tag(interval(0,2))",
            IntervalSweep(start=0.0, end=2.0),
            id="tag(interval(0,2))",
        ),
        param(
            "tag(tag1,tag2,interval(0,2))",
            IntervalSweep(start=0.0, end=2.0, tags={"tag1", "tag2"}),
            id="tag(tag1,tag2,interval(0,2))",
        ),
        # range
        param("tag(range(1,2))", RangeSweep(start=1, stop=2), id="tag(range(1,2))"),
        param(
            "tag(tag1,tag2,range(1,2))",
            RangeSweep(start=1, stop=2, tags={"tag1", "tag2"}),
            id="tag(tag1,tag2,range(1,2))",
        ),
        param(
            "tag(tag1,tag2,sweep=range(1,2))",
            RangeSweep(start=1, stop=2, tags={"tag1", "tag2"}),
            id="tag(tag1,tag2,sweep=range(1,2))",
        ),
    ],
)
def test_tag_sweep(value: str, expected: str) -> None:
    ret = parse_rule(value, "function")
    assert ret == expected


@mark.parametrize(
    "value, expected",
    [
        # value
        param("sort(1)", 1, id="sort:value"),
        param("sort({a:10})", {"a": 10}, id="sort:value"),
        # list
        param("sort([1])", [1], id="sort:list"),
        param("sort([1,2,3])", [1, 2, 3], id="sort:list"),
        param("sort(list=[1,2,3])", [1, 2, 3], id="sort:list:named"),
        param("sort(list=[])", [], id="sort:list:named:empty"),
        param("sort(list=[1,2,3], reverse=True)", [3, 2, 1], id="sort:list:named:rev"),
        # simple choice sweep
        param(
            "sort(1,2,3)",
            ChoiceSweep(list=[1, 2, 3], simple_form=True),
            id="sort:choice:simple",
        ),
        param(
            "sort(1,2,3,reverse=True)",
            ChoiceSweep(list=[3, 2, 1], simple_form=True),
            id="sort:choice:simple:rev",
        ),
        # choice sweep
        param("sort(choice(1,2,3))", ChoiceSweep(list=[1, 2, 3]), id="sort:choice"),
        param(
            "sort(sweep=choice(1,2,3))",
            ChoiceSweep(list=[1, 2, 3]),
            id="sort:choice:named",
        ),
        param(
            "sort(choice(1,2,3), reverse=True)",
            ChoiceSweep(list=[3, 2, 1]),
            id="sort:choice:rev",
        ),
        param(
            "sort(tag(a,b,choice(1,2,3)), reverse=True)",
            ChoiceSweep(list=[3, 2, 1], tags={"a", "b"}),
            id="sort:tag:choice:rev",
        ),
        # sort integer range
        param(
            "sort(range(1, 10))",
            RangeSweep(start=1, stop=10, step=1),
            id="sort(range(1, 10))",
        ),
        param(
            "sort(range(9,0,-1))",
            RangeSweep(start=1, stop=10, step=1),
            id="sort(range(1, 10))",
        ),
        param(
            "sort(range(1,10),reverse=True)",
            RangeSweep(start=9, stop=0, step=-1),
            id="sort(range(1,10),reverse=True)",
        ),
        param(
            "sort(sort(range(1, 10),reverse=true))",
            RangeSweep(start=1, stop=10, step=1),
            id="sort(sort(range(1, 10),reverse=true))",
        ),
        # sort float range
        param(
            "sort(range(0,2,0.5))",
            RangeSweep(start=0, stop=2, step=0.5),
            id="sort(range(0,2,0.5))",
        ),
        param(
            "sort(range(1.5,-0.5,-0.5))",
            RangeSweep(start=0.0, stop=1.75, step=0.5),
            id="sort(range(1.5,-0.5,-0.5))",
        ),
        param(
            "sort(range(0,2,0.5),reverse=true)",
            RangeSweep(start=1.5, stop=-0.25, step=-0.5),
            id="range:sort:reverse)",
        ),
        # ranges that do not land exactly on ``stop`` (last element != stop - step)
        param(
            "sort(range(0,5,2),reverse=True)",
            RangeSweep(start=4, stop=-2, step=-2),
            id="sort:range:non_landing:reverse",
        ),
        param(
            "sort(range(4,-1,-2))",
            RangeSweep(start=0, stop=6, step=2),
            id="sort:range:non_landing:ascending",
        ),
        param(
            "sort(range(7,0,-3))",
            RangeSweep(start=1, stop=10, step=3),
            id="sort:range:non_landing:ascending2",
        ),
        param(
            "shuffle(range(1, 10))",
            RangeSweep(start=1, stop=10, step=1, shuffle=True),
            id="range:shuffle",
        ),
    ],
)
def test_sort(value: str, expected: str) -> None:
    ret = parse_rule(value, "function")
    assert ret == expected


@mark.parametrize(
    "start, stop, step",
    [
        param(0, 5, 2, id="int:non_landing"),
        param(4, -1, -2, id="int:non_landing:neg_step"),
        param(7, 0, -3, id="int:non_landing:neg_step2"),
        param(1, 10, 1, id="int:landing"),
        param(0, 1, 1, id="int:single_element"),
        param(0, 0, 1, id="int:empty"),
        param(1, 0, 1, id="int:empty_positive_step"),
        param(0, 2, 0.5, id="float:landing"),
        param(0, 1.3, 0.5, id="float:non_landing"),
        param(1.3, 0, -0.5, id="float:non_landing:neg_step"),
        param(0, 1, 0.1, id="float:decimal_step"),
        param(0, 1, 0.2, id="float:decimal_step2"),
        param(0, 0.3, 0.1, id="float:short_decimal_step"),
        param(1, 0, -0.1, id="float:negative_decimal_step"),
    ],
)
def test_sort_range_materializes_to_sorted_values(
    start: float, stop: float, step: float
) -> None:
    original = list(grammar_functions.range(start, stop, step).range())
    for reverse in (False, True):
        sweep = grammar_functions.sort(
            grammar_functions.range(start, stop, step), reverse=reverse
        )
        assert list(sweep.range()) == sorted(original, reverse=reverse)


@mark.parametrize(
    "value, expected",
    [
        # simple choice sweep
        param(
            "shuffle(1,2,3)",
            ChoiceSweep(simple_form=True, list=[1, 2, 3], tags=set(), shuffle=True),
            id="shuffle:choice:simple",
        ),
        # choice sweep
        param(
            "shuffle(choice(1,2,3))",
            ChoiceSweep(list=[1, 2, 3], tags=set(), shuffle=True),
            id="shuffle:choice",
        ),
        param(
            "shuffle(tag(a,b,choice(1,2,3)))",
            ChoiceSweep(list=[1, 2, 3], tags={"a", "b"}, shuffle=True),
            id="shuffle:tag:choice",
        ),
        # range sweep
        param(
            "shuffle(range(10,1))",
            RangeSweep(start=10, stop=1, shuffle=True),
            id="shuffle:range",
        ),
        param(
            "shuffle(float(range(10,1))))",
            RangeSweep(start=10.0, stop=1.0, shuffle=True),
            id="shuffle:float:range",
        ),
        param(
            "shuffle(tag(a,b,range(1,10,2)))",
            RangeSweep(start=1, stop=10, step=2, tags={"a", "b"}, shuffle=True),
            id="shuffle:tag:range",
        ),
    ],
)
def test_sweep_shuffle(value: str, expected: str) -> None:
    ret = parse_rule(value, "function")
    assert ret == expected


@dataclass
class CastResults:
    json_str: Union[
        str,
        Sweep,
        RaisesContext[HydraException],
    ]
    int: Union[
        int,
        List[Union[int, List[int]]],
        Dict[str, Any],
        Sweep,
        RaisesContext[HydraException],
    ]
    float: Union[
        float,
        List[Union[float, List[float]]],
        Dict[str, Any],
        Sweep,
        RaisesContext[HydraException],
    ]
    bool: Union[
        bool,
        List[Union[bool, List[bool]]],
        Dict[str, Any],
        Sweep,
        RaisesContext[HydraException],
    ]
    str: Union[
        str,
        List[Union[str, List[str]]],
        Dict[str, Any],
        Sweep,
        RaisesContext[HydraException],
    ]

    @staticmethod
    def error(msg: builtins.str) -> Any:
        return raises(HydraException, match=f"^{re.escape(msg)}")


@mark.parametrize(
    "value,expected_value",
    [
        # int
        param(
            10,
            CastResults(int=10, float=10.0, str="10", bool=True, json_str="10"),
            id="10",
        ),
        param(
            0, CastResults(int=0, float=0.0, str="0", bool=False, json_str="0"), id="0"
        ),
        # float
        param(
            10.0,
            CastResults(int=10, float=10.0, str="10.0", bool=True, json_str="10.0"),
            id="10.0",
        ),
        param(
            0.0,
            CastResults(int=0, float=0.0, str="0.0", bool=False, json_str="0.0"),
            id="0.0",
        ),
        param(
            "inf",
            CastResults(
                int=CastResults.error(
                    "OverflowError while evaluating 'int(inf)': cannot convert float infinity to integer"
                ),
                float=math.inf,
                str="inf",
                bool=True,
                json_str="Infinity",
            ),
            id="inf",
        ),
        param(
            "nan",
            CastResults(
                int=CastResults.error(
                    "ValueError while evaluating 'int(nan)': cannot convert float NaN to integer"
                ),
                float=math.nan,
                str="nan",
                bool=True,
                json_str="NaN",
            ),
            id="nan",
        ),
        param(
            "1e6",
            CastResults(
                int=1000000, float=1e6, str="1000000.0", bool=True, json_str="1000000.0"
            ),
            id="1e6",
        ),
        param(
            "''",
            CastResults(
                int=CastResults.error(
                    "ValueError while evaluating 'int('')': invalid literal for int() with base 10:"
                ),
                float=CastResults.error(
                    "ValueError while evaluating 'float('')': could not convert string to float:"
                ),
                str="",
                bool=CastResults.error(
                    "ValueError while evaluating 'bool('')': Cannot cast '' to bool"
                ),
                json_str='""',
            ),
            id="''",
        ),
        # string
        param(
            "'10'",
            CastResults(
                int=10,
                float=10.0,
                str="10",
                bool=CastResults.error(
                    "ValueError while evaluating 'bool('10')': Cannot cast '10' to bool"
                ),
                json_str='"10"',
            ),
            id="'10'",
        ),
        param(
            "'10.0'",
            CastResults(
                int=CastResults.error(
                    "ValueError while evaluating 'int('10.0')': invalid literal for int() with base 10: '10.0'"
                ),
                float=10.0,
                str="10.0",
                bool=CastResults.error(
                    "ValueError while evaluating 'bool('10.0')': Cannot cast '10.0' to bool"
                ),
                json_str='"10.0"',
            ),
            id="'10.0'",
        ),
        param(
            "'true'",
            CastResults(
                int=CastResults.error(
                    "ValueError while evaluating 'int('true')': invalid literal for int() with base 10: 'true'"
                ),
                float=CastResults.error(
                    "ValueError while evaluating 'float('true')': could not convert string to float: 'true'"
                ),
                str="true",
                bool=True,
                json_str='"true"',
            ),
            id="'true'",
        ),
        param(
            "'false'",
            CastResults(
                int=CastResults.error(
                    "ValueError while evaluating 'int('false')': invalid literal for int() with base 10: 'false'"
                ),
                float=CastResults.error(
                    "ValueError while evaluating 'float('false')': could not convert string to float: 'false'"
                ),
                str="false",
                bool=False,
                json_str='"false"',
            ),
            id="'false'",
        ),
        param(
            "'[1,2,3]'",
            CastResults(
                int=CastResults.error(
                    "ValueError while evaluating 'int('[1,2,3]')': invalid literal for int() with base 10: '[1,2,3]'"
                ),
                float=CastResults.error(
                    "ValueError while evaluating 'float('[1,2,3]')': could not convert string to float: '[1,2,3]'"
                ),
                str="[1,2,3]",
                bool=CastResults.error(
                    "ValueError while evaluating 'bool('[1,2,3]')': Cannot cast '[1,2,3]' to bool"
                ),
                json_str='"[1,2,3]"',
            ),
            id="'[1,2,3]'",
        ),
        param(
            "'{a:10}'",
            CastResults(
                int=CastResults.error(
                    "ValueError while evaluating 'int('{a:10}')': invalid literal for int() with base 10: '{a:10}'"
                ),
                float=CastResults.error(
                    "ValueError while evaluating 'float('{a:10}')': could not convert string to float: '{a:10}'"
                ),
                str="{a:10}",
                bool=CastResults.error(
                    "ValueError while evaluating 'bool('{a:10}')': Cannot cast '{a:10}' to bool"
                ),
                json_str='"{a:10}"',
            ),
            id="'{a:10}'",
        ),
        # bool
        param(
            "true",
            CastResults(int=1, float=1.0, str="true", bool=True, json_str="true"),
            id="true",
        ),
        param(
            "false",
            CastResults(int=0, float=0.0, str="false", bool=False, json_str="false"),
            id="false",
        ),
        # list
        param(
            "[]", CastResults(int=[], float=[], str=[], bool=[], json_str="[]"), id="[]"
        ),
        param(
            "[0,1,2]",
            CastResults(
                int=[0, 1, 2],
                float=[0.0, 1.0, 2.0],
                str=["0", "1", "2"],
                bool=[False, True, True],
                json_str="[0, 1, 2]",
            ),
            id="[1,2,3]",
        ),
        param(
            "[1,[2]]",
            CastResults(
                int=[1, [2]],
                float=[1.0, [2.0]],
                str=["1", ["2"]],
                bool=[True, [True]],
                json_str="[1, [2]]",
            ),
            id="[1,[2]]",
        ),
        param(
            "[a,1]",
            CastResults(
                int=CastResults.error(
                    "ValueError while evaluating 'int([a,1])': invalid literal for int() with base 10: 'a'"
                ),
                float=CastResults.error(
                    "ValueError while evaluating 'float([a,1])': could not convert string to float: 'a'"
                ),
                str=["a", "1"],
                bool=CastResults.error(
                    "ValueError while evaluating 'bool([a,1])': Cannot cast 'a' to bool"
                ),
                json_str='["a", 1]',
            ),
            id="[a,1]",
        ),
        # dicts
        param(
            "{}", CastResults(int={}, float={}, str={}, bool={}, json_str="{}"), id="{}"
        ),
        param(
            "{a:10}",
            CastResults(
                int={"a": 10},
                float={"a": 10.0},
                str={"a": "10"},
                bool={"a": True},
                json_str='{"a": 10}',
            ),
            id="{a:10}",
        ),
        param(
            "{a:[0,1,2]}",
            CastResults(
                int={"a": [0, 1, 2]},
                float={"a": [0.0, 1.0, 2.0]},
                str={"a": ["0", "1", "2"]},
                bool={"a": [False, True, True]},
                json_str='{"a": [0, 1, 2]}',
            ),
            id="{a:[0,1,2]}",
        ),
        param(
            "{a:10,b:xyz}",
            CastResults(
                int=CastResults.error(
                    "ValueError while evaluating 'int({a:10,b:xyz})': invalid literal for int() with base 10: 'xyz'"
                ),
                float=CastResults.error(
                    "ValueError while evaluating 'float({a:10,b:xyz})': could not convert string to float: 'xyz'"
                ),
                str={"a": "10", "b": "xyz"},
                bool=CastResults.error(
                    "ValueError while evaluating 'bool({a:10,b:xyz})': Cannot cast 'xyz' to bool"
                ),
                json_str='{"a": 10, "b": "xyz"}',
            ),
            id="{a:10,b:xyz}",
        ),
        param(
            "{a:10,b:xyz,c:{d:foo,f:[1,2,{g:0}]}}",
            CastResults(
                int=CastResults.error(
                    "ValueError while evaluating 'int({a:10,b:xyz,c:{d:foo,f:[1,2,{g:0}]}})': "
                    "invalid literal for int() with base 10: 'xyz'"
                ),
                float=CastResults.error(
                    "ValueError while evaluating 'float({a:10,b:xyz,c:{d:foo,f:[1,2,{g:0}]}})': "
                    "could not convert string to float: 'xyz'"
                ),
                str={
                    "a": "10",
                    "b": "xyz",
                    "c": {"d": "foo", "f": ["1", "2", {"g": "0"}]},
                },
                bool=CastResults.error(
                    "ValueError while evaluating 'bool({a:10,b:xyz,c:{d:foo,f:[1,2,{g:0}]}})': "
                    "Cannot cast 'xyz' to bool"
                ),
                json_str='{"a": 10, "b": "xyz", "c": {"d": "foo", "f": [1, 2, {"g": 0}]}}',
            ),
            id="{a:10,b:xyz,c:{d:foo,f:[1,2,{g:0}]}}",
        ),
        # choice
        param(
            "choice(0,1)",
            CastResults(
                int=ChoiceSweep(list=[0, 1]),
                float=ChoiceSweep(list=[0.0, 1.0]),
                str=ChoiceSweep(list=["0", "1"]),
                bool=ChoiceSweep(list=[False, True]),
                json_str=ChoiceSweep(list=["0", "1"]),
            ),
            id="choice(0,1)",
        ),
        param(
            "2,1,0",
            CastResults(
                int=ChoiceSweep(list=[2, 1, 0], simple_form=True),
                float=ChoiceSweep(list=[2.0, 1.0, 0.0], simple_form=True),
                str=ChoiceSweep(list=["2", "1", "0"], simple_form=True),
                bool=ChoiceSweep(list=[True, True, False], simple_form=True),
                json_str=ChoiceSweep(list=["2", "1", "0"], simple_form=True),
            ),
            id="simple_choice:ints",
        ),
        param(
            "a,'b',1,1.0,true,[a,b],{a:10}",
            CastResults(
                int=CastResults.error(
                    "ValueError while evaluating 'int(a,'b',1,1.0,true,[a,b],{a:10})':"
                    " invalid literal for int() with base 10: 'a'"
                ),
                float=CastResults.error(
                    "ValueError while evaluating 'float(a,'b',1,1.0,true,[a,b],{a:10})':"
                    " could not convert string to float: 'a'"
                ),
                str=ChoiceSweep(
                    list=["a", "b", "1", "1.0", "true", ["a", "b"], {"a": "10"}],
                    simple_form=True,
                ),
                bool=CastResults.error(
                    "ValueError while evaluating 'bool(a,'b',1,1.0,true,[a,b],{a:10})': Cannot cast 'a' to bool"
                ),
                json_str=ChoiceSweep(
                    list=['"a"', '"b"', "1", "1.0", "true", '["a", "b"]', '{"a": 10}'],
                    simple_form=True,
                ),
            ),
            id="simple_choice:types",
        ),
        param(
            "choice(a,b)",
            CastResults(
                int=CastResults.error(
                    "ValueError while evaluating 'int(choice(a,b))': invalid literal for int() with base 10: 'a'"
                ),
                float=CastResults.error(
                    "ValueError while evaluating 'float(choice(a,b))': could not convert string to float: 'a'"
                ),
                str=ChoiceSweep(list=["a", "b"]),
                bool=CastResults.error(
                    "ValueError while evaluating 'bool(choice(a,b))': Cannot cast 'a' to bool"
                ),
                json_str=ChoiceSweep(list=['"a"', '"b"']),
            ),
            id="choice(a,b)",
        ),
        param(
            "choice(1,a)",
            CastResults(
                int=CastResults.error(
                    "ValueError while evaluating 'int(choice(1,a))': invalid literal for int() with base 10: 'a'"
                ),
                float=CastResults.error(
                    "ValueError while evaluating 'float(choice(1,a))': could not convert string to float: 'a'"
                ),
                str=ChoiceSweep(list=["1", "a"]),
                bool=CastResults.error(
                    "ValueError while evaluating 'bool(choice(1,a))': Cannot cast 'a' to bool"
                ),
                json_str=ChoiceSweep(list=["1", '"a"']),
            ),
            id="choice(1,a)",
        ),
        # interval
        param(
            "interval(1.0, 2.0)",
            CastResults(
                int=IntervalSweep(start=1, end=2),
                float=IntervalSweep(start=1.0, end=2.0),
                str=CastResults.error(
                    "ValueError while evaluating 'str(interval(1.0, 2.0))': Intervals cannot be cast to str"
                ),
                bool=CastResults.error(
                    "ValueError while evaluating 'bool(interval(1.0, 2.0))': Intervals cannot be cast to bool"
                ),
                json_str=CastResults.error(
                    "ValueError while evaluating 'json_str(interval(1.0, 2.0))': Intervals cannot be cast to json_str"
                ),
            ),
            id="interval(1.0, 2.0)",
        ),
        # range
        param(
            "range(1,10)",
            CastResults(
                int=RangeSweep(start=1, stop=10, step=1),
                float=RangeSweep(start=1.0, stop=10.0, step=1.0),
                str=CastResults.error(
                    "ValueError while evaluating 'str(range(1,10))': Range can only be cast to int or float"
                ),
                bool=CastResults.error(
                    "ValueError while evaluating 'bool(range(1,10))': Range can only be cast to int or float"
                ),
                json_str=CastResults.error(
                    "ValueError while evaluating 'json_str(range(1,10))': Range can only be cast to int or float"
                ),
            ),
            id="range(1,10)",
        ),
        param(
            "range(1.0,10.0)",
            CastResults(
                int=RangeSweep(start=1, stop=10, step=1),
                float=RangeSweep(start=1.0, stop=10.0, step=1.0),
                str=CastResults.error(
                    "ValueError while evaluating 'str(range(1.0,10.0))': Range can only be cast to int or float"
                ),
                bool=CastResults.error(
                    "ValueError while evaluating 'bool(range(1.0,10.0))': Range can only be cast to int or float"
                ),
                json_str=CastResults.error(
                    "ValueError while evaluating 'json_str(range(1.0,10.0))': Range can only be cast to int or float"
                ),
            ),
            id="range(1.0,10.0)",
        ),
    ],
)
def test_cast_conversions(value: Any, expected_value: Any) -> None:
    for field in ("int", "float", "bool", "str", "json_str"):
        cast_str = f"{field}({value})"
        expected = getattr(expected_value, field)
        warning = (
            warns(UserWarning, match=re.escape(JSON_STR_DEPRECATION_WARNING))
            if field == "json_str"
            else nullcontext()
        )
        with warning:
            if isinstance(expected, RaisesContext):
                with expected:
                    parser.parse_rule(cast_str, "function")
            else:
                result = parser.parse_rule(cast_str, "function")
                assert eq(result, expected), f"{field} cast result mismatch"


@mark.parametrize(
    "expression,expected",
    [
        param(
            "float(tag(log,shuffle(range(1,4))))",
            RangeSweep(tags={"log"}, start=1.0, stop=4.0, step=1.0, shuffle=True),
            id="float:cast:range",
        ),
        param(
            "int(tag(log,shuffle(range(1.0,4.0))))",
            RangeSweep(tags={"log"}, start=1, stop=4, step=1, shuffle=True),
            id="int:cast:range",
        ),
        param(
            "tag(log,shuffle(range(1,4)))",
            RangeSweep(tags={"log"}, start=1, stop=4, step=1, shuffle=True),
            id="range:no:cast",
        ),
        param(
            "str(tag(log,shuffle(choice(1,2,3))))",
            ChoiceSweep(tags={"log"}, list=["1", "2", "3"], shuffle=True),
            id="str:cast:choice",
        ),
        param(
            "float(tag(log,shuffle(choice(1.5,2,3))))",
            ChoiceSweep(tags={"log"}, list=[1.5, 2.0, 3.0], shuffle=True),
            id="float:cast:choice",
        ),
        param(
            "tag(log,shuffle(choice(1,2,3)))",
            ChoiceSweep(tags={"log"}, list=[1, 2, 3], shuffle=True),
            id="choice:no:cast",
        ),
        param(
            "bool(tag(log,shuffle(choice(1,0))))",
            ChoiceSweep(tags={"log"}, list=[True, False], shuffle=True),
            id="bool:cast:choice",
        ),
        param(
            "str(tag(log,shuffle(1,2,3)))",
            ChoiceSweep(
                tags={"log"}, list=["1", "2", "3"], simple_form=True, shuffle=True
            ),
            id="str:cast:simple:choice",
        ),
        param(
            "json_str(tag(log,shuffle(choice(1,2))))",
            ChoiceSweep(tags={"log"}, list=["1", "2"], shuffle=True),
            id="json_str:cast:choice",
        ),
    ],
)
def test_cast_preserves_sweep_metadata(expression: str, expected: Any) -> None:
    warning = (
        warns(UserWarning, match=re.escape(JSON_STR_DEPRECATION_WARNING))
        if expression.startswith("json_str")
        else nullcontext()
    )
    with warning:
        assert eq(parse_rule(expression, "function"), expected)


@mark.parametrize(
    "expression,expected_str_list",
    [
        param(
            "x=float(tag(log,shuffle(range(1,4))))",
            ["1.0", "2.0", "3.0"],
            id="float:cast:range:shuffled-iteration",
        ),
        param(
            "x=str(tag(log,shuffle(choice(1,2,3))))",
            ["1", "2", "3"],
            id="str:cast:choice:shuffled-iteration",
        ),
    ],
)
def test_cast_sweep_still_shuffles(
    expression: str, expected_str_list: List[str]
) -> None:
    ret = parser.parse_override(expression)
    actual = list(ret.sweep_string_iterator())
    assert sorted(expected_str_list) == sorted(actual)

    for _ in range(1, 10):
        actual = list(ret.sweep_string_iterator())
        if actual != expected_str_list:
            return
    assert False


@mark.parametrize(
    "value,expected_value",
    [
        param("abs(10)", 10, id="abs(10)"),
        param("abs(-10)", 10, id="abs(-10)"),
        param("mul(abs(-10),2)", 20, id="mul(abs(-10),2)"),
    ],
)
def test_function(value: Any, expected_value: Any) -> None:
    functions = Functions()
    functions.register(name="abs", func=abs)
    functions.register(name="mul", func=lambda n, m: n * m)
    ret = OverridesParser(functions).parse_rule(value, "function")
    assert ret == expected_value


class F:
    @staticmethod
    def foo1(value: int) -> str:
        return f"{type(value).__name__}:{str(value)}"

    @staticmethod
    def foo2(x: Union[int, str], y: Union[int, str]) -> str:
        return f"{type(x).__name__}:{str(x)},{type(y).__name__}:{str(y)}"

    @staticmethod
    def range(start: int, stop: int, step: int = 1) -> str:
        return f"res:range(start={start},stop={stop},step={step})"

    @staticmethod
    def empty() -> int:
        return 10

    @staticmethod
    def sum(*args: int) -> int:
        return sum(args, 0)

    @staticmethod
    def sort(*args: int, reverse: bool = False) -> List[int]:
        if reverse:
            return list(reversed(sorted(args)))
        else:
            return list(sorted(args))


@mark.parametrize(
    "func_name, func, value, expected",
    [
        param("foo_1", F.foo1, "foo_1(10)", "int:10", id="foo_1(10)"),
        param("foo_1", F.foo1, "foo_1(value=10)", "int:10", id="foo_1(value=10)"),
        param("foo_2", F.foo2, "foo_2('10',10)", "str:10,int:10", id="foo_2('10',10)"),
        param("empty", F.empty, "empty()", 10, id="empty()"),
        param("sum", F.sum, "sum()", 0, id="sum()"),
        param("sum", F.sum, "sum(1)", 1, id="sum(1)"),
        param("sum", F.sum, "sum(1,2,3)", 6, id="sum(1,2,3)"),
        param(
            "range",
            F.range,
            "range(10,20)",
            "res:range(start=10,stop=20,step=1)",
            id="range(10,20)",
        ),
        param(
            "range",
            F.range,
            "range(10,20,5)",
            "res:range(start=10,stop=20,step=5)",
            id="range(10,20,5)",
        ),
        param(
            "range",
            F.range,
            "range(10,20,step=5)",
            "res:range(start=10,stop=20,step=5)",
            id="range(10,20,step=5)",
        ),
        param(
            "range",
            F.range,
            "range(start=10,stop=20,step=5)",
            "res:range(start=10,stop=20,step=5)",
            id="range(start=10,stop=20,step=5)",
        ),
        param(
            "range",
            F.range,
            "range(step=5,start=10,stop=20)",
            "res:range(start=10,stop=20,step=5)",
            id="range(step=5,start=10,stop=20)",
        ),
        param(
            "range",
            F.range,
            "range(10,step=5,stop=20)",
            "res:range(start=10,stop=20,step=5)",
            id="range(10,step=5,stop=20)",
        ),
        param("sort", F.sort, "sort(10,1,5)", [1, 5, 10], id="sort(10,1,5)"),
        param(
            "sort",
            F.sort,
            "sort(10,1,5,reverse=true)",
            [10, 5, 1],
            id="sort(10,1,5,reverse=true)",
        ),
    ],
)
def test_eval(
    func_name: str, func: Callable[..., Any], value: str, expected: Any
) -> None:
    functions = Functions()
    functions.register(name=func_name, func=func)
    parser = OverridesParser(functions)
    assert parser.parse_rule(value, "function") == expected


@mark.parametrize(
    "func_name, func, value, expected",
    [
        param(
            "empty",
            F.empty,
            "empty(100)",
            raises(HydraException, match=re.escape("too many positional arguments")),
            id="empty(100)",
        ),
        param(
            "foo",
            F.foo1,
            "foo(true)",
            raises(
                HydraException,
                match=re.escape(
                    "TypeError while evaluating 'foo(true)':"
                    " mismatch type argument value: bool is incompatible with int"
                ),
            ),
            id="foo_1(true)",
        ),
        param(
            "foo",
            F.foo1,
            "foo(value=true)",
            raises(
                HydraException,
                match=re.escape(
                    "TypeError while evaluating 'foo(value=true)':"
                    " mismatch type argument value: bool is incompatible with int"
                ),
            ),
            id="foo_1(value:true)",
        ),
        param(
            "empty",
            F.foo1,
            "empty(no_such_name=10)",
            raises(
                HydraException,
                match=re.escape(
                    "TypeError while evaluating 'empty(no_such_name=10)': missing a required argument: 'value'"
                ),
            ),
            id="empty(no_such_name=10)",
        ),
        param(
            "empty",
            F.foo1,
            "empty(value=10,no_such_name=10)",
            raises(
                HydraException,
                match=re.escape(
                    "TypeError while evaluating 'empty(value=10,no_such_name=10)':"
                    " got an unexpected keyword argument 'no_such_name'"
                ),
            ),
            id="empty(value=10,no_such_name=10)",
        ),
        param(
            "sum",
            F.sum,
            "sum(true)",
            raises(
                HydraException,
                match=re.escape(
                    "TypeError while evaluating 'sum(true)':"
                    " mismatch type argument args[0]: bool is incompatible with int"
                ),
            ),
            id="sum(true)",
        ),
        param(
            "range",
            F.range,
            "range(start=10,20,1)",
            raises(
                HydraException,
                match=re.escape("positional argument follows keyword argument"),
            ),
            id="range(start=10,20,1)",
        ),
    ],
)
def test_eval_errors(
    func_name: str, func: Callable[..., Any], value: str, expected: Any
) -> None:
    functions = Functions()
    functions.register(name=func_name, func=func)
    parser = OverridesParser(functions)
    with expected:
        parser.parse_rule(value, "function")


@mark.parametrize(
    "value,expected",
    [
        param("glob(*)", Glob(include=["*"], exclude=[])),
        param("glob(include=*)", Glob(include=["*"], exclude=[])),
        param("glob(include=[*])", Glob(include=["*"], exclude=[])),
        param(
            "glob(include=[a*, b*], exclude=c*)",
            Glob(include=["a*", "b*"], exclude=["c*"]),
        ),
    ],
)
def test_glob(value: str, expected: Any) -> None:
    ret = parse_rule(value, "function")
    assert ret == expected


@mark.parametrize(
    "include,exclude,expected",
    [
        param(
            ["*"],
            [],
            ["the", "quick", "brown", "fox", "jumped", "under", "the", "lazy", "dog"],
            id="include=*",
        ),
        param(
            ["*"],
            ["quick", "under"],
            ["the", "brown", "fox", "jumped", "the", "lazy", "dog"],
            id="include=*, exclude=[quick,under]]",
        ),
        param(["*"], ["*d*"], ["the", "quick", "brown", "fox", "the", "lazy"], id="=*"),
        param(["t*"], [], ["the", "the"], id="=*"),
    ],
)
def test_glob_filter(
    include: List[str], exclude: List[str], expected: List[str]
) -> None:
    strings = ["the", "quick", "brown", "fox", "jumped", "under", "the", "lazy", "dog"]
    assert Glob(include=include, exclude=exclude).filter(strings) == expected


@mark.parametrize(
    "value,expected_key,expected_value,expected_value_type",
    [
        param(
            "key= \tvalue \t", "key", "value", ValueType.ELEMENT, id="leading+trailing"
        ),
        param(
            "key=value \t 123",
            "key",
            "value \t 123",
            ValueType.ELEMENT,
            id="inside_primitive",
        ),
        param(
            "key='  foo,bar\t'",
            "key",
            QuotedString(text="  foo,bar\t", quote=Quote.single),
            ValueType.ELEMENT,
            id="inside_quoted_value_outer",
        ),
        param(
            "key='foo , \t\t bar'",
            "key",
            QuotedString(text="foo , \t\t bar", quote=Quote.single),
            ValueType.ELEMENT,
            id="inside_quoted_value_inter",
        ),
        param(
            "key=1 ,  2,\t\t3",
            "key",
            ChoiceSweep(list=[1, 2, 3], simple_form=True),
            ValueType.SIMPLE_CHOICE_SWEEP,
            id="around_commas",
        ),
        param(
            "key=choice\t(  1\t\t )",
            "key",
            ChoiceSweep(list=[1]),
            ValueType.CHOICE_SWEEP,
            id="function_one_arg",
        ),
        param(
            "key=choice(\t\t1,   2, \t 3 )",
            "key",
            ChoiceSweep(list=[1, 2, 3]),
            ValueType.CHOICE_SWEEP,
            id="function_many_args",
        ),
        param(
            "key=[1  ,\t2\t],[\t3\t   ,4  ]",
            "key",
            ChoiceSweep(list=[[1, 2], [3, 4]], simple_form=True),
            ValueType.SIMPLE_CHOICE_SWEEP,
            id="in_lists",
        ),
        param(
            "key=str(\t  [  1,\t2  ]\t   )",
            "key",
            ["1", "2"],
            ValueType.ELEMENT,
            id="mixed",
        ),
    ],
)
def test_whitespaces(
    value: str, expected_key: str, expected_value: Any, expected_value_type: ValueType
) -> None:
    ret = parse_rule(value, "override")
    expected = Override(
        input_line=value,
        type=OverrideType.CHANGE,
        key_or_group=expected_key,
        _value=expected_value,
        value_type=expected_value_type,
    )
    assert ret == expected


@mark.parametrize(
    "value, expected_sweep_string_list, expected_sweep_encoded_list",
    [
        ("x=choice(1,2,3)", ["1", "2", "3"], [1, 2, 3]),
        ("x=choice('1', '2', '3')", ["1", "2", "3"], ["1", "2", "3"]),
        ("x=choice('a', 'b')", ["a", "b"], ["a", "b"]),
        (
            "x=choice(True, 'True', False, 'False', 'a', 1, 1.1, 2.0, 3, '1.5', '4')",
            ["True", "True", "False", "False", "a", "1", "1.1", "2.0", "3", "1.5", "4"],
            [True, "True", False, "False", "a", 1, 1.1, 2.0, 3, "1.5", "4"],
        ),
        (
            "x=range(1, 10)",
            ["1", "2", "3", "4", "5", "6", "7", "8", "9"],
            [1, 2, 3, 4, 5, 6, 7, 8, 9],
        ),
        (
            "x=choice([1,2,3], ['a', 'b'])",
            ["[1,2,3]", "['a','b']"],
            ["[1,2,3]", "['a','b']"],
        ),
        (
            "x=choice([1, 1.1, '2', 'a'], [True, False])",
            ["[1,1.1,'2','a']", "[True,False]"],
            ["[1,1.1,'2','a']", "[True,False]"],
        ),
    ],
)
def test_sweep_iterators(
    value: str,
    expected_sweep_string_list: List[str],
    expected_sweep_encoded_list: List[Any],
) -> None:
    ret = parser.parse_override(value)
    actual_sweep_string_list = [x for x in ret.sweep_string_iterator()]
    actual_sweep_encoded_list = [
        x for x in ret.sweep_iterator(transformer=Transformer.encode)
    ]
    assert actual_sweep_string_list == expected_sweep_string_list
    assert actual_sweep_encoded_list == expected_sweep_encoded_list


@mark.parametrize(
    ("s", "expected"),
    [
        param("abc", "abc", id="no_esc"),
        param("\\", "\\\\", id="esc_backslash"),
        param("\\\\\\", "\\\\\\\\\\\\", id="esc_backslash_x3"),
        param("()", "\\(\\)", id="esc_parentheses"),
        param("[]", "\\[\\]", id="esc_brackets"),
        param("{}", "\\{\\}", id="esc_braces"),
        param(":=,", "\\:\\=\\,", id="esc_symbols"),
        param("  \t", "\\ \\ \\\t", id="esc_ws"),
        param(
            "ab\\(cd{ef}[gh]): ij,kl\t",
            "ab\\\\\\(cd\\{ef\\}\\[gh\\]\\)\\:\\ ij\\,kl\\\t",
            id="esc_mixed",
        ),
    ],
)
def test_escape_special_characters(s: str, expected: str) -> None:
    escaped = escape_special_characters(s)
    assert escaped == expected

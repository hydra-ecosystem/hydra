# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved
import os
from os.path import realpath

from pytest import mark

from hydra._internal.config_search_path_impl import ConfigSearchPathImpl
from hydra._internal.utils import compute_search_path_dir
from hydra.core.config_search_path import SearchPathElement, SearchPathQuery


def create_search_path(base_list: list[tuple[str, str]]) -> ConfigSearchPathImpl:
    csp = ConfigSearchPathImpl()
    csp.config_search_path = [SearchPathElement(x[0], x[1]) for x in base_list]
    return csp


def to_tuples_list(
    search_path: ConfigSearchPathImpl,
) -> list[tuple[str | None, str | None]]:
    return [(x.provider, x.path) for x in search_path.config_search_path]


@mark.parametrize(
    "input_list, reference, expected_idx",
    [
        ([], ("", ""), -1),
        ([("a", "10")], ("a", None), 0),
        ([("a", "10"), ("b", "20"), ("a", "30")], ("a", None), 2),
        ([("a", "10"), ("b", "20"), ("a", "30")], ("b", None), 1),
        ([("a", "10"), ("b", "20"), ("a", "30")], ("a", "10"), 0),
    ],
)
def test_find_last_match(
    input_list: list[tuple[str, str]], reference: str, expected_idx: int
) -> None:
    csp = create_search_path(input_list)
    assert (
        csp.find_last_match(SearchPathQuery(reference[0], reference[1])) == expected_idx
    )


@mark.parametrize(
    "input_list, reference, expected_idx",
    [
        ([], ("", ""), -1),
        ([("a", "10")], ("a", None), 0),
        ([("a", "10"), ("b", "20"), ("a", "30")], ("a", None), 0),
        ([("a", "10"), ("b", "20"), ("a", "30")], ("b", None), 1),
        ([("a", "10"), ("b", "20"), ("a", "30")], ("a", "10"), 0),
    ],
)
def test_find_first_match(
    input_list: list[tuple[str, str]], reference: str, expected_idx: int
) -> None:
    csp = create_search_path(input_list)
    sp = SearchPathQuery(reference[0], reference[1])
    assert csp.find_first_match(sp) == expected_idx


@mark.parametrize(
    "base_list, provider, path, anchor_provider, result_list",
    [
        # appending to an empty list
        ([], "foo", "/path", None, [("foo", "/path")]),
        # appending to a non empty list
        ([("f1", "/p1")], "f2", "/p2", None, [("f1", "/p1"), ("f2", "/p2")]),
        # appending after an anchor at key 0
        (
            [("f1", "A"), ("f2", "B")],
            "f3",
            "B",
            SearchPathQuery(None, "A"),
            [("f1", "A"), ("f3", "B"), ("f2", "B")],
        ),
        # appending after an anchor at the end of the list
        (
            [("f1", "A"), ("f2", "B")],
            "f3",
            "B",
            SearchPathQuery(None, "B"),
            [("f1", "A"), ("f2", "B"), ("f3", "B")],
        ),
        # appending after a non existent anchor
        (
            [],
            "new_provider",
            "/path",
            "unregister_provider",
            [("new_provider", "/path")],
        ),
    ],
)
def test_append(
    base_list: list[tuple[str, str]],
    provider: str,
    path: str,
    anchor_provider: SearchPathQuery,
    result_list: list[tuple[str, str]],
) -> None:
    csp = create_search_path(base_list)
    csp.append(provider=provider, path=path, anchor=anchor_provider)
    assert to_tuples_list(csp) == result_list


@mark.parametrize(
    "base_list, provider, path, anchor_provider, result_list",
    [
        # prepending to an empty list
        ([], "foo", "/path", None, [("foo", "/path")]),
        # prepending to a full list
        (
            [("foo", "/path")],
            "foo2",
            "/path2",
            None,
            [("foo2", "/path2"), ("foo", "/path")],
        ),
        # prepending in front of an anchor at key 0
        (
            [("foo", "/path")],
            "foo2",
            "/path2",
            SearchPathQuery("foo", "/path"),
            [("foo2", "/path2"), ("foo", "/path")],
        ),
        # prepending in front of an anchor at key 1
        (
            [("foo", "/path"), ("foo2", "/path2")],
            "foo3",
            "/path3",
            SearchPathQuery("foo2", "/path2"),
            [("foo", "/path"), ("foo3", "/path3"), ("foo2", "/path2")],
        ),
        # prepending in front of a none existing anchor results in prepending to the head of the list
        ([], "foo2", "/path2", "does not exist", [("foo2", "/path2")]),
    ],
)
def test_prepend(
    base_list: list[tuple[str, str]],
    provider: str,
    path: str,
    anchor_provider: SearchPathQuery,
    result_list: list[tuple[str, str]],
) -> None:
    csp = create_search_path(base_list)
    csp.prepend(provider=provider, path=path, anchor=anchor_provider)
    assert to_tuples_list(csp) == result_list


@mark.parametrize(
    "calling_file, calling_module, config_path, expected",
    [
        ("foo.py", None, None, None),
        ("foo/bar.py", None, None, None),
        ("foo/bar.py", None, "conf", realpath("foo/conf")),
        ("foo/bar.py", None, "../conf", realpath("conf")),
        ("foo/bar.py", None, realpath("conf"), realpath("conf")),
        ("c:/foo/bar.py", None, "conf", realpath("c:/foo/conf")),
        ("c:/foo/bar.py", None, "../conf", realpath("c:/conf")),
        (None, "module", None, "pkg://"),
        (None, "package.module", None, "pkg://package"),
        (None, "package.module", "conf", "pkg://package/conf"),
        # This is an unusual one. this behavior is intentional.
        (None, "package.module", "../conf", "pkg://conf"),
        (None, "package1.rename_package_to.module", "../conf", "pkg://package1/conf"),
        # prefer directory
        (
            "foo",
            "package1.rename_package_to.module",
            "../conf",
            realpath(os.path.join(os.getcwd(), "../conf")),
        ),
        (None, "package.module", "pkg://some/conf", "pkg://some/conf"),
    ],
)
def test_compute_search_path_dir(
    calling_file: str, calling_module: str, config_path: str, expected: str
) -> None:
    res = compute_search_path_dir(calling_file, calling_module, config_path)
    assert res == expected

# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved
import re
from textwrap import dedent
from typing import Any, List, Optional

from pytest import mark, param, raises

from hydra._internal.defaults_list import (
    _validate_paths,
    _validate_self,
    create_defaults_list,
)
from hydra.core.default_element import (
    ConfigDefault,
    GroupDefault,
    InputDefault,
    ResultDefault,
)
from hydra.core.override_parser.overrides_parser import OverridesParser
from hydra.core.plugins import Plugins
from hydra.errors import ConfigCompositionException
from hydra.test_utils.test_utils import chdir_hydra_root
from tests.defaults_list import create_repo

chdir_hydra_root()

# registers config source plugins
Plugins.instance()


def test_missing_self_is_appended_without_warning(recwarn: Any) -> None:
    default = GroupDefault(group="group1", value="file1")
    defaults: List[InputDefault] = [default]

    assert _validate_self(
        containing_node=ConfigDefault(path="config", primary=True),
        defaults=defaults,
    )
    assert defaults == [default, ConfigDefault(path="_self_")]
    assert len(recwarn) == 0


@mark.parametrize(
    "config_path,expected_list",
    [
        param("empty", [], id="empty"),
        param(
            "group_default",
            [GroupDefault(group="group1", value="file1")],
            id="one_item",
        ),
        param(
            "self_leading",
            [
                ConfigDefault(path="_self_"),
                GroupDefault(group="group1", value="file1"),
            ],
            id="self_leading",
        ),
        param(
            "self_trailing",
            [
                GroupDefault(group="group1", value="file1"),
                ConfigDefault(path="_self_"),
            ],
            id="self_trailing",
        ),
        param(
            "optional",
            [GroupDefault(group="group1", value="file1", optional=True)],
            id="optional",
        ),
        param(
            "keyword_whitespace",
            [
                GroupDefault(group="group1", value="file1", optional=True),
                GroupDefault(group="group2", value="file2", override=True),
            ],
            id="keyword_whitespace",
        ),
        param(
            "config_default",
            [ConfigDefault(path="empty")],
            id="non_config_group_default",
        ),
    ],
)
def test_loaded_defaults_list(
    config_path: str, expected_list: List[InputDefault]
) -> None:
    repo = create_repo()
    result = repo.load_config(config_path=config_path)
    assert result is not None
    assert result.defaults_list == expected_list


def test_unknown_keyword_in_defaults_list() -> None:
    repo = create_repo()
    with raises(
        ValueError,
        match=re.escape(
            "In unknown_keyword: Unsupported keyword 'optioal' in defaults list"
        ),
    ):
        repo.load_config(config_path="unknown_keyword")


@mark.parametrize(
    "config_path", ["conflicting_keywords", "conflicting_keywords_reversed"]
)
def test_conflicting_keywords_in_defaults_list(config_path: str) -> None:
    repo = create_repo()
    with raises(
        ValueError,
        match=re.escape(
            f"In {config_path}: 'optional' and 'override' keywords "
            "cannot be combined in defaults list"
        ),
    ):
        repo.load_config(config_path=config_path)


@mark.parametrize("config_name", ["empty_group", "whitespace_group"])
def test_missing_group_name_in_defaults_list(config_name: str) -> None:
    repo = create_repo()
    with raises(
        ValueError,
        match=re.escape(f"In {config_name}: Missing group name in defaults list"),
    ):
        repo.load_config(config_path=config_name)


@mark.parametrize(
    "config_path,expected_list",
    [
        param(
            "optional_deprecated",
            [GroupDefault(group="group1", value="file1", optional=True)],
            id="optional",
        ),
    ],
)
class TestRemovedOptionalSyntax:
    def test_rejected(
        self,
        config_path: str,
        expected_list: List[InputDefault],
        hydra_restore_singletons: Any,
    ) -> None:
        repo = create_repo()
        err = "In optional_deprecated: Too many keys in default item {'group1': 'file1', 'optional': True}"
        with raises(
            ValueError,
            match=re.escape(err),
        ):
            repo.load_config(config_path=config_path)


def _test_defaults_list_impl(
    config_name: Optional[str],
    overrides: List[str],
    expected: Any,
    prepend_hydra: bool = False,
    skip_missing: bool = False,
) -> None:
    parser = OverridesParser.create()
    repo = create_repo()
    overrides_list = parser.parse_overrides(overrides=overrides)
    if isinstance(expected, list) or expected is None:
        result = create_defaults_list(
            repo=repo,
            config_name=config_name,
            overrides_list=overrides_list,
            prepend_hydra=prepend_hydra,
            skip_missing=skip_missing,
        )
        assert result.defaults == expected
    else:
        with expected:
            create_defaults_list(
                repo=repo,
                config_name=config_name,
                overrides_list=overrides_list,
                prepend_hydra=prepend_hydra,
                skip_missing=skip_missing,
            )


@mark.parametrize(
    "default,expected_group_path,expected_config_path",
    [
        param(
            ConfigDefault(path="bar", parent_base_dir=""),
            "",
            "bar",
            id="config_default:empty_basedir",
        ),
        param(
            ConfigDefault(path="bar", parent_base_dir="foo"),
            "foo",
            "foo/bar",
            id="config_default:with_parent_basedir",
        ),
        param(
            GroupDefault(group="foo", value="bar", parent_base_dir=""),
            "foo",
            "foo/bar",
            id="group_default:empty_basedir",
        ),
        param(
            GroupDefault(group="foo", value="bar", parent_base_dir="zoo"),
            "zoo/foo",
            "zoo/foo/bar",
            id="group_default:with_parent_basedir",
        ),
        # absolute group
        param(
            ConfigDefault(path="/foo/zoo", parent_base_dir="irrelevant"),
            "foo",
            "foo/zoo",
            id="config_default:absolute",
        ),
        param(
            GroupDefault(group="/foo", value="zoo", parent_base_dir="irrelevant"),
            "foo",
            "foo/zoo",
            id="group_default:absolute",
        ),
    ],
)
def test_get_paths(
    default: InputDefault, expected_group_path: Any, expected_config_path: Any
) -> None:
    assert default.get_group_path() == expected_group_path
    assert default.get_config_path() == expected_config_path


@mark.parametrize(
    "default,expected",
    [
        param(
            ConfigDefault(path="bar", parent_base_dir=""),
            "",
            id="config_default",
        ),
        param(
            ConfigDefault(path="foo/bar", parent_base_dir=""),
            "foo",
            id="config_default",
        ),
        param(
            ConfigDefault(path="bar", parent_base_dir="foo"),
            "foo",
            id="config_default",
        ),
        param(
            ConfigDefault(path="bar", parent_base_dir="a/b"),
            "a.b",
            id="config_default",
        ),
        param(
            GroupDefault(group="a", value="a1", parent_base_dir=""),
            "a",
            id="group_default",
        ),
        param(
            GroupDefault(group="a/b", value="a1", parent_base_dir=""),
            "a.b",
            id="group_default",
        ),
        param(
            GroupDefault(group="a/b", value="a1", parent_base_dir="x"),
            "x.a.b",
            id="group_default",
        ),
        # absolute group/path
        param(
            ConfigDefault(path="/foo/bar", parent_base_dir="irrelevant"),
            "foo",
            id="config_default:absolute",
        ),
        param(
            GroupDefault(group="/foo", value="bar", parent_base_dir="irrelevant"),
            "foo",
            id="group_default:absolute",
        ),
    ],
)
def test_get_default_package(default: InputDefault, expected: Any) -> None:
    assert default.get_default_package() == expected


@mark.parametrize(
    "default,parent_package, parent_base_dir, expected",
    [
        # empty parent package
        param(
            ConfigDefault(path="bar"),
            "",
            "",
            "",
            id="config_default:path=bar,parent_package=,package=",
        ),
        param(
            ConfigDefault(path="group1/bar"),
            "",
            "",
            "group1",
            id="config_default:path=group1/bar,parent_package=, package=",
        ),
        param(
            ConfigDefault(path="bar", package="pkg1"),
            "",
            "",
            "pkg1",
            id="config_default:path=bar,parent_package=, package=pkg1",
        ),
        param(
            ConfigDefault(path="group1/bar", package="pkg1"),
            "",
            "",
            "pkg1",
            id="config_default:path=group1/bar,parent_package=,package=pkg1",
        ),
        # non empty parent package
        param(
            ConfigDefault(path="bar", package="pkg1"),
            "a",
            "",
            "a.pkg1",
            id="config_default:path=bar,parent_package=a, package=pkg1",
        ),
        # global package
        param(
            ConfigDefault(
                path="bar",
                package="_global_.pkg1",
            ),
            "",
            "",
            "pkg1",
            id="config_default:parent_package=a, package=_global_.pkg1",
        ),
        # global parent package
        param(
            ConfigDefault(path="bar", package="pkg1"),
            "_global_.foo",
            "",
            "foo.pkg1",
            id="config_default:parent_package=_global_.foo, package=pkg1",
        ),
        # both globals
        param(
            ConfigDefault(path="bar", package="_global_.pkg1"),
            "_global_.foo",
            "",
            "pkg1",
            id="config_default:parent_package=_global_.foo, package=_global_.pkg1",
        ),
        # _group_
        param(
            GroupDefault(group="foo", value="bar", package="_group_"),
            "",
            "",
            "_group_",
            id="group_default:parent_package=, package=_group_",
        ),
        param(
            ConfigDefault(path="foo/bar", package="_group_"),
            "",
            "",
            "_group_",
            id="config_default:parent_package=, package=_group_",
        ),
        param(
            GroupDefault(group="foo", value="bar", package="_group_.zoo"),
            "",
            "",
            "_group_.zoo",
            id="group_default:parent_package=, package=_group_.zoo",
        ),
        param(
            ConfigDefault(
                path="foo/bar",
                package="_group_.zoo",
            ),
            "",
            "",
            "_group_.zoo",
            id="config_default:parent_package=, package=_group_.zoo",
        ),
    ],
)
def test_get_final_package(
    default: InputDefault, parent_package: str, parent_base_dir: str, expected: Any
) -> None:
    default.update_parent(
        parent_base_dir=parent_base_dir, parent_package=parent_package
    )
    assert default.get_final_package() == expected


@mark.parametrize(
    "config_name, overrides, expected",
    [
        param(
            "empty",
            [],
            [ResultDefault(config_path="empty", package="")],
            id="empty",
        ),
        param(
            "config_default",
            [],
            [
                ResultDefault(config_path="empty", package="", parent="config_default"),
                ResultDefault(config_path="config_default", package="", is_self=True),
            ],
            id="config_default",
        ),
        param(
            "group_default",
            [],
            [
                ResultDefault(
                    config_path="group1/file1", package="group1", parent="group_default"
                ),
                ResultDefault(config_path="group_default", package="", is_self=True),
            ],
            id="group_default",
        ),
        param(
            "self_leading",
            [],
            [
                ResultDefault(config_path="self_leading", package="", is_self=True),
                ResultDefault(
                    config_path="group1/file1", package="group1", parent="self_leading"
                ),
            ],
            id="self_leading",
        ),
        param(
            "self_trailing",
            [],
            [
                ResultDefault(
                    config_path="group1/file1", package="group1", parent="self_trailing"
                ),
                ResultDefault(config_path="self_trailing", package="", is_self=True),
            ],
            id="self_trailing",
        ),
        param(
            "include_nested_group",
            [],
            [
                ResultDefault(
                    config_path="group1/group2/file1",
                    package="group1.group2",
                    parent="group1/group_item1",
                ),
                ResultDefault(
                    config_path="group1/group_item1",
                    parent="include_nested_group",
                    package="group1",
                    is_self=True,
                ),
                ResultDefault(
                    config_path="include_nested_group", package="", is_self=True
                ),
            ],
            id="include_nested_group",
        ),
    ],
)
def test_simple_defaults_list_cases(
    config_name: str, overrides: List[str], expected: List[ResultDefault]
) -> None:
    _test_defaults_list_impl(
        config_name=config_name, overrides=overrides, expected=expected
    )


@mark.parametrize(
    "config_name, overrides, expected",
    [
        param(
            "config_default_pkg1",
            [],
            [
                ResultDefault(
                    config_path="empty", package="pkg1", parent="config_default_pkg1"
                ),
                ResultDefault(
                    config_path="config_default_pkg1", package="", is_self=True
                ),
            ],
            id="config_default_pkg1",
        ),
        param(
            "include_nested_config_item_pkg2",
            [],
            [
                ResultDefault(
                    config_path="group1/group2/file1",
                    package="group1.pkg2",
                    parent="group1/config_item_pkg2",
                ),
                ResultDefault(
                    config_path="group1/config_item_pkg2",
                    parent="include_nested_config_item_pkg2",
                    package="group1",
                    is_self=True,
                ),
                ResultDefault(
                    config_path="include_nested_config_item_pkg2",
                    package="",
                    is_self=True,
                ),
            ],
            id="include_nested_config_item_pkg2",
        ),
        param(
            "include_nested_config_item_global",
            [],
            [
                ResultDefault(
                    config_path="group1/group2/file1",
                    package="",
                    parent="group1/config_item_global_",
                ),
                ResultDefault(
                    config_path="group1/config_item_global_",
                    parent="include_nested_config_item_global",
                    package="group1",
                    is_self=True,
                ),
                ResultDefault(
                    config_path="include_nested_config_item_global",
                    package="",
                    is_self=True,
                ),
            ],
            id="include_nested_config_item_global",
        ),
    ],
)
def test_override_package_in_defaults_list(
    config_name: str, overrides: List[str], expected: List[ResultDefault]
) -> None:
    _test_defaults_list_impl(
        config_name=config_name, overrides=overrides, expected=expected
    )


@mark.parametrize(
    "config_name, overrides, expected",
    [
        param(
            "include_nested_group_pkg2",
            [],
            [
                ResultDefault(
                    config_path="group1/group2/file1",
                    package="group1.pkg2",
                    parent="group1/group_item1_pkg2",
                ),
                ResultDefault(
                    config_path="group1/group_item1_pkg2",
                    parent="include_nested_group_pkg2",
                    package="group1",
                    is_self=True,
                ),
                ResultDefault(
                    config_path="include_nested_group_pkg2", package="", is_self=True
                ),
            ],
            id="include_nested_group_pkg2",
        ),
        param(
            "include_nested_group_pkg2",
            ["group1/group2@group1.pkg2=file2"],
            [
                ResultDefault(
                    config_path="group1/group2/file2",
                    package="group1.pkg2",
                    parent="group1/group_item1_pkg2",
                ),
                ResultDefault(
                    config_path="group1/group_item1_pkg2",
                    parent="include_nested_group_pkg2",
                    package="group1",
                    is_self=True,
                ),
                ResultDefault(
                    config_path="include_nested_group_pkg2", package="", is_self=True
                ),
            ],
            id="option_override:include_nested_group_pkg2",
        ),
    ],
)
def test_include_nested_group_pkg2(
    config_name: str, overrides: List[str], expected: List[ResultDefault]
) -> None:
    _test_defaults_list_impl(
        config_name=config_name, overrides=overrides, expected=expected
    )


@mark.parametrize(
    "config_name, overrides, expected",
    [
        param(
            "group_default_pkg1",
            [],
            [
                ResultDefault(
                    config_path="group1/file1",
                    package="pkg1",
                    parent="group_default_pkg1",
                ),
                ResultDefault(
                    config_path="group_default_pkg1", package="", is_self=True
                ),
            ],
            id="group_default_pkg1",
        ),
        param(
            "group_default_pkg1",
            ["group1@pkg1=file2"],
            [
                ResultDefault(
                    config_path="group1/file2",
                    package="pkg1",
                    parent="group_default_pkg1",
                ),
                ResultDefault(
                    config_path="group_default_pkg1", package="", is_self=True
                ),
            ],
            id="option_override:group_default_pkg1",
        ),
        param(
            "group_default_pkg1",
            ["group1@wrong=file2"],
            raises(
                ConfigCompositionException,
                match=re.escape(
                    dedent("""\
                        Could not override 'group1@wrong'.
                        Did you mean to override group1@pkg1?
                        To append to your default list use +group1@wrong=file2""")
                ),
            ),
            id="option_override:group_default_pkg1:bad_package_in_override",
        ),
    ],
)
def test_group_default_pkg1(
    config_name: str, overrides: List[str], expected: List[ResultDefault]
) -> None:
    _test_defaults_list_impl(
        config_name=config_name, overrides=overrides, expected=expected
    )


@mark.parametrize(
    "config_name, overrides, expected",
    [
        param(
            "include_nested_group_global_",
            [],
            [
                ResultDefault(
                    config_path="group1/group2/file1",
                    package="",
                    parent="group1/group_item1_global_",
                ),
                ResultDefault(
                    config_path="group1/group_item1_global_",
                    parent="include_nested_group_global_",
                    package="group1",
                    is_self=True,
                ),
                ResultDefault(
                    config_path="include_nested_group_global_",
                    package="",
                    is_self=True,
                ),
            ],
            id="include_nested_config_item_global",
        ),
        param(
            "include_nested_group_global_",
            ["group1/group2@_global_=file2"],
            [
                ResultDefault(
                    config_path="group1/group2/file2",
                    package="",
                    parent="group1/group_item1_global_",
                ),
                ResultDefault(
                    config_path="group1/group_item1_global_",
                    parent="include_nested_group_global_",
                    package="group1",
                    is_self=True,
                ),
                ResultDefault(
                    config_path="include_nested_group_global_",
                    package="",
                    is_self=True,
                ),
            ],
            id="option_override:include_nested_config_item_global",
        ),
    ],
)
def test_include_nested_group_global(
    config_name: str, overrides: List[str], expected: List[ResultDefault]
) -> None:
    _test_defaults_list_impl(
        config_name=config_name, overrides=overrides, expected=expected
    )


@mark.parametrize(
    "config_name, overrides, expected",
    [
        param(
            "group_default_at_global",
            [],
            [
                ResultDefault(
                    config_path="group1/file1",
                    package="",
                    parent="group_default_at_global",
                ),
                ResultDefault(
                    config_path="group_default_at_global",
                    package="",
                    is_self=True,
                ),
            ],
            id="group_default_at_global",
        ),
        param(
            "group_default_at_global",
            ["+experiment=override_with_global_default2"],
            [
                ResultDefault(
                    config_path="group1/file2",
                    package="",
                    parent="group_default_at_global",
                ),
                ResultDefault(
                    config_path="group_default_at_global",
                    package="",
                    is_self=True,
                ),
                ResultDefault(
                    config_path="experiment/override_with_global_default2",
                    package="experiment",
                    parent="group_default_at_global",
                ),
            ],
            id="group_default_at_global:include_experiment_to_override_toplevel_package",
        ),
        param(
            "two_group_defaults_different_pkgs_global",
            [],
            [
                ResultDefault(
                    config_path="group1/file1",
                    parent="two_group_defaults_different_pkgs_global",
                    package="group1",
                ),
                ResultDefault(
                    config_path="group1/file2",
                    parent="two_group_defaults_different_pkgs_global",
                    package="",
                ),
                ResultDefault(
                    config_path="two_group_defaults_different_pkgs_global",
                    package="",
                    is_self=True,
                ),
            ],
            id="two_group_defaults_different_pkgs_global",
        ),
    ],
)
def test_group_global(
    config_name: str, overrides: List[str], expected: List[ResultDefault]
) -> None:
    _test_defaults_list_impl(
        config_name=config_name, overrides=overrides, expected=expected
    )


@mark.parametrize(
    "config_name, overrides, expected",
    [
        param(
            "include_nested_group_global_foo",
            [],
            [
                ResultDefault(
                    config_path="group1/group2/file1",
                    package="foo",
                    parent="group1/group_item1_global_foo",
                ),
                ResultDefault(
                    config_path="group1/group_item1_global_foo",
                    parent="include_nested_group_global_foo",
                    package="group1",
                    is_self=True,
                ),
                ResultDefault(
                    config_path="include_nested_group_global_foo",
                    package="",
                    is_self=True,
                ),
            ],
            id="include_nested_group_global_foo",
        ),
        param(
            "include_nested_group_global_foo",
            ["group1/group2@foo=file2"],
            [
                ResultDefault(
                    config_path="group1/group2/file2",
                    package="foo",
                    parent="group1/group_item1_global_foo",
                ),
                ResultDefault(
                    config_path="group1/group_item1_global_foo",
                    parent="include_nested_group_global_foo",
                    package="group1",
                    is_self=True,
                ),
                ResultDefault(
                    config_path="include_nested_group_global_foo",
                    package="",
                    is_self=True,
                ),
            ],
            id="include_nested_group_global_foo",
        ),
    ],
)
def test_include_nested_group_global_foo(
    config_name: str, overrides: List[str], expected: List[ResultDefault]
) -> None:
    _test_defaults_list_impl(
        config_name=config_name, overrides=overrides, expected=expected
    )


@mark.parametrize(
    "config_name, overrides, expected",
    [
        param(
            "include_nested_group_name_",
            [],
            [
                ResultDefault(
                    config_path="group1/group2/file1",
                    package="group1._name_",
                    parent="group1/group_item1_name_",
                ),
                ResultDefault(
                    config_path="group1/group_item1_name_",
                    parent="include_nested_group_name_",
                    package="group1",
                    is_self=True,
                ),
                ResultDefault(
                    config_path="include_nested_group_name_",
                    package="",
                    is_self=True,
                ),
            ],
            id="include_nested_group_name_",
        ),
        param(
            "include_nested_group_name_",
            ["group1/group2@group1._name_=file2"],
            [
                ResultDefault(
                    config_path="group1/group2/file2",
                    package="group1._name_",
                    parent="group1/group_item1_name_",
                ),
                ResultDefault(
                    config_path="group1/group_item1_name_",
                    parent="include_nested_group_name_",
                    package="group1",
                    is_self=True,
                ),
                ResultDefault(
                    config_path="include_nested_group_name_",
                    package="",
                    is_self=True,
                ),
            ],
            id="include_nested_group_name_",
        ),
        param(
            "include_nested_config_item_name_",
            [],
            [
                ResultDefault(
                    config_path="group1/group2/file1",
                    package="group1._name_",
                    parent="group1/config_item_name_",
                ),
                ResultDefault(
                    config_path="group1/config_item_name_",
                    package="group1",
                    parent="include_nested_config_item_name_",
                    is_self=True,
                ),
                ResultDefault(
                    config_path="include_nested_config_item_name_",
                    package="",
                    is_self=True,
                    primary=True,
                ),
            ],
            id="include_nested_config_item_name_",
        ),
    ],
)
def test_include_nested_group_name_(
    config_name: str,
    overrides: List[str],
    expected: List[ResultDefault],
) -> None:
    _test_defaults_list_impl(
        config_name=config_name, overrides=overrides, expected=expected
    )


@mark.parametrize(
    "config_name, overrides, expected",
    [
        param(
            "primary_pkg_header_foo",
            [],
            [
                ResultDefault(
                    config_path="group1/file1",
                    package="foo.group1",
                    parent="primary_pkg_header_foo",
                ),
                ResultDefault(
                    config_path="group1/file1",
                    package="foo.pkg",
                    parent="primary_pkg_header_foo",
                ),
                ResultDefault(
                    config_path="primary_pkg_header_foo",
                    package="foo",
                    is_self=True,
                ),
            ],
            id="primary_pkg_header_foo",
        ),
        param(
            "primary_pkg_header_foo",
            ["group1@foo.group1=file2", "group1@foo.pkg=file3"],
            [
                ResultDefault(
                    config_path="group1/file2",
                    package="foo.group1",
                    parent="primary_pkg_header_foo",
                ),
                ResultDefault(
                    config_path="group1/file3",
                    package="foo.pkg",
                    parent="primary_pkg_header_foo",
                ),
                ResultDefault(
                    config_path="primary_pkg_header_foo",
                    package="foo",
                    is_self=True,
                ),
            ],
            id="primary_pkg_header_foo",
        ),
    ],
)
def test_primary_cfg_pkg_header_foo(
    config_name: str, overrides: List[str], expected: List[ResultDefault]
) -> None:
    _test_defaults_list_impl(
        config_name=config_name, overrides=overrides, expected=expected
    )


@mark.parametrize(
    "config_name, overrides, expected",
    [
        param(
            "include_nested_group_pkg_header_foo",
            [],
            [
                ResultDefault(
                    config_path="group1/group2/file1",
                    package="foo.group2",
                    parent="group1/group_item1_pkg_header_foo",
                ),
                ResultDefault(
                    config_path="group1/group_item1_pkg_header_foo",
                    package="foo",
                    is_self=True,
                    parent="include_nested_group_pkg_header_foo",
                ),
                ResultDefault(
                    config_path="include_nested_group_pkg_header_foo",
                    package="",
                    is_self=True,
                ),
            ],
            id="include_nested_group_pkg_header_foo",
        ),
        param(
            "include_nested_group_pkg_header_foo",
            ["group1/group2@foo.group2=file2"],
            [
                ResultDefault(
                    config_path="group1/group2/file2",
                    package="foo.group2",
                    parent="group1/group_item1_pkg_header_foo",
                ),
                ResultDefault(
                    config_path="group1/group_item1_pkg_header_foo",
                    package="foo",
                    is_self=True,
                    parent="include_nested_group_pkg_header_foo",
                ),
                ResultDefault(
                    config_path="include_nested_group_pkg_header_foo",
                    package="",
                    is_self=True,
                ),
            ],
            id="include_nested_group_pkg_header_foo:override_nested",
        ),
        param(
            "include_nested_group_pkg_header_foo",
            ["group1=group_item2_pkg_header_foo"],
            [
                ResultDefault(
                    config_path="group1/group2/file2",
                    package="foo.group2",
                    parent="group1/group_item2_pkg_header_foo",
                ),
                ResultDefault(
                    config_path="group1/group_item2_pkg_header_foo",
                    package="foo",
                    is_self=True,
                    parent="include_nested_group_pkg_header_foo",
                ),
                ResultDefault(
                    config_path="include_nested_group_pkg_header_foo",
                    package="",
                    is_self=True,
                ),
            ],
            id="include_nested_group_pkg_header_foo:override_first_level",
        ),
        param(
            "include_nested_group_pkg_header_foo",
            ["group1=group_item2_pkg_header_bar"],
            [
                ResultDefault(
                    config_path="group1/group2/file2",
                    package="bar.group2",
                    parent="group1/group_item2_pkg_header_bar",
                ),
                ResultDefault(
                    config_path="group1/group_item2_pkg_header_bar",
                    package="bar",
                    is_self=True,
                    parent="include_nested_group_pkg_header_foo",
                ),
                ResultDefault(
                    config_path="include_nested_group_pkg_header_foo",
                    package="",
                    is_self=True,
                ),
            ],
            id="include_nested_group_pkg_header_foo:override_first_level_with_package_header_change",
        ),
    ],
)
def test_include_nested_group_pkg_header_foo(
    config_name: str, overrides: List[str], expected: List[ResultDefault]
) -> None:
    _test_defaults_list_impl(
        config_name=config_name, overrides=overrides, expected=expected
    )


@mark.parametrize(
    "config_name, overrides, expected",
    [
        param(
            "empty",
            ["+group1/group2=file1_pkg_header_foo"],
            [
                ResultDefault(config_path="empty", package="", is_self=True),
                ResultDefault(
                    config_path="group1/group2/file1_pkg_header_foo",
                    parent="empty",
                    package="foo",
                ),
            ],
            id="included_from_overrides",
        ),
        param(
            "empty",
            ["+group1=group_item1_with_pkg_header_foo"],
            [
                ResultDefault(
                    config_path="empty", package="", is_self=True, primary=True
                ),
                ResultDefault(
                    config_path="group1/group2/file1_pkg_header_foo",
                    parent="group1/group_item1_with_pkg_header_foo",
                    package="foo",
                    is_self=False,
                ),
                ResultDefault(
                    config_path="group1/group_item1_with_pkg_header_foo",
                    parent="empty",
                    package="group1",
                    is_self=True,
                ),
            ],
            id="included_from_overrides",
        ),
    ],
)
def test_nested_package_header_is_absolute(
    config_name: str, overrides: List[str], expected: List[ResultDefault]
) -> None:
    _test_defaults_list_impl(
        config_name=config_name, overrides=overrides, expected=expected
    )


@mark.parametrize(
    "config_name, overrides, expected",
    [
        param(
            "include_nested_group_pkg_header_foo_override_pkg_bar",
            [],
            [
                ResultDefault(
                    config_path="group1/group2/file1",
                    parent="group1/group_item1_pkg_header_foo",
                    package="bar.group2",
                    is_self=False,
                ),
                ResultDefault(
                    config_path="group1/group_item1_pkg_header_foo",
                    parent="include_nested_group_pkg_header_foo_override_pkg_bar",
                    package="bar",
                    is_self=True,
                ),
                ResultDefault(
                    config_path="include_nested_group_pkg_header_foo_override_pkg_bar",
                    parent=None,
                    package="",
                    is_self=True,
                ),
            ],
            id="include_nested_group_global_foo_override_pkg_bar",
        ),
        param(
            "include_nested_group_pkg_header_foo_override_pkg_bar",
            ["group1@bar=group_item2"],
            [
                ResultDefault(
                    config_path="group1/group2/file2",
                    parent="group1/group_item2",
                    package="bar.group2",
                    is_self=False,
                ),
                ResultDefault(
                    config_path="group1/group_item2",
                    parent="include_nested_group_pkg_header_foo_override_pkg_bar",
                    package="bar",
                    is_self=True,
                ),
                ResultDefault(
                    config_path="include_nested_group_pkg_header_foo_override_pkg_bar",
                    parent=None,
                    package="",
                    is_self=True,
                ),
            ],
            id="include_nested_group_global_foo_override_pkg_bar:override_group1",
        ),
        param(
            "include_nested_group_pkg_header_foo_override_pkg_bar",
            ["group1/group2@bar.group2=file2"],
            [
                ResultDefault(
                    config_path="group1/group2/file2",
                    parent="group1/group_item1_pkg_header_foo",
                    package="bar.group2",
                    is_self=False,
                ),
                ResultDefault(
                    config_path="group1/group_item1_pkg_header_foo",
                    parent="include_nested_group_pkg_header_foo_override_pkg_bar",
                    package="bar",
                    is_self=True,
                ),
                ResultDefault(
                    config_path="include_nested_group_pkg_header_foo_override_pkg_bar",
                    parent=None,
                    package="",
                    is_self=True,
                ),
            ],
            id="include_nested_group_global_foo_override_pkg_bar:override_group2",
        ),
    ],
)
def test_overriding_package_header_from_defaults_list(
    config_name: str, overrides: List[str], expected: List[ResultDefault]
) -> None:
    _test_defaults_list_impl(
        config_name=config_name, overrides=overrides, expected=expected
    )


@mark.parametrize(
    "config_name,overrides,expected",
    [
        param(
            "legacy_override_hydra",
            [],
            raises(
                ConfigCompositionException,
                match=re.escape(
                    dedent(
                        """\
                        Multiple values for hydra/help. To override a value use 'override hydra/help: custom1'"""
                    )
                ),
            ),
            id="override_hydra",
        ),
    ],
)
def test_legacy_override_hydra_is_rejected(
    config_name: str,
    overrides: List[str],
    expected: List[ResultDefault],
    recwarn: Any,  # Testing deprecated behavior
    hydra_restore_singletons: Any,
) -> None:
    _test_defaults_list_impl(
        config_name=config_name,
        overrides=overrides,
        expected=expected,
        prepend_hydra=True,
    )


@mark.parametrize(
    "config_name,overrides,expected",
    [
        param(
            "empty",
            [],
            [
                ResultDefault(
                    config_path="hydra/help/default",
                    parent="hydra/config",
                    package="hydra.help",
                ),
                ResultDefault(
                    config_path="hydra/output/default",
                    parent="hydra/config",
                    package="hydra",
                ),
                ResultDefault(
                    config_path="hydra/config",
                    parent="<root>",
                    package="hydra",
                    is_self=True,
                ),
                ResultDefault(config_path="empty", parent="<root>", package=""),
            ],
            id="just_hydra_config",
        ),
        param(
            "override_hydra2",
            [],
            [
                ResultDefault(
                    config_path="hydra/help/custom1",
                    parent="hydra/config",
                    package="hydra.help",
                    is_self=False,
                ),
                ResultDefault(
                    config_path="hydra/output/default",
                    parent="hydra/config",
                    package="hydra",
                    is_self=False,
                ),
                ResultDefault(
                    config_path="hydra/config",
                    parent="<root>",
                    package="hydra",
                    is_self=True,
                ),
                ResultDefault(
                    config_path="override_hydra2",
                    parent="<root>",
                    package="",
                    primary=True,
                ),
            ],
            id="override_hydra2",
        ),
    ],
)
def test_with_hydra_config(
    config_name: str,
    overrides: List[str],
    expected: List[ResultDefault],
    recwarn: Any,  # Testing deprecated behavior
) -> None:
    _test_defaults_list_impl(
        config_name=config_name,
        overrides=overrides,
        expected=expected,
        prepend_hydra=True,
    )


@mark.parametrize(
    "config_name,overrides,expected",
    [
        param(
            "group_default",
            ["+experiment=include_absolute_config"],
            [
                ResultDefault(
                    config_path="group1/file1", package="group1", parent="group_default"
                ),
                ResultDefault(config_path="group_default", package="", is_self=True),
                ResultDefault(
                    config_path="group1/group2/file1",
                    package="group1.group2",
                    parent="experiment/include_absolute_config",
                ),
                ResultDefault(
                    config_path="experiment/include_absolute_config",
                    package="",
                    parent="group_default",
                    is_self=True,
                ),
            ],
            id="group_default:experiment=include_absolute_config",
        ),
    ],
)
def test_experiment_use_case(
    config_name: str, overrides: List[str], expected: List[ResultDefault]
) -> None:
    _test_defaults_list_impl(
        config_name=config_name,
        overrides=overrides,
        expected=expected,
    )


@mark.parametrize("override", ["+nested/choice=two", "+nested/choice=[two]"])
def test_external_append_is_rooted_at_search_path(override: str) -> None:
    _test_defaults_list_impl(
        config_name="nested/base",
        overrides=[override],
        expected=[
            ResultDefault(
                config_path="nested/base",
                package="",
                is_self=True,
                primary=True,
            ),
            ResultDefault(
                config_path="nested/choice/two",
                package="",
                parent="nested/base",
            ),
        ],
    )


def test_external_append_package_is_rooted_at_search_path() -> None:
    _test_defaults_list_impl(
        config_name="nested/base",
        overrides=["+nested/choice=default_package"],
        expected=[
            ResultDefault(
                config_path="nested/base",
                package="",
                is_self=True,
                primary=True,
            ),
            ResultDefault(
                config_path="nested/choice/default_package",
                package="nested.choice",
                parent="nested/base",
            ),
        ],
    )


@mark.parametrize(
    "config_name,overrides,expected",
    [
        param(
            "experiment/override_hydra",
            [],
            [
                ResultDefault(
                    config_path="hydra/help/custom1",
                    package="hydra.help",
                    parent="hydra/config",
                ),
                ResultDefault(
                    config_path="hydra/output/default",
                    package="hydra",
                    parent="hydra/config",
                ),
                ResultDefault(
                    config_path="hydra/config",
                    package="hydra",
                    parent="<root>",
                    is_self=True,
                ),
                ResultDefault(
                    config_path="experiment/override_hydra",
                    package="",
                    parent="<root>",
                ),
            ],
            id="group_default:experiment=include_absolute_config",
        ),
    ],
)
def test_as_as_primary(
    config_name: str, overrides: List[str], expected: List[ResultDefault]
) -> None:
    _test_defaults_list_impl(
        config_name=config_name,
        overrides=overrides,
        expected=expected,
        prepend_hydra=True,
    )


@mark.parametrize(
    "config_name,overrides,expected",
    [
        param(
            "placeholder",
            [],
            [ResultDefault(config_path="placeholder", package="", is_self=True)],
            id="placeholder",
        ),
        param(
            "placeholder",
            ["group1=file1"],
            [
                ResultDefault(
                    config_path="group1/file1", package="group1", parent="placeholder"
                ),
                ResultDefault(config_path="placeholder", package="", is_self=True),
            ],
            id="placeholder:override",
        ),
        param(
            "nested_placeholder",
            [],
            [
                ResultDefault(
                    config_path="group1/placeholder",
                    package="group1",
                    parent="nested_placeholder",
                    is_self=True,
                ),
                ResultDefault(
                    config_path="nested_placeholder", package="", is_self=True
                ),
            ],
            id="nested_placeholder",
        ),
        param(
            "nested_placeholder",
            ["group1/group2=file1"],
            [
                ResultDefault(
                    config_path="group1/group2/file1",
                    package="group1.group2",
                    parent="group1/placeholder",
                ),
                ResultDefault(
                    config_path="group1/placeholder",
                    package="group1",
                    parent="nested_placeholder",
                    is_self=True,
                ),
                ResultDefault(
                    config_path="nested_placeholder", package="", is_self=True
                ),
            ],
            id="nested_placeholder:override",
        ),
    ],
)
def test_placeholder(
    config_name: str, overrides: List[str], expected: List[ResultDefault]
) -> None:
    _test_defaults_list_impl(
        config_name=config_name,
        overrides=overrides,
        expected=expected,
    )


@mark.parametrize(
    "config_name,overrides,expected",
    [
        param(
            "interpolation_simple",
            ["group1=file2"],
            [
                ResultDefault(
                    config_path="group1/file2",
                    package="group1",
                    parent="interpolation_simple",
                ),
                ResultDefault(
                    config_path="group2/file2",
                    package="group2",
                    parent="interpolation_simple",
                ),
                ResultDefault(
                    config_path="group1_group2/file2_file2",
                    package="group1_group2",
                    parent="interpolation_simple",
                ),
                ResultDefault(
                    config_path="interpolation_simple", package="", is_self=True
                ),
            ],
            id="interpolation_simple",
        ),
        param(
            "interpolation_with_nested_defaults_list",
            [],
            [
                ResultDefault(
                    config_path="group1/file1",
                    package="group1",
                    parent="interpolation_with_nested_defaults_list",
                ),
                ResultDefault(
                    config_path="group2/file1",
                    package="group2",
                    parent="interpolation_with_nested_defaults_list",
                ),
                ResultDefault(
                    config_path="group1_group2/empty1",
                    package="group1_group2",
                    parent="group1_group2/file1_file1_with_defaults_list",
                ),
                ResultDefault(
                    config_path="group1_group2/file1_file1_with_defaults_list",
                    package="group1_group2",
                    parent="interpolation_with_nested_defaults_list",
                    is_self=True,
                ),
                ResultDefault(
                    config_path="interpolation_with_nested_defaults_list",
                    package="",
                    is_self=True,
                ),
            ],
            id="interpolation_with_nested_defaults_list",
        ),
    ],
)
def test_interpolation_simple(
    config_name: str, overrides: List[str], expected: List[ResultDefault]
) -> None:
    _test_defaults_list_impl(
        config_name=config_name,
        overrides=overrides,
        expected=expected,
    )


@mark.parametrize(
    "config_name,overrides,expected",
    [
        param(
            "include_nested_group",
            ["~group1"],
            [
                ResultDefault(
                    config_path="include_nested_group", package="", is_self=True
                ),
            ],
            id="delete:include_nested_group:group1",
        ),
    ],
)
def test_deletion(
    config_name: str, overrides: List[str], expected: List[ResultDefault]
) -> None:
    _test_defaults_list_impl(
        config_name=config_name,
        overrides=overrides,
        expected=expected,
    )


@mark.parametrize(
    "config_name,overrides,expected",
    [
        param(
            "error_duplicate_group",
            [],
            raises(
                ConfigCompositionException,
                match=re.escape(
                    "group1 appears more than once in the final defaults list"
                ),
            ),
            id="error_duplicate_group",
        ),
        param(
            "error_duplicate_group_nested",
            [],
            raises(
                ConfigCompositionException,
                match=re.escape(
                    "group1/group2 appears more than once in the final defaults list"
                ),
            ),
            id="error_duplicate_group_nested",
        ),
    ],
)
def test_duplicate_items(
    config_name: str, overrides: List[str], expected: List[ResultDefault]
) -> None:
    _test_defaults_list_impl(
        config_name=config_name,
        overrides=overrides,
        expected=expected,
    )


@mark.parametrize(
    "config_name,overrides,expected",
    [
        param(
            "config_with_same_name_as_group",
            [],
            [
                ResultDefault(
                    config_path="config_with_same_name_as_group/item",
                    package="config_with_same_name_as_group",
                    parent="config_with_same_name_as_group",
                ),
                ResultDefault(
                    config_path="config_with_same_name_as_group",
                    package="",
                    is_self=True,
                    primary=True,
                ),
            ],
            id="config_with_same_name_as_group",
        ),
        param(
            "include_group_with_same_name_as_config",
            [],
            [
                ResultDefault(
                    config_path="config_with_same_name_as_group/item",
                    package="config_with_same_name_as_group",
                    parent="include_group_with_same_name_as_config",
                ),
                ResultDefault(
                    config_path="include_group_with_same_name_as_config",
                    package="",
                    is_self=True,
                    primary=True,
                ),
            ],
            id="include_group_with_same_name_as_config",
        ),
        param(
            "test_extend_from_config_with_same_name_as_group",
            [],
            [
                ResultDefault(
                    config_path="config_with_same_name_as_group/item",
                    package="config_with_same_name_as_group",
                    parent="config_with_same_name_as_group",
                ),
                ResultDefault(
                    config_path="config_with_same_name_as_group",
                    package="",
                    parent="test_extend_from_config_with_same_name_as_group",
                    is_self=True,
                ),
                ResultDefault(
                    config_path="test_extend_from_config_with_same_name_as_group",
                    package="",
                    is_self=True,
                    primary=True,
                ),
            ],
            id="test_extend_from_config_with_same_name_as_group",
        ),
        param(
            "test_extend_from_group_with_same_name_as_config",
            [],
            [
                ResultDefault(
                    config_path="config_with_same_name_as_group/item",
                    package="config_with_same_name_as_group",
                    parent="test_extend_from_group_with_same_name_as_config",
                ),
                ResultDefault(
                    config_path="test_extend_from_group_with_same_name_as_config",
                    package="",
                    is_self=True,
                    primary=True,
                ),
            ],
            id="test_extend_from_group_with_same_name_as_config",
        ),
    ],
)
def test_name_collision(
    config_name: str,
    overrides: List[str],
    expected: List[ResultDefault],
    hydra_restore_singletons: Any,
) -> None:
    _test_defaults_list_impl(
        config_name=config_name,
        overrides=overrides,
        expected=expected,
    )


@mark.parametrize(
    "config_name,overrides,expected",
    [
        param(
            "group1/file_with_group_header",
            [],
            [
                ResultDefault(
                    config_path="group1/file_with_group_header", package="_group_"
                )
            ],
            id="group1/file_with_group_header",
        ),
        param(
            "empty",
            ["+group1=file_with_group_header"],
            [
                ResultDefault(config_path="empty", package="", is_self=True),
                ResultDefault(
                    config_path="group1/file_with_group_header",
                    package="_group_",
                    parent="empty",
                ),
            ],
            id="empty_group1/file_with_group_header",
        ),
        param(
            "group1/group2/file_with_group_header",
            [],
            [
                ResultDefault(
                    config_path="group1/group2/file_with_group_header",
                    package="_group_",
                )
            ],
            id="group1/group2/file_with_group_header",
        ),
        param(
            "empty",
            ["+group1/group2=file_with_group_header"],
            [
                ResultDefault(config_path="empty", package="", is_self=True),
                ResultDefault(
                    config_path="group1/group2/file_with_group_header",
                    package="_group_",
                    parent="empty",
                ),
            ],
            id="empty+group1/group2/file_with_group_header",
        ),
    ],
)
def test_load_group_header(
    config_name: str, overrides: List[str], expected: List[ResultDefault], recwarn: Any
) -> None:
    _test_defaults_list_impl(
        config_name=config_name,
        overrides=overrides,
        expected=expected,
    )


@mark.parametrize(
    "config_name,overrides,expected",
    [
        param(
            None,
            [],
            [],
            id="none",
        ),
        param(
            None,
            ["+group1=file1"],
            [
                ResultDefault(
                    config_path="group1/file1",
                    package="group1",
                    parent="_dummy_empty_config_",
                )
            ],
            id="none+group1=file1",
        ),
    ],
)
def test_with_none_primary(
    config_name: str,
    overrides: List[str],
    expected: List[ResultDefault],
) -> None:
    _test_defaults_list_impl(
        config_name=config_name,
        overrides=overrides,
        expected=expected,
    )


@mark.parametrize(
    "config_name,overrides,expected",
    [
        param(
            None,
            [],
            [
                ResultDefault(
                    config_path="hydra/help/default",
                    package="hydra.help",
                    parent="hydra/config",
                ),
                ResultDefault(
                    config_path="hydra/output/default",
                    package="hydra",
                    parent="hydra/config",
                ),
                ResultDefault(
                    config_path="hydra/config",
                    package="hydra",
                    parent="<root>",
                    is_self=True,
                ),
            ],
            id="none",
        ),
        param(
            None,
            ["+group1=file1"],
            [
                ResultDefault(
                    config_path="hydra/help/default",
                    package="hydra.help",
                    parent="hydra/config",
                ),
                ResultDefault(
                    config_path="hydra/output/default",
                    package="hydra",
                    parent="hydra/config",
                ),
                ResultDefault(
                    config_path="hydra/config",
                    package="hydra",
                    parent="<root>",
                    is_self=True,
                ),
                ResultDefault(
                    config_path="group1/file1",
                    package="group1",
                    parent="_dummy_empty_config_",
                ),
            ],
            id="none+group1=file1",
        ),
    ],
)
def test_with_none_primary_with_hydra(
    config_name: str,
    overrides: List[str],
    expected: List[ResultDefault],
) -> None:
    _test_defaults_list_impl(
        config_name=config_name,
        overrides=overrides,
        expected=expected,
        prepend_hydra=True,
    )


@mark.parametrize(
    "config_name,overrides,expected",
    [
        param(
            "two_config_items",
            [],
            [
                ResultDefault(
                    config_path="group1/file1",
                    package="group1",
                    parent="two_config_items",
                ),
                ResultDefault(
                    config_path="group1/file2",
                    package="group1",
                    parent="two_config_items",
                ),
                ResultDefault(config_path="two_config_items", package="", is_self=True),
            ],
            id="two_config_items",
        ),
        param(
            "two_config_items",
            ["~group1/file1"],
            [
                ResultDefault(
                    config_path="group1/file2",
                    package="group1",
                    parent="two_config_items",
                ),
                ResultDefault(config_path="two_config_items", package="", is_self=True),
            ],
            id="two_config_items:delete_config_path",
        ),
    ],
)
def test_two_config_items(
    config_name: str,
    overrides: List[str],
    expected: List[ResultDefault],
) -> None:
    _test_defaults_list_impl(
        config_name=config_name,
        overrides=overrides,
        expected=expected,
    )


@mark.parametrize(
    "config_name,overrides,skip_missing,expected",
    [
        param(
            "with_missing",
            [],
            True,
            [
                ResultDefault(config_path="with_missing", package="", is_self=True),
            ],
            id="with_missing:ignore_missing",
        ),
        param(
            "with_missing",
            ["db=base_db"],
            True,
            [
                ResultDefault(
                    config_path="db/base_db", package="db", parent="with_missing"
                ),
                ResultDefault(config_path="with_missing", package="", is_self=True),
            ],
            id="with_missing:ignore_missing+override",
        ),
        param(
            "with_missing",
            [],
            False,
            raises(
                ConfigCompositionException,
                match=re.escape(
                    dedent("""\
                        You must specify 'db', e.g, db=<OPTION>
                        Available options:
                        \tbase_db""")
                ),
            ),
            id="with_missing:not_ignore_missing",
        ),
    ],
)
def test_with_missing_config(
    config_name: str,
    overrides: List[str],
    skip_missing: bool,
    expected: List[ResultDefault],
) -> None:
    _test_defaults_list_impl(
        config_name=config_name,
        overrides=overrides,
        expected=expected,
        skip_missing=skip_missing,
    )


@mark.parametrize(
    "default,package_header,expected",
    [
        param(
            GroupDefault(group="group1", value="file"),
            "_group_",
            "_group_",
            id="gd:_group_",
        ),
        param(
            GroupDefault(group="group1", value="file"),
            "group1",
            "group1",
            id="gd:group1",
        ),
        param(
            GroupDefault(group="group1", value="file"),
            "abc",
            "abc",
            id="gd:abc",
        ),
        param(
            GroupDefault(group="group1", value="file"),
            "_global_",
            "",
            id="gd:_global_",
        ),
        param(
            GroupDefault(group="group1", value="file"),
            "_group_._name_",
            "_group_._name_",
            id="gd:_group_._name_",
        ),
    ],
)
def test_set_package_header_no_parent_pkg(
    default: InputDefault, package_header: str, expected: str, recwarn: Any
) -> None:
    default.update_parent(parent_base_dir="", parent_package="")
    default.set_package_header(package_header)
    assert default.get_final_package() == expected


@mark.parametrize(
    "default,package_header,expected",
    [
        param(
            GroupDefault(group="group1", value="file"),
            "_group_",
            "_group_",
            id="gd:_group_",
        ),
    ],
)
def test_set_package_header_with_parent_pkg(
    default: InputDefault, package_header: str, expected: str, recwarn: Any
) -> None:
    default.update_parent(parent_base_dir="", parent_package="parent_pkg")
    default.set_package_header(package_header)
    assert default.get_final_package() == expected


@mark.parametrize(
    "config_name,overrides,skip_missing,expected",
    [
        param(
            "select_multi_pkg",
            [],
            True,
            [
                ResultDefault(
                    config_path="group1/file1", package="foo", parent="select_multi_pkg"
                ),
                ResultDefault(
                    config_path="group1/file2", package="foo", parent="select_multi_pkg"
                ),
                ResultDefault(
                    config_path="select_multi_pkg",
                    package="",
                    is_self=True,
                    primary=True,
                ),
            ],
            id="select_multi_pkg",
        )
    ],
)
def test_select_multi_pkg(
    config_name: str,
    overrides: List[str],
    skip_missing: bool,
    expected: List[ResultDefault],
) -> None:
    _test_defaults_list_impl(
        config_name=config_name,
        overrides=overrides,
        expected=expected,
        skip_missing=skip_missing,
    )


@mark.parametrize(
    "config_name,overrides,error_path_type,error_path",
    [
        param(
            "error_parent_traversal_escapes_root",
            [],
            "config group",
            "../group1",
            id="config-group-escapes-root",
        ),
        param(
            "group1/error_parent_traversal_within_root",
            [],
            "config group",
            "../group2",
            id="nested-config-group",
        ),
        param(
            "error_parent_traversal_config",
            [],
            "config",
            "../group1/file1",
            id="config-escapes-root",
        ),
        param(
            "group1/error_parent_traversal_config",
            [],
            "config",
            "../group2/file1",
            id="nested-config",
        ),
        param(
            "error_parent_traversal_option",
            [],
            "config option",
            "../file1",
            id="config-option",
        ),
        param(
            "error_parent_traversal_options",
            [],
            "config option",
            "../file1",
            id="config-options-list",
        ),
        param(
            "empty",
            ["+group1=../file1"],
            "config option",
            "../file1",
            id="cli-append-option",
        ),
        param(
            "empty",
            ["+group1=[file1,../file1]"],
            "config option",
            "../file1",
            id="cli-append-options-list",
        ),
        param(
            "group_default",
            ["group1=../file1"],
            "config option",
            "../file1",
            id="cli-override-option",
        ),
    ],
)
def test_parent_traversal_error(
    config_name: str,
    overrides: List[str],
    error_path_type: str,
    error_path: str,
) -> None:
    guidance = {
        "config": "Use an absolute config path instead, such as '/group/config'.",
        "config group": (
            "Use an absolute config group path instead, such as '/group: option'."
        ),
        "config option": (
            "Config options cannot contain parent traversal. Select the target "
            "config directly. Use '/config' or '/group: option' in a Defaults "
            "List, or 'group=option' (with '+' when adding a new default) on the "
            "command line."
        ),
    }[error_path_type]
    expected = raises(
        ConfigCompositionException,
        match=re.escape(
            "Parent traversal ('..') in Defaults List "
            f"{error_path_type} paths is not supported ('{error_path}').\n"
            f"{guidance}"
        ),
    )
    _test_defaults_list_impl(
        config_name=config_name,
        overrides=overrides,
        expected=expected,
    )


@mark.parametrize(
    "default",
    [
        param(
            ConfigDefault(path="group1/file..1"),
            id="config",
        ),
        param(
            GroupDefault(group="group..1", value="file1"),
            id="config-group",
        ),
        param(
            GroupDefault(group="group1", value="file..1"),
            id="config-option",
        ),
    ],
)
def test_parent_traversal_substring_is_allowed(default: InputDefault) -> None:
    parent = ConfigDefault(path="empty")
    parent.update_parent("", "")

    _validate_paths(default, parent)


@mark.parametrize(
    "config_name,overrides,error_path_type,error_path",
    [
        param(
            "error_backslash_config",
            [],
            "config",
            "group1\\file1",
            id="config",
        ),
        param(
            "error_backslash_group",
            [],
            "config group",
            "group1\\group2",
            id="config-group",
        ),
        param(
            "error_backslash_config_traversal",
            [],
            "config",
            "..\\secret",
            id="config-traversal-bypass",
        ),
        param(
            "error_backslash_option",
            [],
            "config option",
            "..\\file1",
            id="config-option-traversal-bypass",
        ),
        param(
            "error_backslash_options",
            [],
            "config option",
            "sub\\file1",
            id="config-options-list",
        ),
        param(
            "error_backslash_interpolation",
            [],
            "config option",
            "${group1}\\extra",
            id="config-option-interpolation",
        ),
        param(
            "empty",
            ["+group1=..\\file1"],
            "config option",
            "..\\file1",
            id="cli-append-option",
        ),
        param(
            "empty",
            ["+group1=[file1,sub\\file1]"],
            "config option",
            "sub\\file1",
            id="cli-append-options-list",
        ),
        param(
            "group_default",
            ["group1=sub\\file1"],
            "config option",
            "sub\\file1",
            id="cli-override-option",
        ),
    ],
)
def test_backslash_error(
    config_name: str,
    overrides: List[str],
    error_path_type: str,
    error_path: str,
) -> None:
    expected = raises(
        ConfigCompositionException,
        match=re.escape(
            "Backslash ('\\') in Defaults List "
            f"{error_path_type} paths is not supported ('{error_path}').\n"
            "Use '/' as the config group separator; it is the only "
            "supported separator, regardless of the operating system.\n"
            "See https://hydra.cc/docs/advanced/defaults_list/ for more "
            "information."
        ),
    )
    _test_defaults_list_impl(
        config_name=config_name,
        overrides=overrides,
        expected=expected,
    )


def test_backslash_error_includes_location_prefix() -> None:
    expected = raises(
        ConfigCompositionException,
        match=re.escape(
            "In error_backslash_option: Backslash ('\\') in Defaults List "
            "config option paths is not supported ('..\\file1').\n"
            "Use '/' as the config group separator; it is the only "
            "supported separator, regardless of the operating system.\n"
            "See https://hydra.cc/docs/advanced/defaults_list/ for more "
            "information."
        ),
    )
    _test_defaults_list_impl(
        config_name="error_backslash_option",
        overrides=[],
        expected=expected,
    )


def test_parent_traversal_error_explains_supported_paths() -> None:
    expected = raises(
        ConfigCompositionException,
        match=re.escape(
            "In group1/error_parent_traversal_config: Parent traversal ('..') "
            "in Defaults List config paths is not supported "
            "('../group2/file1').\n"
            "Use an absolute config path instead, such as '/group/config'.\n"
            "See https://hydra.cc/docs/advanced/defaults_list/ for more "
            "information."
        ),
    )
    _test_defaults_list_impl(
        config_name="group1/error_parent_traversal_config",
        overrides=[],
        expected=expected,
    )

# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved
import re
from textwrap import dedent
from typing import Any

from omegaconf import OmegaConf
from pytest import mark, param, raises

from hydra.core.default_element import (
    ConfigDefault,
    DefaultsTreeNode,
    GroupDefault,
    VirtualRoot,
)
from hydra.core.plugins import Plugins
from hydra.errors import ConfigCompositionException
from hydra.test_utils.test_utils import chdir_hydra_root
from tests.defaults_list import _test_defaults_tree_impl

chdir_hydra_root()

# registers config source plugins
Plugins.instance()


@mark.parametrize(
    "config_name, overrides, expected",
    [
        param(
            "empty",
            [],
            DefaultsTreeNode(node=ConfigDefault(path="empty")),
            id="empty",
        ),
        param(
            "config_default",
            [],
            DefaultsTreeNode(
                node=ConfigDefault(path="config_default"),
                children=[ConfigDefault(path="empty"), ConfigDefault(path="_self_")],
            ),
            id="config_default",
        ),
        param(
            "group_default",
            [],
            DefaultsTreeNode(
                node=ConfigDefault(path="group_default"),
                children=[
                    GroupDefault(group="group1", value="file1"),
                    ConfigDefault(path="_self_"),
                ],
            ),
            id="group_default",
        ),
        param(
            "optional",
            [],
            DefaultsTreeNode(
                node=ConfigDefault(path="optional"),
                children=[
                    GroupDefault(group="group1", value="file1", optional=True),
                    ConfigDefault(path="_self_"),
                ],
            ),
            id="optional",
        ),
        param(
            "self_leading",
            [],
            DefaultsTreeNode(
                node=ConfigDefault(path="self_leading"),
                children=[
                    ConfigDefault(path="_self_"),
                    GroupDefault(group="group1", value="file1"),
                ],
            ),
            id="self_leading",
        ),
        param(
            "self_trailing",
            [],
            DefaultsTreeNode(
                node=ConfigDefault(path="self_trailing"),
                children=[
                    GroupDefault(group="group1", value="file1"),
                    ConfigDefault(path="_self_"),
                ],
            ),
            id="self_trailing",
        ),
        param(
            "include_nested_group",
            [],
            DefaultsTreeNode(
                node=ConfigDefault(path="include_nested_group"),
                children=[
                    DefaultsTreeNode(
                        node=GroupDefault(group="group1", value="group_item1"),
                        children=[
                            GroupDefault(group="group2", value="file1"),
                            ConfigDefault(path="_self_"),
                        ],
                    ),
                    ConfigDefault(path="_self_"),
                ],
            ),
            id="include_nested_group",
        ),
        param(
            "include_nested_config_item",
            [],
            DefaultsTreeNode(
                node=ConfigDefault(path="include_nested_config_item"),
                children=[
                    DefaultsTreeNode(
                        node=GroupDefault(group="group1", value="config_item"),
                        children=[
                            ConfigDefault(path="group2/file1"),
                            ConfigDefault(path="_self_"),
                        ],
                    ),
                    ConfigDefault(path="_self_"),
                ],
            ),
            id="include_nested_config_item",
        ),
    ],
)
def test_simple_defaults_tree_cases(
    config_name: str,
    overrides: list[str],
    expected: DefaultsTreeNode,
) -> None:
    _test_defaults_tree_impl(
        config_name=config_name, input_overrides=overrides, expected=expected
    )


@mark.parametrize(
    "config_name, overrides, expected",
    [
        param(
            "empty",
            ["+group1=file1"],
            DefaultsTreeNode(
                node=ConfigDefault(path="empty"),
                children=[
                    ConfigDefault(path="_self_"),
                    GroupDefault(group="group1", value="file1"),
                ],
            ),
            id="empty:append",
        ),
        param(
            "config_default",
            ["+group1=file1"],
            DefaultsTreeNode(
                node=ConfigDefault(path="config_default"),
                children=[
                    ConfigDefault(path="empty"),
                    ConfigDefault(path="_self_"),
                    GroupDefault(group="group1", value="file1"),
                ],
            ),
            id="config_default:append",
        ),
        param(
            "group_default",
            ["+group1=file1"],
            DefaultsTreeNode(
                node=ConfigDefault(path="group_default"),
                children=[
                    # config tree allow for duplicate items
                    GroupDefault(group="group1", value="file1"),
                    ConfigDefault(path="_self_"),
                    GroupDefault(group="group1", value="file1"),
                ],
            ),
            id="group_default:append",
        ),
        param(
            "self_trailing",
            ["+group1=file1"],
            DefaultsTreeNode(
                node=ConfigDefault(path="self_trailing"),
                children=[
                    GroupDefault(group="group1", value="file1"),
                    ConfigDefault(path="_self_"),
                    GroupDefault(group="group1", value="file1"),
                ],
            ),
            id="self_trailing:append",
        ),
        param(
            "include_nested_group",
            ["+group2=file1"],
            DefaultsTreeNode(
                node=ConfigDefault(path="include_nested_group"),
                children=[
                    DefaultsTreeNode(
                        node=GroupDefault(group="group1", value="group_item1"),
                        children=[
                            GroupDefault(group="group2", value="file1"),
                            ConfigDefault(path="_self_"),
                        ],
                    ),
                    ConfigDefault(path="_self_"),
                    GroupDefault(group="group2", value="file1"),
                ],
            ),
            id="include_nested_group:append",
        ),
        param(
            "group_override_only",
            ["+group1=file1"],
            raises(
                ConfigCompositionException,
                match=re.escape(
                    "In 'group_override_only': Invalid Defaults List override 'group1: file2'."
                    "\nNo earlier Group Default for 'group1' exists to override."
                ),
            ),
            id="group_override_only:append_does_not_rescue_dangling_override",
        ),
        param(
            "dangling_nested_override",
            ["group1=group_item1"],
            DefaultsTreeNode(
                node=ConfigDefault(path="dangling_nested_override"),
                children=[
                    DefaultsTreeNode(
                        node=GroupDefault(group="group1", value="group_item1"),
                        children=[
                            GroupDefault(group="group2", value="file2"),
                            ConfigDefault(path="_self_"),
                        ],
                    ),
                    ConfigDefault(path="_self_"),
                ],
            ),
            id="dangling_nested_override:selection_introduces_target",
        ),
        param(
            "dangling_nested_override",
            [],
            raises(
                ConfigCompositionException,
                match=re.escape(
                    "In 'dangling_nested_override': "
                    "Invalid Defaults List override 'group1/group2: file2'."
                    "\nNo earlier Group Default for 'group1/group2' exists to override."
                ),
            ),
            id="dangling_nested_override:selection_does_not_introduce_target",
        ),
        param(
            "dangling_nested_override",
            ["group1/group2=file3"],
            raises(
                ConfigCompositionException,
                match=re.escape(
                    "Could not override 'group1/group2'. No match in the defaults list."
                ),
            ),
            id="dangling_nested_override:cli_override_does_not_recover",
        ),
        param(
            "dangling_nested_override",
            ["+group1/group2=file3"],
            raises(
                ConfigCompositionException,
                match=re.escape(
                    "In 'dangling_nested_override': "
                    "Invalid Defaults List override 'group1/group2: file2'."
                    "\nNo earlier Group Default for 'group1/group2' exists to override."
                ),
            ),
            id="dangling_nested_override:cli_append_does_not_recover",
        ),
        param(
            "dangling_nested_override",
            ["group1=group_item1", "group1/group2=file3"],
            DefaultsTreeNode(
                node=ConfigDefault(path="dangling_nested_override"),
                children=[
                    DefaultsTreeNode(
                        node=GroupDefault(group="group1", value="group_item1"),
                        children=[
                            GroupDefault(group="group2", value="file3"),
                            ConfigDefault(path="_self_"),
                        ],
                    ),
                    ConfigDefault(path="_self_"),
                ],
            ),
            id="dangling_nested_override:cli_override_wins_when_target_introduced",
        ),
    ],
)
def test_tree_with_append_override(
    config_name: str,
    overrides: list[str],
    expected: DefaultsTreeNode,
) -> None:
    _test_defaults_tree_impl(
        config_name=config_name, input_overrides=overrides, expected=expected
    )


@mark.parametrize(
    "config_name, overrides, expected",
    [
        param(
            "group_default",
            ["group1=file2"],
            DefaultsTreeNode(
                node=ConfigDefault(path="group_default"),
                children=[
                    GroupDefault(group="group1", value="file2"),
                    ConfigDefault(path="_self_"),
                ],
            ),
            id="group_default:override",
        ),
        param(
            "optional",
            ["group1=file2"],
            DefaultsTreeNode(
                node=ConfigDefault(path="optional"),
                children=[
                    GroupDefault(group="group1", value="file2", optional=True),
                    ConfigDefault(path="_self_"),
                ],
            ),
            id="optional:override",
        ),
        param(
            "include_nested_group",
            ["group1=group_item2"],
            DefaultsTreeNode(
                node=ConfigDefault(path="include_nested_group"),
                children=[
                    DefaultsTreeNode(
                        node=GroupDefault(group="group1", value="group_item2"),
                        children=[
                            GroupDefault(group="group2", value="file2"),
                            ConfigDefault(path="_self_"),
                        ],
                    ),
                    ConfigDefault(path="_self_"),
                ],
            ),
            id="include_nested_group:override",
        ),
        param(
            "include_nested_group",
            ["group1/group2=file2"],
            DefaultsTreeNode(
                node=ConfigDefault(path="include_nested_group"),
                children=[
                    DefaultsTreeNode(
                        node=GroupDefault(group="group1", value="group_item1"),
                        children=[
                            GroupDefault(group="group2", value="file2"),
                            ConfigDefault(path="_self_"),
                        ],
                    ),
                    ConfigDefault(path="_self_"),
                ],
            ),
            id="include_nested_group:override_nested",
        ),
    ],
)
def test_simple_group_override(
    config_name: str,
    overrides: list[str],
    expected: DefaultsTreeNode,
) -> None:
    _test_defaults_tree_impl(
        config_name=config_name, input_overrides=overrides, expected=expected
    )


@mark.parametrize(
    "config_name, overrides, expected",
    [
        param(
            "error_self_pkg1",
            [],
            raises(ValueError, match=re.escape("_self_@PACKAGE is not supported")),
            id="error_self_pkg1",
        ),
        param(
            "error_changing_group",
            [],
            raises(
                ConfigCompositionException,
                match=re.escape(
                    "Multiple values for group1. To override a value use 'override group1: file2'"
                ),
            ),
            id="error_changing_group",
        ),
        param(
            "duplicate_self",
            [],
            raises(
                ConfigCompositionException,
                match="Duplicate _self_ defined in duplicate_self",
            ),
            id="duplicate_self",
        ),
        param(
            "invalid_override_in_defaults",
            [],
            raises(
                ConfigCompositionException,
                match=re.escape(
                    "In 'invalid_override_in_defaults': Invalid Defaults List override 'foo: bar'."
                    "\nNo earlier Group Default for 'foo' exists to override."
                )
                + "$",
            ),
            id="invalid_override_in_defaults",
        ),
    ],
)
def test_misc_errors(
    config_name: str,
    overrides: list[str],
    expected: Any,
) -> None:
    _test_defaults_tree_impl(
        config_name=config_name, input_overrides=overrides, expected=expected
    )


@mark.parametrize(
    "config_name, overrides, expected",
    [
        param(
            "config_default_pkg1",
            [],
            DefaultsTreeNode(
                node=ConfigDefault(path="config_default_pkg1"),
                children=[
                    ConfigDefault(path="empty", package="pkg1"),
                    ConfigDefault(path="_self_"),
                ],
            ),
            id="config_default_pkg1",
        ),
        param(
            "group_default_pkg1",
            [],
            DefaultsTreeNode(
                node=ConfigDefault(path="group_default_pkg1"),
                children=[
                    GroupDefault(group="group1", value="file1", package="pkg1"),
                    ConfigDefault(path="_self_"),
                ],
            ),
            id="group_default_pkg1",
        ),
        param(
            "include_nested_group_pkg2",
            [],
            DefaultsTreeNode(
                node=ConfigDefault(path="include_nested_group_pkg2"),
                children=[
                    DefaultsTreeNode(
                        node=GroupDefault(group="group1", value="group_item1_pkg2"),
                        children=[
                            GroupDefault(group="group2", value="file1", package="pkg2"),
                            ConfigDefault(path="_self_"),
                        ],
                    ),
                    ConfigDefault(path="_self_"),
                ],
            ),
            id="include_nested_group_pkg2",
        ),
        param(
            "include_nested_config_item_pkg2",
            [],
            DefaultsTreeNode(
                node=ConfigDefault(path="include_nested_config_item_pkg2"),
                children=[
                    DefaultsTreeNode(
                        node=GroupDefault(group="group1", value="config_item_pkg2"),
                        children=[
                            ConfigDefault(path="group2/file1", package="pkg2"),
                            ConfigDefault(path="_self_"),
                        ],
                    ),
                    ConfigDefault(path="_self_"),
                ],
            ),
            id="include_nested_config_item_pkg2",
        ),
    ],
)
def test_defaults_tree_with_package_overrides(
    config_name: str,
    overrides: list[str],
    expected: DefaultsTreeNode,
) -> None:
    _test_defaults_tree_impl(
        config_name=config_name, input_overrides=overrides, expected=expected
    )


@mark.parametrize(
    "config_name, overrides, expected",
    [
        param(
            "group_default_pkg1",
            ["group1@pkg1=file2"],
            DefaultsTreeNode(
                node=ConfigDefault(path="group_default_pkg1"),
                children=[
                    GroupDefault(group="group1", value="file2", package="pkg1"),
                    ConfigDefault(path="_self_"),
                ],
            ),
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
        param(
            "include_nested_group_pkg2",
            ["group1/group2@group1.pkg2=file2"],
            DefaultsTreeNode(
                node=ConfigDefault(path="include_nested_group_pkg2"),
                children=[
                    DefaultsTreeNode(
                        node=GroupDefault(group="group1", value="group_item1_pkg2"),
                        children=[
                            GroupDefault(group="group2", value="file2", package="pkg2"),
                            ConfigDefault(path="_self_"),
                        ],
                    ),
                    ConfigDefault(path="_self_"),
                ],
            ),
            id="option_override:include_nested_group_pkg2",
        ),
        param(
            "include_nested_group_pkg2",
            ["group1/group2=file2"],
            raises(
                ConfigCompositionException,
                match=re.escape(
                    dedent("""\
                        Could not override 'group1/group2'.
                        Did you mean to override group1/group2@group1.pkg2?
                        To append to your default list use +group1/group2=file2""")
                ),
            ),
            id="option_override:include_nested_group_pkg2:missing_package_in_override",
        ),
    ],
)
def test_defaults_tree_with_package_overrides__group_override(
    config_name: str,
    overrides: list[str],
    expected: DefaultsTreeNode,
) -> None:
    _test_defaults_tree_impl(
        config_name=config_name, input_overrides=overrides, expected=expected
    )


@mark.parametrize(
    "config_name, overrides, expected",
    [
        param(
            "override_same_level",
            [],
            DefaultsTreeNode(
                node=ConfigDefault(path="override_same_level"),
                children=[
                    GroupDefault(group="group1", value="file2"),
                    ConfigDefault(path="_self_"),
                ],
            ),
            id="override_same_level",
        ),
        param(
            "override_same_level",
            ["group1=file3"],
            DefaultsTreeNode(
                node=ConfigDefault(path="override_same_level"),
                children=[
                    GroupDefault(group="group1", value="file3"),
                    ConfigDefault(path="_self_"),
                ],
            ),
            id="override_same_level:external_override",
        ),
        param(
            "include_override_same_level",
            [],
            DefaultsTreeNode(
                node=ConfigDefault(path="include_override_same_level"),
                children=[
                    DefaultsTreeNode(
                        node=GroupDefault(
                            group="group1",
                            value="override_same_level",
                        ),
                        children=[
                            GroupDefault(
                                group="group2",
                                value="file2",
                            ),
                            ConfigDefault(path="_self_"),
                        ],
                    ),
                    ConfigDefault(path="_self_"),
                ],
            ),
            id="include_override_same_level",
        ),
        param(
            "include_override_same_level",
            ["group1/group2=file3"],
            DefaultsTreeNode(
                node=ConfigDefault(path="include_override_same_level"),
                children=[
                    DefaultsTreeNode(
                        node=GroupDefault(
                            group="group1",
                            value="override_same_level",
                        ),
                        children=[
                            GroupDefault(
                                group="group2",
                                value="file3",
                            ),
                            ConfigDefault(path="_self_"),
                        ],
                    ),
                    ConfigDefault(path="_self_"),
                ],
            ),
            id="include_override_same_level:external_override",
        ),
        param(
            "override_nested_group_item",
            [],
            DefaultsTreeNode(
                node=ConfigDefault(path="override_nested_group_item"),
                children=[
                    DefaultsTreeNode(
                        node=GroupDefault(group="group1", value="group_item1"),
                        children=[
                            GroupDefault(group="group2", value="file2"),
                            ConfigDefault(path="_self_"),
                        ],
                    ),
                    ConfigDefault(path="_self_"),
                ],
            ),
            id="override_nested_group_item",
        ),
        param(
            "override_nested_group_item",
            ["group1/group2=file3"],
            DefaultsTreeNode(
                node=ConfigDefault(path="override_nested_group_item"),
                children=[
                    DefaultsTreeNode(
                        node=GroupDefault(group="group1", value="group_item1"),
                        children=[
                            GroupDefault(group="group2", value="file3"),
                            ConfigDefault(path="_self_"),
                        ],
                    ),
                    ConfigDefault(path="_self_"),
                ],
            ),
            id="override_nested_group_item:external_override",
        ),
        param(
            "override_wrong_order",
            [],
            raises(
                ConfigCompositionException,
                match=re.escape(
                    dedent("""\
                        In override_wrong_order: Override 'group1 : file2' is defined before 'group1: file1'.
                        Overrides must be at the end of the defaults list""")
                ),
            ),
            id="test_override_wrong_order_in_defaults_list",
        ),
        param(
            "override_list",
            [],
            raises(
                ConfigCompositionException,
                match=re.escape(
                    dedent("""\
                        In override_list: Override 'group1 : file2' is defined before 'group1: ['file1', 'file2']'.
                        Overrides must be at the end of the defaults list""")
                ),
            ),
            id="test_override_before_list_in_defaults_list",
        ),
    ],
)
def test_override_option_from_defaults_list(
    config_name: str,
    overrides: list[str],
    expected: DefaultsTreeNode,
) -> None:
    _test_defaults_tree_impl(
        config_name=config_name, input_overrides=overrides, expected=expected
    )


@mark.parametrize(
    "config_name, overrides, expected",
    [
        param(
            "two_group_defaults_different_pkgs",
            [],
            DefaultsTreeNode(
                node=ConfigDefault(path="two_group_defaults_different_pkgs"),
                children=[
                    GroupDefault(group="group1", value="file1", package="pkg1"),
                    GroupDefault(group="group1", value="file1", package="pkg2"),
                    ConfigDefault(path="_self_"),
                ],
            ),
            id="two_group_defaults_different_pkgs",
        ),
        param(
            "two_group_defaults_different_pkgs",
            ["group1@pkg1=file2"],
            DefaultsTreeNode(
                node=ConfigDefault(path="two_group_defaults_different_pkgs"),
                children=[
                    GroupDefault(group="group1", value="file2", package="pkg1"),
                    GroupDefault(group="group1", value="file1", package="pkg2"),
                    ConfigDefault(path="_self_"),
                ],
            ),
            id="two_group_defaults_different_pkgs:override_first",
        ),
        param(
            "two_group_defaults_different_pkgs",
            ["group1@pkg2=file2"],
            DefaultsTreeNode(
                node=ConfigDefault(path="two_group_defaults_different_pkgs"),
                children=[
                    GroupDefault(group="group1", value="file1", package="pkg1"),
                    GroupDefault(group="group1", value="file2", package="pkg2"),
                    ConfigDefault(path="_self_"),
                ],
            ),
            id="two_group_defaults_different_pkgs:override_second",
        ),
        param(
            "two_group_defaults_different_pkgs_global",
            [],
            DefaultsTreeNode(
                node=ConfigDefault(path="two_group_defaults_different_pkgs_global"),
                children=[
                    GroupDefault(group="group1", value="file1"),
                    GroupDefault(group="group1", value="file2", package="_global_"),
                    ConfigDefault(path="_self_"),
                ],
            ),
            id="two_group_defaults_different_pkgs_global",
        ),
    ],
)
def test_two_group_defaults_different_pkgs(
    config_name: str,
    overrides: list[str],
    expected: DefaultsTreeNode,
) -> None:
    _test_defaults_tree_impl(
        config_name=config_name, input_overrides=overrides, expected=expected
    )


@mark.parametrize(
    "config_name,overrides,expected",
    [
        param(
            "override_hydra2",
            [],
            DefaultsTreeNode(
                node=VirtualRoot(),
                children=[
                    DefaultsTreeNode(
                        node=ConfigDefault(path="hydra/config"),
                        children=[
                            GroupDefault(group="help", value="custom1"),
                            GroupDefault(group="output", value="default"),
                            ConfigDefault(path="_self_"),
                        ],
                    ),
                    ConfigDefault(path="override_hydra2"),
                ],
            ),
            id="override_hydra2",
        ),
        param(
            "override_hydra2",
            ["hydra/help=custom2"],
            DefaultsTreeNode(
                node=VirtualRoot(),
                children=[
                    DefaultsTreeNode(
                        node=ConfigDefault(path="hydra/config"),
                        children=[
                            GroupDefault(group="help", value="custom2"),
                            GroupDefault(group="output", value="default"),
                            ConfigDefault(path="_self_"),
                        ],
                    ),
                    ConfigDefault(path="override_hydra2"),
                ],
            ),
            id="override_hydra2+external",
        ),
        param(
            "override_hydra3",
            [],
            DefaultsTreeNode(
                node=VirtualRoot(),
                children=[
                    DefaultsTreeNode(
                        node=ConfigDefault(path="hydra/config"),
                        children=[
                            GroupDefault(group="help", value="custom1"),
                            GroupDefault(group="output", value="disabled"),
                            ConfigDefault(path="_self_"),
                        ],
                    ),
                    ConfigDefault(path="override_hydra3"),
                ],
            ),
            id="override_hydra3+external",
        ),
        param(
            "override_hydra_wrong_order",
            [],
            raises(
                ConfigCompositionException,
                match=re.escape(
                    dedent(
                        """\
                    In override_hydra_wrong_order: Override 'hydra/help : custom1' is defined before 'group1: file1'"""
                    )
                ),
            ),
            id="override_hydra_wrong_order",
        ),
    ],
)
def test_hydra_overrides_from_primary_config(
    config_name: str,
    overrides: list[str],
    expected: DefaultsTreeNode,
) -> None:
    _test_defaults_tree_impl(
        config_name=config_name,
        input_overrides=overrides,
        expected=expected,
        prepend_hydra=True,
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
            id="legacy_override_hydra-error",
        ),
        param(
            "legacy_override_hydra2",
            [],
            raises(
                ConfigCompositionException,
                match=re.escape(
                    dedent(
                        """\
                        Multiple values for hydra/output. To override a value use 'override hydra/output: disabled'"""
                    )
                ),
            ),
            id="legacy_override_hydra2-error",
        ),
        param(
            "legacy_override_hydra_wrong_order",
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
            id="legacy_override_hydra_wrong_order",
        ),
    ],
)
def test_legacy_override_hydra_is_rejected(
    config_name: str,
    overrides: list[str],
    expected: DefaultsTreeNode,
    hydra_restore_singletons: Any,
) -> None:
    _test_defaults_tree_impl(
        config_name=config_name,
        input_overrides=overrides,
        expected=expected,
        prepend_hydra=True,
    )


@mark.parametrize(
    "config_name,overrides,expected",
    [
        param(
            "legacy_override_hydra2",
            [],
            raises(
                ConfigCompositionException,
                match=re.escape(
                    "Multiple values for hydra/output. To override a value use "
                    "'override hydra/output: disabled'"
                ),
            ),
            id="legacy_override_hydra2-error",
        ),
    ],
)
def test_legacy_hydra_overrides_from_primary_config_are_rejected(
    config_name: str, overrides: list[str], expected: DefaultsTreeNode
) -> None:
    _test_defaults_tree_impl(
        config_name=config_name,
        input_overrides=overrides,
        expected=expected,
        prepend_hydra=True,
    )


@mark.parametrize(
    "config_name,overrides,expected",
    [
        param(
            "group_default_with_explicit_experiment",
            [],
            DefaultsTreeNode(
                node=ConfigDefault(path="group_default_with_explicit_experiment"),
                children=[
                    GroupDefault(group="group1", value="file2"),
                    GroupDefault(group="experiment", value="override_config_group"),
                    ConfigDefault(path="_self_"),
                ],
            ),
            id="group_default_with_explicit_experiment",
        ),
        param(
            "group_default_with_explicit_experiment",
            ["group1=file3"],
            DefaultsTreeNode(
                node=ConfigDefault(path="group_default_with_explicit_experiment"),
                children=[
                    GroupDefault(group="group1", value="file3"),
                    GroupDefault(group="experiment", value="override_config_group"),
                    ConfigDefault(path="_self_"),
                ],
            ),
            id="group_default_with_explicit_experiment:with_external_override",
        ),
        param(
            "group_default_after_explicit_experiment",
            [],
            DefaultsTreeNode(
                node=ConfigDefault(path="group_default_after_explicit_experiment"),
                children=[
                    GroupDefault(group="experiment", value="override_config_group"),
                    GroupDefault(group="group1", value="file3"),
                    ConfigDefault(path="_self_"),
                ],
            ),
            id="group_default_after_explicit_experiment",
        ),
        param(
            "group_default_with_explicit_experiment_and_override",
            [],
            DefaultsTreeNode(
                node=ConfigDefault(
                    path="group_default_with_explicit_experiment_and_override"
                ),
                children=[
                    GroupDefault(group="group1", value="file3"),
                    GroupDefault(group="experiment", value="override_config_group"),
                    ConfigDefault(path="_self_"),
                ],
            ),
            id="group_default_with_explicit_experiment_and_override",
        ),
        param(
            "group_default_with_explicit_experiment_and_override",
            ["group1=file1"],
            DefaultsTreeNode(
                node=ConfigDefault(
                    path="group_default_with_explicit_experiment_and_override"
                ),
                children=[
                    GroupDefault(group="group1", value="file1"),
                    GroupDefault(group="experiment", value="override_config_group"),
                    ConfigDefault(path="_self_"),
                ],
            ),
            id="group_default_with_explicit_experiment_and_override:with_external_override",
        ),
    ],
)
def test_group_default_with_explicit_experiment(
    config_name: str,
    overrides: list[str],
    expected: DefaultsTreeNode,
) -> None:
    _test_defaults_tree_impl(
        config_name=config_name,
        input_overrides=overrides,
        expected=expected,
    )


@mark.parametrize(
    "config_name,overrides,expected",
    [
        param(
            "group_default",
            ["+experiment=override_config_group"],
            DefaultsTreeNode(
                node=ConfigDefault(path="group_default"),
                children=[
                    GroupDefault(group="group1", value="file2"),
                    ConfigDefault(path="_self_"),
                    GroupDefault(group="experiment", value="override_config_group"),
                ],
            ),
            id="group_default_with_appended_experiment",
        ),
        param(
            "group_default",
            ["group1=file3", "+experiment=override_config_group"],
            DefaultsTreeNode(
                node=ConfigDefault(path="group_default"),
                children=[
                    GroupDefault(group="group1", value="file3"),
                    ConfigDefault(path="_self_"),
                    GroupDefault(group="experiment", value="override_config_group"),
                ],
            ),
            id="group_default_with_appended_experiment:with_external_override",
        ),
        param(
            "group_default_with_override",
            ["+experiment=override_config_group"],
            DefaultsTreeNode(
                node=ConfigDefault(path="group_default_with_override"),
                children=[
                    GroupDefault(group="group1", value="file2"),
                    ConfigDefault(path="_self_"),
                    GroupDefault(group="experiment", value="override_config_group"),
                ],
            ),
            id="group_default_with_override_with_appended_experiment",
        ),
        param(
            "group_default_with_override",
            ["group1=file1", "+experiment=override_config_group"],
            DefaultsTreeNode(
                node=ConfigDefault(path="group_default_with_override"),
                children=[
                    GroupDefault(group="group1", value="file1"),
                    ConfigDefault(path="_self_"),
                    GroupDefault(group="experiment", value="override_config_group"),
                ],
            ),
            id="group_default_with_override_with_appended_experiment:with_external_override",
        ),
    ],
)
def test_group_default_with_appended_experiment(
    config_name: str,
    overrides: list[str],
    expected: DefaultsTreeNode,
) -> None:
    _test_defaults_tree_impl(
        config_name=config_name,
        input_overrides=overrides,
        expected=expected,
    )


@mark.parametrize(
    "config_name,overrides,expected",
    [
        param(
            "override_hydra1",
            ["+experiment=override_config_group"],
            DefaultsTreeNode(
                node=VirtualRoot(),
                children=[
                    DefaultsTreeNode(
                        node=ConfigDefault(path="hydra/config"),
                        children=[
                            GroupDefault(group="help", value="default"),
                            GroupDefault(group="output", value="disabled"),
                            ConfigDefault(path="_self_"),
                        ],
                    ),
                    DefaultsTreeNode(
                        node=ConfigDefault(path="override_hydra1"),
                        children=[
                            GroupDefault(group="group1", value="file2"),
                            ConfigDefault(path="_self_"),
                            GroupDefault(
                                group="experiment", value="override_config_group"
                            ),
                        ],
                    ),
                ],
            ),
            id="override_hydra_with_experiment",
        ),
    ],
)
def test_experiment_where_primary_config_has_override(
    config_name: str,
    overrides: list[str],
    expected: DefaultsTreeNode,
) -> None:
    _test_defaults_tree_impl(
        config_name=config_name,
        input_overrides=overrides,
        expected=expected,
        prepend_hydra=True,
    )


@mark.parametrize(
    "config_name,overrides,expected",
    [
        param(
            "override_hydra4",
            [],
            DefaultsTreeNode(
                node=VirtualRoot(),
                children=[
                    DefaultsTreeNode(
                        node=ConfigDefault(path="hydra/config"),
                        children=[
                            GroupDefault(group="help", value="default"),
                            GroupDefault(group="output", value="disabled"),
                            ConfigDefault(path="_self_"),
                        ],
                    ),
                    DefaultsTreeNode(
                        node=ConfigDefault(path="override_hydra4"),
                        children=[
                            GroupDefault(group="group1", value="file1"),
                            GroupDefault(group="hydra/run", value="custom1"),
                            ConfigDefault(path="_self_"),
                        ],
                    ),
                ],
            ),
            id="override_hydra4",
        ),
    ],
)
def test_use_of_custom_subgroup_of_hydra(
    config_name: str,
    overrides: list[str],
    expected: DefaultsTreeNode,
    hydra_restore_singletons: Any,
) -> None:
    _test_defaults_tree_impl(
        config_name=config_name,
        input_overrides=overrides,
        expected=expected,
        prepend_hydra=True,
    )


@mark.parametrize(
    "config_name,overrides,expected",
    [
        param(
            "group_default",
            ["+experiment=include_absolute_config"],
            DefaultsTreeNode(
                node=ConfigDefault(path="group_default"),
                children=[
                    GroupDefault(group="group1", value="file1"),
                    ConfigDefault(path="_self_"),
                    DefaultsTreeNode(
                        node=GroupDefault(
                            group="experiment", value="include_absolute_config"
                        ),
                        children=[
                            GroupDefault(group="/group1/group2", value="file1"),
                            ConfigDefault(path="_self_"),
                        ],
                    ),
                ],
            ),
            id="include_absolute_config",
        ),
        param(
            "group_default",
            ["+experiment=include_absolute_config", "group1/group2=file2"],
            DefaultsTreeNode(
                node=ConfigDefault(path="group_default"),
                children=[
                    GroupDefault(group="group1", value="file1"),
                    ConfigDefault(path="_self_"),
                    DefaultsTreeNode(
                        node=GroupDefault(
                            group="experiment", value="include_absolute_config"
                        ),
                        children=[
                            GroupDefault(group="/group1/group2", value="file2"),
                            ConfigDefault(path="_self_"),
                        ],
                    ),
                ],
            ),
            id="include_absolute_config:with_external_override",
        ),
    ],
)
def test_experiment_include_absolute_config(
    config_name: str,
    overrides: list[str],
    expected: DefaultsTreeNode,
) -> None:
    _test_defaults_tree_impl(
        config_name=config_name, input_overrides=overrides, expected=expected
    )


@mark.parametrize(
    "config_name,overrides,expected",
    [
        param(
            "group_default",
            ["+experiment=override_hydra"],
            DefaultsTreeNode(
                node=VirtualRoot(),
                children=[
                    DefaultsTreeNode(
                        node=ConfigDefault(path="hydra/config"),
                        children=[
                            GroupDefault(group="help", value="custom1"),
                            GroupDefault(group="output", value="default"),
                            ConfigDefault(path="_self_"),
                        ],
                    ),
                    DefaultsTreeNode(
                        node=ConfigDefault(path="group_default"),
                        children=[
                            GroupDefault(group="group1", value="file1"),
                            ConfigDefault(path="_self_"),
                            GroupDefault(group="experiment", value="override_hydra"),
                        ],
                    ),
                ],
            ),
            id="experiment_overriding_hydra_group",
        ),
        param(
            "group_default",
            ["+experiment=override_hydra", "hydra/help=custom2"],
            DefaultsTreeNode(
                node=VirtualRoot(),
                children=[
                    DefaultsTreeNode(
                        node=ConfigDefault(path="hydra/config"),
                        children=[
                            GroupDefault(group="help", value="custom2"),
                            GroupDefault(group="output", value="default"),
                            ConfigDefault(path="_self_"),
                        ],
                    ),
                    DefaultsTreeNode(
                        node=ConfigDefault(path="group_default"),
                        children=[
                            GroupDefault(group="group1", value="file1"),
                            ConfigDefault(path="_self_"),
                            GroupDefault(group="experiment", value="override_hydra"),
                        ],
                    ),
                ],
            ),
            id="experiment_overriding_hydra_group:with_external_hydra_override",
        ),
    ],
)
def test_experiment_overriding_hydra_group(
    config_name: str,
    overrides: list[str],
    expected: DefaultsTreeNode,
) -> None:
    _test_defaults_tree_impl(
        config_name=config_name,
        input_overrides=overrides,
        expected=expected,
        prepend_hydra=True,
    )


@mark.parametrize(
    "config_name,overrides,expected",
    [
        param(
            "group_default",
            ["+experiment=override_with_global_default"],
            DefaultsTreeNode(
                node=ConfigDefault(path="group_default"),
                children=[
                    GroupDefault(group="group1", value="file2"),
                    ConfigDefault(path="_self_"),
                    GroupDefault(
                        group="experiment", value="override_with_global_default"
                    ),
                ],
            ),
            id="include_absolute_config:override_with_global_default",
        ),
        param(
            "group_default_at_global",
            ["+experiment=override_with_global_default2"],
            DefaultsTreeNode(
                node=ConfigDefault(path="group_default_at_global"),
                children=[
                    GroupDefault(group="group1", value="file2", package="_global_"),
                    ConfigDefault(path="_self_"),
                    GroupDefault(
                        group="experiment", value="override_with_global_default2"
                    ),
                ],
            ),
            id="include_absolute_config:override_with_global_default2",
        ),
    ],
)
def test_experiment_overriding_global_group(
    config_name: str,
    overrides: list[str],
    expected: DefaultsTreeNode,
) -> None:
    _test_defaults_tree_impl(
        config_name=config_name,
        input_overrides=overrides,
        expected=expected,
        prepend_hydra=False,
    )


@mark.parametrize(
    "config_name,overrides,expected",
    [
        param(
            "experiment/override_hydra",
            [],
            DefaultsTreeNode(
                node=VirtualRoot(),
                children=[
                    DefaultsTreeNode(
                        node=ConfigDefault(path="hydra/config"),
                        children=[
                            GroupDefault(group="help", value="custom1"),
                            GroupDefault(group="output", value="default"),
                            ConfigDefault(path="_self_"),
                        ],
                    ),
                    ConfigDefault(path="experiment/override_hydra"),
                ],
            ),
            id="experiment_overriding_hydra_group_as_primary",
        ),
    ],
)
def test_experiment_as_primary_config(
    config_name: str,
    overrides: list[str],
    expected: DefaultsTreeNode,
) -> None:
    _test_defaults_tree_impl(
        config_name=config_name,
        input_overrides=overrides,
        expected=expected,
        prepend_hydra=True,
    )


@mark.parametrize(
    "config_name,overrides,expected",
    [
        param(
            "test_extend_same_group",
            [],
            DefaultsTreeNode(
                node=ConfigDefault(path="test_extend_same_group"),
                children=[
                    DefaultsTreeNode(
                        node=GroupDefault(group="extend", value="here"),
                        children=[
                            ConfigDefault(path="base_db"),
                            ConfigDefault(path="_self_"),
                        ],
                    ),
                    ConfigDefault(path="_self_"),
                ],
            ),
            id="test_extend_same_group",
        ),
        param(
            "test_extend_from_external_group",
            [],
            DefaultsTreeNode(
                node=ConfigDefault(path="test_extend_from_external_group"),
                children=[
                    DefaultsTreeNode(
                        node=GroupDefault(group="extend", value="external"),
                        children=[
                            ConfigDefault(path="/db/base_db", package=""),
                            ConfigDefault(path="_self_"),
                        ],
                    ),
                    ConfigDefault(path="_self_"),
                ],
            ),
            id="test_extend_from_external_group",
        ),
        param(
            "test_extend_from_nested_group",
            [],
            DefaultsTreeNode(
                node=ConfigDefault(path="test_extend_from_nested_group"),
                children=[
                    DefaultsTreeNode(
                        node=GroupDefault(group="extend", value="nested"),
                        children=[
                            ConfigDefault(path="nested/base_db", package=""),
                            ConfigDefault(path="_self_"),
                        ],
                    ),
                    ConfigDefault(path="_self_"),
                ],
            ),
            id="test_extend_from_nested_group",
        ),
        param(
            "test_extend_from_nested_group",
            ["extend=nested_here_keyword"],
            DefaultsTreeNode(
                node=ConfigDefault(path="test_extend_from_nested_group"),
                children=[
                    DefaultsTreeNode(
                        node=GroupDefault(group="extend", value="nested_here_keyword"),
                        children=[
                            ConfigDefault(path="nested/base_db", package=""),
                            ConfigDefault(path="_self_"),
                        ],
                    ),
                    ConfigDefault(path="_self_"),
                ],
            ),
            id="nested_here_keyword",
        ),
    ],
)
def test_extension_use_cases(
    config_name: str,
    overrides: list[str],
    expected: DefaultsTreeNode,
) -> None:
    _test_defaults_tree_impl(
        config_name=config_name,
        input_overrides=overrides,
        expected=expected,
    )


@mark.parametrize(
    "config_name,overrides,expected",
    [
        param(
            "config_with_same_name_as_group",
            [],
            DefaultsTreeNode(
                node=ConfigDefault(path="config_with_same_name_as_group"),
                children=[
                    GroupDefault(
                        group="config_with_same_name_as_group",
                        value="item",
                    ),
                    ConfigDefault(path="_self_"),
                ],
            ),
            id="config_with_same_name_as_group",
        ),
        param(
            "include_group_with_same_name_as_config",
            [],
            DefaultsTreeNode(
                node=ConfigDefault(path="include_group_with_same_name_as_config"),
                children=[
                    GroupDefault(
                        group="config_with_same_name_as_group",
                        value="item",
                    ),
                    ConfigDefault(path="_self_"),
                ],
            ),
            id="include_group_with_same_name_as_config",
        ),
        param(
            "test_extend_from_config_with_same_name_as_group",
            [],
            DefaultsTreeNode(
                node=ConfigDefault(
                    path="test_extend_from_config_with_same_name_as_group"
                ),
                children=[
                    DefaultsTreeNode(
                        node=ConfigDefault(path="config_with_same_name_as_group"),
                        children=[
                            GroupDefault(
                                group="config_with_same_name_as_group", value="item"
                            ),
                            ConfigDefault(path="_self_"),
                        ],
                    ),
                    ConfigDefault(path="_self_"),
                ],
            ),
            id="test_extend_from_config_with_same_name_as_group",
        ),
        param(
            "test_extend_from_group_with_same_name_as_config",
            [],
            DefaultsTreeNode(
                node=ConfigDefault(
                    path="test_extend_from_group_with_same_name_as_config"
                ),
                children=[
                    ConfigDefault(path="config_with_same_name_as_group/item"),
                    ConfigDefault(path="_self_"),
                ],
            ),
            id="test_extend_from_group_with_same_name_as_config",
        ),
    ],
)
def test_name_collision(
    config_name: str,
    overrides: list[str],
    expected: DefaultsTreeNode,
) -> None:
    _test_defaults_tree_impl(
        config_name=config_name,
        input_overrides=overrides,
        expected=expected,
    )


@mark.parametrize(
    "config_name,overrides,expected",
    [
        param(
            "with_missing",
            [],
            raises(
                ConfigCompositionException,
                match=dedent("""\
                In 'with_missing': You must specify 'db', e.g, db=<OPTION>
                Available options:"""),
            ),
            id="with_missing",
        ),
        param(
            "with_missing_at_global",
            [],
            raises(
                ConfigCompositionException,
                match=dedent("""\
                You must specify 'db@_global_', e.g, db@_global_=<OPTION>
                Available options:"""),
            ),
            id="with_missing_at_global",
        ),
        param(
            "with_missing",
            ["db=base_db"],
            DefaultsTreeNode(
                node=ConfigDefault(path="with_missing"),
                children=[
                    GroupDefault(group="db", value="base_db"),
                    ConfigDefault(path="_self_"),
                ],
            ),
            id="with_missing:override",
        ),
        param(
            "with_missing_at_foo",
            [],
            raises(
                ConfigCompositionException,
                match=dedent("""\
                You must specify 'db@foo', e.g, db@foo=<OPTION>
                Available options:"""),
            ),
            id="with_missing_at_foo",
        ),
        param(
            "with_missing_at_foo",
            ["db@foo=base_db"],
            DefaultsTreeNode(
                node=ConfigDefault(path="with_missing_at_foo"),
                children=[
                    GroupDefault(group="db", value="base_db", package="foo"),
                    ConfigDefault(path="_self_"),
                ],
            ),
            id="with_missing_at_foo:override",
        ),
        param(
            "empty",
            ["+group1=with_missing"],
            raises(
                ConfigCompositionException,
                match=dedent("""\
                    In 'group1/with_missing': You must specify 'group1/group2', e.g, group1/group2=<OPTION>
                    Available options"""),
            ),
            id="nested_missing",
        ),
        param(
            "empty",
            ["+group1=with_missing", "group1/group2=file1"],
            DefaultsTreeNode(
                node=ConfigDefault(path="empty"),
                children=[
                    ConfigDefault(path="_self_"),
                    DefaultsTreeNode(
                        node=GroupDefault(group="group1", value="with_missing"),
                        children=[
                            GroupDefault(group="group2", value="file1"),
                            ConfigDefault(path="_self_"),
                        ],
                    ),
                ],
            ),
            id="nested_missing:override",
        ),
        param(
            "empty",
            ["+group1=with_missing_at_foo"],
            raises(
                ConfigCompositionException,
                match=dedent("""\
                    You must specify 'group1/group2@group1.foo', e.g, group1/group2@group1.foo=<OPTION>
                    Available options"""),
            ),
            id="nested_missing_at_foo",
        ),
        param(
            "empty",
            ["+group1=with_missing_at_foo", "group1/group2@group1.foo=file1"],
            DefaultsTreeNode(
                node=ConfigDefault(path="empty"),
                children=[
                    ConfigDefault(path="_self_"),
                    DefaultsTreeNode(
                        node=GroupDefault(group="group1", value="with_missing_at_foo"),
                        children=[
                            GroupDefault(group="group2", value="file1", package="foo"),
                            ConfigDefault(path="_self_"),
                        ],
                    ),
                ],
            ),
            id="nested_missing_at_foo:override",
        ),
    ],
)
def test_with_missing(
    config_name: str,
    overrides: list[str],
    expected: DefaultsTreeNode,
) -> None:
    _test_defaults_tree_impl(
        config_name=config_name,
        input_overrides=overrides,
        expected=expected,
    )


@mark.parametrize(
    "config_name,overrides,expected",
    [
        param(
            "with_missing",
            [],
            DefaultsTreeNode(
                node=ConfigDefault(path="with_missing"),
                children=[
                    GroupDefault(group="db", value="???"),
                    ConfigDefault(path="_self_"),
                ],
            ),
            id="with_missing",
        ),
    ],
)
def test_with_missing_and_skip_missing_flag(
    config_name: str,
    overrides: list[str],
    expected: DefaultsTreeNode,
) -> None:
    _test_defaults_tree_impl(
        config_name=config_name,
        input_overrides=overrides,
        expected=expected,
        skip_missing=True,
    )


@mark.parametrize(
    "config_name,overrides,expected",
    [
        param(
            "placeholder",
            [],
            DefaultsTreeNode(
                node=ConfigDefault(path="placeholder"),
                children=[
                    GroupDefault(group="group1"),
                    ConfigDefault(path="_self_"),
                ],
            ),
            id="placeholder",
        ),
        param(
            "placeholder",
            ["group1=file1"],
            DefaultsTreeNode(
                node=ConfigDefault(path="placeholder"),
                children=[
                    GroupDefault(group="group1", value="file1"),
                    ConfigDefault(path="_self_"),
                ],
            ),
            id="placeholder:override",
        ),
        param(
            "nested_placeholder",
            [],
            DefaultsTreeNode(
                node=ConfigDefault(path="nested_placeholder"),
                children=[
                    DefaultsTreeNode(
                        node=GroupDefault(group="group1", value="placeholder"),
                        children=[
                            GroupDefault(group="group2"),
                            ConfigDefault(path="_self_"),
                        ],
                    ),
                    ConfigDefault(path="_self_"),
                ],
            ),
            id="nested_placeholder",
        ),
        param(
            "nested_placeholder",
            ["group1/group2=file1"],
            DefaultsTreeNode(
                node=ConfigDefault(path="nested_placeholder"),
                children=[
                    DefaultsTreeNode(
                        node=GroupDefault(group="group1", value="placeholder"),
                        children=[
                            GroupDefault(group="group2", value="file1"),
                            ConfigDefault(path="_self_"),
                        ],
                    ),
                    ConfigDefault(path="_self_"),
                ],
            ),
            id="nested_placeholder:override",
        ),
    ],
)
def test_placeholder(
    config_name: str,
    overrides: list[str],
    expected: DefaultsTreeNode,
) -> None:
    _test_defaults_tree_impl(
        config_name=config_name,
        input_overrides=overrides,
        expected=expected,
    )


@mark.parametrize(
    "config_name,overrides,expected",
    [
        param(
            "interpolation_simple",
            [],
            DefaultsTreeNode(
                node=ConfigDefault(path="interpolation_simple"),
                children=[
                    GroupDefault(group="group1", value="file1"),
                    GroupDefault(group="group2", value="file2"),
                    GroupDefault(group="group1_group2", value="file1_file2"),
                    ConfigDefault(path="_self_"),
                ],
            ),
            id="interpolation_simple",
        ),
        param(
            "interpolation_simple",
            ["group1=file2"],
            DefaultsTreeNode(
                node=ConfigDefault(path="interpolation_simple"),
                children=[
                    GroupDefault(group="group1", value="file2"),
                    GroupDefault(group="group2", value="file2"),
                    GroupDefault(group="group1_group2", value="file2_file2"),
                    ConfigDefault(path="_self_"),
                ],
            ),
            id="interpolation_simple:override",
        ),
        param(
            "interpolation_forward",
            [],
            DefaultsTreeNode(
                node=ConfigDefault(path="interpolation_forward"),
                children=[
                    GroupDefault(group="group1_group2", value="file1_file2"),
                    GroupDefault(group="group1", value="file1"),
                    GroupDefault(group="group2", value="file2"),
                    ConfigDefault(path="_self_"),
                ],
            ),
            id="interpolation_forward",
        ),
        param(
            "interpolation_forward",
            ["group1=file2"],
            DefaultsTreeNode(
                node=ConfigDefault(path="interpolation_forward"),
                children=[
                    GroupDefault(group="group1_group2", value="file2_file2"),
                    GroupDefault(group="group1", value="file2"),
                    GroupDefault(group="group2", value="file2"),
                    ConfigDefault(path="_self_"),
                ],
            ),
            id="interpolation_forward:override",
        ),
        param(
            "interpolation_nested",
            [],
            DefaultsTreeNode(
                node=ConfigDefault(path="interpolation_nested"),
                children=[
                    GroupDefault(group="group1/group2", value="file1"),
                    GroupDefault(group="group1_group2", value="foo_file1"),
                    ConfigDefault(path="_self_"),
                ],
            ),
            id="interpolation_nested",
        ),
        param(
            "interpolation_nested",
            ["group1/group2=file2"],
            DefaultsTreeNode(
                node=ConfigDefault(path="interpolation_nested"),
                children=[
                    GroupDefault(group="group1/group2", value="file2"),
                    GroupDefault(group="group1_group2", value="foo_file2"),
                    ConfigDefault(path="_self_"),
                ],
            ),
            id="interpolation_nested:override",
        ),
        param(
            "interpolation_with_package_override",
            [],
            DefaultsTreeNode(
                node=ConfigDefault(path="interpolation_with_package_override"),
                children=[
                    GroupDefault(group="group1", value="file1", package="package"),
                    GroupDefault(group="group2", value="file2"),
                    GroupDefault(group="group1_group2", value="file1_file2"),
                    ConfigDefault(path="_self_"),
                ],
            ),
            id="interpolation_with_package_override",
        ),
        param(
            "interpolation_with_package_override",
            ["group1@package=file2"],
            DefaultsTreeNode(
                node=ConfigDefault(path="interpolation_with_package_override"),
                children=[
                    GroupDefault(group="group1", value="file2", package="package"),
                    GroupDefault(group="group2", value="file2"),
                    GroupDefault(group="group1_group2", value="file2_file2"),
                    ConfigDefault(path="_self_"),
                ],
            ),
            id="interpolation_with_package_override:override",
        ),
        param(
            "interpolation_with_nested_package_override",
            [],
            DefaultsTreeNode(
                node=ConfigDefault(path="interpolation_with_nested_package_override"),
                children=[
                    DefaultsTreeNode(
                        node=GroupDefault(group="group1", value="group_item1_pkg2"),
                        children=[
                            GroupDefault(group="group2", value="file1", package="pkg2"),
                            ConfigDefault(path="_self_"),
                        ],
                    ),
                    GroupDefault(group="group2", value="file1"),
                    ConfigDefault(path="_self_"),
                ],
            ),
            id="interpolation_with_nested_package_override",
        ),
        param(
            "interpolation_with_nested_package_override",
            ["group1/group2@group1.pkg2=file2"],
            DefaultsTreeNode(
                node=ConfigDefault(path="interpolation_with_nested_package_override"),
                children=[
                    DefaultsTreeNode(
                        node=GroupDefault(group="group1", value="group_item1_pkg2"),
                        children=[
                            GroupDefault(group="group2", value="file2", package="pkg2"),
                            ConfigDefault(path="_self_"),
                        ],
                    ),
                    GroupDefault(group="group2", value="file2"),
                    ConfigDefault(path="_self_"),
                ],
            ),
            id="interpolation_with_nested_package_override:override",
        ),
        param(
            "interpolation_with_nested_defaults_list",
            [],
            DefaultsTreeNode(
                node=ConfigDefault(path="interpolation_with_nested_defaults_list"),
                children=[
                    GroupDefault(group="group1", value="file1"),
                    GroupDefault(group="group2", value="file1"),
                    DefaultsTreeNode(
                        node=GroupDefault(
                            group="group1_group2",
                            value="file1_file1_with_defaults_list",
                        ),
                        children=[
                            ConfigDefault(path="empty1"),
                            ConfigDefault(path="_self_"),
                        ],
                    ),
                    ConfigDefault(path="_self_"),
                ],
            ),
            id="interpolation_with_nested_defaults_list",
        ),
        param(
            "interpolation_with_nested_defaults_list",
            ["group2=file2"],
            DefaultsTreeNode(
                node=ConfigDefault(path="interpolation_with_nested_defaults_list"),
                children=[
                    GroupDefault(group="group1", value="file1"),
                    GroupDefault(group="group2", value="file2"),
                    DefaultsTreeNode(
                        node=GroupDefault(
                            group="group1_group2",
                            value="file1_file2_with_defaults_list",
                        ),
                        children=[
                            ConfigDefault(path="empty2"),
                            ConfigDefault(path="_self_"),
                        ],
                    ),
                    ConfigDefault(path="_self_"),
                ],
            ),
            id="interpolation_with_nested_defaults_list:override",
        ),
        param(
            "interpolation_with_nested_defaults_list_with_override",
            [],
            raises(
                ConfigCompositionException,
                match=re.escape(
                    dedent("""\
                group1_group2/file1_file1_defaults_with_override: Default List Overrides are not allowed in the subtree
                of an in interpolated config group (override group1_group2/foo=bar).
                """)
                ),
            ),
            id="interpolation_with_nested_defaults_list_with_override",
        ),
        param(
            "interpolation_in_nested",
            [],
            DefaultsTreeNode(
                node=ConfigDefault(path="interpolation_in_nested"),
                children=[
                    DefaultsTreeNode(
                        node=GroupDefault(group="group1", value="interpolation"),
                        children=[
                            GroupDefault(group="group2", value="interpolation_ext"),
                            ConfigDefault(path="_self_"),
                        ],
                    ),
                    ConfigDefault(path="_self_"),
                ],
            ),
            id="interpolation_in_nested",
        ),
        param(
            "interpolation_resolver_in_nested",
            [],
            raises(
                ConfigCompositionException,
                match=re.escape(
                    "Error resolving interpolation '${oc.decode:file1}', "
                    "possible interpolation keys: group1"
                ),
            ),
            id="interpolation_resolver_in_nested",
        ),
        param(
            "interpolation_config_default",
            [],
            DefaultsTreeNode(
                node=ConfigDefault(path="interpolation_config_default"),
                children=[
                    GroupDefault(group="group1", value="file1"),
                    ConfigDefault(path="group1/group2/file1"),
                    ConfigDefault(path="_self_"),
                ],
            ),
            id="interpolation_config_default",
        ),
        param(
            "interpolation_config_default_in_nested",
            [],
            DefaultsTreeNode(
                node=ConfigDefault(path="interpolation_config_default_in_nested"),
                children=[
                    DefaultsTreeNode(
                        node=GroupDefault(
                            group="group1", value="config_default_interpolation"
                        ),
                        children=[
                            ConfigDefault(path="file1"),
                            ConfigDefault(path="_self_"),
                        ],
                    ),
                    GroupDefault(group="group2", value="file1"),
                    ConfigDefault(path="_self_"),
                ],
            ),
            id="interpolation_config_default_in_nested",
        ),
        param(
            "interpolation_config_default_absolute_in_nested",
            [],
            DefaultsTreeNode(
                node=ConfigDefault(
                    path="interpolation_config_default_absolute_in_nested"
                ),
                children=[
                    DefaultsTreeNode(
                        node=GroupDefault(
                            group="group1",
                            value="config_default_absolute_interpolation",
                        ),
                        children=[
                            ConfigDefault(path="/file1"),
                            ConfigDefault(path="_self_"),
                        ],
                    ),
                    GroupDefault(group="group2", value="file1"),
                    ConfigDefault(path="_self_"),
                ],
            ),
            id="interpolation_config_default_absolute_in_nested",
        ),
        param(
            "interpolation_bad_key",
            [],
            raises(
                ConfigCompositionException,
                match=re.escape(
                    "Error resolving interpolation '${not_found}', possible interpolation keys: group1"
                ),
            ),
            id="interpolation_bad_key",
        ),
    ],
)
def test_interpolation(
    config_name: str,
    overrides: list[str],
    expected: DefaultsTreeNode,
) -> None:
    _test_defaults_tree_impl(
        config_name=config_name,
        input_overrides=overrides,
        expected=expected,
    )


@mark.parametrize(
    "config_name,overrides,expected",
    [
        param(
            "interpolation_nested_sibling",
            [],
            DefaultsTreeNode(
                node=ConfigDefault(path="interpolation_nested_sibling"),
                children=[
                    GroupDefault(group="group1", value="file1"),
                    DefaultsTreeNode(
                        node=GroupDefault(
                            group="experiment",
                            value="interpolation_from_sibling",
                        ),
                        children=[
                            GroupDefault(group="/group2", value="file1"),
                            ConfigDefault(path="_self_"),
                        ],
                    ),
                    ConfigDefault(path="_self_"),
                ],
            ),
            id="nested_sibling",
        ),
        param(
            "empty",
            ["+group1=file1", "+experiment=interpolation_from_sibling"],
            DefaultsTreeNode(
                node=ConfigDefault(path="empty"),
                children=[
                    ConfigDefault(path="_self_"),
                    GroupDefault(group="group1", value="file1"),
                    DefaultsTreeNode(
                        node=GroupDefault(
                            group="experiment",
                            value="interpolation_from_sibling",
                        ),
                        children=[
                            GroupDefault(group="/group2", value="file1"),
                            ConfigDefault(path="_self_"),
                        ],
                    ),
                ],
            ),
            id="external_appends_dependency_first",
        ),
        param(
            "empty",
            ["+experiment=interpolation_from_sibling", "+group1=file1"],
            DefaultsTreeNode(
                node=ConfigDefault(path="empty"),
                children=[
                    ConfigDefault(path="_self_"),
                    DefaultsTreeNode(
                        node=GroupDefault(
                            group="experiment",
                            value="interpolation_from_sibling",
                        ),
                        children=[
                            GroupDefault(group="/group2", value="file1"),
                            ConfigDefault(path="_self_"),
                        ],
                    ),
                    GroupDefault(group="group1", value="file1"),
                ],
            ),
            id="external_appends_interpolation_first",
        ),
        param(
            "interpolation_dependency_chain",
            [],
            DefaultsTreeNode(
                node=ConfigDefault(path="interpolation_dependency_chain"),
                children=[
                    DefaultsTreeNode(
                        node=GroupDefault(group="source", value="file1"),
                        children=[
                            GroupDefault(group="/group2", value="file2"),
                            ConfigDefault(path="_self_"),
                        ],
                    ),
                    GroupDefault(group="target", value="file2"),
                    GroupDefault(group="group1", value="file1"),
                    ConfigDefault(path="_self_"),
                ],
            ),
            id="dependency_chain",
        ),
    ],
)
def test_interpolation_after_tree_traversal(
    config_name: str,
    overrides: list[str],
    expected: DefaultsTreeNode,
) -> None:
    _test_defaults_tree_impl(
        config_name=config_name,
        input_overrides=overrides,
        expected=expected,
    )


def test_interpolation_dependency_cycle() -> None:
    _test_defaults_tree_impl(
        config_name="interpolation_cycle",
        input_overrides=[],
        expected=raises(
            ConfigCompositionException,
            match=r"Error resolving interpolation '\$\{group[12]\}'",
        ),
    )


def test_deferred_interpolation_preserves_override_order() -> None:
    _test_defaults_tree_impl(
        config_name="interpolation_override_before_deferred_target",
        input_overrides=[],
        expected=raises(
            ConfigCompositionException,
            match=re.escape(
                "In 'override_group2_global': "
                "Invalid Defaults List override '/group2@_global_: file2'."
                "\nNo earlier Group Default for 'group2@_global_' exists to override."
            ),
        ),
    )


def test_deferred_interpolation_applies_later_override() -> None:
    _test_defaults_tree_impl(
        config_name="interpolation_override_after_deferred_target",
        input_overrides=[],
        expected=DefaultsTreeNode(
            node=ConfigDefault(path="interpolation_override_after_deferred_target"),
            children=[
                DefaultsTreeNode(
                    node=GroupDefault(group="deferred_target", value="file1"),
                    children=[
                        GroupDefault(
                            group="/group2",
                            value="file2",
                            package="_global_",
                        ),
                        ConfigDefault(path="_self_"),
                    ],
                ),
                ConfigDefault(path="override_group2_global"),
                GroupDefault(group="group1", value="file1"),
                ConfigDefault(path="_self_"),
            ],
        ),
    )


@mark.parametrize(
    "config_name,overrides,expected",
    [
        param(
            "interpolation_legacy_with_self",
            [],
            DefaultsTreeNode(
                node=ConfigDefault(path="interpolation_legacy_with_self"),
                children=[
                    ConfigDefault(path="_self_"),
                    GroupDefault(group="group1", value="file1"),
                    GroupDefault(group="group2", value="file2"),
                    GroupDefault(group="group1_group2", value="file1_file2"),
                ],
            ),
            id="interpolation_legacy_with_self",
        ),
        param(
            "interpolation_legacy_without_self",
            [],
            DefaultsTreeNode(
                node=ConfigDefault(path="interpolation_legacy_without_self"),
                children=[
                    GroupDefault(group="group1", value="file1"),
                    GroupDefault(group="group2", value="file2"),
                    GroupDefault(group="group1_group2", value="file1_file2"),
                    ConfigDefault(path="_self_"),
                ],
            ),
            id="interpolation_legacy_without_self",
        ),
    ],
)
def test_legacy_interpolation(
    config_name: str,
    overrides: list[str],
    expected: DefaultsTreeNode,
    hydra_restore_singletons: Any,
) -> None:
    msg = dedent(
        """
    Defaults list element '.*=.*' is using a deprecated interpolation form.
    See http://hydra.cc/docs/1.1/upgrades/1.0_to_1.1/defaults_list_interpolation for migration information."""
    )
    with raises(ConfigCompositionException, match=msg):
        _test_defaults_tree_impl(
            config_name=config_name,
            input_overrides=overrides,
            expected=expected,
        )


def test_legacy_interpolation_multi_digit_index(
    hydra_restore_singletons: Any,
) -> None:
    msg = dedent(
        """
    Defaults list element 'target=.*' is using a deprecated interpolation form.
    See http://hydra.cc/docs/1.1/upgrades/1.0_to_1.1/defaults_list_interpolation for migration information."""
    )
    known_choices = OmegaConf.create(
        {"defaults": [{}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {"group": "file1"}]}
    )

    default = GroupDefault(group="target", value="${defaults.10.group}")
    default.update_parent("", "")
    with raises(ConfigCompositionException, match=msg):
        default.resolve_interpolation(known_choices)


def test_legacy_interpolation_in_config_path(
    hydra_restore_singletons: Any,
) -> None:
    msg = re.escape(
        "Error resolving interpolation '${defaults.0.group1}/file', "
        "possible interpolation keys: group1"
    )
    with raises(ConfigCompositionException, match=msg):
        _test_defaults_tree_impl(
            config_name="interpolation_legacy_config_path",
            input_overrides=[],
            expected=None,
        )


@mark.parametrize(
    "config_name,overrides,expected",
    [
        param(
            "override_nested_to_null",
            [],
            DefaultsTreeNode(
                node=ConfigDefault(path="override_nested_to_null"),
                children=[
                    DefaultsTreeNode(
                        node=GroupDefault(group="group1", value="group_item1"),
                        children=[
                            GroupDefault(group="group2"),
                            ConfigDefault(path="_self_"),
                        ],
                    ),
                    ConfigDefault(path="_self_"),
                ],
            ),
            id="override_nested_to_null",
        ),
        param(
            "override_nested_to_null",
            ["group1/group2=file2"],
            DefaultsTreeNode(
                node=ConfigDefault(path="override_nested_to_null"),
                children=[
                    DefaultsTreeNode(
                        node=GroupDefault(group="group1", value="group_item1"),
                        children=[
                            GroupDefault(group="group2", value="file2"),
                            ConfigDefault(path="_self_"),
                        ],
                    ),
                    ConfigDefault(path="_self_"),
                ],
            ),
            id="override_nested_to_null:override",
        ),
    ],
)
def test_override_nested_to_null(
    config_name: str,
    overrides: list[str],
    expected: DefaultsTreeNode,
) -> None:
    _test_defaults_tree_impl(
        config_name=config_name,
        input_overrides=overrides,
        expected=expected,
    )


@mark.parametrize(
    "config_name,overrides,expected",
    [
        param(
            "include_nested_group",
            [],
            DefaultsTreeNode(
                node=ConfigDefault(path="include_nested_group"),
                children=[
                    DefaultsTreeNode(
                        node=GroupDefault(group="group1", value="group_item1"),
                        children=[
                            GroupDefault(group="group2", value="file1"),
                            ConfigDefault(path="_self_"),
                        ],
                    ),
                    ConfigDefault(path="_self_"),
                ],
            ),
            id="delete:include_nested_group:baseline",
        ),
        param(
            "include_nested_group",
            ["~group1"],
            DefaultsTreeNode(
                node=ConfigDefault(path="include_nested_group"),
                children=[
                    GroupDefault(group="group1", value="group_item1", deleted=True),
                    ConfigDefault(path="_self_"),
                ],
            ),
            id="delete:include_nested_group:group1",
        ),
        param(
            "include_nested_group",
            ["~group1/group2"],
            DefaultsTreeNode(
                node=ConfigDefault(path="include_nested_group"),
                children=[
                    DefaultsTreeNode(
                        node=GroupDefault(group="group1", value="group_item1"),
                        children=[
                            GroupDefault(group="group2", value="file1", deleted=True),
                            ConfigDefault(path="_self_"),
                        ],
                    ),
                    ConfigDefault(path="_self_"),
                ],
            ),
            id="delete:include_nested_group:group1/group2",
        ),
        param(
            "include_nested_group",
            ["~group1=group_item1"],
            DefaultsTreeNode(
                node=ConfigDefault(path="include_nested_group"),
                children=[
                    GroupDefault(group="group1", value="group_item1", deleted=True),
                    ConfigDefault(path="_self_"),
                ],
            ),
            id="delete:include_nested_group:group1=group_item1",
        ),
        param(
            "include_nested_group",
            ["~group1=wrong"],
            raises(
                ConfigCompositionException,
                match="Could not delete 'group1=wrong'. No match in the defaults list",
            ),
            id="delete:include_nested_group:group1=wrong",
        ),
        param(
            "two_config_items",
            ["~group1/file1"],
            DefaultsTreeNode(
                node=ConfigDefault(path="two_config_items"),
                children=[
                    ConfigDefault(path="group1/file1", deleted=True),
                    ConfigDefault(path="group1/file2"),
                    ConfigDefault(path="_self_"),
                ],
            ),
            id="delete:two_config_items:group1/file1",
        ),
        param(
            "two_group_defaults_different_pkgs",
            [],
            DefaultsTreeNode(
                node=ConfigDefault(path="two_group_defaults_different_pkgs"),
                children=[
                    GroupDefault(group="group1", value="file1", package="pkg1"),
                    GroupDefault(group="group1", value="file1", package="pkg2"),
                    ConfigDefault(path="_self_"),
                ],
            ),
            id="delete:two_group_defaults_different_pkgs:baseline",
        ),
        param(
            "two_group_defaults_different_pkgs",
            ["~group1@pkg1"],
            DefaultsTreeNode(
                node=ConfigDefault(path="two_group_defaults_different_pkgs"),
                children=[
                    GroupDefault(
                        group="group1", value="file1", package="pkg1", deleted=True
                    ),
                    GroupDefault(group="group1", value="file1", package="pkg2"),
                    ConfigDefault(path="_self_"),
                ],
            ),
            id="delete:two_group_defaults_different_pkgs:delete_pkg1",
        ),
        param(
            "two_group_defaults_different_pkgs",
            ["~group1@pkg2"],
            DefaultsTreeNode(
                node=ConfigDefault(path="two_group_defaults_different_pkgs"),
                children=[
                    GroupDefault(group="group1", value="file1", package="pkg1"),
                    GroupDefault(
                        group="group1", value="file1", package="pkg2", deleted=True
                    ),
                    ConfigDefault(path="_self_"),
                ],
            ),
            id="delete:two_group_defaults_different_pkgs:delete_pkg1",
        ),
    ],
)
def test_deletion(
    config_name: str,
    overrides: list[str],
    expected: DefaultsTreeNode,
) -> None:
    _test_defaults_tree_impl(
        config_name=config_name,
        input_overrides=overrides,
        expected=expected,
    )


@mark.parametrize(
    "config_name,overrides,expected",
    [
        param(
            "empty",
            ["~group1"],
            raises(
                ConfigCompositionException,
                match="Could not delete 'group1'. No match in the defaults list",
            ),
            id="override_non_existing",
        ),
        param(
            "empty",
            ["~group1=abc"],
            raises(
                ConfigCompositionException,
                match="Could not delete 'group1=abc'. No match in the defaults list",
            ),
            id="override_non_existing",
        ),
        param(
            "empty",
            ["~group1@pkg1=abc"],
            raises(
                ConfigCompositionException,
                match="Could not delete 'group1@pkg1=abc'. No match in the defaults list",
            ),
            id="override_non_existing",
        ),
    ],
)
def test_delete_non_existing(
    config_name: str,
    overrides: list[str],
    expected: DefaultsTreeNode,
) -> None:
    _test_defaults_tree_impl(
        config_name=config_name,
        input_overrides=overrides,
        expected=expected,
    )


@mark.parametrize(
    "config_name,overrides,expected",
    [
        param(
            "not_found",
            [],
            raises(
                ConfigCompositionException,
                match="^Cannot find primary config 'not_found'. Check that it's in your config search path.",
            ),
            id="missing_primary",
        ),
        param(
            "empty",
            ["+group1=not_found"],
            raises(
                ConfigCompositionException,
                match="^In 'empty': Could not find 'group1/not_found'\n\nAvailable options in 'group1':",
            ),
            id="missing_included_config",
        ),
        param(
            "empty",
            ["+group1=not_found"],
            raises(
                ConfigCompositionException,
                match="^In 'empty': Could not find 'group1/not_found'\n\nAvailable options in 'group1':",
            ),
            id="missing_included_config",
        ),
    ],
)
def test_missing_config_errors(
    config_name: str,
    overrides: list[str],
    expected: DefaultsTreeNode,
) -> None:
    _test_defaults_tree_impl(
        config_name=config_name,
        input_overrides=overrides,
        expected=expected,
    )


@mark.parametrize(
    "config_name,overrides,expected",
    [
        param(
            "empty",
            ["group1=file1"],
            raises(
                ConfigCompositionException,
                match="Could not override 'group1'. No match in the defaults list.",
            ),
            id="override_non_existing",
        ),
        param(
            "empty",
            ["group1@pkg1=file1"],
            raises(
                ConfigCompositionException,
                match="Could not override 'group1@pkg1'. No match in the defaults list.",
            ),
            id="override_non_existing",
        ),
        param(
            "empty",
            ["group1/group2=file1"],
            raises(
                ConfigCompositionException,
                match="Could not override 'group1/group2'. No match in the defaults list.",
            ),
            id="override_non_existing",
        ),
        param(
            "error_invalid_override",
            [],
            raises(
                ConfigCompositionException,
                match=re.escape(
                    "In 'error_invalid_override': Invalid Defaults List override 'group1: file'."
                    "\nNo earlier Group Default for 'group1' exists to override."
                ),
            ),
            id="error_invalid_override",
        ),
        param(
            "group_override_only",
            [],
            raises(
                ConfigCompositionException,
                match=re.escape(
                    "In 'group_override_only': Invalid Defaults List override 'group1: file2'."
                    "\nNo earlier Group Default for 'group1' exists to override."
                ),
            ),
            id="dangling_override_without_append",
        ),
        param(
            "group_default",
            ["group1@foo=file1"],
            raises(
                ConfigCompositionException,
                match=re.escape(
                    dedent("""\
                Could not override 'group1@foo'.
                Did you mean to override group1?
                To append to your default list use +group1@foo=file1""")
                ),
            ),
            id="no_match_package_one_candidate",
        ),
        param(
            "two_group_defaults_different_pkgs",
            ["group1@foo=file1"],
            raises(
                ConfigCompositionException,
                match=re.escape(
                    dedent("""\
                        Could not override 'group1@foo'.
                        Did you mean to override one of group1@pkg1, group1@pkg2?
                        To append to your default list use +group1@foo=file1""")
                ),
            ),
            id="no_match_package_multiple_candidates",
        ),
        param(
            "empty",
            ["+group1=override_invalid"],
            raises(
                ConfigCompositionException,
                match=re.escape(
                    "In 'group1/override_invalid': Invalid Defaults List override 'group2@foo: file1'."
                    "\nNo earlier Group Default for 'group1/group2@group1.foo' exists to override."
                ),
            ),
            id="nested_override_invalid_group",
        ),
        param(
            "empty",
            ["+group1=override_invalid2"],
            raises(
                ConfigCompositionException,
                match=re.escape(
                    "In 'group1/override_invalid2': Invalid Defaults List override 'group2: file1'."
                    "\nNo earlier Group Default for 'group1/group2' exists to override."
                ),
            ),
            id="nested_override_invalid_group",
        ),
    ],
)
def test_override_errors(
    config_name: str,
    overrides: list[str],
    expected: DefaultsTreeNode,
) -> None:
    _test_defaults_tree_impl(
        config_name=config_name,
        input_overrides=overrides,
        expected=expected,
    )


@mark.parametrize(
    "config_name,overrides,expected",
    [
        param(
            "missing_optional_default",
            [],
            DefaultsTreeNode(
                node=ConfigDefault(path="missing_optional_default"),
                children=[
                    ConfigDefault(path="empty"),
                    GroupDefault(
                        group="foo", value="missing", optional=True, deleted=True
                    ),
                    ConfigDefault(path="_self_"),
                ],
            ),
            id="missing_optional_default",
        ),
    ],
)
def test_load_missing_optional(
    config_name: str,
    overrides: list[str],
    expected: DefaultsTreeNode,
) -> None:
    _test_defaults_tree_impl(
        config_name=config_name,
        input_overrides=overrides,
        expected=expected,
    )


@mark.parametrize(
    "config_name,overrides,expected",
    [
        param(
            "group_default_global",
            [],
            DefaultsTreeNode(
                node=ConfigDefault(path="group_default_global"),
                children=[
                    GroupDefault(group="group1", value="file_with_global_header"),
                    ConfigDefault(path="_self_"),
                ],
            ),
            id="group_default_global",
        ),
        param(
            "group_default_global",
            ["group1=file_with_global_header"],
            DefaultsTreeNode(
                node=ConfigDefault(path="group_default_global"),
                children=[
                    GroupDefault(group="group1", value="file_with_global_header"),
                    ConfigDefault(path="_self_"),
                ],
            ),
            id="group_default_global",
        ),
    ],
)
def test_overriding_group_file_with_global_header(
    config_name: str,
    overrides: list[str],
    expected: DefaultsTreeNode,
) -> None:
    _test_defaults_tree_impl(
        config_name=config_name,
        input_overrides=overrides,
        expected=expected,
    )


@mark.parametrize(
    "config_name,overrides,expected",
    [
        param(
            None,
            [],
            DefaultsTreeNode(node=ConfigDefault(path="_dummy_empty_config_")),
            id="none_config",
        ),
        param(
            None,
            ["+group1=file1"],
            DefaultsTreeNode(
                node=ConfigDefault(path="_dummy_empty_config_"),
                children=[
                    ConfigDefault(path="_self_"),
                    GroupDefault(group="group1", value="file1"),
                ],
            ),
            id="none_config+group1=file1",
        ),
    ],
)
def test_none_config(
    config_name: str | None,
    overrides: list[str],
    expected: DefaultsTreeNode,
) -> None:
    _test_defaults_tree_impl(
        config_name=config_name,
        input_overrides=overrides,
        expected=expected,
    )


@mark.parametrize(
    "config_name,overrides,expected",
    [
        param(
            None,
            [],
            DefaultsTreeNode(
                node=VirtualRoot(),
                children=[
                    DefaultsTreeNode(
                        node=ConfigDefault(path="hydra/config"),
                        children=[
                            GroupDefault(group="help", value="default"),
                            GroupDefault(group="output", value="default"),
                            ConfigDefault(path="_self_"),
                        ],
                    ),
                    ConfigDefault(path="_dummy_empty_config_"),
                ],
            ),
            id="none_config",
        ),
        param(
            None,
            ["+group1=file1"],
            DefaultsTreeNode(
                node=VirtualRoot(),
                children=[
                    DefaultsTreeNode(
                        node=ConfigDefault(path="hydra/config"),
                        children=[
                            GroupDefault(group="help", value="default"),
                            GroupDefault(group="output", value="default"),
                            ConfigDefault(path="_self_"),
                        ],
                    ),
                    DefaultsTreeNode(
                        node=ConfigDefault(path="_dummy_empty_config_"),
                        children=[
                            ConfigDefault(path="_self_"),
                            GroupDefault(group="group1", value="file1"),
                        ],
                    ),
                ],
            ),
            id="none_config+group1=file1",
        ),
    ],
)
def test_none_config_with_hydra(
    config_name: str | None,
    overrides: list[str],
    expected: DefaultsTreeNode,
) -> None:
    _test_defaults_tree_impl(
        config_name=config_name,
        input_overrides=overrides,
        expected=expected,
        prepend_hydra=True,
    )


@mark.parametrize(
    ("config_name", "overrides", "expected"),
    [
        param(
            "defaults_with_override_only",
            [],
            DefaultsTreeNode(
                node=VirtualRoot(),
                children=[
                    DefaultsTreeNode(
                        node=ConfigDefault(path="hydra/config"),
                        children=[
                            GroupDefault(group="help", value="custom1"),
                            GroupDefault(group="output", value="default"),
                            ConfigDefault(path="_self_"),
                        ],
                    ),
                    ConfigDefault(path="defaults_with_override_only"),
                ],
            ),
            id="defaults_with_override_only",
        ),
        param(
            "defaults_with_override_only",
            ["+group1=file1"],
            DefaultsTreeNode(
                node=VirtualRoot(),
                children=[
                    DefaultsTreeNode(
                        node=ConfigDefault(path="hydra/config"),
                        children=[
                            GroupDefault(group="help", value="custom1"),
                            GroupDefault(group="output", value="default"),
                            ConfigDefault(path="_self_"),
                        ],
                    ),
                    DefaultsTreeNode(
                        node=ConfigDefault(path="defaults_with_override_only"),
                        children=[GroupDefault(group="group1", value="file1")],
                    ),
                ],
            ),
            id="defaults_with_override_only",
        ),
    ],
)
def test_defaults_with_overrides_only(
    config_name: str | None,
    overrides: list[str],
    expected: DefaultsTreeNode,
) -> None:
    _test_defaults_tree_impl(
        config_name=config_name,
        input_overrides=overrides,
        expected=expected,
        prepend_hydra=True,
    )


@mark.parametrize(
    ("config_name", "overrides", "expected"),
    [
        param(
            "keyword_as_groups",
            [],
            DefaultsTreeNode(
                node=ConfigDefault(path="keyword_as_groups"),
                children=[
                    GroupDefault(group="optional", value="file1"),
                    GroupDefault(group="override", value="file1"),
                    ConfigDefault(path="_self_"),
                ],
            ),
            id="keyword_override_as_group",
        ),
        param(
            "keyword_override_override",
            [],
            DefaultsTreeNode(
                node=ConfigDefault(path="keyword_override_override"),
                children=[
                    GroupDefault(group="override", value="file2"),
                    ConfigDefault(path="_self_"),
                ],
            ),
            id="keyword_override_override",
        ),
        param(
            "keyword_optional_optional",
            [],
            DefaultsTreeNode(
                node=ConfigDefault(path="keyword_optional_optional"),
                children=[
                    GroupDefault(group="optional", value="file1", optional=True),
                    ConfigDefault(path="_self_"),
                ],
            ),
            id="keyword_optional_optional",
        ),
    ],
)
def test_group_with_keyword_names(
    config_name: str | None,
    overrides: list[str],
    expected: DefaultsTreeNode,
) -> None:
    _test_defaults_tree_impl(
        config_name=config_name,
        input_overrides=overrides,
        expected=expected,
    )


@mark.parametrize(
    ("config_name", "overrides", "expected", "expected_choices"),
    [
        param(
            "empty",
            [],
            DefaultsTreeNode(node=ConfigDefault(path="empty")),
            {},
            id="empty",
        ),
        param(
            "group_default",
            [],
            DefaultsTreeNode(
                node=ConfigDefault(path="group_default"),
                children=[
                    GroupDefault(group="group1", value="file1"),
                    ConfigDefault(path="_self_"),
                ],
            ),
            {"group1": "file1"},
            id="group_default",
        ),
        param(
            "group_default",
            ["group1=file2"],
            DefaultsTreeNode(
                node=ConfigDefault(path="group_default"),
                children=[
                    GroupDefault(group="group1", value="file2"),
                    ConfigDefault(path="_self_"),
                ],
            ),
            {"group1": "file2"},
            id="group_default:override",
        ),
        param(
            "nested_placeholder",
            [],
            DefaultsTreeNode(
                node=ConfigDefault(path="nested_placeholder"),
                children=[
                    DefaultsTreeNode(
                        node=GroupDefault(group="group1", value="placeholder"),
                        children=[
                            GroupDefault(group="group2"),
                            ConfigDefault(path="_self_"),
                        ],
                    ),
                    ConfigDefault(path="_self_"),
                ],
            ),
            {"group1": "placeholder", "group1/group2": None},
            id="nested_placeholder",
        ),
        param(
            "include_nested_group_pkg2",
            [],
            DefaultsTreeNode(
                node=ConfigDefault(path="include_nested_group_pkg2"),
                children=[
                    DefaultsTreeNode(
                        node=GroupDefault(group="group1", value="group_item1_pkg2"),
                        children=[
                            GroupDefault(group="group2", value="file1", package="pkg2"),
                            ConfigDefault(path="_self_"),
                        ],
                    ),
                    ConfigDefault(path="_self_"),
                ],
            ),
            {"group1": "group_item1_pkg2", "group1/group2@group1.pkg2": "file1"},
            id="include_nested_group_pkg2",
        ),
    ],
)
def test_choices(
    config_name: str | None,
    overrides: list[str],
    expected: DefaultsTreeNode,
    expected_choices: dict[str, str],
) -> None:
    res = _test_defaults_tree_impl(
        config_name=config_name,
        input_overrides=overrides,
        expected=expected,
    )
    assert res is not None
    assert res.overrides.known_choices == expected_choices


@mark.parametrize(
    ("config_name", "overrides", "package_header", "expected"),
    [
        param(
            "deprecated_headers/group",
            [],
            "_group_",
            DefaultsTreeNode(node=ConfigDefault(path="deprecated_headers/group")),
            id="deprecated_headers/group",
        ),
        param(
            "deprecated_headers/name",
            [],
            "_name_",
            DefaultsTreeNode(node=ConfigDefault(path="deprecated_headers/name")),
            id="deprecated_headers/name",
        ),
        param(
            "deprecated_headers/group_name",
            [],
            "_group_._name_",
            DefaultsTreeNode(node=ConfigDefault(path="deprecated_headers/group_name")),
            id="deprecated_headers/group_name",
        ),
        param(
            "deprecated_headers/group_foo",
            [],
            "_group_.foo",
            DefaultsTreeNode(node=ConfigDefault(path="deprecated_headers/group_foo")),
            id="deprecated_headers/group_foo",
        ),
    ],
)
def test_package_header_keywords_are_literal(
    config_name: str | None,
    overrides: list[str],
    package_header: str,
    expected: DefaultsTreeNode,
    hydra_restore_singletons: Any,
) -> None:
    _test_defaults_tree_impl(
        config_name=config_name,
        input_overrides=overrides,
        expected=expected,
    )


@mark.parametrize(
    ("config_name", "overrides", "with_hydra", "expected"),
    [
        param(
            "select_multi",
            [],
            False,
            DefaultsTreeNode(
                node=ConfigDefault(path="select_multi"),
                children=[
                    ConfigDefault(path="group1/file1"),
                    ConfigDefault(path="group1/file2"),
                    ConfigDefault(path="_self_"),
                ],
            ),
            id="select_multi",
        ),
        param(
            "select_multi",
            ["group1=[file1,file3]"],
            False,
            DefaultsTreeNode(
                node=ConfigDefault(path="select_multi"),
                children=[
                    ConfigDefault(path="group1/file1"),
                    ConfigDefault(path="group1/file3"),
                    ConfigDefault(path="_self_"),
                ],
            ),
            id="select_multi:override_list",
        ),
        param(
            "select_multi",
            ["group1=[]"],
            False,
            DefaultsTreeNode(
                node=ConfigDefault(path="select_multi"),
                children=[ConfigDefault(path="_self_")],
            ),
            id="select_multi:override_to_empty_list",
        ),
        param(
            "select_multi",
            ["~group1/file1"],
            False,
            DefaultsTreeNode(
                node=ConfigDefault(path="select_multi"),
                children=[
                    ConfigDefault(path="group1/file1", deleted=True),
                    ConfigDefault(path="group1/file2"),
                    ConfigDefault(path="_self_"),
                ],
            ),
            id="select_multi:delete_config_path",
        ),
        param(
            "select_multi",
            ["group1=file1"],
            False,
            DefaultsTreeNode(
                node=ConfigDefault(path="select_multi"),
                children=[
                    GroupDefault(group="group1", value="file1"),
                    ConfigDefault(path="_self_"),
                ],
            ),
            id="select_multi:override_to_option",
        ),
        # nested
        param(
            "group1/select_multi",
            [],
            False,
            DefaultsTreeNode(
                node=ConfigDefault(path="group1/select_multi"),
                children=[
                    ConfigDefault(path="group2/file1"),
                    ConfigDefault(path="group2/file2"),
                    ConfigDefault(path="_self_"),
                ],
            ),
            id="group1/select_multi",
        ),
        param(
            "group1/select_multi",
            ["group1/group2=[file1,file3]"],
            False,
            DefaultsTreeNode(
                node=ConfigDefault(path="group1/select_multi"),
                children=[
                    ConfigDefault(path="group2/file1"),
                    ConfigDefault(path="group2/file3"),
                    ConfigDefault(path="_self_"),
                ],
            ),
            id="group1/select_multi:override",
        ),
        param(
            "select_multi_interpolation",
            [],
            False,
            raises(
                ConfigCompositionException,
                match=re.escape(
                    "In 'select_multi_interpolation': "
                    "Defaults List interpolation is not supported in options list items"
                ),
            ),
            id="select_multi_interpolation",
        ),
        param(
            "select_multi_override",
            [],
            False,
            DefaultsTreeNode(
                node=ConfigDefault(path="select_multi_override"),
                children=[
                    ConfigDefault(path="group1/file3"),
                    ConfigDefault(path="group1/file1"),
                    ConfigDefault(path="_self_"),
                ],
            ),
            id="select_multi_override",
        ),
        param(
            "select_multi_optional",
            [],
            False,
            DefaultsTreeNode(
                node=ConfigDefault(path="select_multi_optional"),
                children=[
                    ConfigDefault(path="group1/not_found", deleted=True, optional=True),
                    ConfigDefault(path="_self_"),
                ],
            ),
            id="select_multi_optional",
        ),
        param(
            "select_multi_optional",
            ["group1=[file1,not_found2]"],
            False,
            DefaultsTreeNode(
                node=ConfigDefault(path="select_multi_optional"),
                children=[
                    ConfigDefault(path="group1/file1", optional=True),
                    ConfigDefault(
                        path="group1/not_found2", deleted=True, optional=True
                    ),
                    ConfigDefault(path="_self_"),
                ],
            ),
            id="select_multi_optional:override",
        ),
        param(
            "empty",
            ["+group1=[file1]"],
            False,
            DefaultsTreeNode(
                node=ConfigDefault(path="empty"),
                children=[
                    ConfigDefault(path="_self_"),
                    ConfigDefault(path="group1/file1"),
                ],
            ),
            id="append_new_list_to_a_config_without_a_defaults_list",
        ),
        param(
            None,
            ["+group1=[file1]"],
            False,
            DefaultsTreeNode(
                node=ConfigDefault(path="_dummy_empty_config_"),
                children=[
                    ConfigDefault(path="_self_"),
                    ConfigDefault(path="group1/file1"),
                ],
            ),
            id="append_new_list_to_without_a_primary_config",
        ),
        param(
            "empty",
            ["+group1=[file1]"],
            True,
            DefaultsTreeNode(
                node=VirtualRoot(),
                children=[
                    DefaultsTreeNode(
                        node=ConfigDefault(path="hydra/config"),
                        children=[
                            GroupDefault(group="help", value="default"),
                            GroupDefault(group="output", value="default"),
                            ConfigDefault(path="_self_"),
                        ],
                    ),
                    DefaultsTreeNode(
                        node=ConfigDefault(path="empty"),
                        children=[
                            ConfigDefault(path="_self_"),
                            ConfigDefault(path="group1/file1"),
                        ],
                    ),
                ],
            ),
            id="append_new_list_to_a_config_without_a_defaults_list+with_hydra",
        ),
        param(
            None,
            ["+group1=[file1]"],
            True,
            DefaultsTreeNode(
                node=VirtualRoot(),
                children=[
                    DefaultsTreeNode(
                        node=ConfigDefault(path="hydra/config"),
                        children=[
                            GroupDefault(group="help", value="default"),
                            GroupDefault(group="output", value="default"),
                            ConfigDefault(path="_self_"),
                        ],
                    ),
                    DefaultsTreeNode(
                        node=ConfigDefault(path="_dummy_empty_config_"),
                        children=[
                            ConfigDefault(path="_self_"),
                            ConfigDefault(path="group1/file1"),
                        ],
                    ),
                ],
            ),
            id="append_new_list_to_without_a_primary_config+with_hydra",
        ),
    ],
)
def test_select_multi(
    config_name: str | None,
    overrides: list[str],
    with_hydra: bool,
    expected: DefaultsTreeNode,
) -> None:
    _test_defaults_tree_impl(
        config_name=config_name,
        input_overrides=overrides,
        prepend_hydra=with_hydra,
        expected=expected,
    )


@mark.parametrize(
    ("config_name", "overrides", "expected"),
    [
        param(
            "select_multi_pkg",
            [],
            DefaultsTreeNode(
                node=ConfigDefault(path="select_multi_pkg"),
                children=[
                    ConfigDefault(path="group1/file1", package="foo"),
                    ConfigDefault(path="group1/file2", package="foo"),
                    ConfigDefault(path="_self_"),
                ],
            ),
            id="select_multi",
        ),
        param(
            "select_multi_pkg",
            ["group1@foo=[file1,file3]"],
            DefaultsTreeNode(
                node=ConfigDefault(path="select_multi_pkg"),
                children=[
                    ConfigDefault(path="group1/file1", package="foo"),
                    ConfigDefault(path="group1/file3", package="foo"),
                    ConfigDefault(path="_self_"),
                ],
            ),
            id="select_multi_pkg:override_list",
        ),
        param(
            "select_multi_pkg",
            ["group1@foo=[]"],
            DefaultsTreeNode(
                node=ConfigDefault(path="select_multi_pkg"),
                children=[ConfigDefault(path="_self_")],
            ),
            id="select_multi_pkg:override_to_empty_list",
        ),
        param(
            "select_multi_pkg",
            ["group1@foo=file1"],
            DefaultsTreeNode(
                node=ConfigDefault(path="select_multi_pkg"),
                children=[
                    GroupDefault(group="group1", value="file1", package="foo"),
                    ConfigDefault(path="_self_"),
                ],
            ),
            id="select_multi_pkg:override_to_option",
        ),
        # nested
        param(
            "group1/select_multi_pkg",
            [],
            DefaultsTreeNode(
                node=ConfigDefault(path="group1/select_multi_pkg"),
                children=[
                    ConfigDefault(path="group2/file1", package="bar"),
                    ConfigDefault(path="group2/file2", package="bar"),
                    ConfigDefault(path="_self_"),
                ],
            ),
            id="group1/select_multi_pkg",
        ),
        param(
            "group1/select_multi_pkg",
            ["group1/group2@group1.bar=[file1,file3]"],
            DefaultsTreeNode(
                node=ConfigDefault(path="group1/select_multi_pkg"),
                children=[
                    ConfigDefault(path="group2/file1", package="bar"),
                    ConfigDefault(path="group2/file3", package="bar"),
                    ConfigDefault(path="_self_"),
                ],
            ),
            id="group1/select_multi:override",
        ),
        param(
            "group1/group_item1",
            ["group1/group2=[file1,file2]"],
            DefaultsTreeNode(
                node=ConfigDefault(path="group1/group_item1"),
                children=[
                    ConfigDefault(path="group2/file1"),
                    ConfigDefault(path="group2/file2"),
                    ConfigDefault(path="_self_"),
                ],
            ),
            id="group1/override_single_to_list",
        ),
    ],
)
def test_select_multi_pkg(
    config_name: str | None,
    overrides: list[str],
    expected: DefaultsTreeNode,
) -> None:
    _test_defaults_tree_impl(
        config_name=config_name,
        input_overrides=overrides,
        expected=expected,
    )


@mark.parametrize(
    ("config_name", "overrides", "expected"),
    [
        param(
            "experiment/error_override_without_abs_and_header",
            [],
            raises(
                ConfigCompositionException,
                match=re.escape(
                    "In 'experiment/error_override_without_abs_and_header': "
                    "Invalid Defaults List override 'group1: file1'."
                    "\nNo earlier Group Default for 'experiment/group1' exists to override."
                ),
            ),
            id="experiment/error_override_without_abs_and_header",
        ),
        param(
            "experiment/error_override_without_global",
            [],
            raises(
                ConfigCompositionException,
                match=re.escape(
                    "In 'experiment/error_override_without_global': "
                    "Invalid Defaults List override '/group1: file1'."
                    "\nNo earlier Group Default for 'group1@experiment.group1' exists to override."
                ),
            ),
            id="experiment/error_override_without_global",
        ),
    ],
)
def test_nested_override_errors(
    config_name: str | None,
    overrides: list[str],
    expected: DefaultsTreeNode,
) -> None:
    _test_defaults_tree_impl(
        config_name=config_name,
        input_overrides=overrides,
        expected=expected,
    )

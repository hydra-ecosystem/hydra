# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved
from typing import Any

from hydra._internal.config_repository import ConfigRepository, IConfigRepository
from hydra._internal.config_search_path_impl import ConfigSearchPathImpl
from hydra._internal.defaults_list import (
    DefaultsList,
    Overrides,
    _create_defaults_tree,
    _create_root,
)
from hydra.core.default_element import DefaultsTreeNode
from hydra.core.override_parser.overrides_parser import OverridesParser


def create_repo() -> IConfigRepository:
    csp = ConfigSearchPathImpl()
    csp.append(provider="test", path="file://tests/defaults_list/data")
    csp.append("schema", "structured://")
    return ConfigRepository(config_search_path=csp)


def _test_defaults_tree_impl(
    config_name: str | None,
    input_overrides: list[str],
    expected: Any,
    prepend_hydra: bool = False,
    skip_missing: bool = False,
) -> DefaultsList | None:
    parser = OverridesParser.create()
    repo = create_repo()
    root = _create_root(config_name=config_name, with_hydra=prepend_hydra)
    overrides_list = parser.parse_overrides(overrides=input_overrides)
    overrides = Overrides(repo=repo, overrides_list=overrides_list)

    if expected is None or isinstance(expected, DefaultsTreeNode):
        result = _create_defaults_tree(
            repo=repo,
            root=root,
            overrides=overrides,
            is_root_config=True,
            interpolated_subtree=False,
            skip_missing=skip_missing,
        )
        overrides.ensure_overrides_used()
        overrides.ensure_deletions_used()
        assert result == expected
        return DefaultsList(
            defaults=[], defaults_tree=result, overrides=overrides, config_overrides=[]
        )
    else:
        with expected:
            _create_defaults_tree(
                repo=repo,
                root=root,
                overrides=overrides,
                is_root_config=True,
                interpolated_subtree=False,
                skip_missing=skip_missing,
            )
            overrides.ensure_overrides_used()
            overrides.ensure_deletions_used()
        return None

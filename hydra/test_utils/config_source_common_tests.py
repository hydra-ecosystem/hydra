# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved
from typing import Any

from pytest import mark, param, raises, skip

from hydra.core.default_element import InputDefault
from hydra.core.object_type import ObjectType
from hydra.plugins.config_source import ConfigLoadError, ConfigSource


class ConfigSourceTestSuite:
    def skip_overlap_config_path_name(self) -> bool:
        """
        Some config source plugins do not support config name and path overlap.
        For example the following may not be allowed:
        (dataset exists both as a config object and a config group)
        /dateset.yaml
        /dataset/cifar.yaml

        Overriding and returning True here will disable testing of this scenario
        by assuming the dataset config (dataset.yaml) is not present.
        """
        return False

    def test_not_available(self, type_: type[ConfigSource], path: str) -> None:
        scheme = type_(provider="foo", path=path).scheme()
        # Test is meaningless for StructuredConfigSource
        if scheme == "structured":
            return
        src = type_(provider="foo", path=f"{scheme}://___NOT_FOUND___")
        assert not src.available()

    @mark.parametrize(
        "config_path, expected",
        [
            param("", True, id="empty"),
            param("dataset", True, id="dataset"),
            param("optimizer", True, id="optimizer"),
            param(
                "configs_with_defaults_list",
                True,
                id="configs_with_defaults_list",
            ),
            param("dataset/imagenet", False, id="dataset/imagenet"),
            param("level1", True, id="level1"),
            param("level1/level2", True, id="level1/level2"),
            param("level1/level2/nested1", False, id="level1/level2/nested1"),
            param("not_found", False, id="not_found"),
        ],
    )
    def test_is_group(
        self, type_: type[ConfigSource], path: str, config_path: str, expected: bool
    ) -> None:
        src = type_(provider="foo", path=path)
        ret = src.is_group(config_path=config_path)
        assert ret == expected

    @mark.parametrize(
        "config_path, expected",
        [
            ("", False),
            ("optimizer", False),
            ("dataset/imagenet", True),
            ("dataset/imagenet.yaml", True),
            ("dataset/imagenet.foobar", False),
            ("configs_with_defaults_list/global_package", True),
            ("configs_with_defaults_list/group_package", True),
            ("level1", False),
            ("level1/level2", False),
            ("level1/level2/nested1", True),
            ("not_found", False),
        ],
    )
    def test_is_config(
        self, type_: type[ConfigSource], path: str, config_path: str, expected: bool
    ) -> None:
        src = type_(provider="foo", path=path)
        ret = src.is_config(config_path=config_path)
        assert ret == expected

    @mark.parametrize(
        "config_path, expected",
        [
            ("dataset", True),
        ],
    )
    def test_is_config_with_overlap_name(
        self, type_: type[ConfigSource], path: str, config_path: str, expected: bool
    ) -> None:
        if self.skip_overlap_config_path_name():
            skip(
                f"ConfigSourcePlugin {type_.__name__} does not support config objects and config groups "
                f"with overlapping names."
            )
        src = type_(provider="foo", path=path)
        ret = src.is_config(config_path=config_path)
        assert ret == expected

    @mark.parametrize(
        "config_path,results_filter,expected",
        [
            # groups
            ("", ObjectType.GROUP, ["dataset", "level1", "optimizer"]),
            ("dataset", ObjectType.GROUP, []),
            ("optimizer", ObjectType.GROUP, []),
            ("level1", ObjectType.GROUP, ["level2"]),
            ("level1/level2", ObjectType.GROUP, []),
            # Configs
            ("", ObjectType.CONFIG, ["config_without_group"]),
            ("dataset", ObjectType.CONFIG, ["cifar10", "imagenet"]),
            ("optimizer", ObjectType.CONFIG, ["adam", "nesterov"]),
            ("level1", ObjectType.CONFIG, []),
            ("level1/level2", ObjectType.CONFIG, ["nested1", "nested2"]),
            # both
            ("", None, ["config_without_group", "dataset", "level1", "optimizer"]),
            ("dataset", None, ["cifar10", "imagenet"]),
            ("optimizer", None, ["adam", "nesterov"]),
            ("level1", None, ["level2"]),
            ("level1/level2", None, ["nested1", "nested2"]),
            ("", None, ["config_without_group", "dataset", "level1", "optimizer"]),
        ],
    )
    def test_list(
        self,
        type_: type[ConfigSource],
        path: str,
        config_path: str,
        results_filter: ObjectType | None,
        expected: list[str],
    ) -> None:
        src = type_(provider="foo", path=path)
        ret = src.list(config_path=config_path, results_filter=results_filter)
        for x in expected:
            assert x in ret
        assert ret == sorted(ret)

    @mark.parametrize(
        "config_path,results_filter,expected",
        [
            # Configs
            ("", ObjectType.CONFIG, ["dataset"]),
        ],
    )
    def test_list_with_overlap_name(
        self,
        type_: type[ConfigSource],
        path: str,
        config_path: str,
        results_filter: ObjectType | None,
        expected: list[str],
    ) -> None:
        if self.skip_overlap_config_path_name():
            skip(
                f"ConfigSourcePlugin {type_.__name__} does not support config objects and config groups "
                f"with overlapping names."
            )
        src = type_(provider="foo", path=path)
        ret = src.list(config_path=config_path, results_filter=results_filter)
        for x in expected:
            assert x in ret
        assert ret == sorted(ret)

    @mark.parametrize(
        "config_path,expected_config,expected_defaults_list,expected_package",
        [
            param(
                "config_without_group",
                {"group": False},
                None,
                None,
                id="config_without_group",
            ),
            param(
                "config_with_unicode",
                {"group": "数据库"},
                None,
                None,
                id="config_with_unicode",
            ),
            param(
                "dataset/imagenet",
                {"name": "imagenet", "path": "/datasets/imagenet"},
                None,
                None,
                id="dataset/imagenet",
            ),
            param(
                "dataset/cifar10",
                {"name": "cifar10", "path": "/datasets/cifar10"},
                None,
                None,
                id="dataset/cifar10",
            ),
            param(
                "dataset/not_found",
                raises(ConfigLoadError),
                None,
                None,
                id="dataset/not_found",
            ),
            param(
                "level1/level2/nested1",
                {"l1_l2_n1": True},
                None,
                None,
                id="level1/level2/nested1",
            ),
            param(
                "level1/level2/nested2",
                {"l1_l2_n2": True},
                None,
                None,
                id="level1/level2/nested2",
            ),
            param(
                "config_with_defaults_list",
                {
                    "defaults": [{"dataset": "imagenet"}],
                    "key": "value",
                },
                None,
                None,
                id="config_with_defaults_list",
            ),
            param(
                "configs_with_defaults_list/global_package",
                {
                    "defaults": [{"foo": "bar"}],
                    "x": 10,
                },
                None,
                "_global_",
                id="configs_with_defaults_list/global_package",
            ),
            param(
                "configs_with_defaults_list/group_package",
                {
                    "defaults": [{"foo": "bar"}],
                    "x": 10,
                },
                None,
                "_group_",
                id="configs_with_defaults_list/group_package",
            ),
        ],
    )
    def test_source_load_config(
        self,
        type_: type[ConfigSource],
        path: str,
        config_path: str,
        expected_defaults_list: list[InputDefault],
        expected_package: Any,
        expected_config: Any,
        recwarn: Any,
    ) -> None:
        assert issubclass(type_, ConfigSource)
        src = type_(provider="foo", path=path)
        if isinstance(expected_config, dict):
            ret = src.load_config(config_path=config_path)
            assert ret.config == expected_config
            assert ret.header["package"] == expected_package
            assert ret.defaults_list == expected_defaults_list
        else:
            with expected_config:
                src.load_config(config_path=config_path)

    @mark.parametrize(
        "config_path, expected_result, expected_package",
        [
            param("package_test/none", {"foo": "bar"}, None, id="none"),
            param("package_test/explicit", {"foo": "bar"}, "a.b", id="explicit"),
            param("package_test/global", {"foo": "bar"}, "_global_", id="global"),
            param("package_test/group", {"foo": "bar"}, "_group_", id="group"),
            param(
                "package_test/group_name",
                {"foo": "bar"},
                "foo._group_._name_",
                id="group_name",
            ),
            param("package_test/name", {"foo": "bar"}, "_name_", id="name"),
        ],
    )
    def test_package_behavior(
        self,
        type_: type[ConfigSource],
        path: str,
        config_path: str,
        expected_result: Any,
        expected_package: str,
    ) -> None:
        src = type_(provider="foo", path=path)
        cfg = src.load_config(config_path=config_path)
        assert cfg.header["package"] == expected_package
        assert cfg.config == expected_result

    def test_default_package_for_primary_config(
        self, type_: type[ConfigSource], path: str
    ) -> None:
        src = type_(provider="foo", path=path)
        cfg = src.load_config(config_path="primary_config")
        assert cfg.header["package"] == None

    def test_primary_config_with_non_global_package(
        self, type_: type[ConfigSource], path: str
    ) -> None:
        src = type_(provider="foo", path=path)
        cfg = src.load_config(config_path="primary_config_with_non_global_package")
        assert cfg.header["package"] == "foo"

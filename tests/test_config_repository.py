# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved
import copy
import re
import zipfile
from typing import Any

from pytest import mark, param, raises

from hydra._internal.config_repository import CachingConfigRepository, ConfigRepository
from hydra._internal.config_search_path_impl import ConfigSearchPathImpl
from hydra._internal.core_plugins import importlib_resources_config_source
from hydra._internal.core_plugins.file_config_source import FileConfigSource
from hydra._internal.core_plugins.importlib_resources_config_source import (
    ImportlibResourcesConfigSource,
)
from hydra._internal.core_plugins.structured_config_source import StructuredConfigSource
from hydra.core.config_store import ConfigStore
from hydra.core.default_element import GroupDefault, InputDefault
from hydra.core.object_type import ObjectType
from hydra.core.plugins import Plugins
from hydra.core.singleton import Singleton
from hydra.plugins.config_source import ConfigLoadError, ConfigSource
from hydra.test_utils.config_source_common_tests import ConfigSourceTestSuite
from hydra.test_utils.test_utils import chdir_hydra_root

chdir_hydra_root()


# Manually save and restore singletons to work around an issue with things added to the config store via importing.
# restoring is done in test_restore_singleton_state_hack(), which must be the last test in this file.
state = copy.deepcopy(Singleton.get_state())


@mark.parametrize(
    "type_, path",
    [
        param(
            FileConfigSource,
            "file://tests/test_apps/config_source_test/dir",
            id="FileConfigSource",
        ),
        param(
            ImportlibResourcesConfigSource,
            "pkg://tests.test_apps.config_source_test.dir",
            id="ImportlibResourcesConfigSource",
        ),
        param(
            StructuredConfigSource,
            "structured://tests.test_apps.config_source_test.structured",
            id="StructuredConfigSource",
        ),
    ],
)
class TestCoreConfigSources(ConfigSourceTestSuite):
    pass


def create_config_search_path(path: str) -> ConfigSearchPathImpl:
    csp = ConfigSearchPathImpl()
    csp.append(provider="test", path=path)
    return csp


def test_caching_repository_uses_current_config_store(
    hydra_restore_singletons: Any,
) -> None:
    Plugins.instance()
    repository = CachingConfigRepository(
        ConfigRepository(config_search_path=create_config_search_path("structured://"))
    )

    ConfigStore.instance().store(
        name="registered_after_repository_copy", node={"value": 10}
    )

    assert repository.config_exists("registered_after_repository_copy.yaml")
    result = repository.load_config("registered_after_repository_copy.yaml")
    assert result is not None
    assert result.config == {"value": 10}


def test_config_store_empty_group_is_stored_at_root(
    hydra_restore_singletons: Any,
) -> None:
    """An empty group path represents a config outside any config group and must
    behave exactly like group=None. Storing it under a literal empty-string child
    group instead makes help generation traverse that child as the root group
    without terminating."""
    Plugins.instance()
    cs = ConfigStore.instance()
    cs.store(group="", name="empty_group_cfg", node={"age": 18})

    assert "" not in cs.repo
    stored = cs.repo["empty_group_cfg.yaml"]
    assert stored.group is None
    assert stored.node == {"age": 18}

    repository = ConfigRepository(
        config_search_path=create_config_search_path("structured://")
    )
    assert repository.config_exists("empty_group_cfg.yaml")
    loaded = repository.load_config("empty_group_cfg.yaml")
    assert loaded is not None
    assert loaded.config == {"age": 18}
    assert "" not in repository.get_group_options("", ObjectType.GROUP)


@mark.parametrize(
    "path",
    [
        "file://tests/test_apps/config_source_test/dir",
        "pkg://tests.test_apps.config_source_test.dir",
    ],
)
class TestConfigRepository:
    def test_config_repository_load(
        self, hydra_restore_singletons: Any, path: str
    ) -> None:
        Plugins.instance()  # initializes
        config_search_path = create_config_search_path(path)
        repo = ConfigRepository(config_search_path=config_search_path)
        ret = repo.load_config(config_path="dataset/imagenet.yaml")
        assert ret is not None
        assert ret.config == {"name": "imagenet", "path": "/datasets/imagenet"}
        assert repo.load_config(config_path="not_found.yaml") is None

    def test_config_repository_exists(
        self, hydra_restore_singletons: Any, path: str
    ) -> None:
        Plugins.instance()  # initializes
        config_search_path = create_config_search_path(path)
        repo = ConfigRepository(config_search_path=config_search_path)
        assert repo.config_exists("dataset/imagenet.yaml")
        assert not repo.config_exists("not_found.yaml")

    @mark.parametrize(
        "config_path,expected",
        [
            param(
                "primary_config",
                [],
                id="no_defaults",
            ),
            param(
                "config_with_defaults_list",
                [GroupDefault(group="dataset", value="imagenet")],
                id="defaults_in_root",
            ),
            param(
                "configs_with_defaults_list/global_package",
                [GroupDefault(group="foo", value="bar")],
                id="configs_with_defaults_list/global_package",
            ),
            param(
                "configs_with_defaults_list/group_package",
                [GroupDefault(group="foo", value="bar")],
                id="configs_with_defaults_list/group_package",
            ),
            param(
                "configs_with_defaults_list/no_package",
                [GroupDefault(group="foo", value="bar")],
                id="configs_with_defaults_list/no_package",
            ),
        ],
    )
    def test_config_repository_list(
        self,
        hydra_restore_singletons: Any,
        path: str,
        config_path: str,
        expected: list[InputDefault],
    ) -> None:
        Plugins.instance()
        config_search_path = create_config_search_path(path)
        repo = ConfigRepository(config_search_path=config_search_path)
        ret = repo.load_config(config_path)
        assert ret is not None
        assert ret.defaults_list == expected


@mark.parametrize("sep", [" "])
@mark.parametrize(
    "cfg_text, expected",
    [
        ("# @package{sep}foo.bar", {"package": "foo.bar"}),
        ("# @package{sep} foo.bar", {"package": "foo.bar"}),
        ("# @package {sep}foo.bar", {"package": "foo.bar"}),
        ("#@package{sep}foo.bar", {"package": "foo.bar"}),
        ("#@package{sep}foo.bar ", {"package": "foo.bar"}),
        (
            "#@package{sep}foo.bar bah",
            raises(ValueError, match=re.escape("Too many components in")),
        ),
        (
            "#@package",
            raises(
                ValueError, match=re.escape("Expected header format: KEY VALUE, got")
            ),
        ),
        (
            """# @package{sep}foo.bar
foo: bar
# comment dsa
""",
            {"package": "foo.bar"},
        ),
        (
            """
# @package{sep}foo.bar
""",
            {"package": "foo.bar"},
        ),
    ],
)
def test_get_config_header(cfg_text: str, expected: Any, sep: str) -> None:
    cfg_text = cfg_text.format(sep=sep)
    if isinstance(expected, dict):
        header = ConfigSource._get_header_dict(cfg_text)
        assert header == expected
    else:
        with expected:
            ConfigSource._get_header_dict(cfg_text)


def test_singleton_get_state(hydra_restore_singletons: Any) -> None:
    s = Singleton.get_state()
    assert Plugins not in s["instances"]
    assert Plugins in Singleton._instances
    Singleton.set_state(s)
    assert Plugins in Singleton._instances


def test_restore_singleton_state_hack() -> None:
    """
    This is a hack that allow us to undo changes to the ConfigStore.
    During this test, the config store is being modified in Python imports.
    Python imports can only run once, so clearing the state during the tests will break
    The tests because it will not be reinitialized.

    A solution is to undo the changes after the last test.
    The reason this logic is in a test is that if it's outside it's being executed during
    Pytest's test collection phase, which is before the tests are dunning - so it does not solve the problem.
    """
    Singleton.set_state(state)


def test_importlib_resource_load_zip_path() -> None:
    config_source = ImportlibResourcesConfigSource(provider="foo", path="pkg://bar")
    conf = config_source._read_config(
        zipfile.Path("hydra/test_utils/configs/conf.zip", "config.yaml")
    )
    assert conf.config == {"foo": "bar"}
    assert conf.header == {"package": None}


def test_importlib_resource_checks_do_not_require_exists(monkeypatch: Any) -> None:
    class TraversableWithoutExists:
        name = "missing.yaml"

        def __init__(self, *, is_file: bool = False, is_dir: bool = False) -> None:
            self._is_file = is_file
            self._is_dir = is_dir

        def joinpath(self, *_: str) -> Any:
            return self

        def is_file(self) -> bool:
            return self._is_file

        def is_dir(self) -> bool:
            return self._is_dir

    config_source = ImportlibResourcesConfigSource(
        provider="foo", path="pkg://hydra.conf"
    )
    monkeypatch.setattr(
        importlib_resources_config_source.resources,
        "files",
        lambda _: TraversableWithoutExists(),
    )

    assert not config_source.is_config("missing")
    assert not config_source.is_group("missing")
    with raises(ConfigLoadError, match="Config not found : missing.yaml"):
        config_source.load_config("missing")

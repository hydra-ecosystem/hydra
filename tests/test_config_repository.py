# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved
import copy
import os
import re
import subprocess
import zipfile
from pathlib import Path
from typing import Any
from unittest.mock import Mock

from pytest import MonkeyPatch, mark, param, raises, skip

from hydra._internal.config_repository import CachingConfigRepository, ConfigRepository
from hydra._internal.config_search_path_impl import ConfigSearchPathImpl
from hydra._internal.core_plugins import (
    file_config_source,
    importlib_resources_config_source,
)
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


@mark.parametrize("operation", ["load_config", "is_config", "is_group", "list"])
@mark.parametrize("escape", ["parent", "absolute", "same_prefix", "symlink"])
def test_file_source_rejects_escape(
    tmp_path: Path, monkeypatch: MonkeyPatch, operation: str, escape: str
) -> None:
    root = tmp_path / "conf"
    root.mkdir()
    outside = tmp_path / ("conf-sibling" if escape == "same_prefix" else "outside")
    (outside / "secret").mkdir(parents=True)
    (outside / "secret.yaml").write_text("value: 7\n")
    if escape == "symlink":
        try:
            (root / "escape").symlink_to(outside, target_is_directory=True)
        except OSError:
            skip("Directory symlinks are unavailable")
        config_path = "escape/secret"
    elif escape == "parent":
        config_path = "../outside/secret"
    else:
        config_path = str(outside / "secret")
    source = FileConfigSource(provider="test", path=str(root))
    read = Mock(side_effect=AssertionError("Outside config was opened"))
    listing = Mock(side_effect=AssertionError("Outside directory was listed"))
    monkeypatch.setattr(file_config_source, "open", read, raising=False)
    monkeypatch.setattr(os, "listdir", listing)

    with raises(ConfigLoadError, match="outside.*root"):
        if operation == "list":
            source.list(config_path, None)
        else:
            getattr(source, operation)(config_path)
    read.assert_not_called()
    listing.assert_not_called()


def test_file_source_lists_internal_links_and_rejects_external_links(
    tmp_path: Path,
) -> None:
    group = tmp_path / "group"
    group.mkdir()
    (group / "config.yaml").write_text("value: 7\n")
    try:
        (tmp_path / "alias").symlink_to(group, target_is_directory=True)
    except OSError:
        skip("Directory symlinks are unavailable")
    source = FileConfigSource(provider="test", path=str(tmp_path))
    assert source.load_config("alias/config").config == {"value": 7}
    assert source.is_config("alias/config")
    assert source.is_group("alias")
    assert source.list("alias", None) == ["config"]
    (tmp_path / "escape").symlink_to(tmp_path.parent, target_is_directory=True)
    with raises(ConfigLoadError, match="outside.*root"):
        source.list("", None)


def test_file_source_root_is_pinned(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    root = tmp_path / "conf"
    root.mkdir()
    (root / "config.yaml").write_text("value: 7\n")
    monkeypatch.chdir(tmp_path)
    source = FileConfigSource(provider="test", path="conf")
    monkeypatch.chdir(root)
    assert source.load_config("config").config == {"value": 7}
    assert source.list("", None) == ["config"]


def test_file_source_rejects_unresolvable_path(tmp_path: Path) -> None:
    source = FileConfigSource(provider="test", path=str(tmp_path))
    with raises(ConfigLoadError, match="Cannot resolve.*source root"):
        source.load_config("invalid\0name")


@mark.skipif(os.name != "nt", reason="Requires native Windows junctions")
def test_file_source_windows_junction(tmp_path: Path) -> None:
    root = tmp_path / "conf"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "config.yaml").write_text("value: 7\n")
    link = root / "escape"
    subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(link), str(outside)],
        check=True,
        capture_output=True,
    )
    try:
        source = FileConfigSource(provider="test", path=str(root))
        with raises(ConfigLoadError, match="outside.*root"):
            source.load_config("escape/config")
        with raises(ConfigLoadError, match="outside.*root"):
            source.list("", None)
    finally:
        os.rmdir(link)


@mark.skipif(os.name != "nt", reason="Requires native Windows path rules")
@mark.parametrize("outside", ["Z:\\outside\\config", "\\\\outside\\share\\config"])
def test_file_source_windows_roots(
    tmp_path: Path, monkeypatch: MonkeyPatch, outside: str
) -> None:
    source = FileConfigSource(provider="test", path=str(tmp_path))
    # Avoid accessing an actual remote share; exercise native drive/UNC comparison.
    monkeypatch.setattr(os.path, "realpath", lambda value: value)
    with raises(ConfigLoadError, match="source root"):
        source.is_config(outside)


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

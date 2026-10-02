# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved
import re
import subprocess
import sys
import warnings
from dataclasses import dataclass, field
from enum import Enum
from inspect import signature
from pathlib import Path
from typing import Any

from omegaconf import MISSING, OmegaConf
from pytest import fixture, mark, param, raises, warns

from hydra import (
    __version__,
    compose,
    initialize,
    initialize_config_dir,
    initialize_config_module,
    initialize_config_search_path,
    version,
)
from hydra._internal.config_search_path_impl import ConfigSearchPathImpl
from hydra.core.config_search_path import SearchPathQuery
from hydra.core.config_store import ConfigStore
from hydra.core.global_hydra import GlobalHydra
from hydra.errors import (
    ConfigCompositionException,
    Hydra15MigrationWarning,
    HydraDeprecationError,
    HydraException,
    OverrideParseException,
)
from hydra.test_utils.test_utils import chdir_hydra_root
from hydra.types import RunMode

chdir_hydra_root()

EXTEND_LIST_DEPRECATION_WARNING = (
    "extend_list(...) is deprecated and will be removed in Hydra 1.5. "
    "See https://github.com/hydra-ecosystem/hydra/issues/3200"
)


@fixture
def initialize_hydra(config_path: str | None) -> Any:
    try:
        init = initialize(config_path=config_path)
        init.__enter__()
        yield
    finally:
        init.__exit__(*sys.exc_info())


@fixture
def initialize_hydra_no_path() -> Any:
    try:
        init = initialize()
        init.__enter__()
        yield
    finally:
        init.__exit__(*sys.exc_info())


def test_initialize(hydra_restore_singletons: Any) -> None:
    assert not GlobalHydra().is_initialized()
    initialize()
    assert GlobalHydra().is_initialized()


@mark.parametrize(
    "version_base", ["1.0", "1.1", "1.2", "1.2.0", "1.2.0.dev2", "1.2.0rc1"]
)
def test_initialize_old_version_base(
    hydra_restore_singletons: Any, version_base: str
) -> None:
    assert not GlobalHydra().is_initialized()
    with raises(
        HydraException,
        match=(
            f"version_base={version_base!r} is not supported in Hydra 1.4; "
            "omit version_base to use the current behavior"
        ),
    ):
        initialize(version_base=version_base)


@mark.parametrize("version_base", [1.1, object()])
def test_initialize_bad_version_base(
    hydra_restore_singletons: Any, version_base: Any
) -> None:
    assert not GlobalHydra().is_initialized()
    with raises(TypeError):
        initialize(version_base=version_base)


@mark.parametrize("version_base", ["1.3", "1.3.0", "1.3.0.dev2", "1.3.0rc1", "1.4"])
def test_initialize_hydra_version_string_base(
    hydra_restore_singletons: Any, version_base: str
) -> None:
    assert not GlobalHydra().is_initialized()
    with warns(
        Hydra15MigrationWarning,
        match="The version_base parameter is deprecated and will be removed in Hydra 1.5",
    ):
        initialize(version_base=version_base)
    assert version.getbase() == version._get_version(version_base)


@mark.parametrize(
    "version_base",
    ["1", "one.two", "1.2rc1", "1.2.bad", "1.2.0a1", "1.2.0b1"],
)
def test_initialize_invalid_version_base(
    hydra_restore_singletons: Any, version_base: str
) -> None:
    with raises(ValueError, match="Invalid version"):
        initialize(version_base=version_base)


def test_initialize_cur_version_base(hydra_restore_singletons: Any) -> None:
    assert not GlobalHydra().is_initialized()
    with warns(
        Hydra15MigrationWarning,
        match="The version_base parameter is deprecated and will be removed in Hydra 1.5",
    ):
        initialize(version_base=None)
    assert version.getbase() == version._get_version(__version__)


def test_initialize_config_module_version_base_is_deprecated(
    hydra_restore_singletons: Any,
) -> None:
    with warns(Hydra15MigrationWarning):
        initialize_config_module(
            config_module="examples.jupyter_notebooks.cloud_app.conf",
            version_base="1.3",
        )


def test_initialize_config_dir_version_base_is_deprecated(
    hydra_restore_singletons: Any, tmp_path: Path
) -> None:
    with warns(Hydra15MigrationWarning):
        initialize_config_dir(config_dir=str(tmp_path), version_base="1.3")


def test_initialize_omitted_version_base(hydra_restore_singletons: Any) -> None:
    assert not GlobalHydra().is_initialized()
    initialize()
    assert version.getbase() == version._get_version(__version__)


def test_suppress_version_base_warning(hydra_restore_singletons: Any) -> None:
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        warnings.filterwarnings("ignore", category=Hydra15MigrationWarning)
        initialize(version_base=None)
        warnings.warn("unrelated warning", UserWarning)

    assert [str(item.message) for item in caught] == ["unrelated warning"]


def test_version_base_warning_as_error(
    hydra_restore_singletons: Any, monkeypatch: Any
) -> None:
    monkeypatch.setenv("HYDRA_DEPRECATION_WARNINGS_AS_ERRORS", "1")
    with raises(
        HydraDeprecationError,
        match="The version_base parameter is deprecated and will be removed in Hydra 1.5",
    ):
        initialize(version_base=None)


def test_initialize_with_config_path(hydra_restore_singletons: Any) -> None:
    assert not GlobalHydra().is_initialized()
    initialize(config_path="../hydra/test_utils/configs")
    assert GlobalHydra().is_initialized()

    gh = GlobalHydra.instance()
    assert gh.hydra is not None
    config_search_path = gh.hydra.config_loader.get_search_path()
    assert isinstance(config_search_path, ConfigSearchPathImpl)
    idx = config_search_path.find_first_match(
        SearchPathQuery(provider="main", path=None)
    )
    assert idx != -1


def test_initialize_config_search_path_composes_across_sources(
    hydra_restore_singletons: Any, tmp_path: Path
) -> None:
    (tmp_path / "config.yaml").write_text(
        "defaults:\n  - group1: file1\n  - _self_\nsource: external\n",
        encoding="utf-8",
    )
    paths = [f"file://{tmp_path}", "pkg://hydra.test_utils.configs"]

    with initialize_config_search_path(paths):
        assert compose(config_name="config") == {"foo": 10, "source": "external"}
        search_path = GlobalHydra.instance().config_loader().get_search_path()
        assert [
            entry.path for entry in search_path.get_path() if entry.provider == "main"
        ] == paths


def test_initialize_config_search_path_uses_first_match(
    hydra_restore_singletons: Any, tmp_path: Path
) -> None:
    first, second = tmp_path / "first", tmp_path / "second"
    first.mkdir()
    second.mkdir()
    (first / "config.yaml").write_text("source: first\n", encoding="utf-8")
    (second / "config.yaml").write_text("source: second\n", encoding="utf-8")

    with initialize_config_search_path([f"file://{first}", f"file://{second}"]):
        assert compose(config_name="config") == {"source": "first"}
    with initialize_config_search_path([f"file://{second}", f"file://{first}"]):
        assert compose(config_name="config") == {"source": "second"}


def test_initialize_config_search_path_caller_directory(
    hydra_restore_singletons: Any,
) -> None:
    with initialize_config_search_path(["caller://"]):
        search_path = GlobalHydra.instance().config_loader().get_search_path()
        assert [
            entry.path for entry in search_path.get_path() if entry.provider == "main"
        ] == [f"file://{Path(__file__).resolve().parent}"]
        cfg = compose(config_name="test_apps/app_with_cfg_groups/conf/optimizer/adam")
        assert cfg.test_apps.app_with_cfg_groups.conf.optimizer.type == "adam"


def test_initialize_config_search_path_caller_relative_directory(
    hydra_restore_singletons: Any,
) -> None:
    with initialize_config_search_path(["caller://test_apps/app_with_cfg_groups/conf"]):
        search_path = GlobalHydra.instance().config_loader().get_search_path()
        assert [
            entry.path for entry in search_path.get_path() if entry.provider == "main"
        ] == [
            f"file://{Path(__file__).resolve().parent / 'test_apps/app_with_cfg_groups/conf'}"
        ]
        assert compose(config_name="optimizer/adam").optimizer.type == "adam"


def test_initialize_config_search_path_restores_global_hydra(
    hydra_restore_singletons: Any, tmp_path: Path
) -> None:
    (tmp_path / "config.yaml").write_text("source: outer\n", encoding="utf-8")
    with initialize_config_search_path(
        ["pkg://hydra.test_utils.configs"], job_name="inner"
    ):
        assert compose(return_hydra_config=True).hydra.job.name == "inner"
    assert not GlobalHydra.instance().is_initialized()

    with initialize_config_dir(config_dir=str(tmp_path)):
        assert compose(config_name="config") == {"source": "outer"}
    assert not GlobalHydra.instance().is_initialized()


def test_initialize_config_search_path_globally(
    hydra_restore_singletons: Any,
) -> None:
    initialize_config_search_path(["pkg://hydra.test_utils.configs"])
    assert GlobalHydra.instance().is_initialized()
    assert compose(config_name="group1/file1") == {"foo": 10}


@mark.parametrize(
    ("paths", "message"),
    [
        ([], "at least one"),
        ("pkg://hydra.test_utils.configs", "sequence"),
        ([42], "entry 0"),
        (["hydra.test_utils.configs"], "URI"),
        (["pkg://"], "entry 0"),
        (["file://relative/path"], "absolute"),
        (["caller:///absolute/path"], "relative"),
        (["caller://pkg://module"], "relative"),
    ],
)
def test_initialize_config_search_path_rejects_invalid_entries(
    hydra_restore_singletons: Any, paths: Any, message: str
) -> None:
    with raises(HydraException, match=message):
        initialize_config_search_path(paths)
    assert not GlobalHydra.instance().is_initialized()


def test_initialize_config_search_path_rejects_unregistered_scheme(
    hydra_restore_singletons: Any,
) -> None:
    with raises(ValueError, match="No config source registered for schema unknown"):
        initialize_config_search_path(["unknown://configs"])


def test_initialize_config_search_path_has_no_version_base_parameter() -> None:
    assert "version_base" not in signature(initialize_config_search_path).parameters


@mark.usefixtures("initialize_hydra")
@mark.parametrize("config_path", ["../hydra/test_utils/configs"])
@mark.parametrize(
    "config_file, overrides, expected",
    [
        (None, [], {}),
        (None, ["+foo=bar"], {"foo": "bar"}),
        ("compose", [], {"foo": 10, "bar": 100}),
        ("compose", ["group1=file2"], {"foo": 20, "bar": 100}),
        (None, ["+top_level_list=file1"], {"top_level_list": ["a"]}),
        (
            None,
            ["+top_level_list=file1", "top_level_list.0=b"],
            {"top_level_list": ["b"]},
        ),
    ],
)
class TestCompose:
    def test_compose_config(
        self,
        config_file: str,
        overrides: list[str],
        expected: Any,
    ) -> None:
        cfg = compose(config_file, overrides)
        assert cfg == expected

    def test_strict_failure_global_strict(
        self, config_file: str, overrides: list[str], expected: Any
    ) -> None:
        # default strict True, call is unspecified
        overrides.append("fooooooooo=bar")
        with raises(HydraException):
            compose(config_file, overrides)


@mark.usefixtures("initialize_hydra")
@mark.parametrize("config_path", ["../hydra/test_utils/configs"])
def test_top_level_config_is_list() -> None:
    with raises(
        HydraException,
        match="primary config 'top_level_list/file1' must be a DictConfig, got ListConfig",
    ):
        compose("top_level_list/file1", overrides=[])


@mark.usefixtures("hydra_restore_singletons")
@mark.parametrize(
    "config_file, overrides, expected",
    [
        # empty
        (None, [], {}),
        (
            None,
            ["+db=sqlite"],
            {
                "db": {
                    "driver": "sqlite",
                    "user": "???",
                    "pass": "???",
                    "file": "test.db",
                }
            },
        ),
        (
            None,
            ["+db=mysql", "+environment=production"],
            {"db": {"driver": "mysql", "user": "mysql", "pass": "r4Zn*jQ9JB1Rz2kfz"}},
        ),
        (
            None,
            ["+db=mysql", "+environment=production", "+application=donkey"],
            {
                "db": {"driver": "mysql", "user": "mysql", "pass": "r4Zn*jQ9JB1Rz2kfz"},
                "donkey": {"name": "kong", "rank": "king"},
            },
        ),
        (
            None,
            [
                "+db=mysql",
                "+environment=production",
                "+application=donkey",
                "donkey.name=Dapple",
                "donkey.rank=squire_donkey",
            ],
            {
                "db": {"driver": "mysql", "user": "mysql", "pass": "r4Zn*jQ9JB1Rz2kfz"},
                "donkey": {"name": "Dapple", "rank": "squire_donkey"},
            },
        ),
        # load config
        (
            "config",
            [],
            {
                "db": {
                    "driver": "sqlite",
                    "user": "test",
                    "pass": "test",
                    "file": "test.db",
                },
                "cloud": {"name": "local", "host": "localhost", "port": 9876},
            },
        ),
        (
            "config",
            ["environment=production", "db=mysql"],
            {
                "db": {"driver": "mysql", "user": "mysql", "pass": "r4Zn*jQ9JB1Rz2kfz"},
                "cloud": {"name": "local", "host": "localhost", "port": 9876},
            },
        ),
    ],
)
class TestComposeInits:
    def test_initialize_ctx(
        self, config_file: str, overrides: list[str], expected: Any
    ) -> None:
        with initialize(
            config_path="../examples/jupyter_notebooks/cloud_app/conf",
        ):
            ret = compose(config_file, overrides)
            assert ret == expected

    def test_initialize_config_dir_ctx_with_relative_dir(
        self, config_file: str, overrides: list[str], expected: Any
    ) -> None:
        with raises(
            HydraException,
            match=re.escape(
                "initialize_config_dir() requires an absolute config_dir as input"
            ),
        ):
            with initialize_config_dir(
                config_dir="../examples/jupyter_notebooks/cloud_app/conf",
                job_name="job_name",
            ):
                ret = compose(config_file, overrides)
                assert ret == expected

    def test_initialize_config_module_ctx(
        self, config_file: str, overrides: list[str], expected: Any
    ) -> None:
        with initialize_config_module(
            config_module="examples.jupyter_notebooks.cloud_app.conf",
            job_name="job_name",
        ):
            ret = compose(config_file, overrides)
            assert ret == expected


def test_initialize_ctx_with_absolute_dir(
    hydra_restore_singletons: Any, tmp_path: Path
) -> None:
    (tmp_path / "config.yaml").write_text("source: absolute\n", encoding="utf-8")
    with initialize(config_path=str(tmp_path)):
        assert compose(config_name="config") == {"source": "absolute"}


def test_initialize_config_dir_ctx_with_absolute_dir(
    hydra_restore_singletons: Any, tmpdir: Any
) -> None:
    tmpdir = Path(tmpdir)
    (tmpdir / "test_group").mkdir(parents=True)
    cfg = OmegaConf.create({"foo": "bar"})

    cfg_file = tmpdir / "test_group" / "test.yaml"
    with open(str(cfg_file), "w") as f:
        OmegaConf.save(cfg, f)

    with initialize_config_dir(
        config_dir=str(tmpdir),
    ):
        ret = compose(overrides=["+test_group=test"])
        assert ret == {"test_group": cfg}


@mark.parametrize(
    "job_name,expected", [(None, "test_compose"), ("test_job", "test_job")]
)
def test_jobname_override_initialize_ctx(
    hydra_restore_singletons: Any, job_name: str | None, expected: str
) -> None:
    with initialize(
        config_path="../examples/jupyter_notebooks/cloud_app/conf",
        job_name=job_name,
    ):
        ret = compose(return_hydra_config=True)
        assert ret.hydra.job.name == expected


def test_jobname_override_initialize_config_dir_ctx(
    hydra_restore_singletons: Any, tmpdir: Any
) -> None:
    with initialize_config_dir(config_dir=str(tmpdir), job_name="test_job"):
        ret = compose(return_hydra_config=True)
        assert ret.hydra.job.name == "test_job"


def test_initialize_config_module_ctx(hydra_restore_singletons: Any) -> None:
    with initialize_config_module(
        config_module="examples.jupyter_notebooks.cloud_app.conf",
    ):
        ret = compose(return_hydra_config=True)
        assert ret.hydra.job.name == "app"

    with initialize_config_module(
        config_module="examples.jupyter_notebooks.cloud_app.conf",
        job_name="test_job",
    ):
        ret = compose(return_hydra_config=True)
        assert ret.hydra.job.name == "test_job"

    with initialize_config_module(
        config_module="examples.jupyter_notebooks.cloud_app.conf",
        job_name="test_job",
    ):
        ret = compose(return_hydra_config=True)
        assert ret.hydra.job.name == "test_job"


def test_namespace_config_module_error(hydra_restore_singletons: Any) -> None:
    expected = (
        "Primary config module 'hydra.test_utils.configs.missing_init_py' not found."
        "\nCheck that it's an importable regular Python package containing configs."
    )

    with raises(Exception, match=re.escape(expected)):
        with initialize_config_module(
            config_module="hydra.test_utils.configs.missing_init_py",
        ):
            hydra = GlobalHydra.instance().hydra
            assert hydra is not None
            compose(config_name="test.yaml", overrides=[])


def test_missing_bad_config_dir_error(hydra_restore_singletons: Any) -> None:
    # Use a platform-appropriate absolute path that doesn't exist
    if sys.platform == "win32":
        bad_dir = "C:\\no_way_in_hell_1234567890"
    else:
        bad_dir = "/no_way_in_hell_1234567890"

    expected = (
        "Primary config directory not found."
        f"\nCheck that the config directory '{bad_dir}' exists and readable"
    )

    with raises(Exception, match=re.escape(expected)):
        with initialize_config_dir(
            config_dir=bad_dir,
        ):
            hydra = GlobalHydra.instance().hydra
            assert hydra is not None
            compose(config_name="test.yaml", overrides=[])


def test_initialize_with_module(hydra_restore_singletons: Any) -> None:
    with initialize_config_module(
        config_module="tests.test_apps.app_with_cfg_groups.conf",
        job_name="my_pp",
    ):
        assert compose(config_name="config") == {
            "optimizer": {"type": "nesterov", "lr": 0.001}
        }


def test_hydra_main_passthrough(hydra_restore_singletons: Any) -> None:
    with initialize(config_path="test_apps/app_with_cfg_groups/conf"):
        from tests.test_apps.app_with_cfg_groups.my_app import my_app

        cfg = compose(config_name="config", overrides=["optimizer.lr=1.0"])
        assert my_app(cfg) == {"optimizer": {"type": "nesterov", "lr": 1.0}}


def test_initialization_root_module(monkeypatch: Any) -> None:
    monkeypatch.chdir("tests/test_apps/init_in_app_without_module")
    subprocess.check_call([sys.executable, "main.py"])
    subprocess.check_call([sys.executable, "-m", "main"])


@mark.usefixtures("initialize_hydra_no_path")
@mark.parametrize(
    ("overrides", "expected"),
    [
        param(["+map.foo=bar"], {"map": {"foo": "bar"}}, id="add_with_plus"),
        param(["map.foo=bar"], raises(ConfigCompositionException), id="add_no_plus"),
    ],
)
def test_adding_to_sc_dict(
    hydra_restore_singletons: Any, overrides: list[str], expected: Any
) -> None:
    @dataclass
    class Config:
        map: dict[str, str] = field(default_factory=dict)

    ConfigStore.instance().store(name="config", node=Config)

    if isinstance(expected, dict):
        cfg = compose(config_name="config", overrides=overrides)
        assert cfg == expected
    else:
        with expected:
            compose(config_name="config", overrides=overrides)


@mark.usefixtures("initialize_hydra_no_path")
@mark.parametrize(
    ("overrides", "expected"),
    [
        param(
            ["list_key=extend_list(d, e)"],
            {"list_key": ["a", "b", "c", "d", "e"]},
            id="extend_list_with_str",
        ),
        param(
            ["list_key=extend_list([d1, d2])"],
            {"list_key": ["a", "b", "c", ["d1", "d2"]]},
            id="extend_list_with_list",
        ),
        param(
            ["list_key=extend_list(d, [e1])", "list_key=extend_list(f)"],
            {"list_key": ["a", "b", "c", "d", ["e1"], "f"]},
            id="extend_list_twice",
        ),
        param(
            ["+list_key=extend_list([d1, d2])"],
            raises(OverrideParseException),
            id="extend_list_with_append_key",
        ),
    ],
)
def test_extending_list(
    hydra_restore_singletons: Any, overrides: list[str], expected: Any
) -> None:
    @dataclass
    class Config:
        list_key: Any = field(default_factory=lambda: ["a", "b", "c"])

    ConfigStore.instance().store(name="config", node=Config)

    if isinstance(expected, dict):
        with warns(
            UserWarning, match=re.escape(EXTEND_LIST_DEPRECATION_WARNING)
        ) as records:
            cfg = compose(config_name="config", overrides=overrides)
        assert cfg == expected
        assert len(records) == len(overrides)
    else:
        with expected:
            compose(config_name="config", overrides=overrides)


@mark.parametrize("override", ["hydra.foo=bar", "hydra.job_logging.foo=bar"])
def test_hydra_node_validated(initialize_hydra_no_path: Any, override: str) -> None:
    with raises(ConfigCompositionException):
        compose(overrides=[override])


@mark.usefixtures("hydra_restore_singletons")
@mark.usefixtures("initialize_hydra_no_path")
class TestAdd:
    def test_add(self) -> None:
        ConfigStore.instance().store(name="config", node={"key": 0})
        with raises(
            ConfigCompositionException,
            match="Could not append to config. An item is already at 'key'",
        ):
            compose(config_name="config", overrides=["+key=value"])

        cfg = compose(config_name="config", overrides=["key=1"])
        assert cfg == {"key": 1}

    def test_force_add(self) -> None:
        ConfigStore.instance().store(name="config", node={"key": 0})
        cfg = compose(config_name="config", overrides=["++key=1"])
        assert cfg == {"key": 1}

        cfg = compose(config_name="config", overrides=["++key2=1"])
        assert cfg == {"key": 0, "key2": 1}

    def test_add_config_group(self) -> None:
        ConfigStore.instance().store(group="group", name="a0", node={"key": 0})
        ConfigStore.instance().store(group="group", name="a1", node={"key": 1})
        # overriding non existing group throws
        with raises(ConfigCompositionException):
            compose(overrides=["group=a0"])

        # appending a new group
        cfg = compose(overrides=["+group=a0"])
        assert cfg == {"group": {"key": 0}}

        # force adding is not supported for config groups.
        with raises(
            ConfigCompositionException,
            match=re.escape(
                "force-add of config groups is not supported: '++group=a1'"
            ),
        ):
            compose(overrides=["++group=a1"])

    @mark.parametrize("override", ["+nested/choice=two", "+nested/choice=[two]"])
    def test_add_config_group_from_nested_primary_config(self, override: str) -> None:
        cs = ConfigStore.instance()
        cs.store(
            node={"a": 1},
            name="base",
            group="nested",
            package="_global_",
        )
        cs.store(
            node={"a": 2},
            name="two",
            group="nested/choice",
            package="_global_",
        )

        cfg = compose(config_name="nested/base", overrides=[override])

        assert cfg == {"a": 2}

    def test_add_config_group_from_nested_primary_config_uses_default_package(
        self,
    ) -> None:
        cs = ConfigStore.instance()
        cs.store(
            node={"a": 1},
            name="base",
            group="nested",
            package="_global_",
        )
        cs.store(
            node={"a": 2},
            name="two",
            group="nested/choice",
        )

        cfg = compose(config_name="nested/base", overrides=["+nested/choice=two"])

        assert cfg == {"a": 1, "nested": {"choice": {"a": 2}}}

    def test_add_to_structured_config(self, hydra_restore_singletons: Any) -> None:
        @dataclass
        class Config:
            a: int = 10

        ConfigStore.instance().store(name="config", node=Config, package="nested")

        assert compose("config", overrides=["+nested.b=20"]) == {
            "nested": {"a": 10, "b": 20}
        }

        assert compose("config", overrides=["++nested.a=30", "++nested.b=20"]) == {
            "nested": {"a": 30, "b": 20}
        }

        assert compose("config", overrides=["+nested.b.c=20"]) == {
            "nested": {"a": 10, "b": {"c": 20}}
        }


@mark.usefixtures("hydra_restore_singletons")
@mark.usefixtures("initialize_hydra_no_path")
class TestConfigSearchPathOverride:
    @fixture
    def init_configs(self) -> Any:
        cs = ConfigStore.instance()
        cs.store(
            name="with_sp",
            node={"hydra": {"searchpath": ["pkg://hydra.test_utils.configs"]}},
        )
        cs.store(name="without_sp", node={})

        cs.store(name="bad1", node={"hydra": {"searchpath": 42}})
        cs.store(name="bad2", node={"hydra": {"searchpath": [42]}})

        # Using this triggers an error. Only primary configs are allowed to override hydra.searchpath
        cs.store(
            group="group2",
            name="overriding_sp",
            node={"hydra": {"searchpath": ["abc"]}},
            package="_global_",
        )
        yield

    @mark.parametrize(
        ("config_name", "overrides", "expected"),
        [
            # config group is interpreted as simple config value addition.
            param("without_sp", ["+group1=file1"], {"group1": "file1"}, id="without"),
            param("with_sp", ["+group1=file1"], {"foo": 10}, id="with"),
            # Overriding hydra.searchpath
            param(
                "without_sp",
                ["hydra.searchpath=[pkg://hydra.test_utils.configs]", "+group1=file1"],
                {"foo": 10},
                id="sp_added_by_override",
            ),
            param(
                "with_sp",
                ["hydra.searchpath=[]", "+group1=file1"],
                {"group1": "file1"},
                id="sp_removed_by_override",
            ),
        ],
    )
    def test_searchpath_in_primary_config(
        self,
        init_configs: Any,
        config_name: str,
        overrides: list[str],
        expected: Any,
    ) -> None:
        cfg = compose(config_name=config_name, overrides=overrides)
        assert cfg == expected

    @mark.parametrize(
        ("config_name", "overrides", "expected"),
        [
            param(
                "bad1",
                [],
                raises(
                    ConfigCompositionException,
                    match=re.escape(
                        "hydra.searchpath must be a list of strings. Got: 42"
                    ),
                ),
                id="bad_cp_in_config",
            ),
            param(
                "bad2",
                [],
                raises(
                    ConfigCompositionException,
                    match=re.escape(
                        "hydra.searchpath must be a list of strings. Got: [42]"
                    ),
                ),
                id="bad_cp_element_in_config",
            ),
            param(
                "without_sp",
                ["hydra.searchpath=42"],
                raises(
                    ConfigCompositionException,
                    match=re.escape(
                        "hydra.searchpath must be a list of strings. Got: 42"
                    ),
                ),
                id="bad_override1",
            ),
            param(
                "without_sp",
                ["hydra.searchpath=[42]"],
                raises(
                    ConfigCompositionException,
                    match=re.escape(
                        "hydra.searchpath must be a list of strings. Got: [42]"
                    ),
                ),
                id="bad_override2",
            ),
            param(
                "without_sp",
                ["+group2=overriding_sp"],
                raises(
                    ConfigCompositionException,
                    match=re.escape(
                        "In 'group2/overriding_sp': Overriding hydra.searchpath "
                        "is only supported from the primary config"
                    ),
                ),
                id="overriding_sp_from_non_primary_config",
            ),
        ],
    )
    def test_searchpath_config_errors(
        self,
        init_configs: Any,
        config_name: str,
        overrides: list[str],
        expected: Any,
    ) -> None:
        with expected:
            compose(config_name=config_name, overrides=overrides)

    def test_searchpath_invalid(
        self,
        init_configs: Any,
    ) -> None:
        config_name = "without_sp"
        override = "hydra.searchpath=['pkg://fakeconf']"
        with warns(
            expected_warning=UserWarning,
            match=re.escape(
                "provider=hydra.searchpath in command-line, path=fakeconf is not available."
            ),
        ):
            compose(config_name=config_name, overrides=[override])

    def test_compose_searchpath_does_not_change_active_repository(
        self, init_configs: Any
    ) -> None:
        gh = GlobalHydra.instance()
        assert gh.hydra is not None
        cfg = gh.hydra.compose_config(
            config_name="with_sp",
            overrides=["+group1=file1"],
            run_mode=RunMode.RUN,
            from_shell=False,
            activate_config_repository=True,
        )
        assert cfg.foo == 10

        config_loader = gh.hydra.config_loader
        options = config_loader.get_group_options("group1")
        sources = [
            (source.provider, source.path) for source in config_loader.get_sources()
        ]
        assert options == ["abc.cde", "file1", "file2"]
        assert (
            "hydra.searchpath in main",
            "hydra.test_utils.configs",
        ) in sources

        assert compose(config_name="without_sp") == {}
        assert config_loader.get_group_options("group1") == options
        assert [
            (source.provider, source.path) for source in config_loader.get_sources()
        ] == sources


def test_initialize_without_config_path(tmpdir: Path) -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        with initialize():
            pass


@mark.usefixtures("initialize_hydra_no_path")
@mark.parametrize(
    ("overrides", "expected"),
    [
        param(
            ["hydra.hydra_logging=null"],
            raises(
                ConfigCompositionException,
                match="Error merging override hydra.hydra_logging=null",
            ),
            id="hydra.hydra_logging=null",
        ),
        param(
            ["hydra.job_logging=null"],
            raises(
                ConfigCompositionException,
                match="Error merging override hydra.job_logging=null",
            ),
            id="hydra.job_logging=null",
        ),
        param(
            ["hydra.job.chdir=null"],
            raises(
                ConfigCompositionException,
                match="Error merging override hydra.job.chdir=null",
            ),
            id="hydra.job.chdir=null",
        ),
    ],
)
def test_error_assigning_null_to_hydra_config(
    hydra_restore_singletons: Any, overrides: list[str], expected: Any
) -> None:
    with expected:
        compose(overrides=overrides)


@mark.parametrize(
    "strict",
    [
        param(None, id="strict=None"),
        param(True, id="strict=True"),
        param(False, id="strict=False"),
    ],
)
def test_removed_compose_strict_flag(strict: bool | None) -> None:
    compose_func = globals()["compose"]
    with raises(TypeError, match="got an unexpected keyword argument 'strict'"):
        compose_func(overrides=[], strict=strict)


@mark.usefixtures("initialize_hydra_no_path")
def test_missing_node_with_defaults_list(hydra_restore_singletons: Any) -> None:
    @dataclass
    class Reducer:
        defaults: list[Any] = field(default_factory=lambda: [])

    @dataclass
    class Trainer:
        reducer: Reducer = MISSING
        defaults: list[Any] = field(
            default_factory=lambda: [{"/reducer": "base_reducer"}]
        )

    cs = ConfigStore.instance()
    cs.store(name="base_trainer", node=Trainer(), group="trainer")
    cs.store(name="base_reducer", node=Reducer(), group="reducer")

    cfg = compose("trainer/base_trainer")
    assert cfg == {"trainer": {"reducer": {}}}


@mark.usefixtures("initialize_hydra_no_path")
def test_enum_with_removed_defaults_list(hydra_restore_singletons: Any) -> None:
    class Category(Enum):
        X = 0
        Y = 1
        Z = 2

    @dataclass
    class Conf:
        enum_dict: dict[Category, str] = field(default_factory=dict)
        int_dict: dict[int, str] = field(default_factory=dict)
        str_dict: dict[str, str] = field(default_factory=dict)

    cs = ConfigStore.instance()
    cs.store(name="conf", node=Conf)

    cfg = compose("conf")
    assert cfg == {"enum_dict": {}, "int_dict": {}, "str_dict": {}}

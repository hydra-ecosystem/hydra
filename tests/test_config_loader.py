# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved
import re
from dataclasses import dataclass, field
from textwrap import dedent
from typing import Any, cast

from omegaconf import MISSING, DictConfig, OmegaConf, ValidationError, open_dict
from omegaconf.errors import InterpolationResolutionError
from pytest import mark, param, raises

from hydra import __version__, version
from hydra._internal.config_loader_impl import ConfigLoaderImpl
from hydra._internal.utils import create_config_search_path
from hydra.core.config_store import ConfigStore, ConfigStoreWithProvider
from hydra.core.override_parser.overrides_parser import OverridesParser
from hydra.core.singleton import Singleton
from hydra.core.utils import env_override, setup_globals
from hydra.errors import (
    ConfigCompositionException,
    HydraException,
    MissingConfigException,
)
from hydra.plugins.config_source import ConfigLoadError
from hydra.test_utils.test_utils import chdir_hydra_root
from hydra.types import RunMode
from tests.instantiate import UserGroup

chdir_hydra_root()


@dataclass
class MySQLConfig:
    driver: str = MISSING
    host: str = MISSING
    port: int = MISSING
    user: str = MISSING
    password: str = MISSING


@dataclass
class TopLevelConfig:
    normal_yaml_config: bool = MISSING
    db: MySQLConfig = field(default_factory=MySQLConfig)


@mark.parametrize(
    "path",
    [
        param("file://hydra/test_utils/configs", id="file"),
        param("pkg://hydra.test_utils.configs", id="pkg"),
    ],
)
class TestConfigLoader:
    def test_load_configuration(self, path: str) -> None:
        config_loader = ConfigLoaderImpl(
            config_search_path=create_config_search_path(path)
        )
        cfg = config_loader.load_configuration(
            config_name="config.yaml",
            overrides=["+abc=123"],
            run_mode=RunMode.RUN,
        )
        with open_dict(cfg):
            del cfg["hydra"]
        assert cfg == {"normal_yaml_config": True, "abc": 123}

    def test_load_configuration_sets_current_version_base(
        self, path: str, hydra_restore_singletons: Any
    ) -> None:
        Singleton._instances.pop(version.VersionBase, None)
        config_loader = ConfigLoaderImpl(
            config_search_path=create_config_search_path(path)
        )
        cfg = config_loader.load_configuration(
            config_name="config.yaml",
            overrides=[],
            run_mode=RunMode.RUN,
        )
        assert cfg.hydra.runtime.version_base == version._get_version(__version__)

    def test_load_with_missing_default(self, path: str) -> None:
        config_loader = ConfigLoaderImpl(
            config_search_path=create_config_search_path(path)
        )
        with raises(MissingConfigException):
            config_loader.load_configuration(
                config_name="missing-default.yaml", overrides=[], run_mode=RunMode.RUN
            )

    def test_load_with_optional_default(self, path: str) -> None:
        config_loader = ConfigLoaderImpl(
            config_search_path=create_config_search_path(path)
        )
        cfg = config_loader.load_configuration(
            config_name="optional-default.yaml", overrides=[], run_mode=RunMode.RUN
        )
        with open_dict(cfg):
            del cfg["hydra"]
        assert cfg == {"foo": 10}

    @mark.parametrize(
        "overrides,expected",
        [
            param(
                [],
                {"pkg1": {"group1_option1": True}, "pkg2": {"group1_option1": True}},
                id="baseline",
            ),
            param(
                ["+group1@pkg3=option1"],
                {
                    "pkg1": {"group1_option1": True},
                    "pkg2": {"group1_option1": True},
                    "pkg3": {"group1_option1": True},
                },
                id="append",
            ),
            param(
                ["~group1@pkg1"],
                {"pkg2": {"group1_option1": True}},
                id="delete_package",
            ),
        ],
    )
    def test_override_compose_two_package_one_group(
        self, path: str, overrides: list[str], expected: Any
    ) -> None:
        config_loader = ConfigLoaderImpl(
            config_search_path=create_config_search_path(f"{path}/package_tests")
        )
        cfg = config_loader.load_configuration(
            config_name="two_packages_one_group",
            overrides=overrides,
            run_mode=RunMode.RUN,
        )
        with open_dict(cfg):
            del cfg["hydra"]
        assert cfg == expected

    def test_load_adding_group_not_in_default(self, path: str) -> None:
        config_loader = ConfigLoaderImpl(
            config_search_path=create_config_search_path(path)
        )
        cfg = config_loader.load_configuration(
            config_name="optional-default.yaml",
            overrides=["+group2=file1"],
            run_mode=RunMode.RUN,
        )
        with open_dict(cfg):
            del cfg["hydra"]
        assert cfg == {"foo": 10, "bar": 100}

    def test_change_run_dir_with_override(self, path: str) -> None:
        config_loader = ConfigLoaderImpl(
            config_search_path=create_config_search_path(path)
        )
        cfg = config_loader.load_configuration(
            config_name="overriding_run_dir.yaml",
            overrides=["hydra.run.dir=abc"],
            run_mode=RunMode.RUN,
        )
        assert cfg.hydra.run.dir == "abc"

    def test_change_run_dir_with_config(self, path: str) -> None:
        config_loader = ConfigLoaderImpl(
            config_search_path=create_config_search_path(path)
        )
        cfg = config_loader.load_configuration(
            config_name="overriding_run_dir.yaml",
            overrides=[],
            run_mode=RunMode.RUN,
        )
        assert cfg.hydra.run.dir == "cde"

    def test_load_strict(self, path: str) -> None:
        """
        Ensure that in strict mode we can override only things that are already in the config
        :return:
        """
        config_loader = ConfigLoaderImpl(
            config_search_path=create_config_search_path(path)
        )
        # Test that overriding existing things works in strict mode
        cfg = config_loader.load_configuration(
            config_name="compose.yaml",
            overrides=["foo=ZZZ"],
            run_mode=RunMode.RUN,
        )
        with open_dict(cfg):
            del cfg["hydra"]
        assert cfg == {"foo": "ZZZ", "bar": 100}

        # Test that accessing a key that is not there will fail
        with raises(AttributeError):
            # noinspection PyStatementEffect
            cfg.not_here

        # Test that bad overrides triggers the KeyError
        with raises(HydraException):
            config_loader.load_configuration(
                config_name="compose.yaml",
                overrides=["f00=ZZZ"],
                run_mode=RunMode.RUN,
            )

    def test_load_yml_file(self, path: str, hydra_restore_singletons: Any) -> None:
        config_loader = ConfigLoaderImpl(
            config_search_path=create_config_search_path(path)
        )
        with raises(
            ConfigLoadError,
            match=re.escape(
                "Unsupported config file extension '.yml'. "
                "Hydra config files must use the '.yaml' extension."
            ),
        ):
            config_loader.load_configuration(
                config_name="config.yml",
                overrides=[],
                run_mode=RunMode.RUN,
            )

    def test_override_with_equals(self, path: str) -> None:
        config_loader = ConfigLoaderImpl(
            config_search_path=create_config_search_path(path)
        )
        cfg = config_loader.load_configuration(
            config_name="config",
            overrides=["+abc='cde=12'"],
            run_mode=RunMode.RUN,
        )
        with open_dict(cfg):
            del cfg["hydra"]
        assert cfg == OmegaConf.create({"normal_yaml_config": True, "abc": "cde=12"})

    def test_compose_file_with_dot(self, path: str) -> None:
        config_loader = ConfigLoaderImpl(
            config_search_path=create_config_search_path(path)
        )
        cfg = config_loader.load_configuration(
            config_name="compose.yaml",
            overrides=["group1=abc.cde"],
            run_mode=RunMode.RUN,
        )
        with open_dict(cfg):
            del cfg["hydra"]
        assert cfg == {"abc=cde": None, "bar": 100}

    def test_load_config_with_schema(
        self, hydra_restore_singletons: Any, path: str
    ) -> None:
        ConfigStore.instance().store(
            name="config_with_schema", node=TopLevelConfig, provider="this_test"
        )
        ConfigStore.instance().store(
            group="db", name="base_mysql", node=MySQLConfig, provider="this_test"
        )

        config_loader = ConfigLoaderImpl(
            config_search_path=create_config_search_path(path)
        )

        cfg = config_loader.load_configuration(
            config_name="config",
            overrides=["+db=validated_mysql"],
            run_mode=RunMode.RUN,
        )

        with open_dict(cfg):
            del cfg["hydra"]
        assert cfg == {
            "normal_yaml_config": True,
            "db": {
                "driver": "mysql",
                "host": "???",
                "port": "???",
                "user": "omry",
                "password": "secret",
            },
        }

        # verify illegal modification is rejected at runtime
        with raises(ValidationError):
            cfg.db.port = "fail"

        # verify illegal override is rejected during load
        with raises(HydraException):
            config_loader.load_configuration(
                config_name="db/mysql", overrides=["db.port=fail"], run_mode=RunMode.RUN
            )

    def test_config_store_schema_is_not_automatically_matched(
        self, hydra_restore_singletons: Any, path: str
    ) -> None:
        with ConfigStoreWithProvider("this_test") as cs:
            cs.store(name="config", node=TopLevelConfig)
            cs.store(group="db", name="mysql", node=MySQLConfig, package="db")

        config_loader = ConfigLoaderImpl(
            config_search_path=create_config_search_path(path)
        )

        cfg = config_loader.load_configuration(
            config_name="config",
            overrides=["+db=mysql"],
            run_mode=RunMode.RUN,
        )

        with open_dict(cfg):
            del cfg["hydra"]
        assert cfg == {
            "normal_yaml_config": True,
            "db": {
                "driver": "mysql",
                "user": "omry",
                "password": "secret",
            },
        }

    def test_load_config_with_validation_error(
        self, hydra_restore_singletons: Any, path: str
    ) -> None:
        ConfigStore.instance().store(
            name="base_mysql", node=MySQLConfig, provider="this_test"
        )
        config_loader = ConfigLoaderImpl(
            config_search_path=create_config_search_path(path)
        )

        msg = dedent("""\
            In 'schema_validation_error': ValidationError raised while composing config:
            Value 'not_an_int'( of type 'str')? could not be converted to Integer
                full_key: port
                object_type=MySQLConfig""")
        with raises(ConfigCompositionException, match=msg):
            config_loader.load_configuration(
                config_name="schema_validation_error",
                overrides=[],
                run_mode=RunMode.RUN,
            )

    def test_load_config_with_key_error(
        self, hydra_restore_singletons: Any, path: str
    ) -> None:
        ConfigStore.instance().store(
            name="base_mysql", node=MySQLConfig, provider="this_test"
        )
        config_loader = ConfigLoaderImpl(
            config_search_path=create_config_search_path(path)
        )

        msg = dedent("""\
            In 'schema_key_error': ConfigKeyError raised while composing config:
            Key 'foo' not in 'MySQLConfig'
                full_key: foo
                object_type=MySQLConfig""")
        with raises(ConfigCompositionException, match=re.escape(msg)):
            config_loader.load_configuration(
                config_name="schema_key_error",
                overrides=[],
                run_mode=RunMode.RUN,
            )

    def test_assign_null(self, hydra_restore_singletons: Any, path: str) -> None:
        config_loader = ConfigLoaderImpl(
            config_search_path=create_config_search_path(path)
        )
        cfg = config_loader.load_configuration(
            config_name="config.yaml", overrides=["+abc=null"], run_mode=RunMode.RUN
        )
        with open_dict(cfg):
            del cfg["hydra"]
        assert cfg == {"normal_yaml_config": True, "abc": None}

    def test_sweep_config_cache(
        self, hydra_restore_singletons: Any, path: str, monkeypatch: Any
    ) -> None:
        setup_globals()

        # pseudorandom resolvers with/without value caching
        pseudorandom_values = iter(["1st", "2nd", "3rd", "4th"])
        OmegaConf.register_resolver(
            "cached", lambda: next(pseudorandom_values), use_cache=True, replace=True
        )
        OmegaConf.register_resolver(
            "uncached", lambda: next(pseudorandom_values), use_cache=False, replace=True
        )

        monkeypatch.setenv("TEST_ENV", "test_env")

        config_loader = ConfigLoaderImpl(
            config_search_path=create_config_search_path(path)
        )
        master_cfg = config_loader.load_configuration(
            config_name="config.yaml",
            overrides=[
                "+time=${now:%H-%M-%S}",
                "+test_env=${oc.env:TEST_ENV}",
                "+test_cached=${cached:}",
                "+test_uncached=${uncached:}",
            ],
            run_mode=RunMode.RUN,
        )

        # trigger resolution by type assertion
        assert type(master_cfg.time) is str
        assert type(master_cfg.test_env) is str
        assert type(master_cfg.test_cached) is str  # "1st"
        assert type(master_cfg.test_uncached) is str  # "2nd"

        master_cfg_cache = OmegaConf.get_cache(master_cfg)
        assert "now" in master_cfg_cache.keys()
        # oc.env is not cached as of OmegaConf 2.1
        assert "oc.env" not in master_cfg_cache.keys()
        assert master_cfg.test_env == "test_env"
        assert "cached" in master_cfg_cache.keys()
        assert master_cfg.test_cached == "1st"  # use cached value
        assert "uncached" not in master_cfg_cache.keys()
        assert master_cfg.test_uncached == "3rd"  # use `next` value

        sweep_cfg = config_loader.load_sweep_config(
            master_config=master_cfg,
            sweep_overrides=[
                "+time=${now:%H-%M-%S}",
                "+test_env=${oc.env:TEST_ENV}",
                "+test_cached=${cached:}",
                "+test_uncached=${uncached:}",
            ],
        )

        sweep_cfg_cache = OmegaConf.get_cache(sweep_cfg)
        assert len(sweep_cfg_cache.keys()) == 2  # "now", and "cached"
        assert "now" in sweep_cfg_cache.keys()
        assert "oc.env" not in sweep_cfg_cache.keys()
        assert "cached" in sweep_cfg_cache.keys()
        assert "uncached" not in sweep_cfg_cache.keys()
        assert sweep_cfg_cache["now"] == master_cfg_cache["now"]
        assert sweep_cfg_cache["cached"] == master_cfg_cache["cached"]
        monkeypatch.setenv("TEST_ENV", "test_env2")
        assert sweep_cfg.test_env == "test_env2"
        assert master_cfg.test_cached == "1st"  # use cached value
        assert master_cfg.test_uncached == "4th"  # use `next` value


def test_defaults_not_list_exception() -> None:
    config_loader = ConfigLoaderImpl(
        config_search_path=create_config_search_path("hydra/test_utils/configs")
    )
    with raises(
        ConfigCompositionException,
        match="Invalid defaults list in 'defaults_not_list.yaml', defaults must be a list",
    ):
        config_loader.load_configuration(
            config_name="defaults_not_list.yaml",
            overrides=[],
            run_mode=RunMode.RUN,
        )


def test_config_store_defaults_list_error_provenance(
    hydra_restore_singletons: Any,
) -> None:
    cs = ConfigStore.instance()
    cs.store(name="provenance_missing", node={"defaults": [{"db": "???"}]})
    cs.store(group="db", name="first", node={})
    cs.store(group="db", name="second", node={})
    cs.store(name="provenance_nested", node={"defaults": [{"db": "second"}]})
    cs.store(
        name="provenance_conflict",
        node={"defaults": [{"db": "first"}, "provenance_nested"]},
    )
    cs.store(name="provenance_invalid", node={"defaults": {"db": "first"}})
    config_loader = ConfigLoaderImpl(config_search_path=create_config_search_path(None))

    with raises(ConfigCompositionException, match="In 'provenance_missing':") as e:
        config_loader.load_configuration(
            config_name="provenance_missing", overrides=[], run_mode=RunMode.RUN
        )
    assert "You must specify 'db'" in str(e.value)

    with raises(ConfigCompositionException, match="Multiple values for db") as e:
        config_loader.load_configuration(
            config_name="provenance_conflict", overrides=[], run_mode=RunMode.RUN
        )
    assert "'second' from 'provenance_nested'" in str(e.value)
    assert "'first' from 'provenance_conflict'" in str(e.value)

    with raises(ConfigCompositionException, match="provenance_invalid") as e:
        config_loader.load_configuration(
            config_name="provenance_invalid", overrides=[], run_mode=RunMode.RUN
        )
    assert "defaults must be a list (got mapping)" in str(e.value)


def test_override_hydra_config_value_from_config_file() -> None:
    config_loader = ConfigLoaderImpl(
        config_search_path=create_config_search_path("hydra/test_utils/configs")
    )

    cfg = config_loader.load_configuration(
        config_name="overriding_output_dir.yaml",
        overrides=[],
        run_mode=RunMode.RUN,
    )
    assert cfg.hydra.run.dir == "foo"


def test_list_groups() -> None:
    config_loader = ConfigLoaderImpl(
        config_search_path=create_config_search_path(
            "examples/jupyter_notebooks/cloud_app/conf"
        )
    )
    groups = config_loader.list_groups("")
    assert sorted(groups) == [
        "application",
        "cloud_provider",
        "db",
        "environment",
        "hydra",
    ]

    assert sorted(config_loader.list_groups("hydra")) == [
        "env",
        "help",
        "hydra_help",
        "hydra_logging",
        "job_logging",
        "launcher",
        "output",
        "sweeper",
    ]


def test_load_schema_as_config(hydra_restore_singletons: Any) -> None:
    """
    Load structured config as a configuration
    """
    ConfigStore.instance().store(
        name="config", node=TopLevelConfig, provider="this_test"
    )

    ConfigStore.instance().store(
        name="db/mysql", node=MySQLConfig, provider="this_test"
    )

    config_loader = ConfigLoaderImpl(config_search_path=create_config_search_path(None))
    cfg = config_loader.load_configuration(
        config_name="config", overrides=[], run_mode=RunMode.RUN
    )

    with open_dict(cfg):
        del cfg["hydra"]
    assert cfg == {
        "normal_yaml_config": "???",
        "db": {
            "driver": MISSING,
            "host": MISSING,
            "port": MISSING,
            "user": MISSING,
            "password": MISSING,
        },
    }


@dataclass
class Plugin:
    name: str = MISSING
    params: Any = MISSING


@dataclass
class ConcretePlugin(Plugin):
    name: str = "foobar_plugin"

    @dataclass
    class FoobarParams:
        foo: int = 10

    params: FoobarParams = field(default_factory=FoobarParams)


@dataclass
# A plugin that does not extend the parent Plugin class
class InvalidPlugin:
    name: str = "invalid_plugin"


@dataclass
class Config:
    plugin: Plugin = field(default_factory=Plugin)


def test_overlapping_schemas(hydra_restore_singletons: Any) -> None:
    cs = ConfigStore.instance()
    cs.store(name="config", node=Config)
    cs.store(group="plugin", name="concrete", node=ConcretePlugin)

    config_loader = ConfigLoaderImpl(config_search_path=create_config_search_path(None))
    cfg = config_loader.load_configuration(
        config_name="config", overrides=[], run_mode=RunMode.RUN
    )
    with open_dict(cfg):
        del cfg["hydra"]

    assert cfg == {"plugin": {"name": "???", "params": "???"}}
    assert OmegaConf.get_type(cfg.plugin) == Plugin

    cfg = config_loader.load_configuration(
        config_name="config", overrides=["+plugin=concrete"], run_mode=RunMode.RUN
    )
    with open_dict(cfg):
        del cfg["hydra"]

    assert cfg == {"plugin": {"name": "foobar_plugin", "params": {"foo": 10}}}
    assert OmegaConf.get_type(cfg.plugin) == ConcretePlugin
    assert OmegaConf.get_type(cfg.plugin.params) == ConcretePlugin.FoobarParams
    with raises(ValidationError):
        cfg.plugin = 10


def test_invalid_plugin_merge(hydra_restore_singletons: Any) -> Any:
    cs = ConfigStore.instance()
    cs.store(name="config", node=Config)
    cs.store(group="plugin", name="invalid", node=InvalidPlugin)

    cl = ConfigLoaderImpl(config_search_path=create_config_search_path(None))
    with raises(HydraException):
        cl.load_configuration(
            config_name="config", overrides=["plugin=invalid"], run_mode=RunMode.RUN
        )


def test_job_env_copy() -> None:
    config_loader = ConfigLoaderImpl(config_search_path=create_config_search_path(None))
    with env_override({"zonk": "123456"}):
        cfg = config_loader.load_configuration(
            config_name=None,
            overrides=["hydra.job.env_copy=[zonk]"],
            run_mode=RunMode.RUN,
        )
        assert cfg.hydra.job.env_set == {"zonk": "123456"}


@mark.parametrize(
    "overrides,expected",
    [
        (
            [],
            {
                "optimizer": {"type": "adam", "lr": 0.1, "beta": 0.01},
                "dataset": {"name": "imagenet", "path": "/datasets/imagenet"},
                "adam_imagenet": True,
            },
        ),
        (
            ["optimizer=nesterov"],
            {
                "optimizer": {"type": "nesterov", "lr": 0.001},
                "dataset": {"name": "imagenet", "path": "/datasets/imagenet"},
                "nesterov_imagenet": True,
            },
        ),
    ],
)
def test_complex_defaults(overrides: Any, expected: Any) -> None:
    config_loader = ConfigLoaderImpl(
        config_search_path=create_config_search_path(
            "tests/test_apps/sweep_complex_defaults/conf"
        )
    )

    cfg = config_loader.load_configuration(
        config_name="config", overrides=overrides, run_mode=RunMode.RUN
    )
    with open_dict(cfg):
        del cfg["hydra"]
    assert cfg == expected


@mark.parametrize(
    "input_cfg,overrides,expected",
    [
        # append
        param(
            {},
            ["x=10"],
            raises(
                HydraException,
                match=re.escape(
                    "Could not override 'x'.\nTo append to your config use +x=10"
                ),
            ),
            id="append:error:no_match",
        ),
        param({}, ["+x=10"], {"x": 10}, id="append"),
        param({}, ["+x=[1,2,3]"], {"x": [1, 2, 3]}, id="append:list"),
        param({}, ["+x={}"], {"x": {}}, id="append:dict:empty"),
        param({}, ["+x={a:1}"], {"x": {"a": 1}}, id="append:dict"),
        param({}, ["+x={a:1,b:2}"], {"x": {"a": 1, "b": 2}}, id="append:dict"),
        param({}, ["+x={a:10,b:20}"], {"x": {"a": 10, "b": 20}}, id="append:dict"),
        param(
            {"x": 20},
            ["+x=10"],
            raises(
                HydraException,
                match=re.escape(
                    "Could not append to config. An item is already at 'x'"
                ),
            ),
            id="append:error:already_there",
        ),
        # override
        param({"x": 20}, ["x=10"], {"x": 10}, id="override"),
        param({"x": 20}, ["x=10"], {"x": 10}, id="override"),
        param({"x": None}, ["x=[1,2,3]"], {"x": [1, 2, 3]}, id="override:list"),
        param({"x": 20}, ["x=null"], {"x": None}, id="override_with_null"),
        param({"x": {"a": 10}}, ["x={a:20}"], {"x": {"a": 20}}, id="merge_dict"),
        param(
            {"x": {"a": 10, "b": None}},
            ["x={b:20}"],
            {"x": {"a": 10, "b": 20}},
            id="merge_dict",
        ),
        param(
            {"x": {"a": 10}},
            ["+x={b:20}"],
            {"x": {"a": 10, "b": 20}},
            id="merge_dict",
        ),
        param(
            UserGroup,
            ["name=agents", "users=[]"],
            {"name": "agents", "users": []},
            id="merge_list",
        ),
        param(
            UserGroup,
            ["name=agents", "users=[{}]"],
            {"name": "agents", "users": [{"name": MISSING, "age": MISSING}]},
            id="merge_list",
        ),
        param(
            UserGroup,
            ["name=agents", "users=[{name:bond,age:7}]"],
            {"name": "agents", "users": [{"name": "bond", "age": 7}]},
            id="merge_list",
        ),
        param(
            UserGroup,
            ["name=agents", "users=[{name:bond,age:nope}]"],
            raises(
                ConfigCompositionException,
                match=re.escape("Error merging override users=[{name:bond,age:nope}]"),
            ),
            id="merge_list",
        ),
        # delete
        param({"x": 20}, ["~x"], {}, id="delete"),
        param({"x": 20}, ["~x=20"], {}, id="delete_strict"),
        param({"x": {"y": 10}}, ["~x"], {}, id="delete"),
        param({"x": {"y": 10}}, ["~x.y"], {"x": {}}, id="delete"),
        param({"x": {"y": 10}}, ["~x.y=10"], {"x": {}}, id="delete_strict"),
        param({"x": 20}, ["~x"], {}, id="delete"),
        param({"x": 20}, ["~x=20"], {}, id="delete_strict"),
        param({"x": {"y": 10}}, ["~x"], {}, id="delete"),
        param({"x": {"y": 10}}, ["~x.y"], {"x": {}}, id="delete"),
        param({"x": {"y": 10}}, ["~x.y=10"], {"x": {}}, id="delete_strict"),
        param({"x": [1, 2, 3]}, ["~x"], {}, id="delete:list"),
        param({"x": [1, 2, 3]}, ["~x=[1,2,3]"], {}, id="delete:list"),
        param({"x": [1, 2, 3]}, ["~x.0"], {"x": [2, 3]}, id="delete:list_item"),
        param({"x": [1, 2, 3]}, ["~x.1"], {"x": [1, 3]}, id="delete:list_item_middle"),
        param({"x": [None, 1]}, ["~x.0"], {"x": [1]}, id="delete:list_item_null"),
        param(
            {"x": [None, 1]},
            ["~x.0=null"],
            {"x": [1]},
            id="delete:list_item_null_strict",
        ),
        param({"x": [MISSING, 1]}, ["~x.0"], {"x": [1]}, id="delete:list_item_missing"),
        param(
            {"x": [MISSING, 1]},
            ["~x.0=???"],
            {"x": [1]},
            id="delete:list_item_missing_strict",
        ),
        param({"x": None}, ["~x"], {}, id="delete:null"),
        param({"x": {"y": None}}, ["~x.y"], {"x": {}}, id="delete:null_nested"),
        param({"x": None}, ["~x=null"], {}, id="delete:null_strict"),
        param({"x": MISSING}, ["~x=???"], {}, id="delete:missing_strict"),
        param({"x": MISSING}, ["~x"], {}, id="delete:missing"),
        param({"x": {"y": MISSING}}, ["~x.y"], {"x": {}}, id="delete:missing_nested"),
        param(
            {"x": 20},
            ["~z"],
            raises(
                HydraException,
                match=re.escape("Could not delete from config. 'z' does not exist."),
            ),
            id="delete_error_key",
        ),
        param(
            {"x": MISSING},
            ["~x.y"],
            raises(
                HydraException,
                match=re.escape("Could not delete from config. 'x.y' does not exist."),
            ),
            id="delete_error_missing_parent",
        ),
        param(
            {"x": None},
            ["~x.y"],
            raises(
                HydraException,
                match=re.escape("Could not delete from config. 'x.y' does not exist."),
            ),
            id="delete_error_null_parent",
        ),
        param(
            {"x": 20},
            ["~x=10"],
            raises(
                HydraException,
                match=re.escape(
                    "Could not delete from config. The value of 'x' is 20 and not 10."
                ),
            ),
            id="delete_error_value",
        ),
        param(
            {"x": 20},
            ["~x=null"],
            raises(
                HydraException,
                match=re.escape(
                    "Could not delete from config. The value of 'x' is 20 and not None."
                ),
            ),
            id="delete_error_value_null",
        ),
        param(
            {"x": 20},
            ["foo@bar=10"],
            raises(
                HydraException,
                match=re.escape(
                    "Override foo@bar=10 looks like a config group override, but config"
                    " group 'foo' does not exist."
                ),
            ),
            id="config_group_missing",
        ),
    ],
)
def test_apply_overrides_to_config(
    input_cfg: Any, overrides: list[str], expected: Any
) -> None:
    cfg = cast(DictConfig, OmegaConf.create(input_cfg))
    OmegaConf.set_struct(cfg, True)
    parser = OverridesParser.create()
    parsed = parser.parse_overrides(overrides=overrides)

    if isinstance(expected, dict):
        ConfigLoaderImpl._apply_overrides_to_config(overrides=parsed, cfg=cfg)
        assert cfg == expected
    else:
        with expected:
            ConfigLoaderImpl._apply_overrides_to_config(overrides=parsed, cfg=cfg)


@mark.parametrize(
    "config,overrides,expected",
    [
        param(
            "config",
            [],
            {"optimizer": {"type": "nesterov", "lr": 0.001}},
            id="default_choice",
        ),
        param(
            "config",
            ["optimizer=adam"],
            {"optimizer": {"type": "adam", "lr": 0.1, "beta": 0.01}},
            id="default_change",
        ),
        param(
            "config",
            ["optimizer={type:nesterov2,lr:1}"],
            {"optimizer": {"type": "nesterov2", "lr": 1}},
            id="dict_merge",
        ),
        param(
            "config",
            ["+optimizer={foo:10}"],
            {"optimizer": {"type": "nesterov", "lr": 0.001, "foo": 10}},
            id="dict_merge_append",
        ),
        param(
            # need to unset optimizer config group first, otherwise they get merged
            "missing_default",
            ["~optimizer", "+optimizer={type:super,good:true,fast:true}"],
            {"optimizer": {"type": "super", "good": True, "fast": True}},
            id="dict_replace_default",
        ),
    ],
)
def test_overriding_with_dict(config: str, overrides: Any, expected: Any) -> None:
    config_loader = ConfigLoaderImpl(
        config_search_path=create_config_search_path(
            "tests/test_apps/app_with_cfg_groups/conf"
        ),
    )

    cfg = config_loader.load_configuration(
        config_name=config, overrides=overrides, run_mode=RunMode.RUN
    )
    with open_dict(cfg):
        del cfg["hydra"]
    assert cfg == expected


@mark.parametrize(
    ("config", "overrides", "expected_choices"),
    [
        param(
            "config",
            [],
            {
                "optimizer": "nesterov",
                "hydra/env": "default",
                "hydra/callbacks": None,
                "hydra/hydra_help": "default",
                "hydra/help": "default",
                "hydra/output": "default",
                "hydra/sweeper": "basic",
                "hydra/launcher": "basic",
                "hydra/job_logging": "default",
                "hydra/hydra_logging": "default",
            },
            id="test_choices",
        ),
        param(
            "config",
            ["optimizer=adam"],
            {
                "optimizer": "adam",
                "hydra/env": "default",
                "hydra/callbacks": None,
                "hydra/hydra_help": "default",
                "hydra/help": "default",
                "hydra/output": "default",
                "hydra/sweeper": "basic",
                "hydra/launcher": "basic",
                "hydra/job_logging": "default",
                "hydra/hydra_logging": "default",
            },
            id="test_choices:override",
        ),
    ],
)
def test_hydra_choices(config: str, overrides: Any, expected_choices: Any) -> None:
    config_loader = ConfigLoaderImpl(
        config_search_path=create_config_search_path(
            "tests/test_apps/app_with_cfg_groups/conf"
        ),
    )

    cfg = config_loader.load_configuration(
        config_name=config, overrides=overrides, run_mode=RunMode.RUN
    )
    assert cfg.hydra.runtime.choices == expected_choices


def test_hydra_override_dirname_resolver_defaults(
    hydra_restore_singletons: Any,
) -> None:
    setup_globals()
    config_loader = ConfigLoaderImpl(
        config_search_path=create_config_search_path("hydra/test_utils/configs")
    )

    cfg = config_loader.load_configuration(
        config_name="config.yaml",
        overrides=["+b=2", "+a=1"],
        run_mode=RunMode.RUN,
    )
    with open_dict(cfg.hydra.sweep):
        cfg.hydra.sweep.subdir = "${hydra_override_dirname:}"

    assert OmegaConf.select(cfg, "hydra.sweep.subdir") == "+a=1,+b=2"


def test_hydra_override_dirname_resolver_options(
    hydra_restore_singletons: Any,
) -> None:
    setup_globals()
    config_loader = ConfigLoaderImpl(
        config_search_path=create_config_search_path("hydra/test_utils/configs")
    )

    cfg = config_loader.load_configuration(
        config_name="config.yaml",
        overrides=["+b=2", "+a=1", "+seed=123"],
        run_mode=RunMode.RUN,
    )
    with open_dict(cfg.hydra.sweep):
        cfg.hydra.sweep.subdir = (
            "${hydra_override_dirname:{kv_sep: '-', item_sep: '/', "
            "exclude_keys: [seed]}}"
        )

    assert OmegaConf.select(cfg, "hydra.sweep.subdir") == "+a-1/+b-2"


@mark.parametrize(
    ("options", "expected_error"),
    [
        param("{kv_sep: 1}", "hydra_override_dirname kv_sep must be a string"),
        param("{item_sep: 1}", "hydra_override_dirname item_sep must be a string"),
        param(
            "{exclude_keys: seed}",
            "hydra_override_dirname exclude_keys must be a list",
        ),
        param(
            "{exclude_keys: [seed, 1]}",
            "hydra_override_dirname exclude_keys must contain strings",
        ),
        param(
            "{element_resolver: 1}",
            "hydra_override_dirname element_resolver must be a string",
        ),
    ],
)
def test_hydra_override_dirname_resolver_validates_options(
    hydra_restore_singletons: Any, options: str, expected_error: str
) -> None:
    setup_globals()
    config_loader = ConfigLoaderImpl(
        config_search_path=create_config_search_path("hydra/test_utils/configs")
    )

    cfg = config_loader.load_configuration(
        config_name="config.yaml",
        overrides=["+a=1"],
        run_mode=RunMode.RUN,
    )
    with open_dict(cfg.hydra.sweep):
        cfg.hydra.sweep.subdir = f"${{hydra_override_dirname:{options}}}"

    with raises(InterpolationResolutionError, match=re.escape(expected_error)):
        OmegaConf.select(cfg, "hydra.sweep.subdir")


def test_hydra_override_dirname_resolver_options_from_config_node(
    hydra_restore_singletons: Any,
) -> None:
    setup_globals()
    config_loader = ConfigLoaderImpl(
        config_search_path=create_config_search_path("hydra/test_utils/configs")
    )

    cfg = config_loader.load_configuration(
        config_name="config.yaml",
        overrides=["+b=2", "+a=1", "+seed=123"],
        run_mode=RunMode.RUN,
    )
    with open_dict(cfg.hydra.sweep):
        cfg.hydra.sweep.override_dirname_options = {
            "kv_sep": "-",
            "item_sep": "/",
            "exclude_keys": ["seed"],
        }
        cfg.hydra.sweep.subdir = (
            "${hydra_override_dirname:${hydra.sweep.override_dirname_options}}"
        )

    assert OmegaConf.select(cfg, "hydra.sweep.subdir") == "+a-1/+b-2"


def test_hydra_override_dirname_resolver_element_resolver(
    hydra_restore_singletons: Any,
) -> None:
    setup_globals()
    try:
        OmegaConf.register_resolver(
            "pathsafe",
            lambda value: str(value).replace("/", "_").replace("\\", "_"),
            replace=True,
        )
        config_loader = ConfigLoaderImpl(
            config_search_path=create_config_search_path("hydra/test_utils/configs")
        )

        cfg = config_loader.load_configuration(
            config_name="config.yaml",
            overrides=["+models/temporal_nets=net2", "+seed=123"],
            run_mode=RunMode.RUN,
        )
        with open_dict(cfg.hydra.sweep):
            cfg.hydra.sweep.subdir = (
                "${hydra_override_dirname:{item_sep: '/', element_resolver: pathsafe}}"
            )

        assert (
            OmegaConf.select(cfg, "hydra.sweep.subdir")
            == "+models_temporal_nets=net2/+seed=123"
        )
    finally:
        OmegaConf.clear_resolver("pathsafe")


def test_hydra_job_override_dirname_uses_resolver(
    hydra_restore_singletons: Any,
) -> None:
    setup_globals()
    config_loader = ConfigLoaderImpl(
        config_search_path=create_config_search_path("hydra/test_utils/configs")
    )

    cfg = config_loader.load_configuration(
        config_name="config.yaml",
        overrides=["+x=1"],
        run_mode=RunMode.RUN,
    )

    assert "_override_dirname" not in cfg.hydra.job
    assert cfg.hydra.job.override_dirname == "+x=1"


def test_hydra_job_override_dirname_uses_legacy_options(
    hydra_restore_singletons: Any,
) -> None:
    setup_globals()
    config_loader = ConfigLoaderImpl(
        config_search_path=create_config_search_path("hydra/test_utils/configs")
    )

    cfg = config_loader.load_configuration(
        config_name="config.yaml",
        overrides=[
            "+a-1=2",
            "+a=1",
            "+seed=123",
            "hydra.job.config.override_dirname.kv_sep=-",
            "hydra.job.config.override_dirname.item_sep=/",
            "hydra.job.config.override_dirname.exclude_keys=[seed]",
        ],
        run_mode=RunMode.RUN,
    )

    assert cfg.hydra.job.override_dirname == "+a-1-2/+a-1"

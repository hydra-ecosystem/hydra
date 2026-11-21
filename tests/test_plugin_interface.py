# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved
import importlib
import pkgutil
import sys
import types
import warnings
from abc import ABCMeta
from importlib.metadata import entry_points
from typing import Any, Sequence

from omegaconf import DictConfig, OmegaConf
from pytest import MonkeyPatch, mark, raises, warns

from hydra.core.config_search_path import ConfigSearchPath
from hydra.core.config_store import ConfigStore
from hydra.core.plugins import Plugins, _warn_unenumerable_editable_namespace
from hydra.core.utils import JobReturn
from hydra.plugins.launcher import Launcher
from hydra.plugins.plugin import Plugin
from hydra.plugins.search_path_plugin import SearchPathPlugin
from hydra.plugins.sweeper import Sweeper
from hydra.types import HydraContext, TaskFunction
from hydra.utils import get_class

# This only test core plugins.
# Individual plugins are responsible to test that they are discoverable.
launchers = ["hydra._internal.core_plugins.basic_launcher.BasicLauncher"]
sweepers = ["hydra._internal.core_plugins.basic_sweeper.BasicSweeper"]
search_path_plugins: list[str] = []


class PluginWithNestedTarget(Launcher):
    def __init__(self, nested: DictConfig) -> None:
        self.nested = nested

    def setup(
        self,
        *,
        hydra_context: HydraContext,
        task_function: TaskFunction,
        config: DictConfig,
    ) -> None:
        pass

    def launch(
        self, job_overrides: Sequence[Sequence[str]], initial_job_idx: int
    ) -> Sequence[JobReturn]:
        raise NotImplementedError()


PluginWithNestedTarget.__module__ = "hydra._internal.core_plugins.test_plugin"


class ExternalLauncher(PluginWithNestedTarget):
    pass


class ImportFailingLauncher(PluginWithNestedTarget):
    def __init__(self) -> None:
        super().__init__(nested=OmegaConf.create({}))
        raise ImportError("optional dependency unavailable")


class ExternalSweeper(Sweeper):
    def setup(
        self,
        *,
        hydra_context: HydraContext,
        task_function: TaskFunction,
        config: DictConfig,
    ) -> None:
        pass

    def sweep(self, arguments: Sequence[str]) -> Any:
        return []


@mark.parametrize(
    "plugin_type, expected",
    [
        (Launcher, launchers),
        (Sweeper, sweepers),
        (SearchPathPlugin, search_path_plugins),
        (Plugin, launchers + sweepers + search_path_plugins),
    ],
)
def test_discover(plugin_type: type[Plugin], expected: list[str]) -> None:
    plugins = Plugins.instance().discover(plugin_type)
    expected_classes = [get_class(c) for c in expected]
    for ex in expected_classes:
        assert ex in plugins


def test_register_plugin() -> None:
    class MyPlugin(SearchPathPlugin):
        def manipulate_search_path(self, search_path: ConfigSearchPath) -> None: ...

    Plugins.instance().register(MyPlugin)

    assert MyPlugin in Plugins.instance().discover(Plugin)
    assert MyPlugin in Plugins.instance().discover(SearchPathPlugin)
    assert MyPlugin not in Plugins.instance().discover(Launcher)


def test_register_bad_plugin() -> None:
    class NotAPlugin: ...

    with raises(ValueError, match="Not a valid Hydra Plugin"):
        Plugins.instance().register(NotAPlugin)  # type: ignore


def test_registration_defers_external_discovery(
    monkeypatch: MonkeyPatch, hydra_restore_singletons: Any
) -> None:
    from hydra.core.singleton import Singleton

    loaded: list[str] = []
    entry = types.SimpleNamespace(
        name="external",
        load=lambda: loaded.append("external") or ExternalSweeper,
    )
    installed_entries = entry_points(group="hydra.plugins")
    monkeypatch.setattr(
        "hydra.core.plugins.entry_points", lambda **kwargs: [*installed_entries, entry]
    )
    monkeypatch.setattr(
        "hydra.core.plugins._warn_unenumerable_editable_namespace", lambda *args: None
    )
    Singleton._instances.pop(Plugins, None)
    plugins = Plugins.instance()
    plugins.register(ExternalLauncher)
    assert loaded == []

    assert ExternalLauncher in plugins.discover(Launcher)
    assert ExternalSweeper in plugins.discover(Sweeper)
    assert plugins.get_stats() is not None
    assert loaded == ["external"]


def test_discovery_preserves_imported_plugin_and_config(
    hydra_restore_singletons: Any,
) -> None:
    module = importlib.import_module("hydra._internal.core_plugins.basic_launcher")
    launcher = module.BasicLauncher
    cs = ConfigStore.instance()
    cs.store(
        group="hydra/launcher",
        name="basic",
        node={"custom": True},
        provider="test",
        replace=True,
    )

    plugins = Plugins.instance()
    plugins._initialize()

    assert module.BasicLauncher is launcher
    assert launcher in plugins.discover(Launcher)
    config = cs.load("hydra/launcher/basic.yaml")
    assert config.node == {"custom": True}
    assert config.provider == "test"


def test_entry_point_plugin_discovery(
    monkeypatch: MonkeyPatch, hydra_restore_singletons: Any
) -> None:
    original_import_module = importlib.import_module

    def import_module(name: str) -> Any:
        if name == "hydra_plugins":
            raise ImportError(name)
        return original_import_module(name)

    class EntryPoint:
        name = "external"

        def load(self) -> type[ExternalLauncher]:
            return ExternalLauncher

    with monkeypatch.context() as patch:
        patch.setattr("hydra.core.plugins.importlib.import_module", import_module)
        patch.setattr("hydra.core.plugins.entry_points", lambda group: [EntryPoint()])
        Plugins.instance()._initialize()
        assert ExternalLauncher in Plugins.instance().discover(Launcher)
        stats = Plugins.instance().get_stats()
        assert stats is not None
        assert "entry point: external" in stats.modules_import_time
        assert stats.total_time >= stats.total_modules_import_time


@mark.parametrize("error_type", [AttributeError, RuntimeError])
def test_bad_entry_point_does_not_stop_discovery(
    monkeypatch: MonkeyPatch,
    hydra_restore_singletons: Any,
    error_type: type[Exception],
) -> None:
    original_import_module = importlib.import_module

    def import_module(name: str) -> Any:
        if name == "hydra_plugins":
            raise ImportError(name)
        return original_import_module(name)

    class MissingEntryPoint:
        name = "missing"

        def load(self) -> None:
            raise error_type("plugin could not load")

    class ValidEntryPoint:
        name = "valid"

        def load(self) -> type[ExternalLauncher]:
            return ExternalLauncher

    with monkeypatch.context() as patch:
        patch.setattr("hydra.core.plugins.importlib.import_module", import_module)
        patch.setattr(
            "hydra.core.plugins.entry_points",
            lambda group: [MissingEntryPoint(), ValidEntryPoint()],
        )
        with warns(UserWarning, match="entry point 'missing'"):
            Plugins.instance()._initialize()
        assert ExternalLauncher in Plugins.instance().discover(Launcher)
        stats = Plugins.instance().get_stats()
        assert stats is not None
        assert "entry point: missing" in stats.modules_import_time


@mark.parametrize("entry_kind", ["absent", "same", "unrelated", "invalid", "failed"])
def test_namespace_plugin_migration_warning(
    monkeypatch: MonkeyPatch, hydra_restore_singletons: Any, entry_kind: str
) -> None:
    original_import = importlib.import_module
    original_walk = pkgutil.walk_packages
    namespace_path = ["test namespace"]
    namespace = types.SimpleNamespace(__name__="hydra_plugins", __path__=namespace_path)
    # The scanner can find aliases for a class defined outside hydra_plugins.
    module = types.SimpleNamespace(
        first=ExternalLauncher, alias=ExternalLauncher, imported_core_base=Plugin
    )

    def import_module(name: str) -> Any:
        if name == "hydra_plugins":
            return namespace
        if name == "hydra_plugins.legacy":
            return module
        return original_import(name)

    def walk_packages(path: Any, **kwargs: Any) -> Any:
        if path is namespace_path:
            return [(None, "hydra_plugins.legacy", False)]
        return original_walk(path=path, **kwargs)

    class EntryPoint:
        name = "legacy"

        def load(self) -> Any:
            if entry_kind == "failed":
                raise ImportError("missing plugin")
            return {
                "same": ExternalLauncher,
                "unrelated": ExternalSweeper,
                "invalid": object(),
            }[entry_kind]

    monkeypatch.setattr("hydra.core.plugins.importlib.import_module", import_module)
    monkeypatch.setattr("hydra.core.plugins.pkgutil.walk_packages", walk_packages)
    monkeypatch.setattr(
        "hydra.core.plugins.entry_points",
        lambda **kwargs: [] if entry_kind == "absent" else [EntryPoint()],
    )
    with warnings.catch_warnings(record=True) as recorded:
        warnings.simplefilter("always")
        plugins = Plugins.instance()
        plugins._initialize()
        assert ExternalLauncher in plugins.discover(Launcher)
        plugins.get_stats()
    migration = [item for item in recorded if item.category is FutureWarning]
    if entry_kind == "same":
        assert migration == []
    else:
        assert len(migration) == 1
        message = str(migration[0].message)
        assert (
            f"{ExternalLauncher.__module__}.{ExternalLauncher.__qualname__}" in message
        )
        assert "https://hydra.cc/docs/upgrades/1.3_to_1.4/plugin_discovery/" in message
    if entry_kind in {"invalid", "failed"}:
        assert any(item.category is UserWarning for item in recorded)


@mark.parametrize(
    "entry_kind,expected_names",
    [
        ("absent", ["NamespaceOne", "NamespaceTwo"]),
        ("same", ["NamespaceTwo"]),
        ("equal", ["NamespaceOne", "NamespaceTwo"]),
    ],
)
def test_namespace_warning_uses_class_identity(
    monkeypatch: MonkeyPatch,
    hydra_restore_singletons: Any,
    entry_kind: str,
    expected_names: list[str],
) -> None:
    class EqualMeta(ABCMeta):
        def __hash__(cls) -> int:
            return 1

        def __eq__(cls, other: object) -> bool:
            return isinstance(other, EqualMeta)

    class NamespaceOne(ExternalLauncher, metaclass=EqualMeta):
        pass

    class NamespaceTwo(ExternalLauncher, metaclass=EqualMeta):
        pass

    class DistinctEntryPlugin(ExternalLauncher, metaclass=EqualMeta):
        pass

    assert NamespaceOne is not NamespaceTwo
    assert NamespaceOne == NamespaceTwo == DistinctEntryPlugin
    original_import = importlib.import_module
    original_walk = pkgutil.walk_packages
    namespace_path = ["identity test namespace"]
    namespace = types.SimpleNamespace(__name__="hydra_plugins", __path__=namespace_path)
    module = types.SimpleNamespace(
        one=NamespaceOne, alias=NamespaceOne, two=NamespaceTwo
    )

    def import_module(name: str) -> Any:
        if name == "hydra_plugins":
            return namespace
        if name == "hydra_plugins.identity":
            return module
        return original_import(name)

    def walk_packages(path: Any, **kwargs: Any) -> Any:
        if path is namespace_path:
            return [(None, "hydra_plugins.identity", False)]
        return original_walk(path=path, **kwargs)

    class EntryPoint:
        name = "identity"

        def load(self) -> type[Launcher]:
            return NamespaceOne if entry_kind == "same" else DistinctEntryPlugin

    monkeypatch.setattr("hydra.core.plugins.importlib.import_module", import_module)
    monkeypatch.setattr("hydra.core.plugins.pkgutil.walk_packages", walk_packages)
    monkeypatch.setattr(
        "hydra.core.plugins.entry_points",
        lambda **kwargs: [] if entry_kind == "absent" else [EntryPoint()],
    )
    with warnings.catch_warnings(record=True) as recorded:
        warnings.simplefilter("always")
        Plugins.instance()._initialize()
    migration = [
        str(item.message) for item in recorded if item.category is FutureWarning
    ]
    assert len(migration) == len(expected_names)
    for name, message in zip(expected_names, migration, strict=True):
        assert f".{name}' relies on" in message


def test_editable_namespace_without_enumerable_plugins_warns() -> None:
    with warns(UserWarning, match="editable hydra_plugins namespace install"):
        _warn_unenumerable_editable_namespace(
            ["__editable__.example-1.0.finder.__path_hook__"], []
        )


def test_unrelated_entry_point_does_not_hide_editable_warning(
    monkeypatch: MonkeyPatch, hydra_restore_singletons: Any
) -> None:
    original_import_module = importlib.import_module
    namespace = types.SimpleNamespace(
        __name__="hydra_plugins",
        __path__=["__editable__.legacy_plugin-1.0.finder.__path_hook__"],
    )

    def import_module(name: str) -> Any:
        if name == "hydra_plugins":
            return namespace
        return original_import_module(name)

    class EntryPoint:
        name = "external"
        dist = types.SimpleNamespace(name="another-plugin")

        def load(self) -> type[ExternalLauncher]:
            return ExternalLauncher

    with monkeypatch.context() as patch:
        patch.setattr("hydra.core.plugins.importlib.import_module", import_module)
        patch.setattr("hydra.core.plugins.entry_points", lambda group: [EntryPoint()])
        with warns(UserWarning, match="editable hydra_plugins namespace install"):
            Plugins.instance()._initialize()


def test_matching_entry_point_covers_editable_namespace() -> None:
    entry_point = types.SimpleNamespace(
        dist=types.SimpleNamespace(name="legacy-plugin")
    )
    with warnings.catch_warnings(record=True) as recorded:
        _warn_unenumerable_editable_namespace(
            ["__editable__.legacy_plugin-1.0.finder.__path_hook__"], [entry_point]
        )
    assert recorded == []


def test_registered_plugins_outside_hydra_namespace(
    hydra_restore_singletons: Any,
) -> None:
    plugins = Plugins.instance()
    plugins.register(ExternalLauncher)
    plugins.register(ExternalSweeper)

    launcher = plugins._instantiate(
        OmegaConf.create(
            {
                "_target_": f"{ExternalLauncher.__module__}.{ExternalLauncher.__qualname__}",
                "nested": {},
            }
        )
    )
    sweeper = plugins._instantiate(
        OmegaConf.create(
            {"_target_": f"{ExternalSweeper.__module__}.{ExternalSweeper.__qualname__}"}
        )
    )
    assert isinstance(launcher, ExternalLauncher)
    assert isinstance(sweeper, ExternalSweeper)


def test_unregistered_plugin_is_rejected(hydra_restore_singletons: Any) -> None:
    with raises(RuntimeError, match="Unknown plugin class"):
        Plugins.instance()._instantiate(
            OmegaConf.create(
                {
                    "_target_": f"{ExternalLauncher.__module__}.{ExternalLauncher.__qualname__}"
                }
            )
        )


def test_plugin_constructor_import_error_is_preserved(
    hydra_restore_singletons: Any,
) -> None:
    plugins = Plugins.instance()
    plugins.register(ImportFailingLauncher)

    with raises(ImportError, match="^optional dependency unavailable$"):
        plugins._instantiate(
            OmegaConf.create(
                {
                    "_target_": f"{ImportFailingLauncher.__module__}.{ImportFailingLauncher.__qualname__}"
                }
            )
        )


def test_plugin_instantiation_is_not_recursive(
    monkeypatch: MonkeyPatch, hydra_restore_singletons: Any
) -> None:
    classname = "hydra._internal.core_plugins.test_plugin.PluginWithNestedTarget"
    module = types.ModuleType("hydra._internal.core_plugins.test_plugin")
    setattr(module, "PluginWithNestedTarget", PluginWithNestedTarget)
    monkeypatch.setitem(sys.modules, module.__name__, module)
    Plugins.instance().register(PluginWithNestedTarget)

    plugin = Plugins.instance()._instantiate(
        OmegaConf.create(
            {
                "_target_": classname,
                "nested": {
                    "_target_": "tests.instantiate.AClass",
                    "a": 1,
                    "b": 2,
                    "c": 3,
                },
            }
        )
    )

    assert isinstance(plugin, PluginWithNestedTarget)
    assert isinstance(plugin.nested, DictConfig)
    assert plugin.nested._target_ == "tests.instantiate.AClass"

# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved
import importlib
import sys
import types
import warnings
from typing import Any, List, Sequence, Type

from omegaconf import DictConfig, OmegaConf
from pytest import MonkeyPatch, mark, raises, warns

from hydra.core.config_search_path import ConfigSearchPath
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
search_path_plugins: List[str] = []


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
def test_discover(plugin_type: Type[Plugin], expected: List[str]) -> None:
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

        def load(self) -> Type[ExternalLauncher]:
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
    error_type: Type[Exception],
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

        def load(self) -> Type[ExternalLauncher]:
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

        def load(self) -> Type[ExternalLauncher]:
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


def test_plugin_instantiation_is_not_recursive(monkeypatch: MonkeyPatch) -> None:
    classname = "hydra._internal.core_plugins.test_plugin.PluginWithNestedTarget"
    module = types.ModuleType("hydra._internal.core_plugins.test_plugin")
    setattr(module, "PluginWithNestedTarget", PluginWithNestedTarget)
    monkeypatch.setitem(sys.modules, module.__name__, module)
    monkeypatch.setitem(
        Plugins.instance().class_name_to_class, classname, PluginWithNestedTarget
    )

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

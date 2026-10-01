# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved
import re
from typing import Any, Sequence
from unittest.mock import Mock

from omegaconf import DictConfig, OmegaConf
from pytest import mark, raises

from hydra import TaskFunction
from hydra._internal.callbacks import Callbacks
from hydra._internal.config_loader_impl import ConfigLoaderImpl
from hydra._internal.utils import create_config_search_path
from hydra.core.config_loader import ConfigLoader
from hydra.core.plugins import Plugins
from hydra.core.utils import JobReturn
from hydra.plugins.launcher import Launcher
from hydra.plugins.sweeper import Sweeper
from hydra.test_utils.test_utils import chdir_hydra_root
from hydra.types import HydraContext

chdir_hydra_root()


class IncompatibleSweeper(Sweeper):
    def __init__(self) -> None:
        pass

    def setup(  # type: ignore
        self,
        config: DictConfig,
        config_loader: ConfigLoader,
        task_function: TaskFunction,
    ) -> None:
        pass

    def sweep(self, arguments: list[str]) -> Any:
        pass


class IncompatibleLauncher(Launcher):
    def __init__(self) -> None:
        pass

    def setup(  # type: ignore
        self,
        config: DictConfig,
        config_loader: ConfigLoader,
        task_function: TaskFunction,
    ) -> None:
        pass

    def launch(  # type: ignore[empty-body]
        self, job_overrides: Sequence[Sequence[str]], initial_job_idx: int
    ) -> Sequence[JobReturn]:
        raise NotImplementedError


@mark.parametrize(
    "plugin, config",
    [
        (IncompatibleLauncher(), OmegaConf.create({"hydra": {"launcher": {}}})),
        (IncompatibleSweeper(), OmegaConf.create({"hydra": {"sweeper": {}}})),
    ],
)
def test_setup_plugins(
    monkeypatch: Any, plugin: Launcher | Sweeper, config: DictConfig
) -> None:
    task_function = Mock(spec=TaskFunction)
    config_loader = ConfigLoaderImpl(config_search_path=create_config_search_path(None))
    hydra_context = HydraContext(config_loader=config_loader, callbacks=Callbacks())
    plugin_instance = Plugins.instance()
    monkeypatch.setattr(Plugins, "check_usage", lambda _: None)
    monkeypatch.setattr(plugin_instance, "_instantiate", lambda _: plugin)

    msg = "setup() got an unexpected keyword argument 'hydra_context'"
    with raises(TypeError, match=re.escape(msg)):
        if isinstance(plugin, Launcher):
            Plugins.instance().instantiate_launcher(
                hydra_context=hydra_context,
                task_function=task_function,
                config=config,
            )
        else:
            Plugins.instance().instantiate_sweeper(
                hydra_context=hydra_context,
                task_function=task_function,
                config=config,
            )

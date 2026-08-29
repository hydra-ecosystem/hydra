# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved
import sys
from typing import Any, cast

from omegaconf import OmegaConf, open_dict

from hydra._internal.config_loader_impl import ConfigLoaderImpl
from hydra._internal.target_policy import _get_active_execution_whitelist
from hydra._internal.utils import create_config_search_path
from hydra.core import utils
from hydra.core.hydra_config import HydraConfig
from hydra.types import HydraContext, RunMode


def test_accessing_hydra_config(hydra_restore_singletons: Any) -> Any:
    utils.setup_globals()

    config_loader = ConfigLoaderImpl(
        config_search_path=create_config_search_path("pkg://hydra.test_utils.configs")
    )
    cfg = config_loader.load_configuration(
        config_name="accessing_hydra_config", run_mode=RunMode.RUN, overrides=[]
    )
    HydraConfig.instance().set_config(cfg)
    with open_dict(cfg):
        del cfg["hydra"]
    assert cfg.job_name == "UNKNOWN_NAME"
    assert cfg.config_name == "accessing_hydra_config"


def test_py_version_resolver(hydra_restore_singletons: Any, monkeypatch: Any) -> Any:
    monkeypatch.setattr(sys, "version_info", (3, 8, 2))
    utils.setup_globals()
    assert OmegaConf.create({"key": "${python_version:}"}).key == "3.8"
    assert OmegaConf.create({"key": "${python_version:major}"}).key == "3"
    assert OmegaConf.create({"key": "${python_version:minor}"}).key == "3.8"
    assert OmegaConf.create({"key": "${python_version:micro}"}).key == "3.8.2"


def test_run_job_reestablishes_execution_whitelist(monkeypatch: Any) -> None:
    expected = ("tests.test_core_utils.Allowed",)
    sentinel = object()

    def fake_run_job(**kwargs: Any) -> object:
        assert _get_active_execution_whitelist() == expected
        return sentinel

    monkeypatch.setattr(utils, "_run_job", fake_run_job)
    hydra_context = HydraContext(
        config_loader=cast(Any, object()),
        callbacks=cast(Any, object()),
        execution_whitelist=expected,
    )

    result = utils.run_job(
        task_function=cast(Any, object()),
        config=OmegaConf.create(),
        job_dir_key="unused",
        job_subdir_key=None,
        hydra_context=hydra_context,
    )

    assert result is sentinel
    assert _get_active_execution_whitelist() is None

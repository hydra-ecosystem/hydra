# SPDX-FileCopyrightText: Contributors to Hydra
# SPDX-License-Identifier: MIT
import json
import logging
from dataclasses import dataclass, is_dataclass
from pathlib import Path
from typing import Any

from omegaconf import MISSING, DictConfig, OmegaConf

import hydra
from hydra.core.config_store import ConfigStore
from hydra.core.hydra_config import HydraConfig
from hydra.core.utils import JobReturn
from hydra.experimental.callback import Callback

log = logging.getLogger(__name__)


@dataclass
class Config:
    foo: int = 10
    db: Any = MISSING


ConfigStore.instance().store(name="schema", node=Config)


class RecordingCallback(Callback):
    def on_run_start(self, config: DictConfig, **kwargs: Any) -> None:
        print("on_run_start")

    def on_job_start(self, config: DictConfig, **kwargs: Any) -> None:
        print("on_job_start")

    def on_job_end(
        self, config: DictConfig, job_return: JobReturn, **kwargs: Any
    ) -> None:
        print(f"on_job_end: {job_return.status.name}")

    def on_run_end(self, config: DictConfig, **kwargs: Any) -> None:
        print("on_run_end")


@hydra.main(config_path=".", config_name="config", execution_whitelist="my_app.*")
def my_app(cfg: DictConfig) -> None:
    assert is_dataclass(OmegaConf.to_object(cfg))
    output_dir = Path(HydraConfig.get().runtime.output_dir)
    result = {
        "config": OmegaConf.to_container(cfg, resolve=True),
        "cwd": str(Path.cwd()),
        "config_name": HydraConfig.get().job.config_name,
    }
    (output_dir / "result.json").write_text(json.dumps(result), encoding="utf-8")
    log.info("Running my_app")


if __name__ == "__main__":
    my_app()

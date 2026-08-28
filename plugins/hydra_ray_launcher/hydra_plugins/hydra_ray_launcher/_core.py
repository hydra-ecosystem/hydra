# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved
import logging
from pathlib import Path
from typing import Sequence, cast

import ray
from hydra.core.singleton import Singleton
from hydra.core.utils import JobReturn, configure_log, filter_overrides, setup_globals
from omegaconf import DictConfig, OmegaConf, open_dict

from ._launcher_util import launch_job_on_ray, start_ray
from .ray_launcher import RayLauncher

log = logging.getLogger(__name__)


def launch(
    launcher: RayLauncher,
    job_overrides: Sequence[Sequence[str]],
    initial_job_idx: int,
) -> Sequence[JobReturn]:
    setup_globals()
    assert launcher.config is not None
    assert launcher.hydra_context is not None
    assert launcher.task_function is not None

    configure_log(
        launcher.config.hydra.hydra_logging,
        launcher.config.hydra.verbose,
        target_whitelist=getattr(launcher.hydra_context, "target_whitelist", None),
    )
    sweep_dir = Path(str(launcher.config.hydra.sweep.dir))
    sweep_dir.mkdir(parents=True, exist_ok=True)
    log.info(
        f"Ray Launcher is launching {len(job_overrides)} jobs, "
        f"sweep output dir: {sweep_dir}"
    )

    ray_init = cast(
        DictConfig,
        OmegaConf.create(OmegaConf.to_container(launcher.ray_cfg.init, resolve=True)),
    )
    start_ray(ray_init)

    runs = []
    for idx, overrides in enumerate(job_overrides):
        idx = initial_job_idx + idx
        ostr = " ".join(filter_overrides(overrides))
        log.info(f"\t#{idx} : {ostr}")
        sweep_config = launcher.hydra_context.config_loader.load_sweep_config(
            launcher.config, list(overrides)
        )
        with open_dict(sweep_config):
            # This typically coming from the underlying scheduler (SLURM_JOB_ID for instance)
            # In that case, it will not be available here because we are still in the main process.
            # but instead should be populated remotely before calling the task_function.
            sweep_config.hydra.job.id = f"job_id_for_{idx}"
            sweep_config.hydra.job.num = idx
            ray_obj = launch_job_on_ray(
                launcher.hydra_context,
                launcher.ray_cfg.remote,
                sweep_config,
                launcher.task_function,
                Singleton.get_state(),
            )
            runs.append(ray_obj)

    return [ray.get(run) for run in runs]

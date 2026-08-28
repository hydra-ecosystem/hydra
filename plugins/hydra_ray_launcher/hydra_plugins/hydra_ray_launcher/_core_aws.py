# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved
import logging
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Sequence, Union, cast

import cloudpickle  # type: ignore
from hydra.core.singleton import Singleton
from hydra.core.utils import JobReturn, configure_log, filter_overrides, setup_globals
from omegaconf import DictConfig, OmegaConf, open_dict

from ._launcher_util import JOB_RETURN_PICKLE, JOB_SPEC_PICKLE, ray_tmp_dir, rsync
from .ray_aws_launcher import RayAWSLauncher

try:
    import pickle5 as pickle  # type: ignore
except ModuleNotFoundError:
    import pickle


# Static type checkers can complain about "unused type: ignore comment" on macos
# workaround adapted from: https://github.com/twisted/twisted/pull/1416
try:
    import importlib

    sdk: Any = importlib.import_module("ray.autoscaler.sdk")
except ModuleNotFoundError as e:
    raise ImportError(e)

log = logging.getLogger(__name__)


def _get_abs_code_dir(code_dir: Union[str, Path]) -> str:
    code_dir = str(code_dir)
    if code_dir:
        if os.path.isabs(code_dir):
            return code_dir
        else:
            return os.path.join(os.getcwd(), code_dir)
    else:
        return ""


def _pickle_jobs(tmp_dir: str, **jobspec: Any) -> None:
    path = os.path.join(tmp_dir, JOB_SPEC_PICKLE)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        cloudpickle.dump(jobspec, f)
    log.info(f"Pickle for jobs: {f.name}")


def launch(
    launcher: RayAWSLauncher,
    job_overrides: Sequence[Sequence[str]],
    initial_job_idx: int,
) -> Sequence[JobReturn]:
    setup_globals()
    assert launcher.config is not None
    assert launcher.hydra_context is not None
    assert launcher.task_function is not None

    setup_commands = list(launcher.env_setup.commands)
    packages = filter(
        lambda x: x[1] is not None, launcher.env_setup.pip_packages.items()
    )
    setup_commands.extend(
        [f"pip install {package}=={version}" for package, version in packages]
    )
    setup_commands.extend(launcher.ray_cfg.cluster.setup_commands)
    ray_cluster = cast(
        DictConfig,
        OmegaConf.create(
            OmegaConf.to_container(launcher.ray_cfg.cluster, resolve=True)
        ),
    )
    ray_cluster["setup_commands"] = setup_commands

    configure_log(
        launcher.config.hydra.hydra_logging,
        launcher.config.hydra.verbose,
        target_whitelist=getattr(launcher.hydra_context, "target_whitelist", None),
    )
    logging_config = cast(
        Dict[str, Any],
        OmegaConf.to_container(launcher.logging, resolve=True, enum_to_str=True),
    )
    sdk.configure_logging(**logging_config)

    log.info(f"Ray Launcher is launching {len(job_overrides)} jobs, ")

    with tempfile.TemporaryDirectory() as local_tmp_dir:
        sweep_configs = []
        for idx, overrides in enumerate(job_overrides):
            idx = initial_job_idx + idx
            ostr = " ".join(filter_overrides(overrides))
            log.info(f"\t#{idx} : {ostr}")
            sweep_config = launcher.hydra_context.config_loader.load_sweep_config(
                launcher.config, list(overrides)
            )
            with open_dict(sweep_config):
                # job.id will be set on the EC2 instance before running the job.
                sweep_config.hydra.job.num = idx

            sweep_configs.append(sweep_config)

        _pickle_jobs(
            tmp_dir=local_tmp_dir,
            hydra_context=launcher.hydra_context,
            sweep_configs=sweep_configs,
            task_function=launcher.task_function,
            singleton_state=Singleton.get_state(),
        )
        return launch_jobs(
            launcher,
            local_tmp_dir,
            Path(launcher.config.hydra.sweep.dir),
            ray_cluster,
        )


def launch_jobs(
    launcher: RayAWSLauncher,
    local_tmp_dir: str,
    sweep_dir: Path,
    ray_cluster: DictConfig,
) -> Sequence[JobReturn]:
    config = OmegaConf.to_container(ray_cluster, resolve=True, enum_to_str=True)
    sdk.create_or_update_cluster(
        config,
        **cast(Dict[str, Any], launcher.create_update_cluster),
    )
    with tempfile.TemporaryDirectory() as local_tmp_download_dir:
        assert isinstance(config, dict)
        with ray_tmp_dir(config, launcher.ray_cfg.run_env.name) as remote_tmp_dir:
            sdk.rsync(
                config,
                source=os.path.join(local_tmp_dir, ""),
                target=remote_tmp_dir,
                down=False,
            )

            script_path = os.path.join(os.path.dirname(__file__), "_remote_invoke.py")
            remote_script_path = os.path.join(remote_tmp_dir, "_remote_invoke.py")
            sdk.rsync(
                config,
                source=script_path,
                target=remote_script_path,
                down=False,
            )

            if launcher.sync_up.source_dir:
                sync_up_source_dir = _get_abs_code_dir(launcher.sync_up.source_dir)
                target_dir = (
                    launcher.sync_up.target_dir
                    if launcher.sync_up.target_dir
                    else remote_tmp_dir
                )
                rsync(
                    config,
                    launcher.sync_up.include,
                    launcher.sync_up.exclude,
                    os.path.join(sync_up_source_dir, ""),
                    target_dir,
                )
            sdk.run_on_cluster(
                config,
                run_env=launcher.ray_cfg.run_env.name,
                cmd=f"python {remote_script_path} {remote_tmp_dir}",
            )

            sdk.rsync(
                config,
                source=os.path.join(remote_tmp_dir, JOB_RETURN_PICKLE),
                target=local_tmp_download_dir,
                down=True,
            )

            sync_down_cfg = launcher.sync_down

            if (
                sync_down_cfg.target_dir
                or sync_down_cfg.source_dir
                or sync_down_cfg.include
                or sync_down_cfg.exclude
            ):
                sync_down_source_dir: Union[str, Path] = (
                    sync_down_cfg.source_dir if sync_down_cfg.source_dir else sweep_dir
                )
                target_dir = (
                    sync_down_cfg.target_dir if sync_down_cfg.target_dir else sweep_dir
                )
                target_dir = Path(_get_abs_code_dir(target_dir))
                target_dir.mkdir(parents=True, exist_ok=True)

                rsync(
                    config,
                    launcher.sync_down.include,
                    launcher.sync_down.exclude,
                    os.path.join(sync_down_source_dir),
                    str(target_dir),
                    up=False,
                )
                log.info(
                    f"Syncing outputs from remote dir: {sync_down_source_dir} to local dir: {target_dir.absolute()} "
                )

        if launcher.stop_cluster:
            log.info("Stopping cluster now. (stop_cluster=true)")
            if launcher.ray_cfg.cluster.provider.cache_stopped_nodes:
                log.info("NOT deleting the cluster (provider.cache_stopped_nodes=true)")
            else:
                log.info("Deleted the cluster (provider.cache_stopped_nodes=false)")
            sdk.teardown_cluster(
                config,
                **cast(Dict[str, Any], launcher.teardown_cluster),
            )
        else:
            log.warning(
                "NOT stopping cluster, this may incur extra cost for you. (stop_cluster=false)"
            )

        with open(os.path.join(local_tmp_download_dir, JOB_RETURN_PICKLE), "rb") as f:
            job_returns = pickle.load(f)  # nosec
            assert isinstance(job_returns, List)
            for run in job_returns:
                assert isinstance(run, JobReturn)
            return job_returns

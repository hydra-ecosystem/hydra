# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved
import logging
import os
from contextlib import contextmanager
from subprocess import PIPE, Popen
from typing import Any, Generator, cast

import ray
from hydra.core.hydra_config import HydraConfig
from hydra.core.singleton import Singleton
from hydra.core.utils import JobReturn, run_job, setup_globals
from hydra.types import HydraContext, TaskFunction
from omegaconf import DictConfig, OmegaConf

# Static type checkers can complain about "unused type: ignore comment" on macos
# workaround adapted from: https://github.com/twisted/twisted/pull/1416
try:
    import importlib

    sdk: Any = importlib.import_module("ray.autoscaler.sdk")
except ModuleNotFoundError as e:
    raise ImportError(e)

log = logging.getLogger(__name__)

JOB_SPEC_PICKLE = "job_spec.pkl"
JOB_RETURN_PICKLE = "returns.pkl"


def start_ray(init_cfg: DictConfig) -> None:
    if not ray.is_initialized():
        log.info(f"Initializing ray with config: {init_cfg}")
        if init_cfg:
            ray.init(
                **cast(dict[str, Any], OmegaConf.to_container(init_cfg, resolve=True))
            )
        else:
            ray.init()
    else:
        log.info("Ray is already running.")


def _run_job(
    hydra_context: HydraContext,
    sweep_config: DictConfig,
    task_function: TaskFunction,
    singleton_state: dict[Any, Any],
) -> JobReturn:
    setup_globals()
    Singleton.set_state(singleton_state)
    HydraConfig.instance().set_config(sweep_config)
    return run_job(
        hydra_context=hydra_context,
        task_function=task_function,
        config=sweep_config,
        job_dir_key="hydra.sweep.dir",
        job_subdir_key="hydra.sweep.subdir",
    )


def launch_job_on_ray(
    hydra_context: HydraContext,
    ray_remote: DictConfig,
    sweep_config: DictConfig,
    task_function: TaskFunction,
    singleton_state: Any,
) -> Any:
    if ray_remote:
        run_job_ray = ray.remote(
            **cast(dict[str, Any], OmegaConf.to_container(ray_remote, resolve=True))
        )(_run_job)
    else:
        run_job_ray = ray.remote(_run_job)

    ret = run_job_ray.remote(
        hydra_context=hydra_context,
        sweep_config=sweep_config,
        task_function=task_function,
        singleton_state=singleton_state,
    )
    return ret


def _run_command(args: Any) -> tuple[str, str]:
    with Popen(args=args, stdout=PIPE, stderr=PIPE) as proc:
        log.info(f"Running command: {' '.join(args)}")
        out, err = proc.communicate()
        out_str = out.decode().strip() if out is not None else ""
        err_str = err.decode().strip() if err is not None else ""
        log.info(f"Output: {out_str} \n Error: {err_str}")
        return out_str, err_str


@contextmanager
def ray_tmp_dir(config: dict[Any, Any], run_env: str) -> Generator[Any, None, None]:
    out = sdk.run_on_cluster(
        config, run_env=run_env, cmd="echo $(mktemp -d)", with_output=True
    ).decode()

    tmppath = [
        x
        for x in out.strip().split()
        if x.startswith("/tmp/") and "ray-config" not in x  # nosec
    ]
    assert len(tmppath) == 1, f"tmppath is : {tmppath}"
    tmp_path = tmppath[0]
    log.info(f"Created temp path on remote server {tmp_path}")
    yield tmp_path
    sdk.run_on_cluster(config, run_env=run_env, cmd=f"rm -rf {tmp_path}")


def _get_pem(config: Any) -> Any:
    key_name = config["auth"].get("ssh_private_key")
    if key_name is not None:
        return key_name
    key_name = config["provider"].get("key_pair", {}).get("key_name")
    if key_name:
        return os.path.expanduser(os.path.expanduser(f"~/.ssh/{key_name}.pem"))
    region = config["provider"]["region"]
    key_pair_name = f"ray-autoscaler_{region}"
    return os.path.expanduser(f"~/.ssh/{key_pair_name}.pem")


def rsync(
    config: dict[Any, Any],
    include: list[str],
    exclude: list[str],
    source: str,
    target: str,
    up: bool = True,
) -> None:
    keypair = _get_pem(config)
    remote_ip = sdk.get_head_node_ip(config)
    user = config["auth"]["ssh_user"]
    args = ["rsync", "--rsh", f"ssh -i {keypair}  -o StrictHostKeyChecking=no", "-avz"]

    for i in include:
        args += [f"--include={i}"]
    for e in exclude:
        args += [f"--exclude={e}"]

    args += ["--prune-empty-dirs"]

    if up:
        target = f"{user}@{remote_ip}:{target}"
    else:
        source = f"{user}@{remote_ip}:{source}"
    args += [source, target]
    _run_command(args)

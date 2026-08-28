# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple, cast

from hydra.core.hydra_config import HydraConfig
from hydra.core.singleton import Singleton
from hydra.core.utils import (
    JobReturn,
    configure_log,
    filter_overrides,
    run_job,
    setup_globals,
)
from hydra.types import HydraContext, TaskFunction
from joblib import (  # type: ignore
    Parallel,
    delayed,
    effective_n_jobs,
    parallel_backend,
    wrap_non_picklable_objects,
)
from omegaconf import DictConfig, open_dict

from .joblib_launcher import JoblibLauncher

log = logging.getLogger(__name__)

SUPPORTED_BACKENDS = {"loky", "multiprocessing"}


def execute_job(
    idx: int,
    overrides: Sequence[str],
    hydra_context: HydraContext,
    config: DictConfig,
    task_function: TaskFunction,
    task_function_unwrap_depth: int,
    singleton_state: Any,
    wrap_result: bool,
) -> Any:
    """Calls `run_job` in parallel"""
    for _ in range(task_function_unwrap_depth):
        task_function = cast(TaskFunction, getattr(task_function, "__wrapped__"))
    setup_globals()
    Singleton.set_state(singleton_state)

    sweep_config = hydra_context.config_loader.load_sweep_config(
        config, list(overrides)
    )
    with open_dict(sweep_config):
        sweep_config.hydra.job.id = f"{sweep_config.hydra.job.name}_{idx}"
        sweep_config.hydra.job.num = idx
    HydraConfig.instance().set_config(sweep_config)

    ret = run_job(
        hydra_context=hydra_context,
        config=sweep_config,
        task_function=task_function,
        job_dir_key="hydra.sweep.dir",
        job_subdir_key="hydra.sweep.subdir",
    )

    if wrap_result:
        ret = wrap_non_picklable_objects(ret, keep_wrapper=False)
    return ret


def _get_multiprocessing_task_function(
    task_function: TaskFunction,
) -> Tuple[TaskFunction, int]:
    module_name = getattr(task_function, "__module__", None)
    task_name = getattr(task_function, "__name__", None)
    if module_name is None or task_name is None:
        return task_function, 0

    module = sys.modules.get(module_name)
    module_task_function = (
        getattr(module, task_name, None) if module is not None else None
    )

    unwrap_depth = 0
    candidate = module_task_function
    while candidate is not task_function:
        candidate = getattr(candidate, "__wrapped__", None)
        if candidate is None:
            raise TypeError(
                "The Joblib multiprocessing backend requires function tasks to be "
                "defined at module scope and decorators around @hydra.main to use "
                "functools.wraps"
            )
        unwrap_depth += 1

    return cast(TaskFunction, module_task_function), unwrap_depth


def process_joblib_cfg(joblib_cfg: Dict[str, Any]) -> None:
    backend = joblib_cfg.get("backend") or "loky"
    if backend not in SUPPORTED_BACKENDS:
        raise ValueError(
            f"Unsupported Joblib backend '{backend}'. "
            f"Supported backends: {sorted(SUPPORTED_BACKENDS)}"
        )
    joblib_cfg["backend"] = backend

    inner_max_num_threads = joblib_cfg.get("inner_max_num_threads")
    if inner_max_num_threads is not None and backend != "loky":
        raise ValueError("inner_max_num_threads is supported only by the loky backend")

    maxtasksperchild = joblib_cfg.pop("maxtasksperchild", None)
    if backend == "multiprocessing":
        if maxtasksperchild not in (None, 1):
            raise ValueError(
                "The multiprocessing backend fixes maxtasksperchild at 1 "
                "to preserve per-job process isolation"
            )
        batch_size = joblib_cfg.get("batch_size", "auto")
        if batch_size not in ("auto", "1", 1):
            raise ValueError(
                "The multiprocessing backend requires batch_size=1 "
                "to preserve per-job process isolation"
            )
        joblib_cfg["batch_size"] = 1
        joblib_cfg["maxtasksperchild"] = 1
    elif maxtasksperchild is not None:
        raise ValueError(
            "maxtasksperchild is supported only by the multiprocessing backend"
        )

    for k in ["pre_dispatch", "batch_size", "max_nbytes"]:
        if k in joblib_cfg.keys():
            try:
                val = joblib_cfg.get(k)
                if val:
                    joblib_cfg[k] = int(val)
            except ValueError:
                pass


def launch(
    launcher: JoblibLauncher,
    job_overrides: Sequence[Sequence[str]],
    initial_job_idx: int,
) -> Sequence[JobReturn]:
    """
    :param job_overrides: a List of List<String>, where each inner list is the arguments for one job run.
    :param initial_job_idx: Initial job idx in batch.
    :return: an array of return values from run_job with indexes corresponding to the input list indexes.
    """
    setup_globals()
    assert launcher.config is not None
    assert launcher.task_function is not None
    assert launcher.hydra_context is not None

    configure_log(
        launcher.config.hydra.hydra_logging,
        launcher.config.hydra.verbose,
        target_whitelist=getattr(launcher.hydra_context, "target_whitelist", None),
    )
    sweep_dir = Path(str(launcher.config.hydra.sweep.dir))
    sweep_dir.mkdir(parents=True, exist_ok=True)

    joblib_cfg = dict(launcher.joblib)
    process_joblib_cfg(joblib_cfg)
    selected_backend = joblib_cfg["backend"]
    inner_max_num_threads = joblib_cfg.pop("inner_max_num_threads", None)

    backend = None
    backend_cfg = None
    parallel_cfg = dict(joblib_cfg)
    # Joblib runs n_jobs=1 in the caller, so keep one task in flight in a worker pool.
    if (
        selected_backend == "multiprocessing"
        and effective_n_jobs(parallel_cfg.get("n_jobs")) == 1
    ):
        parallel_cfg["n_jobs"] = 2
        parallel_cfg["pre_dispatch"] = 1
    if inner_max_num_threads is not None:
        backend = parallel_cfg.pop("backend")
        parallel_cfg.pop("prefer", None)
        parallel_cfg.pop("require", None)
        backend_cfg = {"inner_max_num_threads": inner_max_num_threads}
        if "n_jobs" in parallel_cfg:
            backend_cfg["n_jobs"] = parallel_cfg.pop("n_jobs")

    parallel_args = ",".join(f"{k}={v}" for k, v in parallel_cfg.items())
    if backend_cfg is None:
        launch_msg = f"Joblib.Parallel({parallel_args})"
    else:
        backend_args = ",".join(f"{k}={v}" for k, v in backend_cfg.items())
        launch_msg = (
            f"joblib.parallel_backend({backend},{backend_args}) "
            f"with Joblib.Parallel({parallel_args})"
        )

    log.info(
        "{} is launching {} jobs".format(
            launch_msg,
            len(job_overrides),
        ),
    )
    log.info(f"Launching jobs, sweep output dir : {sweep_dir}")
    for idx, overrides in enumerate(job_overrides):
        log.info("\t#{} : {}".format(idx, " ".join(filter_overrides(overrides))))

    singleton_state = Singleton.get_state()
    task_function = launcher.task_function
    task_function_unwrap_depth = 0
    wrap_for_multiprocessing = selected_backend == "multiprocessing"
    if wrap_for_multiprocessing:
        singleton_state = wrap_non_picklable_objects(
            singleton_state, keep_wrapper=False
        )
        task_function, task_function_unwrap_depth = _get_multiprocessing_task_function(
            task_function
        )

    calls = (
        delayed(execute_job)(
            initial_job_idx + idx,
            overrides,
            launcher.hydra_context,
            launcher.config,
            task_function,
            task_function_unwrap_depth,
            singleton_state,
            wrap_for_multiprocessing,
        )
        for idx, overrides in enumerate(job_overrides)
    )
    if backend_cfg is None:
        runs = Parallel(**parallel_cfg)(calls)
    else:
        assert backend is not None
        with parallel_backend(backend, **backend_cfg):
            runs = Parallel(**parallel_cfg)(calls)

    assert isinstance(runs, List)
    for run in runs:
        assert isinstance(run, JobReturn)
    return runs

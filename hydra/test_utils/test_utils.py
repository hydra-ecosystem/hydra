# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved
"""
Utilities used by tests
"""

import copy
import logging
import os
import re
import shutil
import string
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from difflib import unified_diff
from pathlib import Path
from subprocess import PIPE, Popen
from typing import Any, Callable, Dict, Iterator, List, Optional, Protocol, Tuple, Union

from omegaconf import Container, DictConfig, OmegaConf

from hydra._internal.hydra import Hydra
from hydra._internal.utils import detect_task_name
from hydra.core.global_hydra import GlobalHydra
from hydra.core.utils import JobReturn, validate_config_path
from hydra.types import TaskFunction


@contextmanager
def does_not_raise(enter_result: Any = None) -> Iterator[Any]:
    yield enter_result


class TaskTestFunction:
    """
    Context function
    """

    def __init__(self) -> None:
        self.temp_dir: Optional[str] = None
        self.overrides: Optional[List[str]] = None
        self.calling_file: Optional[str] = None
        self.calling_module: Optional[str] = None
        self.config_path: Optional[str] = None
        self.config_name: Optional[str] = None
        self.hydra: Optional[Hydra] = None
        self.job_ret: Optional[JobReturn] = None
        self.configure_logging: bool = False

    def __call__(self, cfg: DictConfig) -> Any:
        """
        Actual function being executed by Hydra
        """

        return 100

    def __enter__(self) -> "TaskTestFunction":
        try:
            validate_config_path(self.config_path)

            job_name = detect_task_name(self.calling_file, self.calling_module)

            self.hydra = Hydra.create_main_hydra_file_or_module(
                calling_file=self.calling_file,
                calling_module=self.calling_module,
                config_path=self.config_path,
                job_name=job_name,
            )
            self.temp_dir = tempfile.mkdtemp()
            overrides = copy.deepcopy(self.overrides)
            assert overrides is not None
            overrides.append(f'hydra.run.dir="{self.temp_dir}"')
            self.job_ret = self.hydra.run(
                config_name=self.config_name,
                task_function=self,
                overrides=overrides,
                with_log_configuration=self.configure_logging,
            )
            return self
        finally:
            GlobalHydra().clear()

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        # release log file handles.
        if self.configure_logging:
            logging.shutdown()
        assert self.temp_dir is not None
        shutil.rmtree(self.temp_dir, ignore_errors=True)


class TTaskRunner(Protocol):
    def __call__(
        self,
        calling_file: Optional[str],
        calling_module: Optional[str],
        config_path: Optional[str],
        config_name: Optional[str],
        overrides: Optional[List[str]] = None,
        configure_logging: bool = False,
    ) -> TaskTestFunction: ...


class SweepTaskFunction:
    """
    Context function
    """

    def __init__(self) -> None:
        """
        if sweep_dir is None,  we use a temp dir, else we will create dir with the path from sweep_dir.
        """
        self.temp_dir: Optional[str] = None
        self.overrides: Optional[List[str]] = None
        self.calling_file: Optional[str] = None
        self.calling_module: Optional[str] = None
        self.task_function: Optional[TaskFunction] = None
        self.config_path: Optional[str] = None
        self.config_name: Optional[str] = None
        self.sweeps = None
        self.returns = None
        self.configure_logging: bool = False

    def __call__(self, cfg: DictConfig) -> Any:
        """
        Actual function being executed by Hydra
        """
        if self.task_function is not None:
            return self.task_function(cfg)
        return 100

    def __enter__(self) -> "SweepTaskFunction":
        overrides = copy.deepcopy(self.overrides)
        assert overrides is not None
        if self.temp_dir:
            Path(self.temp_dir).mkdir(parents=True, exist_ok=True)
        else:
            self.temp_dir = tempfile.mkdtemp()
        overrides.append(f"hydra.sweep.dir={self.temp_dir}")

        try:
            validate_config_path(self.config_path)
            job_name = detect_task_name(self.calling_file, self.calling_module)

            hydra_ = Hydra.create_main_hydra_file_or_module(
                calling_file=self.calling_file,
                calling_module=self.calling_module,
                config_path=self.config_path,
                job_name=job_name,
            )

            self.returns = hydra_.multirun(
                config_name=self.config_name,
                task_function=self,
                overrides=overrides,
                with_log_configuration=self.configure_logging,
            )
        finally:
            GlobalHydra().clear()

        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if self.configure_logging:
            logging.shutdown()
        assert self.temp_dir is not None
        shutil.rmtree(self.temp_dir, ignore_errors=True)


class TSweepRunner(Protocol):
    returns: List[List[JobReturn]]

    def __call__(
        self,
        calling_file: Optional[str],
        calling_module: Optional[str],
        task_function: Optional[TaskFunction],
        config_path: Optional[str],
        config_name: Optional[str],
        overrides: Optional[List[str]],
        temp_dir: Optional[Path] = None,
    ) -> SweepTaskFunction: ...


def chdir_hydra_root(subdir: Optional[str] = None) -> None:
    """
    Change the cwd to the root of the hydra project.
    used from unit tests to make them runnable from anywhere in the tree.
    """
    _chdir_to_dir_containing(target="ATTRIBUTION")

    if subdir is not None:
        os.chdir(subdir)


def chdir_plugin_root() -> None:
    """
    Change the cwd to the root of the plugin (location of setup.py)
    """
    _chdir_to_dir_containing(target="setup.py")


def _chdir_to_dir_containing(
    target: str, max_up: int = 6, initial_dir: str = os.getcwd()
) -> None:
    cur = find_parent_dir_containing(target, max_up, initial_dir)
    os.chdir(cur)


def find_parent_dir_containing(
    target: str, max_up: int = 6, initial_dir: str = os.getcwd()
) -> str:
    cur = initial_dir
    while not os.path.exists(os.path.join(cur, target)) and max_up > 0:
        cur = os.path.relpath(os.path.join(cur, ".."))
        max_up = max_up - 1
    if max_up == 0:
        raise OSError(f"Could not find {target} in parents of {os.getcwd()}")
    return cur


def verify_dir_outputs(
    job_return: JobReturn, overrides: Optional[List[str]] = None
) -> None:
    """
    Verify that directory output makes sense
    """
    assert isinstance(job_return, JobReturn)
    assert job_return.working_dir is not None
    assert job_return.task_name is not None
    assert job_return.hydra_cfg is not None

    output_dir = job_return.hydra_cfg.hydra.runtime.output_dir
    assert os.path.exists(os.path.join(output_dir, job_return.task_name + ".log"))
    hydra_dir = os.path.join(output_dir, job_return.hydra_cfg.hydra.output_subdir)
    assert os.path.exists(os.path.join(hydra_dir, "config.yaml"))
    assert os.path.exists(os.path.join(hydra_dir, "overrides.yaml"))
    assert OmegaConf.load(
        os.path.join(hydra_dir, "overrides.yaml")
    ) == OmegaConf.create(overrides or [])


def _get_statements(indent: str, statements: Union[None, str, List[str]]) -> str:
    if isinstance(statements, str):
        statements = [statements]

    code = ""
    if statements is None or len(statements) == 0:
        code = "pass"
    else:
        for p in statements:
            code += f"{indent}{p}\n"
    return code


def integration_test(
    tmpdir: Path,
    task_config: Any,
    overrides: List[str],
    prints: Union[str, List[str]],
    expected_outputs: Union[str, List[str]],
    prolog: Union[None, str, List[str]] = None,
    filename: str = "task.py",
    env_override: Optional[Dict[str, str]] = None,
    clean_environment: bool = False,
    generate_custom_cmd: Callable[..., List[str]] = lambda cmd, *args, **kwargs: cmd,
) -> str:
    Path(tmpdir).mkdir(parents=True, exist_ok=True)
    if isinstance(expected_outputs, str):
        expected_outputs = [expected_outputs]
    if not isinstance(task_config, Container):
        task_config = OmegaConf.create(task_config)
    if isinstance(prints, str):
        prints = [prints]
    prints = [f'f.write({p} + "\\n")' for p in prints]

    s = string.Template("""import hydra
import os
from hydra.core.hydra_config import HydraConfig

$PROLOG

@hydra.main(config_path='.', config_name='config')
def experiment(cfg):
    with open("$OUTPUT_FILE", "w") as f:
$PRINTS

if __name__ == "__main__":
    experiment()
""")

    print_code = _get_statements(indent="        ", statements=prints)
    prolog_code = _get_statements(indent="", statements=prolog)

    if task_config is not None:
        cfg_file = tmpdir / "config.yaml"
        with open(str(cfg_file), "w") as f:
            f.write("# @package _global_\n")
            OmegaConf.save(task_config, f)
    output_file = str(tmpdir / "output.txt")
    # replace Windows path separator \ with an escaped version \\
    output_file = output_file.replace("\\", "\\\\")
    code = s.substitute(
        PRINTS=print_code,
        OUTPUT_FILE=output_file,
        PROLOG=prolog_code,
    )
    task_file = tmpdir / filename
    task_file.write_text(str(code), encoding="utf-8")

    cmd = [sys.executable, str(task_file)]
    orig_dir = os.getcwd()
    try:
        os.chdir(str(tmpdir))
        cmd = generate_custom_cmd(cmd, filename)
        cmd.extend(overrides)
        if clean_environment:
            modified_env = {}
        else:
            modified_env = os.environ.copy()
            if env_override is not None:
                modified_env.update(env_override)
        subprocess.check_call(cmd, env=modified_env)

        with open(output_file) as f:
            file_str = f.read()
            output = str.splitlines(file_str)

        if expected_outputs is not None:
            assert len(output) == len(expected_outputs), (
                f"Unexpected number of output lines from {task_file}, output lines:\n\n{file_str}"
            )
            for idx in range(len(output)):
                assert_multiline_regex_search(expected_outputs[idx], output[idx])
        # some tests are parsing the file output for more specialized testing.
        return file_str
    finally:
        os.chdir(orig_dir)


def run_with_error(cmd: Any, env: Any = None) -> str:
    cmd = [sys.executable, "-Werror"] + cmd
    with Popen(cmd, stdout=PIPE, stderr=PIPE, env=env) as p:
        _stdout, stderr = p.communicate()
        err = stderr.decode("utf-8").rstrip().replace("\r\n", "\n")
        assert p.returncode != 0
    return err


def run_python_script(
    cmd: Any,
    env: Any = None,
    allow_warnings: bool = False,
    print_error: bool = True,
    raise_exception: bool = True,
) -> Tuple[str, str]:
    if allow_warnings:
        cmd = [sys.executable] + cmd
    else:
        cmd = [sys.executable, "-Werror"] + cmd
    return run_process(cmd, env, print_error, raise_exception)


def run_process(
    cmd: Any,
    env: Any = None,
    print_error: bool = True,
    raise_exception: bool = True,
    timeout: Optional[float] = None,
) -> Tuple[str, str]:
    try:
        process = subprocess.Popen(
            args=cmd,
            shell=False,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        bstdout, bstderr = process.communicate(timeout=timeout)
        stdout = normalize_newlines(bstdout.decode().rstrip())
        stderr = normalize_newlines(bstderr.decode().rstrip())
        if process.returncode != 0:
            if print_error:
                sys.stderr.write(f"Subprocess error:\n{stderr}\n")
            if raise_exception:
                raise subprocess.CalledProcessError(
                    returncode=process.returncode, cmd=cmd
                )
        return stdout, stderr
    except Exception as e:
        if print_error:
            cmd = " ".join(cmd)
            sys.stderr.write(f"=== Error executing:\n{cmd}\n===================")
        raise e


def normalize_newlines(s: str) -> str:
    """
    Normalizes new lines such they are comparable across different operating systems
    :param s:
    :return:
    """
    return s.replace("\r\n", "\n").replace("\r", "\n")


def assert_text_same(
    from_line: str, to_line: str, from_name: str = "Expected", to_name: str = "Actual"
) -> None:
    from_line = normalize_newlines(from_line)
    to_line = normalize_newlines(to_line)
    lines = [
        line
        for line in unified_diff(
            a=from_line.splitlines(),
            b=to_line.splitlines(),
            fromfile=from_name,
            tofile=to_name,
        )
    ]

    diff = "\n".join(lines)
    if len(diff) > 0:
        print("\n------------ DIFF -------------")
        print(diff)
        print("-------------------------------")
        assert False, "Mismatch between expected and actual text"


def assert_multiline_regex_search(
    pattern: str, string: str, from_name: str = "Expected", to_name: str = "Actual"
) -> None:
    """Search with a multiline regex after normalizing newlines.

    Use anchors to require a full-string match. On failure, print the pattern
    and the actual string.
    """
    pattern = normalize_newlines(pattern)
    string = normalize_newlines(string)
    if re.search(pattern, string, flags=re.MULTILINE) is None:
        print("\n-------- PATTERN: -----------")
        print(pattern)
        print("---------- STRING: ------------")
        print(string)
        print("-------------------------------")
        assert False, "Regex pattern did not match"

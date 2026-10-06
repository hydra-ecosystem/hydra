# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved
import re
import subprocess
import sys
import warnings
from pathlib import Path
from textwrap import dedent
from typing import Any

from omegaconf import OmegaConf
from pytest import mark, param, raises, warns

from hydra._internal.callbacks import Callbacks
from hydra.core.utils import JobReturn, JobStatus
from hydra.errors import Hydra15MigrationWarning
from hydra.experimental.callback import Callback
from hydra.experimental.callbacks import LogJobReturnCallback
from hydra.test_utils.test_utils import (
    assert_multiline_regex_search,
    chdir_hydra_root,
    run_python_script,
)

chdir_hydra_root()


def test_callback_exception_warns_and_dispatch_continues() -> None:
    events = []

    class RecordingCallback(Callback):
        def on_job_end(self, config: Any, job_return: JobReturn, **kwargs: Any) -> None:
            events.append("recording")

    class FailingCallback(Callback):
        def on_job_end(self, config: Any, job_return: JobReturn, **kwargs: Any) -> None:
            events.append("failing")
            raise RuntimeError("callback failed")

    callbacks = Callbacks()
    # End hooks run in reverse order, so the failing callback runs first.
    callbacks.callbacks = [RecordingCallback(), FailingCallback()]
    task_error = ValueError("task failed")
    job_return = JobReturn(status=JobStatus.FAILED, _return_value=task_error)

    with warns(UserWarning, match="FailingCallback.on_job_end raised RuntimeError"):
        callbacks.on_job_end(config=OmegaConf.create({}), job_return=job_return)

    assert events == ["failing", "recording"]
    assert job_return.status is JobStatus.FAILED
    with raises(ValueError, match="task failed") as exc_info:
        _ = job_return.return_value
    assert exc_info.value is task_error


def test_callback_exception_is_nonfatal_with_warnings_as_errors() -> None:
    events = []

    class RecordingCallback(Callback):
        def on_run_start(self, config: Any, **kwargs: Any) -> None:
            events.append("recording")

    class FailingCallback(Callback):
        def on_run_start(self, config: Any, **kwargs: Any) -> None:
            events.append("failing")
            raise RuntimeError("callback failed")

    callbacks = Callbacks()
    callbacks.callbacks = [FailingCallback(), RecordingCallback()]

    with warnings.catch_warnings():
        warnings.simplefilter("error", UserWarning)
        callbacks.on_run_start(config=OmegaConf.create({}))

    assert events == ["failing", "recording"]


def test_callback_exception_is_nonfatal_when_warning_formatting_fails() -> None:
    events = []

    class UnprintableError(RuntimeError):
        def __str__(self) -> str:
            raise ValueError("could not format callback error")

    class RecordingCallback(Callback):
        def on_run_start(self, config: Any, **kwargs: Any) -> None:
            events.append("recording")

    class FailingCallback(Callback):
        def on_run_start(self, config: Any, **kwargs: Any) -> None:
            events.append("failing")
            raise UnprintableError()

    callbacks = Callbacks()
    callbacks.callbacks = [FailingCallback(), RecordingCallback()]

    callbacks.on_run_start(config=OmegaConf.create({}))

    assert events == ["failing", "recording"]


def test_callback_exception_is_nonfatal_when_warning_formatting_raises_system_exit() -> (
    None
):
    events = []

    class UnprintableError(RuntimeError):
        def __str__(self) -> str:
            raise SystemExit(2)

    class RecordingCallback(Callback):
        def on_run_start(self, config: Any, **kwargs: Any) -> None:
            events.append("recording")

    class FailingCallback(Callback):
        def on_run_start(self, config: Any, **kwargs: Any) -> None:
            events.append("failing")
            raise UnprintableError()

    callbacks = Callbacks()
    callbacks.callbacks = [FailingCallback(), RecordingCallback()]

    callbacks.on_run_start(config=OmegaConf.create({}))

    assert events == ["failing", "recording"]


def test_callback_control_flow_exception_propagates() -> None:
    class ExitingCallback(Callback):
        def on_run_start(self, config: Any, **kwargs: Any) -> None:
            raise SystemExit(3)

    callbacks = Callbacks()
    callbacks.callbacks = [ExitingCallback()]

    with raises(SystemExit) as exc_info:
        callbacks.on_run_start(config=OmegaConf.create({}))

    assert exc_info.value.code == 3


@mark.parametrize(
    "app_path,args,expected",
    [
        param(
            "tests/test_apps/app_with_callbacks/custom_callback/my_app.py",
            [],
            re.escape(
                dedent("""\
                [HYDRA] Init custom_callback
                [HYDRA] custom_callback on_run_start
                [JOB] custom_callback on_job_start
                [JOB] foo: bar

                [JOB] custom_callback on_job_end
                [JOB] custom_callback on_run_end""")
            ),
            id="custom_callback",
        ),
        param(
            "tests/test_apps/app_with_callbacks/custom_callback/my_app.py",
            [
                "foo=bar",
                "-m",
            ],
            re.escape(
                dedent("""\
                [HYDRA] Init custom_callback
                [HYDRA] custom_callback on_multirun_start
                [HYDRA] Launching 1 jobs locally
                [HYDRA] \t#0 : foo=bar
                [JOB] custom_callback on_job_start
                [JOB] foo: bar

                [JOB] custom_callback on_job_end
                [HYDRA] custom_callback on_multirun_end""")
            ),
            id="custom_callback_multirun",
        ),
        param(
            "tests/test_apps/app_with_callbacks/custom_callback/my_app.py",
            [
                "--config-name",
                "config_with_two_callbacks",
            ],
            re.escape(
                dedent("""\
                [HYDRA] Init callback_1
                [HYDRA] Init callback_2
                [HYDRA] callback_1 on_run_start
                [HYDRA] callback_2 on_run_start
                [JOB] callback_1 on_job_start
                [JOB] callback_2 on_job_start
                [JOB] {}

                [JOB] callback_2 on_job_end
                [JOB] callback_1 on_job_end
                [JOB] callback_2 on_run_end
                [JOB] callback_1 on_run_end""")
            ),
            id="two_custom_callbacks",
        ),
        param(
            "tests/test_apps/app_with_callbacks/on_job_start_accepts_task_function/my_app.py",
            [],
            r"\[JOB\] on_job_start task_function: <function my_app at 0x[0-9a-fA-F]+>",
            id="on_job_start_task_function",
        ),
    ],
)
def test_app_with_callbacks(
    tmpdir: Path,
    app_path: str,
    args: list[str],
    expected: str,
) -> None:
    cmd = [
        app_path,
        f'hydra.run.dir="{str(tmpdir)}"',
        "hydra.job.chdir=True",
        "hydra.hydra_logging.formatters.simple.format='[HYDRA] %(message)s'",
        "hydra.job_logging.formatters.simple.format='[JOB] %(message)s'",
    ]
    cmd.extend(args)
    result, _err = run_python_script(cmd)

    assert_multiline_regex_search(
        pattern=r"\A" + expected + r"\Z",
        string=result,
        from_name="Expected output",
        to_name="Actual output",
    )


def test_callbacks_on_keyboard_interrupt(tmpdir: Path) -> None:
    app_path = "tests/test_apps/app_with_callbacks/keyboard_interrupt/my_app.py"
    cmd = [
        sys.executable,
        app_path,
        f'hydra.run.dir="{str(tmpdir)}"',
        "hydra.job.chdir=True",
        "hydra.hydra_logging.formatters.simple.format='[HYDRA] %(message)s'",
        "hydra.job_logging.formatters.simple.format='[JOB] %(message)s'",
    ]
    process = subprocess.run(cmd, capture_output=True, text=True)
    result = process.stdout

    expected_job_return = (
        "status=FAILED exc=KeyboardInterrupt task_name=my_app "
        "has_cfg=True has_working_dir=True"
    )
    # both callbacks fire exactly once, with a fully populated JobReturn
    # carrying the interrupt
    assert result.count("custom_callback on_job_end") == 1
    assert result.count("custom_callback on_run_end") == 1
    assert f"[JOB] custom_callback on_job_end {expected_job_return}" in result
    assert f"[JOB] custom_callback on_run_end {expected_job_return}" in result
    # the interrupt must still propagate out of the application
    assert process.returncode != 0
    assert "KeyboardInterrupt" in process.stderr


@mark.parametrize("status", [JobStatus.COMPLETED, JobStatus.FAILED])
def test_log_job_return_callback_is_deprecated_noop(
    status: JobStatus, caplog: Any
) -> None:
    with warns(Hydra15MigrationWarning, match="no longer has any effect") as record:
        callback = LogJobReturnCallback()
    assert "task exceptions" in str(record[0].message)

    callback.on_job_end(
        config=OmegaConf.create({}),
        job_return=JobReturn(status=status, _return_value=ValueError("job failed")),
    )
    assert not caplog.records


def test_log_job_return_callback_config_warns_only_once() -> None:
    config = OmegaConf.create(
        {
            "hydra": {
                "callbacks": {
                    "log_job_return": {
                        "_target_": "hydra.experimental.callbacks.LogJobReturnCallback"
                    }
                }
            }
        }
    )
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        callbacks = Callbacks(config)

    assert len(caught) == 1
    assert issubclass(caught[0].category, Hydra15MigrationWarning)
    assert "no longer has any effect" in str(caught[0].message)
    assert isinstance(callbacks.callbacks[0], LogJobReturnCallback)

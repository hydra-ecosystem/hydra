# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved
import builtins
import pickle
import sys
import traceback
from typing import Any, cast

from omegaconf import OmegaConf, open_dict
from pytest import mark, raises

from hydra._internal.config_loader_impl import ConfigLoaderImpl
from hydra._internal.execution_policy import _get_active_execution_whitelist
from hydra._internal.utils import create_config_search_path
from hydra.core import utils
from hydra.core.hydra_config import HydraConfig
from hydra.types import HydraContext, RunMode


class NonRoundtripError(Exception):
    def __init__(self) -> None:
        super().__init__("non-roundtrip failure")


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


def test_job_return_preserves_traceback_after_pickle() -> None:
    job_return = utils.JobReturn(
        overrides=["job=0"],
        status=utils.JobStatus.FAILED,
    )
    try:
        raise ValueError("remote failure")
    except ValueError as error:
        job_return.return_value = error
        job_return._remote_traceback = utils._serialize_traceback(error.__traceback__)
        expected_traceback = job_return._remote_traceback

    restored = pickle.loads(pickle.dumps(job_return))  # nosec B301: trusted test data

    with raises(ValueError, match="remote failure") as exc_info:
        restored.return_value

    assert exc_info.value.__cause__ is None
    reconstructed = traceback.extract_tb(exc_info.value.__traceback__)
    assert [
        (frame.filename, frame.name, frame.lineno)
        for frame in reconstructed[-len(expected_traceback) :]
    ] == expected_traceback

    formatted = "".join(
        traceback.TracebackException.from_exception(exc_info.value).format()
    )
    assert "test_job_return_preserves_traceback_after_pickle" in formatted
    assert "ValueError: remote failure" in formatted


@mark.parametrize(
    "error",
    [NonRoundtripError(), ValueError("unpickleable state")],
)
def test_job_return_transports_non_picklable_exception(error: Exception) -> None:
    if isinstance(error, ValueError):
        setattr(error, "callback", lambda: None)
    error.__cause__ = ValueError("remote cause")
    job_return = utils.JobReturn(status=utils.JobStatus.FAILED)
    job_return.return_value = error
    job_return._remote_exception_chain = utils._serialize_exception_chain(error)
    job_return._remote_traceback = []
    assert job_return._return_value is error

    restored = pickle.loads(pickle.dumps(job_return))  # nosec B301: trusted test data
    with raises(RuntimeError, match=rf"Remote .*\.{type(error).__name__}") as exc_info:
        restored.return_value
    assert str(exc_info.value.__cause__) == "remote cause"


def test_job_return_from_older_pickle_without_remote_traceback_fields() -> None:
    job_return = utils.JobReturn(
        overrides=["job=0"],
        status=utils.JobStatus.FAILED,
    )
    job_return.return_value = ValueError("old failure")
    del job_return.__dict__["_remote_traceback"]
    del job_return.__dict__["_remote_exception_chain"]
    del job_return.__dict__["_remote_exception_group"]

    restored = pickle.loads(pickle.dumps(job_return))  # nosec B301: trusted test data

    with raises(ValueError, match="old failure"):
        restored.return_value


def test_job_return_preserves_exception_chain_after_pickle() -> None:
    job_return = utils.JobReturn(
        overrides=["job=0"],
        status=utils.JobStatus.FAILED,
    )
    try:
        try:
            raise ValueError("remote cause")
        except ValueError as cause:
            raise RuntimeError("remote failure") from cause
    except RuntimeError as error:
        job_return.return_value = error
        job_return._remote_traceback = utils._serialize_traceback(error.__traceback__)
        job_return._remote_exception_chain = utils._serialize_exception_chain(error)

    restored = pickle.loads(pickle.dumps(job_return))  # nosec B301: trusted test data

    with raises(RuntimeError, match="remote failure") as exc_info:
        restored.return_value

    cause = exc_info.value.__cause__
    assert cause is not None
    assert type(cause).__name__ == "ValueError"
    formatted = "".join(
        traceback.TracebackException.from_exception(exc_info.value).format()
    )
    assert "ValueError: remote cause" in formatted
    assert "The above exception was the direct cause" in formatted
    assert "RuntimeError: remote failure" in formatted


@mark.skipif(sys.version_info < (3, 11), reason="ExceptionGroup requires Python 3.11")
def test_job_return_preserves_exception_group_tracebacks_after_pickle() -> None:
    exception_group_type = cast(Any, getattr(builtins, "ExceptionGroup"))

    def member_failure() -> None:
        try:
            raise ValueError("member cause")
        except ValueError as cause:
            raise RuntimeError("member failure") from cause

    job_return = utils.JobReturn(
        overrides=["job=0"],
        status=utils.JobStatus.FAILED,
    )
    try:
        try:
            member_failure()
        except RuntimeError as member:
            nested = exception_group_type("nested group", [member])
            raise exception_group_type("remote group", [nested])
    except Exception as error:
        job_return.return_value = error
        job_return._remote_traceback = utils._serialize_traceback(error.__traceback__)
        job_return._remote_exception_chain = utils._serialize_exception_chain(error)
        job_return._remote_exception_group = utils._serialize_exception_group(error)

    restored = pickle.loads(pickle.dumps(job_return))  # nosec B301: trusted test data

    with raises(exception_group_type, match="remote group") as exc_info:
        restored.return_value

    formatted = "".join(
        traceback.TracebackException.from_exception(exc_info.value).format()
    )
    assert "ValueError: member cause" in formatted
    assert "The above exception was the direct cause" in formatted
    assert "in member_failure" in formatted
    assert "RuntimeError: member failure" in formatted


@mark.skipif(sys.version_info < (3, 11), reason="ExceptionGroup requires Python 3.11")
def test_job_return_preserves_chained_exception_group_after_pickle() -> None:
    exception_group_type = cast(Any, getattr(builtins, "ExceptionGroup"))

    def member_failure() -> None:
        raise ValueError("member failure")

    job_return = utils.JobReturn(
        overrides=["job=0"],
        status=utils.JobStatus.FAILED,
    )
    try:
        try:
            member_failure()
        except ValueError as member:
            raise exception_group_type("cause group", [member])
    except Exception as cause:
        try:
            raise RuntimeError("remote failure") from cause
        except RuntimeError as error:
            job_return.return_value = error
            job_return._remote_traceback = utils._serialize_traceback(
                error.__traceback__
            )
            job_return._remote_exception_chain = utils._serialize_exception_chain(error)

    restored = pickle.loads(pickle.dumps(job_return))  # nosec B301: trusted test data

    with raises(RuntimeError, match="remote failure") as exc_info:
        restored.return_value

    cause = exc_info.value.__cause__
    assert isinstance(cause, exception_group_type)
    formatted = "".join(
        traceback.TracebackException.from_exception(exc_info.value).format()
    )
    assert "ExceptionGroup: cause group" in formatted
    assert "in member_failure" in formatted
    assert "ValueError: member failure" in formatted


def test_run_job_handles_unprintable_chained_exception(
    hydra_restore_singletons: Any, tmp_path: Any
) -> None:
    class BrokenCause(Exception):
        def __str__(self) -> str:
            raise RuntimeError("broken __str__")

    completed = []

    class RecordingCallbacks:
        def on_job_start(self, **kwargs: Any) -> None:
            pass

        def on_job_end(self, **kwargs: Any) -> None:
            completed.append(kwargs["job_return"])

    def task_function(_: Any) -> None:
        try:
            raise BrokenCause()
        except BrokenCause as cause:
            raise ValueError("task failure") from cause

    config_loader = ConfigLoaderImpl(
        config_search_path=create_config_search_path("pkg://hydra.test_utils.configs")
    )
    cfg = config_loader.load_configuration(
        config_name="compose",
        run_mode=RunMode.RUN,
        overrides=[f"hydra.run.dir={tmp_path}", "hydra.output_subdir=null"],
    )
    result = utils.run_job(
        task_function=task_function,
        config=cfg,
        job_dir_key="hydra.run.dir",
        job_subdir_key=None,
        hydra_context=HydraContext(
            config_loader=config_loader,
            callbacks=cast(Any, RecordingCallbacks()),
        ),
        configure_logging=False,
    )

    assert result.status is utils.JobStatus.FAILED
    assert completed == [result]

    restored = pickle.loads(pickle.dumps(result))  # nosec B301: trusted test data
    with raises(ValueError, match="task failure") as exc_info:
        restored.return_value

    formatted = "".join(
        traceback.TracebackException.from_exception(exc_info.value).format()
    )
    assert "BrokenCause: <exception message unavailable>" in formatted
    assert "ValueError: task failure" in formatted

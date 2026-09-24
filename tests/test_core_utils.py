# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved
import builtins
import pickle
import sys
import threading
import traceback
from typing import Any, cast

from omegaconf import OmegaConf, open_dict
from pytest import importorskip, mark, raises

from hydra._internal.config_loader_impl import ConfigLoaderImpl
from hydra._internal.execution_policy import _get_active_execution_whitelist
from hydra._internal.utils import create_config_search_path
from hydra.core import utils
from hydra.core.hydra_config import HydraConfig
from hydra.types import HydraContext, RunMode


class NonRoundtripError(Exception):
    def __init__(self) -> None:
        super().__init__("non-roundtrip failure")


class NoteDroppingError(Exception):
    def __reduce__(self) -> Any:
        return type(self), self.args


class CausePreservingError(Exception):
    def __reduce__(self) -> Any:
        return type(self), self.args, {"cause": self.__cause__}


class ContextPreservingError(Exception):
    def __reduce__(self) -> Any:
        return type(self), self.args, {"context": self.__context__}


class MessageChangingError(Exception):
    def __reduce__(self) -> Any:
        return type(self), ("changed message",), {"__notes__": self.__notes__}


class ArgsChangingError(Exception):
    def __reduce__(self) -> Any:
        return type(self), (str(self),)


class OverridingTracebackError(Exception):
    def with_traceback(self, tb: Any) -> Any:
        raise RuntimeError("custom with_traceback called")


class InterruptingReducerError(Exception):
    def __reduce__(self) -> Any:
        raise KeyboardInterrupt("reducer interrupted")


class OneShotReducerError(Exception):
    def __reduce__(self) -> Any:
        calls = getattr(self, "reduce_calls", 0) + 1
        self.reduce_calls = calls
        if calls > 1:
            raise KeyboardInterrupt("reducer called twice")
        return type(self), self.args


class SecondLoadFailureError(Exception):
    load_count = 0

    def __reduce__(self) -> Any:
        return type(self), self.args, {}

    def __setstate__(self, state: Any) -> None:
        type(self).load_count += 1
        if type(self).load_count > 1:
            raise ValueError("second exception load failed")


class InterruptingNotesError(Exception):
    def __getattribute__(self, name: str) -> Any:
        if name == "__notes__":
            raise KeyboardInterrupt("notes unavailable")
        return super().__getattribute__(name)


class InterruptingNoteList(list[str]):
    def __iter__(self) -> Any:
        raise RuntimeError("note iteration unavailable")


class FalseyNoteList(list[Any]):
    def __bool__(self) -> bool:
        return False


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
        if hasattr(error, "add_note"):
            error.add_note("full_key: foo")
        job_return.return_value = error
        job_return._remote_traceback = utils._serialize_traceback(error.__traceback__)
        expected_traceback = job_return._remote_traceback

    restored = pickle.loads(pickle.dumps(job_return))  # nosec B301: trusted test data

    with raises(ValueError, match="remote failure") as exc_info:
        restored.return_value

    assert exc_info.value.__cause__ is None
    if hasattr(exc_info.value, "add_note"):
        assert exc_info.value.__notes__ == ["full_key: foo"]
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


def test_job_return_bypasses_custom_with_traceback_after_pickle() -> None:
    job_return = utils.JobReturn(status=utils.JobStatus.FAILED)
    job_return.return_value = OverridingTracebackError("remote failure")
    job_return._remote_traceback = []

    restored = pickle.loads(pickle.dumps(job_return))  # nosec B301: trusted test data

    with raises(OverridingTracebackError, match="remote failure"):
        restored.return_value


@mark.parametrize(
    "error",
    [NonRoundtripError(), ValueError("unpickleable state")],
)
def test_job_return_transports_non_picklable_exception(error: Exception) -> None:
    if isinstance(error, ValueError):
        setattr(error, "callback", threading.Lock())
    error.__cause__ = ValueError("remote cause")
    if hasattr(error, "add_note"):
        error.add_note("full_key: foo")
    job_return = utils.JobReturn(status=utils.JobStatus.FAILED)
    job_return.return_value = error
    job_return._remote_exception_chain = utils._serialize_exception_chain(error)
    job_return._remote_traceback = []
    assert job_return._return_value is error

    restored = pickle.loads(pickle.dumps(job_return))  # nosec B301: trusted test data
    with raises(RuntimeError, match=rf"Remote .*\.{type(error).__name__}") as exc_info:
        restored.return_value
    assert str(exc_info.value.__cause__) == "remote cause"
    if hasattr(error, "add_note"):
        assert exc_info.value.__notes__ == ["full_key: foo"]


def test_job_return_preserves_exception_with_nan_arg() -> None:
    job_return = utils.JobReturn(status=utils.JobStatus.FAILED)
    job_return.return_value = ValueError(float("nan"))

    restored = pickle.loads(pickle.dumps(job_return))  # nosec B301: trusted test data

    with raises(ValueError, match="nan"):
        restored.return_value


def test_job_return_drops_non_string_notes() -> None:
    error = ValueError("remote failure")
    setattr(error, "__notes__", ["full_key: foo", {"unsafe": "note"}])
    job_return = utils.JobReturn(status=utils.JobStatus.FAILED)
    job_return.return_value = error

    restored = pickle.loads(pickle.dumps(job_return))  # nosec B301: trusted test data

    assert job_return._return_value is error
    assert error.__notes__ == ["full_key: foo", {"unsafe": "note"}]
    with raises(RuntimeError, match="Remote builtins.ValueError") as exc_info:
        restored.return_value
    assert getattr(exc_info.value, "__notes__", []) == (
        ["full_key: foo"] if hasattr(BaseException, "add_note") else []
    )


@mark.skipif(sys.version_info < (3, 11), reason="Exception notes require Python 3.11")
def test_job_return_preserves_notes_with_custom_reducer() -> None:
    error = NoteDroppingError("remote failure")
    error.add_note("full_key: foo")
    job_return = utils.JobReturn(status=utils.JobStatus.FAILED)
    job_return.return_value = error

    restored = pickle.loads(pickle.dumps(job_return))  # nosec B301: trusted test data

    assert job_return._return_value is error
    with raises(
        RuntimeError, match="Remote tests.test_core_utils.NoteDroppingError"
    ) as exc_info:
        restored.return_value
    assert exc_info.value.__notes__ == ["full_key: foo"]


def test_job_return_drops_non_string_notes_on_custom_chained_cause() -> None:
    cause = ValueError("remote cause")
    setattr(cause, "__notes__", ["full_key: nested", {"unsafe": "note"}])
    error = CausePreservingError("remote failure")
    error.__cause__ = cause
    job_return = utils.JobReturn(status=utils.JobStatus.FAILED)
    job_return.return_value = error
    job_return._remote_traceback = []
    job_return._remote_exception_chain = utils._serialize_exception_chain(error)

    serialized = pickle.dumps(job_return)

    assert b"unsafe" not in serialized
    assert job_return._return_value is error
    restored = pickle.loads(serialized)  # nosec B301: trusted test data
    with raises(
        RuntimeError, match="Remote tests.test_core_utils.CausePreservingError"
    ) as exc_info:
        restored.return_value
    assert getattr(exc_info.value.__cause__, "__notes__", []) == (
        ["full_key: nested"] if hasattr(BaseException, "add_note") else []
    )


@mark.skipif(sys.version_info < (3, 11), reason="Exception notes require Python 3.11")
def test_job_return_preserves_duplicate_notes_in_chained_cause() -> None:
    cause = ValueError("remote cause")
    cause.add_note("detail")
    cause.add_note("detail")
    error = ValueError("remote failure")
    error.__cause__ = cause
    job_return = utils.JobReturn(status=utils.JobStatus.FAILED)
    job_return.return_value = error
    job_return._remote_traceback = []
    job_return._remote_exception_chain = utils._serialize_exception_chain(error)

    restored = pickle.loads(pickle.dumps(job_return))  # nosec B301: trusted test data

    with raises(ValueError, match="remote failure") as exc_info:
        restored.return_value
    assert exc_info.value.__cause__ is not None
    assert exc_info.value.__cause__.__notes__ == ["detail", "detail"]


def test_job_return_preserves_cloudpickle_only_error() -> None:
    cloudpickle = importorskip("cloudpickle")

    class LocalError(Exception):
        pass

    job_return = utils.JobReturn(status=utils.JobStatus.FAILED)
    job_return.return_value = LocalError("remote failure")

    restored = cloudpickle.loads(cloudpickle.dumps(job_return))

    assert type(restored._return_value).__name__ == "LocalError"
    assert str(restored._return_value) == "remote failure"


def test_job_return_uses_standard_pickle_for_builtin_error(monkeypatch: Any) -> None:
    cloudpickle = importorskip("cloudpickle")

    def fail_dumps(*args: Any, **kwargs: Any) -> bytes:
        raise AssertionError("cloudpickle should not serialize built-in exceptions")

    monkeypatch.setattr(cloudpickle, "dumps", fail_dumps)
    error = RuntimeError("launcher failure")
    error.__cause__ = ValueError("launcher cause")
    job_return = utils.JobReturn(status=utils.JobStatus.FAILED)
    job_return.return_value = error

    restored = pickle.loads(pickle.dumps(job_return))  # nosec B301: trusted test data

    assert type(restored._return_value) is RuntimeError
    assert str(restored._return_value) == "launcher failure"


@mark.skipif(sys.version_info < (3, 11), reason="Exception notes require Python 3.11")
def test_job_return_preserves_message_with_custom_reducer() -> None:
    error = MessageChangingError("original message")
    error.add_note("full_key: foo")
    job_return = utils.JobReturn(status=utils.JobStatus.FAILED)
    job_return.return_value = error

    restored = pickle.loads(pickle.dumps(job_return))  # nosec B301: trusted test data

    assert job_return._return_value is error
    with raises(RuntimeError, match="original message") as exc_info:
        restored.return_value
    assert exc_info.value.__notes__ == ["full_key: foo"]


def test_job_return_falls_back_when_args_change_without_message_change() -> None:
    error = ArgsChangingError(1, 2)
    job_return = utils.JobReturn(status=utils.JobStatus.FAILED)
    job_return.return_value = error

    restored = pickle.loads(pickle.dumps(job_return))  # nosec B301: trusted test data

    assert job_return._return_value is error
    with raises(RuntimeError, match="Remote tests.test_core_utils.ArgsChangingError"):
        restored.return_value


def test_job_return_drops_non_string_notes_in_suppressed_context() -> None:
    context = ValueError("hidden context")
    setattr(context, "__notes__", ["full_key: hidden", {"unsafe": "note"}])
    error = ContextPreservingError("visible failure")
    error.__context__ = context
    error.__suppress_context__ = True
    job_return = utils.JobReturn(status=utils.JobStatus.FAILED)
    job_return.return_value = error
    job_return._remote_traceback = []
    job_return._remote_exception_chain = utils._serialize_exception_chain(error)

    serialized = pickle.dumps(job_return)

    assert b"unsafe" not in serialized
    restored = pickle.loads(serialized)  # nosec B301: trusted test data
    with raises(RuntimeError, match="visible failure"):
        restored.return_value


def test_job_return_falls_back_when_reducer_raises_base_exception() -> None:
    error = InterruptingReducerError("remote failure")
    job_return = utils.JobReturn(status=utils.JobStatus.FAILED)
    job_return.return_value = error

    restored = pickle.loads(pickle.dumps(job_return))  # nosec B301: trusted test data

    assert job_return._return_value is error
    with raises(
        RuntimeError, match="Remote tests.test_core_utils.InterruptingReducerError"
    ):
        restored.return_value


def test_job_return_does_not_reduce_exception_twice() -> None:
    error = OneShotReducerError("remote failure")
    job_return = utils.JobReturn(status=utils.JobStatus.FAILED)
    job_return.return_value = error

    restored = pickle.loads(pickle.dumps(job_return))  # nosec B301: trusted test data

    assert job_return._return_value is error
    assert error.reduce_calls == 1
    with raises(OneShotReducerError, match="remote failure"):
        restored.return_value


def test_job_return_falls_back_when_second_exception_load_fails() -> None:
    SecondLoadFailureError.load_count = 0
    error = SecondLoadFailureError("remote failure")
    job_return = utils.JobReturn(status=utils.JobStatus.FAILED)
    job_return.return_value = error

    restored = pickle.loads(pickle.dumps(job_return))  # nosec B301: trusted test data

    assert job_return._return_value is error
    assert SecondLoadFailureError.load_count == 2
    with raises(
        RuntimeError, match="Remote tests.test_core_utils.SecondLoadFailureError"
    ):
        restored.return_value


@mark.skipif(sys.version_info < (3, 11), reason="Exception notes require Python 3.11")
def test_job_return_falls_back_when_exception_notes_interrupt() -> None:
    error = InterruptingNotesError("remote failure")
    job_return = utils.JobReturn(status=utils.JobStatus.FAILED)
    job_return.return_value = error

    restored = pickle.loads(pickle.dumps(job_return))  # nosec B301: trusted test data

    assert job_return._return_value is error
    with raises(
        RuntimeError, match="Remote tests.test_core_utils.InterruptingNotesError"
    ):
        restored.return_value


@mark.skipif(sys.version_info < (3, 11), reason="Exception notes require Python 3.11")
def test_job_return_drops_custom_exception_note_list() -> None:
    error = ValueError("remote failure")
    setattr(error, "__notes__", InterruptingNoteList(["safe note"]))
    job_return = utils.JobReturn(status=utils.JobStatus.FAILED)
    job_return.return_value = error

    restored = pickle.loads(pickle.dumps(job_return))  # nosec B301: trusted test data

    with raises(RuntimeError, match="Remote builtins.ValueError") as exc_info:
        restored.return_value
    assert getattr(exc_info.value, "__notes__", []) == []


@mark.skipif(sys.version_info < (3, 11), reason="Exception notes require Python 3.11")
def test_job_return_drops_falsey_custom_exception_note_list() -> None:
    error = ValueError("remote failure")
    setattr(error, "__notes__", FalseyNoteList([{"unsafe": "note"}]))
    job_return = utils.JobReturn(status=utils.JobStatus.FAILED)
    job_return.return_value = error

    serialized = pickle.dumps(job_return)
    restored = pickle.loads(serialized)  # nosec B301: trusted test data

    assert b"unsafe" not in serialized
    with raises(RuntimeError, match="Remote builtins.ValueError"):
        restored.return_value


def test_job_return_from_older_state_without_remote_traceback_fields() -> None:
    job_return = utils.JobReturn(
        overrides=["job=0"],
        status=utils.JobStatus.FAILED,
    )
    job_return.return_value = ValueError("old failure")
    del job_return.__dict__["_remote_traceback"]
    del job_return.__dict__["_remote_exception_chain"]
    del job_return.__dict__["_remote_exception_group"]

    restored = utils.JobReturn.__new__(utils.JobReturn)
    restored.__setstate__(job_return.__dict__.copy())

    with raises(ValueError, match="old failure"):
        restored.return_value


def test_legacy_serialized_exception_node_without_notes() -> None:
    legacy_node = ("builtins", "ValueError", "old failure", True, [], [], [])
    restored = utils._deserialize_exception_node(cast(Any, legacy_node))
    assert type(restored).__name__ == "ValueError"
    assert str(restored) == "old failure"


def test_job_return_preserves_exception_chain_after_pickle() -> None:
    job_return = utils.JobReturn(
        overrides=["job=0"],
        status=utils.JobStatus.FAILED,
    )
    try:
        try:
            raise ValueError("remote cause")
        except ValueError as cause:
            if hasattr(cause, "add_note"):
                cause.add_note("full_key: nested")
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
    if hasattr(cause, "add_note"):
        assert cause.__notes__ == ["full_key: nested"]
    formatted = "".join(
        traceback.TracebackException.from_exception(exc_info.value).format()
    )
    assert "ValueError: remote cause" in formatted
    assert "The above exception was the direct cause" in formatted
    assert "RuntimeError: remote failure" in formatted


@mark.skipif(sys.version_info < (3, 11), reason="ExceptionGroup requires Python 3.11")
def test_job_return_drops_non_string_group_member_notes() -> None:
    exception_group_type = cast(Any, getattr(builtins, "ExceptionGroup"))
    member = ValueError("member failure")
    setattr(member, "__notes__", ["full_key: child", {"unsafe": "note"}])
    error = exception_group_type("remote group", [member])
    job_return = utils.JobReturn(status=utils.JobStatus.FAILED)
    job_return.return_value = error
    job_return._remote_exception_group = utils._serialize_exception_group(error)

    serialized = pickle.dumps(job_return)
    assert b"unsafe" not in serialized
    restored = pickle.loads(serialized)  # nosec B301: trusted test data
    with raises(RuntimeError, match="Remote builtins.ExceptionGroup"):
        restored.return_value


@mark.skipif(sys.version_info < (3, 11), reason="ExceptionGroup requires Python 3.11")
def test_job_return_falls_back_when_group_member_message_changes() -> None:
    exception_group_type = cast(Any, getattr(builtins, "ExceptionGroup"))
    member = MessageChangingError("original message")
    member.add_note("full_key: child")
    error = exception_group_type("remote group", [member])
    job_return = utils.JobReturn(status=utils.JobStatus.FAILED)
    job_return.return_value = error
    job_return._remote_exception_group = utils._serialize_exception_group(error)

    restored = pickle.loads(pickle.dumps(job_return))  # nosec B301: trusted test data

    assert job_return._return_value is error
    with raises(RuntimeError, match="Remote builtins.ExceptionGroup"):
        restored.return_value


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

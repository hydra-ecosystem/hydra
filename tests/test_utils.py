# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved
import builtins
import io
import json
import os
import pickle
import re
import sys
import traceback
from dataclasses import dataclass
from pathlib import Path
from textwrap import dedent
from types import TracebackType
from typing import Any, NoReturn, Optional
from unittest.mock import patch

from omegaconf import DictConfig, OmegaConf
from pytest import mark, param, raises, warns

from hydra import utils
from hydra._internal.deprecation_warning import deprecation_warning
from hydra._internal.utils import _hidden_instantiation_frame, run_and_report
from hydra.conf import HydraConf, RuntimeConf
from hydra.core.hydra_config import HydraConfig
from hydra.core.override_parser.overrides_parser import OverridesParser
from hydra.core.utils import (
    JobReturn,
    JobStatus,
    _deserialize_traceback,
    _serialize_exception_chain,
    _serialize_traceback,
)
from hydra.errors import (
    ConfigCompositionException,
    HydraDeprecationError,
    InstantiationException,
)
from hydra.test_utils.test_utils import (
    assert_multiline_regex_search,
    assert_regex_match,
)


def test_get_original_cwd(hydra_restore_singletons: Any) -> None:
    orig = "/foo/AClass"
    cfg = OmegaConf.create({"hydra": HydraConf(runtime=RuntimeConf(cwd=orig))})
    assert isinstance(cfg, DictConfig)
    HydraConfig.instance().set_config(cfg)
    assert utils.get_original_cwd() == orig


def test_get_original_cwd_without_hydra(hydra_restore_singletons: Any) -> None:
    with raises(ValueError):
        utils.get_original_cwd()


@mark.parametrize(
    "orig_cwd, path, expected",
    [
        ("/home/omry/hydra", "foo/bar", "/home/omry/hydra/foo/bar"),
        ("/home/omry/hydra/", "foo/bar", "/home/omry/hydra/foo/bar"),
        ("/home/omry/hydra/", "/foo/bar", "/foo/bar"),
    ],
)
def test_to_absolute_path(
    hydra_restore_singletons: Any, orig_cwd: str, path: str, expected: str
) -> None:
    # normalize paths to current OS
    orig_cwd = str(Path(orig_cwd))
    path = str(Path(path))
    expected = str(Path(expected))
    cfg = OmegaConf.create({"hydra": HydraConf(runtime=RuntimeConf(cwd=orig_cwd))})
    assert isinstance(cfg, DictConfig)
    HydraConfig().set_config(cfg)
    assert utils.to_absolute_path(path) == expected


@mark.parametrize(
    "path, expected",
    [
        ("foo/bar", f"{os.getcwd()}/foo/bar"),
        ("foo/bar", f"{os.getcwd()}/foo/bar"),
        ("/foo/bar", os.path.abspath("/foo/bar")),
    ],
)
def test_to_absolute_path_without_hydra(
    hydra_restore_singletons: Any, path: str, expected: str
) -> None:
    # normalize paths to current OS
    path = str(Path(path))
    expected = str(Path(expected).absolute())
    assert utils.to_absolute_path(path) == expected


@mark.parametrize(
    "obj",
    [
        ("foo bar"),
        (10),
        ({"foo": '\\"bar\\\'"'}),
        ([1, 2, "3", {"a": "xyz"}]),
        ({"a": 10, "b": "c", "d": {"e": [1, 2, "3"], "f": ["g", {"h": {"i": "j"}}]}}),
        (
            {
                "a": 10,
                "b": "c\nnl",
                "d": {"e": [1, 2, "3"], "f": ["g", {"h": {"i": "j"}}]},
            }
        ),
        ({"json_val": json.dumps({"a": 10, "b": "c\\\nnl"}, indent=4)}),
    ],
)
def test_to_hydra_override_value_str_roundtrip(
    hydra_restore_singletons: Any, obj: Any
) -> None:
    msg = (
        "to_hydra_override_value_str() is deprecated and will be removed in "
        "Hydra 1.5. See "
        "https://github.com/hydra-ecosystem/hydra/pull/2930#issuecomment-5018616929"
    )
    with warns(UserWarning, match=re.escape(msg)) as records:
        override_str = utils.to_hydra_override_value_str(obj)
    assert len(records) == 1
    override_params = f"++ov={override_str}"
    o = OverridesParser.create().parse_override(override_params)
    assert o.value() == obj


@mark.parametrize(
    "env_setting,expected_error",
    [
        param(None, False, id="env_unset"),
        param("", False, id="env_empty"),
        param("1", True, id="env_set"),
    ],
)
def test_deprecation_warning(
    monkeypatch: Any, env_setting: Optional[str], expected_error: bool
) -> None:
    msg = "Feature FooBar is deprecated"
    if env_setting is not None:
        monkeypatch.setenv("HYDRA_DEPRECATION_WARNINGS_AS_ERRORS", env_setting)
    if expected_error:
        with raises(HydraDeprecationError, match=re.escape(msg)):
            deprecation_warning(msg)
    else:
        with warns(UserWarning, match=re.escape(msg)):
            deprecation_warning(msg)


class TestRunAndReport:
    """
    Test the `hydra._internal.utils.run_and_report` function.

    def run_and_report(func: Any) -> Any: ...

    This class defines several test methods:
      test_success:
          a simple test case where `run_and_report(func)` succeeds.
      test_failure:
          test when `func` raises an exception, and `run_and_report(func)`
          prints a nicely-formatted error message
      test_simplified_traceback_failure:
          test when printing a nicely-formatted error message fails, so
          `run_and_report` falls back to re-raising the exception from `func`.
    """

    def test_hidden_frame_does_not_resolve_local_source(
        self, tmp_path: Path, monkeypatch: Any
    ) -> None:
        (tmp_path / "Hydra frames hidden").write_text("unrelated local source\n")
        monkeypatch.chdir(tmp_path)
        with patch("linecache.cache", {}):
            formatted = "".join(traceback.format_tb(_hidden_instantiation_frame()))
        assert "unrelated local source" not in formatted

    class DemoFunctions:
        """
        The methods of this `DemoFunctions` class are passed to
        `run_and_report` as the func argument.
        """

        @staticmethod
        def success_func() -> Any:
            return 123

        @staticmethod
        def simple_error() -> None:
            assert False, "simple_err_msg"

        @staticmethod
        def run_job_wrapper() -> None:
            """
            Trigger special logic in `run_and_report` that looks for a function
            called "run_job" in the stack and strips away the leading stack
            frames.
            """

            def run_job() -> None:
                def nested_error() -> None:
                    assert False, "nested_err"

                nested_error()

            run_job()

        @staticmethod
        def omegaconf_job_wrapper() -> None:
            """
            Trigger special logic in `run_and_report` that looks for the
            `omegaconf` module in the stack and strips away the bottom stack
            frames.
            """

            def run_job() -> None:
                def job_calling_omconf() -> None:
                    from omegaconf import OmegaConf

                    # The below causes an exception:
                    OmegaConf.resolve(123)  # type: ignore

                job_calling_omconf()

            run_job()

    def test_success(self) -> None:
        assert run_and_report(self.DemoFunctions.success_func) == 123

    def test_composition_error_remains_compact(self) -> None:
        def fail() -> None:
            raise ConfigCompositionException("bad config")

        mock_stderr = io.StringIO()
        with raises(SystemExit, match="1"), patch("sys.stderr", new=mock_stderr):
            run_and_report(fail)

        assert mock_stderr.getvalue() == f"bad config{os.linesep}"

    def test_instantiation_error_under_debugger_is_unmodified(self) -> None:
        error = InstantiationException("bad target")

        def fail() -> None:
            raise error

        with (
            patch("hydra._internal.utils.is_under_debugger", return_value=True),
            raises(InstantiationException) as exc_info,
        ):
            run_and_report(fail)

        assert exc_info.value is error

    @mark.parametrize("with_cause", [False, True])
    def test_restored_instantiation_traceback(self, with_cause: bool) -> None:
        root = Path(__file__).resolve().parent.parent
        error = InstantiationException("bad target")
        error.__traceback__ = _deserialize_traceback(
            [
                (str(root / "hydra/core/utils.py"), "_run_job", 208),
                (str(root / "tests/test_utils.py"), "user_task", 1),
                (
                    str(root / "hydra/_internal/instantiate/_instantiate2.py"),
                    "instantiate",
                    476,
                ),
            ]
        )
        if with_cause:
            cause = ValueError("target failed")
            cause.__traceback__ = _deserialize_traceback(
                [
                    (
                        str(root / "hydra/_internal/instantiate/_instantiate2.py"),
                        "_call_target",
                        275,
                    ),
                    (str(root / "tests/test_utils.py"), "user_target", 1),
                ]
            )
            error.__cause__ = cause

        captured: list[list[str]] = []

        def hook(
            error_type: type[BaseException],
            exception: BaseException,
            tb: Optional[TracebackType],
        ) -> None:
            assert error_type is InstantiationException
            assert exception is error
            for current in (
                tb,
                exception.__cause__.__traceback__ if exception.__cause__ else None,
            ):
                frames = []
                while current is not None:
                    frames.append(current.tb_frame.f_code.co_name)
                    current = current.tb_next
                captured.append(frames)

        def fail() -> None:
            raise error

        with raises(SystemExit, match="1"), patch("sys.excepthook", new=hook):
            run_and_report(fail)

        assert captured == (
            [["user_task", "omitted"], ["omitted", "user_target"]]
            if with_cause
            else [["user_task", "omitted"], []]
        )

    def test_restored_nested_instantiation_traceback(self) -> None:
        root = Path(__file__).resolve().parent.parent
        inner_type = type(
            "InstantiationException",
            (Exception,),
            {"__module__": "hydra.errors"},
        )
        cause = ValueError("target failed")
        cause.__traceback__ = _deserialize_traceback(
            [(str(root / "tests/test_utils.py"), "user_target", 1)]
        )
        inner = inner_type("inner target:\nValueError('target failed')")
        inner.__cause__ = cause
        inner.__traceback__ = _deserialize_traceback(
            [
                (str(root / "tests/test_utils.py"), "user_nested", 1),
                (
                    str(root / "hydra/_internal/instantiate/_instantiate2.py"),
                    "instantiate",
                    476,
                ),
            ]
        )
        error = InstantiationException("outer target")
        error.__cause__ = inner
        error.__traceback__ = _deserialize_traceback(
            [
                (str(root / "hydra/core/utils.py"), "_run_job", 208),
                (str(root / "tests/test_utils.py"), "user_task", 1),
            ]
        )

        def fail() -> None:
            raise error

        mock_stderr = io.StringIO()
        with raises(SystemExit, match="1"), patch("sys.stderr", new=mock_stderr):
            run_and_report(fail)

        output = mock_stderr.getvalue()
        assert "in user_task" in output
        assert "in user_nested" in output
        assert "in user_target" in output
        assert "_instantiate2.py" not in output
        assert output.count("ValueError: target failed") == 1
        assert "ValueError('target failed')" not in output

    def test_restored_lookup_wrapper_does_not_repeat_cause(self) -> None:
        root = Path(__file__).resolve().parent.parent
        missing_type = type(
            "ModuleNotFoundError", (Exception,), {"__module__": "builtins"}
        )
        import_type = type("ImportError", (Exception,), {"__module__": "builtins"})
        cause = missing_type("no module")
        cause.__traceback__ = _deserialize_traceback(
            [(str(root / "tests/test_utils.py"), "user_target", 1)]
        )
        lookup = import_type(f"Error loading target:\n{cause!r}")
        lookup.__cause__ = cause
        lookup.__traceback__ = _deserialize_traceback(
            [(str(root / "hydra/_internal/_locate.py"), "_locate", 46)]
        )
        error = InstantiationException("Error locating target")
        error.__cause__ = lookup
        error.__traceback__ = _deserialize_traceback(
            [
                (str(root / "hydra/core/utils.py"), "_run_job", 208),
                (str(root / "tests/test_utils.py"), "user_task", 1),
            ]
        )

        def fail() -> None:
            raise error

        mock_stderr = io.StringIO()
        with raises(SystemExit, match="1"), patch("sys.stderr", new=mock_stderr):
            run_and_report(fail)

        output = mock_stderr.getvalue()
        assert "ModuleNotFoundError: no module" in output
        assert "ModuleNotFoundError('no module')" not in output

    def test_user_exception_with_read_only_args(self) -> None:
        class ReadOnlyArgsError(Exception):
            @property
            def args(self) -> tuple[str]:  # pyrefly: ignore [bad-override]
                return ("target failed",)

            def __str__(self) -> str:
                return "target failed"

        root = Path(__file__).resolve().parent.parent
        cause = ReadOnlyArgsError()
        cause.__traceback__ = _deserialize_traceback(
            [(str(root / "tests/test_utils.py"), "user_target", 1)]
        )
        error = InstantiationException("bad target")
        error.__cause__ = cause
        error.__traceback__ = _deserialize_traceback(
            [
                (str(root / "hydra/core/utils.py"), "_run_job", 208),
                (str(root / "tests/test_utils.py"), "user_task", 1),
            ]
        )

        def fail() -> None:
            raise error

        mock_stderr = io.StringIO()
        with raises(SystemExit, match="1"), patch("sys.stderr", new=mock_stderr):
            run_and_report(fail)

        assert "ReadOnlyArgsError: target failed" in mock_stderr.getvalue()

    def test_frozen_user_exception_traceback(self) -> None:
        @dataclass(frozen=True)
        class FrozenError(Exception):
            message: str

            def __str__(self) -> str:
                return self.message

        root = Path(__file__).resolve().parent.parent
        cause = FrozenError("target failed")
        cause.with_traceback(
            _deserialize_traceback(
                [
                    (
                        str(root / "hydra/_internal/instantiate/_instantiate2.py"),
                        "_call_target",
                        275,
                    ),
                    (str(root / "tests/test_utils.py"), "user_target", 1),
                ]
            )
        )
        original_tb = cause.__traceback__
        error = InstantiationException("bad target")
        error.__cause__ = cause
        error.__traceback__ = _deserialize_traceback(
            [
                (str(root / "hydra/core/utils.py"), "_run_job", 208),
                (str(root / "tests/test_utils.py"), "user_task", 1),
            ]
        )

        def fail() -> None:
            raise error

        mock_stderr = io.StringIO()
        with raises(SystemExit, match="1"), patch("sys.stderr", new=mock_stderr):
            run_and_report(fail)

        output = mock_stderr.getvalue()
        assert "FrozenError: target failed" in output
        assert "in user_target" in output
        assert "_instantiate2.py" not in output
        assert cause.__traceback__ is original_tb

    def test_overridden_with_traceback_is_not_called(self) -> None:
        class RejectingTraceback(InstantiationException):
            def with_traceback(
                self, tb: Optional[TracebackType]
            ) -> "RejectingTraceback":
                raise AssertionError("custom with_traceback called")

        root = Path(__file__).resolve().parent.parent
        error = RejectingTraceback("bad target")
        error.__traceback__ = _deserialize_traceback(
            [
                (str(root / "hydra/core/utils.py"), "_run_job", 208),
                (str(root / "tests/test_utils.py"), "user_task", 1),
                (
                    str(root / "hydra/_internal/instantiate/_instantiate2.py"),
                    "instantiate",
                    476,
                ),
            ]
        )
        captured: list[str] = []

        def hook(
            error_type: type[BaseException],
            exception: BaseException,
            tb: Optional[TracebackType],
        ) -> None:
            assert error_type is RejectingTraceback
            assert exception is error
            while tb is not None:
                captured.append(tb.tb_frame.f_code.co_name)
                tb = tb.tb_next

        def fail() -> None:
            raise error

        with raises(SystemExit, match="1"), patch("sys.excepthook", new=hook):
            run_and_report(fail)

        assert captured == ["user_task", "omitted"]

    @mark.parametrize("raise_on_bool", [False, True])
    def test_explicit_cause_is_not_truth_tested(self, raise_on_bool: bool) -> None:
        bool_calls = []

        class FalseyError(Exception):
            def __bool__(self) -> bool:
                bool_calls.append(True)
                if raise_on_bool:
                    raise TypeError("cause truth-tested")
                return False

        root = Path(__file__).resolve().parent.parent
        cause = FalseyError("target failed")
        cause.__traceback__ = _deserialize_traceback(
            [
                (
                    str(root / "hydra/_internal/instantiate/_instantiate2.py"),
                    "_call_target",
                    275,
                ),
                (str(root / "tests/test_utils.py"), "user_target", 1),
            ]
        )
        error = InstantiationException("bad target")
        error.__cause__ = cause
        error.__traceback__ = _deserialize_traceback(
            [
                (str(root / "hydra/core/utils.py"), "_run_job", 208),
                (str(root / "tests/test_utils.py"), "user_task", 1),
            ]
        )

        def fail() -> None:
            raise error

        captured = []

        def hook(
            error_type: type[BaseException],
            exception: BaseException,
            tb: Optional[TracebackType],
        ) -> None:
            assert error_type is InstantiationException
            assert exception.__cause__ is cause
            current = cause.__traceback__
            while current is not None:
                captured.append(current.tb_frame.f_code.co_name)
                current = current.tb_next

        with raises(SystemExit, match="1"), patch("sys.excepthook", new=hook):
            run_and_report(fail)

        assert bool_calls == []
        assert captured == ["omitted", "user_target"]

    @mark.skipif(
        sys.version_info < (3, 11), reason="ExceptionGroup requires Python 3.11"
    )
    @mark.parametrize("remote", [False, True])
    def test_instantiation_exception_group_member_traceback(self, remote: bool) -> None:
        root = Path(__file__).resolve().parent.parent
        member = InstantiationException("nested failure")
        member.__traceback__ = _deserialize_traceback(
            [
                (str(root / "tests/test_utils.py"), "user_nested", 1),
                (
                    str(root / "hydra/_internal/instantiate/_instantiate2.py"),
                    "instantiate",
                    476,
                ),
            ]
        )
        group_type = getattr(builtins, "ExceptionGroup")
        group = group_type("target failures", [member])
        error = InstantiationException("outer failure")
        error.__cause__ = group
        error.__traceback__ = _deserialize_traceback(
            [
                (str(root / "hydra/core/utils.py"), "_run_job", 208),
                (str(root / "tests/test_utils.py"), "user_task", 1),
            ]
        )
        if remote:
            job_return = JobReturn(status=JobStatus.FAILED)
            job_return.return_value = error
            job_return._remote_traceback = _serialize_traceback(error.__traceback__)
            job_return._remote_exception_chain = _serialize_exception_chain(error)
            restored = pickle.loads(pickle.dumps(job_return))  # nosec B301: trusted test data
            with raises(InstantiationException) as exc_info:
                restored.return_value
            error = exc_info.value

        def fail() -> None:
            raise error

        mock_stderr = io.StringIO()
        with raises(SystemExit, match="1"), patch("sys.stderr", new=mock_stderr):
            run_and_report(fail)

        output = mock_stderr.getvalue()
        assert "in user_task" in output
        assert "in user_nested" in output
        assert "_instantiate2.py" not in output

    @mark.parametrize(
        "demo_func, expected_traceback_regex",
        [
            param(
                DemoFunctions.simple_error,
                dedent(r"""
                    Traceback \(most recent call last\):
                      File "[^"]+", line \d+, in run_and_report
                        return func\(\)(
                               \^+)?
                      File "[^"]+", line \d+, in simple_error
                        assert False, "simple_err_msg"
                    AssertionError: simple_err_msg
                    assert False
                    """).strip(),
                id="simple_failure_full_traceback",
            ),
            param(
                DemoFunctions.run_job_wrapper,
                dedent(r"""
                    Traceback \(most recent call last\):
                      File "[^"]+", line \d+, in nested_error
                        assert False, "nested_err"
                    AssertionError: nested_err
                    assert False
                    """).strip(),
                id="strip_run_job_from_top_of_stack",
            ),
            param(
                DemoFunctions.omegaconf_job_wrapper,
                dedent(r"""
                    Traceback \(most recent call last\):
                      File "[^"]+", line \d+, in job_calling_omconf
                        OmegaConf.resolve\(123\)  # type: ignore(\n    [~\^]+)?
                    ValueError: Invalid config type \(int\), expected an OmegaConf Container
                    """).strip(),
                id="strip_omegaconf_from_bottom_of_stack",
            ),
        ],
    )
    def test_failure(self, demo_func: Any, expected_traceback_regex: str) -> None:
        mock_stderr = io.StringIO()
        with (
            raises(SystemExit, match="1"),
            patch("sys.excepthook", new=sys.__excepthook__),
            patch("sys.stderr", new=mock_stderr),
        ):
            run_and_report(demo_func)
        mock_stderr.seek(0)
        stderr_output = mock_stderr.read()
        assert_multiline_regex_search(expected_traceback_regex, stderr_output)

    @mark.parametrize(
        "demo_func,expected_frames",
        [
            param(
                DemoFunctions.run_job_wrapper,
                ["nested_error"],
                id="strip_run_job_from_top_of_stack",
            ),
            param(
                DemoFunctions.omegaconf_job_wrapper,
                ["job_calling_omconf"],
                id="strip_omegaconf_from_bottom_of_stack",
            ),
        ],
    )
    def test_custom_excepthook_receives_sanitized_traceback(
        self, demo_func: Any, expected_frames: list[str]
    ) -> None:
        captured: list[tuple[type[BaseException], BaseException, TracebackType]] = []

        def custom_excepthook(
            exception_type: type[BaseException],
            exception: BaseException,
            tb: TracebackType,
        ) -> None:
            captured.append((exception_type, exception, tb))

        with (
            raises(SystemExit, match="1"),
            patch("sys.excepthook", new=custom_excepthook),
        ):
            run_and_report(demo_func)

        assert len(captured) == 1
        exception_type, exception, tb = captured[0]
        assert exception_type is type(exception)

        frames = []
        current_tb: Optional[TracebackType] = tb
        while current_tb is not None:
            frames.append(current_tb.tb_frame.f_code.co_name)
            current_tb = current_tb.tb_next
        assert frames == expected_frames

    def test_custom_excepthook_failure_uses_default_renderer(self) -> None:
        def broken_excepthook(*args: Any) -> NoReturn:
            raise RuntimeError("hook failed")

        mock_stderr = io.StringIO()
        with (
            raises(SystemExit, match="1"),
            patch("sys.excepthook", new=broken_excepthook),
            patch("sys.stderr", new=mock_stderr),
        ):
            run_and_report(self.DemoFunctions.run_job_wrapper)

        assert "AssertionError: nested_err" in mock_stderr.getvalue()

    def test_simplified_traceback_with_no_module(self) -> None:
        """
        Test that simplified traceback logic can succeed even if
        `inspect.getmodule(frame)` returns `None` for one of
        the frames in the stacktrace.
        """
        demo_func = self.DemoFunctions.run_job_wrapper
        expected_traceback_regex = dedent(r"""
            Traceback \(most recent call last\):$
              File "[^"]+", line \d+, in nested_error$
                assert False, "nested_err"$
            AssertionError: nested_err$
            assert False$
            """)
        mock_stderr = io.StringIO()
        with (
            raises(SystemExit, match="1"),
            patch("sys.excepthook", new=sys.__excepthook__),
            patch("sys.stderr", new=mock_stderr),
        ):
            # Patch `inspect.getmodule` so that it will return None. This simulates a
            # situation where a python module cannot be identified from a traceback
            # stack frame. This can occur when python extension modules or
            # multithreading are involved.
            with patch("inspect.getmodule", new=lambda *args: None):
                run_and_report(demo_func)
        mock_stderr.seek(0)
        stderr_output = mock_stderr.read()
        assert_regex_match(expected_traceback_regex, stderr_output)

    def test_simplified_traceback_failure(self) -> None:
        """
        Test that a warning is printed and the original exception is re-raised
        when an exception occurs during the simplified traceback logic.
        """
        demo_func = self.DemoFunctions.run_job_wrapper

        def throws(*args: Any, **kwargs: Any) -> NoReturn:
            assert False, "Error thrown"

        expected_traceback_regex = dedent(r"""
            An error occurred during Hydra's exception formatting:$
            AssertionError\(.*Error thrown.*\)$
            """)
        mock_stderr = io.StringIO()
        with (
            raises(AssertionError, match="nested_err"),
            patch("sys.excepthook", new=sys.__excepthook__),
            patch("sys.stderr", new=mock_stderr),
        ):
            # patch `traceback.print_exception` so that an exception will occur
            # in the simplified traceback logic:
            with patch("traceback.print_exception", new=throws):
                run_and_report(demo_func)
        mock_stderr.seek(0)
        stderr_output = mock_stderr.read()
        assert_regex_match(expected_traceback_regex, stderr_output)

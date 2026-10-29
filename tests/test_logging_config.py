# SPDX-FileCopyrightText: Contributors to Hydra
# SPDX-License-Identifier: MIT

import inspect
import logging
import logging.config
import logging.handlers
import os
import queue
import sys
import types
import warnings
from functools import partial
from pathlib import Path
from typing import Any, Generator, cast

from omegaconf import DictConfig, OmegaConf
from pytest import (
    CaptureFixture,
    MonkeyPatch,
    fixture,
    importorskip,
    mark,
    raises,
    warns,
)

from hydra import main
from hydra._internal import execution_policy
from hydra._internal.execution_policy import (
    UNSAFE_DISABLE_EXECUTION_CHECKS,
    _get_active_execution_whitelist,
)
from hydra._internal.logging_config import HydraDictConfigurator
from hydra.core.utils import configure_log
from hydra.errors import InstantiationException
from hydra.utils import execution_whitelist


class CustomHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        pass


class CustomFormatter(logging.Formatter):
    pass


class CustomFilter(logging.Filter):
    pass


def logging_function_target(*, marker: str = "original") -> None:
    pass


def function_factory() -> Any:
    return logging_function_target


class CallableHandler(logging.Handler):
    configured = False

    def __call__(self) -> None:
        pass

    def setLevel(self, level: int | str) -> None:
        type(self).configured = True
        super().setLevel(level)

    def emit(self, record: logging.LogRecord) -> None:
        pass


class SubstitutingHandlerMeta(type):
    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        return CallableHandler()


class SubstitutingHandler(logging.Handler, metaclass=SubstitutingHandlerMeta):
    def emit(self, record: logging.LogRecord) -> None:
        pass


class UnlistedQueueListener(logging.handlers.QueueListener):
    invoked = False

    def __init__(
        self,
        queue: Any,
        *handlers: logging.Handler,
        respect_handler_level: bool = False,
    ) -> None:
        type(self).invoked = True
        super().__init__(queue, *handlers, respect_handler_level=respect_handler_level)


class CallableQueue(queue.Queue[Any]):
    def __call__(self) -> None:
        pass


def callable_queue_factory() -> CallableQueue:
    return CallableQueue()


class CallableQueueListener(logging.handlers.QueueListener):
    def __call__(self) -> None:
        pass


class SubstitutingQueueListenerMeta(type):
    def __call__(self, *args: Any, **kwargs: Any) -> CallableQueueListener:
        return CallableQueueListener(*args, **kwargs)


class SubstitutingQueueListener(
    logging.handlers.QueueListener, metaclass=SubstitutingQueueListenerMeta
):
    pass


def callable_queue_listener_factory(
    work_queue: Any,
    *handlers: logging.Handler,
    respect_handler_level: bool = False,
) -> CallableQueueListener:
    return CallableQueueListener(
        work_queue, *handlers, respect_handler_level=respect_handler_level
    )


@fixture(autouse=True)
def restore_root_logger() -> Generator[None, None, None]:
    root = logging.getLogger()
    handlers = root.handlers[:]
    filters = root.filters[:]
    level = root.level
    disabled = root.disabled
    try:
        yield
    finally:
        for handler in root.handlers:
            if handler not in handlers:
                handler.close()
        root.handlers = handlers
        root.filters = filters
        root.setLevel(level)
        root.disabled = disabled


def _logging_config(handler: dict[str, Any]) -> DictConfig:
    return OmegaConf.create(
        {
            "version": 1,
            "handlers": {"test": handler},
            "root": {"handlers": ["test"]},
            "disable_existing_loggers": False,
        }
    )


def _root_cause(error: BaseException) -> BaseException:
    while error.__cause__ is not None:
        error = error.__cause__
    return error


def test_logging_blacklist_rejects_custom_factory_rce() -> None:
    config = _logging_config({"()": "subprocess.Popen", "args": ["must-not-execute"]})

    with raises(ValueError, match="Unable to configure handler") as exc_info:
        configure_log(config)

    cause = _root_cause(exc_info.value)
    assert isinstance(cause, InstantiationException)
    assert "Target 'subprocess.Popen' is blacklisted" in str(cause)


def test_logging_blacklist_rejects_handler_class_rce() -> None:
    config = _logging_config(
        {"class": "subprocess.Popen", "args": ["must-not-execute"]}
    )

    with raises(ValueError, match="Unable to configure handler") as exc_info:
        configure_log(config)

    cause = _root_cause(exc_info.value)
    assert isinstance(cause, InstantiationException)
    assert "Target 'subprocess.Popen' is blacklisted" in str(cause)


@mark.parametrize(
    "target",
    [
        "builtins.locals",
        "builtins.vars",
        "sys.exc_info",
        "types.GetSetDescriptorType.__get__",
    ],
)
def test_logging_whitelist_cannot_authorize_runtime_capability(target: str) -> None:
    config = _logging_config({"()": target})

    with execution_whitelist(target):
        with raises(ValueError, match="Unable to configure handler") as exc_info:
            configure_log(config)

    cause = _root_cause(exc_info.value)
    assert isinstance(cause, InstantiationException)
    assert "cannot be authorized" in str(cause)


def test_logging_whitelist_rejects_unlisted_factory() -> None:
    config = _logging_config({"()": "tests.test_logging_config.CustomHandler"})

    with execution_whitelist([]):
        with raises(ValueError, match="Unable to configure handler") as exc_info:
            configure_log(config)

    assert "Logging target 'tests.test_logging_config.CustomHandler'" in str(
        exc_info.value
    )
    assert "is not in the Hydra execution whitelist" in str(exc_info.value)
    cause = _root_cause(exc_info.value)
    assert isinstance(cause, InstantiationException)
    message = str(cause)
    assert "Logging target 'tests.test_logging_config.CustomHandler'" in message
    assert "is not in the Hydra execution whitelist" in message
    assert "execution_whitelist= on @hydra.main()" in message
    assert "hydra.utils.execution_whitelist()" in message
    assert "advanced/execution_whitelist/" in message


def test_logging_whitelist_allows_custom_factory() -> None:
    config = _logging_config({"()": "tests.test_logging_config.CustomHandler"})

    with execution_whitelist("tests.test_logging_config.CustomHandler"):
        configure_log(config)

    assert isinstance(logging.getLogger().handlers[0], CustomHandler)


def test_logging_rejects_internal_policy_reference() -> None:
    target = "hydra._internal.execution_policy._capture_execution_policy"
    config = _logging_config({"()": target})

    with execution_whitelist(target):
        with raises(ValueError, match="implementation state"):
            configure_log(config)


def test_logging_policy_integrity_mismatch_fails_closed(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setattr(execution_policy, "LEGACY_EXECUTION_TARGETS", frozenset())

    with raises(InstantiationException, match="integrity"):
        configure_log(_logging_config({"class": "logging.StreamHandler"}))


def test_logging_properties_cannot_mutate_function_code() -> None:
    original = logging_function_target.__kwdefaults__
    config = OmegaConf.create(
        {
            "version": 1,
            "formatters": {
                "test": {
                    "()": "tests.test_logging_config.function_factory",
                    ".": {"__kwdefaults__": {"marker": "mutated"}},
                }
            },
            "handlers": {
                "test": {"class": "logging.StreamHandler", "formatter": "test"}
            },
            "root": {"handlers": ["test"]},
        }
    )

    with execution_whitelist(
        [
            "tests.test_logging_config.function_factory",
            "tests.test_logging_config.logging_function_target",
        ]
    ):
        with raises(ValueError, match="cannot modify Python functions"):
            configure_log(config)

    assert logging_function_target.__kwdefaults__ is original


@mark.parametrize(
    ("alias", "module", "attribute", "message"),
    [
        (
            "tests.test_logging_config.inspect",
            inspect,
            "getmembers",
            "cannot be authorized",
        ),
        ("tests.test_logging_config.types", types, "SimpleNamespace", "cannot modify"),
    ],
)
def test_logging_discovery_cannot_expose_or_mutate_module(
    alias: str, module: types.ModuleType, attribute: str, message: str
) -> None:
    original = getattr(module, attribute)
    config = OmegaConf.create(
        {
            "version": 1,
            "formatters": {
                "test": {
                    "()": "hydra.utils.get_object",
                    "path": alias,
                    ".": {attribute: "mutated"},
                }
            },
            "handlers": {
                "test": {"class": "logging.StreamHandler", "formatter": "test"}
            },
            "root": {"handlers": ["test"]},
        }
    )

    with execution_whitelist(["hydra.utils.get_object", alias]):
        with raises(ValueError, match="Unable to configure formatter") as exc_info:
            configure_log(config)

    cause = _root_cause(exc_info.value)
    assert isinstance(cause, InstantiationException)
    assert message in str(cause)
    assert getattr(module, attribute) is original


def test_logging_handler_factory_cannot_return_function() -> None:
    config = _logging_config({"()": "tests.test_logging_config.function_factory"})

    with execution_whitelist(
        [
            "tests.test_logging_config.function_factory",
            "tests.test_logging_config.logging_function_target",
        ]
    ):
        with raises(ValueError, match="Unable to configure handler") as exc_info:
            configure_log(config)

    cause = _root_cause(exc_info.value)
    assert isinstance(cause, TypeError)
    assert "must return a logging.Handler instance" in str(cause)
    assert not hasattr(logging_function_target, "name")


def test_logging_handler_class_result_uses_execution_whitelist() -> None:
    CallableHandler.configured = False
    config = _logging_config(
        {"class": "tests.test_logging_config.SubstitutingHandler", "level": "INFO"}
    )

    with execution_whitelist("tests.test_logging_config.SubstitutingHandler"):
        with raises(ValueError, match="Unable to configure handler") as exc_info:
            configure_log(config)

    cause = _root_cause(exc_info.value)
    assert isinstance(cause, InstantiationException)
    assert "CallableHandler" in str(cause)
    assert not CallableHandler.configured


def test_logging_factory_invocation_uses_argument_checks() -> None:
    config = _logging_config(
        {"()": "unittest.mock.NonCallableMock", "return_value": "unsafe"}
    )

    with execution_whitelist("unittest.mock.NonCallableMock"):
        with raises(ValueError, match="Unable to configure handler") as exc_info:
            configure_log(config)

    cause = _root_cause(exc_info.value)
    assert isinstance(cause, InstantiationException)
    assert "unsafe parameters: return_value" in str(cause)


def test_logging_handler_class_invocation_uses_argument_checks() -> None:
    config = _logging_config(
        {"class": "unittest.mock.NonCallableMock", "return_value": "unsafe"}
    )

    with execution_whitelist("unittest.mock.NonCallableMock"):
        with raises(ValueError, match="Unable to configure handler") as exc_info:
            configure_log(config)

    cause = _root_cause(exc_info.value)
    assert isinstance(cause, InstantiationException)
    assert "unsafe parameters: return_value" in str(cause)


def test_logging_handler_class_is_resolved_once() -> None:
    payload_executed = False

    def payload(*args: object, **kwargs: object) -> logging.Handler:
        nonlocal payload_executed
        payload_executed = True
        return logging.StreamHandler()

    class AlternatingModule(types.ModuleType):
        lookups = 0

        def __getattr__(self, name: str) -> object:
            if name != "Handler":
                raise AttributeError(name)
            self.lookups += 1
            return logging.StreamHandler if self.lookups == 1 else payload

    module_name = "hydra_logging_alternating_handler_test"
    module = AlternatingModule(module_name)
    sys.modules[module_name] = module
    try:
        config = _logging_config({"class": f"{module_name}.Handler"})
        with execution_whitelist(f"{module_name}.Handler"):
            configure_log(config)
    finally:
        del sys.modules[module_name]

    assert module.lookups == 1
    assert not payload_executed


def test_logging_whitelist_allows_builtin_defaults() -> None:
    config = _logging_config(
        {"class": "logging.StreamHandler", "stream": "ext://sys.stdout"}
    )

    with execution_whitelist([]):
        configure_log(config)

    assert isinstance(logging.getLogger().handlers[0], logging.StreamHandler)


def test_logging_whitelist_allows_colorlog_plugin() -> None:
    colorlog = importorskip("colorlog")
    config = OmegaConf.create(
        {
            "version": 1,
            "formatters": {"color": {"()": "colorlog.ColoredFormatter"}},
            "handlers": {
                "test": {"class": "logging.StreamHandler", "formatter": "color"}
            },
            "root": {"handlers": ["test"]},
            "disable_existing_loggers": False,
        }
    )

    with execution_whitelist([]):
        configure_log(config)

    formatter = logging.getLogger().handlers[0].formatter
    assert isinstance(formatter, colorlog.ColoredFormatter)


def test_logging_formatter_class_uses_execution_whitelist() -> None:
    config = OmegaConf.create(
        {
            "version": 1,
            "formatters": {
                "test": {"class": "tests.test_logging_config.CustomFormatter"}
            },
            "handlers": {
                "test": {"class": "logging.StreamHandler", "formatter": "test"}
            },
            "root": {"handlers": ["test"]},
            "disable_existing_loggers": False,
        }
    )

    with execution_whitelist([]):
        with raises(ValueError, match="Unable to configure formatter") as exc_info:
            configure_log(config)

    cause = _root_cause(exc_info.value)
    assert isinstance(cause, InstantiationException)
    assert "CustomFormatter" in str(cause)


def test_logging_brace_format_style_is_permanently_blocked() -> None:
    config = OmegaConf.create(
        {
            "version": 1,
            "formatters": {
                "test": {"format": "{message}", "style": "{"},
            },
            "handlers": {
                "test": {"class": "logging.StreamHandler", "formatter": "test"}
            },
            "root": {"handlers": ["test"]},
            "disable_existing_loggers": False,
        }
    )

    with execution_whitelist([]):
        with raises(ValueError, match="Unable to configure formatter") as exc_info:
            configure_log(config)

    cause = _root_cause(exc_info.value)
    assert isinstance(cause, InstantiationException)
    assert "cannot be selected by declarative configuration" in str(cause)


@mark.parametrize(
    "formatter",
    [
        {"()": "logging.Formatter", "format": "{message}", "style": "{"},
        {"class": "logging.Formatter", "format": "{message}", "style": "{"},
    ],
)
def test_logging_brace_format_style_is_blocked_for_custom_routes(
    formatter: dict[str, Any],
) -> None:
    config = OmegaConf.create(
        {
            "version": 1,
            "formatters": {"test": formatter},
            "handlers": {
                "test": {"class": "logging.StreamHandler", "formatter": "test"}
            },
            "root": {"handlers": ["test"]},
            "disable_existing_loggers": False,
        }
    )

    with execution_whitelist([]):
        with raises(ValueError, match="Unable to configure formatter") as exc_info:
            configure_log(config)

    cause = _root_cause(exc_info.value)
    assert isinstance(cause, InstantiationException)
    assert "cannot be selected by declarative configuration" in str(cause)


def test_logging_str_format_style_factory_is_permanently_blocked() -> None:
    config = OmegaConf.create(
        {
            "version": 1,
            "formatters": {
                "test": {
                    "()": "logging.StrFormatStyle",
                    "fmt": "{message.__class__}",
                }
            },
            "handlers": {
                "test": {"class": "logging.StreamHandler", "formatter": "test"}
            },
            "root": {"handlers": ["test"]},
            "disable_existing_loggers": False,
        }
    )

    with execution_whitelist("logging.*"):
        with raises(ValueError, match="Unable to configure formatter") as exc_info:
            configure_log(config)

    cause = _root_cause(exc_info.value)
    assert isinstance(cause, InstantiationException)
    assert "logging.StrFormatStyle" in str(cause)
    assert "cannot be authorized" in str(cause)


def test_logging_drops_non_formatter_factory_result(
    monkeypatch: MonkeyPatch, capsys: CaptureFixture[str]
) -> None:
    monkeypatch.setenv("HYDRA_SECURITY_PROBE", "sentinel-secret")
    config = OmegaConf.create(
        {
            "version": 1,
            "formatters": {
                "test": {
                    "()": "builtins.str",
                    "object": ("{0.msg.__globals__[os].environ[HYDRA_SECURITY_PROBE]}"),
                }
            },
            "handlers": {
                "test": {"class": "logging.StreamHandler", "formatter": "test"}
            },
            "root": {"level": "INFO", "handlers": ["test"]},
            "disable_existing_loggers": False,
        }
    )

    with (
        execution_whitelist("builtins.str"),
        warns(
            UserWarning,
            match="returned str instead of logging.Formatter; ignoring",
        ),
    ):
        configure_log(config)

    handler = logging.getLogger().handlers[0]
    assert handler.formatter is None
    logging.getLogger().info(test_logging_drops_non_formatter_factory_result)
    assert "sentinel-secret" not in capsys.readouterr().err


def test_logging_drops_non_formatter_class_result(
    monkeypatch: MonkeyPatch, capsys: CaptureFixture[str]
) -> None:
    monkeypatch.setenv("HYDRA_SECURITY_PROBE", "sentinel-secret")
    config = OmegaConf.create(
        {
            "version": 1,
            "formatters": {
                "test": {
                    "class": "builtins.str",
                    "format": b"{0.msg.__globals__[os].environ[HYDRA_SECURITY_PROBE]}",
                    "datefmt": "utf-8",
                    "style": "strict",
                },
            },
            "handlers": {
                "test": {"class": "logging.StreamHandler", "formatter": "test"}
            },
            "root": {"level": "INFO", "handlers": ["test"]},
            "disable_existing_loggers": False,
        }
    )

    with (
        execution_whitelist("builtins.str"),
        warns(
            UserWarning,
            match="returned str instead of logging.Formatter; ignoring",
        ),
    ):
        configure_log(config)

    handler = logging.getLogger().handlers[0]
    assert handler.formatter is None
    logging.getLogger().info(test_logging_drops_non_formatter_class_result)
    assert "sentinel-secret" not in capsys.readouterr().err


@mark.parametrize(
    "formatter",
    [
        {"()": "builtins.str", "object": "safe"},
        {
            "class": "builtins.str",
            "format": b"safe",
            "datefmt": "utf-8",
            "style": "strict",
        },
    ],
)
def test_unsafe_disable_allows_non_formatter_result(
    formatter: dict[str, Any],
) -> None:
    config = OmegaConf.create(
        {
            "version": 1,
            "formatters": {"test": formatter},
            "handlers": {
                "test": {"class": "logging.StreamHandler", "formatter": "test"}
            },
            "root": {"handlers": ["test"]},
            "disable_existing_loggers": False,
        }
    )

    with execution_whitelist(UNSAFE_DISABLE_EXECUTION_CHECKS):
        configure_log(config)

    assert logging.getLogger().handlers[0].formatter == "safe"


@mark.parametrize(
    ("style", "fmt"),
    [("%", "%(message)s"), ("$", "$message")],
)
def test_logging_non_traversing_format_styles_remain_available(
    style: str, fmt: str
) -> None:
    config = OmegaConf.create(
        {
            "version": 1,
            "formatters": {"test": {"format": fmt, "style": style}},
            "handlers": {
                "test": {"class": "logging.StreamHandler", "formatter": "test"}
            },
            "root": {"handlers": ["test"]},
            "disable_existing_loggers": False,
        }
    )

    with execution_whitelist([]):
        configure_log(config)

    formatter = logging.getLogger().handlers[0].formatter
    assert formatter is not None
    assert formatter._style._fmt == fmt


def test_unsafe_disable_execution_checks_allows_brace_format_style() -> None:
    config = OmegaConf.create(
        {
            "version": 1,
            "formatters": {
                "test": {"format": "{message}", "style": "{"},
            },
            "handlers": {
                "test": {"class": "logging.StreamHandler", "formatter": "test"}
            },
            "root": {"handlers": ["test"]},
            "disable_existing_loggers": False,
        }
    )

    with execution_whitelist(UNSAFE_DISABLE_EXECUTION_CHECKS):
        configure_log(config)

    formatter = logging.getLogger().handlers[0].formatter
    assert formatter is not None
    assert formatter._style._fmt == "{message}"


def test_logging_formatter_class_is_resolved_once() -> None:
    payload_executed = False

    def payload(*args: object, **kwargs: object) -> logging.Formatter:
        nonlocal payload_executed
        payload_executed = True
        return logging.Formatter()

    class AlternatingModule(types.ModuleType):
        lookups = 0

        def __getattr__(self, name: str) -> object:
            if name != "Formatter":
                raise AttributeError(name)
            self.lookups += 1
            return CustomFormatter if self.lookups == 1 else payload

    module_name = "hydra_logging_alternating_test"
    module = AlternatingModule(module_name)
    sys.modules[module_name] = module
    try:
        config = OmegaConf.create(
            {
                "version": 1,
                "formatters": {"test": {"class": f"{module_name}.Formatter"}},
                "handlers": {
                    "test": {
                        "class": "logging.StreamHandler",
                        "formatter": "test",
                    }
                },
                "root": {"handlers": ["test"]},
            }
        )

        with execution_whitelist(f"{module_name}.Formatter"):
            configure_log(config)
    finally:
        del sys.modules[module_name]

    assert module.lookups == 1
    assert not payload_executed


def test_logging_filter_factory_uses_execution_whitelist() -> None:
    config = OmegaConf.create(
        {
            "version": 1,
            "filters": {"test": {"()": "tests.test_logging_config.CustomFilter"}},
            "handlers": {
                "test": {"class": "logging.StreamHandler", "filters": ["test"]}
            },
            "root": {"handlers": ["test"]},
            "disable_existing_loggers": False,
        }
    )

    with execution_whitelist("tests.test_logging_config.CustomFilter"):
        configure_log(config)

    assert isinstance(logging.getLogger().handlers[0].filters[0], CustomFilter)


@mark.skipif(
    sys.version_info < (3, 12),
    reason="dictConfig queue listener factories require Python 3.12 or newer",
)
def test_logging_discovery_factory_result_uses_execution_whitelist() -> None:
    UnlistedQueueListener.invoked = False
    config = OmegaConf.create(
        {
            "version": 1,
            "handlers": {
                "sink": {"class": "logging.StreamHandler"},
                "queue": {
                    "class": "logging.handlers.QueueHandler",
                    "handlers": ["sink"],
                    "listener": {
                        "()": "hydra.utils.get_object",
                        "path": "tests.test_logging_config.UnlistedQueueListener",
                    },
                },
            },
            "root": {"handlers": ["queue"]},
        }
    )

    with execution_whitelist(
        ["logging.handlers.QueueHandler", "hydra.utils.get_object"]
    ):
        with raises(ValueError, match="Unable to configure handler") as exc_info:
            configure_log(config)

    cause = _root_cause(exc_info.value)
    assert isinstance(cause, InstantiationException)
    assert "UnlistedQueueListener" in str(cause)
    assert not UnlistedQueueListener.invoked


@mark.skipif(
    sys.version_info < (3, 12),
    reason="dictConfig queue factories require Python 3.12 or newer",
)
def test_logging_queue_factory_result_uses_execution_whitelist() -> None:
    config = _logging_config(
        {
            "class": "logging.handlers.QueueHandler",
            "queue": "tests.test_logging_config.callable_queue_factory",
        }
    )

    with execution_whitelist(
        [
            "logging.handlers.QueueHandler",
            "tests.test_logging_config.callable_queue_factory",
        ]
    ):
        with raises(ValueError, match="Unable to configure handler") as exc_info:
            configure_log(config)

    cause = _root_cause(exc_info.value)
    assert isinstance(cause, InstantiationException)
    assert "CallableQueue" in str(cause)


@mark.skipif(
    sys.version_info < (3, 12),
    reason="dictConfig queue listener factories require Python 3.12 or newer",
)
@mark.parametrize(
    ("listener_factory", "listener_target"),
    [
        (
            "tests.test_logging_config.callable_queue_listener_factory",
            "tests.test_logging_config.callable_queue_listener_factory",
        ),
        (
            SubstitutingQueueListener,
            "tests.test_logging_config.SubstitutingQueueListener",
        ),
    ],
)
def test_logging_queue_listener_result_uses_execution_whitelist(
    listener_factory: Any,
    listener_target: str,
) -> None:
    config = OmegaConf.create(
        {
            "version": 1,
            "handlers": {
                "sink": {"class": "logging.StreamHandler"},
                "queue": {
                    "class": "logging.handlers.QueueHandler",
                    "handlers": ["sink"],
                    "listener": listener_factory,
                },
            },
            "root": {"handlers": ["queue"]},
        },
        flags={"allow_objects": True},
    )

    with execution_whitelist(
        [
            "logging.handlers.QueueHandler",
            listener_target,
        ]
    ):
        with raises(ValueError, match="Unable to configure handler") as exc_info:
            configure_log(config)

    cause = _root_cause(exc_info.value)
    assert isinstance(cause, InstantiationException)
    assert "CallableQueueListener" in str(cause)


def test_logging_ext_value_uses_execution_whitelist() -> None:
    configurator = HydraDictConfigurator({}, ())

    with raises(InstantiationException, match="Logging target 'os.environ'.*not in"):
        configurator.convert("ext://os.environ")


def test_logging_resolved_alias_cannot_hide_non_whitelistable_target() -> None:
    config = _logging_config({"()": "logging.os.system", "command": "must-not-execute"})

    with execution_whitelist("logging.*"):
        with raises(ValueError, match="Unable to configure handler") as exc_info:
            configure_log(config)

    assert "Target 'os.system'" in str(exc_info.value)
    assert "cannot be authorized" in str(exc_info.value)
    cause = _root_cause(exc_info.value)
    assert isinstance(cause, InstantiationException)
    assert "Target 'os.system'" in str(cause)
    assert "cannot be authorized" in str(cause)


def test_logging_cannot_mutate_os_environ(monkeypatch: MonkeyPatch) -> None:
    data: dict[bytes, bytes] = {}
    environ = cast(Any, os._Environ)(  # type: ignore[attr-defined]
        data, os.fsencode, os.fsdecode, os.fsencode, os.fsdecode
    )
    monkeypatch.setattr(
        sys.modules[__name__], "environment_probe", environ, raising=False
    )
    monkeypatch.setattr(os, "putenv", lambda _key, _value: None)
    target = f"{__name__}.environment_probe.update"
    config = _logging_config({"()": target, "HYDRA_SECURITY_TEST": "tampered"})

    with execution_whitelist(target):
        with raises(ValueError, match="Unable to configure handler") as exc_info:
            configure_log(config)

    cause = _root_cause(exc_info.value)
    assert isinstance(cause, InstantiationException)
    assert "cannot modify the process environment" in str(cause)
    assert data == {}


def test_logging_cannot_mutate_os_environ_through_call_wrapper(
    monkeypatch: MonkeyPatch,
) -> None:
    data: dict[bytes, bytes] = {}
    environ = cast(Any, os._Environ)(  # type: ignore[attr-defined]
        data, os.fsencode, os.fsdecode, os.fsencode, os.fsdecode
    )
    monkeypatch.setattr(
        sys.modules[__name__], "environment_probe", environ, raising=False
    )
    monkeypatch.setattr(os, "putenv", lambda _key, _value: None)
    target = f"{__name__}.environment_probe.__setitem__.__call__"
    config = _logging_config({"()": target, "key": "NEW", "value": "tampered"})

    with execution_whitelist([target, "os._Environ.__setitem__"]):
        with raises(ValueError, match="Unable to configure handler") as exc_info:
            configure_log(config)

    cause = _root_cause(exc_info.value)
    assert isinstance(cause, InstantiationException)
    assert "cannot modify the process environment" in str(cause)
    assert data == {}


def test_logging_cannot_mutate_os_environ_through_partial(
    monkeypatch: MonkeyPatch,
) -> None:
    data: dict[bytes, bytes] = {}
    environ = cast(Any, os._Environ)(  # type: ignore[attr-defined]
        data, os.fsencode, os.fsdecode, os.fsencode, os.fsdecode
    )
    monkeypatch.setattr(os, "putenv", lambda _key, _value: None)
    factory = partial(environ.update)
    target = execution_policy._get_resolved_target_name_for_check(factory)
    config = OmegaConf.create(
        {
            "version": 1,
            "handlers": {"test": {"()": factory, "NEW": "tampered"}},
            "root": {"handlers": ["test"]},
            "disable_existing_loggers": False,
        },
        flags={"allow_objects": True},
    )

    with execution_whitelist(target):
        with raises(ValueError, match="Unable to configure handler") as exc_info:
            configure_log(config)

    cause = _root_cause(exc_info.value)
    assert isinstance(cause, InstantiationException)
    assert "cannot modify the process environment" in str(cause)
    assert data == {}


def test_logging_configured_property_cannot_mutate_os_environ(
    monkeypatch: MonkeyPatch,
) -> None:
    data: dict[bytes, bytes] = {}
    environ = cast(Any, os._Environ)(  # type: ignore[attr-defined]
        data, os.fsencode, os.fsdecode, os.fsencode, os.fsdecode
    )
    monkeypatch.setattr(
        sys.modules[__name__], "environment_probe", environ, raising=False
    )
    probe_path = f"{__name__}.environment_probe"
    config = OmegaConf.create(
        {
            "version": 1,
            "filters": {
                "test": {
                    "()": "hydra.utils.get_object",
                    "path": probe_path,
                    ".": {"encodekey": "tampered"},
                }
            },
            "handlers": {
                "test": {"class": "logging.StreamHandler", "filters": ["test"]}
            },
            "root": {"handlers": ["test"]},
            "disable_existing_loggers": False,
        }
    )

    with execution_whitelist(["hydra.utils.get_object", probe_path]):
        with raises(ValueError, match="Unable to configure filter") as exc_info:
            configure_log(config)

    cause = _root_cause(exc_info.value)
    assert isinstance(cause, InstantiationException)
    assert "cannot modify the process environment" in str(cause)
    assert data == {}


def test_logging_cannot_mutate_os_environ_with_keyword_receiver(
    monkeypatch: MonkeyPatch,
) -> None:
    data: dict[bytes, bytes] = {}
    environ = cast(Any, os._Environ)(  # type: ignore[attr-defined]
        data, os.fsencode, os.fsdecode, os.fsencode, os.fsdecode
    )
    monkeypatch.setattr(
        sys.modules[__name__], "environment_probe", environ, raising=False
    )
    monkeypatch.setattr(os, "putenv", lambda _key, _value: None)
    target = "os._Environ.__setitem__"
    probe_path = f"{__name__}.environment_probe"
    config = _logging_config(
        {
            "()": target,
            "self": f"ext://{probe_path}",
            "key": "NEW",
            "value": "tampered",
        }
    )

    with execution_whitelist([target, probe_path]):
        with raises(ValueError, match="Unable to configure handler") as exc_info:
            configure_log(config)

    cause = _root_cause(exc_info.value)
    assert isinstance(cause, InstantiationException)
    assert "cannot modify the process environment" in str(cause)
    assert data == {}


def test_logging_unsafe_disable_execution_checks_is_explicit_escape_hatch() -> None:
    configurator = HydraDictConfigurator({}, UNSAFE_DISABLE_EXECUTION_CHECKS)

    assert configurator.resolve("subprocess.Popen").__name__ == "Popen"


def test_logging_without_whitelist_warns() -> None:
    config = _logging_config({"class": "tests.test_logging_config.CustomHandler"})

    with warns(UserWarning, match="logging without an execution whitelist") as records:
        configure_log(config)

    assert Path(records[0].filename) == Path(__file__)


def test_non_callable_logging_target_without_whitelist_warns() -> None:
    config = _logging_config(
        {"class": "logging.StreamHandler", "stream": "ext://os.environ"}
    )

    with warns(UserWarning, match="logging without an execution whitelist") as records:
        configure_log(config)

    assert Path(records[0].filename) == Path(__file__)


def test_builtin_logging_without_whitelist_does_not_warn() -> None:
    config = _logging_config({"class": "logging.StreamHandler"})

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        configure_log(config)


def test_custom_dict_config_class_is_rejected(monkeypatch: MonkeyPatch) -> None:
    class CustomDictConfigurator(logging.config.DictConfigurator):
        called = False

        def configure(self) -> None:
            type(self).called = True

    monkeypatch.setattr(logging.config, "dictConfigClass", CustomDictConfigurator)

    with raises(ValueError, match="custom logging.config.dictConfigClass"):
        configure_log(_logging_config({"class": "logging.StreamHandler"}))

    assert not CustomDictConfigurator.called


def test_hydra_main_execution_whitelist_applies_to_full_invocation() -> None:
    @main(execution_whitelist="tests.test_logging_config.CustomHandler")
    def app(config: DictConfig) -> Any:
        configure_log(
            _logging_config({"()": "tests.test_logging_config.CustomHandler"})
        )
        return _get_active_execution_whitelist()

    assert app(OmegaConf.create()) == ("tests.test_logging_config.CustomHandler",)
    assert _get_active_execution_whitelist() is None

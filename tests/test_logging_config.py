# SPDX-FileCopyrightText: Contributors to Hydra
# SPDX-License-Identifier: MIT

import logging
import logging.config
import logging.handlers
import subprocess
import sys
import types
from typing import Any, Dict, Generator

from omegaconf import DictConfig, OmegaConf
from pytest import MonkeyPatch, fixture, mark, raises

from hydra._internal.logging_config import HydraDictConfigurator
from hydra.core.utils import configure_log
from hydra.errors import InstantiationException


class CustomHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        pass


class CustomFormatter(logging.Formatter):
    pass


class CustomFilter(logging.Filter):
    pass


def blocked_callable_factory(*args: Any, **kwargs: Any) -> Any:
    return subprocess.Popen


class BlockedCallableHandlerMeta(type):
    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        return subprocess.Popen


class BlockedCallableHandler(logging.Handler, metaclass=BlockedCallableHandlerMeta):
    def emit(self, record: logging.LogRecord) -> None:
        pass


def blocked_queue_factory() -> Any:
    return subprocess.Popen


class BlockedCallableQueueListenerMeta(type):
    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        return subprocess.Popen


class BlockedCallableQueueListener(
    logging.handlers.QueueListener, metaclass=BlockedCallableQueueListenerMeta
):
    pass


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


def _logging_config(handler: Dict[str, Any]) -> DictConfig:
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


def _assert_blocklisted(error: BaseException, target: str) -> None:
    cause = _root_cause(error)
    assert isinstance(cause, InstantiationException)
    assert f"Target '{target}'" in str(cause)
    assert "blocklisted" in str(cause)


def test_logging_blocklist_rejects_custom_factory_rce() -> None:
    config = _logging_config({"()": "subprocess.Popen", "args": ["must-not-execute"]})

    with raises(ValueError, match="Unable to configure handler") as exc_info:
        configure_log(config)

    _assert_blocklisted(exc_info.value, "subprocess.Popen")


def test_logging_blocklist_rejects_handler_class_rce() -> None:
    config = _logging_config(
        {"class": "subprocess.Popen", "args": ["must-not-execute"]}
    )

    with raises(ValueError, match="Unable to configure handler") as exc_info:
        configure_log(config)

    _assert_blocklisted(exc_info.value, "subprocess.Popen")


def test_logging_allows_custom_factory() -> None:
    config = _logging_config({"()": "tests.test_logging_config.CustomHandler"})

    configure_log(config)

    assert isinstance(logging.getLogger().handlers[0], CustomHandler)


def test_logging_factory_result_is_reauthorized() -> None:
    config = _logging_config(
        {"()": "tests.test_logging_config.blocked_callable_factory"}
    )

    with raises(ValueError, match="Unable to configure handler") as exc_info:
        configure_log(config)

    _assert_blocklisted(exc_info.value, "subprocess.Popen")


def test_logging_handler_class_result_is_reauthorized() -> None:
    config = _logging_config(
        {"class": "tests.test_logging_config.BlockedCallableHandler"}
    )

    with raises(ValueError, match="Unable to configure handler") as exc_info:
        configure_log(config)

    _assert_blocklisted(exc_info.value, "subprocess.Popen")


def test_logging_factory_invocation_uses_argument_checks() -> None:
    config = _logging_config(
        {"()": "unittest.mock.NonCallableMock", "return_value": "unsafe"}
    )

    with raises(ValueError, match="Unable to configure handler") as exc_info:
        configure_log(config)

    cause = _root_cause(exc_info.value)
    assert isinstance(cause, InstantiationException)
    assert "unsafe parameters: return_value" in str(cause)


def test_logging_handler_class_invocation_uses_argument_checks() -> None:
    config = _logging_config(
        {"class": "unittest.mock.NonCallableMock", "return_value": "unsafe"}
    )

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
        configure_log(_logging_config({"class": f"{module_name}.Handler"}))
    finally:
        del sys.modules[module_name]

    assert module.lookups == 1
    assert not payload_executed


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
            return logging.Formatter if self.lookups == 1 else payload

    module_name = "hydra_logging_alternating_formatter_test"
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
        configure_log(config)
    finally:
        del sys.modules[module_name]

    assert module.lookups == 1
    assert not payload_executed


def test_logging_custom_formatter_and_filter_work() -> None:
    config = OmegaConf.create(
        {
            "version": 1,
            "formatters": {
                "test": {"class": "tests.test_logging_config.CustomFormatter"}
            },
            "filters": {"test": {"()": "tests.test_logging_config.CustomFilter"}},
            "handlers": {
                "test": {
                    "class": "logging.StreamHandler",
                    "formatter": "test",
                    "filters": ["test"],
                }
            },
            "root": {"handlers": ["test"]},
            "disable_existing_loggers": False,
        }
    )

    configure_log(config)

    handler = logging.getLogger().handlers[0]
    assert isinstance(handler.formatter, CustomFormatter)
    assert isinstance(handler.filters[0], CustomFilter)


def test_logging_discovery_factory_rejects_blocked_result() -> None:
    config = _logging_config(
        {
            "()": "hydra.utils.get_object",
            "path": "subprocess.Popen",
        }
    )

    with raises(ValueError, match="Unable to configure handler") as exc_info:
        configure_log(config)

    _assert_blocklisted(exc_info.value, "subprocess.Popen")


def test_logging_ext_value_uses_blocklist() -> None:
    configurator = HydraDictConfigurator({})

    with raises(InstantiationException, match="Target 'os.system'.*blocklisted"):
        configurator.convert("ext://os.system")


def test_logging_resolved_alias_cannot_hide_blocklisted_target() -> None:
    config = _logging_config({"()": "logging.os.system", "command": "must-not-execute"})

    with raises(ValueError, match="Unable to configure handler") as exc_info:
        configure_log(config)

    _assert_blocklisted(exc_info.value, "os.system")


@mark.skipif(
    sys.version_info < (3, 12),
    reason="dictConfig queue factories require Python 3.12 or newer",
)
def test_logging_queue_factory_result_is_reauthorized() -> None:
    config = _logging_config(
        {
            "class": "logging.handlers.QueueHandler",
            "queue": "tests.test_logging_config.blocked_queue_factory",
        }
    )

    with raises(ValueError, match="Unable to configure handler") as exc_info:
        configure_log(config)

    _assert_blocklisted(exc_info.value, "subprocess.Popen")


@mark.skipif(
    sys.version_info < (3, 12),
    reason="dictConfig queue listeners require Python 3.12 or newer",
)
def test_logging_queue_listener_result_is_reauthorized() -> None:
    config = OmegaConf.create(
        {
            "version": 1,
            "handlers": {
                "sink": {"class": "logging.StreamHandler"},
                "queue": {
                    "class": "logging.handlers.QueueHandler",
                    "handlers": ["sink"],
                    "listener": BlockedCallableQueueListener,
                },
            },
            "root": {"handlers": ["queue"]},
        },
        flags={"allow_objects": True},
    )

    with raises(ValueError, match="Unable to configure handler") as exc_info:
        configure_log(config)

    _assert_blocklisted(exc_info.value, "subprocess.Popen")


def test_builtin_logging_configuration_works() -> None:
    config = _logging_config(
        {"class": "logging.StreamHandler", "stream": "ext://sys.stdout"}
    )

    configure_log(config)

    assert isinstance(logging.getLogger().handlers[0], logging.StreamHandler)


def test_custom_dict_config_class_is_rejected(monkeypatch: MonkeyPatch) -> None:
    class CustomDictConfigurator(logging.config.DictConfigurator):
        called = False

        def configure(self) -> None:
            type(self).called = True

    monkeypatch.setattr(logging.config, "dictConfigClass", CustomDictConfigurator)

    with raises(ValueError, match="custom logging.config.dictConfigClass"):
        configure_log(_logging_config({"class": "logging.StreamHandler"}))

    assert not CustomDictConfigurator.called

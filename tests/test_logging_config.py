# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved

import logging
import logging.config
import logging.handlers
import sys
import types
import warnings
from pathlib import Path
from typing import Any, Generator

from omegaconf import DictConfig, OmegaConf
from pytest import MonkeyPatch, fixture, importorskip, mark, raises, warns

from hydra import main
from hydra._internal.logging_config import HydraDictConfigurator
from hydra._internal.target_policy import (
    UNSAFE_ALLOW_ALL_TARGETS,
    _get_active_target_whitelist,
)
from hydra.core.utils import configure_log
from hydra.errors import InstantiationException
from hydra.utils import target_whitelist


class CustomHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        pass


class CustomFormatter(logging.Formatter):
    pass


class CustomFilter(logging.Filter):
    pass


class CallableHandler(logging.Handler):
    def __call__(self) -> None:
        pass

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


def test_logging_blocklist_rejects_custom_factory_rce() -> None:
    config = _logging_config({"()": "subprocess.Popen", "args": ["must-not-execute"]})

    with raises(ValueError, match="Unable to configure handler") as exc_info:
        configure_log(config)

    cause = _root_cause(exc_info.value)
    assert isinstance(cause, InstantiationException)
    assert "Target 'subprocess.Popen' is blocklisted" in str(cause)


def test_logging_blocklist_rejects_handler_class_rce() -> None:
    config = _logging_config(
        {"class": "subprocess.Popen", "args": ["must-not-execute"]}
    )

    with raises(ValueError, match="Unable to configure handler") as exc_info:
        configure_log(config)

    cause = _root_cause(exc_info.value)
    assert isinstance(cause, InstantiationException)
    assert "Target 'subprocess.Popen' is blocklisted" in str(cause)


def test_logging_whitelist_rejects_unlisted_factory() -> None:
    config = _logging_config({"()": "tests.test_logging_config.CustomHandler"})

    with target_whitelist([]):
        with raises(ValueError, match="Unable to configure handler") as exc_info:
            configure_log(config)

    cause = _root_cause(exc_info.value)
    assert isinstance(cause, InstantiationException)
    message = str(cause)
    assert "Logging target 'tests.test_logging_config.CustomHandler'" in message
    assert "is not in the Hydra target whitelist" in message
    assert "target_whitelist= on @hydra.main()" in message
    assert "hydra.utils.target_whitelist()" in message
    assert "instantiate_target_whitelist/" in message


def test_logging_whitelist_allows_custom_factory() -> None:
    config = _logging_config({"()": "tests.test_logging_config.CustomHandler"})

    with target_whitelist("tests.test_logging_config.CustomHandler"):
        configure_log(config)

    assert isinstance(logging.getLogger().handlers[0], CustomHandler)


def test_logging_handler_class_result_uses_target_whitelist() -> None:
    config = _logging_config({"class": "tests.test_logging_config.SubstitutingHandler"})

    with target_whitelist("tests.test_logging_config.SubstitutingHandler"):
        with raises(ValueError, match="Unable to configure handler") as exc_info:
            configure_log(config)

    cause = _root_cause(exc_info.value)
    assert isinstance(cause, InstantiationException)
    assert "CallableHandler" in str(cause)


def test_logging_factory_invocation_uses_argument_checks() -> None:
    config = _logging_config(
        {"()": "unittest.mock.NonCallableMock", "return_value": "unsafe"}
    )

    with target_whitelist("unittest.mock.NonCallableMock"):
        with raises(ValueError, match="Unable to configure handler") as exc_info:
            configure_log(config)

    cause = _root_cause(exc_info.value)
    assert isinstance(cause, InstantiationException)
    assert "unsafe parameters: return_value" in str(cause)


def test_logging_whitelist_allows_builtin_defaults() -> None:
    config = _logging_config(
        {"class": "logging.StreamHandler", "stream": "ext://sys.stdout"}
    )

    with target_whitelist([]):
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

    with target_whitelist([]):
        configure_log(config)

    formatter = logging.getLogger().handlers[0].formatter
    assert isinstance(formatter, colorlog.ColoredFormatter)


def test_logging_formatter_class_uses_target_whitelist() -> None:
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

    with target_whitelist([]):
        with raises(ValueError, match="Unable to configure formatter") as exc_info:
            configure_log(config)

    cause = _root_cause(exc_info.value)
    assert isinstance(cause, InstantiationException)
    assert "CustomFormatter" in str(cause)


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

        with target_whitelist(f"{module_name}.Formatter"):
            configure_log(config)
    finally:
        del sys.modules[module_name]

    assert module.lookups == 1
    assert not payload_executed


def test_logging_filter_factory_uses_target_whitelist() -> None:
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

    with target_whitelist("tests.test_logging_config.CustomFilter"):
        configure_log(config)

    assert isinstance(logging.getLogger().handlers[0].filters[0], CustomFilter)


@mark.skipif(
    sys.version_info < (3, 12),
    reason="dictConfig queue listener factories require Python 3.12 or newer",
)
def test_logging_discovery_factory_result_uses_target_whitelist() -> None:
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

    with target_whitelist(["logging.handlers.QueueHandler", "hydra.utils.get_object"]):
        with raises(ValueError, match="Unable to configure handler") as exc_info:
            configure_log(config)

    cause = _root_cause(exc_info.value)
    assert isinstance(cause, InstantiationException)
    assert "UnlistedQueueListener" in str(cause)
    assert not UnlistedQueueListener.invoked


def test_logging_ext_value_uses_target_whitelist() -> None:
    configurator = HydraDictConfigurator({}, ())

    with raises(InstantiationException, match="Logging target 'os.environ'.*not in"):
        configurator.convert("ext://os.environ")


def test_logging_resolved_alias_cannot_hide_non_whitelistable_target() -> None:
    config = _logging_config({"()": "logging.os.system", "command": "must-not-execute"})

    with target_whitelist("logging.*"):
        with raises(ValueError, match="Unable to configure handler") as exc_info:
            configure_log(config)

    cause = _root_cause(exc_info.value)
    assert isinstance(cause, InstantiationException)
    assert "Target 'os.system'" in str(cause)
    assert "cannot be authorized" in str(cause)


def test_logging_unsafe_allow_all_is_explicit_escape_hatch() -> None:
    configurator = HydraDictConfigurator({}, UNSAFE_ALLOW_ALL_TARGETS)

    assert configurator.resolve("subprocess.Popen").__name__ == "Popen"


def test_logging_without_whitelist_warns() -> None:
    config = _logging_config({"class": "tests.test_logging_config.CustomHandler"})

    with warns(UserWarning, match="logging without a target whitelist") as records:
        configure_log(config)

    assert Path(records[0].filename) == Path(__file__)


def test_non_callable_logging_target_without_whitelist_warns() -> None:
    config = _logging_config(
        {"class": "logging.StreamHandler", "stream": "ext://os.environ"}
    )

    with warns(UserWarning, match="logging without a target whitelist") as records:
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


def test_hydra_main_target_whitelist_applies_to_full_invocation() -> None:
    @main(target_whitelist="tests.test_logging_config.CustomHandler")
    def app(config: DictConfig) -> Any:
        configure_log(
            _logging_config({"()": "tests.test_logging_config.CustomHandler"})
        )
        return _get_active_target_whitelist()

    assert app(OmegaConf.create()) == ("tests.test_logging_config.CustomHandler",)
    assert _get_active_target_whitelist() is None

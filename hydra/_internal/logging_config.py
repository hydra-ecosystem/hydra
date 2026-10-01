# SPDX-FileCopyrightText: Contributors to Hydra
# SPDX-License-Identifier: MIT

import inspect
import logging.config
import logging.handlers
import sys
import warnings
from pathlib import Path
from textwrap import dedent
from typing import Any, Callable, cast

from hydra._internal.deprecation_warning import deprecation_warning
from hydra._internal.execution_policy import (
    UNSAFE_DISABLE_EXECUTION_CHECKS,
    ExecutionWhitelist,
    NormalizedExecutionWhitelist,
    _authorize_discovery_path,
    _authorize_resolved_target_identity,
    _authorize_target_invocation,
    _authorize_target_name,
    _combine_execution_whitelists,
    _execution_policy_context,
    _get_os_alias_target,
    _get_resolved_target_name_for_check,
    _mediate_target_result,
    _reject_protected_reference,
    _reject_protected_result,
    _resolve_execution_whitelist,
    _validated_execution_policy,
)
from hydra.errors import InstantiationException

# Hydra's built-in logging configurations must continue to work when an
# application enables a restrictive execution whitelist. Keep this list exact so
# it does not broaden instantiate() authorization or trust a package namespace.
_BUILTIN_LOGGING_TARGETS: tuple[str, ...] = (
    "colorlog.ColoredFormatter",
    "logging.FileHandler",
    "logging.StreamHandler",
    "sys.stderr",
    "sys.stdout",
)


def _resolve_logging_execution_whitelist(
    execution_whitelist: ExecutionWhitelist,
) -> NormalizedExecutionWhitelist:
    resolved = _resolve_execution_whitelist(execution_whitelist)
    if resolved is None or resolved is UNSAFE_DISABLE_EXECUTION_CHECKS:
        return resolved
    return _combine_execution_whitelists(resolved, _BUILTIN_LOGGING_TARGETS)


def _warn_legacy_logging_execution_whitelist() -> None:
    stacklevel = 1
    frame = inspect.currentframe()
    hydra_package = Path(__file__).resolve().parents[1]
    stdlib_logging_config = Path(logging.config.__file__).resolve()
    while frame is not None:
        filename = Path(frame.f_code.co_filename).resolve()
        if not (
            filename.is_relative_to(hydra_package) or filename == stdlib_logging_config
        ):
            break
        stacklevel += 1
        frame = frame.f_back
    deprecation_warning(
        dedent(
            """\
            Hydra configured Python logging without an execution whitelist. This
            preserves legacy behavior but is deprecated because logging
            configuration can select and execute arbitrary Python callables.
            This warning will become an error in Hydra 1.5. Pass execution_whitelist=
            to @hydra.main(), use hydra.utils.execution_whitelist(), or pass
            UNSAFE_DISABLE_EXECUTION_CHECKS to explicitly keep legacy behavior.
            See https://hydra.cc/docs/advanced/execution_whitelist/"""
        ),
        stacklevel=stacklevel,
    )


class HydraDictConfigurator(logging.config.DictConfigurator):
    """Apply Hydra target authorization to Python logging configuration."""

    def __init__(
        self,
        config: dict[str, Any],
        execution_whitelist: NormalizedExecutionWhitelist,
    ) -> None:
        super().__init__(config)
        self._execution_whitelist = execution_whitelist
        self._execution_policy = (
            None
            if execution_whitelist is UNSAFE_DISABLE_EXECUTION_CHECKS
            else _validated_execution_policy(
                "5e70100572e2183db32478e51b32d1edd9b9e1af4a47747d10c7b80b8fadf76e"
            )
        )
        self._resolved_targets: dict[str, Any] = {}
        self._resolved_target_sources: dict[int, str] = {}

    def configure(self) -> None:
        with _execution_policy_context(self._execution_policy):
            super().configure()

    def _authorize_callable(self, target: Any, resolved_from: str) -> str:
        if not callable(target):
            return ""
        if resolved_from:
            target_name = _authorize_resolved_target_identity(
                target,
                resolved_from,
                "hydra.logging",
                self._execution_whitelist,
            )
        else:
            target_name = _get_os_alias_target(
                _get_resolved_target_name_for_check(target)
            )
            _authorize_target_name(
                target_name,
                target_name,
                "hydra.logging",
                self._execution_whitelist,
            )
        if (
            self._execution_whitelist is None
            and target_name not in _BUILTIN_LOGGING_TARGETS
            and resolved_from not in _BUILTIN_LOGGING_TARGETS
        ):
            _warn_legacy_logging_execution_whitelist()
        return target_name

    def _invoke_authorized_callable(
        self,
        target: Callable[..., Any],
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
        resolved_from: str,
    ) -> Any:
        effective_target, effective_args, effective_kwargs = (
            _authorize_target_invocation(
                target,
                args,
                kwargs,
                "hydra.logging",
                self._execution_whitelist,
            )
        )
        discovery_path = _authorize_discovery_path(
            effective_target,
            effective_args,
            effective_kwargs,
            "hydra.logging",
            self._execution_whitelist,
        )
        result = target(*args, **kwargs)
        return _mediate_target_result(
            result,
            discovery_path or resolved_from,
            "hydra.logging",
            self._execution_whitelist,
            discovery_path=discovery_path,
        )

    def resolve(self, s: str) -> Any:
        if s in self._resolved_targets:
            return self._resolved_targets[s]
        _reject_protected_reference(s, "hydra.logging", self._execution_whitelist)
        _authorize_target_name(s, s, "hydra.logging", self._execution_whitelist)
        result = super().resolve(s)
        _reject_protected_result(result, s, "hydra.logging", self._execution_whitelist)
        self._authorize_callable(result, s)
        if (
            not callable(result)
            and self._execution_whitelist is None
            and s not in _BUILTIN_LOGGING_TARGETS
        ):
            _warn_legacy_logging_execution_whitelist()
        self._resolved_targets[s] = result
        self._resolved_target_sources[id(result)] = s
        return result

    def _prepare_custom_factory(self, config: Any) -> None:
        factory = config.get("()")
        if callable(factory):
            resolved_from = self._authorize_callable(factory, "")
        elif isinstance(factory, str):
            resolved_from = factory
            factory = self.resolve(factory)
        else:
            return

        def authorized_factory(*args: Any, **kwargs: Any) -> Any:
            return self._invoke_authorized_callable(
                factory, args, kwargs, resolved_from
            )

        config["()"] = authorized_factory

    def _apply_configured_properties(self, result: Any, props: Any) -> None:
        if props:
            for name, value in props.items():
                _authorize_target_invocation(
                    setattr,
                    (result, name, value),
                    {},
                    "hydra.logging",
                    self._execution_whitelist,
                )
                setattr(result, name, value)

    def configure_custom(self, config: Any) -> Any:
        self._prepare_custom_factory(config)
        props = config.pop(".", None)
        result = super().configure_custom(config)
        self._apply_configured_properties(result, props)
        return result

    def _drop_invalid_formatter_result(self, result: Any, source: Any) -> Any:
        if (
            self._execution_whitelist is not UNSAFE_DISABLE_EXECUTION_CHECKS
            and not isinstance(result, logging.Formatter)
        ):
            warnings.warn(
                f"Logging formatter {source!r} returned "
                f"{type(result).__name__} instead of logging.Formatter; "
                "ignoring the configured formatter.",
                UserWarning,
                stacklevel=3,
            )
            return None
        return result

    def configure_formatter(self, config: Any) -> Any:
        if (
            config.get("style", "%") == "{"
            and self._execution_whitelist is not UNSAFE_DISABLE_EXECUTION_CHECKS
        ):
            raise InstantiationException(
                "Logging format style '{' cannot be selected by declarative "
                "configuration because its fields can traverse Python objects. "
                "Use '%' or '$' style, or configure logging from trusted Python code."
            )
        source = config.get("()", config.get("class", "logging.Formatter"))
        if "()" in config:
            result = super().configure_formatter(config)
        else:
            formatter_class = config.get("class")
            if isinstance(formatter_class, str):
                target = self.resolve(formatter_class)
                fmt = config.get("format")
                datefmt = config.get("datefmt")
                style = config.get("style", "%")
                args: tuple[Any, ...] = (fmt, datefmt, style)
                if "validate" in config:
                    args += (config["validate"],)
                kwargs: dict[str, Any] = {}
                if sys.version_info >= (3, 12):
                    defaults = config.get("defaults")
                    if defaults is not None:
                        kwargs["defaults"] = defaults
                result = self._invoke_authorized_callable(
                    target, args, kwargs, formatter_class
                )
            else:
                if callable(formatter_class):
                    self._authorize_callable(formatter_class, "")
                result = super().configure_formatter(config)
        return self._drop_invalid_formatter_result(result, source)

    def _configure_queue_handler(self, klass: Any, **kwargs: Any) -> Any:
        listener = kwargs.get("listener")
        if callable(listener):
            resolved_from = self._resolved_target_sources.get(id(listener))
            if resolved_from is None:
                resolved_from = self._authorize_callable(listener, "")

            def authorized_listener(*args: Any, **listener_kwargs: Any) -> Any:
                return self._invoke_authorized_callable(
                    listener, args, listener_kwargs, resolved_from
                )

            kwargs["listener"] = authorized_listener

        configure_queue_handler = getattr(super(), "_configure_queue_handler")
        return configure_queue_handler(klass, **kwargs)

    def configure_handler(self, config: Any) -> Any:
        if "()" in config:
            self._prepare_custom_factory(config)
        handler_class = config.get("class")
        resolved_from = ""
        queue_factory_path = ""
        if isinstance(handler_class, str):
            resolved_from = handler_class
            handler_class = self.resolve(handler_class)
        elif callable(handler_class):
            resolved_from = self._authorize_callable(handler_class, "")
        if callable(handler_class):
            kwargs = {
                key: value
                for key, value in config.items()
                if key not in {"class", "formatter", "level", "filters", "."}
                and key.isidentifier()
            }
            effective_target, effective_args, effective_kwargs = (
                _authorize_target_invocation(
                    handler_class,
                    (),
                    kwargs,
                    "hydra.logging",
                    self._execution_whitelist,
                )
            )
            discovery_path = _authorize_discovery_path(
                effective_target,
                effective_args,
                effective_kwargs,
                "hydra.logging",
                self._execution_whitelist,
            )
            resolved_from = discovery_path or resolved_from
        for key in ("queue", "listener"):
            value = config.get(key)
            if callable(value):
                self._authorize_callable(value, "")

        deferred_config = {
            key: config.pop(key)
            for key in ("formatter", "level", "filters", ".")
            if key in config
        }
        try:
            if isinstance(handler_class, type) and issubclass(
                handler_class, logging.handlers.QueueHandler
            ):
                queue_factory = config.get("queue")
                if isinstance(queue_factory, str):
                    queue_factory_path = queue_factory
                    queue_target = self.resolve(queue_factory)
                    if not callable(queue_target):
                        raise TypeError(f"Invalid queue specifier {queue_factory!r}")
                    config["queue"] = self._invoke_authorized_callable(
                        queue_target, (), {}, queue_factory
                    )
            result = super().configure_handler(config)
        except Exception:
            if queue_factory_path:
                config["queue"] = queue_factory_path
            config.update(deferred_config)
            raise

        if not isinstance(result, logging.Handler):
            raise TypeError(
                "Configured handler factory must return a logging.Handler instance"
            )

        if resolved_from:
            result = _mediate_target_result(
                result,
                resolved_from,
                "hydra.logging",
                self._execution_whitelist,
            )

        formatter = deferred_config.get("formatter")
        if formatter:
            try:
                formatter = self.config["formatters"][formatter]
            except Exception as exc:
                raise ValueError(f"Unable to set formatter {formatter!r}") from exc
            result.setFormatter(formatter)
        level = deferred_config.get("level")
        if level is not None:
            result.setLevel(level)
        filters = deferred_config.get("filters")
        if filters:
            self.add_filters(result, filters)
        props = deferred_config.get(".")
        self._apply_configured_properties(result, props)
        return result


def configure_logging(
    config: dict[str, Any], execution_whitelist: ExecutionWhitelist = None
) -> None:
    if logging.config.dictConfigClass is not logging.config.DictConfigurator:
        raise ValueError(
            dedent(
                """\
                Hydra does not support a custom logging.config.dictConfigClass
                because it can bypass Hydra target authorization. Express custom
                handlers, formatters, filters, queues, and listeners in the logging
                configuration and authorize them with execution_whitelist instead.
                See https://hydra.cc/docs/advanced/execution_whitelist/"""
            )
        )
    effective_whitelist = _resolve_logging_execution_whitelist(execution_whitelist)
    try:
        HydraDictConfigurator(
            config,
            cast(NormalizedExecutionWhitelist, effective_whitelist),
        ).configure()
    except ValueError as e:
        cause = e.__cause__
        while cause is not None and not isinstance(cause, InstantiationException):
            cause = cause.__cause__
        if isinstance(cause, InstantiationException):
            raise ValueError(f"{e}\n{cause}") from e
        raise

# SPDX-FileCopyrightText: Contributors to Hydra
# SPDX-License-Identifier: MIT

import inspect
import logging.config
import sys
from pathlib import Path
from textwrap import dedent
from typing import Any, Callable, Dict, Tuple, cast

from hydra._internal.deprecation_warning import deprecation_warning
from hydra._internal.target_policy import (
    UNSAFE_ALLOW_ALL_TARGETS,
    NormalizedTargetWhitelist,
    TargetWhitelist,
    _authorize_discovery_path,
    _authorize_resolved_target_identity,
    _authorize_target_invocation,
    _authorize_target_name,
    _combine_target_whitelists,
    _get_os_alias_target,
    _get_resolved_target_name_for_check,
    _mediate_target_result,
    _resolve_target_whitelist,
)

# Hydra's built-in logging configurations must continue to work when an
# application enables a restrictive target whitelist. Keep this list exact so
# it does not broaden instantiate() authorization or trust a package namespace.
_BUILTIN_LOGGING_TARGETS: Tuple[str, ...] = (
    "colorlog.ColoredFormatter",
    "logging.FileHandler",
    "logging.StreamHandler",
    "sys.stderr",
    "sys.stdout",
)


def _resolve_logging_target_whitelist(
    target_whitelist: TargetWhitelist,
) -> NormalizedTargetWhitelist:
    resolved = _resolve_target_whitelist(target_whitelist)
    if resolved is None or resolved is UNSAFE_ALLOW_ALL_TARGETS:
        return resolved
    return _combine_target_whitelists(resolved, _BUILTIN_LOGGING_TARGETS)


def _warn_legacy_logging_target_whitelist() -> None:
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
            Hydra configured Python logging without a target whitelist. This
            preserves legacy behavior but is deprecated because logging
            configuration can select and execute arbitrary Python callables.
            This warning will become an error in Hydra 1.5. Pass target_whitelist=
            to @hydra.main(), use hydra.utils.target_whitelist(), or pass
            UNSAFE_ALLOW_ALL_TARGETS to explicitly keep legacy behavior.
            See https://hydra.cc/docs/upgrades/1.3_to_1.4/instantiate_target_whitelist/"""
        ),
        stacklevel=stacklevel,
    )


class HydraDictConfigurator(logging.config.DictConfigurator):
    """Apply Hydra target authorization to Python logging configuration."""

    def __init__(
        self,
        config: Dict[str, Any],
        target_whitelist: NormalizedTargetWhitelist,
    ) -> None:
        super().__init__(config)
        self._target_whitelist = target_whitelist
        self._resolved_targets: Dict[str, Any] = {}

    def _authorize_callable(self, target: Any, resolved_from: str) -> str:
        if not callable(target):
            return ""
        if resolved_from:
            target_name = _authorize_resolved_target_identity(
                target,
                resolved_from,
                "hydra.logging",
                self._target_whitelist,
            )
        else:
            target_name = _get_os_alias_target(
                _get_resolved_target_name_for_check(target)
            )
            _authorize_target_name(
                target_name,
                target_name,
                "hydra.logging",
                self._target_whitelist,
            )
        if (
            self._target_whitelist is None
            and target_name not in _BUILTIN_LOGGING_TARGETS
            and resolved_from not in _BUILTIN_LOGGING_TARGETS
        ):
            _warn_legacy_logging_target_whitelist()
        return target_name

    def _invoke_authorized_callable(
        self,
        target: Callable[..., Any],
        args: Tuple[Any, ...],
        kwargs: Dict[str, Any],
        resolved_from: str,
    ) -> Any:
        _authorize_target_invocation(
            target,
            args,
            kwargs,
            "hydra.logging",
            self._target_whitelist,
        )
        discovery_path = _authorize_discovery_path(
            target,
            args,
            kwargs,
            "hydra.logging",
            self._target_whitelist,
        )
        result = target(*args, **kwargs)
        return _mediate_target_result(
            result,
            discovery_path or resolved_from,
            "hydra.logging",
            self._target_whitelist,
            discovery_path=discovery_path,
        )

    def resolve(self, s: str) -> Any:
        if s in self._resolved_targets:
            return self._resolved_targets[s]
        _authorize_target_name(s, s, "hydra.logging", self._target_whitelist)
        result = super().resolve(s)
        self._authorize_callable(result, s)
        if (
            not callable(result)
            and self._target_whitelist is None
            and s not in _BUILTIN_LOGGING_TARGETS
        ):
            _warn_legacy_logging_target_whitelist()
        self._resolved_targets[s] = result
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

    def configure_custom(self, config: Any) -> Any:
        self._prepare_custom_factory(config)
        return super().configure_custom(config)

    def configure_formatter(self, config: Any) -> Any:
        if "()" in config:
            return super().configure_formatter(config)

        formatter_class = config.get("class")
        if isinstance(formatter_class, str):
            target = self.resolve(formatter_class)
            fmt = config.get("format")
            datefmt = config.get("datefmt")
            style = config.get("style", "%")
            args: Tuple[Any, ...] = (fmt, datefmt, style)
            if "validate" in config:
                args += (config["validate"],)
            kwargs: Dict[str, Any] = {}
            if sys.version_info >= (3, 12):
                defaults = config.get("defaults")
                if defaults is not None:
                    kwargs["defaults"] = defaults
            return self._invoke_authorized_callable(
                target, args, kwargs, formatter_class
            )
        elif callable(formatter_class):
            self._authorize_callable(formatter_class, "")
        return super().configure_formatter(config)

    def configure_handler(self, config: Any) -> Any:
        if "()" in config:
            self._prepare_custom_factory(config)
        handler_class = config.get("class")
        resolved_from = ""
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
            _authorize_target_invocation(
                handler_class,
                (),
                kwargs,
                "hydra.logging",
                self._target_whitelist,
            )
            discovery_path = _authorize_discovery_path(
                handler_class,
                (),
                kwargs,
                "hydra.logging",
                self._target_whitelist,
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
            result = super().configure_handler(config)
        except Exception:
            config.update(deferred_config)
            raise

        if resolved_from:
            result = _mediate_target_result(
                result,
                resolved_from,
                "hydra.logging",
                self._target_whitelist,
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
        if props:
            for name, value in props.items():
                setattr(result, name, value)
        return result


def configure_logging(
    config: Dict[str, Any], target_whitelist: TargetWhitelist = None
) -> None:
    if logging.config.dictConfigClass is not logging.config.DictConfigurator:
        raise ValueError(
            dedent(
                """\
                Hydra does not support a custom logging.config.dictConfigClass
                because it can bypass Hydra target authorization. Express custom
                handlers, formatters, filters, queues, and listeners in the logging
                configuration and authorize them with target_whitelist instead.
                See https://hydra.cc/docs/upgrades/1.3_to_1.4/instantiate_target_whitelist/"""
            )
        )
    effective_whitelist = _resolve_logging_target_whitelist(target_whitelist)
    HydraDictConfigurator(
        config,
        cast(NormalizedTargetWhitelist, effective_whitelist),
    ).configure()

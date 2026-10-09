# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved
import re
from dataclasses import dataclass, field

from omegaconf import DictConfig, OmegaConf

from hydra.core.override_parser.overrides_parser import OverridesParser
from hydra.errors import ConfigCompositionException, HydraException


def split_override(override: str) -> tuple[str, str, str]:
    """Separate the operator, exact key spelling, and untouched value suffix."""
    match = re.fullmatch(r"(\+\+|\+|~)?((?:\\.|[^=])*)(=.*)?", override, re.DOTALL)
    assert match is not None
    prefix, key, value = match.groups()
    return prefix or "", key, value or ""


@dataclass
class OverrideAliases:
    targets: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_config(cls, config: DictConfig) -> "OverrideAliases":
        if config._get_node("hydra", validate_access=False) is None:
            return cls()
        if OmegaConf.is_interpolation(config, "hydra"):
            raise ConfigCompositionException(
                "Override alias definitions must be literal"
            )
        if OmegaConf.is_interpolation(config.hydra, "override"):
            raise ConfigCompositionException(
                "Override alias definitions must be literal"
            )
        if "override" not in config.hydra:
            return cls()
        policy = config.hydra.override
        if not isinstance(policy, DictConfig) or "aliases" not in policy:
            return cls()
        if OmegaConf.is_interpolation(policy, "aliases"):
            raise ConfigCompositionException(
                "Override alias definitions must be literal"
            )
        definitions = policy.aliases
        if not isinstance(definitions, DictConfig):
            raise ConfigCompositionException("hydra.override.aliases must be a mapping")

        targets: dict[str, str] = {}
        parser = OverridesParser.create()
        for names, target in definitions.items_ex(resolve=False):
            if (
                not isinstance(names, str)
                or not isinstance(target, str)
                or "${" in target
            ):
                raise ConfigCompositionException(
                    "Override aliases must have string names and literal string targets"
                )
            try:
                _, _, value = split_override(target)
                parsed = parser.parse_override(target if value else target + "=null")
                if not value and (
                    parsed.is_add() or parsed.is_force_add() or parsed.is_delete()
                ):
                    raise ConfigCompositionException(
                        "A key alias target cannot have an operator"
                    )
                for name in names.split(","):
                    name = name.strip()
                    prefix, key, suffix = split_override(name)
                    if not name or prefix or suffix:
                        raise ConfigCompositionException(
                            "Alias names must be nonempty override keys"
                        )
                    parser.parse_override(key + "=null")
                    if name in targets:
                        raise ConfigCompositionException(
                            f"Duplicate override alias '{name}'"
                        )
                    targets[name] = target
            except HydraException as e:
                raise ConfigCompositionException(
                    f"Invalid override alias '{names}': {e}"
                ) from e
        return cls(targets)

    def expand(self, override: str) -> str:
        prefix, key, value = split_override(override)
        target = self.targets.get(key)
        if target is None:
            return override
        target_prefix, target_key, target_value = split_override(target)
        if target_value:
            if value:
                return override
            return (prefix or target_prefix) + target_key + target_value
        if not value and prefix != "~":
            raise ConfigCompositionException(
                f"Override alias '{key}' requires a value for '{override}'"
            )
        return prefix + target + value

    def format(self) -> str:
        if not self.targets:
            return ""
        rows = ["== Override aliases ==", ""]
        for name, target in self.targets.items():
            _, _, value = split_override(target)
            rows.append(f"{name} -> {target if value else target + '=<value>'}")
        return "\n".join(rows) + "\n"

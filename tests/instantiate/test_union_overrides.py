# SPDX-FileCopyrightText: Contributors to Hydra
# SPDX-License-Identifier: MIT
"""Regression checks for the override semantics reported in Hydra #3580."""

from dataclasses import dataclass, field
from typing import Any, cast

import pytest
from omegaconf import DictConfig, OmegaConf
from omegaconf.errors import ConfigKeyError

from hydra.types import ConvertMode
from hydra.utils import UNSAFE_DISABLE_EXECUTION_CHECKS, instantiate


@dataclass
class Step:
    step_size: int = 10


@dataclass
class Cos:
    t_max: int = 100


@dataclass
class Adam:
    _target_: str = "builtins.dict"
    lr: float = 0.001
    eps: float = 1e-8
    sched: Step | Cos = field(default_factory=Step)


@dataclass
class SGD:
    _target_: str = "builtins.dict"
    lr: float = 0.1
    momentum: float = 0.9


@dataclass
class Trainer:
    _target_: str = "builtins.dict"
    value: int = 50
    plain: Adam = field(default_factory=Adam)
    optimizer: Adam | SGD = field(default_factory=Adam)
    flexible: Adam | dict[str, float] = field(default_factory=Adam)


@pytest.mark.parametrize(
    "field_name,source_kind,recursive",
    [
        ("optimizer", "dict", False),
        ("optimizer", "config", False),
        ("optimizer", "sgd", False),
        ("optimizer", "sgd", True),
        ("flexible", "typed_dict", False),
    ],
)
def test_union_branch_selection(
    field_name: str, source_kind: str, recursive: bool
) -> None:
    cfg = OmegaConf.structured(Trainer)
    OmegaConf.set_readonly(cfg, True)
    sources: dict[str, Any] = {
        "dict": {"lr": 0.5},
        "config": OmegaConf.create({"lr": 0.5}),
        "typed_dict": OmegaConf.typed_dict(
            {"lr": 0.5}, key_type=str, element_type=float
        ),
        "sgd": OmegaConf.structured(SGD),
    }
    override = sources[source_kind]
    before = OmegaConf.to_container(cfg, resolve=False)
    override_before = (
        OmegaConf.to_container(override, resolve=False)
        if isinstance(override, DictConfig)
        else dict(override)
    )
    merged = cast(DictConfig, OmegaConf.merge(cfg, {field_name: override}))
    expected = merged[field_name]
    actual = instantiate(
        cfg,
        **{field_name: override},
        _recursive_=recursive,
        _execution_whitelist_=UNSAFE_DISABLE_EXECUTION_CHECKS,
    )[field_name]
    if recursive and "_target_" in expected:
        expected_dict = OmegaConf.to_container(expected, resolve=True)
        assert isinstance(expected_dict, dict)
        expected_dict.pop("_target_")
        expected = expected_dict
    assert actual == expected
    if not recursive:
        assert OmegaConf.get_type(actual) is OmegaConf.get_type(expected)
    assert OmegaConf.to_container(cfg, resolve=False) == before
    assert OmegaConf.is_readonly(cfg)
    assert (
        OmegaConf.to_container(override, resolve=False)
        if isinstance(override, DictConfig)
        else override
    ) == override_before


@pytest.mark.parametrize(
    "field_name,outer_config,convert",
    [
        ("plain", False, ConvertMode.NONE),
        ("optimizer", False, ConvertMode.NONE),
        ("optimizer", True, ConvertMode.NONE),
        ("optimizer", False, ConvertMode.OBJECT),
    ],
)
def test_nested_typed_union_override(
    field_name: str, outer_config: bool, convert: ConvertMode
) -> None:
    cfg = OmegaConf.structured(Trainer)
    nested = OmegaConf.structured(Cos(t_max=50))
    override: Any = {"sched": nested}
    if outer_config:
        override = OmegaConf.create(override)
    before = OmegaConf.to_container(cfg, resolve=False)
    merged = cast(DictConfig, OmegaConf.merge(cfg, {field_name: override}))
    expected = merged[field_name].sched
    result = instantiate(
        cfg,
        **{field_name: override},
        _convert_=convert,
        _execution_whitelist_=UNSAFE_DISABLE_EXECUTION_CHECKS,
    )[field_name]["sched"]
    if convert is ConvertMode.OBJECT:
        assert result == Cos(t_max=50)
    else:
        assert result == expected == {"t_max": 50}
        if convert in (ConvertMode.NONE, ConvertMode.PARTIAL):
            assert OmegaConf.get_type(result) is Cos
    assert OmegaConf.to_container(cfg, resolve=False) == before
    assert OmegaConf.get_type(nested) is Cos
    assert nested.t_max == 50


def test_nested_typed_override_resolves_in_merged_context() -> None:
    cfg = OmegaConf.structured(Trainer)
    source = OmegaConf.create({"value": 75, "schedule": Cos()})
    source.schedule.t_max = "${value}"
    OmegaConf.set_readonly(cfg, True)
    OmegaConf.set_readonly(source, True)
    before = OmegaConf.to_container(source, resolve=False)
    overrides: dict[str, Any] = {"optimizer": {"sched": source.schedule}}
    merged = cast(DictConfig, OmegaConf.merge(cfg, overrides))
    assert merged.optimizer.sched.t_max == 50
    result = instantiate(
        cfg,
        **overrides,
        _execution_whitelist_=UNSAFE_DISABLE_EXECUTION_CHECKS,
    )
    assert result["optimizer"]["sched"] == {"t_max": 50}
    assert OmegaConf.get_type(result["optimizer"]["sched"]) is Cos
    assert OmegaConf.to_container(source, resolve=False) == before
    assert OmegaConf.get_type(cfg.optimizer.sched) is Step
    assert OmegaConf.is_readonly(cfg)
    assert OmegaConf.is_readonly(source)


def test_nested_typed_empty_sequence_selects_its_union_branch() -> None:
    @dataclass
    class Value:
        options: list[int] | list[str] = field(default_factory=lambda: [1])

    @dataclass
    class Config:
        _target_: str = "builtins.dict"
        value: Value = field(default_factory=Value)

    cfg = OmegaConf.structured(Config)
    options = OmegaConf.typed_list([], element_type=str)
    result = instantiate(
        cfg,
        value={"options": options},
        _recursive_=False,
        _execution_whitelist_=UNSAFE_DISABLE_EXECUTION_CHECKS,
    )
    assert result["value"].options == []
    assert result["value"].options._metadata.element_type is str
    assert cfg.value.options == [1]
    assert options._metadata.element_type is str


@pytest.mark.parametrize(
    "field_name,as_config", [("optimizer", False), ("flexible", True)]
)
def test_untyped_mapping_keeps_selected_branch_validation(
    field_name: str, as_config: bool
) -> None:
    cfg = OmegaConf.structured(Trainer)
    override: Any = {"momentum": 0.5}
    if as_config:
        override = OmegaConf.create(override)
    before = OmegaConf.to_container(cfg, resolve=False)
    with pytest.raises(ConfigKeyError, match="Key 'momentum' not in 'Adam'"):
        instantiate(
            cfg,
            **{field_name: override},
            _execution_whitelist_=UNSAFE_DISABLE_EXECUTION_CHECKS,
        )
    assert OmegaConf.to_container(cfg, resolve=False) == before

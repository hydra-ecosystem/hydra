# SPDX-FileCopyrightText: Contributors to Hydra
# SPDX-License-Identifier: MIT
"""Integration checks for Hydra's logical traversal with OmegaConf 2.4.1."""

import copy
from dataclasses import dataclass, field
from functools import partial
from typing import Any

import pytest
from omegaconf import DictConfig, OmegaConf

from hydra.utils import UNSAFE_DISABLE_EXECUTION_CHECKS, instantiate


@dataclass
class Adam:
    _target_: str = "builtins.dict"
    lr: float = "${base_lr}"  # type: ignore[assignment]
    eps: float = 1e-8


@dataclass
class SGD:
    _target_: str = "builtins.dict"
    lr: float = 0.1
    momentum: float = 0.9


def optimizer_list() -> list[Adam | SGD]:
    return [Adam()]


def optimizer_dict() -> dict[str, Adam | SGD]:
    return {"adam": Adam()}


@dataclass
class Trainer:
    _target_: str = "builtins.dict"
    base_lr: float = 0.001
    plain: Adam = field(default_factory=Adam)
    optimizer: Adam | SGD = field(default_factory=Adam)
    optimizers: list[Adam | SGD] = field(default_factory=optimizer_list)
    tuple_optimizers: tuple[Adam | SGD, ...] = field(default_factory=lambda: (Adam(),))
    named: dict[str, Adam | SGD] = field(default_factory=optimizer_dict)
    default: Adam | None = field(default_factory=Adam)
    interpolated: Adam | SGD = "${default}"  # type: ignore[assignment]


def select(root: DictConfig, location: str) -> DictConfig:
    if location == "list":
        return root.optimizers[0]
    if location == "tuple":
        return root.tuple_optimizers[0]
    if location == "dict":
        return root.named.adam
    return root[location]


@pytest.mark.parametrize(
    "location", ["plain", "optimizer", "list", "tuple", "dict", "interpolated"]
)
@pytest.mark.parametrize(
    "options",
    [
        {},
        {"lr": 0.5},
        {"_partial_": True},
        {"_recursive_": False},
        {"isolate": True},
        {"isolate": False, "lr": 0.5},
        {"isolate": True, "lr": 0.5},
    ],
)
def test_selected_union_instantiation(location: str, options: dict[str, Any]) -> None:
    root = OmegaConf.structured(Trainer)
    before = OmegaConf.to_container(root, resolve=False)
    interpolated = root._get_node("interpolated")
    selected = select(root, location)
    result = instantiate(
        selected, _execution_whitelist_=UNSAFE_DISABLE_EXECUTION_CHECKS, **options
    )
    if isinstance(result, partial):
        result = result()
    assert result == {"lr": options.get("lr", 0.001), "eps": 1e-8}
    assert OmegaConf.to_container(root, resolve=False) == before
    assert root._get_node("interpolated") is interpolated


@pytest.mark.parametrize("location", ["optimizer", "list", "tuple", "dict"])
def test_union_positional_argument(location: str) -> None:
    root = OmegaConf.structured(Trainer)
    before = OmegaConf.to_container(root, resolve=False)
    result = instantiate(
        select(root, location),
        {"extra": 7},
        _execution_whitelist_=UNSAFE_DISABLE_EXECUTION_CHECKS,
    )
    assert result == {"extra": 7, "lr": 0.001, "eps": 1e-8}
    assert OmegaConf.to_container(root, resolve=False) == before


@pytest.mark.parametrize("location", ["optimizer", "list", "tuple", "dict"])
@pytest.mark.parametrize("readonly", [False, True])
def test_merged_union_member_keeps_context(location: str, readonly: bool) -> None:
    root = OmegaConf.structured(Trainer)
    OmegaConf.set_readonly(root, readonly)
    before = OmegaConf.to_container(root, resolve=False)
    member = select(root, location)
    merged = OmegaConf.merge(member, {"eps": 1e-6})
    assert instantiate(
        merged, lr=0.5, _execution_whitelist_=UNSAFE_DISABLE_EXECUTION_CHECKS
    ) == {"lr": 0.5, "eps": 1e-6}
    assert OmegaConf.to_container(root, resolve=False) == before


@pytest.mark.parametrize("location", ["optimizer", "list", "tuple", "dict"])
def test_deepcopied_union_member_keeps_context(location: str) -> None:
    root = OmegaConf.structured(Trainer)
    copied = copy.deepcopy(select(root, location))
    assert instantiate(
        copied, eps=1e-6, _execution_whitelist_=UNSAFE_DISABLE_EXECUTION_CHECKS
    ) == {"lr": 0.001, "eps": 1e-6}


@pytest.mark.parametrize("isolate", [False, True])
@pytest.mark.parametrize("recursive", [True, False])
@pytest.mark.parametrize("partial", [False, True])
def test_container_union_argument(
    isolate: bool, recursive: bool, partial: bool
) -> None:
    @dataclass
    class Config:
        _target_: str = "builtins.dict"
        sizes: list[int] | dict[str, int] = field(default_factory=lambda: [8, 16])

    cfg = OmegaConf.structured(Config)
    OmegaConf.set_readonly(cfg, True)
    before = OmegaConf.to_container(cfg, resolve=False)
    source = cfg.sizes
    source_readonly = OmegaConf.is_readonly(source)
    result = instantiate(
        cfg,
        isolate=isolate,
        _recursive_=recursive,
        _partial_=partial,
        _execution_whitelist_=UNSAFE_DISABLE_EXECUTION_CHECKS,
    )
    if partial:
        result = result()
    assert result == {"sizes": [8, 16]}
    if isolate:
        assert result["sizes"] is not source
        assert cfg.sizes is source
        assert OmegaConf.to_container(cfg, resolve=False) == before
        assert OmegaConf.is_readonly(cfg) is True
        assert OmegaConf.is_readonly(source) is source_readonly


@pytest.mark.parametrize("recursive", [True, False])
@pytest.mark.parametrize("partial", [False, True])
def test_isolated_structured_union_argument(recursive: bool, partial: bool) -> None:
    root = OmegaConf.structured(Trainer)
    OmegaConf.set_readonly(root, True)
    before = OmegaConf.to_container(root, resolve=False)
    source = root.optimizer
    source_readonly = OmegaConf.is_readonly(source)

    result = instantiate(
        root,
        isolate=True,
        _recursive_=recursive,
        _partial_=partial,
        _execution_whitelist_=UNSAFE_DISABLE_EXECUTION_CHECKS,
    )
    if partial:
        result = result()

    optimizer = result["optimizer"]
    assert optimizer["lr"] == 0.001
    assert optimizer is not source
    assert OmegaConf.to_container(root, resolve=False) == before
    assert root.optimizer is source
    assert OmegaConf.is_readonly(root) is True
    assert OmegaConf.is_readonly(source) is source_readonly


@pytest.mark.parametrize("as_config", [False, True])
def test_parent_union_mapping_override(as_config: bool) -> None:
    root = OmegaConf.structured(Trainer)
    override = {"lr": 0.5}
    if as_config:
        override = OmegaConf.create(override)
    before = OmegaConf.to_container(root, resolve=False)
    result = instantiate(
        root,
        optimizer=override,
        _execution_whitelist_=UNSAFE_DISABLE_EXECUTION_CHECKS,
    )
    assert result["optimizer"] == {"lr": 0.5, "eps": 1e-8}
    assert OmegaConf.to_container(root, resolve=False) == before

# SPDX-FileCopyrightText: Contributors to Hydra
# SPDX-License-Identifier: MIT
"""Integration checks for Hydra's logical traversal with OmegaConf 2.4.1."""

import copy
from dataclasses import dataclass, field

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
    "location", ["optimizer", "list", "tuple", "dict", "interpolated"]
)
def test_selected_union_instantiation(location: str) -> None:
    root = OmegaConf.structured(Trainer)
    before = OmegaConf.to_container(root, resolve=False)
    interpolated = root._get_node("interpolated")
    selected = select(root, location)
    result = instantiate(
        selected, eps=1e-6, _execution_whitelist_=UNSAFE_DISABLE_EXECUTION_CHECKS
    )
    assert result == {"lr": 0.001, "eps": 1e-6}
    assert OmegaConf.to_container(root, resolve=False) == before
    assert root._get_node("interpolated") is interpolated


def test_selected_union_resolves_relative_interpolation() -> None:
    root = OmegaConf.structured(Trainer)
    root.optimizer.lr = "${..base_lr}"
    assert instantiate(
        root.optimizer,
        eps=1e-6,
        _execution_whitelist_=UNSAFE_DISABLE_EXECUTION_CHECKS,
    ) == {"lr": 0.001, "eps": 1e-6}


@pytest.mark.parametrize(
    "clone,location", [("merge", "tuple"), ("deepcopy", "optimizer")]
)
def test_copied_union_member_keeps_context(clone: str, location: str) -> None:
    root = OmegaConf.structured(Trainer)
    OmegaConf.set_readonly(root, True)
    before = OmegaConf.to_container(root, resolve=False)
    member = select(root, location)
    copied = (
        OmegaConf.merge(member, {"eps": 1e-6})
        if clone == "merge"
        else copy.deepcopy(member)
    )
    assert instantiate(
        copied, eps=1e-6, _execution_whitelist_=UNSAFE_DISABLE_EXECUTION_CHECKS
    ) == {"lr": 0.001, "eps": 1e-6}
    assert OmegaConf.to_container(root, resolve=False) == before
    assert OmegaConf.is_readonly(root)


@pytest.mark.parametrize("partial", [False, True])
def test_isolated_nonrecursive_union_argument(partial: bool) -> None:
    root = OmegaConf.structured(Trainer)
    OmegaConf.set_readonly(root, True)
    before = OmegaConf.to_container(root, resolve=False)
    source = root.optimizer
    OmegaConf.set_readonly(source, False)
    OmegaConf.set_readonly(source._get_child("lr"), True)
    source_readonly = OmegaConf.is_readonly(source)

    result = instantiate(
        root,
        isolate=True,
        _recursive_=False,
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
    assert OmegaConf.is_readonly(source._get_child("lr")) is True


@pytest.mark.parametrize("partial", [False, True])
def test_union_argument_is_readonly_during_target_call(partial: bool) -> None:
    @dataclass
    class Payload:
        value: int = 10

    @dataclass
    class Job:
        _target_: str = "tests.instantiate.test_instantiate.ConfigMutationProbe"
        _recursive_: bool = False
        _partial_: bool = False
        payload: Payload | SGD = field(default_factory=Payload)

    root = OmegaConf.structured(Job)
    root._partial_ = partial
    source = root.payload
    OmegaConf.set_readonly(source, False)
    result = instantiate(
        root,
        _execution_whitelist_=UNSAFE_DISABLE_EXECUTION_CHECKS,
    )
    if partial:
        result = result()

    assert result.payload is source
    assert result.readonly
    assert result.mutation_blocked
    assert source.value == 10
    assert source._get_node_flag("readonly") is False


def test_parent_union_mapping_override() -> None:
    root = OmegaConf.structured(Trainer)
    before = OmegaConf.to_container(root, resolve=False)
    result = instantiate(
        root,
        optimizer={"eps": 1e-6},
        _execution_whitelist_=UNSAFE_DISABLE_EXECUTION_CHECKS,
    )
    assert result["optimizer"] == {"lr": 0.001, "eps": 1e-6}
    assert OmegaConf.to_container(root, resolve=False) == before

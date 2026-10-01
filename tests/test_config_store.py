# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved
import warnings
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Dict, Iterator, Optional

from pytest import mark, param, raises, warns

from hydra.core.config_store import ConfigStore, ConfigStoreWithProvider


@dataclass
class Config:
    x: int = 10


@dataclass
class NestedConfig:
    items: Any = field(default_factory=lambda: [1, 2])


@contextmanager
def no_warning() -> Iterator[None]:
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        yield


def store(node: Any = Config(), group: Optional[str] = None, **kwargs: Any) -> None:
    ConfigStore.instance().store(name="cfg", node=node, group=group, **kwargs)


def loaded(name: str) -> Any:
    return ConfigStore.instance().load(name).node


@mark.usefixtures("hydra_restore_singletons")
@mark.parametrize(
    "group,full_name",
    [
        param(None, "cfg.yaml", id="no_group"),
        param("my_group", "my_group/cfg.yaml", id="group"),
        param("a/b", "a/b/cfg.yaml", id="nested_group"),
    ],
)
class TestStoreClobber:
    def test_warns_by_default(self, group: Optional[str], full_name: str) -> None:
        store(Config(x=1), group)
        with warns(UserWarning, match=f"already stored at '{full_name}'"):
            store(Config(x=2), group)
        assert loaded(full_name) == {"x": 2}

    def test_replace_true_is_silent(self, group: Optional[str], full_name: str) -> None:
        store(Config(x=1), group)
        with no_warning():
            store(Config(x=2), group, replace=True)
        assert loaded(full_name) == {"x": 2}

    def test_replace_false_raises(self, group: Optional[str], full_name: str) -> None:
        store(Config(x=1), group)
        with raises(ValueError, match=f"already stored at '{full_name}'"):
            store(Config(x=2), group, replace=False)
        assert loaded(full_name) == {"x": 1}


@mark.usefixtures("hydra_restore_singletons")
@mark.parametrize("replace", [None, False], ids=["default", "replace_false"])
def test_storing_an_equal_config_is_not_a_clobber(replace: Optional[bool]) -> None:
    """Hydra re-executes plugin modules on every plugin discovery pass, so their
    module level store() calls repeat with the same node. That is not a clobber.
    """
    store(Config(x=1), "my_group", provider="p")
    with no_warning():
        store(Config(x=1), "my_group", provider="p", replace=replace)
    assert loaded("my_group/cfg.yaml") == {"x": 1}


@mark.usefixtures("hydra_restore_singletons")
@mark.parametrize(
    "second",
    [
        param({"package": "pkg"}, id="package"),
        param({"provider": "prov"}, id="provider"),
    ],
)
def test_differing_metadata_is_a_clobber(second: Dict[str, Any]) -> None:
    store(group="my_group")
    with warns(UserWarning, match="already stored at 'my_group/cfg.yaml'"):
        store(group="my_group", **second)


@mark.usefixtures("hydra_restore_singletons")
def test_first_store_never_raises() -> None:
    with no_warning():
        store(group="brand_new_group", replace=False)


@mark.usefixtures("hydra_restore_singletons")
def test_nested_values_are_compared() -> None:
    store(NestedConfig())
    with warns(UserWarning, match="already stored at 'cfg.yaml'"):
        store(NestedConfig(items=[1, 3]))


@mark.usefixtures("hydra_restore_singletons")
def test_config_store_with_provider_forwards_replace() -> None:
    with ConfigStoreWithProvider("prov") as cs:
        cs.store(name="cfg", node=Config(x=1), group="my_group")
        with raises(ValueError, match="already stored at 'my_group/cfg.yaml'"):
            cs.store(name="cfg", node=Config(x=2), group="my_group", replace=False)
        cs.store(name="cfg", node=Config(x=2), group="my_group", replace=True)
    assert loaded("my_group/cfg.yaml") == {"x": 2}

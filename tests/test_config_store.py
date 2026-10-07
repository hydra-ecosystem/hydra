# SPDX-FileCopyrightText: Contributors to Hydra
# SPDX-License-Identifier: MIT
import inspect
import warnings
from pathlib import Path
from textwrap import dedent
from typing import Any

from pytest import mark, raises, warns

from hydra.core.config_store import ConfigStore, ConfigStoreWithProvider
from hydra.errors import Hydra15MigrationWarning
from hydra.test_utils.test_utils import run_python_script


@mark.parametrize("replace", [None, True, False])
@mark.parametrize("group", [None, "", "db", "app/db"])
def test_new_registration(
    hydra_restore_singletons: Any, replace: bool | None, group: str | None
) -> None:
    cs = ConfigStore.instance()
    cs.store(name="collision_test", group=group, node={"value": 1}, replace=replace)
    path = f"{group}/collision_test.yaml" if group else "collision_test.yaml"
    assert cs.load(path).node == {"value": 1}


@mark.parametrize("group", [None, "db", "app/db"])
@mark.parametrize("name", ["collision_test", "collision_test.yaml"])
def test_collision_warns_and_replaces(
    hydra_restore_singletons: Any, group: str | None, name: str
) -> None:
    cs = ConfigStore.instance()
    cs.store(name="collision_test", group=group, node={"value": 1}, provider="original")
    path = f"{group}/collision_test.yaml" if group else "collision_test.yaml"
    with warns(Hydra15MigrationWarning) as caught:
        cs.store(name=name, group=group, node={"value": 2}, provider="replacement")
    message = str(caught[0].message)
    assert path in message
    assert "original" in message and "replacement" in message
    assert "replace=True" in message and "replace=False" in message
    assert "Hydra 1.5" in message
    assert (
        "https://hydra.cc/docs/next/upgrades/1.3_to_1.4/config_store_collisions#choose-the-intended-behavior"
        in message
    )
    assert caught[0].filename == __file__
    assert cs.load(path).node == {"value": 2}
    assert cs.load(path).provider == "replacement"


@mark.parametrize("provider", [None, "replacement"])
def test_explicit_replacement(
    hydra_restore_singletons: Any, provider: str | None
) -> None:
    cs = ConfigStore.instance()
    cs.store(name="collision_test", node={"value": 1}, provider="original")
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        cs.store(
            name="collision_test", node={"value": 2}, provider=provider, replace=True
        )
    assert not caught
    assert cs.load("collision_test.yaml").node == {"value": 2}
    assert cs.load("collision_test.yaml").provider == provider


@mark.parametrize("group", [None, "", "app/db"])
def test_collision_rejected_without_mutation(
    hydra_restore_singletons: Any, group: str | None
) -> None:
    cs = ConfigStore.instance()
    cs.store(name="collision_test", group=group, node={"value": 1}, provider="original")
    path = f"{group}/collision_test.yaml" if group else "collision_test.yaml"
    before = cs.load(path)
    with raises(ValueError) as caught:
        cs.store(
            name="collision_test.yaml",
            group=group,
            node={"value": 2},
            provider="replacement",
            replace=False,
        )
    assert path in str(caught.value)
    assert "original" in str(caught.value) and "replacement" in str(caught.value)
    assert "#choose-the-intended-behavior" in str(caught.value)
    assert cs.load(path) == before


def test_empty_and_none_group_collide(hydra_restore_singletons: Any) -> None:
    cs = ConfigStore.instance()
    cs.store(name="collision_test", node={"value": 1}, group="")
    with raises(ValueError):
        cs.store(name="collision_test", node={"value": 2}, replace=False)
    assert cs.load("collision_test.yaml").node == {"value": 1}


def test_same_node_still_collides(hydra_restore_singletons: Any) -> None:
    cs = ConfigStore.instance()
    node = {"value": 1}
    cs.store(name="collision_test", node=node)
    with warns(Hydra15MigrationWarning):
        cs.store(name="collision_test", node=node)


@mark.parametrize("replace", [None, True, False])
def test_provider_wrapper(hydra_restore_singletons: Any, replace: bool | None) -> None:
    cs = ConfigStore.instance()
    cs.store(name="collision_test", node={"value": 1}, provider="original")
    with ConfigStoreWithProvider("replacement") as wrapper:
        if replace is False:
            with raises(ValueError, match="replacement"):
                wrapper.store(name="collision_test", node={"value": 2}, replace=False)
            assert cs.load("collision_test.yaml").node == {"value": 1}
        elif replace is None:
            with warns(Hydra15MigrationWarning, match="replacement"):
                wrapper.store(name="collision_test", node={"value": 2})
            assert cs.load("collision_test.yaml").node == {"value": 2}
        else:
            wrapper.store(name="collision_test", node={"value": 2}, replace=True)
            assert cs.load("collision_test.yaml").provider == "replacement"


@mark.parametrize("with_provider", [False, True])
def test_collision_warning_location(
    hydra_restore_singletons: Any, with_provider: bool
) -> None:
    cs = ConfigStore.instance()
    cs.store(name="collision_test", node={"value": 1})
    store = ConfigStoreWithProvider("replacement") if with_provider else cs
    with warns(Hydra15MigrationWarning) as caught:
        frame = inspect.currentframe()
        assert frame is not None
        expected_line = frame.f_lineno + 1
        store.store(name="collision_test", node={"value": 2})
    assert caught[0].filename == __file__
    assert caught[0].lineno == expected_line


def test_collision_warning_as_error_preserves_registration(
    hydra_restore_singletons: Any,
) -> None:
    cs = ConfigStore.instance()
    cs.store(name="collision_test", node={"value": 1})
    with warnings.catch_warnings():
        warnings.simplefilter("error", Hydra15MigrationWarning)
        with raises(Hydra15MigrationWarning):
            cs.store(name="collision_test", node={"value": 2})
    assert cs.load("collision_test.yaml").node == {"value": 1}


@mark.parametrize("replace", [None, False])
@mark.parametrize("case", ["double-import", "same-module", "different-class"])
def test_collision_documentation_section(
    tmp_path: Path, replace: bool | None, case: str
) -> None:
    script = tmp_path / "my_app.py"
    script.write_text(
        dedent("""\
        import importlib
        from dataclasses import dataclass
        import warnings
        from hydra.core.config_store import ConfigStore
        from hydra.errors import Hydra15MigrationWarning

        @dataclass
        class Config:
            value: int = 1

        @dataclass
        class OtherConfig:
            value: int = 2

        cs = ConfigStore.instance()

        def register_again():
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always", Hydra15MigrationWarning)
                try:
                    cs.store(name="config", node=NODE, replace=REPLACE)
                except ValueError as error:
                    print(error)
                else:
                    print(caught[0].message)

        if __name__ == "__main__":
            cs.store(name="config", node=Config)
            if CASE == "same-module":
                register_again()
            else:
                importlib.import_module("my_app")
        else:
            register_again()
        """)
        .replace("NODE", "OtherConfig" if case == "different-class" else "Config")
        .replace("REPLACE", repr(replace))
        .replace("CASE", repr(case))
    )
    output, error = run_python_script([str(script)])
    assert not error
    section = (
        "registering-configs-in-the-main-script"
        if case == "double-import"
        else "choose-the-intended-behavior"
    )
    assert output.endswith(f"config_store_collisions#{section}")

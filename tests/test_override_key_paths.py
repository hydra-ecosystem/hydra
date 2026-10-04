# SPDX-FileCopyrightText: Contributors to Hydra
# SPDX-License-Identifier: MIT
import re
from pathlib import Path
from typing import Any

from omegaconf import DictConfig, OmegaConf
from pytest import mark, raises

from hydra import compose, initialize
from hydra._internal.config_loader_impl import ConfigLoaderImpl
from hydra._internal.core_plugins.basic_sweeper import BasicSweeper
from hydra._internal.utils import create_config_search_path
from hydra.core.config_store import ConfigStore
from hydra.core.override_parser.overrides_parser import OverridesParser
from hydra.errors import ConfigCompositionException, OverrideParseException
from hydra.test_utils.test_utils import run_python_script
from hydra.types import RunMode


@mark.parametrize(
    "input_cfg,override,expected",
    [
        ({"items": [1, 2]}, "items[0]=3", {"items": [3, 2]}),
        ({"items": [1, 2]}, "items[-1]=3", {"items": [1, 3]}),
        ({"items": [1, 2]}, "++items[0]=3", {"items": [3, 2]}),
        ({"items": [None, 2]}, "+items[0]=3", {"items": [3, 2]}),
        ({"items": [1, 2]}, "~items[0]", {"items": [2]}),
        ({"items": [1, 2]}, "~items[-1]=2", {"items": [1]}),
        ({"items": [None, 2]}, "~items[0]=null", {"items": [2]}),
        ({"items": ["???", 2]}, "~items[0]=???", {"items": [2]}),
        ({"obj": {"20s_labels": 1}}, "obj[20s_labels]=2", {"obj": {"20s_labels": 2}}),
        ({"obj": {}}, "+obj[20s_labels]=2", {"obj": {"20s_labels": 2}}),
        ({"obj": {}}, "++obj[20s_labels]=2", {"obj": {"20s_labels": 2}}),
        ({"obj": {"20s_labels": 1}}, "~obj[20s_labels]=1", {"obj": {}}),
        ({"obj": {"20s_labels": "???"}}, "~obj[20s_labels]", {"obj": {}}),
        ({"obj": {"20s_labels": None}}, "~obj[20s_labels]=null", {"obj": {}}),
        (
            {"items": [{"nested": [1, 2]}]},
            "items[0].nested[-1]=3",
            {"items": [{"nested": [1, 3]}]},
        ),
        ({"items": [[1, 2]]}, "~items[0][-1]", {"items": [[1]]}),
        ({"items": [{"a": 1}]}, "+items[0]={b:2}", {"items": [{"a": 1, "b": 2}]}),
        ({"items": [[1, 2]]}, "+items[0]=[3]", {"items": [[3]]}),
        ({"obj": {"0": 1, "-1": 2}}, "~obj[-1]", {"obj": {"0": 1}}),
        ({"obj": {"0": 1, "-1": 2}}, "obj[0]=3", {"obj": {"0": 3, "-1": 2}}),
        ({"obj": {0: 1, -1: 2}}, "~obj[-1]=2", {"obj": {0: 1}}),
        ({"obj": {0: 1, -1: 2}}, "obj[0]=3", {"obj": {0: 3, -1: 2}}),
        ({"obj": {0: "???"}}, "~obj[0]", {"obj": {}}),
        ({"obj": {0: "${target}"}, "target": 1}, "~obj[0]=1", {"obj": {}, "target": 1}),
        (
            {"items": [1, 2], "alias": "${items}"},
            "~alias[-1]",
            {"items": [1], "alias": "${items}"},
        ),
        (
            {"items": ["${target}"], "target": 1},
            "~items[0]=1",
            {"items": [], "target": 1},
        ),
    ],
)
def test_bracket_value_operations(input_cfg: Any, override: str, expected: Any) -> None:
    cfg = OmegaConf.create(input_cfg)
    OmegaConf.set_struct(cfg, True)
    assert isinstance(cfg, DictConfig)
    parsed = OverridesParser.create().parse_overrides([override])
    assert parsed[0].is_value_path
    ConfigLoaderImpl._apply_overrides_to_config(parsed, cfg)
    assert OmegaConf.to_container(cfg, resolve=False) == expected


@mark.parametrize(
    "input_cfg,override,error",
    [
        ({"items": [1]}, "+items[0]=2", "Could not append to config"),
        ({"items": [1]}, "~items[0]=2", "is 1 and not 2"),
        ({"items": [1]}, "items[1]=2", "Error merging override"),
        ({"items": [1]}, "+items[1]=2", "Error merging override"),
        ({"items": [1]}, "++items[1]=2", "Error merging override"),
        ({"items": [1]}, "items[-2]=2", "Error merging override"),
        ({"items": [1]}, "~items[1]", "does not exist"),
        ({"items": [1]}, "~items[abc]", "does not exist"),
        ({"items": [{"field": 1}]}, "~items[abc].field", "does not exist"),
        ({"items": [{"field": 1}]}, "~items[-].field", "does not exist"),
        ({"obj": {}}, "obj[20s_labels]=2", "Could not override"),
        ({"obj": {}}, "~obj[20s_labels]", "does not exist"),
        ({"obj": None}, "~obj[20s_labels]", "does not exist"),
        ({"obj": "???"}, "~obj[20s_labels]", "does not exist"),
    ],
)
def test_bracket_value_operation_errors(
    input_cfg: Any, override: str, error: str
) -> None:
    cfg = OmegaConf.create(input_cfg)
    OmegaConf.set_struct(cfg, True)
    assert isinstance(cfg, DictConfig)
    parsed = OverridesParser.create().parse_overrides([override])
    with raises(ConfigCompositionException, match=error):
        ConfigLoaderImpl._apply_overrides_to_config(parsed, cfg)
    assert OmegaConf.to_container(cfg, resolve=False) == input_cfg


def test_delete_resolves_value_once() -> None:
    calls = []

    def resolver() -> int:
        calls.append(True)
        return 1

    OmegaConf.register_resolver("key_path_probe", resolver)
    try:
        cfg = OmegaConf.create({"items": ["${key_path_probe:}"]})
        parsed = OverridesParser.create().parse_overrides(["~items[0]=1"])
        ConfigLoaderImpl._apply_overrides_to_config(parsed, cfg)
        assert cfg == {"items": []}
        assert calls == [True]
    finally:
        OmegaConf.clear_resolver("key_path_probe")


def test_bracket_hydra_keys(hydra_restore_singletons: Any, tmp_path: Path) -> None:
    loader = ConfigLoaderImpl(create_config_search_path(None))
    parser = OverridesParser.create()
    overrides = ["hydra[mode]=MULTIRUN"]
    assert (
        loader.get_mode(None, overrides, parser.parse_overrides(overrides))
        == "MULTIRUN"
    )
    parsed = parser.parse_overrides(["hydra[verbose]=true,false"])
    with raises(
        ConfigCompositionException, match="Sweeping over Hydra's configuration"
    ):
        loader.validate_sweep_overrides_legal(
            parsed, RunMode.MULTIRUN, from_shell=False
        )

    OmegaConf.save({"from_searchpath": True}, tmp_path / "extra.yaml")
    ConfigStore.instance().store(
        name="bracket_searchpath", node={"defaults": ["extra"]}
    )
    searchpath_override = "hydra[searchpath]=[" + "file://" + tmp_path.as_posix() + "]"
    with initialize(config_path=None):
        cfg = compose(
            config_name="bracket_searchpath",
            overrides=[searchpath_override],
            return_hydra_config=True,
        )
    assert cfg.from_searchpath is True
    assert searchpath_override in cfg.hydra.overrides.hydra
    assert searchpath_override not in cfg.hydra.overrides.task


@mark.parametrize(
    "key",
    [
        "items[0",
        "items[]",
        "items[0]junk",
        "[0]",
        "items[0]@pkg",
        "items[0]@",
        "group@items[0]",
        "group/items[0]",
        "obj[a.b]",
        "obj[a,b]",
        "obj[a@b]",
        "obj[a/b]",
        "obj[a=b]",
        "obj[a b]",
        "obj['a']",
        "obj[a][b",
        "obj[a]..b",
    ],
)
def test_reject_invalid_bracket_keys(key: str) -> None:
    with raises(OverrideParseException):
        OverridesParser.create().parse_overrides([key + "=x"])


@mark.parametrize(
    "key", ["items[0]", "items[-1]", "obj[20s_labels]", "items[0].nested[1]"]
)
@mark.parametrize("value", ["x,y", "choice(x,y)", "range(1,3)"])
def test_bracket_sweep_round_trip(key: str, value: str) -> None:
    parser = OverridesParser.create()
    parsed = parser.parse_overrides([key + "=" + value])
    batches = BasicSweeper.split_arguments(parsed, max_batch_size=None)
    assert len(batches) == 1 and len(batches[0]) == 2
    for job in batches[0]:
        override = parser.parse_overrides(job)[0]
        assert override.key_or_group == key and override.is_value_path
        assert not override.is_sweep_override()


@mark.parametrize(
    "override,items,obj",
    [
        ("items[0]=changed", ["changed", "last"], {"20s_labels": "original"}),
        ("++items[0]=changed", ["changed", "last"], {"20s_labels": "original"}),
        ("~items[0]=first", ["last"], {"20s_labels": "original"}),
        ("items[-1]=changed", ["first", "changed"], {"20s_labels": "original"}),
        ("obj[20s_labels]=changed", ["first", "last"], {"20s_labels": "changed"}),
        ("~obj[20s_labels]", ["first", "last"], {}),
    ],
)
def test_bracket_paths_do_not_override_groups(
    hydra_restore_singletons: Any, override: str, items: list[str], obj: dict[str, str]
) -> None:
    cs = ConfigStore.instance()
    for index, group in enumerate(["items[0]", "items[-1]", "obj[20s_labels]"]):
        cs.store(
            group=group,
            name="selected",
            node={f"group_{index}": True},
            package="_global_",
        )
    cs.store(group="db", name="mysql", node={"driver": "mysql"})
    cs.store(group="db", name="sqlite", node={"driver": "sqlite"})
    cs.store(
        name="bracket_paths",
        node={
            "defaults": [
                {"items[0]": "selected"},
                {"items[-1]": "selected"},
                {"obj[20s_labels]": "selected"},
                {"db@backup": "mysql"},
                "_self_",
            ],
            "items": ["first", "last"],
            "obj": {"20s_labels": "original"},
        },
    )
    with initialize(config_path=None):
        cfg = compose(
            config_name="bracket_paths", overrides=[override, "db@backup=sqlite"]
        )
    assert cfg == {
        "items": items,
        "obj": obj,
        "group_0": True,
        "group_1": True,
        "group_2": True,
        "backup": {"driver": "sqlite"},
    }


@mark.parametrize(
    "overrides,expected",
    [
        (
            ["items[0]=changed"],
            {"items": ["changed", "last"], "obj": {"20s_labels": "original"}},
        ),
        (
            ["~items[-1]", "obj[20s_labels]=changed"],
            {"items": ["first"], "obj": {"20s_labels": "changed"}},
        ),
    ],
)
def test_bracket_paths_cli(tmp_path: Path, overrides: list[str], expected: Any) -> None:
    OmegaConf.save(
        {"items": ["first", "last"], "obj": {"20s_labels": "original"}},
        tmp_path / "paths.yaml",
    )
    stdout, _ = run_python_script(
        [
            "tests/test_apps/simple_app/my_app.py",
            "--config-dir",
            str(tmp_path),
            "--config-name",
            "paths",
            "--cfg",
            "job",
            *overrides,
        ]
    )
    assert OmegaConf.create(stdout) == expected


@mark.parametrize(
    "override", ["items[0]=x,y", "items[-1]=choice(x,y)", "obj[20s_labels]=x,y"]
)
def test_bracket_paths_cli_multirun(tmp_path: Path, override: str) -> None:
    OmegaConf.save(
        {"items": ["first", "last"], "obj": {"20s_labels": "original"}},
        tmp_path / "paths.yaml",
    )
    run_python_script(
        [
            "tests/test_apps/simple_app/my_app.py",
            "--config-dir",
            str(tmp_path),
            "--config-name",
            "paths",
            "--multirun",
            override,
            "hydra.sweep.dir=" + str(tmp_path / "output"),
            "hydra.job.chdir=False",
        ]
    )
    for index, value in enumerate(["x", "y"]):
        cfg = OmegaConf.load(
            tmp_path / "output" / str(index) / ".hydra" / "config.yaml"
        )
        key = override.split("=", 1)[0]
        assert OmegaConf.select(cfg, key) == value
        recorded = OmegaConf.load(
            tmp_path / "output" / str(index) / ".hydra" / "overrides.yaml"
        )
        assert any(
            re.match(re.escape(key) + "=" + value + "$", line) for line in recorded
        )

# SPDX-FileCopyrightText: Contributors to Hydra
# SPDX-License-Identifier: MIT
import re
from pathlib import Path
from typing import Any

from omegaconf import DictConfig, OmegaConf
from pytest import mark, raises, warns

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


@mark.parametrize("key", ["hydra.searchpath", "hydra[searchpath]"])
def test_searchpath_list_extension(
    hydra_restore_singletons: Any, tmp_path: Path, key: str
) -> None:
    OmegaConf.save({"from_searchpath": True}, tmp_path / "extra.yaml")
    ConfigStore.instance().store(
        name="extended_searchpath", node={"defaults": ["extra"]}
    )
    path = "file://" + tmp_path.as_posix()
    override = f"{key}=extend_list('{path}')"
    with initialize(config_path=None):
        with warns(UserWarning, match="extend_list"):
            cfg = compose(
                config_name="extended_searchpath",
                overrides=[override],
                return_hydra_config=True,
            )
    assert cfg.from_searchpath is True
    assert cfg.hydra.searchpath == [path]
    assert override in cfg.hydra.overrides.hydra


@mark.parametrize(
    "key",
    [
        "items[0",
        "items[]",
        "items[0]junk",
        "[0]",
        "0[0]",
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
    "key",
    [
        "items[0]",
        "items[-1]",
        "obj[20s_labels]",
        "items[0].nested[1]",
        r"obj.a\.b",
        r"obj.a\[0\]",
        r"obj.a\=b",
        r"items[0][a\.b]",
    ],
)
@mark.parametrize("value", ["x,y", "choice(x,y)", "range(1,3)"])
def test_value_path_sweep_round_trip(key: str, value: str) -> None:
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


@mark.parametrize(
    "key,literal",
    [
        (r"obj.a\.b", "a.b"),
        (r"obj[a\.b]", "a.b"),
        (r"obj.a\[0\]", "a[0]"),
        (r"obj[a\[0\]]", "a[0]"),
        (r"obj.a\=b", "a=b"),
        (r"obj[a\=b]", "a=b"),
        (r"obj.a\]b", "a]b"),
        (r"obj.\.", "."),
    ],
)
@mark.parametrize(
    "before,prefix,suffix,after",
    [
        ({"value": 1}, "", "=2", {"value": 2}),
        ({}, "+", "=2", {"value": 2}),
        ({}, "++", "=2", {"value": 2}),
        ({"value": 1}, "++", "=2", {"value": 2}),
        ({"value": None}, "+", "=2", {"value": 2}),
        ({"value": 1}, "~", "", {}),
        ({"value": 1}, "~", "=1", {}),
        ({"value": None}, "~", "=null", {}),
        ({"value": "???"}, "~", "=???", {}),
        ({"value": "${target}"}, "~", "=1", {}),
    ],
)
def test_escaped_key_operations(
    key: str, literal: str, before: Any, prefix: str, suffix: str, after: Any
) -> None:
    cfg = OmegaConf.create({"obj": {literal: v for v in before.values()}, "target": 1})
    OmegaConf.set_struct(cfg, True)
    override = prefix + key + suffix
    parsed = OverridesParser.create().parse_overrides([override])
    assert parsed[0].is_value_path
    assert parsed[0].key_or_group == key
    assert parsed[0].get_key_element() == prefix + key
    assert parsed[0].input_line == override
    ConfigLoaderImpl._apply_overrides_to_config(parsed, cfg)
    assert OmegaConf.to_container(cfg, resolve=False) == {
        "obj": {literal: v for v in after.values()},
        "target": 1,
    }


@mark.parametrize(
    "key,prefix",
    [
        (r"obj.a\=b", ""),
        (r"obj.a\=b", "+"),
        (r"obj.a\=b", "++"),
        (r"obj.a\=b", "~"),
        (r"obj[a\=b]", ""),
        (r"obj[a\=b]", "+"),
        (r"obj[a\=b]", "++"),
        (r"obj[a\=b]", "~"),
    ],
)
@mark.parametrize("value", [r"value\=with\=equals", "'value=with=equals'"])
def test_get_value_string_skips_escaped_equals_in_key(
    key: str, prefix: str, value: str
) -> None:
    override = prefix + key + "=" + value
    parsed = OverridesParser.create().parse_overrides([override])[0]
    assert parsed.get_value_string() == value


@mark.parametrize("key", [r"obj.a\=b", r"obj[a\=b]"])
def test_get_value_string_delete_without_separator(key: str) -> None:
    override = "~" + key
    parsed = OverridesParser.create().parse_overrides([override])[0]
    with raises(ValueError, match=re.escape(f"No value component in {override}")):
        parsed.get_value_string()


@mark.parametrize(
    "input_cfg,override,expected",
    [
        ({"a.b": 1}, r"a\.b=2", {"a.b": 2}),
        ({"a[0]": 1}, r"~a\[0\]=1", {}),
        ({"a=b": 1}, r"a\=b=2", {"a=b": 2}),
        ({"a=b": 1}, r"~a\=b", {}),
        ({"0": {"a.b": 1}}, r"0.a\.b=2", {"0": {"a.b": 2}}),
        ({"a.b": [{"c=d": 1}]}, r"a\.b[0].c\=d=2", {"a.b": [{"c=d": 2}]}),
        (
            {"items": [{"a.b": [1, 2]}]},
            r"~items[0][a\.b][-1]",
            {"items": [{"a.b": [1]}]},
        ),
        (
            {"obj": {"a.b": 1}, "alias": "${obj}"},
            r"~alias.a\.b=1",
            {"obj": {}, "alias": "${obj}"},
        ),
    ],
)
def test_escaped_nested_paths(input_cfg: Any, override: str, expected: Any) -> None:
    cfg = OmegaConf.create(input_cfg)
    parsed = OverridesParser.create().parse_overrides([override])
    ConfigLoaderImpl._apply_overrides_to_config(parsed, cfg)
    assert OmegaConf.to_container(cfg, resolve=False) == expected


@mark.parametrize("key", [r"obj.a\.b", r"obj[a\=b]", r"obj.a\[0\]"])
@mark.parametrize(
    "before,prefix,suffix,error",
    [
        ({"value": 1}, "+", "=2", "Could not append"),
        ({"value": 1}, "~", "=2", "is 1 and not 2"),
        ({}, "", "=2", "Could not override"),
        ({}, "~", "", "does not exist"),
    ],
)
def test_escaped_key_operation_errors(
    key: str, before: Any, prefix: str, suffix: str, error: str
) -> None:
    literal = {r"obj.a\.b": "a.b", r"obj[a\=b]": "a=b", r"obj.a\[0\]": "a[0]"}[key]
    original = {"obj": {literal: v for v in before.values()}}
    cfg = OmegaConf.create(original)
    OmegaConf.set_struct(cfg, True)
    parsed = OverridesParser.create().parse_overrides([prefix + key + suffix])
    with raises(ConfigCompositionException, match=error):
        ConfigLoaderImpl._apply_overrides_to_config(parsed, cfg)
    assert OmegaConf.to_container(cfg, resolve=False) == original


@mark.parametrize(
    "key",
    [
        r"obj.a\q",
        "obj.a\\",
        r"obj.a\\b",
        r"obj.a\,b",
        r"obj.a\ b",
        r"obj[a\.b",
        r"obj.a\.b@pkg",
        r"obj/a\.b",
        r"group@a\.b",
        r"obj[a\.b]@pkg",
        r"obj[a\.b]tail",
        r"obj.a\.b..c",
        r"obj.a\.b/a",
        r"obj.a\.b,c",
        r"obj['a\.b']",
    ],
)
def test_reject_invalid_escaped_keys(key: str) -> None:
    with raises(OverrideParseException):
        OverridesParser.create().parse_overrides([key + "=x"])


@mark.parametrize(
    "key,literal", [(r"obj.a\.b", "a.b"), (r"obj.a\[0\]", "a[0]"), (r"obj.a\=b", "a=b")]
)
@mark.parametrize(
    "prefix,suffix,before,after",
    [
        ("", "=changed", {"value": "original"}, {"value": "changed"}),
        ("+", "=changed", {}, {"value": "changed"}),
        ("++", "=changed", {"value": "original"}, {"value": "changed"}),
        ("~", "", {"value": "original"}, {}),
    ],
)
def test_escaped_paths_do_not_override_groups(
    hydra_restore_singletons: Any,
    key: str,
    literal: str,
    prefix: str,
    suffix: str,
    before: Any,
    after: Any,
) -> None:
    cs = ConfigStore.instance()
    cs.store(
        group=key, name="selected", node={"group_loaded": True}, package="_global_"
    )
    cs.store(group="db", name="mysql", node={"driver": "mysql"})
    cs.store(group="db", name="sqlite", node={"driver": "sqlite"})
    cs.store(
        name="escaped_paths",
        node={
            "defaults": [{"db@backup": "mysql"}, "_self_"],
            "obj": {literal: v for v in before.values()},
        },
    )
    with initialize(config_path=None):
        cfg = compose(
            config_name="escaped_paths",
            overrides=[prefix + key + suffix, "db@backup=sqlite"],
        )
    assert cfg == {
        "obj": {literal: v for v in after.values()},
        "backup": {"driver": "sqlite"},
    }


def test_escaped_hydra_root_is_task_key(hydra_restore_singletons: Any) -> None:
    parser = OverridesParser.create()
    overrides = [r"++hydra\.mode=MULTIRUN", r"++hydra\.searchpath=[]"]
    parsed = parser.parse_overrides(overrides)
    assert all(not override.is_hydra_override() for override in parsed)
    loader = ConfigLoaderImpl(create_config_search_path(None))
    assert loader.get_mode(None, overrides, parsed) is None
    loader.validate_sweep_overrides_legal(
        parser.parse_overrides([r"hydra\.mode=x,y"]), RunMode.MULTIRUN, from_shell=False
    )
    with initialize(config_path=None):
        cfg = compose(overrides=overrides, return_hydra_config=True)
    assert cfg["hydra.mode"] == "MULTIRUN" and cfg["hydra.searchpath"] == []
    assert cfg.hydra.overrides.task == overrides
    assert cfg.hydra.overrides.hydra == []


@mark.parametrize(
    "key,literal", [(r"obj.a\.b", "a.b"), (r"obj.a\[0\]", "a[0]"), (r"obj.a\=b", "a=b")]
)
def test_escaped_paths_cli(tmp_path: Path, key: str, literal: str) -> None:
    OmegaConf.save({"obj": {literal: "original"}}, tmp_path / "paths.yaml")
    app_args = [
        "tests/test_apps/simple_app/my_app.py",
        "--config-dir",
        str(tmp_path),
        "--config-name",
        "paths",
    ]
    stdout, _ = run_python_script([*app_args, "--cfg", "job", key + "=changed"])
    assert OmegaConf.create(stdout) == {"obj": {literal: "changed"}}
    run_python_script(
        [
            *app_args,
            "--multirun",
            key + "=x,y",
            "hydra.sweep.dir=" + str(tmp_path / "output"),
            "hydra.job.chdir=False",
        ]
    )
    for index, value in enumerate(["x", "y"]):
        job_dir = tmp_path / "output" / str(index) / ".hydra"
        assert OmegaConf.load(job_dir / "config.yaml") == {"obj": {literal: value}}
        recorded = OmegaConf.load(job_dir / "overrides.yaml")
        assert key + "=" + value in recorded
        reparsed = OverridesParser.create().parse_overrides(list(recorded))
        assert reparsed[0].key_or_group == key and reparsed[0].value() == value

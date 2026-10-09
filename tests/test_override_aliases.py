# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved
from pathlib import Path
from typing import Any

import pytest
from omegaconf import OmegaConf

from hydra import compose, initialize_config_dir
from hydra._internal.config_loader_impl import ConfigLoaderImpl
from hydra._internal.hydra import Hydra
from hydra._internal.override_aliases import OverrideAliases
from hydra._internal.utils import create_config_search_path
from hydra.core.plugins import Plugins
from hydra.errors import (
    ConfigCompositionException,
    MissingConfigException,
    OverrideParseException,
)
from hydra.plugins.completion_plugin import DefaultCompletionPlugin
from hydra.test_utils.test_utils import run_python_script, run_with_error
from hydra.types import RunMode

pytestmark = pytest.mark.usefixtures("hydra_restore_singletons")

# Capture built-in registrations in the singleton baseline restored by tests.
Plugins.instance()


@pytest.fixture
def configs(tmp_path: Path) -> Path:
    OmegaConf.save(
        OmegaConf.create(
            {
                "defaults": [{"config@_global_": None}, "_self_"],
                "trainer": {"batch_size": 8},
                "batch_size": 1,
                "verbose": False,
                "action": "train",
                "step": 2,
                "hydra": {
                    "override": {
                        "aliases": {
                            "batch_size, bs": "trainer.batch_size",
                            "config": "config@_global_",
                            "verbose,v": "verbose=true",
                            "check": "action=check",
                            "multi": "hydra.mode=MULTIRUN",
                            "added": "trainer.new",
                        }
                    }
                },
            }
        ),
        tmp_path / "aliases.yaml",
    )
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "user.yaml").write_text("selected: user\n")
    return tmp_path


def loader(configs: Path) -> ConfigLoaderImpl:
    return ConfigLoaderImpl(create_config_search_path(str(configs)))


@pytest.mark.parametrize(
    "original, expanded",
    [
        ("batch_size=32", "trainer.batch_size=32"),
        ("bs=16,32", "trainer.batch_size=16,32"),
        ("bs=range(1,5)", "trainer.batch_size=range(1,5)"),
        ("bs=", "trainer.batch_size="),
        ("+bs=32", "+trainer.batch_size=32"),
        ("++bs=32", "++trainer.batch_size=32"),
        ("~bs", "~trainer.batch_size"),
        ("~bs=32", "~trainer.batch_size=32"),
        ("config=user", "config@_global_=user"),
        ("config@other=user", "config@other=user"),
        ("verbose", "verbose=true"),
        ("v", "verbose=true"),
        ("+v", "+verbose=true"),
        ("++v", "++verbose=true"),
        ("~v", "~verbose=true"),
        ("verbose=false", "verbose=false"),
        ("verbose=true,false", "verbose=true,false"),
        ("check", "action=check"),
        ("check=other", "check=other"),
        ("bs.child=32", "bs.child=32"),
        (r"obj[a\=b]=x", r"obj[a\=b]=x"),
        ("bs='a=b,c'", "trainer.batch_size='a=b,c'"),
    ],
)
def test_expansion(configs: Path, original: str, expanded: str) -> None:
    assert loader(configs).get_override_aliases("aliases").expand(original) == expanded


@pytest.mark.parametrize("original", ["bs", "+bs", "++bs", "config"])
def test_missing_alias_value(configs: Path, original: str) -> None:
    with pytest.raises(ConfigCompositionException) as exc_info:
        loader(configs).parse_overrides("aliases", [original])
    assert str(exc_info.value) == (
        f"Override alias '{original.lstrip('+')}' requires a value for '{original}'"
    )


def test_alias_preserves_composition_exception(configs: Path) -> None:
    with pytest.raises(MissingConfigException) as direct_info:
        loader(configs).load_configuration(
            "aliases", ["config@_global_=missing"], RunMode.RUN
        )
    with pytest.raises(MissingConfigException) as alias_info:
        loader(configs).load_configuration("aliases", ["config=missing"], RunMode.RUN)

    direct = direct_info.value
    aliased = alias_info.value
    assert type(aliased) is type(direct)
    assert aliased.missing_cfg_file == direct.missing_cfg_file
    assert aliased.options == direct.options
    assert "Alias expansion:\n  'config=missing' -> 'config@_global_=missing'" in str(
        aliased
    )


@pytest.mark.parametrize(
    "definitions",
    [
        [],
        {"": "x"},
        {"a,": "x"},
        {"a,a": "x"},
        {"a,b": "x", "b": "y"},
        {"a": 1},
        {"a": "${target}"},
        {"a": "x=" + "${target}"},
        {"a": "x["},
        {"a=1": "x"},
        {"+a": "x"},
        {"a": "+x"},
    ],
)
def test_invalid_definitions(definitions: Any) -> None:
    config = OmegaConf.create({"hydra": {"override": {"aliases": definitions}}})
    with pytest.raises(ConfigCompositionException):
        OverrideAliases.from_config(config)


def test_interpolated_hydra_ancestor_rejected() -> None:
    config = OmegaConf.create(
        {
            "defs": {"override": {"aliases": {"a": "x"}}},
            "hydra": "${defs}",
        }
    )
    with pytest.raises(
        ConfigCompositionException, match="Override alias definitions must be literal"
    ):
        OverrideAliases.from_config(config)


def test_interpolated_override_rejected_without_resolver_call() -> None:
    resolver_calls = 0

    def counting_resolver() -> dict[str, dict[str, str]]:
        nonlocal resolver_calls
        resolver_calls += 1
        return {"aliases": {"a": "x"}}

    resolver_name = "test_override_aliases_counting"
    OmegaConf.register_resolver(resolver_name, counting_resolver)
    try:
        config = OmegaConf.create({"hydra": {"override": f"${{{resolver_name}:}}"}})
        with pytest.raises(
            ConfigCompositionException,
            match="Override alias definitions must be literal",
        ):
            OverrideAliases.from_config(config)
        assert resolver_calls == 0
    finally:
        OmegaConf.clear_resolver(resolver_name)


def test_compose_and_history(configs: Path) -> None:
    with initialize_config_dir(str(configs)):
        cfg = compose(
            config_name="aliases",
            overrides=["bs=32", "verbose", "verbose=false", "config=user", "check"],
            return_hydra_config=True,
        )
    assert cfg.trainer.batch_size == 32
    assert cfg.batch_size == 1
    assert cfg.verbose is False
    assert cfg.selected == "user"
    assert cfg.action == "check"
    assert cfg.hydra.overrides.task == [
        "trainer.batch_size=32",
        "verbose=true",
        "verbose=false",
        "config@_global_=user",
        "action=check",
    ]


@pytest.mark.parametrize(
    "overrides, expected",
    [
        (["++added=1"], {"batch_size": 8, "new": 1}),
        (["+added=1"], {"batch_size": 8, "new": 1}),
        (["~bs"], {}),
        (["~bs=8"], {}),
    ],
)
def test_operators(configs: Path, overrides: list[str], expected: Any) -> None:
    cfg = loader(configs).load_configuration("aliases", overrides, RunMode.RUN)
    assert cfg.trainer == expected


def test_mode_alias(configs: Path) -> None:
    config_loader = loader(configs)
    parsed = config_loader.parse_overrides("aliases", ["multi", "bs=16,32"])
    assert (
        config_loader.get_mode("aliases", ["multi", "bs=16,32"], parsed) == "MULTIRUN"
    )
    cfg = config_loader.load_configuration(
        "aliases", ["multi", "bs=16,32"], RunMode.MULTIRUN
    )
    assert cfg.hydra.overrides.hydra == ["hydra.mode=MULTIRUN"]


def test_single_pass_and_sweep_replay(configs: Path) -> None:
    primary = OmegaConf.load(configs / "aliases.yaml")
    primary.hydra.override.aliases["trainer.batch_size"] = "step"
    OmegaConf.save(primary, configs / "aliases.yaml")
    config_loader = loader(configs)
    master = config_loader.load_configuration("aliases", ["bs=16,32"], RunMode.MULTIRUN)
    job = config_loader.load_sweep_config(master, ["trainer.batch_size=32"])
    assert job.trainer.batch_size == 32
    assert job.step == 2


@pytest.mark.parametrize(
    "override",
    [
        "hydra.override.aliases.check=step",
        "hydra.override={aliases:{check:step}}",
        "hydra={override:{aliases:{check:step}}}",
        "~hydra.override.aliases.check",
        "+hydra.override.aliases.new=step",
        "~hydra.override",
    ],
)
def test_cli_cannot_change_aliases(configs: Path, override: str) -> None:
    with pytest.raises(
        ConfigCompositionException, match="command-line overrides cannot change"
    ):
        loader(configs).load_configuration("aliases", [override], RunMode.RUN)


def test_aliases_in_defaults_include_rejected(configs: Path) -> None:
    (configs / "included.yaml").write_text("defaults:\n  - aliases\n")
    with pytest.raises(
        ConfigCompositionException, match="only be defined in the primary config"
    ):
        loader(configs).load_configuration("included", [], RunMode.RUN)


def test_diagnostics_preserve_input(configs: Path) -> None:
    with pytest.raises(
        ConfigCompositionException, match=r"'added=1' -> 'trainer.new=1'"
    ):
        loader(configs).load_configuration("aliases", ["added=1"], RunMode.RUN)
    with pytest.raises(OverrideParseException, match="Alias expansion: 'bs="):
        loader(configs).parse_overrides("aliases", ["bs=["])
    with pytest.raises(ValueError, match="'config=10' -> 'config@_global_=10'"):
        loader(configs).load_configuration("aliases", ["config=10"], RunMode.RUN)


def test_info_preserves_custom_loader_signature(configs: Path) -> None:
    class CustomLoader(ConfigLoaderImpl):
        def compute_defaults_list(self, config_name, overrides, run_mode):
            return super().compute_defaults_list(config_name, overrides, run_mode)

    hydra = Hydra("test", CustomLoader(create_config_search_path(str(configs))))
    hydra.show_info("defaults", "aliases", [])


@pytest.mark.parametrize(
    "word, expected",
    [
        ("b", ["batch_size=", "bs="]),
        ("v", ["v", "verbose", "verbose="]),
        ("bs=", ["bs=8"]),
        ("config=", ["config=user"]),
        ("+bs", ["+bs="]),
        ("~bs", ["~bs", "~bs="]),
    ],
)
def test_alias_completion(configs: Path, word: str, expected: list[str]) -> None:
    completion = DefaultCompletionPlugin(loader(configs))
    assert completion._query("aliases", word) == expected


def cli(configs: Path, *args: str) -> list[str]:
    return [
        "tests/test_apps/app_with_cfg_groups/my_app.py",
        "--config-dir",
        str(configs),
        "--config-name",
        "aliases",
        *args,
    ]


def test_info_aliases_without_composition(configs: Path) -> None:
    primary = OmegaConf.load(configs / "aliases.yaml")
    primary.defaults.insert(0, {"missing_group": "???"})
    OmegaConf.save(primary, configs / "aliases.yaml")
    out, err = run_python_script(
        cli(configs, "--info", "aliases", "bs=32", "verbose=false", "bs=[")
    )
    assert "bs -> trainer.batch_size=<value>" in out
    assert "bs=32 -> trainer.batch_size=32" in out
    assert "verbose=false -> verbose=false" in out
    assert "bs=[ -> trainer.batch_size=[" in out
    assert err == ""


def test_help_aliases(configs: Path) -> None:
    out, err = run_python_script(cli(configs, "--help", "check"))
    assert "== Override aliases ==" in out
    assert "check -> action=check" in out
    assert "action: check" in out
    assert err == ""


def test_cli_multirun_and_canonical_history(configs: Path) -> None:
    output = configs / "sweep"
    out, err = run_python_script(
        cli(configs, "multi", "bs=16,32", f"hydra.sweep.dir={output}")
    )
    assert "Launching 2 jobs locally" in out
    assert (
        OmegaConf.load(output / "0" / ".hydra" / "config.yaml").trainer.batch_size == 16
    )
    assert OmegaConf.load(output / "1" / ".hydra" / "overrides.yaml") == [
        "trainer.batch_size=32"
    ]
    assert err == ""


def test_cli_error_names_alias(configs: Path) -> None:
    err = run_with_error(cli(configs, "added=1"))
    assert "'added=1' -> 'trainer.new=1'" in err


@pytest.mark.parametrize("new_overrides, expected", [([], 32), (["bs=64"], 64)])
@pytest.mark.parametrize(
    "inspection",
    [[], ["--cfg", "job"], ["--help"], ["--info", "config"], ["--info", "aliases"]],
)
def test_rerun_does_not_expand_saved_overrides(
    configs: Path, new_overrides: list[str], expected: int, inspection: list[str]
) -> None:
    output = configs / "job"
    run_python_script(cli(configs, "bs=32", f"hydra.run.dir={output}"))
    primary = OmegaConf.load(configs / "aliases.yaml")
    primary.hydra.override.aliases["trainer.batch_size"] = "step"
    OmegaConf.save(primary, configs / "aliases.yaml")
    out, err = run_python_script(
        [
            "tests/test_apps/app_with_cfg_groups/my_app.py",
            "--config-dir",
            str(configs),
            "--experimental-rerun",
            str(output),
            *inspection,
            *new_overrides,
        ]
    )
    if inspection == ["--info", "aliases"]:
        assert "trainer.batch_size=32 -> trainer.batch_size=32" in out
        if new_overrides:
            assert "bs=64 -> trainer.batch_size=64" in out
    elif inspection:
        assert f"batch_size: {expected}" in out
        assert "step: 2" in out
    else:
        saved = OmegaConf.load(output / ".hydra" / "config.yaml")
        assert saved.trainer.batch_size == expected
        assert saved.step == 2
    assert err == ""

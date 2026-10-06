# SPDX-FileCopyrightText: Contributors to Hydra
# SPDX-License-Identifier: MIT
from pathlib import Path
from typing import Any

from omegaconf import OmegaConf
from pytest import mark, raises

from hydra import compose, initialize, initialize_config_dir
from hydra._internal.config_loader_impl import ConfigLoaderImpl
from hydra._internal.core_plugins.basic_sweeper import BasicSweeper
from hydra.core.default_element import ConfigDefault, GroupDefault
from hydra.core.override_parser.overrides_parser import OverridesParser
from hydra.errors import ConfigCompositionException, InstantiationException
from hydra.test_utils.test_utils import run_python_script
from hydra.utils import instantiate


@mark.parametrize(
    "spelling,expected",
    [
        (r"\???", "???"),
        (r"\\\\???", r"\???"),
        (r"'\???'", "???"),
        (r'"\???"', "???"),
        (r"'\\???'", r"\???"),
        (r'"\\???"', r"\???"),
    ],
)
def test_literal_override_composition(spelling: str, expected: str) -> None:
    with initialize(config_path=None):
        cfg = compose(overrides=[f"+value={spelling}", "+alias=${value}"])
    for resolved in (False, True):
        if resolved:
            OmegaConf.resolve(cfg)
        assert cfg.value == cfg.alias == expected
        assert not OmegaConf.is_missing(cfg.value)
        reloaded = OmegaConf.create(OmegaConf.to_yaml(cfg, resolve=resolved))
        assert reloaded.value == reloaded.alias == expected
        assert not OmegaConf.is_missing(reloaded, "value")
        assert not OmegaConf.is_missing(reloaded, "alias")


@mark.parametrize("spelling", ["???", "'???'", '"???"'])
def test_unescaped_override_is_missing(spelling: str) -> None:
    with initialize(config_path=None):
        cfg = compose(overrides=[f"+value={spelling}"])
    assert OmegaConf.is_missing(cfg, "value")
    assert OmegaConf.is_missing(OmegaConf.create(OmegaConf.to_yaml(cfg)), "value")


def test_nested_resolver_after_composition() -> None:
    OmegaConf.register_resolver("missing_literal_identity", lambda value: value)
    try:
        with initialize(config_path=None):
            cfg = compose(
                overrides=[
                    r"+value=\???",
                    "+nested='${missing_literal_identity:${missing_literal_identity:${value}}}'",
                ]
            )
        for resolved in (False, True):
            if resolved:
                OmegaConf.resolve(cfg)
            assert cfg.nested == "???"
            assert not OmegaConf.is_missing(cfg.nested)
    finally:
        OmegaConf.clear_resolver("missing_literal_identity")


@mark.parametrize("partial", [False, True])
@mark.parametrize("source", ["config", "scalar", "container"])
def test_instantiate_literal_missing_text(partial: bool, source: str) -> None:
    cfg = OmegaConf.create({"_target_": "builtins.dict", "_partial_": partial})
    literal = OmegaConf.create({"value": r"\???"}).value
    overrides = {}
    if source == "config":
        cfg.value = literal
    elif source == "scalar":
        overrides["value"] = literal
    else:
        overrides["value"] = OmegaConf.create({"nested": literal})
    result = instantiate(cfg, _execution_whitelist_=["builtins.dict"], **overrides)
    if partial:
        result = result()
    value = result["value"]
    if source == "container":
        value = value.nested
    assert value == "???"
    assert not OmegaConf.is_missing(value)


@mark.parametrize("partial", [False, True])
def test_plain_callsite_missing_still_rejected(partial: bool) -> None:
    with raises(InstantiationException, match="cannot be an OmegaConf missing value"):
        instantiate({"_target_": "builtins.dict"}, value="???", _partial_=partial)


@mark.parametrize("default_type", [ConfigDefault, GroupDefault])
def test_defaults_missing_uses_omegaconf_semantics(default_type) -> None:
    literal = OmegaConf.create({"value": r"\???"}).value

    def make(value):
        return (
            default_type(path=value)
            if default_type is ConfigDefault
            else default_type(group="db", value=value)
        )

    assert make("???").is_missing()
    assert not make(literal).is_missing()


@mark.parametrize("form", ["direct", "interpolated", "options"])
def test_defaults_list_selects_literal_question_marks(
    tmp_path: Path, form: str
) -> None:
    group = tmp_path / "db"
    group.mkdir()
    (group / "???.yaml").write_text("selected: true\n")
    (tmp_path / "???.yaml").write_text("direct: true\n")
    defaults: list[Any] = [r"\???", {"db": r"\???"}, "_self_"]
    if form == "options":
        defaults[1] = {"db": [r"\???"]}
    if form == "interpolated":
        other = tmp_path / "other"
        other.mkdir()
        (other / "???.yaml").write_text("selected: true\n")
        defaults.insert(2, {"other": "${db}"})
    (tmp_path / "config.yaml").write_text(
        OmegaConf.to_yaml(OmegaConf.create({"defaults": defaults}))
    )
    with initialize_config_dir(config_dir=str(tmp_path)):
        cfg = compose(config_name="config")
    assert cfg.direct and cfg.db.selected
    if form == "interpolated":
        assert cfg.other.selected


def test_sweep_preserves_escaped_missing_values() -> None:
    parser = OverridesParser.create()
    overrides = parser.parse_overrides([r"+value=\???,\\\\???,'???'"])
    chunks = BasicSweeper.split_arguments(overrides, max_batch_size=None)
    assert len(chunks) == 1 and len(chunks[0]) == 3
    for override, expected in zip(chunks[0], ["???", r"\???", None]):
        with initialize(config_path=None):
            cfg = compose(overrides=override)
        if expected is None:
            assert OmegaConf.is_missing(cfg, "value")
        else:
            assert cfg.value == expected
            assert not OmegaConf.is_missing(cfg, "value")


@mark.parametrize(
    "value,spelling,matches",
    [
        (r"\???", r"\???", True),
        (r"\???", "???", False),
        ("???", r"\???", False),
        ("???", "???", True),
        (r"\\???", r"\\\\???", True),
    ],
)
def test_delete_distinguishes_missing_and_literal(value, spelling, matches) -> None:
    cfg = OmegaConf.create({"value": value})
    override = OverridesParser.create().parse_overrides([f"~value={spelling}"])
    if matches:
        ConfigLoaderImpl._apply_overrides_to_config(override, cfg)
        assert list(cfg.keys()) == []
    else:
        with raises(ConfigCompositionException, match="Could not delete from config"):
            ConfigLoaderImpl._apply_overrides_to_config(override, cfg)
        assert list(cfg.keys()) == ["value"]


def test_cli_output_and_saved_config_roundtrip(tmp_path: Path) -> None:
    script = tmp_path / "app.py"
    script.write_text(
        "import hydra\n"
        "from omegaconf import OmegaConf\n"
        "@hydra.main(config_path=None)\n"
        "def app(cfg):\n"
        "    print(OmegaConf.to_yaml(cfg))\n"
        "app()\n"
    )
    overrides = [r"+literal=\???", r"+backslash=\\\\???", "+missing=???"]
    output, _ = run_python_script(
        [str(script), *overrides, "--cfg", "job"], allow_warnings=True
    )
    cfg = OmegaConf.create(output)
    assert cfg.literal == "???" and cfg.backslash == r"\???"
    assert not OmegaConf.is_missing(cfg, "literal")
    assert OmegaConf.is_missing(cfg, "missing")
    run_python_script(
        [str(script), *overrides, f"hydra.run.dir={tmp_path / 'run'}"],
        allow_warnings=True,
    )
    saved = OmegaConf.load(tmp_path / "run/.hydra/config.yaml")
    assert OmegaConf.structural_equality(saved, cfg)

# SPDX-FileCopyrightText: Contributors to Hydra
# SPDX-License-Identifier: MIT
import json
import os
import shutil
from pathlib import Path
from typing import Any

from omegaconf import OmegaConf
from pytest import fixture, mark

from hydra._internal.utils import _get_rerun_overrides
from hydra.core.override_parser.overrides_parser import OverridesParser
from hydra.core.override_parser.types import Quote, QuotedString
from hydra.test_utils.test_utils import run_python_script


@fixture
def rerun_app(tmp_path: Path) -> Path:
    app_dir = tmp_path / "app"
    shutil.copytree("tests/test_apps/rerun", app_dir)
    return app_dir / "my_app.py"


@mark.parametrize("chdir", [False, True])
@mark.parametrize("redirect", [False, True])
def test_rerun_normal_job_execution(
    rerun_app: Path, tmp_path: Path, chdir: bool, redirect: bool
) -> None:
    original_dir = tmp_path / "original [job] café"
    run_python_script(
        [
            str(rerun_app),
            "--config-name=alternate",
            f"hydra.run.dir={json.dumps(str(original_dir), ensure_ascii=False)}",
            f"hydra.job.chdir={chdir}",
            "hydra.job_logging.formatters.simple.format='[JOB] %(message)s'",
            "foo=3",
            "db=mysql",
        ]
    )
    # The saved task config is not used.
    (original_dir / ".hydra" / "config.yaml").unlink()
    overrides = ["foo=4", "db=postgres"]
    output_dir = tmp_path / "redirect" if redirect else original_dir
    if redirect:
        overrides.append(f"hydra.run.dir={json.dumps(str(output_dir))}")
    stdout, _ = run_python_script(
        [str(rerun_app), "--experimental-rerun", str(original_dir)] + overrides
    )
    result = json.loads((output_dir / "result.json").read_text())
    assert result["config"] == {
        "foo": 4,
        "db": {"driver": "postgres", "postgres_only": 2},
    }
    assert result["config_name"] == "alternate"
    assert result["cwd"] == str(output_dir if chdir else Path.cwd())
    for event in ("on_run_start", "on_job_start", "on_job_end", "on_run_end"):
        assert stdout.count(event) == 1
    assert "on_job_end: COMPLETED" in stdout
    assert "[JOB] Running my_app" in stdout
    logs = (output_dir / "my_app.log").read_text()
    assert logs.count("[JOB] Running my_app") == (1 if redirect else 2)
    assert not list(original_dir.rglob("*.pickle"))
    saved_overrides = (output_dir / ".hydra" / "overrides.yaml").read_text()
    assert saved_overrides.index("foo=3") < saved_overrides.index("foo=4")


@mark.parametrize("stored_override", [[], ["foo=3"]])
def test_rerun_recomposes_current_defaults(
    rerun_app: Path, tmp_path: Path, stored_override: list[str]
) -> None:
    output_dir = tmp_path / "original"
    run_python_script(
        [str(rerun_app), "--config-name=alternate", f"hydra.run.dir={output_dir}"]
        + stored_override
    )
    config_file = rerun_app.parent / "alternate.yaml"
    config_file.write_text(config_file.read_text().replace("foo: 2", "foo: 7"))
    run_python_script([str(rerun_app), "--experimental-rerun", str(output_dir)])
    result = json.loads((output_dir / "result.json").read_text())
    assert result["config"]["foo"] == (3 if stored_override else 7)


def test_rerun_individual_sweep_job(rerun_app: Path, tmp_path: Path) -> None:
    sweep_dir = tmp_path / "sweep"
    run_python_script([str(rerun_app), "-m", f"hydra.sweep.dir={sweep_dir}", "foo=3,4"])
    job_dir = sweep_dir / "0"
    run_python_script([str(rerun_app), "--experimental-rerun", str(job_dir), "foo=5"])
    result = json.loads((job_dir / "result.json").read_text())
    assert result["config"]["foo"] == 5


def test_rerun_preserves_override_interpolations(
    rerun_app: Path, tmp_path: Path
) -> None:
    output_dir = tmp_path / "original"
    run_python_script(
        [str(rerun_app), f"hydra.run.dir={output_dir}", "foo=${db.mysql_only}"]
    )
    run_python_script(
        [
            str(rerun_app),
            "--experimental-rerun",
            str(output_dir),
            "db.mysql_only=6",
        ]
    )
    result = json.loads((output_dir / "result.json").read_text())
    assert result["config"]["foo"] == 6


@mark.parametrize(
    "suffix",
    [
        "unicode café",
        'embedded "quote"',
        "interior\\backslash",
        "trailing\\",
        "newline\npath",
        "tab\tpath",
        "carriage\rpath",
    ],
)
def test_rerun_output_dir_override_round_trips(
    tmp_path: Path, monkeypatch: Any, suffix: str
) -> None:
    job_dir = tmp_path / suffix

    def fake_load(path: Path) -> Any:
        if path.name == "hydra.yaml":
            return OmegaConf.create(
                {
                    "hydra": {
                        "job": {"config_name": "config"},
                        "overrides": {"hydra": []},
                    }
                }
            )
        return OmegaConf.create([])

    monkeypatch.setattr(OmegaConf, "load", fake_load)
    _, overrides = _get_rerun_overrides(str(job_dir))
    parsed = OverridesParser.create().parse_override(overrides[-1])
    assert parsed.value() == str(job_dir.resolve())


@mark.skipif(os.name != "posix", reason="backslash is a valid POSIX path character")
def test_rerun_reuses_original_dir_with_backslash(
    rerun_app: Path, tmp_path: Path
) -> None:
    original_dir = tmp_path / "original\\backslash"
    run_python_script(
        [
            str(rerun_app),
            f"hydra.run.dir={QuotedString(str(original_dir), Quote.double).with_quotes()}",
        ]
    )
    (original_dir / "result.json").unlink()

    run_python_script([str(rerun_app), "--experimental-rerun", str(original_dir)])

    assert (original_dir / "result.json").is_file()
    assert not (tmp_path / "original\\\\backslash" / "result.json").exists()


def test_rerun_rejects_config_name_override(rerun_app: Path, tmp_path: Path) -> None:
    output_dir = tmp_path / "original"
    run_python_script(
        [
            str(rerun_app),
            "--config-name=alternate",
            f"hydra.run.dir={output_dir}",
        ]
    )
    _, stderr = run_python_script(
        [
            str(rerun_app),
            "--experimental-rerun",
            str(output_dir),
            "--config-name=config",
        ],
        raise_exception=False,
        print_error=False,
    )
    assert "--experimental-rerun does not support --config-name" in stderr


@mark.parametrize(
    "overrides,error",
    [
        (["-m"], "does not support --multirun"),
        (["hydra.mode=MULTIRUN"], "hydra.mode changed during config composition"),
        (["foo=3,4"], "Ambiguous value for argument"),
        (["foo=wrong"], "could not be converted to Integer"),
    ],
)
def test_rerun_rejects_invalid_overrides(
    rerun_app: Path, tmp_path: Path, overrides: list[str], error: str
) -> None:
    output_dir = tmp_path / "original"
    run_python_script([str(rerun_app), f"hydra.run.dir={output_dir}"])
    _, stderr = run_python_script(
        [str(rerun_app), "--experimental-rerun", str(output_dir)] + overrides,
        raise_exception=False,
        print_error=False,
    )
    assert error in stderr


@mark.parametrize("input_kind", ["missing", "pickle"])
def test_rerun_requires_saved_yaml_metadata(
    rerun_app: Path, tmp_path: Path, input_kind: str
) -> None:
    path = tmp_path / input_kind
    if input_kind == "pickle":
        path.write_bytes(b"not a pickle")
    _, stderr = run_python_script(
        [str(rerun_app), "--experimental-rerun", str(path)],
        raise_exception=False,
        print_error=False,
    )
    assert "hydra.yaml" in stderr

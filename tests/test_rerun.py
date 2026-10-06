# SPDX-FileCopyrightText: Contributors to Hydra
# SPDX-License-Identifier: MIT
import json
import os
import shutil
from pathlib import Path
from typing import Any

from omegaconf import OmegaConf
from pytest import fixture, mark

from hydra.core.override_parser.types import Quote, QuotedString
from hydra.test_utils.test_utils import run_python_script


@fixture
def rerun_app(tmp_path: Path) -> Path:
    app_dir = tmp_path / "app"
    shutil.copytree("tests/test_apps/rerun", app_dir)
    return app_dir / "my_app.py"


def run_app(app: Path, *args: str) -> dict[str, Any]:
    stdout, _ = run_python_script([str(app), *args])
    return json.loads(stdout)


@mark.parametrize("redirect", [False, True])
def test_rerun_recomposes(rerun_app: Path, tmp_path: Path, redirect: bool) -> None:
    original_dir = tmp_path / "original [job] café"
    run_app(
        rerun_app,
        "--config-name=alternate",
        f"hydra.run.dir={json.dumps(str(original_dir), ensure_ascii=False)}",
        "hydra.job.chdir=true",
        "foo=3",
        "db=mysql",
    )
    # Rerun must compose without the saved task config.
    (original_dir / ".hydra" / "config.yaml").unlink()
    overrides = ["foo=4", "db=postgres"]
    output_dir = tmp_path / "redirect" if redirect else original_dir
    if redirect:
        overrides.append(f"hydra.run.dir={json.dumps(str(output_dir))}")
    result = run_app(rerun_app, "--experimental-rerun", str(original_dir), *overrides)
    assert result == {
        "config": {"foo": 4, "db": {"driver": "postgres", "postgres_only": 2}},
        "cwd": str(output_dir),
    }
    metadata = OmegaConf.load(output_dir / ".hydra" / "hydra.yaml")
    assert metadata.hydra.job.config_name == "alternate"


@mark.parametrize("stored_override", [[], ["foo=3"]])
def test_rerun_recomposes_current_defaults(
    rerun_app: Path, tmp_path: Path, stored_override: list[str]
) -> None:
    output_dir = tmp_path / "original"
    run_app(rerun_app, f"hydra.run.dir={output_dir}", *stored_override)
    config_file = rerun_app.parent / "config.yaml"
    config_file.write_text(config_file.read_text().replace("foo: 1", "foo: 7"))
    result = run_app(rerun_app, "--experimental-rerun", str(output_dir))
    assert result["config"]["foo"] == (3 if stored_override else 7)


@mark.parametrize("new_identity", [False, True])
def test_rerun_preserves_sweep_job_identity(
    rerun_app: Path, tmp_path: Path, new_identity: bool
) -> None:
    sweep_dir = tmp_path / "sweep"
    run_python_script(
        [
            str(rerun_app),
            "-m",
            f"hydra.sweep.dir={sweep_dir}",
            "foo=${hydra:job.num}",
            "db.mysql_only=${hydra:job.id}",
        ]
    )
    overrides = ["hydra.job.num=7", "hydra.job.id=resume"] if new_identity else []
    result = run_app(
        rerun_app, "--experimental-rerun", str(sweep_dir / "0"), *overrides
    )
    assert result["config"]["foo"] == (7 if new_identity else 0)
    assert result["config"]["db"]["mysql_only"] == ("resume" if new_identity else "0")


def test_rerun_preserves_override_interpolations(
    rerun_app: Path, tmp_path: Path
) -> None:
    output_dir = tmp_path / "original"
    run_app(rerun_app, f"hydra.run.dir={output_dir}", "foo=${db.mysql_only}")
    result = run_app(
        rerun_app, "--experimental-rerun", str(output_dir), "db.mysql_only=6"
    )
    assert result["config"]["foo"] == 6


@mark.skipif(os.name != "posix", reason="backslash is a valid POSIX path character")
def test_rerun_reuses_original_dir_with_backslash(
    rerun_app: Path, tmp_path: Path
) -> None:
    original_dir = tmp_path / "original\\backslash"
    quoted_dir = QuotedString(str(original_dir), Quote.double).with_quotes()
    run_app(rerun_app, f"hydra.run.dir={quoted_dir}")
    run_app(rerun_app, "--experimental-rerun", str(original_dir), "foo=2")
    assert OmegaConf.load(original_dir / ".hydra" / "config.yaml").foo == 2


@mark.parametrize(
    "overrides,error",
    [
        (["-m"], "does not support --multirun"),
        (["hydra.mode=MULTIRUN"], "hydra.mode changed during config composition"),
        (["foo=3,4"], "Ambiguous value for argument"),
        (["--config-name=config"], "does not support --config-name"),
    ],
)
def test_rerun_rejects_unsupported_arguments(
    rerun_app: Path, tmp_path: Path, overrides: list[str], error: str
) -> None:
    output_dir = tmp_path / "original"
    run_app(rerun_app, f"hydra.run.dir={output_dir}")
    _, stderr = run_python_script(
        [str(rerun_app), "--experimental-rerun", str(output_dir)] + overrides,
        raise_exception=False,
        print_error=False,
    )
    assert error in stderr

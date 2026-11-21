# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved
from pathlib import Path

from hydra.test_utils.test_utils import chdir_hydra_root, run_python_script

chdir_hydra_root()


def _run_app(arguments: list[str]) -> tuple[str, str]:
    stdout, stderr = run_python_script(
        [
            "-Wdefault:Hydra plugin:FutureWarning",
            "tests/test_apps/custom_env_defaults/my_app.py",
            *arguments,
        ]
    )
    assert "TestEnvDefaultSearchPathPlugin' relies on deprecated" in stderr
    return stdout, stderr


def test_env_defaults(tmpdir: Path) -> None:
    cmd = [
        f'hydra.run.dir="{str(tmpdir)}"',
        "hydra.job.chdir=True",
    ]
    _run_app(cmd)


def test_named_env_defaults() -> None:
    stdout, _ = _run_app(
        [
            "hydra/env=campus",
            "--cfg",
            "hydra",
        ]
    )
    assert "FOO: campus" in stdout
    assert "dir: ./campus_outputs" in stdout


def test_named_env_defaults_from_application_config() -> None:
    stdout, _ = _run_app(
        [
            "--config-path=conf",
            "--config-name=config",
            "--cfg",
            "hydra",
        ]
    )
    assert "FOO: campus" in stdout


def test_application_overrides_env_defaults() -> None:
    stdout, _ = _run_app(
        [
            "--config-path=conf",
            "--config-name=app_override",
            "--cfg",
            "hydra",
        ]
    )
    assert "FOO: app" in stdout

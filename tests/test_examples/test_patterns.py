# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved
from pathlib import Path
from textwrap import dedent
from typing import Any

from omegaconf import OmegaConf
from pytest import mark, param

from hydra.test_utils.test_utils import (
    TTaskRunner,
    assert_text_same,
    chdir_hydra_root,
    run_python_script,
    run_with_error,
    verify_dir_outputs,
)

chdir_hydra_root()


def test_specializing_config_example(
    hydra_restore_singletons: Any, hydra_task_runner: TTaskRunner
) -> None:
    with hydra_task_runner(
        calling_file="examples/patterns/specializing_config/example.py",
        calling_module=None,
        config_path="conf",
        config_name="config.yaml",
        overrides=["dataset=cifar10"],
        configure_logging=True,
    ) as task:
        assert task.job_ret is not None and task.job_ret.cfg == dict(
            dataset=dict(name="cifar10", path="/datasets/cifar10"),
            model=dict(num_layers=5, type="alexnet"),
        )
        verify_dir_outputs(task.job_ret, overrides=task.overrides)


def test_write_protect_config_node(tmpdir: Any) -> None:
    cmd = [
        "examples/patterns/write_protect_config_node/frozen.py",
        f'hydra.run.dir="{str(tmpdir)}"',
        "hydra.job.chdir=True",
        "data_bits=10",
    ]

    expected = dedent("""\
        Error merging override data_bits=10
        Cannot change read-only config container
            full_key: data_bits
            object_type=SerialPort
        """)
    err = run_with_error(cmd)
    assert_text_same(from_line=expected, to_line=err)


@mark.parametrize(
    "overrides",
    [
        param(["db=mysql_extending_from_this_group"], id="from_same_group"),
        param(["db=mysql_extending_from_another_group"], id="from_different_group"),
    ],
)
def test_extending_configs(
    monkeypatch: Any, tmpdir: Path, overrides: list[str]
) -> None:
    monkeypatch.chdir("examples/patterns/extending_configs")
    cmd = [
        "my_app.py",
        f'hydra.run.dir="{str(tmpdir)}"',
        "hydra.job.chdir=True",
    ] + overrides
    result, _err = run_python_script(cmd)
    assert OmegaConf.create(result) == {
        "db": {
            "host": "localhost",
            "port": 3307,
            "user": "omry",
            "password": "secret",
            "encoding": "utf8",
        }
    }


@mark.parametrize(
    ("overrides", "expected"),
    [
        param(
            [],
            {"db": {"name": "mysql"}, "server": {"name": "apache", "port": 80}},
            id="default",
        ),
        param(
            ["+experiment=nglite"],
            {"db": {"name": "sqlite"}, "server": {"name": "nginx", "port": 8080}},
            id="exp1",
        ),
        param(
            ["+experiment=nglite", "server=apache"],
            {"db": {"name": "sqlite"}, "server": {"name": "apache", "port": 8080}},
            id="exp1+override",
        ),
    ],
)
def test_configuring_experiments(
    monkeypatch: Any, tmpdir: Path, overrides: list[str], expected: Any
) -> None:
    monkeypatch.chdir("examples/patterns/configuring_experiments")
    cmd = [
        "my_app.py",
        f'hydra.run.dir="{str(tmpdir)}"',
        "hydra.job.chdir=True",
    ] + overrides
    result, _err = run_python_script(cmd)
    assert OmegaConf.create(result) == expected


@mark.parametrize(
    ("overrides", "expected"),
    [
        param(
            [],
            {
                "server": {
                    "site": {
                        "fb": {"domain": "facebook.com"},
                        "google": {"domain": "google.com"},
                    },
                    "host": "localhost",
                    "port": 443,
                }
            },
            id="default",
        ),
        param(
            ["server/site=[amazon,google]"],
            {
                "server": {
                    "site": {
                        "amazon": {"domain": "amazon.com"},
                        "google": {"domain": "google.com"},
                    },
                    "host": "localhost",
                    "port": 443,
                }
            },
            id="default:override",
        ),
    ],
)
def test_multi_select(
    monkeypatch: Any, tmpdir: Path, overrides: list[str], expected: Any
) -> None:
    monkeypatch.chdir("examples/patterns/multi-select")
    cmd = [
        "my_app.py",
        f'hydra.run.dir="{str(tmpdir)}"',
        "hydra.job.chdir=True",
    ] + overrides
    result, _err = run_python_script(cmd)
    assert OmegaConf.create(result) == expected
